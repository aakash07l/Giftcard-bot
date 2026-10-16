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
from services.browser_manager import browser_manager

logger = logging.getLogger(__name__)

class RooterService(BasePlatform):
    """Playwright scraper for Rooter Shop PlayStation and Google Play voucher automation."""

    def __init__(self):
        super().__init__(
            platform_id="rooter",
            name="Rooter",
            base_url="https://shop.rooter.gg"
        )
        self.playstation_url = getattr(config, "ROOTER_PLAYSTATION_URL", "https://shop.rooter.gg/product/playstation-gift-cards")
        self.google_play_url = getattr(config, "ROOTER_GOOGLE_PLAY_URL", "https://shop.rooter.gg/product/google-play-gift-card")

    def get_product_info(self, denomination: int) -> dict:
        """Returns product url, name, and type based on denomination."""
        if denomination < 1000:
            return {
                "type": "google_play",
                "name": "Google Play Recharge Code",
                "url": self.google_play_url,
                "expected_price": 8.0,
            }
        return {
            "type": "playstation",
            "name": "PlayStation Gift Card",
            "url": self.playstation_url,
            "expected_price": float(denomination),
        }

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
        """Navigates directly to Rooter gift card pages and checks available options."""
        cards: List[CardItem] = []

        # If user asked specifically for Google Play (e.g. 10)
        if denomination == 10:
            in_stock = await self.check_is_in_stock(page, 10)
            cards.append(CardItem(
                title="Google Play Recharge Code ₹10",
                denomination=10,
                price=8.0,
                platform="rooter",
                in_stock=in_stock,
            ))
            return cards

        target_url = self.playstation_url
        if target_url not in page.url:
            if progress_callback:
                await progress_callback("Opening Rooter PlayStation Gift Cards page...", "🔍")
            await page.goto(target_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)

        # Include Google Play ₹10 test option if searching all
        if not denomination:
            cards.append(CardItem(
                title="Google Play Recharge Code ₹10 (Test)",
                denomination=10,
                price=8.0,
                platform="rooter",
                in_stock=True,
            ))

        supported = [1000, 2000, 3000, 4000, 5000]
        for d in supported:
            opt_locator = page.locator("div, span, p").filter(has_text=re.compile(rf"Rs\.?\s*{d}\s*Wallet Code", re.IGNORECASE))
            in_stock = False

            try:
                if await opt_locator.count() > 0:
                    parent_text = await opt_locator.first.locator("xpath=..").inner_text()
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
        """Accurate, denomination-specific check on Rooter product pages."""
        try:
            prod_info = self.get_product_info(denomination)
            target_url = prod_info["url"]

            if target_url not in page.url:
                await page.goto(target_url, timeout=20000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1000)
            else:
                await page.reload(timeout=20000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(800)

            # A. Google Play Recharge Code (₹10 Test Buy)
            if prod_info["type"] == "google_play":
                # Ensure denomination card is clicked if available
                opt_10 = page.locator("div, span, button").filter(has_text=re.compile(rf"^₹?\s*{denomination}(?:\s|$)", re.IGNORECASE)).first
                if await opt_10.is_visible(timeout=1000):
                    await opt_10.click()
                    await page.wait_for_timeout(400)

                # Check if bottom action button is active (Pay ₹8 / Pay Now / Buy Now)
                action_btn = page.locator("button:has-text('Pay'), button:has-text('Buy Now'), button:has-text('Proceed')").first
                if await action_btn.is_visible(timeout=2000):
                    btn_text = await action_btn.inner_text()
                    if "out of stock" not in btn_text.lower():
                        logger.info(f"🚨 [Rooter] IN STOCK: Google Play ₹{denomination} is active ({btn_text})!")
                        return True

                out_btn = page.locator("button:has-text('Out of Stock')").first
                if await out_btn.is_visible(timeout=1000):
                    return False
                return True

            # B. PlayStation Gift Cards (₹1,000 to ₹5,000)
            else:
                denom_opt = page.locator("div").filter(has_text=re.compile(rf"Rs\.?\s*{denomination}\s*Wallet Code", re.IGNORECASE))
                if await denom_opt.count() == 0:
                    denom_opt = page.locator("div").filter(has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE))

                if await denom_opt.count() > 0:
                    target_card = denom_opt.last
                    card_text = await target_card.inner_text()

                    # Check for out of stock indicator
                    if "out of stock" in card_text.lower():
                        logger.debug(f"[Rooter] ₹{denomination} card option is labeled Out of Stock.")
                        return False

                    # Click to select denomination
                    await target_card.click()
                    await page.wait_for_timeout(600)

                    # Check bottom action button
                    bottom_btn = page.locator("button:has-text('Buy Now'), button:has-text('Proceed'), button:has-text('Pay')").first
                    if await bottom_btn.is_visible(timeout=2000):
                        btn_text = await bottom_btn.inner_text()
                        if "out of stock" not in btn_text.lower():
                            logger.info(f"🚨 [Rooter] IN STOCK: PlayStation ₹{denomination} button is active ({btn_text})!")
                            return True

                    out_btn = page.locator("button:has-text('Out of Stock')").first
                    if await out_btn.is_visible(timeout=1000):
                        return False

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
            prod_info = self.get_product_info(denomination)
            target_url = prod_info["url"]
            prod_name = prod_info["name"]

            if target_url not in page.url:
                if progress_callback:
                    await progress_callback(f"Navigating to {prod_name} page...", "🔍")
                await page.goto(target_url, timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1000)

            # 1. Select the specific denomination
            if prod_info["type"] == "google_play":
                opt_10 = page.locator("div, span, button").filter(has_text=re.compile(rf"^₹?\s*{denomination}(?:\s|$)", re.IGNORECASE)).first
                if await opt_10.is_visible(timeout=1000):
                    await opt_10.click()
                    await page.wait_for_timeout(500)
            else:
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
                    message=f"{prod_name} ₹{denomination:,} went out of stock right before checkout!",
                )

            # 3. Handle Simulation Mode
            if simulation:
                if progress_callback:
                    await progress_callback(f"SIMULATION MODE: {prod_name} stock verified! Simulating dry-run purchase...", "💳")
                await page.wait_for_timeout(1500)

                prefix = "GOOG" if prod_info["type"] == "google_play" else "PSN"
                mock_code = f"ROTR-{prefix}-{denomination}-{hash(page) % 90000 + 10000}"
                mock_pin = f"{hash(page) % 9000 + 1000}"
                mock_order = f"RTR-ORD-{int(asyncio.get_event_loop().time())}"

                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=denomination,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    order_id=mock_order,
                    receipt_summary=f"Rooter {prod_name} ₹{denomination:,} [SIMULATION]",
                    message="Purchase flow simulated successfully in dry-run mode. Turn off SIMULATION_MODE to purchase with real balance.",
                    simulation=True,
                )

            # 4. Live Purchase Execution
            if progress_callback:
                await progress_callback(f"Clicking Buy / Pay on {prod_name}...", "🛒")

            # Click active Buy Now / Proceed / Pay button
            buy_btn = page.locator("button:has-text('Pay via wallet'), button:has-text('Buy Now'), button:has-text('Proceed'), button:has-text('Pay')").first
            if await buy_btn.is_visible(timeout=3000):
                await buy_btn.click()
                await page.wait_for_timeout(1500)

            # Check if Delivery Details modal is visible
            delivery_modal = page.locator("text='Delivery Details', div[role='dialog']:has-text('Delivery Details')").first
            if await delivery_modal.is_visible(timeout=2500):
                if progress_callback:
                    await progress_callback("Confirming Delivery Details & submitting order...", "📝")
                logger.info("[Rooter] Delivery Details modal detected. Clicking Pay via wallet inside modal...")
                modal_pay_btn = page.locator("div[role='dialog'] button:has-text('Pay via wallet'), div[class*='modal'] button:has-text('Pay via wallet'), button:has-text('Pay via wallet')").last
                if await modal_pay_btn.is_visible(timeout=2000):
                    await modal_pay_btn.click()
                    await page.wait_for_timeout(4000)

            # Close coupon or offer popup if shown
            close_coupon = page.locator("button:has-text('Skip'), svg[class*='close'], button[aria-label*='Close']").first
            if await close_coupon.is_visible(timeout=1500):
                try:
                    await close_coupon.click()
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

            # Select Rooter Wallet / Balance payment method if presented
            wallet_opt = page.locator("div, span, label").filter(has_text=re.compile(r"(?:Rooter\s*Wallet|Wallet\s*Balance|Pay\s*via\s*Wallet|Rooter\s*Pay|Rooter\s*Credits)", re.IGNORECASE)).first
            if await wallet_opt.is_visible(timeout=2000):
                await wallet_opt.click()
                await page.wait_for_timeout(500)

            # Confirm payment / final proceed button
            confirm_pay = page.locator("button:has-text('Pay via wallet'), button:has-text('Pay Now'), button:has-text('Proceed to Pay'), button:has-text('Confirm')").last
            if await confirm_pay.is_visible(timeout=2000):
                if progress_callback:
                    await progress_callback("Submitting payment with Rooter balance...", "💳")
                await confirm_pay.click()
                await page.wait_for_timeout(4000)

            # Capture confirmation screenshot
            shot_path = await browser_manager.capture_screenshot(page, f"order_{prod_info['type']}_{denomination}")

            # Inspect page content for voucher code or errors
            body_content = await page.locator("body").inner_text()

            # Check for error indicators
            if "insufficient" in body_content.lower() or "low balance" in body_content.lower():
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Rooter wallet balance insufficient for this purchase.",
                    error_screenshot=shot_path,
                )

            # Check if login modal unexpectedly appeared (e.g. auth expired or not logged in)
            is_login_modal = any(
                p in body_content.lower()
                for p in [
                    "login / sign up",
                    "login / register",
                    "enter your mobile number",
                    "enter mobile number",
                    "continue with google",
                    "have a referral code",
                ]
            )
            if is_login_modal:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Rooter session expired or not logged in! Rooter login popup appeared. Please send /login to bot and paste your Bearer token, or set ROOTER_AUTH_TOKEN in Railway variables.",
                    error_screenshot=shot_path,
                )

            # Search for Code, PIN, Order ID on current page
            code_match = re.search(r"(?:Code\s*#?\d*|Voucher|Key|Redeem\s*Code|Coupon\s*Codes?)[\s:\n]+([A-Z0-9-]{10,25})", body_content, re.IGNORECASE)
            if not code_match and prod_info["type"] == "google_play":
                gp_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b", body_content, re.IGNORECASE)
                if not gp_match:
                    gp_match = re.search(r"\b([A-Z0-9]{16})\b", body_content)
                if gp_match:
                    code_match = gp_match

            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", body_content, re.IGNORECASE)
            order_match = re.search(r"(?:Order\s*Id|Txn\s*ID|Reference)[\s:]*#?([A-Z0-9_-]+)", body_content, re.IGNORECASE)

            # Success indicators
            success_indicators = [
                "delivered successfully", "items delivered", "item purchased", "coupon codes",
                "paid amount", "order placed", "order successful", "purchase successful",
                "transaction successful", "thank you", "congratulations", "redeem code"
            ]
            is_successful_order = any(ind in body_content.lower() for ind in success_indicators) or (code_match is not None)

            # If code was not found directly on post-checkout page, auto-fetch from Rooter profile/orders
            if not code_match:
                try:
                    logger.info("[Rooter] Checking profile/orders to extract latest voucher code...")
                    await page.goto("https://shop.rooter.gg/profile/orders", wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2500)

                    # Click top order card to view coupon code
                    order_card = page.locator("text='Google Play Recharge Code', text='PlayStation Gift Card', div[class*='order']").first
                    if await order_card.is_visible(timeout=3000):
                        await order_card.click()
                        await page.wait_for_timeout(2000)

                    orders_body = await page.locator("body").inner_text()
                    code_match = re.search(r"(?:Code\s*#?\d*|Voucher|Key|Redeem\s*Code|Coupon\s*Codes?)[\s:\n]+([A-Z0-9-]{10,25})", orders_body, re.IGNORECASE)
                    if not code_match and prod_info["type"] == "google_play":
                        code_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b", orders_body, re.IGNORECASE)
                        if not code_match:
                            code_match = re.search(r"\b([A-Z0-9]{16})\b", orders_body)

                    if not pin_match:
                        pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", orders_body, re.IGNORECASE)
                    if not order_match:
                        order_match = re.search(r"(?:Order\s*Id|Txn\s*ID|Reference)[\s:]*#?([A-Z0-9_-]+)", orders_body, re.IGNORECASE)

                    if code_match or any(ind in orders_body.lower() for ind in success_indicators):
                        is_successful_order = True
                        shot_path = await browser_manager.capture_screenshot(page, f"order_{prod_info['type']}_{denomination}")
                except Exception as oe:
                    logger.warning(f"[Rooter] Could not auto-fetch from profile/orders: {oe}")

            if not is_successful_order and not code_match:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    message="Order submitted, but order confirmation was not detected on page. Please verify your Rooter profile / Orders tab.",
                    error_screenshot=shot_path,
                )

            code = code_match.group(1) if code_match else "Check Orders Tab in Rooter"
            pin = pin_match.group(1) if pin_match else "N/A"
            order_id = order_match.group(1) if order_match else f"RTR-{int(asyncio.get_event_loop().time())}"

            return PurchaseResult(
                success=True,
                platform="rooter",
                denomination=denomination,
                voucher_code=code,
                voucher_pin=pin,
                order_id=order_id,
                receipt_summary=f"Rooter {prod_name} ₹{denomination:,}",
                message=f"{prod_name} successfully purchased on Rooter with wallet balance!",
                error_screenshot=shot_path,
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
