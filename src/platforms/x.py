"""X / Twitter watcher — Space detection via Nitter RSS (no auth, no API key).

How it works:
  - For each handle, fetch https://<nitter>/<handle>/rss (rotates across public
    instances on failure).
  - Parse the RSS; for each recent item, scan title + description for an
    /i/spaces/<id> URL. That's the only signal we trust — we deliberately do
    NOT match "live now"/"join me" text because it misses most Spaces and
    produces false positives.
  - Dedup Space IDs in-memory within the watcher instance; SQLite dedups at the
    notifier level too.

Caveats:
  - Nitter instances come and go. Keep NITTER_INSTANCES fresh.
  - Only detects Spaces the user tweets about. Silent Spaces (hosted without a
    tweet) are invisible — same limitation as any public-web approach.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

from .base import Event, Platform

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.cz",
    "https://nitter.tiekoetter.com",
]

SPACE_URL_RE = re.compile(r"(?:twitter\.com|x\.com)/i/spaces/([A-Za-z0-9]+)", re.I)


class XWatcher(Platform):
    name = "x"

    def __init__(self, lookback_minutes: int = 120) -> None:
        self.lookback = timedelta(minutes=lookback_minutes)
        self._seen_space_ids: set[str] = set()
        self._working_instance: str | None = None

    async def _fetch_rss(self, client: httpx.AsyncClient, handle: str) -> str | None:
        """Try instances in order; return the first successful RSS body."""
        order = list(NITTER_INSTANCES)
        if self._working_instance and self._working_instance in order:
            order.remove(self._working_instance)
            order.insert(0, self._working_instance)
        for base in order:
            try:
                r = await client.get(
                    f"{base}/{handle}/rss",
                    headers={"User-Agent": "Mozilla/5.0 (clip-notifier)"},
                )
                if r.status_code == 200 and r.text.lstrip().startswith("<?xml"):
                    self._working_instance = base
                    return r.text
            except Exception:
                continue
        return None

    def _parse_space_hits(
        self, rss_text: str, since: datetime
    ) -> list[tuple[str, str, str]]:
        """Return (space_id, title, space_url) for recent tweets containing Spaces."""
        try:
            root = ET.fromstring(rss_text)
        except ET.ParseError:
            return []
        channel = root.find("channel")
        if channel is None:
            return []
        out: list[tuple[str, str, str]] = []
        for item in channel.findall("item"):
            pub_elem = item.find("pubDate")
            if pub_elem is None or not pub_elem.text:
                continue
            try:
                pub = parsedate_to_datetime(pub_elem.text)
            except (TypeError, ValueError):
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub < since:
                continue
            title = (item.findtext("title") or "").strip()
            desc = item.findtext("description") or ""
            m = SPACE_URL_RE.search(f"{title}\n{desc}")
            if not m:
                continue
            space_id = m.group(1)
            out.append((space_id, title, f"https://x.com/i/spaces/{space_id}"))
        return out

    async def poll(self, handles: list[str]) -> list[Event]:
        if not handles:
            return []
        since = datetime.now(timezone.utc) - self.lookback
        events: list[Event] = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for handle in handles:
                clean = handle.lstrip("@")
                rss = await self._fetch_rss(client, clean)
                if not rss:
                    continue
                for space_id, title, space_url in self._parse_space_hits(rss, since):
                    if space_id in self._seen_space_ids:
                        continue
                    self._seen_space_ids.add(space_id)
                    events.append(
                        Event(
                            platform="x",
                            kind="live",
                            creator=f"@{clean}",
                            title=title[:200] or f"Space by @{clean}",
                            url=space_url,
                        )
                    )
        return events
