#!/usr/bin/env bash
# Tear down lab and clean up resources
set -euo pipefail

echo "=========================================="
echo "  Tearing Down Data Center Fabric Lab     "
echo "=========================================="

export PYTHONPATH="${PYTHONPATH:-}:src"
python3 -m netauto down --cleanup
