"""
Interactive Local Rooter Login Helper
Runs locally on Indian IP to guarantee SMS OTP delivery by Indian telecom gateways.
Extracts the clean JWT Bearer Token and auto-saves it for the bot.
"""
import asyncio
import os
import re
import sys
import json
import subprocess
from playwright.async_api import async_playwright

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")


def copy_to_clipboard(text: str):
    """Copies text directly to Windows clipboard using clip.exe."""
    try:
        subprocess.run(["clip"], input=text.strip().encode("utf-8"), check=False)
        return True
    except Exception:
        return False


def save_token_to_env(token: str):
    """Updates ROOTER_AUTH_TOKEN in .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "ROOTER_AUTH_TOKEN=" in content:
            new_content = re.sub(r"ROOTER_AUTH_TOKEN=.*", f"ROOTER_AUTH_TOKEN={token}", content)
        else:
            new_content = content + f"\nROOTER_AUTH_TOKEN={token}\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("[OK] Updated ROOTER_AUTH_TOKEN in .env")
    except Exception as e:
        print(f"[!] Note: Could not auto-update .env: {e}")


def save_token_to_accounts(token: str, phone: str):
    """Updates primary account token in sessions/accounts.json."""
    accounts_path = os.path.join(os.path.dirname(__file__), "sessions", "accounts.json")
    if not os.path.exists(accounts_path):
        return
    try:
        with open(accounts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        accounts = data.get("accounts", [])
        if accounts:
            accounts[0]["token"] = token
            accounts[0]["label"] = f"Account 1 (+91 {phone})"
        with open(accounts_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[OK] Updated token in sessions/accounts.json")
    except Exception as e:
        print(f"[!] Note: Could not auto-update accounts.json: {e}")


async def main():
    print("=" * 60)
    print("  ROOTER 1-CLICK LOCAL LOGIN HELPER (INDIAN IP)")
    print("=" * 60)

    default_phone = "9179326103"
    prompt = f"\nEnter your 10-digit Rooter Mobile Number [default: {default_phone}]: "
    user_input = input(prompt).strip()
    phone_to_use = user_input if user_input else default_phone
    clean_phone = re.sub(r"\D", "", phone_to_use)[-10:]

    if len(clean_phone) != 10:
        print("[ERROR] Invalid phone number. Please enter a valid 10-digit number.")
        return

    print(f"\n[1/4] Launching browser to request OTP for +91 {clean_phone}...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()

        # Listen for OTP API status
        page.on(
            "response",
            lambda r: print(f"      [Network] {r.status} {r.url.split('?')[0]}")
            if "otp" in r.url or "auth" in r.url
            else None,
        )

        print("      Loading shop.rooter.gg...")
        await page.goto("https://shop.rooter.gg", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Clear old auth
        await page.evaluate("""() => {
            try {
                localStorage.removeItem('token');
                localStorage.removeItem('user_auth');
                localStorage.removeItem('rooter_token');
            } catch(e) {}
        }""")

        # Open profile drawer
        phone_input = page.locator("input[placeholder*='Mobile Number']").first
        if not await phone_input.is_visible():
            avatar = page.locator("div[class*='headerIconWrappers'], img[alt='profile-avatar-icon']").first
            await avatar.click(force=True)
            await page.wait_for_timeout(1000)

        await phone_input.wait_for(state="visible", timeout=12000)
        await phone_input.fill(clean_phone)
        await page.wait_for_timeout(300)

        # Click Continue
        cont_btn = page.locator("button:has-text('Continue'), button[type='submit']").first
        await cont_btn.click(force=True)

        # Wait for OTP input
        otp_input = page.locator("input[data-path='step2.otp'], input.mantine-NumberInput-input, button:has-text('Verify Now')").first
        await otp_input.wait_for(state="visible", timeout=15000)

        print("\n" + "=" * 60)
        print(f"[2/4] OTP HAS BEEN SENT TO YOUR MOBILE (+91 {clean_phone})!")
        print("      Please check the SMS on your phone.")
        print("=" * 60)

        otp_code = input("\nEnter the 6-digit OTP received on your phone: ").strip()
        clean_otp = re.sub(r"\D", "", otp_code)

        if not clean_otp:
            print("[ERROR] No OTP entered. Aborting.")
            await browser.close()
            return

        print(f"\n[3/4] Verifying OTP {clean_otp} on Rooter...")
        real_otp_input = page.locator("input[data-path='step2.otp'], input.mantine-NumberInput-input, input[inputmode='numeric']").first
        await real_otp_input.wait_for(state="visible", timeout=5000)
        await real_otp_input.fill(clean_otp)
        await page.wait_for_timeout(300)

        verify_btn = page.locator("button.styles_verifyOtpBtn__DkYRE, button:has-text('Verify Now'), button:has-text('Verify')").first
        await verify_btn.click(force=True)

        # Extract token
        print("\n[4/4] Retrieving clean JWT Bearer Token...")
        extracted_token = None
        for _ in range(25):
            await page.wait_for_timeout(500)
            extracted_token = await page.evaluate("""() => {
                const tok = localStorage.getItem('token') || localStorage.getItem('rooter_token');
                if (tok && tok.length > 20) return tok;
                try {
                    const auth = JSON.parse(localStorage.getItem('user_auth') || '{}');
                    if (auth.accessToken && auth.accessToken.length > 20) return auth.accessToken;
                } catch (e) {}
                return null;
            }""")
            if extracted_token:
                break

        if extracted_token:
            save_token_to_env(extracted_token)
            save_token_to_accounts(extracted_token, clean_phone)
            copied = copy_to_clipboard(extracted_token)

            print("\n" + "=" * 60)
            print("  [SUCCESS] LOGIN COMPLETE! CLEAN TOKEN RETRIEVED!")
            print("=" * 60)
            if copied:
                print(">> [COPIED] Token has been AUTOMATICALLY copied to your clipboard!")
                print("            You can just press Ctrl+V to paste it anywhere.")
            print("\nBearer Token:")
            print("-" * 60)
            print(extracted_token)
            print("-" * 60)
            print("\nHow to use:")
            print("1. Telegram Bot: Send /login -> Paste Bearer Token -> Paste it!")
            print("2. Railway: Add/Update ROOTER_AUTH_TOKEN in Variables")
            print("=" * 60)
        else:
            print("\n[ERROR] Could not retrieve token. Please check OTP and try again.")

        await page.wait_for_timeout(2000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
