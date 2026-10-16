"""
Configuration settings for PlayStation Gift Card Telegram Bot.
Handles environment variables, platform URLs, denominations, and browser settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables
load_dotenv(dotenv_path=ENV_PATH)

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    # Fallback to provided token if not in environment
    BOT_TOKEN = "8975433711:AAFk_OxMHcTR67JyXsbLwI1l4Ougm69z82I"

# Simulation / Dry Run mode (safe mode for testing without real card debit)
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "True").lower() in ("true", "1", "yes")

# Application Environment
ENV = os.getenv("ENV", "production").lower()

# Browser Configuration
HEADLESS = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes")
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "45000"))

# Rooter Account Credentials / Auth Details
ROOTER_MOBILE = os.getenv("ROOTER_MOBILE", "").strip()
ROOTER_AUTH_TOKEN = os.getenv("ROOTER_AUTH_TOKEN", "").strip()

# Directories
SESSION_DIR = BASE_DIR / "sessions"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Supported Platforms
PLATFORMS = {
    "rooter": {
        "name": "Rooter Shop",
        "url": "https://shop.rooter.gg/product/playstation-gift-cards",
        "search_query": "PlayStation",
        "description": "Gaming and esports voucher marketplace",
        "supported_denominations": [1000, 2000, 3000, 4000, 5000],
    },
}

DEFAULT_DENOMINATIONS = [1000, 2000, 3000, 4000, 5000]

# Auto-Sniper Restock Refresh Interval in Seconds (Default: 30s)
SNIPE_INTERVAL_SECONDS = int(os.getenv("SNIPE_INTERVAL_SECONDS", "30"))

# Periodic Heartbeat Notifications in Chat (Set to False to avoid spam and save credit)
ENABLE_SNIPER_HEARTBEAT = os.getenv("ENABLE_SNIPER_HEARTBEAT", "False").lower() in ("true", "1", "yes")

# Resource Optimization: Block images and media in headless browser to minimize RAM/CPU usage on Railway
BLOCK_MEDIA_RESOURCES = os.getenv("BLOCK_MEDIA_RESOURCES", "True").lower() in ("true", "1", "yes")

