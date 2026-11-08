#!/usr/bin/env bash
# Quick-start setup script for Ubuntu / WSL2 Ubuntu environments
set -euo pipefail

echo "==============================================="
echo " Setting up Containerlab & Network Lab Tools   "
echo "==============================================="

# 1. Update APT
sudo apt-get update -y
sudo apt-get install -y curl git python3 python3-pip python3-venv iproute2 iputils-ping

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "[*] Installing Docker Engine..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    echo "[✓] Docker installed. You may need to log out and back in for group changes."
fi

# 3. Install Containerlab if not present
if ! command -v clab &> /dev/null; then
    echo "[*] Installing Containerlab..."
    bash -c "$(curl -sL https://get.containerlab.dev)"
    echo "[✓] Containerlab installed successfully."
fi

# 4. Set up Python environment
echo "[*] Installing Python dependencies..."
python3 -m pip install -r requirements.txt || python3 -m pip install --break-system-packages -e .

echo "==============================================="
echo " Environment setup complete!                   "
echo " Run: ./scripts/deploy.sh                     "
echo "==============================================="
