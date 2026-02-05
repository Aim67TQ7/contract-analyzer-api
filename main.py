"""
Contract Analyzer API — FastAPI backend for contract intelligence.
Accepts PDF, DOCX, TXT uploads or plain text, returns structured analysis.
"""

import os
import json
import traceback
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from parsers import extract_text
from analyzer import analyze_contract

load_dotenv()

app = FastAPI(
    title="Contract Analyzer API",
    description="Supplier-perspective contract risk analysis powered by Claude",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "contract-analyzer",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "api_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/analyze")
async def analyze(
    file: Optional[UploadFile] = File(None),
    content: Optional[str] = Form(None),
    fileName: Optional[str] = Form("contract.txt"),
    fileType: Optional[str] = Form(None),
):
    """
    Analyze a contract document.

    Accepts either:
    - A file upload (PDF, DOCX, TXT) via multipart form
    - Plain text via the 'content' form field
    - JSON body with { "content": "...", "fileName": "...", "fileType": "..." }
    """
    text = ""
    name = fileName or "contract.txt"

    try:
        if file and file.filename:
            # File upload path
            file_bytes = await file.read()
            if len(file_bytes) == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            if len(file_bytes) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File exceeds 20MB limit")
            name = file.filename
            text = extract_text(file_bytes, name)
        elif content:
            # Text content path
            text = content
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either a file upload or content text",
            )

        if len(text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Contract text too short for meaningful analysis (minimum 50 characters)",
            )

        result = analyze_contract(text, name)
        return result

    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse AI response: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


@app.post("/analyze-json")
async def analyze_json(body: dict):
    """
    Alternative JSON endpoint for text-only analysis.
    Accepts: { "content": "...", "fileName": "...", "fileType": "..." }
    """
    content = body.get("content", "")
    file_name = body.get("fileName", "contract.txt")

    if not content or len(content.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Content text too short for analysis",
        )

    try:
        result = analyze_contract(content, file_name)
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Failed to parse AI response: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8002")))
