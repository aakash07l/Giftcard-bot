"""
Telegram inline keyboards for the PlayStation Gift Card Buyer Bot.
Provides rich interactive UI buttons for platform selection, denominations, login modes, and confirmations.
"""

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the main menu dashboard keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🛒 Buy PS Gift Card", callback_data="buy_start"),
            InlineKeyboardButton("🔑 Account Login", callback_data="login_start"),
        ],
        [
            InlineKeyboardButton("📊 Session & Balance Status", callback_data="status_check"),
            InlineKeyboardButton("⚙️ Toggle Sim Mode", callback_data="toggle_sim"),
        ],
        [
            InlineKeyboardButton("📖 Help & Commands", callback_data="help_info"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_platforms_keyboard(prefix: str = "plat_select") -> InlineKeyboardMarkup:
    """Keyboard to select between supported voucher platforms (Blinkit, Rooter)."""
    keyboard = [
        [
            InlineKeyboardButton("⚡ Blinkit (10-Min Vouchers)", callback_data=f"{prefix}:blinkit"),
        ],
        [
            InlineKeyboardButton("🎯 Rooter (Gaming Shop)", callback_data=f"{prefix}:rooter"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_login_methods_keyboard(platform: str) -> InlineKeyboardMarkup:
    """Keyboard to pick login method: interactive Phone+OTP or Paste Session Cookies."""
    platform_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())
    keyboard = [
        [
            InlineKeyboardButton("📱 Interactive Phone + OTP", callback_data=f"login_method:{platform}:phone"),
        ],
        [
            InlineKeyboardButton("🍪 Paste Cookie / Session JSON", callback_data=f"login_method:{platform}:cookie"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Platforms", callback_data="login_start"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_denominations_keyboard(platform: str, denominations: List[int] = None) -> InlineKeyboardMarkup:
    """Keyboard to pick PlayStation voucher denomination."""
    if not denominations:
        platform_info = config.PLATFORMS.get(platform, {})
        denominations = platform_info.get("supported_denominations", config.DEFAULT_DENOMINATIONS)

    # 2 buttons per row
    rows = []
    current_row = []
    for denom in denominations:
        btn = InlineKeyboardButton(f"₹{denom:,}", callback_data=f"denom_pick:{platform}:{denom}")
        current_row.append(btn)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows.append([
        InlineKeyboardButton("🔄 Change Platform", callback_data="buy_start"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
    ])
    return InlineKeyboardMarkup(rows)

def get_confirmation_keyboard(platform: str, denomination: int) -> InlineKeyboardMarkup:
    """Keyboard to confirm purchase before triggering Playwright headless checkout."""
    keyboard = [
        [
            InlineKeyboardButton("🚀 Confirm & Buy Now", callback_data=f"confirm_buy:{platform}:{denomination}"),
        ],
        [
            InlineKeyboardButton("🔙 Change Denomination", callback_data=f"buy_plat:{platform}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_alternate_platform_keyboard(current_platform: str, denomination: int) -> InlineKeyboardMarkup:
    """Offers quick fallback when item is Out-of-Stock on one platform."""
    alt_platform = "rooter" if current_platform == "blinkit" else "blinkit"
    alt_name = config.PLATFORMS.get(alt_platform, {}).get("name", alt_platform.title())
    
    keyboard = [
        [
            InlineKeyboardButton(f"🔁 Search on {alt_name} Instead (₹{denomination:,})", callback_data=f"confirm_buy:{alt_platform}:{denomination}"),
        ],
        [
            InlineKeyboardButton("🔙 Main Menu", callback_data="nav_main_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Simple cancel button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
    ])
