"""
Rooter automation service using Playwright.
Handles gaming shop navigation, user authentication, PlayStation wallet voucher search, redemption/checkout, and PIN extraction.
"""

import asyncio
import logging
import re
from typing import Optional, List, Callable, Awaitable
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from services.base_platform import BasePlatform, CardItem, PurchaseResult, ProgressCallback

logger = logging.getLogger(__name__)

class RooterService(BasePlatform):
    """Playwright scraper for Rooter Shop PlayStation voucher automation."""

    def __init__(self):
        super().__init__(
            platform_id="rooter",
            name="Rooter",
            base_url="https://shop.rooter.gg"
        )

    async def check_login_status(self, page: Page) -> bool:
        """Verifies if user is logged into Rooter."""
        try:
            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1500)

            # Check if login button is visible
            login_btn = page.locator("button:has-text('Login'), button:has-text('Sign In'), div:has-text('Login / Register')").first
            if await login_btn.is_visible(timeout=3000):
                return False

            # Check for profile icon / coin balance
            profile = page.locator("div[class*='Profile'], img[alt*='avatar'], div[class*='coin-balance']").first
            return await profile.is_visible(timeout=2000)
        except Exception as e:
            logger.warning(f"Error checking Rooter login status: {e}")
            return False

    async def perform_login(
        self,
        page: Page,
        phone_number: str,
        otp_callback: Callable[[], Awaitable[str]],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Logs into Rooter via mobile number and SMS OTP."""
        try:
            if progress_callback:
                await progress_callback("Navigating to Rooter login...", "🔍")

            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("networkidle")

            # Click login button
            login_btn = page.locator("button:has-text('Login'), div:has-text('Login')").first
            await login_btn.click(timeout=5000)
            await page.wait_for_timeout(1000)

            # Fill phone number
            clean_phone = re.sub(r"\D", "", phone_number)[-10:]
            phone_input = page.locator("input[type='tel'], input[placeholder*='Mobile'], input[name*='phone']").first
            await phone_input.fill(clean_phone)
            await page.wait_for_timeout(500)

            # Submit phone to request OTP
            get_otp_btn = page.locator("button:has-text('Get OTP'), button:has-text('Continue'), button:has-text('Next')").first
            await get_otp_btn.click()

            if progress_callback:
                await progress_callback(f"OTP sent to +91 {clean_phone}. Please reply with OTP in chat...", "📩")

            # Await OTP code from user
            otp_code = await otp_callback()
            if not otp_code:
                logger.error("No OTP provided for Rooter login.")
                return False

            clean_otp = re.sub(r"\D", "", otp_code)

            # Fill OTP inputs
            otp_inputs = page.locator("input[type='number'], input[inputmode='numeric']")
            count = await otp_inputs.count()
            if count > 1:
                for i in range(min(count, len(clean_otp))):
                    await otp_inputs.nth(i).fill(clean_otp[i])
            else:
                single_input = page.locator("input[placeholder*='OTP'], input[name*='otp']").first
                await single_input.fill(clean_otp)

            await page.wait_for_timeout(800)

            # Click verify
            verify_btn = page.locator("button:has-text('Verify'), button:has-text('Submit')").first
            if await verify_btn.is_visible(timeout=2000):
                await verify_btn.click()

            await page.wait_for_load_state("networkidle", timeout=10000)
            if progress_callback:
                await progress_callback("Rooter account verified successfully!", "✅")
            return True

        except Exception as e:
            logger.error(f"Error during Rooter login: {e}")
            return False

    async def search_playstation_cards(
        self,
        page: Page,
        denomination: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[CardItem]:
        """Navigates to Rooter Shop and looks for PlayStation Wallet vouchers."""
        if progress_callback:
            await progress_callback("Navigating to Rooter Shop...", "🔍")

        await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        if progress_callback:
            await progress_callback("Searching Rooter gaming vouchers for PlayStation...", "🔎")

        cards: List[CardItem] = []

        # Try search bar if present
        search_input = page.locator("input[placeholder*='Search'], input[type='search']").first
        if await search_input.is_visible(timeout=2000):
            await search_input.fill("PlayStation")
            await search_input.press("Enter")
            await page.wait_for_timeout(1500)

        # Scrape item cards
        items = page.locator("div[class*='VoucherCard'], div[class*='shop-item'], div[class*='reward-card']")
        count = await items.count()

        for i in range(count):
            item = items.nth(i)
            text = await item.inner_text()
            if "playstation" in text.lower() or "psn" in text.lower():
                denom_match = re.search(r"₹\s*([0-9,]+)", text)
                extracted_price = int(denom_match.group(1).replace(",", "")) if denom_match else (denomination or 1000)
                in_stock = "out of stock" not in text.lower() and "sold out" not in text.lower()

                cards.append(CardItem(
                    title=f"Rooter PlayStation Voucher ₹{extracted_price:,}",
                    denomination=extracted_price,
                    price=float(extracted_price),
                    platform="rooter",
                    in_stock=in_stock,
                ))

        # If cards list is empty or page indicates Out of Stock
        if not cards:
            body_text = await page.locator("body").inner_text()
            is_out_of_stock = "out of stock" in body_text.lower() or "sold out" in body_text.lower()
            logger.info(f"Rooter Shop catalog status: out_of_stock={is_out_of_stock}")
            for d in config.PLATFORMS["rooter"]["supported_denominations"]:
                cards.append(CardItem(
                    title=f"Rooter PlayStation Voucher ₹{d:,}",
                    denomination=d,
                    price=float(d),
                    platform="rooter",
                    in_stock=not is_out_of_stock,
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
        """Completes automated voucher redemption or purchase on Rooter."""
        try:
            cards = await self.search_playstation_cards(page, denomination=denomination, progress_callback=progress_callback)

            in_stock_card = next((c for c in cards if c.in_stock), None)
            if not in_stock_card:
                if progress_callback:
                    await progress_callback(f"PlayStation ₹{denomination:,} card is Out of Stock on Rooter!", "⚠️")
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message=f"PlayStation Gift Card (₹{denomination:,}) is currently OUT OF STOCK on Rooter Shop. Please try Blinkit instead!",
                )

            if progress_callback:
                await progress_callback("Adding PlayStation voucher to cart...", "🛒")

            # Click voucher / redeem button
            redeem_btn = page.locator("button:has-text('Redeem'), button:has-text('Buy Now'), button:has-text('Claim')").first
            if await redeem_btn.is_visible(timeout=3000):
                await redeem_btn.click()
                await page.wait_for_timeout(1000)

            # Check simulation mode
            if simulation:
                if progress_callback:
                    await progress_callback("SIMULATION MODE: Rooter order verified! Generating mock voucher code...", "💳")
                await page.wait_for_timeout(2000)

                mock_code = f"ROTR-PSN-{denomination}-{hash(page) % 90000 + 10000}"
                mock_pin = f"{hash(page) % 9000 + 1000}"
                mock_order = f"RTR-ORD-{asyncio.get_event_loop().time():.0f}"

                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=denomination,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    order_id=mock_order,
                    receipt_summary=f"Rooter Gaming Rewards - 1x PlayStation Network ₹{denomination:,}",
                    message="Purchase flow simulated successfully in dry-run mode.",
                    simulation=True,
                )

            if progress_callback:
                await progress_callback("Completing purchase & verifying payment on Rooter...", "💳")

            confirm_checkout = page.locator("button:has-text('Confirm'), button:has-text('Pay Now'), button:has-text('Proceed')").first
            if await confirm_checkout.is_visible(timeout=5000):
                await confirm_checkout.click()
                await page.wait_for_timeout(4000)

            # Check page content for voucher details OR errors
            page_content = await page.locator("body").inner_text()
            
            # Check for error indicators (insufficient balance, payment failed, etc.)
            if "insufficient" in page_content.lower() or "low balance" in page_content.lower() or "add coins" in page_content.lower():
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Insufficient balance in your Rooter wallet. Please add funds/coins to your Rooter account first!",
                )

            code_match = re.search(r"(?:Code|Voucher|Key)[\s:]+([A-Z0-9-]{10,25})", page_content, re.IGNORECASE)
            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", page_content, re.IGNORECASE)
            order_match = re.search(r"(?:Order ID|Txn ID|Reference)[\s:]+([A-Z0-9#-]+)", page_content, re.IGNORECASE)

            if not code_match:
                # No voucher was produced - payment was not completed or gateway pending
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Purchase could not be completed automatically. Rooter requires active wallet balance or manual payment approval (UPI/QR).",
                )

            code = code_match.group(1)
            pin = pin_match.group(1) if pin_match else "N/A"
            order_id = order_match.group(1) if order_match else "Rooter Order"

            return PurchaseResult(
                success=True,
                platform="rooter",
                denomination=denomination,
                voucher_code=code,
                voucher_pin=pin,
                order_id=order_id,
                receipt_summary=f"Rooter Redeemed Voucher - PlayStation ₹{denomination:,}",
                message="Voucher successfully redeemed on Rooter!",
                simulation=False,
            )

        except Exception as e:
            logger.error(f"Rooter purchase failed: {e}", exc_info=True)
            return PurchaseResult(
                success=False,
                platform="rooter",
                denomination=denomination,
                message=f"Rooter automation encountered an issue: {str(e)}",
            )

    async def check_is_in_stock(self, page: Page, denomination: int) -> bool:
        """Fast check to see if PlayStation voucher is currently in stock on Rooter Shop."""
        try:
            await page.goto(self.base_url, timeout=20000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1500)

            # Search PlayStation
            search_input = page.locator("input[placeholder*='Search']").first
            if await search_input.is_visible(timeout=2000):
                await search_input.fill("PlayStation")
                await search_input.press("Enter")
                await page.wait_for_timeout(2000)

            body_text = await page.locator("body").inner_text()
            # If all PlayStation items are labeled 'Out of Stock'
            if "out of stock" in body_text.lower():
                return False

            # Check if any Redeem or Buy Now button is visible
            redeem_btn = page.locator("button:has-text('Redeem'), button:has-text('Buy Now'), button:has-text('Claim')").first
            return await redeem_btn.is_visible(timeout=2000)
        except Exception as e:
            logger.warning(f"Error checking Rooter stock: {e}")
            return False
