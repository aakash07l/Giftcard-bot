"""
Telegram Bot handlers for commands, conversations, and interactive callbacks.
Uses HTML ParseMode for ultra-stable, error-free formatting.
Supports environment credentials (ROOTER_AUTH_TOKEN) and interactive flows.
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
    get_snipe_denominations_keyboard,
    get_confirmation_keyboard,
    get_alternate_platform_keyboard,
    get_stop_snipe_keyboard,
    get_cancel_keyboard,
)
from services.browser_manager import browser_manager
from services.rooter_service import RooterService
from services.base_platform import BasePlatform

logger = logging.getLogger(__name__)

# Register platform services
PLATFORM_SERVICES: Dict[str, BasePlatform] = {
    "rooter": RooterService(),
}

# Temporary memory store for pending interactive logins
LOGIN_SESSIONS: Dict[int, Dict[str, Any]] = {}

# Active background auto-sniper jobs {user_id: {"task": Task, "stop_event": Event, ...}}
ACTIVE_SNIPERS: Dict[int, Dict[str, Any]] = {}

def format_status_text(user_id: int) -> str:
    """Formats current bot status for Rooter PlayStation sniper in HTML."""
    if config.ROOTER_AUTH_TOKEN:
        rooter_logged = "🟢 Configured (ENV Token)"
    elif browser_manager.has_session(user_id, "rooter"):
        rooter_logged = "🟢 Logged In (Session)"
    else:
        rooter_logged = "🔴 Not Logged In"

    mode_text = "🧪 Simulation (Dry Run - Safe)" if config.SIMULATION_MODE else "⚡ Live Purchasing"

    sniper_info = ACTIVE_SNIPERS.get(user_id)
    if sniper_info:
        denom_disp = sniper_info["denomination"]
        checks = sniper_info.get("attempts", 0)
        p_label = "Google Play ₹10" if denom_disp == 10 else f"PSN ₹{denom_disp:,}"
        sniper_text = f"🟢 Active ({p_label} - <code>{checks}</code> checks)"
    else:
        sniper_text = "⚪ Inactive"

    return (
        f"🎮 <b>PlayStation Gift Card Buyer Bot (Rooter Shop)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Execution Mode:</b> <code>{mode_text}</code>\n"
        f"• <b>24/7 Restock Sniper:</b> {sniper_text}\n"
        f"• <b>Rooter Account:</b> {rooter_logged}\n"
        f"• <b>Refresh Interval:</b> <code>{config.SNIPE_INTERVAL_SECONDS}s</code>\n"
        f"• <b>Environment:</b> <code>{config.ENV}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Use the buttons below to log in, trigger instant buy, or start 24/7 auto-sniper."
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
        "• <code>/start</code> — Main dashboard & menu\n"
        "• <code>/snipe</code> — 🎯 24/7 Restock Auto-Sniper (Auto-buys the second stock arrives!)\n"
        "• <code>/stop</code> — 🛑 Stop active 24/7 restock monitoring\n"
        "• <code>/buy</code> — Instant single purchase flow\n"
        "• <code>/login</code> — Store platform session / Bearer Token\n"
        "• <code>/status</code> — View current sessions, sniper status & mode\n"
        "• <code>/toggle_sim</code> — Switch between Safe Simulation & Live Buy\n"
        "• <code>/cancel</code> — Reset active operations\n\n"
        "🎯 <b>Auto-Sniper Workflow:</b>\n"
        "1. Send <code>/snipe</code> and choose PlayStation denomination (₹1,000 to ₹5,000).\n"
        f"2. Bot runs continuously in the background, checking Rooter Shop every {config.SNIPE_INTERVAL_SECONDS}s.\n"
        "3. Jaise hi PlayStation code restock hoga, bot turant Rooter balance se 1-click buy karke code yahan bhej dega!"
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
    """Initiates instant purchase on Rooter Shop by asking for denomination."""
    query = update.callback_query
    context.user_data["buy_platform"] = "rooter"
    msg = (
        "🛒 <b>Instant Buy — Rooter Shop</b>\n\n"
        "Select the voucher denomination to buy using your Rooter wallet balance:\n"
        "<i>(Tip: Aap <b>₹10 Google Play Code</b> se 1-time real test buy kar sakte hain!)</i>"
    )
    if query:
        await query.answer()
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_denominations_keyboard("rooter"),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_denominations_keyboard("rooter"),
        )
    return BotState.SELECT_BUY_DENOMINATION

async def buy_platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler redirecting to Rooter denomination selection."""
    return await buy_start_handler(update, context)

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
    prod_name = "Google Play Recharge Code" if denomination < 1000 else "PlayStation Gift Card"
    price_tag = "₹8 (from Rooter Wallet)" if denomination == 10 else f"₹{denomination:,}"

    await query.edit_message_text(
        text=(
            f"📝 <b>Order Confirmation</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Item:</b> {prod_name}\n"
            f"• <b>Platform:</b> {plat_name}\n"
            f"• <b>Denomination:</b> ₹{denomination:,}\n"
            f"• <b>Cost:</b> {price_tag}\n"
            f"• <b>Mode:</b> <code>{mode_text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Click <b>Confirm & Buy</b> to trigger the Playwright automation engine."
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

    # Pre-flight check: ensure active session exists
    if not browser_manager.has_session(user_id, platform):
        await query.edit_message_text(
            text=(
                "⚠️ <b>Rooter Account Logged In Nahi Hai!</b>\n\n"
                "Cloud server restart hone ki wajah se session reset ho gaya hai ya Bearer token missing hai.\n\n"
                "👉 Kripya pehle <code>/login</code> dabayein aur <b>Paste Bearer Token</b> select karke apna token paste karein.\n\n"
                "💡 <i>Tip: Railway Variables me <code>ROOTER_AUTH_TOKEN</code> set karne se token kabhi reset nahi hoga!</i>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

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

        prod_name = "Google Play Recharge Code" if denomination < 1000 else "PlayStation Gift Card"
        redeem_tip = "Redeem this code in Google Play Store." if denomination < 1000 else "Redeem this on your PlayStation Store console or app."

        if result.success:
            sim_badge = " [SIMULATED TEST]" if result.simulation else ""
            v_code = html.escape(result.voucher_code or "")
            v_pin = html.escape(result.voucher_pin or "")
            o_id = html.escape(result.order_id or "")

            success_text = (
                f"🎉 <b>PURCHASE SUCCESSFUL!{sim_badge}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>Platform:</b> {plat_name}\n"
                f"📦 <b>Item:</b> {prod_name}\n"
                f"💰 <b>Denomination:</b> ₹{result.denomination:,}\n"
                f"🔑 <b>Voucher / Redeem Code:</b>\n<code>{v_code}</code>\n"
                f"🔒 <b>PIN / Key:</b>\n<code>{v_pin}</code>\n"
                f"🧾 <b>Order ID:</b> <code>{o_id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ {redeem_tip}"
            )
            await status_msg.edit_text(
                text=success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            # Send confirmation screenshot if available
            shot_file = result.error_screenshot
            if shot_file and os.path.exists(shot_file):
                try:
                    with open(shot_file, "rb") as photo:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo,
                            caption=f"📸 Order proof for {prod_name} on {plat_name}",
                        )
                except Exception as ex:
                    logger.debug(f"Could not dispatch screenshot: {ex}")
        else:
            # Capture error screenshot for inspection
            screenshot_path = result.error_screenshot or await browser_manager.capture_screenshot(page, name_prefix=f"err_{platform}")

            fail_text = (
                f"⚠️ <b>Notice: Purchase Flow Stopped</b>\n\n"
                f"• <b>Platform:</b> {plat_name}\n"
                f"• <b>Item:</b> {prod_name}\n"
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

# ==================== AUTO-SNIPER (24/7 RESTOCK MONITOR) ====================

async def run_sniper_loop(
    chat_id: int,
    user_id: int,
    platform: str,
    denomination: int,
    bot,
    stop_event: asyncio.Event,
):
    """
    Background worker loop that refreshes Rooter Shop every 30 seconds.
    As soon as stock is detected, it immediately executes purchase and delivers
    the PlayStation voucher code and PIN to the user on Telegram.
    """
    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())
    service = PLATFORM_SERVICES.get(platform)
    browser_context = None
    page = None
    attempts = 0

    logger.info(f"Starting sniper loop for user {user_id} on {platform} ₹{denomination}")

    try:
        browser_context = await browser_manager.create_context(
            user_id=user_id,
            platform=platform,
            apply_storage_state=True,
        )
        page = await browser_context.new_page()

        while not stop_event.is_set():
            attempts += 1
            if user_id in ACTIVE_SNIPERS:
                ACTIVE_SNIPERS[user_id]["attempts"] = attempts

            logger.info(f"[Sniper #{attempts}] Checking stock on {platform} for ₹{denomination}...")

            # Ensure page is alive
            if page.is_closed():
                page = await browser_context.new_page()

            is_in_stock = False
            try:
                is_in_stock = await service.check_is_in_stock(page, denomination)
            except Exception as e:
                logger.warning(f"[Sniper #{attempts}] Error during stock check: {e}")

            if is_in_stock:
                prod_name = "Google Play Recharge Code" if denomination < 1000 else "PlayStation Gift Card"
                redeem_tip = "Redeem this code in Google Play Store." if denomination < 1000 else "Redeem this immediately on your PlayStation console or app."
                logger.info(f"🚨 [Sniper #{attempts}] STOCK DETECTED for {prod_name} ₹{denomination} on {platform}!")

                # Notify Telegram user immediately
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"🚨 <b>STOCK DETECTED!</b>\n\n"
                            f"🎯 <b>Platform:</b> {plat_name}\n"
                            f"📦 <b>Item:</b> {prod_name}\n"
                            f"💰 <b>Denomination:</b> ₹{denomination:,}\n\n"
                            f"⚡ <b>Executing instant 1-click buy with wallet balance...</b>"
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass

                # Execute purchase immediately
                result = await service.execute_buy_flow(
                    page=page,
                    denomination=denomination,
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
                        f"🎯 <b>Platform:</b> {plat_name}\n"
                        f"📦 <b>Item:</b> {prod_name}\n"
                        f"💰 <b>Denomination:</b> ₹{result.denomination:,}\n"
                        f"🔑 <b>Voucher / Redeem Code:</b>\n<code>{v_code}</code>\n"
                        f"🔒 <b>PIN / Key:</b>\n<code>{v_pin}</code>\n"
                        f"🧾 <b>Order ID:</b> <code>{o_id}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✨ <i>Auto-Sniper successfully bought your voucher!</i>\n"
                        f"{redeem_tip}"
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text=success_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_main_menu_keyboard(),
                    )
                    # Send proof photo if available
                    shot_file = result.error_screenshot
                    if shot_file and os.path.exists(shot_file):
                        try:
                            with open(shot_file, "rb") as photo:
                                await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=photo,
                                    caption=f"📸 Order proof for {prod_name}",
                                )
                        except Exception:
                            pass
                    # Successful buy: finish sniper (single-time execution)
                    break
                else:
                    logger.warning(f"[Sniper #{attempts}] Purchase could not complete: {result.message}")
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"⚠️ <b>Sniper Alert:</b> Stock appeared on {plat_name}, but checkout could not finish:\n"
                            f"<code>{html.escape(result.message)}</code>\n\n"
                            f"<i>Monitoring will continue in the next cycle...</i>"
                        ),
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_stop_snipe_keyboard(),
                    )

            # Heartbeat message (Disabled by default to avoid chat spam and save credit)
            if config.ENABLE_SNIPER_HEARTBEAT and attempts % 20 == 0:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"🔄 <b>Auto-Sniper Running (24/7 Restock Monitor)</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Platform:</b> {plat_name}\n"
                            f"• <b>Target:</b> PlayStation ₹{denomination:,}\n"
                            f"• <b>Refreshes Completed:</b> <code>{attempts}</code>\n"
                            f"• <b>Status:</b> Actively checking every {config.SNIPE_INTERVAL_SECONDS}s. Ready to buy instantly when stock arrives!\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━"
                        ),
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_stop_snipe_keyboard(),
                    )
                except Exception:
                    pass

            # Periodic memory cleanup: Refresh page every 50 checks to release Chromium memory
            if attempts % 50 == 0:
                try:
                    if not page.is_closed():
                        await page.close()
                    page = await browser_context.new_page()
                except Exception as e:
                    logger.debug(f"Page memory cleanup: {e}")

            # Wait before next check (interrupted immediately if stop_event is set)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=float(config.SNIPE_INTERVAL_SECONDS))
                # If wait_for returns without TimeoutError, stop_event was signaled
                break
            except asyncio.TimeoutError:
                pass

    except asyncio.CancelledError:
        logger.info(f"Sniper task for user {user_id} was cancelled.")
    except Exception as e:
        logger.error(f"Error in sniper loop for user {user_id}: {e}", exc_info=True)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Auto-Sniper Error:</b> <code>{html.escape(str(e))}</code>\nMonitoring stopped.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
        except Exception:
            pass
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if browser_context:
            try:
                await browser_context.close()
            except Exception:
                pass
        ACTIVE_SNIPERS.pop(user_id, None)
        logger.info(f"Sniper loop closed for user {user_id}")

