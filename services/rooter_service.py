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
        self.product_url = "https://shop.rooter.gg/product/playstation-gift-cards"

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
        """Navigates directly to Rooter PlayStation gift cards page and checks available options."""
        if progress_callback:
            await progress_callback("Opening Rooter PlayStation Gift Cards page...", "🔍")

        target_url = getattr(self, "product_url", "https://shop.rooter.gg/product/playstation-gift-cards")
        if target_url not in page.url:
            await page.goto(target_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)

        cards: List[CardItem] = []
        supported = [1000, 2000, 3000, 4000, 5000]

        for d in supported:
            # Check for denomination option element e.g. "Rs.1000 Wallet Code"
            opt_locator = page.locator("div, span, p").filter(has_text=re.compile(rf"Rs\.?\s*{d}\s*Wallet Code", re.IGNORECASE))
            in_stock = False

            try:
                if await opt_locator.count() > 0:
                    parent_text = await opt_locator.first.locator("xpath=..").inner_text()
                    # An option is out of stock if its specific card text container has 'out of stock'
                    in_stock = "out of stock" not in parent_text.lower()
                else:
                    simple_opt = page.locator("div").filter(has_text=re.compile(rf"{d}\s*Wallet Code", re.IGNORECASE))
                    if await simple_opt.count() > 0:
                        in_stock = "out of stock" not in (await simple_opt.first.inner_text()).lower()
            except Exception:
                in_stock = False

            cards.append(CardItem(
                title=f"Rooter PlayStation Voucher ₹{d:,}",
                denomination=d,
                price=float(d),
                platform="rooter",
                in_stock=in_stock,
            ))

        if denomination:
            cards = [c for c in cards if c.denomination == denomination]

        return cards

    async def check_is_in_stock(self, page: Page, denomination: int) -> bool:
        """Accurate, denomination-specific check on Rooter PlayStation product page."""
        try:
            target_url = getattr(self, "product_url", "https://shop.rooter.gg/product/playstation-gift-cards")
            if target_url not in page.url:
                await page.goto(target_url, timeout=20000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1000)
            else:
                await page.reload(timeout=20000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(800)

            # Find specific denomination block e.g. "Rs.1000 Wallet Code"
            denom_opt = page.locator("div").filter(has_text=re.compile(rf"Rs\.?\s*{denomination}\s*Wallet Code", re.IGNORECASE))
            if await denom_opt.count() == 0:
                denom_opt = page.locator("div").filter(has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE))

            if await denom_opt.count() > 0:
                target_card = denom_opt.last
                card_text = await target_card.inner_text()

                # If this specific denomination card says 'out of stock', it is out of stock
                if "out of stock" in card_text.lower():
                    logger.debug(f"[Rooter] ₹{denomination} card option is labeled Out of Stock.")
                    return False

                # Denomination option is NOT marked out of stock! Click to select it:
                await target_card.click()
                await page.wait_for_timeout(600)

                # Check the main bottom action button
                # When stock is available and selected, button turns to "Buy Now" or "Proceed" or "Pay"
                bottom_btn = page.locator("button:has-text('Buy Now'), button:has-text('Proceed'), button:has-text('Pay')").first
                if await bottom_btn.is_visible(timeout=2000):
                    btn_text = await bottom_btn.inner_text()
                    if "out of stock" not in btn_text.lower():
                        logger.info(f"🚨 [Rooter] IN STOCK: ₹{denomination} button is active ({btn_text})!")
                        return True

                # If the main button still says "Out of Stock"
                out_btn = page.locator("button:has-text('Out of Stock')").first
                if await out_btn.is_visible(timeout=1000):
                    return False

                # If no out of stock indicator found on this denomination, treat as available
                return True

            logger.warning(f"[Rooter] Could not locate option card for ₹{denomination}")
            return False

        except Exception as e:
            logger.warning(f"Error checking Rooter stock: {e}")
            return False

    async def execute_buy_flow(
        self,
        page: Page,
        denomination: int,
        progress_callback: Optional[ProgressCallback] = None,
        simulation: bool = False,
    ) -> PurchaseResult:
        """Completes automated voucher purchase on Rooter with Rooter Wallet balance."""
        try:
            target_url = getattr(self, "product_url", "https://shop.rooter.gg/product/playstation-gift-cards")
            if target_url not in page.url:
                if progress_callback:
                    await progress_callback("Navigating to PlayStation product page...", "🔍")
                await page.goto(target_url, timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1000)

            # 1. Select the specific denomination card
            denom_opt = page.locator("div").filter(has_text=re.compile(rf"Rs\.?\s*{denomination}\s*Wallet Code", re.IGNORECASE))
            if await denom_opt.count() == 0:
                denom_opt = page.locator("div").filter(has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE))

            if await denom_opt.count() > 0:
                await denom_opt.last.click()
                await page.wait_for_timeout(600)

            # 2. Check if main action button is disabled / Out of Stock
            out_btn = page.locator("button:has-text('Out of Stock')").first
            if await out_btn.is_visible(timeout=1500):
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message=f"PlayStation ₹{denomination:,} was caught by someone else or went out of stock right before checkout!",
                )

            # 3. Handle Simulation Mode
            if simulation:
                if progress_callback:
                    await progress_callback("SIMULATION MODE: Voucher stock verified! Simulating dry-run purchase...", "💳")
                await page.wait_for_timeout(1500)

                mock_code = f"ROTR-PSN-{denomination}-{hash(page) % 90000 + 10000}"
                mock_pin = f"{hash(page) % 9000 + 1000}"
                mock_order = f"RTR-ORD-{int(asyncio.get_event_loop().time())}"

                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=denomination,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    order_id=mock_order,
                    receipt_summary=f"Rooter PlayStation Voucher ₹{denomination:,} [SIMULATION]",
                    message="Purchase flow simulated successfully in dry-run mode. Turn off SIMULATION_MODE to purchase with real balance.",
                    simulation=True,
                )

            # 4. Live Purchase Execution
            if progress_callback:
                await progress_callback("Clicking Buy Now & preparing checkout...", "🛒")

            # Click active Buy Now / Proceed button
            buy_btn = page.locator("button:has-text('Buy Now'), button:has-text('Proceed'), button:has-text('Pay')").first
            if await buy_btn.is_visible(timeout=3000):
                await buy_btn.click()
                await page.wait_for_timeout(1500)

            # Close coupon or offer popup if shown
            close_coupon = page.locator("button:has-text('Skip'), svg[class*='close'], button[aria-label*='Close']").first
            if await close_coupon.is_visible(timeout=1500):
                try:
                    await close_coupon.click()
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

            # Select Rooter Wallet / Balance payment method if presented
            wallet_opt = page.locator("div, span, label").filter(has_text=re.compile(r"(?:Rooter\s*Wallet|Wallet\s*Balance|Pay\s*via\s*Wallet|Rooter\s*Pay)", re.IGNORECASE)).first
            if await wallet_opt.is_visible(timeout=2000):
                await wallet_opt.click()
                await page.wait_for_timeout(500)

            # Confirm payment / final proceed button
            confirm_pay = page.locator("button:has-text('Pay Now'), button:has-text('Proceed to Pay'), button:has-text('Confirm')").first
            if await confirm_pay.is_visible(timeout=3000):
                if progress_callback:
                    await progress_callback("Submitting payment with Rooter balance...", "💳")
                await confirm_pay.click()
                await page.wait_for_timeout(4000)

            # Inspect page content for voucher code or errors
            body_content = await page.locator("body").inner_text()

            # Check for error indicators
            if "insufficient" in body_content.lower() or "low balance" in body_content.lower():
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Rooter wallet balance insufficient for this purchase.",
                )

            code_match = re.search(r"(?:Code|Voucher|Key)[\s:]+([A-Z0-9-]{10,25})", body_content, re.IGNORECASE)
            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", body_content, re.IGNORECASE)
            order_match = re.search(r"(?:Order ID|Txn ID|Reference)[\s:]+([A-Z0-9#-]+)", body_content, re.IGNORECASE)

            if not code_match:
                # Capture screenshot for user inspection
                shot_path = await browser_manager.capture_screenshot(page, "rooter_order_result")
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Order submitted, but voucher code was not detected on confirmation page. Please check your Rooter profile / Orders tab.",
                    error_screenshot=shot_path,
                )

            code = code_match.group(1)
            pin = pin_match.group(1) if pin_match else "N/A"
            order_id = order_match.group(1) if order_match else f"RTR-{int(asyncio.get_event_loop().time())}"

            return PurchaseResult(
                success=True,
                platform="rooter",
                denomination=denomination,
                voucher_code=code,
                voucher_pin=pin,
                order_id=order_id,
                receipt_summary=f"Rooter PlayStation Voucher ₹{denomination:,}",
                message="Voucher successfully purchased on Rooter with wallet balance!",
                simulation=False,
            )

        except Exception as e:
            logger.error(f"Rooter buy flow encountered error: {e}", exc_info=True)
            shot_path = await browser_manager.capture_screenshot(page, "rooter_buy_error")
            return PurchaseResult(
                success=False,
                platform="rooter",
                denomination=denomination,
                message=f"Rooter automation error: {str(e)}",
                error_screenshot=shot_path,
            )
