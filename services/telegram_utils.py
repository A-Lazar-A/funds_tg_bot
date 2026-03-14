import asyncio
import logging
from typing import Any

from telegram import Message
from telegram.error import NetworkError, RetryAfter, TimedOut


logger = logging.getLogger(__name__)

SEND_RETRY_ATTEMPTS = 2
SEND_RETRY_DELAY_SECONDS = 1


async def safe_reply_text(message: Message, text: str, **kwargs: Any):
    """Send a Telegram message with a small retry budget for transient errors."""
    for attempt in range(1, SEND_RETRY_ATTEMPTS + 1):
        try:
            return await message.reply_text(text, **kwargs)
        except RetryAfter as exc:
            if attempt == SEND_RETRY_ATTEMPTS:
                raise
            wait_seconds = max(int(exc.retry_after), SEND_RETRY_DELAY_SECONDS)
            logger.warning(
                "Telegram requested retry after %s seconds while sending reply",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
        except (TimedOut, NetworkError):
            if attempt == SEND_RETRY_ATTEMPTS:
                raise
            logger.warning(
                "Transient Telegram send failure on attempt %s/%s",
                attempt,
                SEND_RETRY_ATTEMPTS,
                exc_info=True,
            )
            await asyncio.sleep(SEND_RETRY_DELAY_SECONDS)


async def safe_edit_text(message: Message, text: str, **kwargs: Any):
    """Edit a Telegram message with retry for transient API failures."""
    for attempt in range(1, SEND_RETRY_ATTEMPTS + 1):
        try:
            return await message.edit_text(text, **kwargs)
        except RetryAfter as exc:
            if attempt == SEND_RETRY_ATTEMPTS:
                raise
            wait_seconds = max(int(exc.retry_after), SEND_RETRY_DELAY_SECONDS)
            logger.warning(
                "Telegram requested retry after %s seconds while editing message",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
        except (TimedOut, NetworkError):
            if attempt == SEND_RETRY_ATTEMPTS:
                raise
            logger.warning(
                "Transient Telegram edit failure on attempt %s/%s",
                attempt,
                SEND_RETRY_ATTEMPTS,
                exc_info=True,
            )
            await asyncio.sleep(SEND_RETRY_DELAY_SECONDS)
