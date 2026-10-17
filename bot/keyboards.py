"""
Telegram inline keyboards for the PlayStation Gift Card Buyer Bot.
Provides rich interactive UI buttons for platform selection, denominations, login modes, and confirmations.
"""

from typing import List, Dict, Any, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the main menu dashboard keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🎯 Auto-Snipe PlayStation (24/7)", callback_data="snipe_start"),
            InlineKeyboardButton("🛒 Instant Buy PSN", callback_data="buy_start"),
        ],
        [
            InlineKeyboardButton("👥 Manage Accounts (5-10 AC)", callback_data="accounts_view"),
            InlineKeyboardButton("📊 Status & Sessions", callback_data="status_check"),
        ],
        [
            InlineKeyboardButton("🛑 Stop Play Store / Auto-Sniper", callback_data="stop_playstore_action"),
            InlineKeyboardButton("⚙️ Toggle Sim Mode", callback_data="toggle_sim"),
        ],
        [
            InlineKeyboardButton("🔑 Account Login / Token", callback_data="login_start"),
            InlineKeyboardButton("📖 Help & Guide", callback_data="help_info"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_accounts_keyboard(accounts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Builds interactive keyboard for managing multiple accounts."""
    rows = [
        [
            InlineKeyboardButton("➕ Add Account (Token)", callback_data="acc_add_prompt"),
            InlineKeyboardButton("🔄 Refresh Balances", callback_data="accounts_view"),
        ]
    ]
    for acc in accounts:
        status_icon = "🟢" if acc.get("is_active", True) else "⏸️"
        label = acc.get("label", acc.get("id"))
        bal = float(acc.get("wallet_balance", 0.0))
        btn_text = f"{status_icon} {label} (₹{bal:,.0f})"
        rows.append([
            InlineKeyboardButton(btn_text, callback_data=f"acc_toggle:{acc['id']}"),
            InlineKeyboardButton("❌ Remove", callback_data=f"acc_remove:{acc['id']}"),
        ])
    rows.append([
        InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu"),
    ])
    return InlineKeyboardMarkup(rows)

def get_stop_snipe_keyboard() -> InlineKeyboardMarkup:
    """Keyboard to cancel active auto-sniper or stop Play Store."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Stop Auto-Sniper", callback_data="stop_snipe_action")],
        [InlineKeyboardButton("🛑 Stop Play Store (PS Only)", callback_data="stop_playstore_action")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu")],
    ])

def get_playstore_stopped_keyboard() -> InlineKeyboardMarkup:
    """Keyboard displayed after stopping Play Store buying."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Auto-Snipe Any PlayStation Card", callback_data="snipe_denom:rooter:0")],
        [InlineKeyboardButton("🎮 Select Specific PSN Card", callback_data="snipe_start")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="nav_main_menu")],
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
    """Keyboard to pick PlayStation voucher denomination (PlayStation Only)."""
    if not denominations:
        platform_info = config.PLATFORMS.get("rooter", {})
        denominations = platform_info.get("supported_denominations", config.DEFAULT_DENOMINATIONS)

    # Filter to strictly PlayStation (exclude any test/google play codes)
    ps_denoms = [d for d in denominations if d >= 1000]

    rows = []
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
        InlineKeyboardButton("🛑 Stop Play Store (PS Only)", callback_data="stop_playstore_action"),
    ])
    rows.append([
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav_main_menu"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
    ])
    return InlineKeyboardMarkup(rows)

def get_snipe_denominations_keyboard(platform: str = "rooter", denominations: List[int] = None) -> InlineKeyboardMarkup:
    """Keyboard to pick voucher denomination for Auto-Sniper (PlayStation Only)."""
    if not denominations:
        platform_info = config.PLATFORMS.get("rooter", {})
        denominations = platform_info.get("supported_denominations", config.DEFAULT_DENOMINATIONS)

    rows = [
        [
            InlineKeyboardButton("⚡ Any PlayStation Card (₹1k - ₹5k Auto)", callback_data="snipe_denom:rooter:0")
        ]
    ]

    ps_denoms = [d for d in denominations if d >= 1000]
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
        InlineKeyboardButton("🛑 Stop Play Store (PS Only)", callback_data="stop_playstore_action"),
    ])
    rows.append([
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav_main_menu"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_action"),
    ])
    return InlineKeyboardMarkup(rows)


def get_confirmation_keyboard(platform: str = "rooter", denomination: int = 1000) -> InlineKeyboardMarkup:
    """Keyboard to confirm purchase before triggering Playwright headless checkout."""
    label = f"🚀 Confirm & Buy PlayStation ₹{denomination:,}"
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
