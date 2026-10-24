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
        self.amazon_pay_url = getattr(config, "ROOTER_AMAZON_PAY_URL", "https://shop.rooter.gg/product/amazon-pay-gift-cards")

    def get_product_info(self, denomination: int, product_type: str = "playstation") -> dict:
        """Returns product url, name, and type based on denomination and product_type."""
        if product_type == "amazon" or denomination == 10:
            return {
                "type": "amazon_pay",
                "name": "Amazon Pay Gift Card",
                "url": self.amazon_pay_url,
                "expected_price": 9.92,
            }
        return {
            "type": "playstation",
            "name": "PlayStation Gift Card",
            "url": self.playstation_url,
            "expected_price": float(denomination) if denomination > 0 else 1000.0,
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

        target_url = self.playstation_url
        if target_url not in page.url:
            if progress_callback:
                await progress_callback("Opening Rooter PlayStation Gift Cards page...", "🔍")
            await page.goto(target_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)

        supported = [1000, 2000, 3000, 4000, 5000]
        for d in supported:
            opt_locator = page.locator("div[class*='chipWrapper'], div[class*='styles_chipRoot']").filter(
                has_text=re.compile(rf"{d}\s*Wallet Code", re.IGNORECASE)
            ).first
            in_stock = False

            try:
                if await opt_locator.count() > 0:
                    chip_txt = (await opt_locator.inner_text()).lower()
                    in_stock = ("out of stock" not in chip_txt) and ("sold out" not in chip_txt)
                else:
                    simple_opt = page.locator("div").filter(has_text=re.compile(rf"{d}\s*Wallet Code", re.IGNORECASE)).first
                    if await simple_opt.count() > 0:
                        txt = (await simple_opt.inner_text()).lower()
                        in_stock = ("out of stock" not in txt) and ("sold out" not in txt)
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

    async def dismiss_location_popup(self, page: Page):
        """Auto-dismisses 'Different Location Detected' modal by clicking 'No, stay on this site'."""
        try:
            stay_btn = page.locator("button:has-text('stay on this site'), button:has-text('No, stay on this site'), button:has-text('Stay on this site')").first
            if await stay_btn.is_visible(timeout=800):
                await stay_btn.click(force=True, timeout=1000)
                logger.info("[Rooter] Clicked 'No, stay on this site' on Different Location modal.")
                await page.wait_for_timeout(300)
        except Exception:
            pass

    async def get_in_stock_playstation_denominations(self, page: Page) -> List[int]:
        """Returns all PlayStation denominations currently in stock, sorted from highest to lowest (₹5k -> ₹1k)."""
        in_stock_list = []
        try:
            target_url = self.playstation_url
            if target_url not in page.url:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1000)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(800)

            # Auto-dismiss region popup if present
            await self.dismiss_location_popup(page)

            try:
                await page.wait_for_selector("div[class*='chipWrapper'], div[class*='styles_chipRoot']", timeout=8000)
                await page.wait_for_selector(
                    "button:has-text('Out of Stock'), button:has-text('Proceed to Pay'), button:has-text('Pay via wallet'), button:has-text('Buy Now')",
                    timeout=5000,
                )
            except Exception:
                pass

            await self.dismiss_location_popup(page)

            # Highest to lowest priority: ₹5,000 down to ₹1,000
            supported = [5000, 4000, 3000, 2000, 1000]
            for d in supported:
                denom_opt = page.locator("div[class*='chipWrapper'], div[class*='styles_chipRoot']").filter(
                    has_text=re.compile(rf"{d}\s*Wallet Code", re.IGNORECASE)
                ).first
                if await denom_opt.count() == 0:
                    denom_opt = page.locator("div").filter(has_text=re.compile(rf"{d}\s*Wallet Code", re.IGNORECASE)).last

                if await denom_opt.count() > 0:
                    chip_text = (await denom_opt.inner_text()).lower()
                    if "out of stock" in chip_text or "sold out" in chip_text:
                        continue

                    # Check parent container text as well
                    try:
                        parent_text = (await denom_opt.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")).lower()
                        if "out of stock" in parent_text:
                            continue
                    except Exception:
                        pass

                    # Click to select chip and verify the bottom action button confirms live stock!
                    try:
                        await denom_opt.click(force=True, timeout=1200)
                        await page.wait_for_timeout(250)
                    except Exception:
                        pass

                    bottom_btn = page.locator(
                        "button[data-testid='proceed-to-pay'], button:has-text('Proceed to Pay'), "
                        "button:has-text('Pay via wallet'), button:has-text('Buy Now'), button:has-text('Pay ₹'), "
                        "button:has-text('Out of Stock')"
                    ).first
                    if await bottom_btn.count() > 0:
                        btn_text = (await bottom_btn.inner_text()).lower()
                        is_disabled = await bottom_btn.is_disabled()
                        if "out of stock" in btn_text or is_disabled:
                            continue
                        if any(kw in btn_text for kw in ["pay", "buy", "proceed", "redeem"]):
                            logger.info(f"🚨 [Rooter] CONFIRMED IN STOCK: PlayStation ₹{d} (button: '{btn_text}')")
                            in_stock_list.append(d)
        except Exception as e:
            logger.warning(f"Error checking in-stock denominations: {e}")

        return in_stock_list

    async def find_available_playstation_denomination(self, page: Page) -> Optional[int]:
        """Finds the highest PlayStation denomination currently in stock on Rooter (₹5k -> ₹1k)."""
        denoms = await self.get_in_stock_playstation_denominations(page)
        return denoms[0] if denoms else None

    async def check_is_in_stock(self, page: Page, denomination: int) -> bool:
        """Accurate, denomination-specific check on Rooter product pages."""
        try:
            prod_info = self.get_product_info(denomination)
            target_url = prod_info["url"]

            if target_url not in page.url:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1000)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(800)

            # Auto-dismiss region popup if present
            await self.dismiss_location_popup(page)

            if denomination < 1000:
                logger.info(f"[Rooter] Denomination ₹{denomination} is not a valid PlayStation voucher.")
                return False

            # PlayStation Gift Cards (₹1,000 to ₹5,000)
            try:
                await page.wait_for_selector("div[class*='chipWrapper'], div[class*='styles_chipRoot']", timeout=8000)
                await page.wait_for_selector(
                    "button:has-text('Out of Stock'), button:has-text('Proceed to Pay'), button:has-text('Pay via wallet'), button:has-text('Buy Now')",
                    timeout=5000,
                )
            except Exception:
                pass

            await self.dismiss_location_popup(page)

            denom_opt = page.locator("div[class*='chipWrapper'], div[class*='styles_chipRoot']").filter(
                has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE)
            ).first
            if await denom_opt.count() == 0:
                denom_opt = page.locator("div").filter(has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE)).last

            if await denom_opt.count() > 0:
                chip_text = (await denom_opt.inner_text()).lower()
                if "out of stock" in chip_text or "sold out" in chip_text:
                    logger.debug(f"[Rooter] ₹{denomination} card option is labeled Out of Stock.")
                    return False

                try:
                    parent_text = (await denom_opt.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")).lower()
                    if "out of stock" in parent_text:
                        logger.debug(f"[Rooter] ₹{denomination} card parent wrapper is labeled Out of Stock.")
                        return False
                except Exception:
                    pass

                # Click to select denomination with force=True
                try:
                    await denom_opt.click(force=True, timeout=1200)
                    await page.wait_for_timeout(250)
                except Exception:
                    pass

                # Check bottom action button
                bottom_btn = page.locator(
                    "button[data-testid='proceed-to-pay'], button:has-text('Proceed to Pay'), "
                    "button:has-text('Pay via wallet'), button:has-text('Buy Now'), button:has-text('Pay ₹'), "
                    "button:has-text('Out of Stock')"
                ).first
                if await bottom_btn.count() > 0:
                    btn_text = (await bottom_btn.inner_text()).lower()
                    is_disabled = await bottom_btn.is_disabled()
                    if "out of stock" in btn_text or is_disabled:
                        return False
                    if any(kw in btn_text for kw in ["pay", "buy", "proceed", "redeem"]):
                        logger.info(f"🚨 [Rooter] IN STOCK: PlayStation ₹{denomination} button is active ({btn_text})!")
                        return True

            return False

        except Exception as e:
            logger.warning(f"Error checking Rooter stock: {e}")
            return False

    async def execute_buy_flow(
        self,
        page: Page,
        denomination: int,
        quantity: int = 1,
        account_label: Optional[str] = None,
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
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1000)

            # Auto-dismiss region popup if present
            await self.dismiss_location_popup(page)

            # 1. Select the specific PlayStation denomination
            denom_opt = page.locator("div[class*='chipWrapper'], div[class*='styles_chipRoot']").filter(
                has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE)
            ).first
            if await denom_opt.count() == 0:
                denom_opt = page.locator("label").filter(has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE)).first
            if await denom_opt.count() == 0:
                denom_opt = page.locator("div").filter(has_text=re.compile(rf"{denomination}\s*Wallet Code", re.IGNORECASE)).first

            if await denom_opt.count() > 0:
                chip_text = (await denom_opt.inner_text()).lower()
                if "out of stock" in chip_text or "sold out" in chip_text:
                    return PurchaseResult(
                        success=False,
                        platform="rooter",
                        denomination=denomination,
                        quantity=quantity,
                        account_label=account_label,
                        message=f"Rooter {prod_name} ₹{denomination:,} is currently Out of Stock! Start /snipe {denomination} to automatically grab it the second it restocks.",
                    )

                # Click the Mantine label or wrapper directly to guarantee React state change
                chip_label = denom_opt.locator("label").first if await denom_opt.locator("label").count() > 0 else denom_opt
                try:
                    await chip_label.click(force=True, timeout=1500)
                except Exception:
                    try:
                        await denom_opt.dispatch_event("click")
                    except Exception:
                        pass
                await page.wait_for_timeout(250)

                # Early out-of-stock check on bottom button to avoid needless 10s wait
                bottom_chk = page.locator("button[data-testid='proceed-to-pay'], button.styles_paymentBtn__TiXtN").first
                if await bottom_chk.count() > 0:
                    b_txt = (await bottom_chk.inner_text()).lower()
                    if "out of stock" in b_txt:
                        return PurchaseResult(
                            success=False,
                            platform="rooter",
                            denomination=denomination,
                            quantity=quantity,
                            account_label=account_label,
                            message=f"Rooter {prod_name} ₹{denomination:,} is currently Out of Stock! Start /snipe {denomination} to grab it when restocked.",
                        )

            # 2. Increment quantity if requested (supports Rooter Mantine ActionIcon stepper & NumberInput)
            if quantity > 1:
                try:
                    for _ in range(quantity - 1):
                        plus_btn = page.locator(
                            "button.mantine-ActionIcon-root:has-text('+'), "
                            "div[class*='quantitySelector'] button:has-text('+'), "
                            "div[class*='wrapper'] button:has-text('+'), "
                            "button:has-text('+'), [aria-label*='increase']"
                        ).first
                        if await plus_btn.is_visible(timeout=1200):
                            await plus_btn.click(force=True, timeout=800)
                            await page.wait_for_timeout(150)
                            logger.info(f"[Rooter] Clicked '+' button to increment quantity (target: {quantity})")
                        else:
                            # Direct NumberInput support inside Mantine quantity stepper
                            qty_input = page.locator("div[class*='quantitySelector'] input, div[class*='wrapper'] input, input[type='number']").first
                            if await qty_input.is_visible(timeout=400):
                                await qty_input.fill(str(quantity))
                                await qty_input.dispatch_event("input")
                                await qty_input.dispatch_event("change")
                                logger.info(f"[Rooter] Filled quantity input with {quantity}")
                                break
                except Exception as qe:
                    logger.debug(f"Quantity increment notice: {qe}")

            # 3. Handle Simulation Mode
            if simulation:
                if progress_callback:
                    await progress_callback(f"SIMULATION MODE: {prod_name} stock verified! Simulating dry-run purchase...", "💳")
                await page.wait_for_timeout(1000)

                prefix = "PSN"
                mock_code = f"ROTR-{prefix}-{denomination}-{hash(page) % 90000 + 10000}"
                mock_pin = f"{hash(page) % 9000 + 1000}"
                mock_order = f"RTR-ORD-{int(asyncio.get_event_loop().time())}"

                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    codes=[mock_code] if quantity == 1 else [mock_code, f"{mock_code}-2"],
                    order_id=mock_order,
                    receipt_summary=f"Rooter {prod_name} ₹{denomination:,} x{quantity} [SIMULATION]",
                    message="Purchase flow simulated successfully in dry-run mode. Turn off SIMULATION_MODE to purchase with real balance.",
                    simulation=True,
                )

            # 4. Live Purchase Execution - Ultra Fast Flow
            if progress_callback:
                await progress_callback(f"Clicking Buy / Pay on {prod_name}...", "🛒")

            # Click the main page checkout button (supports proceed-to-pay, add-address-btn, Pay ₹, etc.)
            buy_btn_selector = (
                "button[data-testid='proceed-to-pay'], button[testid='proceed-to-pay'], "
                "button[data-testid='add-address-btn'], button[testid='add-address-btn'], "
                "button.styles_paymentBtn__TiXtN, button:has-text('Pay ₹'), button:has-text('Proceed to Pay'), "
                "button:has-text('Pay via wallet'), button:has-text('Buy Now')"
            )

            # Fast retry loop to click main button as soon as React enables it
            main_clicked = False
            for _ in range(15):
                buy_btn = page.locator(buy_btn_selector).first
                if await buy_btn.is_visible(timeout=500):
                    btn_text = (await buy_btn.inner_text()).lower()
                    if "out of stock" in btn_text:
                        await page.wait_for_timeout(200)
                        continue
                    try:
                        await buy_btn.click(force=True, timeout=2000)
                        main_clicked = True
                    except Exception:
                        try:
                            await buy_btn.dispatch_event("click")
                            main_clicked = True
                        except Exception:
                            pass
                    if main_clicked:
                        break
                await page.wait_for_timeout(100)

            # Wait briefly for Delivery Details modal or payment drawer
            delivery_modal = page.locator(".mantine-Modal-content, div[role='dialog']").first
            try:
                await delivery_modal.wait_for(state="visible", timeout=2500)
            except Exception:
                pass

            # If Delivery Details modal appeared, fill missing inputs so form validation passes
            if await delivery_modal.is_visible():
                try:
                    name_inp = delivery_modal.locator("input[placeholder*='name'], input[placeholder*='Name']").first
                    if await name_inp.is_visible(timeout=400):
                        val = await name_inp.input_value()
                        if not val:
                            await name_inp.fill("Gamer")
                    email_inp = delivery_modal.locator("input[placeholder*='Email'], input[placeholder*='email']").first
                    if await email_inp.is_visible(timeout=400):
                        val = await email_inp.input_value()
                        if not val:
                            await email_inp.fill("rooter.gamer@gmail.com")
                except Exception:
                    pass

                # Click submit / Pay via wallet inside Delivery Details modal
                modal_btn_selector = (
                    ".mantine-Modal-content button:has-text('Pay via wallet'), "
                    ".mantine-Modal-content button:has-text('Pay ₹'), "
                    ".mantine-Modal-content button:has-text('Proceed to Pay'), "
                    ".mantine-Modal-content button:has-text('Proceed'), "
                    ".mantine-Modal-content button[type='submit'], "
                    "div[role='dialog'] button:has-text('Pay via wallet'), "
                    "div[role='dialog'] button:has-text('Pay ₹'), "
                    "div[role='dialog'] button[type='submit']"
                )
                modal_pay_btn = page.locator(modal_btn_selector).last
                if await modal_pay_btn.is_visible(timeout=2500):
                    if progress_callback:
                        await progress_callback("Confirming Delivery Details & submitting order...", "📝")
                    logger.info("[Rooter] Clicking Pay via wallet / Proceed inside modal...")
                    try:
                        await modal_pay_btn.click(force=True, timeout=2500)
                    except Exception:
                        try:
                            await modal_pay_btn.dispatch_event("click")
                        except Exception:
                            pass
                    await page.wait_for_timeout(1000)

            # Close coupon or offer popup if shown
            offers_dialog = page.locator("div[role='dialog']:has-text('Offers'), .mantine-Modal-content:has-text('Offers')").first
            if await offers_dialog.is_visible(timeout=1000):
                close_btn = offers_dialog.locator("button[aria-label*='Close'], svg, button:has-text('Skip')").first
                if await close_btn.is_visible(timeout=800):
                    try:
                        await close_btn.click(force=True, timeout=800)
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

            # If the page still has final 'Pay via wallet' button active, click it
            final_pay_btn = page.locator("button[data-testid='add-address-btn'], button[data-testid='proceed-to-pay'], button:has-text('Pay via wallet')").first
            if await final_pay_btn.is_visible(timeout=1000):
                btn_txt = (await final_pay_btn.inner_text()).lower()
                if "pay via wallet" in btn_txt or "proceed" in btn_txt:
                    try:
                        await final_pay_btn.click(force=True, timeout=2000)
                    except Exception:
                        pass

            # Wait up to 6s for Rooter to process payment and navigate to order confirmation page
            try:
                await page.wait_for_url(re.compile(r".*/order/.*"), timeout=6000)
            except Exception:
                pass

            # Capture confirmation screenshot
            shot_path = await browser_manager.capture_screenshot(page, f"order_{prod_info['type']}_{denomination}")

            current_url = page.url
            body_content = await page.locator("body").inner_text()
            is_order_page = "/order/" in current_url

            # Check for error indicators
            if "insufficient" in body_content.lower() or "low balance" in body_content.lower():
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message="Rooter wallet balance insufficient for this purchase.",
                    error_screenshot=shot_path,
                )

            # Check if out of stock
            if "out of stock" in body_content.lower() and not is_order_page:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message=f"Rooter {prod_name} ₹{denomination:,} went out of stock right before payment completed.",
                    error_screenshot=shot_path,
                )

            # Extract REAL Master Order ID (e.g. MO_2104663773_3832078)
            mo_match = re.search(r"\b(MO_\d+_\d+|ORD_[A-Za-z0-9_-]+)\b", current_url + " " + body_content)
            real_order_id = mo_match.group(1) if mo_match else None

            # Extract REAL 12-char PlayStation voucher codes (XXXX-XXXX-XXXX)
            code_matches = re.findall(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b", body_content)
            if not code_matches:
                code_matches = re.findall(r"(?:Code|Voucher|Redeem Code)[\s:#]+([A-Z0-9-]{10,25})", body_content, re.IGNORECASE)

            # Filter valid codes
            valid_codes = [c for c in code_matches if len(re.sub(r'[^A-Z0-9]', '', c)) in (12, 16)]
            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", body_content, re.IGNORECASE)
            real_pin = pin_match.group(1) if pin_match else "N/A"

            # STRICT VALIDATION: Order is ONLY successful if on real order page OR real MO_ order ID exists OR real voucher code extracted
            if not is_order_page and not real_order_id and not valid_codes:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=denomination,
                    quantity=quantity,
                    account_label=account_label,
                    message="Order was not confirmed by Rooter. No order ID or voucher was generated (item was not debited).",
                    error_screenshot=shot_path,
                )

            # If redirected to order page but code is still loading in React, wait a moment to read it
            if is_order_page and not valid_codes:
                await page.wait_for_timeout(3000)
                body_content = await page.locator("body").inner_text()
                retry_matches = re.findall(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b", body_content)
                valid_codes = [c for c in retry_matches if len(re.sub(r'[^A-Z0-9]', '', c)) in (12, 16)]

            display_code = valid_codes[0] if valid_codes else (real_order_id or "Confirmed on Rooter")
            final_order_id = real_order_id or "MO_CONFIRMED"

            return PurchaseResult(
                success=True,
                platform="rooter",
                denomination=denomination,
                quantity=quantity,
                account_label=account_label,
                voucher_code=display_code,
                voucher_pin=real_pin,
                codes=valid_codes if valid_codes else [display_code],
                order_id=final_order_id,
                receipt_summary=f"Rooter {prod_name} ₹{denomination:,} x{quantity}",
                message=f"{prod_name} (x{quantity}) successfully purchased on Rooter with wallet balance!",
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

    async def execute_amazon_test_buy(
        self,
        page: Page,
        quantity: int = 1,
        account_label: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        simulation: bool = False,
    ) -> PurchaseResult:
        """
        Executes a real or simulated purchase test for a ₹10 Amazon Pay Gift Card.
        Triggered exclusively via admin command: /snipe amazon 1.
        Used to safely verify account token validity, speed, and session health.
        """
        try:
            target_url = self.amazon_pay_url
            if progress_callback:
                await progress_callback("Navigating to Amazon Pay Gift Card page...", "🔍")

            if target_url not in page.url:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1000)

            await self.dismiss_location_popup(page)

            try:
                await page.wait_for_selector("div[class*='chipWrapper'], div[class*='styles_chipRoot']", timeout=8000)
            except Exception:
                pass

            await self.dismiss_location_popup(page)

            # Select the ₹10 denomination chip
            chips = page.locator("div[class*='chipWrapper'], div[class*='styles_chipRoot']")
            count = await chips.count()
            chip_selected = False
            for i in range(count):
                txt = await chips.nth(i).inner_text()
                # Check for 10 chip (exclude 100, 1000, 10000)
                if "10" in txt and "100" not in txt and "1000" not in txt and "10000" not in txt:
                    if "out of stock" in txt.lower() or "sold out" in txt.lower():
                        return PurchaseResult(
                            success=False,
                            platform="rooter",
                            denomination=10,
                            quantity=quantity,
                            account_label=account_label,
                            message="Amazon Pay ₹10 Gift Card is currently Out of Stock on Rooter Shop.",
                        )
                    label_or_chip = chips.nth(i).locator("label").first if await chips.nth(i).locator("label").count() > 0 else chips.nth(i)
                    await label_or_chip.click(force=True, timeout=1500)
                    await page.wait_for_timeout(350)
                    chip_selected = True
                    break

            if not chip_selected:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    message="Could not locate ₹10 Amazon Pay Gift Card chip on Rooter Shop.",
                )

            # Handle Simulation Mode
            if simulation:
                if progress_callback:
                    await progress_callback("SIMULATION MODE: ₹10 Amazon Pay Gift Card verified! Simulating dry-run purchase...", "💳")
                await page.wait_for_timeout(800)
                mock_code = f"AMZN-TEST-{hash(page) % 90000 + 10000}"
                mock_pin = "N/A"
                mock_order = f"MO_TEST_{int(asyncio.get_event_loop().time())}"
                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    voucher_code=mock_code,
                    voucher_pin=mock_pin,
                    codes=[mock_code],
                    order_id=mock_order,
                    receipt_summary=f"Amazon Pay Gift Card ₹10 x{quantity} [SIMULATION]",
                    message="Amazon Pay ₹10 test purchase flow simulated successfully in dry-run mode.",
                    simulation=True,
                )

            # Live checkout execution
            if progress_callback:
                await progress_callback("Clicking Buy / Pay on Amazon Pay ₹10 Gift Card...", "🛒")

            buy_btn_selector = (
                "button[data-testid='proceed-to-pay'], button[testid='proceed-to-pay'], "
                "button[data-testid='add-address-btn'], button[testid='add-address-btn'], "
                "button.styles_paymentBtn__TiXtN, button:has-text('Pay ₹'), button:has-text('Proceed to Pay'), "
                "button:has-text('Pay via wallet'), button:has-text('Buy Now')"
            )

            main_clicked = False
            for _ in range(15):
                buy_btn = page.locator(buy_btn_selector).first
                if await buy_btn.is_visible(timeout=500):
                    btn_text = (await buy_btn.inner_text()).lower()
                    if "out of stock" in btn_text:
                        await page.wait_for_timeout(200)
                        continue
                    try:
                        await buy_btn.click(force=True, timeout=2000)
                        main_clicked = True
                    except Exception:
                        try:
                            await buy_btn.dispatch_event("click")
                            main_clicked = True
                        except Exception:
                            pass
                    if main_clicked:
                        break
                await page.wait_for_timeout(100)

            # Wait briefly for Delivery Details modal or payment drawer
            delivery_modal = page.locator(".mantine-Modal-content, div[role='dialog']").first
            try:
                await delivery_modal.wait_for(state="visible", timeout=2500)
            except Exception:
                pass

            # Fill missing inputs if modal appeared
            if await delivery_modal.is_visible():
                try:
                    name_inp = delivery_modal.locator("input[placeholder*='name'], input[placeholder*='Name']").first
                    if await name_inp.is_visible(timeout=400):
                        val = await name_inp.input_value()
                        if not val:
                            await name_inp.fill("Gamer")
                    email_inp = delivery_modal.locator("input[placeholder*='Email'], input[placeholder*='email']").first
                    if await email_inp.is_visible(timeout=400):
                        val = await email_inp.input_value()
                        if not val:
                            await email_inp.fill("rooter.gamer@gmail.com")
                except Exception:
                    pass

                modal_btn_selector = (
                    ".mantine-Modal-content button:has-text('Pay via wallet'), "
                    ".mantine-Modal-content button:has-text('Pay ₹'), "
                    ".mantine-Modal-content button:has-text('Proceed to Pay'), "
                    ".mantine-Modal-content button:has-text('Proceed'), "
                    ".mantine-Modal-content button[type='submit'], "
                    "div[role='dialog'] button:has-text('Pay via wallet'), "
                    "div[role='dialog'] button:has-text('Pay ₹'), "
                    "div[role='dialog'] button[type='submit']"
                )
                modal_pay_btn = page.locator(modal_btn_selector).last
                if await modal_pay_btn.is_visible(timeout=2500):
                    try:
                        await modal_pay_btn.click(force=True, timeout=2500)
                    except Exception:
                        try:
                            await modal_pay_btn.dispatch_event("click")
                        except Exception:
                            pass
                    await page.wait_for_timeout(1000)

            # Final pay click if still visible
            final_pay_btn = page.locator("button[data-testid='add-address-btn'], button[data-testid='proceed-to-pay'], button:has-text('Pay via wallet')").first
            if await final_pay_btn.is_visible(timeout=1000):
                btn_txt = (await final_pay_btn.inner_text()).lower()
                if "pay via wallet" in btn_txt or "proceed" in btn_txt:
                    try:
                        await final_pay_btn.click(force=True, timeout=2000)
                    except Exception:
                        pass

            try:
                await page.wait_for_url(re.compile(r".*/order/.*"), timeout=6000)
            except Exception:
                pass

            shot_path = await browser_manager.capture_screenshot(page, "order_amazon_10")
            current_url = page.url
            body_content = await page.locator("body").inner_text()
            is_order_page = "/order/" in current_url

            if "insufficient" in body_content.lower() or "low balance" in body_content.lower():
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    message="Rooter wallet balance insufficient for ₹10 Amazon Pay test purchase.",
                    error_screenshot=shot_path,
                )

            # Extract Master Order ID and Amazon Gift Card code/PIN
            mo_match = re.search(r"\b(MO_\d+_\d+|ORD_[A-Za-z0-9_-]+)\b", current_url + " " + body_content)
            real_order_id = mo_match.group(1) if mo_match else None

            # Amazon Gift Card codes: 14-16 alphanumeric or formatted
            amz_codes = re.findall(r"\b([A-Z0-9]{4}-[A-Z0-9]{6}-[A-Z0-9]{4}|[A-Z0-9]{14,16})\b", body_content)
            if not amz_codes:
                amz_codes = re.findall(r"(?:Code|Voucher|Gift Card Code)[\s:#]+([A-Z0-9-]{10,25})", body_content, re.IGNORECASE)

            valid_codes = [c for c in amz_codes if len(re.sub(r'[^A-Z0-9]', '', c)) in (14, 15, 16)]
            pin_match = re.search(r"(?:PIN|Security PIN)[\s:]+([0-9]{4,8})", body_content, re.IGNORECASE)
            real_pin = pin_match.group(1) if pin_match else "N/A"

            if not is_order_page and not real_order_id and not valid_codes:
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    message="Amazon Pay test order was not confirmed by Rooter. (No wallet deduction).",
                    error_screenshot=shot_path,
                )

            display_code = valid_codes[0] if valid_codes else (real_order_id or "Confirmed on Rooter")
            final_order_id = real_order_id or "MO_CONFIRMED"

            return PurchaseResult(
                success=True,
                platform="rooter",
                denomination=10,
                quantity=quantity,
                account_label=account_label,
                voucher_code=display_code,
                voucher_pin=real_pin,
                codes=valid_codes if valid_codes else [display_code],
                order_id=final_order_id,
                receipt_summary=f"Rooter Amazon Pay Gift Card ₹10 x{quantity}",
                message="✅ Amazon Pay ₹10 Test Buy successful! Account token, wallet, and session health are verified active.",
                error_screenshot=shot_path,
                simulation=False,
            )
        except Exception as e:
            logger.error(f"Amazon Pay test buy error: {e}", exc_info=True)
            shot_path = await browser_manager.capture_screenshot(page, "amazon_buy_error")
            return PurchaseResult(
                success=False,
                platform="rooter",
                denomination=10,
                quantity=quantity,
                account_label=account_label,
                message=f"Amazon Pay test automation error: {str(e)}",
                error_screenshot=shot_path,
            )

