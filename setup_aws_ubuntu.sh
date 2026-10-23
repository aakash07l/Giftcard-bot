#!/bin/bash
# ==============================================================================
# Automated 1-Click Setup Script for AWS EC2 (Ubuntu 22.04 / 24.04 LTS)
# PlayStation Gift Card Sniper Bot - 24/7 Ultra Low RAM Mode
# ==============================================================================

set -e

echo "=================================================================="
echo "🚀 Setting up PlayStation Gift Card Sniper Bot on AWS Ubuntu..."
echo "=================================================================="

# 1. Setup 2GB SWAP Memory (Crucial for 1GB t2.micro / t3.micro Free Tier)
SWAP_EXISTS=$(swapon --show | wc -l)
if [ "$SWAP_EXISTS" -le 1 ]; then
    echo "⚙️ Creating 2GB Swap file to prevent Out-Of-Memory on 1GB RAM..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    sudo sysctl vm.swappiness=10
    echo "✅ 2GB Swap created and active!"
else
    echo "✅ Swap is already configured."
fi

# 2. Update packages & install Python, Git, and Chromium dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl fonts-liberation

# Install sound library (libasound2t64 on Ubuntu 24.04+, libasound2 on 22.04)
sudo apt-get install -y libasound2t64 || sudo apt-get install -y libasound2 || true

# 3. Create Python Virtual Environment
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing Python libraries & Playwright..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 4. Install Playwright Chromium headless binary and system dependencies
echo "🌐 Installing Chromium browser and system libraries for Playwright..."
./venv/bin/python -m playwright install --with-deps chromium || ./venv/bin/python -m playwright install chromium

# 5. Create directories
mkdir -p sessions screenshots

# 6. Setup Systemd Service for 24/7 Auto-Restart
SERVICE_FILE="/etc/systemd/system/psgiftcardbot.service"
echo "⚙️ Configuring systemd service at $SERVICE_FILE..."

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=PlayStation Gift Card Sniper Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=HEADLESS=True
Environment=BLOCK_MEDIA_RESOURCES=True

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable psgiftcardbot.service

echo "=================================================================="
echo "🎉 SETUP COMPLETED SUCCESSFULLY!"
echo "=================================================================="
echo ""
echo "👉 Next Steps:"
echo "1. Edit your .env file with your tokens:"
echo "   nano .env"
echo ""
echo "2. Start the 24/7 background service:"
echo "   sudo systemctl start psgiftcardbot"
echo ""
echo "3. View live bot logs:"
echo "   sudo journalctl -u psgiftcardbot -f"
echo ""
echo "4. Stop or restart bot:"
echo "   sudo systemctl restart psgiftcardbot"
echo "   sudo systemctl stop psgiftcardbot"
echo "=================================================================="
