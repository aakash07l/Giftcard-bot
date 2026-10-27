"""
Configuration settings for PlayStation 4K Gift Card Telegram Bot.
Handles environment variables, platform URLs, denominations, admin authorization, and browser settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables
load_dotenv(dotenv_path=ENV_PATH)

# Telegram Bot Token (Dedicated 4K PlayStation Bot)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    BOT_TOKEN = "8918128794:AAFYwsRDHm--pZwe9jm9pnBQe0PWUve4nck"

# Authorized Admin / User Chat IDs for Multiple Telegram Users
DEFAULT_ADMIN_CHAT_IDS = [5701727023, 1988639571, 828429985, 8801210593]
raw_admin_ids = os.getenv("ADMIN_CHAT_IDS", "").strip()
if raw_admin_ids:
    ADMIN_CHAT_IDS = [
        int(x.strip()) for x in raw_admin_ids.split(",")
        if x.strip().lstrip("-").isdigit()
    ]
else:
    ADMIN_CHAT_IDS = list(DEFAULT_ADMIN_CHAT_IDS)

# Target Denomination: Exclusively ₹4,000 PlayStation Card
TARGET_DENOMINATION = int(os.getenv("TARGET_DENOMINATION", "4000"))
DEFAULT_DENOMINATIONS = [TARGET_DENOMINATION]

# Maximum cards to purchase per account (default: 2 cards = ₹8,000 if balance >= ₹8,000)
MAX_CARDS_PER_ACCOUNT = int(os.getenv("MAX_CARDS_PER_ACCOUNT", "2"))

# Simulation / Dry Run mode (safe mode for testing without real card debit)
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "False").lower() in ("true", "1", "yes")

# Application Environment
ENV = os.getenv("ENV", "production").lower()

# Browser Configuration
HEADLESS = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes")
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "45000"))

# Rooter Account Credentials / Auth Details (Supports 1 to 30 Accounts)
def get_env_tokens() -> list:
    """Retrieves list of all configured Rooter tokens from environment variables (1 to 30 accounts)."""
    tokens = []
    for i in range(1, 31):
        tok = (
            os.getenv(f"ROOTER_TOKEN_{i}", "")
            or os.getenv(f"ROOTER_AUTH_TOKEN_{i}", "")
        ).strip()
        if tok and len(tok) > 20 and tok not in tokens:
            tokens.append(tok)

    multi_raw = os.getenv("ROOTER_TOKENS", "").strip()
    if multi_raw:
        for t in multi_raw.replace("\n", ",").split(","):
            cleaned = t.strip()
            if cleaned and len(cleaned) > 20 and cleaned not in tokens:
                tokens.append(cleaned)

    # Only fallback to single ROOTER_AUTH_TOKEN if no indexed tokens are defined
    if not tokens:
        single_tok = os.getenv("ROOTER_AUTH_TOKEN", "").strip()
        if single_tok and len(single_tok) > 20:
            tokens.append(single_tok)

    return tokens

ROOTER_MOBILE = os.getenv("ROOTER_MOBILE", "").strip()
ROOTER_AUTH_TOKENS = get_env_tokens()
ROOTER_AUTH_TOKEN = ROOTER_AUTH_TOKENS[0] if ROOTER_AUTH_TOKENS else os.getenv("ROOTER_AUTH_TOKEN", "").strip()

# Directories
SESSION_DIR = BASE_DIR / "sessions"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Rooter Product URLs
ROOTER_PLAYSTATION_URL = "https://shop.rooter.gg/product/playstation-gift-cards"

# Supported Platforms (PlayStation Only, ₹4,000 Exclusively)
PLATFORMS = {
    "rooter": {
        "name": "Rooter Shop",
        "url": ROOTER_PLAYSTATION_URL,
        "search_query": "PlayStation Gift Cards",
        "description": "PlayStation voucher marketplace (₹4,000 Exclusively)",
        "supported_denominations": [TARGET_DENOMINATION],
    },
}

# Auto-Sniper Restock Refresh Interval in Seconds (Default: 29s)
SNIPE_INTERVAL_SECONDS = int(os.getenv("SNIPE_INTERVAL_SECONDS", "29"))

# Periodic Heartbeat Notifications in Chat
ENABLE_SNIPER_HEARTBEAT = os.getenv("ENABLE_SNIPER_HEARTBEAT", "False").lower() in ("true", "1", "yes")

# Resource Optimization: Block images and media in headless browser to minimize RAM/CPU usage on Railway
BLOCK_MEDIA_RESOURCES = os.getenv("BLOCK_MEDIA_RESOURCES", "True").lower() in ("true", "1", "yes")
