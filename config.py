"""
Configuration settings for PlayStation Gift Card Telegram Bot.
Handles environment variables, platform URLs, denominations, and browser settings.
Optimized for multi-account concurrency and Railway deployment.
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
    BOT_TOKEN = "8975433711:AAFk_OxMHcTR67JyXsbLwI1l4Ougm69z82I"

# Authorized Admin Chat ID for restricted commands (e.g. /snipe amazon 1)
_raw_admin_id = os.getenv("ADMIN_CHAT_ID", "").strip()
try:
    ADMIN_CHAT_ID = int(_raw_admin_id) if _raw_admin_id else 0
except (ValueError, TypeError):
    ADMIN_CHAT_ID = 0

# Simulation / Dry Run mode (safe mode for testing without real card debit)
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "False").lower() in ("true", "1", "yes")

# Application Environment
ENV = os.getenv("ENV", "production").lower()

# Browser Configuration
HEADLESS = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes")
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "45000"))

# Rooter Account Credentials / Auth Details
ROOTER_MOBILE = os.getenv("ROOTER_MOBILE", "916265656481").strip()
ROOTER_AUTH_TOKEN = os.getenv(
    "ROOTER_AUTH_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjIxMDQ2NjM3NzMsInNJZCI6IjVkMWYyNDZiLWMyMTQtNDk2Mi1iMGM3LTQ5MGU0N2I4OGM3NyIsInJvbGVzIjpbXSwiZGV2aWNlIjoid2ViIiwic2ZDcmVhdGVkQXQiOjE3OTIwMzY0MTAsImlzVmVyaWZpZWQiOnRydWUsInVzZXJSb2xlcyI6e30sImlhdCI6MTc5MjAzNjg3OSwiZXhwIjoxNzk1OTI0ODc5fQ.kVdk_tDxFgl8jU0J8J35KQHRFiKJ4rDhSfkMl4YN2jQ"
).strip()
ROOTER_TOKENS = os.getenv("ROOTER_TOKENS", "").strip()
ROOTER_ACCOUNTS_JSON = os.getenv("ROOTER_ACCOUNTS_JSON", "").strip()

# Directories
SESSION_DIR = BASE_DIR / "sessions"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Product URLs (PlayStation Primary, Amazon Pay for Admin Health-Check)
ROOTER_PLAYSTATION_URL = "https://shop.rooter.gg/product/playstation-gift-cards"
ROOTER_AMAZON_PAY_URL = "https://shop.rooter.gg/product/amazon-pay-gift-cards"

# Supported Platforms (PlayStation Only)
PLATFORMS = {
    "rooter": {
        "name": "Rooter Shop",
        "url": ROOTER_PLAYSTATION_URL,
        "amazon_url": ROOTER_AMAZON_PAY_URL,
        "search_query": "PlayStation Gift Cards",
        "description": "PlayStation Gift Card Auto-Buyer (₹1k-₹5k)",
        "supported_denominations": [1000, 2000, 3000, 4000, 5000],
    },
}

DEFAULT_DENOMINATIONS = [1000, 2000, 3000, 4000, 5000]

# Auto-Sniper Restock Refresh Interval in Seconds (Default: 20s for fast restock grab)
SNIPE_INTERVAL_SECONDS = int(os.getenv("SNIPE_INTERVAL_SECONDS", "20"))

# Periodic Heartbeat Notifications in Chat
ENABLE_SNIPER_HEARTBEAT = os.getenv("ENABLE_SNIPER_HEARTBEAT", "False").lower() in ("true", "1", "yes")

# Resource Optimization: Block images/videos in headless browser to minimize RAM/CPU usage on Railway
BLOCK_MEDIA_RESOURCES = os.getenv("BLOCK_MEDIA_RESOURCES", "True").lower() in ("true", "1", "yes")
