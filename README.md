# 🎮 PlayStation 4K Gift Card Telegram Bot (Rooter Shop)

An automated Python Telegram bot built on top of the tested **October 16–17 PlayStation restock auto-buyer engine** (`python-telegram-bot` + `Playwright`).
It monitors and buys **₹4,000 PlayStation Gift Cards / Wallet Vouchers** directly from **Rooter Shop** using your Rooter wallet balance, supporting **multiple Telegram users** and **multi-account parallel buying**.

---

## 🌟 Key Features

1. **4K PlayStation Exclusive Targeting**:
   - Strictly monitors and grabs **₹4,000 PlayStation Gift Cards** on Rooter Shop.
   - Auto-bypasses location prompts and regional dialogs.
   - Executes instant 1-click buy using Rooter Wallet balance the second stock restocks.

2. **Multi-User Telegram Access**:
   - Multiple Telegram user accounts can operate and monitor the bot concurrently (`ADMIN_CHAT_IDS`).
   - Every authorized user can send `/start`, check live `/status`, start `/snipe`, and receive instant voucher delivery notifications.

3. **Multi-Account Parallel Buying (5–10 Accounts)**:
   - Manages multiple Rooter user tokens with live balance auto-sync (`https://payments.rooter.io/wallet/balance`).
   - Automatically distributes purchases across accounts based on available balance and `MAX_CARDS_PER_ACCOUNT`.

4. **Telegram Commands & Interactive Dashboard**:
   - `/start`: Interactive dashboard with live wallet balances and quick-action buttons.
   - `/snipe`: Starts the 24/7 restock sniper loop (refreshes every 29 seconds).
   - `/stop`: Stops active restock monitoring.
   - `/status`: Displays active accounts, balances, and sniper status.
   - `/accounts`: Manage accounts, toggle active/paused states, or add new tokens.
   - `/toggle_sim`: Switch between Safe Simulation Mode and Live Purchasing.

---

## 📁 Project Structure

```
Play-Card-Bot/
├── .env                       # Bot token and environment variables
├── .env.example               # Example template for environment variables
├── requirements.txt           # Python package dependencies
├── Procfile                   # Worker definition for Railway / Heroku
├── Dockerfile                 # Container image for Railway / VPS
├── railway.json               # Railway deployment configuration
├── config.py                  # Bot settings, admin IDs, and 4K denomination
├── main.py                    # Application entry point and Telegram polling
├── start_bot.bat              # 1-click Windows start script
├── bot/
│   ├── __init__.py
│   ├── states.py              # ConversationHandler states
│   ├── keyboards.py           # Dedicated 4K inline keyboards & menus
│   └── handlers.py            # Command handlers and auto-sniper worker
├── services/
│   ├── __init__.py
│   ├── base_platform.py       # Base platform interface and data models
│   ├── browser_manager.py     # Playwright lifecycle & session manager
│   ├── account_manager.py     # Multi-account manager with live balance sync
│   └── rooter_service.py      # Rooter 4K voucher checkout & redemption
└── sessions/                  # Stored authenticated accounts
```

---

## 🚀 Environment Variables

- `BOT_TOKEN`: `8918128794:AAFYwsRDHm--pZwe9jm9pnBQe0PWUve4nck`
- `ADMIN_CHAT_IDS`: `5701727023,1988639571,828429985,8801210593`
- `TARGET_DENOMINATION`: `4000`
- `MAX_CARDS_PER_ACCOUNT`: `2`
- `SIMULATION_MODE`: `False` (for real purchases)
- `SNIPE_INTERVAL_SECONDS`: `29`
- `ROOTER_AUTH_TOKEN`: Your primary Rooter Bearer token
