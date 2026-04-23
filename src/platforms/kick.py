"""Kick watcher — polls the public channel endpoint (no official API)."""
from __future__ import annotations

import httpx

from .base import Event, Platform

KICK_API = "https://kick.com/api/v2/channels"


class KickWatcher(Platform):
    name = "kick"

    async def poll(self, handles: list[str]) -> list[Event]:
        if not handles:
            return []
        events: list[Event] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (clip-notifier)",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for slug in handles:
                try:
                    r = await client.get(f"{KICK_API}/{slug.lower()}")
                    if r.status_code != 200:
                        continue
                    data = r.json()
                except Exception:
                    continue
                livestream = data.get("livestream")
                if not livestream:
                    continue
                events.append(
                    Event(
                        platform="kick",
                        kind="live",
                        creator=data.get("user", {}).get("username", slug),
                        title=livestream.get("session_title", ""),
                        url=f"https://kick.com/{slug.lower()}",
                        thumbnail=(livestream.get("thumbnail") or {}).get("url"),
                    )
                )
        return events
