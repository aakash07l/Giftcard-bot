"""
Telegram Bot handlers for commands, conversations, and interactive callbacks.
Uses HTML ParseMode for ultra-stable, error-free formatting.
Supports environment credentials (ROOTER_AUTH_TOKEN) and interactive flows.
"""

import os
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
    get_accounts_keyboard,
    get_platforms_keyboard,
    get_login_methods_keyboard,
    get_denominations_keyboard,
    get_snipe_denominations_keyboard,
    get_confirmation_keyboard,
    get_alternate_platform_keyboard,
    get_stop_snipe_keyboard,
    get_playstore_stopped_keyboard,
    get_cancel_keyboard,
)
from services.browser_manager import browser_manager
from services.rooter_service import RooterService
from services.base_platform import BasePlatform
from services.account_manager import account_manager

logger = logging.getLogger(__name__)

# Register platform services
PLATFORM_SERVICES: Dict[str, BasePlatform] = {
    "rooter": RooterService(),
}

# Temporary memory store for pending interactive logins
LOGIN_SESSIONS: Dict[int, Dict[str, Any]] = {}

# Global Singleton for 24/7 Restock Sniper (Shared across all Telegram users)
GLOBAL_SNIPER: Dict[str, Any] = {
    "is_running": False,
    "task": None,
    "stop_event": None,
    "platform": "rooter",
    "denomination": 0,
    "attempts": 0,
    "chat_ids": set(),         # Set of Telegram chat IDs to receive broadcast alerts
    "started_by_user_id": 0,
    "started_by_name": "",
}

# Compatibility dictionary for legacy references
ACTIVE_SNIPERS: Dict[int, Dict[str, Any]] = {}

