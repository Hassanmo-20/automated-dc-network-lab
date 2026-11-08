#!/usr/bin/env bash
# Deploy the Data Center fabric lab
set -euo pipefail

echo "=========================================="
echo "  Deploying Automated Data Center Fabric  "
echo "=========================================="

export PYTHONPATH="${PYTHONPATH:-}:src"
python3 -m netauto validate-inventory
python3 -m netauto render
python3 -m netauto up

echo "[✓] Deployment completed."
