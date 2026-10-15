"""
Telegram Bot handlers for commands, conversations, and interactive callbacks.
Uses HTML ParseMode for ultra-stable, error-free formatting.
Supports environment credentials (ROOTER_AUTH_TOKEN, BLINKIT_AUTH_TOKEN) and interactive flows.
"""

import html
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
LOGIN_SESSIONS: Dict[int, Dict[str, Any]] = {}

def format_status_text(user_id: int) -> str:
    """Formats current bot status including logged-in platforms and mode in HTML."""
    if config.BLINKIT_AUTH_TOKEN:
        blinkit_logged = "🟢 Configured (ENV Token)"
    elif browser_manager.has_session(user_id, "blinkit"):
        blinkit_logged = "🟢 Logged In (Session)"
    else:
        blinkit_logged = "🔴 Not Logged In"

    if config.ROOTER_AUTH_TOKEN:
        rooter_logged = "🟢 Configured (ENV Token)"
    elif browser_manager.has_session(user_id, "rooter"):
        rooter_logged = "🟢 Logged In (Session)"
    else:
        rooter_logged = "🔴 Not Logged In"

    mode_text = "🧪 Simulation (Dry Run - Safe)" if config.SIMULATION_MODE else "⚡ Live Purchasing"

    return (
        f"🎮 <b>PlayStation Gift Card Buyer Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Execution Mode:</b> <code>{mode_text}</code>\n"
        f"• <b>Blinkit Account:</b> {blinkit_logged}\n"
        f"• <b>Rooter Account:</b> {rooter_logged}\n"
        f"• <b>Delivery Pincode:</b> <code>{config.DEFAULT_PINCODE}</code>\n"
        f"• <b>Environment:</b> <code>{config.ENV}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Use the buttons below to log into your account or start buying PlayStation vouchers automatically."
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user = update.effective_user
    user_id = user.id if user else 0
    first_name = html.escape(user.first_name if user and user.first_name else "Gamer")

    welcome_msg = (
        f"👋 <b>Welcome, {first_name}!</b>\n\n"
        + format_status_text(user_id)
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=welcome_msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=welcome_msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    help_text = (
        "📖 <b>PlayStation Buyer Bot — User Guide</b>\n\n"
        "⚡ <b>Commands:</b>\n"
        "• <code>/start</code> — Main dashboard & platform picker\n"
        "• <code>/buy</code> — Trigger automated voucher buying\n"
        "• <code>/login</code> — Store platform session cookies or OTP login\n"
        "• <code>/status</code> — View current sessions and configuration\n"
        "• <code>/toggle_sim</code> — Switch between Safe Simulation & Live Buy\n"
        "• <code>/cancel</code> — Reset active operations\n\n"
        "🛒 <b>How It Works:</b>\n"
        "1. Choose platform (<b>Blinkit</b> or <b>Rooter</b>)\n"
        "2. Select your desired denomination (₹500, ₹1000, ₹2500, etc.)\n"
        "3. Bot launches a headless Playwright browser, searches for PlayStation vouchers, checks stock, and handles checkout.\n"
        "4. Voucher Code and PIN are delivered right here in chat!"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=help_text,
            parse_mode=ParseMode.HTML,
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
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )

async def toggle_sim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggles simulation mode on or off."""
    config.SIMULATION_MODE = not config.SIMULATION_MODE
    new_state = "🧪 SIMULATION (Safe Dry Run)" if config.SIMULATION_MODE else "⚡ LIVE PURCHASING (Real Payment)"
    msg = f"⚙️ Mode updated to: <b>{new_state}</b>"

    user_id = update.effective_user.id if update.effective_user else 0
    if update.callback_query:
        await update.callback_query.answer(f"Switched to {new_state}")
        await update.callback_query.edit_message_text(
            text=f"{msg}\n\n" + format_status_text(user_id),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ==================== BUY WORKFLOW ====================

async def buy_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the buy flow by asking for platform selection."""
    query = update.callback_query
    msg = "🛒 <b>Step 1/3: Choose Platform</b>\n\nSelect where you want to buy the PlayStation Gift Card from:"
    if query:
        await query.answer()
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_platforms_keyboard(prefix="buy_plat"),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
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
            f"🎯 <b>Selected Platform:</b> {plat_name}\n\n"
            f"🛒 <b>Step 2/3: Select Denomination</b>\n"
            f"Choose the amount for your PlayStation Gift Card:"
        ),
        parse_mode=ParseMode.HTML,
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
            f"📝 <b>Order Confirmation</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Item:</b> PlayStation Gift Card\n"
            f"• <b>Platform:</b> {plat_name}\n"
            f"• <b>Denomination:</b> ₹{denomination:,}\n"
            f"• <b>Mode:</b> <code>{mode_text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Click <b>Confirm & Buy Now</b> to trigger the Playwright automation engine."
        ),
        parse_mode=ParseMode.HTML,
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
        text=f"🔍 <b>Connecting to Playwright Engine for {plat_name}...</b>",
        parse_mode=ParseMode.HTML,
    )

    # Helper callback to send live updates directly to user
    async def progress_notifier(step_text: str, emoji: str = "⚡"):
        try:
            await status_msg.edit_text(
                text=f"{emoji} <b>{html.escape(step_text)}</b>\n\n<i>Automating via Headless Chromium...</i>",
                parse_mode=ParseMode.HTML,
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
            v_code = html.escape(result.voucher_code or "")
            v_pin = html.escape(result.voucher_pin or "")
            o_id = html.escape(result.order_id or "")

            success_text = (
                f"🎉 <b>PURCHASE SUCCESSFUL!{sim_badge}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎮 <b>Platform:</b> {plat_name}\n"
                f"💰 <b>Denomination:</b> ₹{result.denomination:,}\n"
                f"🔑 <b>Voucher Code:</b>\n<code>{v_code}</code>\n"
                f"🔒 <b>PIN / Key:</b>\n<code>{v_pin}</code>\n"
                f"🧾 <b>Order ID:</b> <code>{o_id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ Redeem this on your PlayStation Store console or app."
            )
            await status_msg.edit_text(
                text=success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
        else:
            # Capture error screenshot for inspection
            screenshot_path = await browser_manager.capture_screenshot(page, name_prefix=f"err_{platform}")

            fail_text = (
                f"⚠️ <b>Notice: Purchase Flow Stopped</b>\n\n"
                f"• <b>Platform:</b> {plat_name}\n"
                f"• <b>Reason:</b> {html.escape(result.message)}\n\n"
            )

            # Check if Out of stock -> offer alternate platform
            if "out of stock" in result.message.lower() or "out-of-stock" in result.message.lower():
                fail_text += "💡 <b>Tip:</b> Check availability on the alternative platform below:"
                await status_msg.edit_text(
                    text=fail_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_alternate_platform_keyboard(platform, denomination),
                )
            else:
                await status_msg.edit_text(
                    text=fail_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_menu_keyboard(),
                )

            # Send error screenshot if captured
            if screenshot_path:
                try:
                    with open(screenshot_path, "rb") as photo:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo,
                            caption=f"📸 Screenshot captured on {plat_name}",
                        )
                except Exception as ex:
                    logger.warning(f"Could not dispatch screenshot: {ex}")

    except Exception as e:
        logger.error(f"Execution error in buy workflow: {e}", exc_info=True)
        await status_msg.edit_text(
            text=f"❌ <b>Automation Error:</b>\n<code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
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
    msg = "🔑 <b>Step 1/2: Select Platform for Login</b>\n\nChoose the platform you wish to authenticate:"
    if query:
        await query.answer()
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_platforms_keyboard(prefix="login_plat"),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
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
            f"🔑 <b>Platform:</b> {plat_name}\n\n"
            f"Select your preferred authentication method:"
        ),
        parse_mode=ParseMode.HTML,
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

    # Pre-configured phone number check
    default_phone = ""
    if platform == "blinkit" and config.BLINKIT_MOBILE:
        default_phone = f"\n💡 <i>(Pre-configured in ENV: {config.BLINKIT_MOBILE})</i>"
    elif platform == "rooter" and config.ROOTER_MOBILE:
        default_phone = f"\n💡 <i>(Pre-configured in ENV: {config.ROOTER_MOBILE})</i>"

    if method == "phone":
        await query.edit_message_text(
            text=(
                f"📱 <b>Interactive Phone Login — {plat_name}</b>\n\n"
                f"Please reply with your <b>10-digit mobile number</b> linked to {plat_name}:\n"
                f"<i>(Example: 9876543210)</i>{default_phone}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard(),
        )
        return BotState.AWAITING_PHONE

    elif method == "cookie":
        await query.edit_message_text(
            text=(
                f"🍪 <b>Paste Session JSON / Cookies — {plat_name}</b>\n\n"
                f"Export cookies or storage state from your desktop browser for <code>{config.PLATFORMS.get(platform, {}).get('url')}</code> "
                f"and paste the JSON here:\n\n"
                f"<i>(Format: [{{'name': '...', 'value': '...'}}] or Playwright storage state dict)</i>"
            ),
            parse_mode=ParseMode.HTML,
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
        f"⏳ <b>Launching headless browser to request OTP on {platform.title()}...</b>",
        parse_mode=ParseMode.HTML,
    )

    async def wait_for_otp() -> str:
        await status_msg.edit_text(
            f"📩 <b>OTP has been triggered to {phone_text}!</b>",
            parse_mode=ParseMode.HTML,
        )
        await update.message.reply_text(
            "🔢 <b>Please reply with the 4-6 digit OTP you just received:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard(),
        )
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
                await browser_manager.save_session(browser_context, user_id, platform)
                await update.message.reply_text(
                    f"✅ <b>Successfully logged into {platform.title()}!</b>\n"
                    f"Session cookies have been saved. You can now use <code>/buy</code>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_menu_keyboard(),
                )
            else:
                await update.message.reply_text(
                    f"❌ Login failed or timed out on {platform.title()}. Please try again with <code>/login</code>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_menu_keyboard(),
                )
        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error during login: {html.escape(str(e))}")
        finally:
            if page:
                await page.close()
            if browser_context:
                await browser_context.close()
            LOGIN_SESSIONS.pop(user_id, None)

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
            f"✅ <b>Cookies successfully imported for {platform.title()}!</b>\n"
            f"You can now trigger automated purchases with <code>/buy</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Invalid JSON format. Please ensure you paste a valid cookies array or Playwright storage state dict.",
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