async def snipe_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the 24/7 auto-sniper restock flow."""
    user_id = update.effective_user.id if update.effective_user else 0
    query = update.callback_query

    # If a sniper is already running for this user, cancel it to allow starting fresh
    if user_id in ACTIVE_SNIPERS:
        old_sniper = ACTIVE_SNIPERS.pop(user_id)
        if old_sniper.get("stop_event"):
            old_sniper["stop_event"].set()
        if old_sniper.get("task") and not old_sniper["task"].done():
            old_sniper["task"].cancel()
        logger.info(f"Previous sniper task cancelled for user {user_id} to start fresh sniper.")

    context.user_data["snipe_platform"] = "rooter"
    has_session = browser_manager.has_session(user_id, "rooter")
    login_note = ""
    if not has_session:
        login_note = (
            "\n\n⚠️ <b>Warning:</b> Aap Rooter par logged in nahi hain! "
            "Instant buy ke liye pehle <code>/login</code> se account token zaroor save kar lein."
        )

    msg = (
        "🎯 <b>Auto-Sniper / Restock Monitor (Rooter Shop)</b>\n\n"
        f"Bot har {config.SNIPE_INTERVAL_SECONDS}s me stock check karega aur jaise hi available hoga, wallet balance se turant instant-buy kar lega!\n\n"
        f"<b>Select Voucher Denomination:</b>\n"
        f"<i>(🧪 <b>₹10 Google Play Code</b> select karne par bot turant 1-time real test buy karke finish kar dega!)</i>{login_note}"
    )
    if query:
        await query.answer()
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_snipe_denominations_keyboard("rooter"),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_snipe_denominations_keyboard("rooter"),
        )
    return BotState.SELECT_SNIPE_DENOMINATION

async def snipe_platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler redirecting to Rooter denomination selection."""
    return await snipe_start_handler(update, context)