async def broadcast_sniper_message(
    bot,
    text: str,
    parse_mode=ParseMode.HTML,
    reply_markup=None,
    photo_path: Optional[str] = None,
):
    """Broadcasts a sniper notification simultaneously to all subscribed chat IDs."""
    chat_ids = list(GLOBAL_SNIPER.get("chat_ids", set()))
    if not chat_ids:
        return

    async def _send_to_one(cid):
        try:
            if photo_path and os.path.exists(photo_path):
                with open(photo_path, "rb") as photo:
                    await bot.send_photo(
                        chat_id=cid,
                        photo=photo,
                        caption=text[:1024],
                        parse_mode=parse_mode,
                    )
            else:
                await bot.send_message(
                    chat_id=cid,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
        except Exception as e:
            logger.warning(f"Failed to dispatch sniper broadcast to chat {cid}: {e}")

    await asyncio.gather(*[_send_to_one(cid) for cid in chat_ids], return_exceptions=True)

def format_status_text(user_id: int) -> str:
    """Formats current bot status for Rooter PlayStation sniper in HTML."""
    all_accs = account_manager.get_all()
    active_accs = account_manager.get_active()
    total_bal = account_manager.get_total_balance()

    if active_accs:
        rooter_logged = f"🟢 {len(active_accs)} Active Account{'s' if len(active_accs) > 1 else ''} (Total: ₹{total_bal:,.0f})"
    elif config.ROOTER_AUTH_TOKEN:
        rooter_logged = "🟢 Configured (ENV Token)"
    elif browser_manager.has_session(user_id, "rooter"):
        rooter_logged = "🟢 Logged In (Session)"
    else:
        rooter_logged = "🔴 Not Logged In"

    mode_text = "🧪 Simulation (Dry Run - Safe)" if config.SIMULATION_MODE else "⚡ Live Purchasing"

    is_running = GLOBAL_SNIPER.get("is_running") and GLOBAL_SNIPER.get("task") and not GLOBAL_SNIPER["task"].done()
    if is_running:
        denom_disp = GLOBAL_SNIPER.get("denomination", 0)
        checks = GLOBAL_SNIPER.get("attempts", 0)
        sub_count = len(GLOBAL_SNIPER.get("chat_ids", set()))
        p_label = "Any PSN (₹1k-₹5k)" if denom_disp == 0 else f"PSN ₹{denom_disp:,}"
        sub_badge = f" | 👥 {sub_count} user{'s' if sub_count > 1 else ''}" if sub_count > 1 else ""
        sniper_text = f"🟢 Active ({p_label} - <code>{checks}</code> checks{sub_badge})"
    else:
        sniper_text = "⚪ Inactive"

    return (
        f"🎮 <b>PlayStation Gift Card Buyer Bot (Rooter Shop)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Execution Mode:</b> <code>{mode_text}</code>\n"
        f"• <b>24/7 Restock Sniper:</b> {sniper_text}\n"
        f"• <b>Active Accounts:</b> {rooter_logged}\n"
        f"• <b>Total Balance:</b> <b>₹{total_bal:,.0f}</b>\n"
        f"• <b>Refresh Interval:</b> <code>{config.SNIPE_INTERVAL_SECONDS}s</code>\n"
        f"• <b>Environment:</b> <code>{config.ENV}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Use the buttons below to manage accounts, instant buy, or start 24/7 auto-sniper."
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user = update.effective_user
    user_id = user.id if user else 0
    first_name = html.escape(user.first_name if user and user.first_name else "Gamer")

    # Auto-subscribe this chat to alerts
    if update.effective_chat:
        GLOBAL_SNIPER["chat_ids"].add(update.effective_chat.id)

    try:
        await account_manager.sync_all_balances()
    except Exception as e:
        logger.debug(f"Live balance sync notice: {e}")

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
        "• <code>/accounts</code> — 👥 Manage 5-10 Rooter Accounts (Auto Live Balance Sync 🟢)\n"
        "• <code>/addaccount &lt;token&gt; [label]</code> — Add a Rooter account (Auto fetches live balance!)\n"
        "• <code>/setbalance &lt;acc_id&gt; &lt;amount&gt;</code> — Set optional manual balance override\n"
        "• <code>/snipe</code> — 🎯 24/7 Restock Auto-Sniper (Parallel buy across all active accounts!)\n"
        "• <code>/stop</code> — 🛑 Stop active 24/7 restock monitoring\n"
        "• <code>/buy</code> — Instant single purchase flow\n"
        "• <code>/login</code> — Store platform session / Bearer Token\n"
        "• <code>/status</code> — View current sessions, sniper status & mode\n"
        "• <code>/toggle_sim</code> — Switch between Safe Simulation & Live Buy\n"
        "• <code>/cancel</code> — Reset active operations\n\n"
        "🎯 <b>Multi-Account Restock Sniper:</b>\n"
        "1. Add your 5 to 10 Rooter accounts with <code>/addaccount</code> or the 👥 button.\n"
        "2. Balance is automatically fetched in real-time from Rooter's live API.\n"
        "3. Send <code>/snipe</code> -> select <b>Any PlayStation Card</b>.\n"
        f"4. Bot checks stock every {config.SNIPE_INTERVAL_SECONDS}s. When stock lands, bot automatically picks the largest affordable denomination for each account and buys in parallel simultaneously!"
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
    try:
        await account_manager.sync_all_balances()
    except Exception as e:
        logger.debug(f"Live balance sync notice: {e}")
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
        "🛒 <b>Instant Buy — Rooter Shop (PlayStation)</b>\n\n"
        "Select the PlayStation Gift Card denomination to buy using your Rooter wallet balance:"
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

    if denomination < 1000:
        await query.edit_message_text(
            text=(
                "⚠️ <b>Play Store Buying Disabled!</b>\n\n"
                "Google Play recharge code buying stop aur disable kar di gayi hai.\n"
                "Bot ab sirf PlayStation Gift Cards (₹1,000 to ₹5,000) buy karne ke liye configured hai."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_playstore_stopped_keyboard(),
        )
        return ConversationHandler.END

    context.user_data["buy_platform"] = platform
    context.user_data["buy_denomination"] = denomination

    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())
    mode_text = "🧪 SIMULATION (No funds deducted)" if config.SIMULATION_MODE else "⚡ LIVE (Real Checkout)"
    prod_name = "PlayStation Gift Card"
    price_tag = f"₹{denomination:,}"

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
        # Launch browser context with stored user session or active account token
        active_tok = browser_manager.get_active_token(user_id)
        browser_context = await browser_manager.create_context(
            user_id=user_id,
            platform=platform,
            apply_storage_state=True,
            custom_token=active_tok,
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
        # Inject primary account token into monitor context
        primary_tok = browser_manager.get_active_token(user_id)
        browser_context = await browser_manager.create_context(
            user_id=user_id,
            platform=platform,
            apply_storage_state=True,
            custom_token=primary_tok,
        )
        page = await browser_context.new_page()
        is_any_mode = (denomination == 0)
        target_denomination = denomination
        prod_name = "PlayStation Gift Card"
        redeem_tip = "Redeem this immediately on your PlayStation console or app."
        if is_any_mode:
            start_desc = "Any PlayStation Gift Card (₹1,000 to ₹5,000)"
        else:
            start_desc = f"{prod_name} ₹{denomination:,}"

        # Register global sniper state
        GLOBAL_SNIPER["is_running"] = True
        GLOBAL_SNIPER["platform"] = platform
        GLOBAL_SNIPER["denomination"] = denomination
        GLOBAL_SNIPER["stop_event"] = stop_event
        GLOBAL_SNIPER["chat_ids"].add(chat_id)

        # Send immediate live confirmation to Telegram chats
        try:
            await broadcast_sniper_message(
                bot,
                text=(
                    f"🔍 <b>Sniper Active:</b> Opening Rooter Shop to inspect <b>{start_desc}</b>...\n"
                    f"⚡ <i>Available hote hi 1 second me instant auto-buy karega!</i>"
                ),
            )
        except Exception as me:
            logger.warning(f"Could not send sniper start message: {me}")

        while not stop_event.is_set():
            attempts += 1
            GLOBAL_SNIPER["attempts"] = attempts
            if user_id in ACTIVE_SNIPERS:
                ACTIVE_SNIPERS[user_id]["attempts"] = attempts

            target_desc = "Any PlayStation (₹1k-₹5k)" if is_any_mode else f"₹{denomination}"
            logger.info(f"[Sniper #{attempts}] Checking stock on {platform} for {target_desc}...")

            # Ensure page is alive
            if page.is_closed():
                page = await browser_context.new_page()

            is_in_stock = False
            available_denominations = []
            try:
                if is_any_mode:
                    available_denominations = await service.get_in_stock_playstation_denominations(page)
                    is_in_stock = len(available_denominations) > 0
                else:
                    is_in_stock = await service.check_is_in_stock(page, denomination)
                    if is_in_stock:
                        available_denominations = [denomination]
            except Exception as e:
                logger.warning(f"[Sniper #{attempts}] Error during stock check: {e}")
                if attempts == 1:
                    try:
                        await broadcast_sniper_message(
                            bot,
                            text=f"⚠️ Rooter page notice: <code>{html.escape(str(e)[:100])}</code>. Continuing check...",
                        )
                    except Exception:
                        pass

            if attempts == 1 and not is_in_stock:
                status_desc = "PlayStation Gift Cards (₹1,000, ₹2,000, ₹3,000, ₹5,000)" if is_any_mode else f"{prod_name} ₹{denomination:,}"
                try:
                    await broadcast_sniper_message(
                        bot,
                        text=(
                            f"ℹ️ <b>Stock Status:</b> {status_desc} abhi Rooter par <b>Out of Stock</b> hai.\n"
                            f"🔄 <i>Monitoring actively every {config.SNIPE_INTERVAL_SECONDS}s. Jaise hi restock hoga, turant buy kar lega!</i>"
                        ),
                    )
                except Exception:
                    pass

            if is_in_stock:
                logger.info(f"🚨 [Sniper #{attempts}] STOCK DETECTED on {platform}: {available_denominations}!")

                # Retrieve all active accounts for multi-account buying
                active_accounts = account_manager.get_active()
                if not active_accounts:
                    active_accounts = [{
                        "id": "acc_1",
                        "label": "Account 1 (Primary)",
                        "token": config.ROOTER_AUTH_TOKEN,
                        "wallet_balance": 0.0,
                    }]

                order_tasks = []
                for acc in active_accounts:
                    bal = float(acc.get("wallet_balance", 0.0))
                    acc_label = acc.get("label", acc.get("id"))
                    target_d = None
                    target_q = 1

                    if bal > 0:
                        # High-to-low priority: 5000 -> 4000 -> 3000 -> 2000 -> 1000
                        for cand_d in available_denominations:
                            if cand_d <= bal:
                                target_d = cand_d
                                target_q = 1  # Rooter restricts PlayStation to 1 card per transaction
                                break
                    else:
                        # Balance untracked: pick highest available denomination, quantity 1
                        target_d = available_denominations[0] if available_denominations else 1000
                        target_q = 1

                    if target_d is not None:
                        order_tasks.append((acc, target_d, target_q))
                    else:
                        min_avail = min(available_denominations) if available_denominations else 1000
                        logger.info(f"[Sniper] Account {acc_label} skipped: Balance ₹{bal:,.0f} < lowest in-stock card ₹{min_avail:,}")
                        asyncio.create_task(
                            broadcast_sniper_message(
                                bot,
                                text=f"⚠️ <b>{html.escape(acc_label)} Skipped:</b> Balance ₹{bal:,.0f} is insufficient for in-stock card ₹{min_avail:,}.",
                            )
                        )

                if not order_tasks:
                    logger.warning("[Sniper] Stock detected but no active accounts have sufficient balance.")
                    continue

                # Notify all Telegram users simultaneously in background so checkout is NOT delayed by even 1ms
                acc_summary = ", ".join([f"{a.get('label', a['id'])} (₹{d:,} x{q})" for a, d, q in order_tasks])
                asyncio.create_task(
                    broadcast_sniper_message(
                        bot,
                        text=(
                            f"🚨 <b>STOCK DETECTED!</b>\n\n"
                            f"🎯 <b>Platform:</b> {plat_name}\n"
                            f"📦 <b>In-Stock Denominations:</b> {', '.join([f'₹{d:,}' for d in available_denominations])}\n"
                            f"👥 <b>Executing Parallel 1-Click Buy for {len(order_tasks)} Account(s):</b>\n"
                            f"<i>{html.escape(acc_summary)}</i>\n\n"
                            f"⚡ <b>All accounts firing simultaneously with Rooter Wallet...</b>"
                        ),
                    )
                )

                # Execute orders: Account 1 buys INSTANTLY on the already-loaded monitor page (Zero Load Lag)
                # Additional accounts execute in isolated parallel browser contexts
                async def execute_account_order(idx, acc_data, d_val, q_val):
                    acc_tok = acc_data.get("token") or config.ROOTER_AUTH_TOKEN
                    acc_lbl = acc_data.get("label", acc_data.get("id"))

                    if idx == 0:
                        # Account 1 fires directly on the existing live page! Zero navigation delay (<50ms)!
                        try:
                            res = await service.execute_buy_flow(
                                page=page,
                                denomination=d_val,
                                quantity=q_val,
                                account_label=acc_lbl,
                                simulation=config.SIMULATION_MODE,
                            )
                            return (acc_data, d_val, q_val, res)
                        except Exception as e1:
                            logger.error(f"[Sniper] Primary account error on monitor page: {e1}")
                            return (acc_data, d_val, q_val, PurchaseResult(success=False, platform="rooter", denomination=d_val, message=str(e1)))

                    # Accounts 2..N use parallel isolated contexts
                    acc_ctx = await browser_manager.create_context(custom_token=acc_tok)
                    acc_page = await acc_ctx.new_page()
                    try:
                        res = await service.execute_buy_flow(
                            page=acc_page,
                            denomination=d_val,
                            quantity=q_val,
                            account_label=acc_lbl,
                            simulation=config.SIMULATION_MODE,
                        )
                        return (acc_data, d_val, q_val, res)
                    finally:
                        try:
                            await acc_page.close()
                            await acc_ctx.close()
                        except Exception:
                            pass

                results = await asyncio.gather(
                    *[execute_account_order(i, a, d, q) for i, (a, d, q) in enumerate(order_tasks)],
                    return_exceptions=True
                )

                any_success = False
                failure_messages = []
                for item in results:
                    if isinstance(item, Exception):
                        logger.error(f"[Sniper] Account order exception: {item}")
                        failure_messages.append(f"Unexpected error: {str(item)[:120]}")
                        continue

                    acc_data, d_val, q_val, result = item
                    acc_lbl = html.escape(acc_data.get("label", acc_data.get("id")))

                    if result.success:
                        any_success = True
                        sim_badge = " [SIMULATED TEST]" if result.simulation else ""
                        total_paid = d_val * q_val
                        # Fetch real-time live balance directly from Rooter API
                        try:
                            live_bal = await account_manager.refresh_account_balance(acc_data.get("id"))
                            rem_bal = live_bal if live_bal is not None else float(acc_data.get("wallet_balance", 0.0))
                        except Exception:
                            account_manager.deduct_balance(acc_data.get("id"), total_paid)
                            rem_bal = float(acc_data.get("wallet_balance", 0.0))

                        codes_display = ""
                        if result.codes and len(result.codes) > 1:
                            codes_display = "\n".join([f"   {i+1}. <code>{html.escape(c)}</code>" for i, c in enumerate(result.codes)])
                        else:
                            codes_display = f"<code>{html.escape(result.voucher_code or 'N/A')}</code>"

                        v_pin = html.escape(result.voucher_pin or "N/A")
                        o_id = html.escape(result.order_id or "N/A")

                        success_text = (
                            f"🎉 <b>PURCHASE SUCCESSFUL!{sim_badge}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 <b>Account:</b> {acc_lbl}\n"
                            f"🎯 <b>Platform:</b> {plat_name}\n"
                            f"📦 <b>Item:</b> PlayStation Gift Card (Qty: {result.quantity})\n"
                            f"💰 <b>Denomination:</b> ₹{result.denomination:,} each (Total Paid: ₹{total_paid:,})\n"
                            f"🔑 <b>Voucher Code(s):</b>\n{codes_display}\n"
                            f"🔒 <b>PIN / Key:</b> <code>{v_pin}</code>\n"
                            f"🧾 <b>Order ID:</b> <code>{o_id}</code>\n"
                            f"💳 <b>Remaining Balance:</b> ₹{rem_bal:,.0f}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"✨ <i>Auto-Sniper successfully claimed your vouchers!</i>\n"
                            f"{redeem_tip}"
                        )
                        try:
                            shot_file = result.error_screenshot
                            await broadcast_sniper_message(
                                bot,
                                text=success_text,
                                reply_markup=get_main_menu_keyboard(),
                                photo_path=shot_file if (shot_file and os.path.exists(shot_file)) else None,
                            )
                        except Exception as me:
                            logger.warning(f"Error broadcasting success message: {me}")
                    else:
                        logger.warning(f"[Sniper] Purchase failed for {acc_lbl}: {result.message}")
                        failure_messages.append(f"{acc_lbl}: {result.message}")

                if any_success:
                    logger.info("[Sniper] Purchase completed successfully for account(s). Finishing sniper run.")
                    break
                else:
                    summary_fails = "\n".join([f"• <code>{html.escape(m)}</code>" for m in failure_messages])
                    logger.warning(f"[Sniper #{attempts}] Purchase could not complete:\n{summary_fails}")
                    try:
                        await broadcast_sniper_message(
                            bot,
                            text=(
                                f"⚠️ <b>Sniper Alert ({plat_name}):</b> Checkout could not complete:\n"
                                f"{summary_fails}\n\n"
                                f"<i>Monitoring will continue in the next cycle...</i>"
                            ),
                            reply_markup=get_stop_snipe_keyboard(),
                        )
                    except Exception as me:
                        logger.warning(f"Error broadcasting sniper alert: {me}")

            # Heartbeat message (Disabled by default to avoid chat spam and save credit)
            if config.ENABLE_SNIPER_HEARTBEAT and attempts % 20 == 0:
                try:
                    await broadcast_sniper_message(
                        bot,
                        text=(
                            f"🔄 <b>Auto-Sniper Running (24/7 Restock Monitor)</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Platform:</b> {plat_name}\n"
                            f"• <b>Target:</b> PlayStation ₹{denomination:,}\n"
                            f"• <b>Refreshes Completed:</b> <code>{attempts}</code>\n"
                            f"• <b>Status:</b> Actively checking every {config.SNIPE_INTERVAL_SECONDS}s. Ready to buy instantly when stock arrives!\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━"
                        ),
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
        logger.info(f"Sniper task was cancelled.")
    except Exception as e:
        logger.error(f"Error in sniper loop: {e}", exc_info=True)
        try:
            await broadcast_sniper_message(
                bot,
                text=f"❌ <b>Auto-Sniper Error:</b> <code>{html.escape(str(e))}</code>\nMonitoring stopped.",
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
        GLOBAL_SNIPER["is_running"] = False
        GLOBAL_SNIPER["task"] = None
        ACTIVE_SNIPERS.clear()
        logger.info(f"Sniper loop closed.")

async def launch_sniper(update: Update, context: ContextTypes.DEFAULT_TYPE, platform: str, denomination: int):
    """Common launcher for auto-sniper background monitoring."""
    user = update.effective_user
    user_id = user.id if user else 0
    chat_id = update.effective_chat.id
    plat_name = config.PLATFORMS.get(platform, {}).get("name", platform.title())

    # Pre-flight check: ensure active session exists OR active accounts in account_manager exist
    has_active_accs = bool(account_manager.get_active())
    if not browser_manager.has_session(user_id, platform) and not has_active_accs:
        warn_text = (
            "⚠️ <b>Rooter Account Logged In Nahi Hai!</b>\n\n"
            "Cloud server restart hone ki wajah se session reset ho gaya hai ya Bearer token missing hai.\n\n"
            "👉 Kripya pehle <code>/login</code> dabayein aur <b>Paste Bearer Token</b> select karke apna token paste karein.\n\n"
            "💡 <i>Tip: Railway Variables me <code>ROOTER_AUTH_TOKEN</code> set karne se token kabhi reset nahi hoga!</i>"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(text=warn_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard())
        else:
            await update.message.reply_text(text=warn_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    # Reject Google Play / Play Store denominations
    if 0 < denomination < 1000:
        warn_text = (
            "⚠️ <b>Play Store Buying Disabled!</b>\n\n"
            "Google Play recharge code buying stop aur disable kar di gayi hai.\n"
            "Bot ab sirf aur sirf <b>PlayStation Gift Cards (₹1,000 to ₹5,000)</b> buy karega.\n\n"
            "👉 PlayStation sniper start karne ke liye <code>/snipe</code> dabayein!"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(text=warn_text, parse_mode=ParseMode.HTML, reply_markup=get_playstore_stopped_keyboard())
        else:
            await update.message.reply_text(text=warn_text, parse_mode=ParseMode.HTML, reply_markup=get_playstore_stopped_keyboard())
        return ConversationHandler.END

    # Always register caller's chat_id in global sniper notification list
    GLOBAL_SNIPER["chat_ids"].add(chat_id)

    # Check if Global Sniper is already active
    is_currently_running = GLOBAL_SNIPER.get("is_running") and GLOBAL_SNIPER.get("task") and not GLOBAL_SNIPER["task"].done()

    if is_currently_running and GLOBAL_SNIPER.get("denomination") == denomination:
        checks = GLOBAL_SNIPER.get("attempts", 0)
        target_name = "⚡ Any PlayStation Card (₹1,000 to ₹5,000)" if denomination == 0 else f"PlayStation ₹{denomination:,}"
        already_msg = (
            f"✅ <b>Auto-Sniper Already Active & Running!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> {target_name}\n"
            f"• <b>Total Checks:</b> <code>{checks}</code>\n"
            f"• <b>Refresh Rate:</b> Every {config.SNIPE_INTERVAL_SECONDS}s\n"
            f"• <b>Subscribed Chats:</b> <code>{len(GLOBAL_SNIPER['chat_ids'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 <b>Aapka Telegram chat alert list me include ho gaya hai!</b>\n"
            f"Jaise hi stock detect hoga aur buy hoga, confirmation aur codes aap dono ko simultaneously aayenge.\n\n"
            f"<i>Stop karne ke liye <code>/stop</code> dabayein.</i>"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(text=already_msg, parse_mode=ParseMode.HTML, reply_markup=get_stop_snipe_keyboard())
        else:
            await update.message.reply_text(text=already_msg, parse_mode=ParseMode.HTML, reply_markup=get_stop_snipe_keyboard())
        return ConversationHandler.END

    # If already running with a different denomination, stop previous task cleanly before restarting
    if is_currently_running:
        if GLOBAL_SNIPER.get("stop_event"):
            GLOBAL_SNIPER["stop_event"].set()
        if GLOBAL_SNIPER.get("task") and not GLOBAL_SNIPER["task"].done():
            GLOBAL_SNIPER["task"].cancel()
        logger.info(f"Switching global sniper target from ₹{GLOBAL_SNIPER.get('denomination')} to ₹{denomination}")

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

    GLOBAL_SNIPER["task"] = task
    GLOBAL_SNIPER["stop_event"] = stop_event
    GLOBAL_SNIPER["platform"] = platform
    GLOBAL_SNIPER["denomination"] = denomination
    GLOBAL_SNIPER["is_running"] = True
    GLOBAL_SNIPER["started_by_user_id"] = user_id
    GLOBAL_SNIPER["started_by_name"] = user.first_name if user and user.first_name else "User"

    ACTIVE_SNIPERS[user_id] = GLOBAL_SNIPER

    mode_text = "🧪 Simulation (Dry Run)" if config.SIMULATION_MODE else "⚡ Live Purchasing (Real Checkout)"
    if denomination == 0:
        prod_name = "⚡ Any PlayStation Card (₹1,000 to ₹5,000)"
        note_text = "✅ <b>Multi-Card Restock Monitor Active:</b> Rooter par ₹1,000, ₹2,000, ₹3,000 ya ₹5,000 me se jo bhi denomination pehle stock me aayega, bot usko turant 1 second me buy kar lega!"
    else:
        prod_name = f"PlayStation ₹{denomination:,}"
        note_text = f"✅ <b>24/7 Restock Monitor Active:</b> Jaise hi PlayStation voucher stock me aayega, bot bina kisi delay ke turant buy kar lega aur voucher code aapko yahan message kar dega."

    success_text = (
        f"🚀 <b>Auto-Sniper Activated!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Platform:</b> {plat_name}\n"
        f"💰 <b>Target Voucher:</b> {prod_name}\n"
        f"⏱️ <b>Refresh Rate:</b> Every {config.SNIPE_INTERVAL_SECONDS} seconds\n"
        f"⚡ <b>Mode:</b> <code>{mode_text}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{note_text}\n\n"
        f"<i>Aap Telegram band kar sakte hain ya doosra kaam kar sakte hain. Stop karne ke liye <code>/stop</code> dabayein.</i>"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=success_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_stop_snipe_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=success_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_stop_snipe_keyboard(),
        )
    return ConversationHandler.END


async def snipe_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the 24/7 auto-sniper restock flow."""
    user_id = update.effective_user.id if update.effective_user else 0
    query = update.callback_query

    # Register chat_id
    if update.effective_chat:
        GLOBAL_SNIPER["chat_ids"].add(update.effective_chat.id)

    # Check if arguments provided in slash command, e.g. /snipe any, /snipe 1000, /snipe 2000
    if context.args and len(context.args) > 0:
        raw_arg = context.args[0].lower().strip().replace("k", "000").replace("₹", "").replace("rs", "").replace(".", "")
        if raw_arg in ("stop", "playstore", "googleplay", "gplay", "stop_playstore", "10"):
            return await stop_playstore_handler(update, context)
        elif raw_arg in ("any", "all", "auto", "0"):
            return await launch_sniper(update, context, "rooter", 0)
        elif raw_arg.isdigit():
            val = int(raw_arg)
            if val < 1000:
                return await stop_playstore_handler(update, context)
            return await launch_sniper(update, context, "rooter", val)

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
        f"<i>(⚡ <b>Any PlayStation Card</b> select karne se ₹1k, ₹2k, ₹3k, ₹5k me jo bhi pehle aayega turant buy ho jayega!)</i>{login_note}"
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

    return await launch_sniper(update, context, platform, denomination)

async def stop_snipe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stops the active auto-sniper background process for all subscribed users."""
    user = update.effective_user
    user_name = html.escape(user.first_name if user and user.first_name else "User")
    query = update.callback_query

    is_running = GLOBAL_SNIPER.get("is_running") and GLOBAL_SNIPER.get("task") and not GLOBAL_SNIPER["task"].done()

    if is_running:
        stop_event = GLOBAL_SNIPER.get("stop_event")
        if stop_event:
            stop_event.set()
        task = GLOBAL_SNIPER.get("task")
        if task and not task.done():
            task.cancel()

        p_name = config.PLATFORMS.get(GLOBAL_SNIPER.get("platform", "rooter"), {}).get("name", "Rooter Shop")
        d_val = GLOBAL_SNIPER.get("denomination", 0)
        target_name = "Any PlayStation (₹1k-₹5k)" if d_val == 0 else f"PlayStation ₹{d_val:,}"
        checks = GLOBAL_SNIPER.get("attempts", 0)

        GLOBAL_SNIPER["is_running"] = False
        GLOBAL_SNIPER["task"] = None
        ACTIVE_SNIPERS.clear()

        msg = (
            f"🛑 <b>Auto-Sniper Stopped!</b>\n\n"
            f"• <b>Stopped By:</b> {user_name}\n"
            f"• <b>Platform:</b> {p_name}\n"
            f"• <b>Target:</b> {target_name}\n"
            f"• <b>Total Page Checks:</b> <code>{checks}</code>\n\n"
            f"Stock monitoring paused. You can restart anytime with /snipe or /start."
        )
        if query:
            await query.answer("Auto-Sniper stopped.")
        await broadcast_sniper_message(context.bot, text=msg, reply_markup=get_main_menu_keyboard())
    else:
        msg = "ℹ️ <b>No active auto-sniper is currently running.</b>\nStart one with /snipe."
        if query:
            await query.answer("No active sniper.")
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

async def stop_playstore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stops Google Play / Play Store buying and locks the bot into PlayStation Only mode."""
    user = update.effective_user
    user_name = html.escape(user.first_name if user and user.first_name else "User")
    query = update.callback_query

    was_running = GLOBAL_SNIPER.get("is_running") and GLOBAL_SNIPER.get("task") and not GLOBAL_SNIPER["task"].done()

    if was_running:
        stop_event = GLOBAL_SNIPER.get("stop_event")
        if stop_event:
            stop_event.set()
        task = GLOBAL_SNIPER.get("task")
        if task and not task.done():
            task.cancel()
        GLOBAL_SNIPER["is_running"] = False
        GLOBAL_SNIPER["task"] = None
        ACTIVE_SNIPERS.clear()
    was_playstore = False
    target_name = "None"

    if user_id in ACTIVE_SNIPERS:
        sniper_data = ACTIVE_SNIPERS.pop(user_id)
        was_running = True
        stop_event = sniper_data.get("stop_event")
        if stop_event:
            stop_event.set()
        task = sniper_data.get("task")
        if task and not task.done():
            task.cancel()

        d = sniper_data.get("denomination", 0)
        if d == 10 or (0 < d < 1000):
            was_playstore = True
            target_name = "Google Play Recharge Code"
        elif d == 0:
            target_name = "Any PlayStation Card (₹1k-₹5k)"
        else:
            target_name = f"PlayStation ₹{d:,}"

    run_status = ""
    if was_playstore:
        run_status = f"🛑 <b>Active Play Store Sniper Stopped:</b> <code>{target_name}</code> has been terminated.\n\n"
    elif was_running:
        run_status = f"🛑 <b>Previous Monitor Stopped:</b> <code>{target_name}</code> has been paused.\n\n"

    msg = (
        "🛑 <b>Play Store Auto-Buy STOPPED!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{run_status}"
        "✅ <b>PlayStation Only Mode Active:</b>\n"
        "• <b>Play Store Gift Cards:</b> ❌ Completely Stopped & Disabled\n"
        "• <b>Target:</b> 🎮 <b>PlayStation Gift Cards ONLY (₹1,000 to ₹5,000)</b>\n"
        "• <b>Multi-Account Sniper:</b> Stock aane par sabhi 5-10 accounts balance-aware parallel buy karenge!\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>PlayStation 24/7 restock monitor start karne ke liye neeche button dabayein:</i>"
    )

    if query:
        await query.answer("Play Store buying stopped. Only PlayStation mode active.")
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_playstore_stopped_keyboard(),
        )
    else:
        await update.message.reply_text(
            text=msg,
            parse_mode=ParseMode.HTML,
            reply_markup=get_playstore_stopped_keyboard(),
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
    """Receives raw Bearer token or JSON cookies, saves session, and auto-registers into AccountManager."""
    user = update.effective_user
    user_id = user.id if user else 0
    raw_text = update.message.text.strip()
    platform = "rooter"

    clean_tok = raw_text
    if clean_tok.lower().startswith("bearer "):
        clean_tok = clean_tok[7:].strip()

    success = browser_manager.import_session_json(user_id, platform, clean_tok)

    added_acc = None
    if clean_tok.startswith("eyJ"):
        try:
            uname = user.first_name if user and user.first_name else f"Telegram {user_id}"
            added_acc = await account_manager.add_account_async(
                token=clean_tok,
                label=f"Account ({uname})",
            )
        except Exception as e:
            logger.warning(f"Failed to auto-register imported token into AccountManager: {e}")

    if success or added_acc:
        acc_info = ""
        if added_acc:
            acc_info = (
                f"\n\n👥 <b>Multi-Account Manager Synchronized:</b>\n"
                f"• <b>Label:</b> {html.escape(added_acc.get('label', ''))}\n"
                f"• <b>Account ID:</b> <code>{added_acc.get('id')}</code>\n"
                f"• <b>User ID:</b> <code>{added_acc.get('user_id')}</code>\n"
                f"• <b>Live Wallet Balance:</b> <b>₹{added_acc.get('wallet_balance'):,.2f}</b> [Rooter Live 🟢]\n"
                f"• <b>Sniper Status:</b> 🟢 Ready for 24/7 Restock Parallel Buying!"
            )
        await update.message.reply_text(
            f"✅ <b>Authentication token successfully saved for {platform.title()}!</b>{acc_info}\n\n"
            f"Restock sniper start karne ke liye <code>/snipe</code> dabayein ya <code>/accounts</code> se list check karein.",
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


# ==================== MULTI-ACCOUNT MANAGEMENT ====================

def format_accounts_text() -> str:
    """Builds an informative message listing all accounts, balances, and active states."""
    accounts = account_manager.get_all()
    if not accounts:
        return (
            "👥 <b>Rooter Accounts (0 Configured)</b>\n\n"
            "Abhi koi account configured nahi hai.\n"
            "Naya account add karne ke liye neeche diye button par click karein ya command use karein:\n"
            "<code>/addaccount &lt;bearer_token&gt; [label]</code>"
        )

    active_accs = account_manager.get_active()
    total_bal = account_manager.get_total_balance()

    lines = [
        "👥 <b>Rooter Accounts Manager (Multi-Account)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Total Accounts:</b> {len(accounts)}",
        f"• <b>Active for Sniping:</b> 🟢 {len(active_accs)} / {len(accounts)}",
        f"• <b>Combined Live Balance:</b> ₹{total_bal:,.2f}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Registered Accounts:</b>",
    ]

    for idx, acc in enumerate(accounts, 1):
        status_icon = "🟢 Active" if acc.get("is_active", True) else "⏸️ Paused"
        lbl = html.escape(acc.get("label", acc.get("id")))
        bal = float(acc.get("wallet_balance", 0.0))
        uid = acc.get("user_id") or "N/A"
        tok_preview = acc.get("token", "")[:12] + "..." if acc.get("token") else "None"
        lines.append(
            f"{idx}. <b>{lbl}</b> [{status_icon}]\n"
            f"   • ID: <code>{acc.get('id')}</code> | UID: <code>{uid}</code>\n"
            f"   • Live Wallet Balance: <b>₹{bal:,.2f}</b> [Rooter Live 🟢]\n"
            f"   • Token: <code>{tok_preview}</code>"
        )

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 <i>Tap an account button below to pause/resume it.</i>",
        "💡 <i>Balances are automatically synced in real-time from Rooter!</i>",
        "💡 <i>Optional override: <code>/setbalance &lt;acc_id&gt; &lt;amount&gt;</code></i>",
    ])
    return "\n".join(lines)


async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the multi-account dashboard and interactive buttons with live balance sync."""
    try:
        await account_manager.sync_all_balances()
    except Exception as e:
        logger.debug(f"Live balance sync notice: {e}")

    text = format_accounts_text()
    accounts = account_manager.get_all()
    markup = get_accounts_keyboard(accounts)

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def acc_add_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts the user to paste Bearer token for adding a new Rooter account."""
    query = update.callback_query
    prompt_text = (
        "➕ <b>Add New Rooter Account (5-10 Multi-Account)</b>\n\n"
        "Apne naye Rooter account ka <b>Bearer Token</b> yahan chat me paste karein:\n\n"
        "💡 <b>Optional format:</b>\n"
        "<code>&lt;bearer_token&gt; [label]</code>\n\n"
        "<b>Example:</b>\n"
        "<code>eyJhbGciOi... Account-2</code>\n\n"
        "<i>(Balance set karne ki zaroorat nahi hai, bot Rooter se live balance auto-fetch kar lega!)</i>"
    )
    if query:
        await query.answer()
        await query.edit_message_text(text=prompt_text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_keyboard())
    else:
        await update.message.reply_text(text=prompt_text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_keyboard())
    return BotState.AWAITING_ADD_ACCOUNT_DATA


async def handle_add_account_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles user input containing new account token, label, and balance."""
    raw_text = update.message.text.strip()
    parts = raw_text.split()
    if not parts:
        await update.message.reply_text("❌ Input empty. Please provide a valid Bearer token.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    token = parts[0]
    label = None
    balance = 0.0

    if len(parts) >= 2:
        if parts[1].replace(".", "", 1).isdigit():
            balance = float(parts[1])
        else:
            label = parts[1]

    if len(parts) >= 3:
        if parts[2].replace(".", "", 1).isdigit():
            balance = float(parts[2])
        elif not label:
            label = parts[2]

    try:
        acc = await account_manager.add_account_async(token=token, label=label, wallet_balance=balance)
        success_text = (
            f"✅ <b>Account Added Successfully!</b>\n\n"
            f"• <b>Label:</b> {html.escape(acc.get('label'))}\n"
            f"• <b>ID:</b> <code>{acc.get('id')}</code>\n"
            f"• <b>User ID:</b> <code>{acc.get('user_id')}</code>\n"
            f"• <b>Live Wallet Balance:</b> <b>₹{acc.get('wallet_balance'):,.2f}</b> (Rooter Verified 🟢)\n"
            f"• <b>Status:</b> 🟢 Active for Auto-Snipe\n\n"
            f"Restock aane par ye account baaki sabhi accounts ke sath parallel me buy karega!"
        )
        accounts = account_manager.get_all()
        await update.message.reply_text(
            text=success_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_accounts_keyboard(accounts),
        )
    except Exception as e:
        logger.error(f"Failed to add account: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Failed to add account: {e}", reply_markup=get_main_menu_keyboard())

    return ConversationHandler.END


async def acc_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggles active status of an account via inline button."""
    query = update.callback_query
    await query.answer()

    acc_id = query.data.split(":")[1]
    new_state = account_manager.toggle_active(acc_id)
    if new_state is not None:
        state_str = "🟢 Active" if new_state else "⏸️ Paused"
        acc = account_manager.get_account(acc_id)
        lbl = acc.get("label", acc_id) if acc else acc_id
        await query.answer(f"{lbl} is now {state_str}")

    text = format_accounts_text()
    accounts = account_manager.get_all()
    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=get_accounts_keyboard(accounts))


async def acc_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes an account via inline button."""
    query = update.callback_query
    await query.answer()

    acc_id = query.data.split(":")[1]
    account_manager.remove_account(acc_id)

    text = format_accounts_text()
    accounts = account_manager.get_all()
    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=get_accounts_keyboard(accounts))


async def add_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slash command to add an account: /addaccount <token> [label] [balance]"""
    if not context.args or len(context.args) == 0:
        return await acc_add_prompt_handler(update, context)

    token = context.args[0]
    label = context.args[1] if len(context.args) > 1 and not context.args[1].replace(".", "", 1).isdigit() else None
    balance = 0.0

    for arg in context.args[1:]:
        if arg.replace(".", "", 1).isdigit():
            balance = float(arg)
            break

    acc = await account_manager.add_account_async(token=token, label=label, wallet_balance=balance)
    await update.message.reply_text(
        f"✅ <b>Account Added / Updated:</b> {html.escape(acc.get('label'))} (Live Balance: ₹{acc.get('wallet_balance'):,.2f})",
        parse_mode=ParseMode.HTML,
        reply_markup=get_accounts_keyboard(account_manager.get_all()),
    )


async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slash command to update an account balance: /setbalance <acc_id_or_number> <amount>"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "ℹ️ <b>Usage:</b> <code>/setbalance &lt;acc_id&gt; &lt;amount&gt;</code>\n"
            "<b>Example:</b> <code>/setbalance acc_1 1084</code> or <code>/setbalance 1 5000</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_id = context.args[0].strip().lower()
    acc_id = f"acc_{raw_id}" if raw_id.isdigit() else raw_id
    try:
        amount = float(context.args[1].replace(",", "").replace("₹", ""))
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Example: <code>/setbalance acc_1 1084</code>", parse_mode=ParseMode.HTML)
        return

    success = account_manager.update_balance(acc_id, amount)
    if success:
        acc = account_manager.get_account(acc_id)
        lbl = acc.get("label", acc_id) if acc else acc_id
        await update.message.reply_text(
            f"✅ <b>Balance Updated:</b> {html.escape(lbl)} wallet balance is now <b>₹{amount:,.0f}</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_accounts_keyboard(account_manager.get_all()),
        )
    else:
        await update.message.reply_text(
            f"❌ Account <code>{html.escape(acc_id)}</code> nahi mila! Check <code>/accounts</code>.",
            parse_mode=ParseMode.HTML,
        )

