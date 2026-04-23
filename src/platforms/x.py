"""X / Twitter watcher — best-effort via snscrape."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

from .base import Event, Platform

LIVE_PATTERNS = [
    re.compile(r"twitter\.com/i/spaces/", re.I),
    re.compile(r"x\.com/i/spaces/", re.I),
    re.compile(r"\blive now\b", re.I),
    re.compile(r"\bjoin me live\b", re.I),
    re.compile(r"\bstreaming now\b", re.I),
    re.compile(r"\bgoing live\b", re.I),
]


def _looks_live(text: str) -> bool:
    return any(p.search(text) for p in LIVE_PATTERNS)


class XWatcher(Platform):
    name = "x"

    def __init__(self, lookback_minutes: int = 15) -> None:
        self.lookback = timedelta(minutes=lookback_minutes)

    def _scrape_sync(self, handle: str, since: datetime) -> list[tuple[str, str, str]]:
        try:
            import snscrape.modules.twitter as sntwitter  # type: ignore
        except Exception:
            return []
        out: list[tuple[str, str, str]] = []
        try:
            scraper = sntwitter.TwitterUserScraper(handle)
            for i, tweet in enumerate(scraper.get_items()):
                if i > 20:
                    break
                if tweet.date < since:
                    break
                content = tweet.rawContent or ""
                if _looks_live(content):
                    out.append((str(tweet.id), content, f"https://x.com/{handle}/status/{tweet.id}"))
        except Exception:
            return []
        return out

    async def poll(self, handles: list[str]) -> list[Event]:
        if not handles:
            return []
        since = datetime.now(timezone.utc) - self.lookback
        events: list[Event] = []
        loop = asyncio.get_running_loop()
        for handle in handles:
            clean = handle.lstrip("@")
            hits = await loop.run_in_executor(None, self._scrape_sync, clean, since)
            for tid, content, url in hits:
                events.append(
                    Event(
                        platform="x",
                        kind="live",
                        creator=f"@{clean}",
                        title=content[:140],
                        url=url,
                    )
                )
        return events
