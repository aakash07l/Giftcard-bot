"""
Telegram Bot handlers for commands, conversations, and interactive callbacks.
Manages user sessions, live progress notifications, and triggers the Playwright purchase flow.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import config
from bot.states import BotState
from bot.keyboards import (
    get_main_menu_keyboard,
    get_platforms_keyboard,
    get_login_methods_keyboard,
    get_denominations_keyboard,
    get_confirmation_keyboard,
    get_alternate_platform_keyboard,
    get_cancel_keyboard,
)
from services.browser_manager import browser_manager
from services.blinkit_service import BlinkitService
from services.rooter_service import RooterService
from services.base_platform import BasePlatform

logger = logging.getLogger(__name__)

# Register platform services
PLATFORM_SERVICES: Dict[str, BasePlatform] = {
    "blinkit": BlinkitService(),
    "rooter": RooterService(),
}

# Temporary memory store for pending interactive logins
# user_id -> {"platform": str, "otp_event": asyncio.Event, "otp_value": str, "phone": str}
LOGIN_SESSIONS: Dict[int, Dict[str, Any]] = {}

def format_status_text(user_id: int) -> str:
    """Formats current bot status including logged-in platforms and mode."""
    blinkit_logged = "🟢 Logged In" if browser_manager.has_session(user_id, "blinkit") else "🔴 Not Logged In"
    rooter_logged = "🟢 Logged In" if browser_manager.has_session(user_id, "rooter") else "🔴 Not Logged In"
    mode_text = "🧪 Simulation (Dry Run - Safe)" if config.SIMULATION_MODE else "⚡ Live Purchasing"

    return (
        f"🎮 *PlayStation Gift Card Buyer Bot*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Execution Mode:* `{mode_text}`\n"
        f"• *Blinkit Session:* {blinkit_logged}\n"
        f"• *Rooter Session:* {rooter_logged}\n"
        f"• *Delivery Pincode:* `{config.DEFAULT_PINCODE}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Use the buttons below to log into your account or start buying PlayStation vouchers automatically\\."
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user = update.effective_user
    user_id = user.id if user else 0

    welcome_msg = (
        f"👋 *Welcome, {user.first_name if user else 'Gamer'}!*\n\n"
        + format_status_text(user_id)
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=welcome_msg,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=welcome_msg,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    help_text = (
        "📖 *PlayStation Buyer Bot — User Guide*\n\n"
        "⚡ *Commands:*\n"
        "• `/start` — Main dashboard & platform picker\n"
        "• `/buy` — Trigger the automated voucher buying process\n"
        "• `/login` — Store platform session cookies or OTP login\n"
        "• `/status` — View current sessions and configuration\n"
        "• `/toggle_sim` — Switch between Safe Simulation & Live Buy\n"
        "• `/cancel` — Reset active operations\n\n"
        "🛒 *How It Works:*\n"
        "1\\. Choose platform \\(*Blinkit* or *Rooter*\\)\n"
        "2\\. Select your desired denomination \\(₹500, ₹1000, ₹2500, etc\\.\\)\n"
        "3\\. Bot launches a headless Playwright browser, searches for PlayStation vouchers, checks stock, and handles checkout\\.\n"
        "4\\. Voucher Code and PIN are delivered right here in chat\\!"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=help_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=help_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /status command."""
    user_id = update.effective_user.id if update.effective_user else 0
    text = format_status_text(user_id)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )

