"""Shared types + base class for platform watchers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventKind = Literal["live", "upload"]


@dataclass
class Event:
    platform: str           # "youtube" | "twitch" | "kick" | "x"
    kind: EventKind         # "live" | "upload"
    creator: str            # display name / handle
    title: str
    url: str
    thumbnail: str | None = None
    duration_seconds: int | None = None  # for uploads
    mentions_hit: list[str] | None = None  # names from the mention watchlist found in title

    @property
    def event_id(self) -> str:
        return f"{self.platform}:{self.kind}:{self.url}"

    def format_message(self) -> str:
        icon = "🔴 LIVE" if self.kind == "live" else "🎬 NEW UPLOAD"
        platform_label = self.platform.capitalize()
        lines = []
        if self.mentions_hit:
            lines.append(f"👀 <b>Mentions:</b> {', '.join(self.mentions_hit)}")
        lines.append(f"{icon} · {platform_label}")
        lines.append(f"<b>{self.creator}</b> — {self.title}")
        if self.kind == "upload" and self.duration_seconds:
            mins = self.duration_seconds // 60
            lines.append(f"Length: {mins} min")
        lines.append(self.url)
        return "\n".join(lines)


class Platform:
    """Each watcher polls its platform and yields new Events."""

    name: str = ""

    async def poll(self, handles: list[str]) -> list[Event]:
        raise NotImplementedError
