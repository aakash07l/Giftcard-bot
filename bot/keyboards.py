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
            InlineKeyboardButton("🎯 Auto-Snipe Stock (24/7)", callback_data="snipe_start"),
            InlineKeyboardButton("🛒 Instant Buy Now", callback_data="buy_start"),
        ],
        [
            InlineKeyboardButton("🔑 Account Login", callback_data="login_start"),
            InlineKeyboardButton("📊 Status & Sessions", callback_data="status_check"),
        ],
        [
            InlineKeyboardButton("⚙️ Toggle Sim Mode", callback_data="toggle_sim"),
            InlineKeyboardButton("📖 Help & Guide", callback_data="help_info"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_stop_snipe_keyboard() -> InlineKeyboardMarkup:
    """Keyboard to cancel active auto-sniper."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Stop Auto-Sniper", callback_data="stop_snipe_action")]
    ])

def get_platforms_keyboard(prefix: str = "plat_select") -> InlineKeyboardMarkup:
    """Keyboard for platform selection (Rooter Shop)."""
    keyboard = [
        [
            InlineKeyboardButton("🎯 Rooter Shop (PlayStation Vouchers)", callback_data=f"{prefix}:rooter"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_login_methods_keyboard(platform: str = "rooter") -> InlineKeyboardMarkup:
    """Keyboard to pick login method: interactive Phone+OTP or Paste Session Cookies."""
    keyboard = [
        [
            InlineKeyboardButton("📱 Interactive Phone + OTP", callback_data="login_method:rooter:phone"),
        ],
        [
            InlineKeyboardButton("🍪 Paste Cookie / Session JSON", callback_data="login_method:rooter:cookie"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_denominations_keyboard(platform: str = "rooter", denominations: List[int] = None) -> InlineKeyboardMarkup:
    """Keyboard to pick PlayStation or Google Play voucher denomination."""
    if not denominations:
        platform_info = config.PLATFORMS.get("rooter", {})
        denominations = platform_info.get("supported_denominations", config.DEFAULT_DENOMINATIONS)

    rows = []
    # Test buy button for ₹10 Google Play Code
    if 10 in denominations:
        rows.append([
            InlineKeyboardButton("🧪 ₹10 Google Play (1-Time Real Test Buy)", callback_data="denom_pick:rooter:10")
        ])

    ps_denoms = [d for d in denominations if d != 10]
    current_row = []
    for denom in ps_denoms:
        btn = InlineKeyboardButton(f"🎮 ₹{denom:,} PSN", callback_data=f"denom_pick:rooter:{denom}")
        current_row.append(btn)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows.append([
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav_main_menu"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
    ])
    return InlineKeyboardMarkup(rows)

def get_snipe_denominations_keyboard(platform: str = "rooter", denominations: List[int] = None) -> InlineKeyboardMarkup:
    """Keyboard to pick voucher denomination for Auto-Sniper."""
    if not denominations:
        platform_info = config.PLATFORMS.get("rooter", {})
        denominations = platform_info.get("supported_denominations", config.DEFAULT_DENOMINATIONS)

    rows = []
    # Test buy button for ₹10 Google Play Code
    if 10 in denominations:
        rows.append([
            InlineKeyboardButton("🧪 ₹10 Google Play (1-Time Real Test Snipe)", callback_data="snipe_denom:rooter:10")
        ])

    ps_denoms = [d for d in denominations if d != 10]
    current_row = []
    for denom in ps_denoms:
        btn = InlineKeyboardButton(f"🎮 ₹{denom:,} PSN", callback_data=f"snipe_denom:rooter:{denom}")
        current_row.append(btn)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows.append([
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav_main_menu"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
    ])
    return InlineKeyboardMarkup(rows)


def get_confirmation_keyboard(platform: str = "rooter", denomination: int = 1000) -> InlineKeyboardMarkup:
    """Keyboard to confirm purchase before triggering Playwright headless checkout."""
    label = "🚀 Confirm & Buy Google Play ₹10" if denomination == 10 else f"🚀 Confirm & Buy PlayStation ₹{denomination:,}"
    keyboard = [
        [
            InlineKeyboardButton(label, callback_data=f"confirm_buy:rooter:{denomination}"),
        ],
        [
            InlineKeyboardButton("🔙 Change Denomination", callback_data="buy_start"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_alternate_platform_keyboard(current_platform: str = "rooter", denomination: int = 1000) -> InlineKeyboardMarkup:
    """Menu navigation fallback."""
    keyboard = [
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Simple cancel button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
    ])