async def snipe_denomination_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Denomination picked; launches background auto-sniper loop."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    platform = parts[1]
    denomination = int(parts[2])

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())

    # Pre-flight check: ensure active session exists
    if not browser_manager.has_session(user_id, platform):
        await query.edit_message_text(
            text=(
                "⚠️ <b>Rooter Account Logged In Nahi Hai!</b>\n\n"
                "Cloud server restart hone ki wajah se session reset ho gaya hai ya Bearer token missing hai.\n\n"
                "👉 Kripya pehle <code>/login</code> dabayein aur <b>Paste Bearer Token</b> select karke apna token paste karein.\n\n"
                "💡 <i>Tip: Railway Variables me <code>ROOTER_AUTH_TOKEN</code> set karne se token kabhi reset nahi hoga!</i>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    # Cancel any previous running sniper
    if user_id in ACTIVE_SNIPERS:
        old_sniper = ACTIVE_SNIPERS.pop(user_id)
        if old_sniper.get("stop_event"):
            old_sniper["stop_event"].set()
        if old_sniper.get("task") and not old_sniper["task"].done():
            old_sniper["task"].cancel()

    stop_event = asyncio.Event()

    task = asyncio.create_task(
        run_sniper_loop(
            chat_id=chat_id,
            user_id=user_id,
            platform=platform,
            denomination=denomination,
            bot=context.bot,
            stop_event=stop_event,
        )
    )

    ACTIVE_SNIPERS[user_id] = {
        "task": task,
        "stop_event": stop_event,
        "platform": platform,
        "denomination": denomination,
        "chat_id": chat_id,
        "attempts": 0,
    }

    mode_text = "🧪 Simulation (Dry Run)" if config.SIMULATION_MODE else "⚡ Live Purchasing (Real Checkout)"
    prod_name = "Google Play Recharge Code (₹10 Real Test Snipe)" if denomination < 1000 else f"PlayStation ₹{denomination:,}"
    note_text = (
        "✅ <b>1-Time Test Snipe Running:</b> Bot Google Play ₹10 code ko Rooter Wallet balance se turant 1 baar buy karega aur complete ho jayega!"
        if denomination < 1000
        else "✅ <b>24/7 Restock Monitor Active:</b> Jaise hi PlayStation voucher stock me aayega, bot bina kisi delay ke turant buy kar lega aur voucher code aapko yahan message kar dega."
    )

    await query.edit_message_text(
        text=(
            f"🚀 <b>Auto-Sniper Activated!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Platform:</b> {plat_name}\n"
            f"💰 <b>Target Voucher:</b> {prod_name}\n"
            f"⏱️ <b>Refresh Rate:</b> Every {config.SNIPE_INTERVAL_SECONDS} seconds\n"
            f"⚡ <b>Mode:</b> <code>{mode_text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{note_text}\n\n"
            f"<i>Aap Telegram band kar sakte hain ya doosra kaam kar sakte hain. Stop karne ke liye <code>/stop</code> dabayein.</i>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=get_stop_snipe_keyboard(),
    )
    return ConversationHandler.END

async def stop_snipe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stops the active auto-sniper background process."""
    user_id = update.effective_user.id if update.effective_user else 0
    query = update.callback_query

    if user_id in ACTIVE_SNIPERS:
        sniper_data = ACTIVE_SNIPERS.pop(user_id)
        stop_event = sniper_data.get("stop_event")
        if stop_event:
            stop_event.set()
        task = sniper_data.get("task")
        if task and not task.done():
            task.cancel()

        p_name = config.PLATFORMS.get(sniper_data["platform"], {}).get("name", sniper_data["platform"].title())
        msg = (
            f"🛑 <b>Auto-Sniper Stopped!</b>\n\n"
            f"• Platform: {p_name}\n"
            f"• Target: PlayStation ₹{sniper_data['denomination']:,}\n"
            f"• Total Page Checks: <code>{sniper_data.get('attempts', 0)}</code>\n\n"
            f"Stock monitoring paused. You can restart anytime with /snipe or /start."
        )
    else:
        msg = "ℹ️ <b>No active auto-sniper is currently running.</b>\nStart one with /snipe."

    if query:
        await query.answer("Auto-Sniper stopped.")
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )

# ==================== LOGIN WORKFLOW ====================

async def login_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates login flow for Rooter Shop."""
    query = update.callback_query
    context.user_data["login_platform"] = "rooter"
    msg = "🔑 <b>Rooter Shop Authentication</b>\n\nChoose how you want to log into your Rooter account:"
    if query:
        await query.answer()
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_login_methods_keyboard("rooter"),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_login_methods_keyboard("rooter"),
        )
    return BotState.SELECT_LOGIN_METHOD

async def login_platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler redirecting to Rooter login methods."""
    return await login_start_handler(update, context)

async def login_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selects Phone+OTP or Cookie import."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    method = parts[2] if len(parts) > 2 else "cookie"
    platform = "rooter"

    context.user_data["login_platform"] = "rooter"

    # Pre-configured phone number check
    default_phone = ""
    if config.ROOTER_MOBILE:
        default_phone = f"\n💡 <i>(Pre-configured in ENV: {config.ROOTER_MOBILE})</i>"

    if method == "phone":
        await query.edit_message_text(
            text=(
                f"📱 <b>Interactive Phone Login — Rooter Shop</b>\n\n"
                f"Please reply with your <b>10-digit mobile number</b> linked to Rooter:\n"
                f"<i>(Example: 9876543210)</i>{default_phone}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard(),
        )
        return BotState.AWAITING_PHONE

    elif method == "cookie":
        await query.edit_message_text(
            text=(
                "🍪 <b>Paste Bearer Token or Cookies — Rooter Shop</b>\n\n"
                "Aap apna <b>Bearer Token</b> (e.g. <code>eyJhbGci...</code>) ya cookies JSON yahan chat me paste karein:\n\n"
                "<i>Bot turant isse session me save kar lega aur wallet connect ho jayega!</i>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_keyboard(),
        )
        return BotState.AWAITING_COOKIE_DATA

async def handle_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives phone number and triggers headless browser OTP request."""
    user_id = update.effective_user.id
    phone_text = update.message.text.strip()
    platform = "rooter"
    service = PLATFORM_SERVICES.get("rooter")

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
                    f"❌ <b>Login failed or timed out on {platform.title()}.</b>\n\n"
                    f"💡 <i>Tip:</i> Cloud servers par Rooter anti-bot security OTP block kar sakti hai.\n"
                    f"Aap seedha <code>/login</code> me jakar <b>Paste Bearer Token</b> option se apna auth token paste kar sakte hain!",
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
    """Receives raw Bearer token or JSON cookies and imports them."""
    user_id = update.effective_user.id
    cookie_text = update.message.text.strip()
    platform = "rooter"

    success = browser_manager.import_session_json(user_id, platform, cookie_text)
    if success:
        await update.message.reply_text(
            f"✅ <b>Authentication token successfully saved for {platform.title()}!</b>\n"
            f"You can now trigger automated purchases with <code>/buy</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Invalid token or JSON format. Please ensure you paste a valid Bearer token string or cookies JSON.",
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
