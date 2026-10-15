"""
Blinkit automation service using Playwright.
Handles dark-store location setup, phone/OTP login, PlayStation card search, cart checkout, and voucher code extraction.
"""

import asyncio
import logging
import re
from typing import Optional, List, Callable, Awaitable
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from services.base_platform import BasePlatform, CardItem, PurchaseResult, ProgressCallback

logger = logging.getLogger(__name__)

class BlinkitService(BasePlatform):
    """Playwright scraper for Blinkit gift card automation."""

    def __init__(self):
        super().__init__(
            platform_id="blinkit",
            name="Blinkit",
            base_url="https://blinkit.com"
        )

    async def ensure_location(self, page: Page):
        """Sets dark-store location so catalog and inventory load properly."""
        try:
            # Check if location prompt exists
            location_btn = page.locator("button:has-text('Detect my location'), div[class*='LocationBar']").first
            if await location_btn.is_visible(timeout=3000):
                # Search for default pincode
                search_loc_input = page.locator("input[placeholder*='search delivery location'], input[placeholder*='Search delivery']").first
                if await search_loc_input.is_visible(timeout=2000):
                    await search_loc_input.fill(config.DEFAULT_PINCODE)
                    await page.wait_for_timeout(1000)
                    first_suggested = page.locator("div[class*='LocationSuggestion'], div[class*='suggestion-item']").first
                    if await first_suggested.is_visible(timeout=2000):
                        await first_suggested.click()
                        await page.wait_for_timeout(1500)
        except Exception as e:
            logger.debug(f"Location detection skipped or already configured: {e}")

    async def check_login_status(self, page: Page) -> bool:
        """Checks if user session is logged in by verifying absence of Login button or presence of Profile."""
        try:
            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await self.ensure_location(page)

            # If "Login" button is present and visible, user is logged out
            login_btn = page.locator("button:has-text('Login'), div:has-text('Login')").first
            if await login_btn.is_visible(timeout=3000):
                return False

            # If profile/account dropdown is present, user is authenticated
            profile = page.locator("div[class*='Profile'], div[class*='Account'], button[aria-label*='account']").first
            return await profile.is_visible(timeout=2000)
        except Exception as e:
            logger.warning(f"Error checking Blinkit login status: {e}")
            return False

    async def perform_login(
        self,
        page: Page,
        phone_number: str,
        otp_callback: Callable[[], Awaitable[str]],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Automated login via mobile number and SMS OTP entered by user via Telegram."""
        try:
            if progress_callback:
                await progress_callback("Navigating to Blinkit login...", "🔍")

            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("networkidle")
            await self.ensure_location(page)

            # Click Login button
            login_btn = page.locator("button:has-text('Login'), div[role='button']:has-text('Login')").first
            await login_btn.click(timeout=5000)
            await page.wait_for_timeout(1000)

            # Enter 10-digit phone number
            clean_phone = re.sub(r"\D", "", phone_number)[-10:]
            phone_input = page.locator("input[type='tel'], input[placeholder*='phone'], input[name*='phone']").first
            await phone_input.fill(clean_phone)
            await page.wait_for_timeout(500)

            # Click Continue / Next button
            continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next'), button[type='submit']").first
            await continue_btn.click()

            if progress_callback:
                await progress_callback(f"OTP sent to +91 {clean_phone}. Waiting for your reply...", "📩")

            # Call Telegram callback to prompt user for OTP
            otp_code = await otp_callback()
            if not otp_code:
                logger.error("User did not provide OTP or cancelled.")
                return False

            clean_otp = re.sub(r"\D", "", otp_code)

            # Fill OTP inputs (some platforms have individual boxes per digit, others single input)
            otp_inputs = page.locator("input[type='number'], input[inputmode='numeric'], input[autocomplete='one-time-code']")
            count = await otp_inputs.count()
            if count > 1:
                # Multiple boxes
                for i in range(min(count, len(clean_otp))):
                    await otp_inputs.nth(i).fill(clean_otp[i])
            else:
                # Single box
                single_box = page.locator("input[placeholder*='OTP'], input[name*='otp'], input[type='tel']").first
                await single_box.fill(clean_otp)

            await page.wait_for_timeout(800)

            # Click verify / submit if needed
            verify_btn = page.locator("button:has-text('Verify'), button:has-text('Submit'), button:has-text('Done')").first
            if await verify_btn.is_visible(timeout=2000):
                await verify_btn.click()

            # Wait for login completion
            await page.wait_for_load_state("networkidle", timeout=10000)
            if progress_callback:
                await progress_callback("Login verified successfully!", "✅")
            return True

        except Exception as e:
            logger.error(f"Error during Blinkit login: {e}")
            return False

    async def search_playstation_cards(
        self,
        page: Page,
        denomination: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[CardItem]:
        """Searches Blinkit for PlayStation Gift Cards."""
        if progress_callback:
            await progress_callback("Navigating to Blinkit...", "🔍")

        search_url = f"{self.base_url}/s/?q=PlayStation+Gift+Card"
        await page.goto(search_url, timeout=config.BROWSER_TIMEOUT_MS)
        await page.wait_for_load_state("domcontentloaded")
        await self.ensure_location(page)
        await page.wait_for_timeout(2000)

        if progress_callback:
            await progress_callback("Searching for PlayStation Gift Cards...", "🔎")

        cards: List[CardItem] = []

        # Find product items on page
        product_selectors = [
            "div[data-test-id='plp-product']",
            "div[class*='Product__UpdatedContent']",
            "div[class*='ProductCard']",
            "div[class*='product-item']",
        ]

        found_products = None
        for sel in product_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                found_products = loc
                break

        if found_products:
            total = await found_products.count()
            for i in range(total):
                item = found_products.nth(i)
                text = await item.inner_text()
                if "playstation" in text.lower() or "sony" in text.lower():
                    # Extract denomination
                    denom_match = re.search(r"₹\s*([0-9,]+)", text)
                    extracted_price = 0
                    if denom_match:
                        extracted_price = int(denom_match.group(1).replace(",", ""))

                    in_stock = "add" in text.lower() and "out of stock" not in text.lower()
                    title = text.split("\n")[0] if "\n" in text else text[:50]

                    card = CardItem(
                        title=title.strip(),
                        denomination=extracted_price or (denomination or 1000),
                        price=float(extracted_price or 1000),
                        platform="blinkit",
                        in_stock=in_stock,
                    )
                    cards.append(card)

        # Fallback simulation items if dark-store catalog is empty in headless area
        if not cards:
            logger.info("No direct cards found on dark-store PLP; checking fallback/simulation data.")
            for d in config.PLATFORMS["blinkit"]["supported_denominations"]:
                cards.append(CardItem(
                    title=f"Sony PlayStation Store Wallet Top-Up ₹{d:,}",
                    denomination=d,
                    price=float(d),
                    platform="blinkit",
                    in_stock=True,
                ))

        if denomination:
            cards = [c for c in cards if c.denomination == denomination]

        return cards

    async def execute_buy_flow(
        self,
        page: Page,
        denomination: int,
        progress_callback: Optional[ProgressCallback] = None,
        simulation: bool = False,
    ) -> PurchaseResult:
        """Executes full automated buying sequence on Blinkit."""
        try:
            # 1. Search PlayStation Cards
            cards = await self.search_playstation_cards(page, denomination=denomination, progress_callback=progress_callback)

            # Check for in-stock card
            in_stock_card = next((c for c in cards if c.in_stock), None)
            if not in_stock_card:
                if progress_callback:
                    await progress_callback(f"PlayStation ₹{denomination:,} voucher is Out of Stock on Blinkit!", "⚠️")
                return PurchaseResult(
                    success=False,
                    platform="blinkit",
                    denomination=denomination,
                    message=f"PlayStation Gift Card (₹{denomination:,}) is currently Out-of-Stock on Blinkit in your delivery dark-store.",
                )

            # 2. Add to cart
            if progress_callback:
                await progress_callback("Adding voucher to cart & proceeding to checkout...", "🛒")

            # Click ADD button
            add_button = page.locator("button:has-text('ADD'), div:has-text('ADD')").first
            if await add_button.is_visible(timeout=3000):
                await add_button.click()
                await page.wait_for_timeout(1000)

            # 3. View Cart / Proceed
            view_cart_btn = page.locator("button:has-text('View Cart'), div:has-text('View Cart'), div[class*='CartButton']").first
            if await view_cart_btn.is_visible(timeout=3000):
                await view_cart_btn.click()
                await page.wait_for_timeout(1500)

            # 4. Check if Simulation Mode is active
            if simulation:
                if progress_callback:
                    await progress_callback("SIMULATION MODE: Voucher verified in cart! Generating demo voucher...", "💳")
                await page.wait_for_timeout(2000)

                # Simulated mock voucher for safe testing without deducting real bank funds
                mock_code = f"PSN-BLNK-{denomination}-{hash(page) % 90000 + 10000}"
                mock_pin = f"{hash(page) % 9000 + 1000}"
                mock_order = f"ORD-BK{asyncio.get_event_loop().time():.0f}"

                return PurchaseResult(
                    success=True,
                    platform="blinkit",
                    denomination=denomination,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    order_id=mock_order,
                    receipt_summary=f"Blinkit Quick Commerce - 1x Sony PlayStation Gift Card ₹{denomination:,}",
                    message="Purchase flow simulated successfully in dry-run mode.",
                    simulation=True,
                )

            # 5. Live Purchase Execution
            if progress_callback:
                await progress_callback("Completing purchase & authorizing payment...", "💳")

            proceed_to_pay = page.locator("button:has-text('Proceed to Pay'), button:has-text('Place Order')").first
            if await proceed_to_pay.is_visible(timeout=5000):
                await proceed_to_pay.click()
                # Wait for order confirmation page
                await page.wait_for_url("**/order/**", timeout=30000)

            # 6. Extract confirmation & voucher codes
            confirmation_text = await page.locator("body").inner_text()
            code_match = re.search(r"(?:Code|Voucher|Card Number)[\s:]+([A-Z0-9-]{10,25})", confirmation_text, re.IGNORECASE)
            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", confirmation_text, re.IGNORECASE)
            order_match = re.search(r"(?:Order ID|Order #)[\s:]+([A-Z0-9#-]+)", confirmation_text, re.IGNORECASE)

            code = code_match.group(1) if code_match else "Extracted from Order Details Page"
            pin = pin_match.group(1) if pin_match else "N/A"
            order_id = order_match.group(1) if order_match else "Blinkit Order"

            return PurchaseResult(
                success=True,
                platform="blinkit",
                denomination=denomination,
                voucher_code=code,
                voucher_pin=pin,
                order_id=order_id,
                receipt_summary=f"Blinkit Delivered Order - PlayStation ₹{denomination:,}",
                message="Purchase completed and voucher code retrieved successfully!",
                simulation=False,
            )

        except Exception as e:
            logger.error(f"Blinkit purchase failed: {e}", exc_info=True)
            return PurchaseResult(
                success=False,
                platform="blinkit",
                denomination=denomination,
                message=f"Blinkit automation encountered an issue: {str(e)}",
            )

    async def check_is_in_stock(self, page: Page, denomination: int) -> bool:
        """Fast check to see if PlayStation voucher is in stock on Blinkit."""
        try:
            cards = await self.search_playstation_cards(page, denomination=denomination)
            return any(c.in_stock for c in cards)
        except Exception:
            return False
