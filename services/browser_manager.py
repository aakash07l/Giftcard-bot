"""
Browser lifecycle manager for Playwright.
Handles headless Chromium instances, session storage_state, anti-detect headers, and screenshot capture.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

import config

logger = logging.getLogger(__name__)

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
                ],
            )
            logger.info("Chromium browser launched successfully.")

    def get_session_file(self, user_id: int, platform: str) -> Path:
        """Returns the storage_state file path for a given user and platform."""
        return config.SESSION_DIR / f"user_{user_id}_{platform}.json"

    def has_session(self, user_id: int, platform: str) -> bool:
        """Checks if a user session file exists or if static AUTH_TOKEN is set in config."""
        if platform == "blinkit" and config.BLINKIT_AUTH_TOKEN:
            return True
        if platform == "rooter" and config.ROOTER_AUTH_TOKEN:
            return True

        session_file = self.get_session_file(user_id, platform)
        if not session_file.exists():
            return False
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("cookies") or data.get("origins"))
        except Exception:
            return False

    async def create_context(
        self,
        user_id: Optional[int] = None,
        platform: Optional[str] = None,
        apply_storage_state: bool = True,
    ) -> BrowserContext:
        """Creates an authenticated or fresh BrowserContext."""
        await self.initialize()

        storage_path = None
        if apply_storage_state and user_id and platform:
            s_file = self.get_session_file(user_id, platform)
            if s_file.exists():
                storage_path = str(s_file)

        extra_http_headers = {}
        if platform == "blinkit" and config.BLINKIT_AUTH_TOKEN:
            extra_http_headers["authorization"] = f"Bearer {config.BLINKIT_AUTH_TOKEN}"
        elif platform == "rooter" and config.ROOTER_AUTH_TOKEN:
            extra_http_headers["authorization"] = f"Bearer {config.ROOTER_AUTH_TOKEN}"

        context = await self._browser.new_context(
            storage_state=storage_path,
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            permissions=["geolocation"],
            geolocation={"latitude": config.DEFAULT_LATITUDE, "longitude": config.DEFAULT_LONGITUDE},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers=extra_http_headers if extra_http_headers else None,
        )

        # Anti-detection stealth script & LocalStorage injection for Auth Tokens
        init_script = """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {}
            };
        """
        if platform == "blinkit" and config.BLINKIT_AUTH_TOKEN:
            init_script += f"""
                try {{
                    localStorage.setItem('auth_token', '{config.BLINKIT_AUTH_TOKEN}');
                    localStorage.setItem('token', '{config.BLINKIT_AUTH_TOKEN}');
                }} catch (e) {{}}
            """
        elif platform == "rooter" and config.ROOTER_AUTH_TOKEN:
            init_script += f"""
                try {{
                    localStorage.setItem('rooter_token', '{config.ROOTER_AUTH_TOKEN}');
                    localStorage.setItem('token', '{config.ROOTER_AUTH_TOKEN}');
                    localStorage.setItem('authToken', '{config.ROOTER_AUTH_TOKEN}');
                }} catch (e) {{}}
            """

        await context.add_init_script(init_script)

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
        domain_origin = "https://rooter.gg" if platform == "rooter" else "https://blinkit.com"

        # Check if raw_data is a plain token string (e.g. Bearer eyJ... or eyJ...)
        clean_token = raw_data
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        # If it's a raw string (not JSON dict or list), treat directly as auth token
        if not (clean_token.startswith("{") or clean_token.startswith("[")):
            if len(clean_token) > 10:
                if platform == "rooter":
                    origins = [
                        {
                            "origin": "https://shop.rooter.gg",
                            "localStorage": [
                                {"name": "token", "value": clean_token},
                                {"name": "auth_token", "value": clean_token},
                                {"name": "rooter_token", "value": clean_token},
                                {"name": "authToken", "value": clean_token},
                            ]
                        },
                        {
                            "origin": "https://rooter.gg",
                            "localStorage": [
                                {"name": "token", "value": clean_token},
                                {"name": "auth_token", "value": clean_token},
                                {"name": "rooter_token", "value": clean_token},
                                {"name": "authToken", "value": clean_token},
                            ]
                        }
                    ]
                else:
                    origins = [
                        {
                            "origin": "https://blinkit.com",
                            "localStorage": [
                                {"name": "token", "value": clean_token},
                                {"name": "auth_token", "value": clean_token},
                            ]
                        }
                    ]

                payload = {
                    "cookies": [],
                    "origins": origins
                }
                with open(session_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                logger.info(f"Saved raw Bearer token for user {user_id} on {platform}")
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
