"""
Abstract base class and data structures for platform automation scrapers.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, Dict, Any, List
from pydantic import BaseModel, Field

class CardItem(BaseModel):
    title: str
    denomination: int
    price: float
    platform: str
    in_stock: bool = True
    url: Optional[str] = None
    selector_ref: Optional[str] = None

class PurchaseResult(BaseModel):
    success: bool
    platform: str
    denomination: int
    voucher_code: Optional[str] = None
    voucher_pin: Optional[str] = None
    order_id: Optional[str] = None
    receipt_summary: Optional[str] = None
    message: str = ""
    error_screenshot: Optional[str] = None
    simulation: bool = False

# Type alias for live progress callback to Telegram
# progress_callback(status_text: str, emoji: str)
ProgressCallback = Callable[[str, str], Awaitable[None]]

class BasePlatform(ABC):
    """Abstract interface that each platform scraper (Blinkit, Rooter) implements."""

    def __init__(self, platform_id: str, name: str, base_url: str):
        self.platform_id = platform_id
        self.name = name
        self.base_url = base_url

    @abstractmethod
    async def check_login_status(self, page) -> bool:
        """Verify whether the current browser context is authenticated."""
        pass

    @abstractmethod
    async def perform_login(
        self,
        page,
        phone_number: str,
        otp_callback: Callable[[], Awaitable[str]],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Interactive OTP login flow."""
        pass

    @abstractmethod
    async def search_playstation_cards(
        self,
        page,
        denomination: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[CardItem]:
        """Search and filter available PlayStation gift cards."""
        pass

    @abstractmethod
    async def execute_buy_flow(
        self,
        page,
        denomination: int,
        progress_callback: Optional[ProgressCallback] = None,
        simulation: bool = False,
    ) -> PurchaseResult:
        """Complete the purchase flow from search to cart, payment, and voucher extraction."""
        pass
