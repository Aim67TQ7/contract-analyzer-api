#!/bin/bash
set -e

# Contract Analyzer API — VPS Deployment Script
# Deploys to /opt/contract-analyzer/ with venv, systemd, and Caddy

VPS_IP="89.116.157.23"
VPS_USER="root"
DEPLOY_PATH="/opt/contract-analyzer"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Contract Analyzer API Deployment ===${NC}"

# Test SSH
echo "Testing SSH connection..."
if ! ssh -o ConnectTimeout=10 ${VPS_USER}@${VPS_IP} "echo 'Connected'"; then
    echo -e "${RED}SSH connection failed.${NC}"
    exit 1
fi

# Copy files
echo "Copying files to VPS..."
scp main.py analyzer.py parsers.py requirements.txt contract-analyzer.service ${VPS_USER}@${VPS_IP}:${DEPLOY_PATH}/

# Set up venv and install deps
echo "Setting up Python environment..."
ssh ${VPS_USER}@${VPS_IP} << 'REMOTE'
cd /opt/contract-analyzer

# Create venv if missing
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

# Install/update deps
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Ensure .env exists
if [ ! -f .env ]; then
    echo "ANTHROPIC_API_KEY=your-key-here" > .env
    echo "WARNING: Set your ANTHROPIC_API_KEY in /opt/contract-analyzer/.env"
fi

# Install systemd service
cp contract-analyzer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable contract-analyzer
systemctl restart contract-analyzer

echo "Service status:"
systemctl status contract-analyzer --no-pager || true
REMOTE

# Add Caddy config
echo "Configuring Caddy reverse proxy..."
ssh ${VPS_USER}@${VPS_IP} << 'REMOTE'
# Check if contract-api block already exists in Caddyfile
if ! grep -q "contract-api.buntinggpt.com" /etc/caddy/Caddyfile 2>/dev/null; then
    cat >> /etc/caddy/Caddyfile << 'CADDY'

contract-api.buntinggpt.com {
    reverse_proxy localhost:8002
    header {
        Access-Control-Allow-Origin *
        Access-Control-Allow-Methods "GET, POST, OPTIONS"
        Access-Control-Allow-Headers "Content-Type, Authorization"
    }
}
CADDY
    systemctl reload caddy
    echo "Caddy config added and reloaded"
else
    echo "Caddy config already exists"
fi
REMOTE

# Health check
echo "Running health check..."
sleep 3
if ssh ${VPS_USER}@${VPS_IP} "curl -sf http://localhost:8002/health"; then
    echo -e "\n${GREEN}Deployment successful!${NC}"
else
    echo -e "${RED}Health check failed. Check logs:${NC}"
    ssh ${VPS_USER}@${VPS_IP} "journalctl -u contract-analyzer -n 20 --no-pager"
fi

echo ""
echo "Endpoints:"
echo "  Health: https://contract-api.buntinggpt.com/health"
echo "  Analyze: https://contract-api.buntinggpt.com/analyze"
echo ""
echo "Logs: ssh ${VPS_USER}@${VPS_IP} 'journalctl -u contract-analyzer -f'"
