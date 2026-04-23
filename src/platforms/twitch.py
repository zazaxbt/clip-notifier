"""Twitch watcher using Helix API with app access token."""
from __future__ import annotations

import time

import httpx

from .base import Event, Platform

HELIX = "https://api.twitch.tv/helix"
OAUTH = "https://id.twitch.tv/oauth2/token"


class TwitchWatcher(Platform):
    name = "twitch"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expires: float = 0.0

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        r = await client.post(
            OAUTH,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._token

    async def poll(self, handles: list[str]) -> list[Event]:
        if not self.client_id or not self.client_secret or not handles:
            return []

        logins = [h.lower() for h in handles]
        async with httpx.AsyncClient(timeout=20) as client:
            token = await self._get_token(client)
            headers = {"Client-Id": self.client_id, "Authorization": f"Bearer {token}"}

            events: list[Event] = []
            for i in range(0, len(logins), 100):
                chunk = logins[i : i + 100]
                params = [("user_login", lg) for lg in chunk] + [("first", str(len(chunk)))]
                r = await client.get(f"{HELIX}/streams", headers=headers, params=params)
                r.raise_for_status()
                for s in r.json().get("data", []):
                    login = s.get("user_login", "").lower()
                    events.append(
                        Event(
                            platform="twitch",
                            kind="live",
                            creator=s.get("user_name", login),
                            title=s.get("title", ""),
                            url=f"https://twitch.tv/{login}",
                            thumbnail=(s.get("thumbnail_url") or "").replace("{width}", "1280").replace("{height}", "720") or None,
                        )
                    )
        return events
