# 🎮 PlayStation Gift Card Telegram Bot (Rooter Shop)

An automated Python Telegram bot built using **`python-telegram-bot`** and **`Playwright`** that snipes, selects, and buys PlayStation Gift Cards / Wallet Vouchers directly from **Rooter Shop** using your Rooter wallet balance.

---

## 🌟 Key Features

1. **Telegram Command Dashboard**:
   - `/start`: Welcome dashboard with live connection status and interactive menu.
   - `/snipe`: 🎯 **24/7 Restock Auto-Sniper** (Directly monitors PlayStation product page every 30s and auto-buys instantly upon restock).
   - `/stop`: 🛑 Stop active 24/7 restock monitoring.
   - `/buy`: Trigger instant single purchase flow.
   - `/login`: Store account Bearer Token or log in via Phone + OTP.
   - `/status`: Check session token status, active sniper state, and execution mode.
   - `/toggle_sim`: Instantly switch between **🧪 Simulation Mode (Safe Dry Run)** and **⚡ Live Purchasing**.
   - `/cancel`: Cancel any ongoing conversational prompt.

2. **Headless Browser Automation (Playwright)**:
   - Direct navigation to Rooter PlayStation product page (`https://shop.rooter.gg/product/playstation-gift-cards`).
   - Per-denomination stock check (₹1000, ₹2000, ₹3000, ₹4000, ₹5000).
   - Fast 1-click buy with Rooter Wallet balance.
   - Persistent session storage and cookie injection (`token`, `authToken`).
   - Automated voucher code/PIN extraction from confirmation receipt.

---

## 📂 Project Structure

```
ps_giftcard_bot/
├── .env                       # Bot token and environment configuration
├── .env.example               # Example template for environment variables
├── requirements.txt           # Python package dependencies
├── Procfile                   # Worker definition for Railway / Heroku
├── Dockerfile                 # Container image for Railway / VPS
├── railway.json               # Railway deployment configuration
├── config.py                  # Environment config and platform metadata
├── main.py                    # Application entry point and Telegram polling
├── bot/
│   ├── __init__.py
│   ├── states.py              # ConversationHandler states
│   ├── keyboards.py           # Inline keyboards (menus, denominations)
│   └── handlers.py            # Commands and callback logic
├── services/
│   ├── __init__.py
│   ├── base_platform.py       # Base platform interface and data models
│   ├── browser_manager.py     # Playwright lifecycle & session manager
│   └── rooter_service.py      # Rooter gaming shop scraper & buyer
└── sessions/                  # Stored authenticated cookies per user
```

---

## 🚀 Quick Start & Railway Deployment

### Railway Environment Variables
- `BOT_TOKEN`: Your Telegram Bot Token
- `SIMULATION_MODE`: `False` (for live purchases with wallet balance)
- `ROOTER_AUTH_TOKEN`: Your Rooter Bearer token
- `HEADLESS`: `true`
- `ENV`: `production`
- `SNIPE_INTERVAL_SECONDS`: `30`
- `ENABLE_SNIPER_HEARTBEAT`: `False`
- `BLOCK_MEDIA_RESOURCES`: `True`