async def toggle_sim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggles simulation mode on or off."""
    config.SIMULATION_MODE = not config.SIMULATION_MODE
    new_state = "🧪 SIMULATION (Safe Dry Run)" if config.SIMULATION_MODE else "⚡ LIVE PURCHASING (Real Payment)"
    msg = f"⚙️ Mode updated to: *{new_state}*"

    user_id = update.effective_user.id if update.effective_user else 0
    if update.callback_query:
        await update.callback_query.answer(f"Switched to {new_state}")
        await update.callback_query.edit_message_text(
            text=f"{msg}\n\n" + format_status_text(user_id),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

# ==================== BUY WORKFLOW ====================

async def buy_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the buy flow by asking for platform selection."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            text="🛒 *Step 1/3: Choose Platform*\n\nSelect where you want to buy the PlayStation Gift Card from:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_platforms_keyboard(prefix="buy_plat"),
        )
    else:
        await update.message.reply_text(
            text="🛒 *Step 1/3: Choose Platform*\n\nSelect where you want to buy the PlayStation Gift Card from:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_platforms_keyboard(prefix="buy_plat"),
        )
    return BotState.SELECT_BUY_PLATFORM

async def buy_platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Platform selected; now asks for denomination."""
    query = update.callback_query
    await query.answer()

    _, platform = query.data.split(":", 1)
    context.user_data["buy_platform"] = platform

    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())

    await query.edit_message_text(
        text=(
            f"🎯 *Selected Platform:* {plat_name}\n\n"
            f"🛒 *Step 2/3: Select Denomination*\n"
            f"Choose the amount for your PlayStation Gift Card:"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_denominations_keyboard(platform),
    )
    return BotState.SELECT_BUY_DENOMINATION

async def buy_denomination_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Denomination picked; show confirmation dialog."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    platform = parts[1]
    denomination = int(parts[2])

    context.user_data["buy_platform"] = platform
    context.user_data["buy_denomination"] = denomination

    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())
    mode_text = "🧪 SIMULATION (No funds deducted)" if config.SIMULATION_MODE else "⚡ LIVE (Real Checkout)"

    await query.edit_message_text(
        text=(
            f"📝 *Order Confirmation*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Item:* PlayStation Gift Card\n"
            f"• *Platform:* {plat_name}\n"
            f"• *Denomination:* ₹{denomination:,}\n"
            f"• *Mode:* `{mode_text}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Click *Confirm & Buy Now* to trigger the Playwright automation engine\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_confirmation_keyboard(platform, denomination),
    )
    return BotState.AWAITING_CONFIRMATION

async def confirm_buy_execution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs the Playwright headless browser automation with live status updates."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    platform = parts[1]
    denomination = int(parts[2])

    user_id = update.effective_user.id
    service = PLATFORM_SERVICES.get(platform)
    if not service:
        await query.edit_message_text(f"❌ Unsupported platform: {platform}")
        return ConversationHandler.END

    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())

    # Initial live status message
    status_msg = await query.edit_message_text(
        text=f"🔍 *Connecting to Playwright Engine for {plat_name}...*",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Helper callback to send live updates directly to user
    async def progress_notifier(step_text: str, emoji: str = "⚡"):
        try:
            await status_msg.edit_text(
                text=f"{emoji} *{step_text}*\n\n_Automating via Headless Chromium..._",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass

    browser_context = None
    page = None
    try:
        # Launch browser context with stored user session if available
        browser_context = await browser_manager.create_context(
            user_id=user_id,
            platform=platform,
            apply_storage_state=True,
        )
        page = await browser_context.new_page()

        # Run purchase flow
        result = await service.execute_buy_flow(
            page=page,
            denomination=denomination,
            progress_callback=progress_notifier,
            simulation=config.SIMULATION_MODE,
        )

        if result.success:
            sim_badge = " [SIMULATED TEST]" if result.simulation else ""
            success_text = (
                f"🎉 *PURCHASE SUCCESSFUL!*{sim_badge}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎮 *Platform:* {plat_name}\n"
                f"💰 *Denomination:* ₹{result.denomination:,}\n"
                f"🔑 *Voucher Code:*\n`{result.voucher_code}`\n"
                f"🔒 *PIN / Key:*\n`{result.voucher_pin}`\n"
                f"🧾 *Order ID:* `{result.order_id}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ Redeem this on your PlayStation Store console or app\\."
            )
            await status_msg.edit_text(
                text=success_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(),
            )
        else:
            # Capture error screenshot for inspection
            screenshot_path = await browser_manager.capture_screenshot(page, name_prefix=f"err_{platform}")

            fail_text = (
                f"⚠️ *Notice: Purchase Flow Stopped*\n\n"
                f"• *Platform:* {plat_name}\n"
                f"• *Reason:* {result.message}\n\n"
            )

            # Check if Out of stock -> offer alternate platform
            if "out of stock" in result.message.lower() or "out-of-stock" in result.message.lower():
                fail_text += "💡 *Tip:* Check availability on the alternative platform below:"
                await status_msg.edit_text(
                    text=fail_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_alternate_platform_keyboard(platform, denomination),
                )
            else:
                await status_msg.edit_text(
                    text=fail_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_main_menu_keyboard(),
                )

            # Send error screenshot if captured
            if screenshot_path:
                try:
                    with open(screenshot_path, "rb") as photo:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo,
                            caption=f"📸 Screenshot captured at failure on {plat_name}",
                        )
                except Exception as ex:
                    logger.warning(f"Could not dispatch screenshot: {ex}")

    except Exception as e:
        logger.error(f"Execution error in buy workflow: {e}", exc_info=True)
        await status_msg.edit_text(
            text=f"❌ *Automation Error:*\n`{str(e)}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard(),
        )
    finally:
        if page:
            await page.close()
        if browser_context:
            await browser_context.close()

    return ConversationHandler.END

# ==================== LOGIN WORKFLOW ====================

async def login_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates login flow by prompting for platform selection."""
    query = update.callback_query
    msg = "🔑 *Step 1/2: Select Platform for Login*\n\nChoose the platform you wish to authenticate:"
    if query:
        await query.answer()
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_platforms_keyboard(prefix="login_plat"),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_platforms_keyboard(prefix="login_plat"),
        )
    return BotState.SELECT_LOGIN_PLATFORM

async def login_platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Platform picked; ask for login method (OTP or Cookies)."""
    query = update.callback_query
    await query.answer()

    _, platform = query.data.split(":", 1)
    context.user_data["login_platform"] = platform
    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())

    await query.edit_message_text(
        text=(
            f"🔑 *Platform:* {plat_name}\n\n"
            f"Select your preferred authentication method:"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_login_methods_keyboard(platform),
    )
    return BotState.SELECT_LOGIN_METHOD

async def login_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selects Phone+OTP or Cookie import."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    platform = parts[1]
    method = parts[2]

    context.user_data["login_platform"] = platform
    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())

    if method == "phone":
        await query.edit_message_text(
            text=(
                f"📱 *Interactive Phone Login — {plat_name}*\n\n"
                f"Please reply with your *10-digit mobile number* linked to {plat_name}:\n"
                f"_(Example: 9876543210)_"
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard(),
        )
        return BotState.AWAITING_PHONE

    elif method == "cookie":
        await query.edit_message_text(
            text=(
                f"🍪 *Paste Session JSON / Cookies — {plat_name}*\n\n"
                f"Export cookies or storage state from your desktop browser for `{config.PLATFORMS.get(platform, {}).get('url')}` "
                f"and paste the JSON here:\n\n"
                f"_(Format: [{{'name': '...', 'value': '...'}}] or Playwright storage state dict)_"
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard(),
        )
        return BotState.AWAITING_COOKIE_DATA

async def handle_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives phone number and triggers headless browser OTP request."""
    user_id = update.effective_user.id
    phone_text = update.message.text.strip()
    platform = context.user_data.get("login_platform", "blinkit")
    service = PLATFORM_SERVICES.get(platform)

    # Store login context
    otp_event = asyncio.Event()
    LOGIN_SESSIONS[user_id] = {
        "platform": platform,
        "phone": phone_text,
        "otp_event": otp_event,
        "otp_value": "",
    }

    status_msg = await update.message.reply_text(
        f"⏳ *Launching headless browser to request OTP on {platform.title()}...*",
        parse_mode=ParseMode.MARKDOWN,
    )

    async def wait_for_otp() -> str:
        await status_msg.edit_text(
            f"📩 *OTP has been triggered to {phone_text}!*",
            parse_mode=ParseMode.MARKDOWN,
        )
        await update.message.reply_text(
            "🔢 *Please reply with the 4-6 digit OTP you just received:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard(),
        )
        # Wait up to 120 seconds for user reply
        try:
            await asyncio.wait_for(otp_event.wait(), timeout=120)
            return LOGIN_SESSIONS.get(user_id, {}).get("otp_value", "")
        except asyncio.TimeoutError:
            return ""

    async def run_login_task():
        browser_context = None
        page = None
        try:
            browser_context = await browser_manager.create_context()
            page = await browser_context.new_page()

            success = await service.perform_login(
                page=page,
                phone_number=phone_text,
                otp_callback=wait_for_otp,
            )

            if success:
                # Save session state
                await browser_manager.save_session(browser_context, user_id, platform)
                await update.message.reply_text(
                    f"✅ *Successfully logged into {platform.title()}!*\n"
                    f"Session cookies have been saved\\. You can now use `/buy`\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=get_main_menu_keyboard(),
                )
            else:
                await update.message.reply_text(
                    f"❌ Login failed or timed out on {platform.title()}\\. Please try again with `/login`\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=get_main_menu_keyboard(),
                )
        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error during login: {str(e)}")
        finally:
            if page:
                await page.close()
            if browser_context:
                await browser_context.close()
            LOGIN_SESSIONS.pop(user_id, None)

    # Run browser login task asynchronously
    asyncio.create_task(run_login_task())
    return BotState.AWAITING_OTP

async def handle_otp_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the OTP from the user and signals the background login browser."""
    user_id = update.effective_user.id
    otp_text = update.message.text.strip()

    if user_id in LOGIN_SESSIONS:
        LOGIN_SESSIONS[user_id]["otp_value"] = otp_text
        LOGIN_SESSIONS[user_id]["otp_event"].set()
        await update.message.reply_text("⏳ Verifying OTP with platform...")
    else:
        await update.message.reply_text("⚠️ No active login process found. Start with /login.")

    return ConversationHandler.END

async def handle_cookie_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives raw JSON cookies/tokens and imports them."""
    user_id = update.effective_user.id
    cookie_text = update.message.text.strip()
    platform = context.user_data.get("login_platform", "blinkit")

    success = browser_manager.import_session_json(user_id, platform, cookie_text)
    if success:
        await update.message.reply_text(
            f"✅ *Cookies successfully imported for {platform.title()}!*\n"
            f"You can now trigger automated purchases with `/buy`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Invalid JSON format. Please ensure you paste valid cookies array or Playwright storage state dict.",
            reply_markup=get_main_menu_keyboard(),
        )
    return ConversationHandler.END

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels active conversation flow."""
    query = update.callback_query
    if query:
        await query.answer("Operation cancelled.")
        await query.edit_message_text(
            "❌ Operation cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Operation cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    return ConversationHandler.END
