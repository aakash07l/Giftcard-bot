# 🎮 PlayStation Gift Card Auto-Buyer Bot (Rooter Shop) — Multi-Account & Railway Ready

An ultra-fast automated Python Telegram bot built using **`python-telegram-bot`**, **`Playwright`**, **`asyncio`**, and **`aiohttp`** that snipes, selects, and buys PlayStation Gift Cards / Wallet Vouchers directly from **Rooter Shop** concurrently across 5-10 accounts using Rooter wallet balances.

---

## 🌟 Key Features

1. **🎮 PlayStation Gift Cards Exclusive**:
   - Focuses strictly on PlayStation Wallet Vouchers (₹1,000, ₹2,000, ₹3,000, ₹4,000, ₹5,000).
   - All legacy Play Store endpoints, loops, and test codes are completely purged.

2. **👥 High-Concurrency Multi-Account Engine (5–10 Accounts)**:
   - Supports 5 to 10 accounts simultaneously.
   - Built with **`asyncio`** and **`aiohttp`** connection pooling.
   - When restock drops, purchase requests fire concurrently across all active accounts with zero delay.
   - Smart balance-aware allocation: automatically buys the highest affordable voucher denomination per account.

3. **☁️ Railway-Compatible Dual Auth & Session Management**:
   - Compatible with Railway ephemeral containers.
   - Dynamically add/update tokens without container restarts via:
     - `/settoken <token>` (Updates Primary / Account 1)
     - `/settoken <acc_id_or_index> <token>` (e.g. `/settoken 2 eyJ...`)
     - `/login` (Interactive Bearer token / Session paste)
   - Pre-flight token validation (`is_token_valid()`) checks JWT claims and calls Rooter's live wallet API before firing requests.

4. **🧪 Admin Safe Verification: `/snipe amazon 1`**:
   - Restricted to authorized `ADMIN_CHAT_ID`.
   - Command: `/snipe amazon 1`
   - Purchases a single **₹10 Amazon Pay Gift Card** (costs ~₹9.92 with Rooter discount).
   - Allows safe verification of account tokens, multi-account setup, execution latency, and session health without risking high-value PlayStation stock.

---

## ⚡ Telegram Commands

| Command | Description |
|---|---|
| `/start` | Welcome dashboard, live wallet balances & main menu |
| `/accounts` | 👥 View and manage 5-10 Rooter accounts with live balance sync |
| `/settoken <token>` | 🔑 Dynamically update account Bearer tokens at runtime |
| `/addaccount <token> [label]` | Add a new account to the multi-account manager |
| `/snipe` | 🎯 Start 24/7 Auto-Sniper (Select specific card or "Any PlayStation") |
| `/snipe amazon 1` | 🧪 **[Admin Only]** Test buy ₹10 Amazon Pay card to verify token & speed |
| `/stop` | 🛑 Stop active 24/7 restock monitoring |
| `/buy` | Manual instant single purchase flow for PlayStation vouchers |
| `/status` | View session status, active sniper state, and accounts summary |
| `/toggle_sim` | Toggle between Simulation Mode (safe dry run) and Live Mode |
| `/cancel` | Cancel any ongoing operation |

---

## 🚀 Railway Deployment Guide

### Required Environment Variables

Set these in your **Railway Project Settings > Variables**:

```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_CHAT_ID=your_telegram_chat_id_here
ROOTER_AUTH_TOKEN=your_primary_rooter_jwt_bearer_token_here
SIMULATION_MODE=False
SNIPE_INTERVAL_SECONDS=20
HEADLESS=true
ENV=production
```

### Optional Multi-Account Variables:
- `ROOTER_TOKENS`: Comma-separated JWT tokens (`token1,token2,token3`)
- `ROOTER_ACCOUNTS_JSON`: JSON array with account objects (`[{"id": "acc_1", "token": "..."}]`)

---

## 📂 Project Structure

```
ps_giftcard_bot/
├── config.py                  # App configuration & environment loader
├── main.py                    # Telegram bot initialization & handlers registration
├── requirements.txt           # Python dependencies (aiohttp, playwright, python-telegram-bot)
├── Dockerfile                 # Railway-ready container build
├── Procfile                   # Process entrypoint
├── railway.json               # Railway deployment configuration
├── bot/
│   ├── states.py              # Conversation state definitions
│   ├── keyboards.py           # Clean PlayStation inline keyboards
│   └── handlers.py            # Command handlers, /snipe amazon 1, /settoken & multi-account sniper
└── services/
    ├── base_platform.py       # Data structures & BasePlatform class
    ├── browser_manager.py     # Playwright lifecycle, context isolation & anti-detection
    ├── account_manager.py     # In-memory dynamic multi-account manager with aiohttp sync
    └── rooter_service.py      # PlayStation sniper & Amazon Pay ₹10 test purchase automation
```
