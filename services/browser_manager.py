"""
Browser lifecycle manager for Playwright.
Handles headless Chromium instances, session storage_state, anti-detect headers, and screenshot capture.
"""

import os
import json
import logging
import urllib.parse
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

import config

logger = logging.getLogger(__name__)

def extract_user_id_from_jwt(token: str) -> int:
    """Safely extracts Rooter userId from JWT payload."""
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            padding = "=" * (-len(parts[1]) % 4)
            payload_str = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
            data = json.loads(payload_str)
            return int(data.get("userId", 2104663773))
    except Exception:
        pass
    return 2104663773

# Modern Chrome User Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

class BrowserManager:
    """Manages Playwright browser instances and user sessions."""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def initialize(self):
        """Starts Playwright and launches Chromium."""
        if not self._playwright:
            self._playwright = await async_playwright().start()
        if not self._browser or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(
                headless=config.HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--mute-audio",
                    "--no-first-run",
                ],
            )
            logger.info("Chromium browser launched successfully.")

    def get_session_file(self, user_id: int, platform: str) -> Path:
        """Returns the storage_state file path for a given user and platform."""
        return config.SESSION_DIR / f"user_{user_id}_{platform}.json"

    def get_active_token(self, user_id: Optional[int] = None) -> Optional[str]:
        """Returns active Bearer token from config, user session, or any stored session file."""
        if config.ROOTER_AUTH_TOKEN and len(config.ROOTER_AUTH_TOKEN) > 10:
            return config.ROOTER_AUTH_TOKEN

        # Check user-specific session file
        if user_id:
            s_file = self.get_session_file(user_id, "rooter")
            if s_file.exists():
                try:
                    with open(s_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for c in data.get("cookies", []):
                            if c.get("name") in ("token", "user_auth", "authToken", "rooter_token"):
                                val = c.get("value")
                                if val and len(val) > 10:
                                    return val
                        for origin in data.get("origins", []):
                            for item in origin.get("localStorage", []):
                                if item.get("name") in ("token", "user_auth", "authToken", "rooter_token", "auth_token"):
                                    val = item.get("value")
                                    if val and len(val) > 10:
                                        return val
                except Exception:
                    pass

        # Check any available session files
        for sf in config.SESSION_DIR.glob("user_*_rooter.json"):
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for c in data.get("cookies", []):
                        if c.get("name") in ("token", "user_auth", "authToken", "rooter_token"):
                            val = c.get("value")
                            if val and len(val) > 10:
                                return val
            except Exception:
                pass
        return None

    def has_session(self, user_id: int, platform: str) -> bool:
        """Checks if a user session file exists or if active AUTH_TOKEN is present."""
        return self.get_active_token(user_id) is not None

    async def create_context(
        self,
        user_id: Optional[int] = None,
        platform: Optional[str] = "rooter",
        apply_storage_state: bool = True,
        custom_token: Optional[str] = None,
    ) -> BrowserContext:
        """Creates an authenticated or fresh BrowserContext."""
        await self.initialize()

        active_token = custom_token or self.get_active_token(user_id)

        storage_path = None
        if apply_storage_state and user_id:
            s_file = self.get_session_file(user_id, "rooter")
            if s_file.exists():
                storage_path = str(s_file)

        context = await self._browser.new_context(
            storage_state=storage_path,
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            permissions=["geolocation"],
            geolocation={"latitude": 28.6304, "longitude": 77.2177},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )

        # Block media resources (images, fonts, videos) to drastically save RAM, CPU, and Railway bandwidth
        if config.BLOCK_MEDIA_RESOURCES:
            try:
                await context.route(
                    "**/*.{png,jpg,jpeg,webp,gif,svg,woff,woff2,ttf,eot,mp4,webm,avi,mp3}",
                    lambda route: route.abort()
                )
            except Exception:
                pass

        # Anti-detection stealth script & LocalStorage injection for Auth Tokens
        init_script = """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {}
            };
            // Auto-dismiss 'Different Location Detected' modal immediately whenever it appears
            try {
                setInterval(() => {
                    const btns = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
                    for (const b of btns) {
                        const txt = (b.innerText || '').toLowerCase().trim();
                        if (txt.includes('stay on this site') || txt.includes('no, stay')) {
                            b.click();
                            break;
                        }
                    }
                }, 200);
            } catch (e) {}
        """
        if active_token:
            uid = extract_user_id_from_jwt(active_token)
            auth_obj = {
                "accessToken": active_token,
                "refreshToken": active_token,
                "userId": uid,
                "country": "IN",
                "deviceId": "web-browser",
                "deviceType": "web",
                "appVersion": "1.0.0"
            }
            auth_str = json.dumps(auth_obj).replace("'", "\\'")
            init_script += f"""
                try {{
                    localStorage.setItem('user_auth', '{auth_str}');
                    localStorage.setItem('rooter_token', '{active_token}');
                    localStorage.setItem('token', '{active_token}');
                    localStorage.setItem('authToken', '{active_token}');
                    localStorage.setItem('auth_token', '{active_token}');
                }} catch (e) {{}}
            """

        await context.add_init_script(init_script)

        # Inject auth cookies for Rooter so backend API and wallet recognize authenticated session
        if platform == "rooter" and active_token:
            try:
                uid = extract_user_id_from_jwt(active_token)
                auth_data = {
                    "accessToken": active_token,
                    "refreshToken": active_token,
                    "userId": uid,
                    "country": "IN",
                    "deviceId": "web-browser",
                    "deviceType": "web",
                    "appVersion": "1.0.0"
                }
                encoded_auth = urllib.parse.quote(json.dumps(auth_data))
                await context.add_cookies([
                    {"name": "user_auth", "value": encoded_auth, "domain": ".rooter.gg", "path": "/"},
                    {"name": "token", "value": active_token, "domain": ".rooter.gg", "path": "/"},
                    {"name": "authToken", "value": active_token, "domain": ".rooter.gg", "path": "/"},
                    {"name": "rooter_token", "value": active_token, "domain": ".rooter.gg", "path": "/"},
                ])
            except Exception as e:
                logger.warning(f"Failed to inject Rooter cookies: {e}")

        return context

    async def save_session(self, context: BrowserContext, user_id: int, platform: str):
        """Saves current cookies and localStorage to session file."""
        session_file = self.get_session_file(user_id, platform)
        await context.storage_state(path=str(session_file))
        logger.info(f"Saved session state for user {user_id} on {platform} -> {session_file}")

    def import_session_json(self, user_id: int, platform: str, raw_data: str) -> bool:
        """Imports user cookies, storage state, or raw Bearer token."""
        raw_data = raw_data.strip()
        session_file = self.get_session_file(user_id, platform)
        domain_origin = "https://shop.rooter.gg"

        # Check if raw_data is a plain token string (e.g. Bearer eyJ... or eyJ...)
        clean_token = raw_data
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        # If it's a raw string (not JSON dict or list), treat directly as auth token
        if not (clean_token.startswith("{") or clean_token.startswith("[")):
            if len(clean_token) > 10:
                origins = [
                    {
                        "origin": "https://shop.rooter.gg",
                        "localStorage": [
                            {"name": "token", "value": clean_token},
                            {"name": "auth_token", "value": clean_token},
                            {"name": "rooter_token", "value": clean_token},
                            {"name": "authToken", "value": clean_token},
                            {"name": "user_auth", "value": clean_token},
                        ]
                    },
                    {
                        "origin": "https://rooter.gg",
                        "localStorage": [
                            {"name": "token", "value": clean_token},
                            {"name": "auth_token", "value": clean_token},
                            {"name": "rooter_token", "value": clean_token},
                            {"name": "authToken", "value": clean_token},
                            {"name": "user_auth", "value": clean_token},
                        ]
                    }
                ]

                cookies = [
                    {"name": "user_auth", "value": clean_token, "domain": ".rooter.gg", "path": "/"},
                    {"name": "token", "value": clean_token, "domain": ".rooter.gg", "path": "/"},
                    {"name": "authToken", "value": clean_token, "domain": ".rooter.gg", "path": "/"},
                    {"name": "rooter_token", "value": clean_token, "domain": ".rooter.gg", "path": "/"},
                    {"name": "user_auth", "value": clean_token, "domain": "shop.rooter.gg", "path": "/"},
                    {"name": "token", "value": clean_token, "domain": "shop.rooter.gg", "path": "/"},
                    {"name": "authToken", "value": clean_token, "domain": "shop.rooter.gg", "path": "/"},
                ]

                payload = {
                    "cookies": cookies,
                    "origins": origins
                }
                with open(session_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)

                # Update in-memory config so all active workers immediately use it!
                config.ROOTER_AUTH_TOKEN = clean_token
                logger.info(f"Saved raw Bearer token for user {user_id} on {platform} and updated ROOTER_AUTH_TOKEN")
                return True
            return False

        try:
            parsed = json.loads(clean_token)
            if isinstance(parsed, list):
                payload = {"cookies": parsed, "origins": []}
            elif isinstance(parsed, dict):
                payload = parsed
            else:
                return False

            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to import session data: {e}")
            return False

    async def capture_screenshot(self, page: Page, name_prefix: str = "shot") -> str:
        """Captures page screenshot and returns absolute path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name_prefix}_{timestamp}.png"
        filepath = config.SCREENSHOT_DIR / filename
        try:
            await page.screenshot(path=str(filepath), full_page=False)
            return str(filepath)
        except Exception as e:
            logger.warning(f"Could not take screenshot: {e}")
            return ""

    async def close(self):
        """Clean shutdown of browser and playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None

# Global singleton instance
browser_manager = BrowserManager()
