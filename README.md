# 🎮 PlayStation Gift Card Telegram Bot

An automated Python Telegram bot built using **`python-telegram-bot`** and **`Playwright`** that searches, selects, and buys PlayStation Gift Cards / Wallet Vouchers from platforms like **Blinkit** and **Rooter Shop**.

---

## 🌟 Key Features

1. **Telegram Command Dashboard**:
   - `/start`: Welcome dashboard with live platform connection statuses and interactive inline keyboard.
   - `/buy`: Trigger the step-by-step automated voucher buying flow.
   - `/login`: Securely store user account sessions via **Interactive Phone + OTP** or **Cookie / Session JSON import**.
   - `/status`: Check login states, session cookie status, and current execution mode.
   - `/toggle_sim`: Instantly switch between **🧪 Simulation Mode (Safe Dry Run)** and **⚡ Live Purchasing**.
   - `/cancel`: Cancel any ongoing conversational prompt.

2. **Headless Browser Automation (Playwright)**:
   - Automated navigation to **Blinkit** (`https://blinkit.com`) and **Rooter Shop** (`https://rooter.gg/shop`).
   - Dark-store pincode and location configuration for Blinkit.
   - Automatic query typing: `"PlayStation Gift Card"` or `"PlayStation Wallet"`.
   - Real-time stock status verification (In-Stock vs Out-of-Stock).
   - Automated denomination matching: ₹500, ₹1000, ₹1500, ₹2500, ₹4000, ₹5000.
   - Persistent session storage using Playwright's `storage_state` (`sessions/user_{id}_{platform}.json`).
   - Automated checkout and voucher code/PIN extraction from confirmation receipt.

3. **Live Telegram Progress Notifications**:
   - Status messages update dynamically via `edit_text`:
     - 🔍 *Navigating to Blinkit / Rooter...*
     - 🔎 *Searching for PlayStation Gift Cards...*
     - 🛒 *Adding voucher to cart & proceeding to checkout...*
     - 💳 *Completing purchase & verifying payment...*
     - 🎉 *PURCHASE SUCCESSFUL! \nCode: PLAYSTATION_CODE_HERE \nPIN: 1234*

4. **Edge Cases & Error Handling**:
   - **Out-of-Stock Handling**: If PlayStation cards are out of stock on one platform (e.g. Blinkit dark-stores), the bot automatically offers a 1-tap fallback button to check Rooter Shop.
   - **Visual Verification**: If checkout encounters an issue, Playwright captures a screenshot and sends it directly to your Telegram chat.
   - **Safe Simulation Mode**: Comes with `SIMULATION_MODE=True` enabled by default so you can test end-to-end flows safely without debiting real bank funds.

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
├── replit.nix                 # Nix packages for Replit deployment
├── start_bot.bat              # One-click Windows runner
├── config.py                  # Environment config and platform metadata
├── main.py                    # Application entry point and Telegram polling
├── bot/
│   ├── __init__.py
│   ├── states.py              # ConversationHandler states
│   ├── keyboards.py           # Inline keyboards (menus, platforms, denominations)
│   └── handlers.py            # Commands and callback logic
├── services/
│   ├── __init__.py
│   ├── base_platform.py       # Base platform interface and data models
│   ├── browser_manager.py     # Playwright lifecycle & session manager
│   ├── blinkit_service.py     # Blinkit dark-store scraper & buyer
│   └── rooter_service.py      # Rooter gaming shop scraper & buyer
└── sessions/                  # Stored authenticated cookies per user
```

---

## 🚀 Quick Start (Local Setup)

### 1. Configure `.env`
Edit the `.env` file in the project root:
```env
# 1. Telegram Credentials
BOT_TOKEN=8975433711:AAFk_OxMHcTR67JyXsbLwI1l4Ougm69z82I

# 2. Execution Mode
SIMULATION_MODE=True

# 3. Rooter Account Credentials / Auth Details
ROOTER_MOBILE=9876543210
ROOTER_AUTH_TOKEN=your_rooter_bearer_token_here

# 4. Blinkit Account Credentials / Auth Details
BLINKIT_MOBILE=9876543210
BLINKIT_AUTH_TOKEN=your_blinkit_token_here

# 5. Application Settings
HEADLESS=true
ENV=production
DEFAULT_PINCODE=110001
```

### 2. Run the Bot
On Windows, simply double-click **`start_bot.bat`** or run:
```bash
python main.py
```

---

## ☁️ Cloud Deployment

### Deploying to Railway
1. Push this repository to GitHub or connect via Railway CLI.
2. In Railway dashboard, click **New Project** -> **Deploy from GitHub Repo**.
3. Railway will detect the `Dockerfile` and `railway.json`.
4. In Railway **Variables**, add the following environment variables:
   - `BOT_TOKEN`: `8975433711:AAFk_OxMHcTR67JyXsbLwI1l4Ougm69z82I`
   - `SIMULATION_MODE`: `True` (Testing) or `False` (Live purchases)
   - `HEADLESS`: `true`
   - `ENV`: `production`
   - `ROOTER_MOBILE`: (Optional) Your 10-digit mobile number for Rooter
   - `ROOTER_AUTH_TOKEN`: (Optional) Your Rooter Bearer token
   - `BLINKIT_MOBILE`: (Optional) Your 10-digit mobile number for Blinkit
   - `BLINKIT_AUTH_TOKEN`: (Optional) Your Blinkit session/auth token
   - `DEFAULT_PINCODE`: `110001` (Or your preferred delivery pincode)
5. Railway will automatically build the container with Chromium and launch the bot worker.

### Deploying to Replit
1. Create a new Python Repl and import this repository.
2. The included `replit.nix` contains all system libraries needed for Chromium headless execution.
3. In Replit Secrets (Environment Variables), set:
   - `BOT_TOKEN`: `8975433711:AAFk_OxMHcTR67JyXsbLwI1l4Ougm69z82I`
4. Set the Run command to `python main.py`.

---

## 🔐 How Platform Authentication Works

You can log into **Blinkit** or **Rooter** using two methods:

### Method 1: Interactive Phone + OTP
1. Send `/login` in Telegram and choose **Phone + OTP**.
2. Enter your 10-digit mobile number.
3. The bot launches a headless browser, inputs your phone number, and triggers an OTP.
4. Reply to the bot with the OTP you receive on your phone.
5. The bot submits the OTP and saves the session cookies to `sessions/user_{id}_{platform}.json`.

### Method 2: Cookie / Session JSON Import
1. In your desktop browser (Chrome/Edge/Brave), log into `blinkit.com` or `rooter.gg`.
2. Use an extension like *Cookie-Editor* or *EditThisCookie* to export cookies as JSON.
3. Send `/login` in Telegram and select **Paste Cookie / Session JSON**.
4. Paste the JSON into the chat. The bot stores the authenticated state for all future purchases.
