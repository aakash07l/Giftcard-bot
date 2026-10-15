"""
States for Telegram ConversationHandler flows.
"""

from enum import IntEnum, auto

class BotState(IntEnum):
    # Main menu & navigation
    MAIN_MENU = auto()

    # Login flow
    SELECT_LOGIN_PLATFORM = auto()
    SELECT_LOGIN_METHOD = auto()
    AWAITING_PHONE = auto()
    AWAITING_OTP = auto()
    AWAITING_COOKIE_DATA = auto()

    # Buying flow
    SELECT_BUY_PLATFORM = auto()
    SELECT_BUY_DENOMINATION = auto()
    AWAITING_CONFIRMATION = auto()
