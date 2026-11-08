#!/usr/bin/env bash
# Validate network health and generate reports
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:src"
python3 -m netauto check
