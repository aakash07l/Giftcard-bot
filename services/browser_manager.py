"""
Browser lifecycle manager for Playwright.
Handles headless Chromium instances, session storage_state, anti-detect headers, and screenshot capture.
"""

import os
import json
import logging
import re
import urllib.parse
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

import config

logger = logging.getLogger(__name__)

def extract_jwt_token(val: Any) -> Optional[str]:
    """Safely extracts a valid JWT access token from raw strings, JSON dicts, or URL-encoded cookies."""
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if val.lower().startswith("bearer "):
        val = val[7:].strip()
    # Check if raw JWT string
    if val.startswith("eyJ") and len(val) > 20 and val.count(".") >= 2:
        return val
    # Check if URL-encoded
    if "%7B" in val or "%22" in val:
        try:
            val = urllib.parse.unquote(val)
        except Exception:
            pass
    # Check if JSON string
    if val.startswith("{") and ("accessToken" in val or "token" in val):
        try:
            parsed = json.loads(val)
            tok = parsed.get("accessToken") or parsed.get("token") or parsed.get("authToken")
            if tok and isinstance(tok, str) and tok.startswith("eyJ"):
                return tok.strip()
        except Exception:
            pass
    # Regex search for JWT pattern
    jwt_match = re.search(r"\b(eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+)\b", val)
    if jwt_match:
        return jwt_match.group(1)
    return None

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
        if config.ROOTER_AUTH_TOKEN:
            tok = extract_jwt_token(config.ROOTER_AUTH_TOKEN)
            if tok:
                return tok

        # Check user-specific session file
        if user_id:
            s_file = self.get_session_file(user_id, "rooter")
            if s_file.exists():
                try:
                    with open(s_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for c in data.get("cookies", []):
                            tok = extract_jwt_token(c.get("value"))
                            if tok:
                                return tok
                        for origin in data.get("origins", []):
                            for item in origin.get("localStorage", []):
                                tok = extract_jwt_token(item.get("value"))
                                if tok:
                                    return tok
                except Exception:
                    pass

        # Check AccountManager active accounts
        try:
            from services.account_manager import account_manager
            active_accs = account_manager.get_active()
            if active_accs:
                for a in active_accs:
                    tok = extract_jwt_token(a.get("token"))
                    if tok:
                        return tok
        except Exception:
            pass

        # Check any available session files
        for sf in config.SESSION_DIR.glob("user_*_rooter.json"):
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for c in data.get("cookies", []):
                        tok = extract_jwt_token(c.get("value"))
                        if tok:
                            return tok
                    for origin in data.get("origins", []):
                        for item in origin.get("localStorage", []):
                            tok = extract_jwt_token(item.get("value"))
                            if tok:
                                return tok
            except Exception:
                pass
        return None

    def has_session(self, user_id: int, platform: str) -> bool:
        """Checks if a user session file exists or if active AUTH_TOKEN / AccountManager account is present."""
        if self.get_active_token(user_id) is not None:
            return True
        try:
            from services.account_manager import account_manager
            return len(account_manager.get_active()) > 0
        except Exception:
            return False

    async def create_context(
        self,
        user_id: Optional[int] = None,
        platform: Optional[str] = "rooter",
        apply_storage_state: bool = True,
        custom_token: Optional[str] = None,
    ) -> BrowserContext:
        """Creates an authenticated or fresh BrowserContext."""
        await self.initialize()

        raw_active_token = custom_token or self.get_active_token(user_id)
        active_token = extract_jwt_token(raw_active_token)

        storage_path = None
        if apply_storage_state and user_id:
            s_file = self.get_session_file(user_id, "rooter")
            if s_file.exists():
                try:
                    # Sanitize legacy session file: if it has corrupted URL-encoded cookies, delete it
                    raw_content = s_file.read_text(encoding="utf-8")
                    if "%7B%22" in raw_content or "%22accessToken%22" in raw_content:
                        logger.warning(f"Purging legacy URL-encoded session file: {s_file}")
                        s_file.unlink(missing_ok=True)
                    else:
                        storage_path = str(s_file)
                except Exception:
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

        # Block heavy media resources (images, videos) to save RAM, CPU, and bandwidth
        # Keep SVGs and fonts unblocked so Next.js / Mantine UI renders without client-side exceptions
        if config.BLOCK_MEDIA_RESOURCES:
            try:
                await context.route(
                    "**/*.{png,jpg,jpeg,webp,gif,mp4,webm,avi,mp3}",
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
            raw_auth_json = json.dumps(auth_obj)
            escaped_json = raw_auth_json.replace("\\", "\\\\").replace("'", "\\'")
            init_script += f"""
                try {{
                    localStorage.setItem('user_auth', '{escaped_json}');
                    localStorage.setItem('rooter_token', '{active_token}');
                    localStorage.setItem('token', '{active_token}');
                    localStorage.setItem('authToken', '{active_token}');
                    localStorage.setItem('auth_token', '{active_token}');
                    document.cookie = "user_auth=" + encodeURIComponent('{escaped_json}') + "; path=/; domain=.rooter.gg";
                    document.cookie = "token={active_token}; path=/; domain=.rooter.gg";
                }} catch (e) {{}}
            """

        await context.add_init_script(init_script)

        # Inject clean alphanumeric auth cookies for Rooter HTTP requests (avoids CloudFront WAF 403 on illegal JSON headers)
        if platform == "rooter" and active_token:
            try:
                await context.clear_cookies()
                await context.add_cookies([
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

        # Check if raw_data is a plain token string (e.g. Bearer eyJ... or eyJ...)
        jwt_token = extract_jwt_token(raw_data)
        if jwt_token:
            uid = extract_user_id_from_jwt(jwt_token)
            auth_data = {
                "accessToken": jwt_token,
                "refreshToken": jwt_token,
                "userId": uid,
                "country": "IN",
                "deviceId": "web-browser",
                "deviceType": "web",
                "appVersion": "1.0.0"
            }
            raw_user_auth = json.dumps(auth_data)
            origins = [
                {
                    "origin": "https://shop.rooter.gg",
                    "localStorage": [
                        {"name": "token", "value": jwt_token},
                        {"name": "auth_token", "value": jwt_token},
                        {"name": "rooter_token", "value": jwt_token},
                        {"name": "authToken", "value": jwt_token},
                        {"name": "user_auth", "value": raw_user_auth},
                    ]
                },
                {
                    "origin": "https://rooter.gg",
                    "localStorage": [
                        {"name": "token", "value": jwt_token},
                        {"name": "auth_token", "value": jwt_token},
                        {"name": "rooter_token", "value": jwt_token},
                        {"name": "authToken", "value": jwt_token},
                        {"name": "user_auth", "value": raw_user_auth},
                    ]
                }
            ]

            cookies = [
                {"name": "user_auth", "value": raw_user_auth, "domain": ".rooter.gg", "path": "/"},
                {"name": "user_auth", "value": raw_user_auth, "domain": "shop.rooter.gg", "path": "/"},
                {"name": "token", "value": jwt_token, "domain": ".rooter.gg", "path": "/"},
                {"name": "token", "value": jwt_token, "domain": "shop.rooter.gg", "path": "/"},
                {"name": "authToken", "value": jwt_token, "domain": ".rooter.gg", "path": "/"},
                {"name": "rooter_token", "value": jwt_token, "domain": ".rooter.gg", "path": "/"},
            ]

            payload = {
                "cookies": cookies,
                "origins": origins
            }
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            # Update in-memory config so all active workers immediately use it!
            config.ROOTER_AUTH_TOKEN = jwt_token
            logger.info(f"Saved clean JWT session for user {user_id} on {platform} and updated ROOTER_AUTH_TOKEN")
            return True

        try:
            parsed = json.loads(raw_data)
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
