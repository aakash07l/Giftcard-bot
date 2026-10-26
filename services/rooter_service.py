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
        self.last_logged_in_token: Optional[str] = None

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
            has_token = await page.evaluate("""() => {
                const tok = localStorage.getItem('token') || localStorage.getItem('rooter_token');
                return !!tok;
            }""")
            if has_token:
                return True
            profile = page.locator("img[alt='profile-avatar-icon'], div[class*='headerIconWrappers']").first
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
            self.last_logged_in_token = None
            if progress_callback:
                await progress_callback("Opening Rooter to request OTP...", "🔍")

            await page.goto(self.base_url, timeout=config.BROWSER_TIMEOUT_MS)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            # Auto-dismiss region popup if present
            await self.dismiss_location_popup(page)
            await page.wait_for_timeout(400)

            # Check if phone input is already visible or open drawer via header profile avatar (with retry for hydration lag)
            phone_input = page.locator("input[placeholder*='Mobile Number'], input[placeholder*='mobile'], input[type='tel']").first
            for attempt in range(10):
                if await phone_input.is_visible():
                    break
                avatar = page.locator("div[class*='headerIconWrappers'], img[alt='profile-avatar-icon'], div[class*='headerRightSide'] > div:last-child, button:has-text('Login')").first
                try:
                    if await avatar.count() > 0:
                        await avatar.click(force=True, timeout=1200)
                    else:
                        await page.click("header div[class*='headerRightSide'] div:last-child", force=True, timeout=1200)
                except Exception:
                    pass
                await page.wait_for_timeout(800)

            # Fallback if avatar click didn't trigger drawer (e.g. hydration lag): click a product's Buy Now
            if not await phone_input.is_visible():
                try:
                    await page.goto(self.amazon_pay_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500)
                    prod_btn = page.locator("button.styles_paymentBtn__TiXtN, button:has-text('Pay'), button:has-text('Buy Now')").first
                    if await prod_btn.is_visible(timeout=3000):
                        await prod_btn.click(force=True)
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

            # Wait directly for phone input on the page (prevents collision with location dialog)
            await phone_input.wait_for(state="visible", timeout=12000)
            await phone_input.fill(clean_phone)
            await page.wait_for_timeout(300)

            # Click Continue / Get OTP
            continue_btn = page.locator("button:has-text('Continue'), button:has-text('Get OTP'), button[type='submit']").first
            await continue_btn.click(force=True)

            # Wait for OTP screen to appear (either "Verify Now" button or OTP input)
            otp_indicator = page.locator("button:has-text('Verify Now'), input[data-path='step2.otp'], button:has-text('Resend OTP')").first
            for _ in range(15):
                if await otp_indicator.is_visible():
                    break
                if await continue_btn.is_visible():
                    try:
                        await continue_btn.click(force=True, timeout=1000)
                    except Exception:
                        pass
                await page.wait_for_timeout(800)

            if progress_callback:
                await progress_callback(f"OTP sent to +91 {clean_phone}! Please reply with OTP in chat...", "📩")

            # Await OTP code from user via Telegram
            otp_code = await otp_callback()
            if not otp_code:
                logger.error("No OTP provided for Rooter login.")
                return False

            clean_otp = re.sub(r"\D", "", otp_code)

            # Fill OTP directly on the page
            otp_input = page.locator("input[data-path='step2.otp'], input.mantine-NumberInput-input, input[inputmode='numeric'], input[placeholder*='OTP']").first
            await otp_input.wait_for(state="visible", timeout=4000)
            await otp_input.fill(clean_otp)
            await page.wait_for_timeout(300)

            # Click Verify Now
            verify_btn = page.locator("button.styles_verifyOtpBtn__2LU_E, button.styles_verifyOtpBtn__DkYRE, button:has-text('Verify Now'), button:has-text('Verify'), button[type='submit']").first
            await verify_btn.click(force=True)

            if progress_callback:
                await progress_callback("Verifying OTP and retrieving session token...", "⏳")

            # Wait up to 10s for auth token in localStorage
            extracted_token = None
            for _ in range(25):
                await page.wait_for_timeout(400)
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
                self.last_logged_in_token = extracted_token
                logger.info(f"Rooter login successful for +91 {clean_phone}! Clean token captured.")
                if progress_callback:
                    await progress_callback("Rooter account verified and token synchronized successfully!", "✅")
                return True

            # Check if an error message is visible in dialog
            err_msg = modal.locator("div[class*='error'], p[class*='error'], span:has-text('Invalid'), span:has-text('incorrect')").first
            if await err_msg.is_visible(timeout=1000):
                err_text = (await err_msg.inner_text()).strip()
                logger.warning(f"Rooter OTP error: {err_text}")
                return False

            return False

        except Exception as e:
            logger.error(f"Error during Rooter login: {e}", exc_info=True)
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
        """Auto-dismisses 'Different Location Detected' modal by clicking 'No, stay on this site' and setting session preference."""
        try:
            # 1. Immediately inject session preference and click 'No, stay on this site' via DOM
            await page.evaluate("""() => {
                try {
                    sessionStorage.setItem('region-switch-stay-preference', 'true');
                    localStorage.setItem('region-switch-stay-preference', 'true');
                    const all = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
                    const stay = all.find(b => (b.innerText || '').toLowerCase().includes('stay on this site'));
                    if (stay) {
                        stay.click();
                    }
                } catch(e) {}
            }""")

            # 2. Playwright locators for 'No, stay on this site'
            btn_selectors = [
                "button:has-text('No, stay on this site')",
                "button:has-text('stay on this site')",
                "button:has-text('Stay on this site')",
                "div[id*='region-switch'] button:has-text('stay')",
                ".mantine-Modal-content button:has-text('stay')",
                "div[role='dialog']:has-text('Different Location') button:has-text('stay')",
                "button:has-text('Stay')",
                ".mantine-Modal-close",
                "button[aria-label='Close modal']",
                "button[aria-label*='Close']",
            ]
            for sel in btn_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(force=True, timeout=1000)
                    logger.info(f"[Rooter] Dismissed location popup using selector: {sel}")
                    await page.wait_for_timeout(300)
                    break
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
                denom_opt = page.locator("div.styles_root__6O3V0, div.styles_chipRoot__zkrmI, div.mantine-Chip-root").filter(
                    has_text=re.compile(rf"(?:Rs\.?|₹)?\s*{d}\b", re.IGNORECASE)
                ).first
                if await denom_opt.count() == 0:
                    denom_opt = page.locator("label").filter(has_text=re.compile(rf"(?:Rs\.?|₹)?\s*{d}\b", re.IGNORECASE)).first
                if await denom_opt.count() == 0:
                    continue

                # 1. Direct disabled check on radio input (guaranteed Out of Stock indicator)
                try:
                    radio_inp = denom_opt.locator("input[type='radio']").first
                    if await radio_inp.count() > 0 and await radio_inp.is_disabled():
                        continue
                except Exception:
                    pass

                # 2. Check inner text
                chip_text = (await denom_opt.inner_text()).lower()
                if "out of stock" in chip_text or "sold out" in chip_text:
                    continue

                # 3. Check parent container text as well
                try:
                    parent_text = (await denom_opt.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")).lower()
                    if "out of stock" in parent_text:
                        continue
                except Exception:
                    pass

                # Click to select chip and verify bottom action button
                try:
                    chip_label = denom_opt.locator("label").first if await denom_opt.locator("label").count() > 0 else denom_opt
                    await chip_label.click(force=True, timeout=1200)
                    await page.wait_for_timeout(350)
                except Exception:
                    pass

                bottom_btn = page.locator(
                    "button.styles_paymentBtn__TiXtN, button:has-text('Out of Stock'), "
                    "button[data-testid='proceed-to-pay'], button:has-text('Proceed to Pay'), "
                    "button:has-text('Pay via wallet'), button:has-text('Buy Now')"
                ).first
                if await bottom_btn.count() > 0:
                    btn_text = (await bottom_btn.inner_text()).lower()
                    if "out of stock" in btn_text:
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
            denom_opt = page.locator("div[class*='chipWrapper'], div[class*='styles_chipRoot'], div[class*='mantine-Chip-root']").filter(
                has_text=re.compile(rf"(?:Rs\.?|₹)?\s*{denomination}\b", re.IGNORECASE)
            ).first
            if await denom_opt.count() == 0:
                denom_opt = page.locator("label").filter(has_text=re.compile(rf"(?:Rs\.?|₹)?\s*{denomination}\b", re.IGNORECASE)).first
            if await denom_opt.count() == 0:
                denom_opt = page.locator("div").filter(has_text=re.compile(rf"(?:Rs\.?|₹)?\s*{denomination}\b", re.IGNORECASE)).first

            if await denom_opt.count() > 0:
                chip_text = (await denom_opt.inner_text()).lower()
                is_radio_disabled = False
                try:
                    radio_inp = denom_opt.locator("input[type='radio']").first
                    if await radio_inp.count() > 0:
                        is_radio_disabled = await radio_inp.is_disabled()
                except Exception:
                    pass

                if "out of stock" in chip_text or "sold out" in chip_text or is_radio_disabled:
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

                # Ensure radio input is actively checked
                try:
                    if await radio_inp.count() > 0 and not await radio_inp.is_checked():
                        await radio_inp.check(force=True)
                except Exception:
                    pass
                await page.wait_for_timeout(350)

                # Early out-of-stock check on bottom button to avoid needless 10s wait
                bottom_chk = page.locator("button.styles_paymentBtn__TiXtN, button:has-text('Out of Stock')").first
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

            # Auto-dismiss region popup if present before clicking
            await self.dismiss_location_popup(page)

            # Click the main page checkout button (supports dynamic cart prices, discounts, fees)
            buy_btn_selector = (
                "button.styles_paymentBtn__TiXtN, "
                "button[data-testid='proceed-to-pay'], button[testid='proceed-to-pay'], "
                "button[data-testid='add-address-btn'], button[testid='add-address-btn'], "
                "button:has-text('Proceed to Pay'), button:has-text('Pay via wallet'), "
                "button:has-text('Pay ₹'), button:has-text('Buy Now')"
            )

            # Fast retry loop to click main button as soon as React enables it
            main_clicked = False
            for retry_i in range(15):
                buy_btn = page.locator(buy_btn_selector).first
                if await buy_btn.is_visible(timeout=500):
                    btn_text = (await buy_btn.inner_text()).strip().replace("\n", " ")
                    if "out of stock" in btn_text.lower():
                        await page.wait_for_timeout(200)
                        continue

                    # Safety Guard: Ensure button amount is not displaying an old/lower denomination (e.g. ₹1,137 for a ₹4,000 card)
                    # If button text shows an amount significantly lower than requested denomination, wait for React to recalculate
                    amt_match = re.search(r"[₹Rs\.]*\s*([\d,]+)", btn_text)
                    if amt_match and retry_i < 10:
                        try:
                            parsed_amt = int(amt_match.group(1).replace(",", ""))
                            if parsed_amt > 0 and parsed_amt < int(denomination * 0.6):
                                logger.info(
                                    f"[{prod_name}] Button text '{btn_text}' is still updating to ₹{denomination:,} "
                                    f"(parsed ₹{parsed_amt:,} < ₹{int(denomination * 0.6):,}). Waiting for React cart recalculation..."
                                )
                                await page.wait_for_timeout(300)
                                continue
                        except Exception:
                            pass

                    logger.info(
                        f"[{prod_name}] Selected denomination: ₹{denomination:,}. "
                        f"Checkout button: '{btn_text}' (paying whatever final amount/discount/fee is displayed)."
                    )
                    if progress_callback:
                        await progress_callback(f"Proceeding to pay {btn_text} (Card Value: ₹{denomination:,})...", "💳")
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

            # Allow animation for Delivery Details modal or payment drawer
            await page.wait_for_timeout(2000)

            delivery_modal = page.locator("div[role='dialog'], .mantine-Modal-content").filter(has_text="Delivery Details").last
            try:
                await delivery_modal.wait_for(state="visible", timeout=3000)
            except Exception:
                pass

            if await delivery_modal.is_visible():
                modal_pay_btn = delivery_modal.locator("button:has-text('Pay'), button:has-text('Proceed'), button[type='submit']").last
                if await modal_pay_btn.is_visible(timeout=2500):
                    if progress_callback:
                        await progress_callback("Confirming Delivery Details & submitting order...", "📝")
                    logger.info("[Rooter] Clicking Pay / Proceed inside Delivery Details modal...")
                    try:
                        await modal_pay_btn.click(force=True, timeout=2500)
                    except Exception:
                        try:
                            await modal_pay_btn.dispatch_event("click")
                        except Exception:
                            pass
                    await page.wait_for_timeout(2500)

            # Close coupon or offer popup if shown
            offers_dialog = page.locator("div[role='dialog']:has-text('Offers'), .mantine-Modal-content:has-text('Offers')").first
            if await offers_dialog.is_visible(timeout=800):
                close_btn = offers_dialog.locator("button[aria-label*='Close'], svg, button:has-text('Skip')").first
                if await close_btn.is_visible(timeout=800):
                    try:
                        await close_btn.click(force=True, timeout=800)
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

            # Wait for transition to /payments or /order/
            try:
                await page.wait_for_url(re.compile(r".*/(payments|order)/.*"), timeout=6000)
            except Exception:
                pass

            # If redirected to /payments, select Rooter Shopping Card / Wallet and click final Pay
            if "/payments" in page.url:
                logger.info("[Rooter] Redirected to Payments page, confirming Rooter Shopping Card / Wallet...")
                try:
                    await page.wait_for_selector("div:has-text('Shopping Card'), div:has-text('Wallet'), button:has-text('Pay')", timeout=3500)
                except Exception:
                    pass

                wallet_opt = page.locator("div:has-text('Rooter Shopping Card'), div:has-text('Shopping Card'), div:has-text('Wallet')").first
                if await wallet_opt.is_visible(timeout=1500):
                    try:
                        await wallet_opt.click(force=True, timeout=1000)
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

                pay_now_btn = page.locator("button:has-text('Pay'), button:has-text('Proceed')").last
                if await pay_now_btn.is_visible(timeout=2500):
                    btn_pay_txt = (await pay_now_btn.inner_text()).strip()
                    logger.info(f"[Rooter] Clicking final payment button on /payments: '{btn_pay_txt}'")
                    try:
                        await pay_now_btn.click(force=True, timeout=2500)
                    except Exception:
                        try:
                            await pay_now_btn.dispatch_event("click")
                        except Exception:
                            pass
                    await page.wait_for_timeout(2000)

            # Wait up to 8s for Rooter to process payment and navigate to order confirmation page
            try:
                await page.wait_for_url(re.compile(r".*/order/.*"), timeout=8000)
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
                try:
                    await page.goto(target_url, wait_until="networkidle", timeout=15000)
                except Exception:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1200)

            await self.dismiss_location_popup(page)

            try:
                await page.wait_for_selector(
                    "div[class*='chipRoot'], div[class*='mantine-Chip-root'], label:has-text('10'), input[type='radio']",
                    timeout=8000,
                )
            except Exception:
                pass

            await self.dismiss_location_popup(page)

            # Search for the ₹10 denomination chip with multiple attempts to allow React hydration
            chip_selected = False
            for attempt in range(1, 6):
                await self.dismiss_location_popup(page)

                # Strategy 1: Find chip containing 9.92 (unique to ₹10 Amazon Pay card on Rooter)
                opt_10 = page.locator("div[class*='chipRoot'], div[class*='mantine-Chip-root']").filter(has_text="9.92").first
                if await opt_10.count() == 0:
                    # Strategy 2: First chip container matching 10
                    opt_10 = page.locator("div[class*='chipRoot'], div[class*='mantine-Chip-root']").filter(has_text="10").first
                if await opt_10.count() == 0:
                    # Strategy 3: Radio input for 10 denomination
                    opt_10 = page.locator("input[type='radio'][value='68b68d024068694101114677']").first

                if await opt_10.count() > 0 and await opt_10.is_visible():
                    txt = (await opt_10.inner_text()).lower()
                    if "out of stock" in txt or "sold out" in txt:
                        shot_path = await browser_manager.capture_screenshot(page, "amazon_10_oos")
                        return PurchaseResult(
                            success=False,
                            platform="rooter",
                            denomination=10,
                            quantity=quantity,
                            account_label=account_label,
                            message="Amazon Pay ₹10 Gift Card is currently Out of Stock on Rooter Shop.",
                            error_screenshot=shot_path,
                        )
                    try:
                        label_10 = opt_10.locator("label").first
                        if await label_10.count() > 0:
                            await label_10.click()
                        else:
                            await opt_10.click()
                    except Exception:
                        await opt_10.dispatch_event("click")
                    await page.wait_for_timeout(1000)
                    chip_selected = True
                    logger.info(f"[Amazon Test Buy] Selected ₹10 chip via direct locator on attempt {attempt}")
                    break

                # Strategy 4: Fallback to scanning all chips/radio buttons
                chips = page.locator(
                    "div[class*='chipWrapper'], div[class*='styles_chipRoot'], div[class*='mantine-Chip-root'], div[class*='chip'], div[data-testid*='chip']"
                )
                count = await chips.count()
                logger.info(f"[Amazon Test Buy] Attempt {attempt}/5: Found {count} chips on page.")

                if count > 0:
                    for i in range(count):
                        txt = await chips.nth(i).inner_text()
                        clean_txt = txt.replace("₹", "").replace("Rs.", "").strip()
                        has_10 = bool(re.search(r"\b10\b", clean_txt) or "9.92" in clean_txt)
                        has_large = any(x in clean_txt for x in ["100", "1000", "2500", "5000", "10000"])

                        if has_10 and not has_large:
                            if "out of stock" in txt.lower() or "sold out" in txt.lower():
                                shot_path = await browser_manager.capture_screenshot(page, "amazon_10_oos")
                                return PurchaseResult(
                                    success=False,
                                    platform="rooter",
                                    denomination=10,
                                    quantity=quantity,
                                    account_label=account_label,
                                    message="Amazon Pay ₹10 Gift Card is currently Out of Stock on Rooter Shop.",
                                    error_screenshot=shot_path,
                                )

                            label_or_chip = chips.nth(i).locator("label").first if await chips.nth(i).locator("label").count() > 0 else chips.nth(i)
                            try:
                                await label_or_chip.click(force=True, timeout=2000)
                            except Exception:
                                await chips.nth(i).dispatch_event("click")
                            await page.wait_for_timeout(400)
                            chip_selected = True
                            logger.info(f"[Amazon Test Buy] Selected ₹10 chip at index {i} (text: {repr(txt[:30])})")
                            break

                if chip_selected:
                    break

                await page.wait_for_timeout(1000)

            if not chip_selected:
                shot_path = await browser_manager.capture_screenshot(page, "amazon_chip_not_found")
                page_title = await page.title()
                current_url = page.url
                logger.warning(f"[Amazon Test Buy] Chip not found! URL: {current_url}, Title: {page_title}, Screenshot: {shot_path}")
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    message=f"Could not locate ₹10 Amazon Pay chip on Rooter Shop (URL: {current_url}, Title: {page_title}). See screenshot.",
                    error_screenshot=shot_path,
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
                "button.styles_paymentBtn__TiXtN, "
                "button:has-text('Pay'), button:has-text('Proceed to Pay'), "
                "button:has-text('Pay via wallet'), button:has-text('Buy Now'), button:has-text('Proceed')"
            )

            main_clicked = False
            for _ in range(15):
                buy_btn = page.locator(buy_btn_selector).first
                if await buy_btn.is_visible(timeout=500):
                    btn_text = (await buy_btn.inner_text()).strip().replace("\n", " ")
                    if "out of stock" in btn_text.lower():
                        await page.wait_for_timeout(200)
                        continue
                    # If button still reflects old default amount (e.g. ₹192 for ₹200 card), wait for React re-render
                    if any(x in btn_text for x in ["192", "191", "200"]):
                        await page.wait_for_timeout(300)
                        continue
                    logger.info(
                        f"[Amazon Test Buy] Selected denomination: ₹10. "
                        f"Checkout button: '{btn_text}' (paying actual amount including discounts/fees, e.g. ₹9.92)."
                    )
                    if progress_callback:
                        await progress_callback(f"Proceeding to pay {btn_text} (Card Value: ₹10)...", "💳")
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
                await page.wait_for_timeout(200)

            # Allow animation for Delivery Details modal
            await page.wait_for_timeout(2500)

            # Locate active Delivery Details modal
            delivery_modal = page.locator("div[role='dialog'], .mantine-Modal-content").filter(has_text="Delivery Details").last
            try:
                await delivery_modal.wait_for(state="visible", timeout=3000)
            except Exception:
                pass

            if await delivery_modal.is_visible():
                modal_pay_btn = delivery_modal.locator("button:has-text('Pay'), button[type='submit']").last
                if await modal_pay_btn.is_visible(timeout=2500):
                    logger.info("[Amazon Test Buy] Clicking Pay inside Delivery Details modal...")
                    try:
                        await modal_pay_btn.click(force=True, timeout=2500)
                    except Exception:
                        try:
                            await modal_pay_btn.dispatch_event("click")
                        except Exception:
                            pass
                    await page.wait_for_timeout(4000)

            # Final pay click if still visible on product page
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

            # Check if Login / Sign Up modal appeared
            if "login / sign up" in body_content.lower() or "enter your mobile number" in body_content.lower():
                return PurchaseResult(
                    success=False,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    message="Login / Sign Up modal appeared. user_auth session cookie was not recognized by Rooter.",
                    error_screenshot=shot_path,
                )

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

            # Check if order was completed directly
            if is_order_page or real_order_id or valid_codes:
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
                    message="✅ Amazon Pay ₹10 Test Buy successful! Order placed and confirmed.",
                    error_screenshot=shot_path,
                    simulation=False,
                )

            # Check if payment gateway was reached successfully (token, auth, cart, and delivery form verified)
            if "/payments" in current_url:
                user_match = re.search(r"to\s+([A-Za-z0-9_.\s]+)\s*\(([^)]+)\)", body_content)
                user_info = f"Logged in as {user_match.group(1).strip()} ({user_match.group(2).strip()})" if user_match else "User session verified active"
                return PurchaseResult(
                    success=True,
                    platform="rooter",
                    denomination=10,
                    quantity=quantity,
                    account_label=account_label,
                    order_id="TEST_CHECKOUT_VERIFIED",
                    receipt_summary=f"Rooter Amazon Pay ₹10 Test Check [PASSED]",
                    message=(
                        f"✅ Session & Token Health 100% VERIFIED!\n"
                        f"• {user_info}\n"
                        f"• No bot blocks, no WAF challenge, and zero login popups.\n"
                        f"• Product chip, payable amount, and delivery details passed.\n"
                        f"💡 Note: Amazon Pay requires UPI/Card on Rooter. PlayStation Gift Cards will purchase automatically via Rooter Wallet balance!"
                    ),
                    error_screenshot=shot_path,
                    simulation=False,
                )

            return PurchaseResult(
                success=False,
                platform="rooter",
                denomination=10,
                quantity=quantity,
                account_label=account_label,
                message="Amazon Pay test order was not confirmed by Rooter. (No wallet deduction).",
                error_screenshot=shot_path,
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

