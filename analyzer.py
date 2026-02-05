"""
Contract analysis using Claude API.
Returns structured JSON matching the t3rms frontend format.
"""

import json
import os
from typing import Optional
from anthropic import Anthropic


SYSTEM_PROMPT = """You are a contract risk analyst evaluating agreements FROM THE SUPPLIER/VENDOR PERSPECTIVE.
Your job is to identify clauses that are unfavorable, risky, or one-sided against the supplier who would be signing this agreement.

Evaluate every section of the contract for risks in these categories:
- Indemnification: unlimited liability exposure, broad hold-harmless clauses
- Liability caps: missing caps, consequential damages, liquidated damages
- IP ownership: work-for-hire, assignment of rights, perpetual licenses
- Payment terms: net 60/90/120, pay-when-paid, retainage
- Termination: asymmetric rights, convenience termination, short cure periods
- Warranties: extended periods, implied warranties, fitness for purpose
- Insurance: excessive requirements, additional insured obligations
- Confidentiality: perpetual obligations, broad definitions
- Force majeure: missing or one-sided clauses
- Non-compete/non-solicitation: overly broad restrictions
- Audit rights: unlimited access, frequency
- Governing law/jurisdiction: unfavorable venue

For EVERY finding, you MUST cite the exact text from the contract.

Respond with ONLY valid JSON in this exact format (no markdown, no explanation outside JSON):
{
  "overallScore": <number 0-100, where 100 means lowest risk>,
  "overallRisk": "<red|yellow|green>",
  "executiveSummary": "<2-3 sentence summary of key risks for the supplier>",
  "criticalPoints": [
    {
      "title": "<short title>",
      "description": "<why this is risky for the supplier>",
      "severity": "<high|medium|low>",
      "reference": {
        "section": "<section name/number if identifiable, or null>",
        "excerpt": "<exact quote from the contract>"
      },
      "suggestedRedline": "<recommended replacement language or null>"
    }
  ],
  "financialRisks": [
    {
      "title": "<short title>",
      "description": "<financial risk explanation>",
      "severity": "<high|medium|low>",
      "reference": {
        "section": "<section name/number or null>",
        "excerpt": "<exact quote>"
      },
      "suggestedRedline": "<recommended replacement or null>"
    }
  ],
  "unusualLanguage": [
    {
      "title": "<short title>",
      "description": "<why this language is unusual or concerning>",
      "severity": "<high|medium|low>",
      "reference": {
        "section": "<section name/number or null>",
        "excerpt": "<exact quote>"
      },
      "suggestedRedline": "<recommended replacement or null>"
    }
  ],
  "indemnification": [
    {
      "title": "<short title>",
      "description": "<indemnification risk>",
      "severity": "<high|medium|low>",
      "reference": {
        "section": "<section or null>",
        "excerpt": "<exact quote>"
      },
      "suggestedRedline": "<replacement or null>"
    }
  ],
  "liability": [
    {
      "title": "<short title>",
      "description": "<liability risk>",
      "severity": "<high|medium|low>",
      "reference": {
        "section": "<section or null>",
        "excerpt": "<exact quote>"
      },
      "suggestedRedline": "<replacement or null>"
    }
  ],
  "recommendations": [
    {
      "text": "<specific actionable recommendation>",
      "priority": "<high|medium|low>",
      "reference": {
        "section": "<related section or null>"
      }
    }
  ],
  "redlinesSummary": [
    {
      "originalText": "<problematic text from contract>",
      "suggestedRevision": "<improved language>",
      "rationale": "<why this change protects the supplier>"
    }
  ]
}

Rules:
- overallScore: 0-30 = red (high risk), 31-60 = yellow (moderate), 61-100 = green (acceptable)
- Every finding MUST include a direct excerpt from the contract text
- severity values must be exactly "high", "medium", or "low" (lowercase)
- If a category has no findings, return an empty array []
- suggestedRedline should provide specific replacement language when possible
- Focus on terms that a SUPPLIER would want to negotiate or reject
- Be thorough but precise - cite exact contract language"""


def analyze_contract(text: str, filename: str = "contract") -> dict:
    """Analyze contract text using Claude and return structured results."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = Anthropic(api_key=api_key)

    # Truncate very long contracts to stay within token limits
    max_chars = 100_000
    truncated = len(text) > max_chars
    analysis_text = text[:max_chars] if truncated else text

    user_message = f"Analyze this contract from the SUPPLIER'S perspective. Identify all risky, unfavorable, or one-sided clauses.\n\nDocument: {filename}\n\nCONTRACT TEXT:\n{analysis_text}"

    if truncated:
        user_message += f"\n\n[NOTE: Document was truncated from {len(text):,} to {max_chars:,} characters. Analysis covers the first portion only.]"

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    content = message.content[0].text

    # Strip markdown code fences if present
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]

    result = json.loads(content.strip())

    # Add metadata
    if truncated:
        result["documentApproach"] = "sampled"
        result["samplingNote"] = f"Document truncated from {len(text):,} to {max_chars:,} characters"
    else:
        result["documentApproach"] = "full"

    # Ensure all required arrays exist
    for key in ("criticalPoints", "financialRisks", "unusualLanguage",
                "indemnification", "liability", "recommendations", "redlinesSummary"):
        if key not in result:
            result[key] = []

    if "overallScore" not in result:
        result["overallScore"] = 50
    if "overallRisk" not in result:
        score = result["overallScore"]
        result["overallRisk"] = "red" if score <= 30 else ("yellow" if score <= 60 else "green")
    if "executiveSummary" not in result:
        result["executiveSummary"] = "Analysis complete."

    return result
