"""Send messages to the Telegram user."""
from __future__ import annotations

import logging

from telegram import Bot
from telegram.constants import ParseMode

from .platforms.base import Event

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, user_id: int) -> None:
        self.bot = bot
        self.user_id = user_id
        self.muted_until: float = 0.0

    def mute_for(self, seconds: int) -> None:
        import time
        self.muted_until = time.time() + seconds

    async def send_event(self, event: Event) -> None:
        import time
        if time.time() < self.muted_until:
            log.info("muted, skipping %s", event.event_id)
            return
        text = event.format_message()
        try:
            await self.bot.send_message(
                chat_id=self.user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
        except Exception as e:
            log.exception("Failed to send notification: %s", e)

    async def send_text(self, text: str) -> None:
        await self.bot.send_message(chat_id=self.user_id, text=text, parse_mode=ParseMode.HTML)
