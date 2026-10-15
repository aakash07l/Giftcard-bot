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

# Blinkit Account Credentials / Auth Details
BLINKIT_MOBILE = os.getenv("BLINKIT_MOBILE", "").strip()
BLINKIT_AUTH_TOKEN = os.getenv("BLINKIT_AUTH_TOKEN", "").strip()

# Default Location Settings (Blinkit dark-store localization)
DEFAULT_PINCODE = os.getenv("DEFAULT_PINCODE", "110001")
DEFAULT_LATITUDE = float(os.getenv("DEFAULT_LATITUDE", "28.6304"))
DEFAULT_LONGITUDE = float(os.getenv("DEFAULT_LONGITUDE", "77.2177"))

# Directories
SESSION_DIR = BASE_DIR / "sessions"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Supported Platforms
PLATFORMS = {
    "blinkit": {
        "name": "Blinkit",
        "url": "https://blinkit.com",
        "search_query": "PlayStation Gift Card",
        "description": "Quick commerce 10-minute delivery vouchers",
        "supported_denominations": [500, 1000, 1500, 2500, 4000, 5000],
    },
    "rooter": {
        "name": "Rooter Shop",
        "url": "https://rooter.gg/shop",
        "search_query": "PlayStation",
        "description": "Gaming and esports voucher marketplace",
        "supported_denominations": [500, 1000, 2500, 4000],
    },
}

DEFAULT_DENOMINATIONS = [500, 1000, 1500, 2500, 4000, 5000]
