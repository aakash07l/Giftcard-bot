"""
Main entry point for PlayStation Gift Card Telegram Bot.
Builds the Telegram Application, registers conversation handlers, and starts polling.
"""

import sys
from pathlib import Path

# Add project root to sys.path so modules are discovered consistently
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import logging
import asyncio
import warnings
from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

import config
from bot.states import BotState
from bot.handlers import (
    start_command,
    help_command,
    status_command,
    toggle_sim_handler,
    buy_start_handler,
    buy_platform_selected,
    buy_denomination_selected,
    confirm_buy_execution,
    login_start_handler,
    login_platform_selected,
    login_method_selected,
    handle_phone_received,
    handle_otp_received,
    handle_cookie_received,
    cancel_flow,
)
from services.browser_manager import browser_manager

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ps_giftcard_bot")

def build_application():
    """Constructs the Telegram bot application and wires all handlers."""
    if not config.BOT_TOKEN or config.BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("FATAL: BOT_TOKEN is not configured! Please set BOT_TOKEN in .env")
        sys.exit(1)

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # 1. Buy Flow Conversation Handler
    buy_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("buy", buy_start_handler),
            CallbackQueryHandler(buy_start_handler, pattern="^buy_start$"),
            CallbackQueryHandler(confirm_buy_execution, pattern="^confirm_buy:"),
        ],
        states={
            BotState.SELECT_BUY_PLATFORM: [
                CallbackQueryHandler(buy_platform_selected, pattern="^buy_plat:"),
            ],
            BotState.SELECT_BUY_DENOMINATION: [
                CallbackQueryHandler(buy_denomination_selected, pattern="^denom_pick:"),
                CallbackQueryHandler(buy_start_handler, pattern="^buy_start$"),
            ],
            BotState.AWAITING_CONFIRMATION: [
                CallbackQueryHandler(confirm_buy_execution, pattern="^confirm_buy:"),
                CallbackQueryHandler(buy_platform_selected, pattern="^buy_plat:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_flow),
            CallbackQueryHandler(cancel_flow, pattern="^cancel_action$"),
            CallbackQueryHandler(start_command, pattern="^nav_main_menu$"),
        ],
        allow_reentry=True,
    )

    # 2. Login Flow Conversation Handler
    login_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("login", login_start_handler),
            CallbackQueryHandler(login_start_handler, pattern="^login_start$"),
        ],
        states={
            BotState.SELECT_LOGIN_PLATFORM: [
                CallbackQueryHandler(login_platform_selected, pattern="^login_plat:"),
            ],
            BotState.SELECT_LOGIN_METHOD: [
                CallbackQueryHandler(login_method_selected, pattern="^login_method:"),
                CallbackQueryHandler(login_start_handler, pattern="^login_start$"),
            ],
            BotState.AWAITING_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_received),
            ],
            BotState.AWAITING_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_otp_received),
            ],
            BotState.AWAITING_COOKIE_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_received),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_flow),
            CallbackQueryHandler(cancel_flow, pattern="^cancel_action$"),
            CallbackQueryHandler(start_command, pattern="^nav_main_menu$"),
        ],
        allow_reentry=True,
    )

    # Register conversations
    app.add_handler(buy_conversation)
    app.add_handler(login_conversation)

    # Register general command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("toggle_sim", toggle_sim_handler))
    app.add_handler(CommandHandler("cancel", cancel_flow))

    # Register navigation callbacks
    app.add_handler(CallbackQueryHandler(start_command, pattern="^nav_main_menu$"))
    app.add_handler(CallbackQueryHandler(status_command, pattern="^status_check$"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="^help_info$"))
    app.add_handler(CallbackQueryHandler(toggle_sim_handler, pattern="^toggle_sim$"))
    app.add_handler(CallbackQueryHandler(cancel_flow, pattern="^cancel_action$"))

    # Global error handler
    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Exception while handling an update:", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Something went wrong. Please send /start to reload the menu."
                )
            except Exception:
                pass

    app.add_error_handler(global_error_handler)

    return app

def main():
    """Starts the Telegram bot polling service."""
    logger.info("Initializing PlayStation Gift Card Telegram Bot...")
    logger.info(f"Simulation Mode: {config.SIMULATION_MODE}")
    logger.info(f"Headless Browser: {config.HEADLESS}")

    app = build_application()

    print("\n" + "=" * 55)
    print("🎮 PLAYSTATION GIFT CARD BUYER BOT STARTED")
    print(f"• Mode: {'SIMULATION (Safe)' if config.SIMULATION_MODE else 'LIVE PURCHASING'}")
    print(f"• Token Loaded: {config.BOT_TOKEN[:10]}...***")
    print("• Listening for Telegram messages and commands...")
    print("=" * 55 + "\n")

    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        # Clean up browser resources
        loop = asyncio.new_event_loop()
        loop.run_until_complete(browser_manager.close())
        loop.close()

if __name__ == "__main__":
    main()
