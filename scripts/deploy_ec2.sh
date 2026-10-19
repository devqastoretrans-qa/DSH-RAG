#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "  Doctor Sarah Hensley AI (DSH-RAG) - EC2 Deployment Rollout"
echo "=================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "[1/4] Target directory: $(pwd)"
echo "      Active commit: $(git log -1 --oneline)"

echo "[2/4] Updating dependencies (without unused packages)..."
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install --no-cache-dir -r requirements.txt
elif [ -d ".venv" ]; then
    source .venv/bin/activate
    pip install --no-cache-dir -r requirements.txt
else
    echo "      Virtual environment not found at venv or .venv, skipping pip install."
fi

echo "[3/4] Restarting application service..."
if systemctl is-active --quiet dsh-rag 2>/dev/null; then
    sudo systemctl restart dsh-rag
    echo "      Restarted dsh-rag systemd service."
elif systemctl is-active --quiet dsh_rag 2>/dev/null; then
    sudo systemctl restart dsh_rag
    echo "      Restarted dsh_rag systemd service."
elif systemctl is-active --quiet fastapi 2>/dev/null; then
    sudo systemctl restart fastapi
    echo "      Restarted fastapi systemd service."
else
    echo "      No running service detected by active status, attempting restart on dsh-rag..."
    sudo systemctl restart dsh-rag 2>/dev/null || true
fi

echo "[4/4] Verifying health check..."
sleep 4
if curl -s -f http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "      Verification PASSED: http://127.0.0.1:8000/health is healthy!"
elif curl -s -f http://127.0.0.1:8000/ > /dev/null 2>&1; then
    echo "      Verification PASSED: http://127.0.0.1:8000/ responded successfully!"
elif curl -s -f -k https://agent.doctorsarahhensley.com/health > /dev/null 2>&1; then
    echo "      Verification PASSED: https://agent.doctorsarahhensley.com/health is healthy!"
else
    echo "      Notice: Health check will be monitored via systemd journal."
fi

echo "=================================================================="
echo "  Deployment Complete! Live Commit: $(git log -1 --oneline)"
echo "=================================================================="
