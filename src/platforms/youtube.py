"""YouTube watcher using RSS feeds (free, no quota) + minimal API for classification.

Quota footprint per poll cycle (8 channels):
  - Channel-ID resolution: 0 units (scraped from @handle HTML, cached forever)
  - Recent-video discovery: 0 units (RSS feed per channel)
  - Classification of new IDs: 1 unit per videos.list call (batched up to 50 IDs)

Well under the 10 000 unit/day default quota.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

import httpx

from .base import Event, Platform

HANDLE_PAGE = "https://www.youtube.com/@{handle}"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"

CHANNEL_ID_RE = re.compile(r'"channelId":"(UC[A-Za-z0-9_\-]{22})"')
ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def _iso_to_seconds(iso: str) -> int:
    m = ISO_DURATION.match(iso or "")
    if not m:
        return 0
    h, mn, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mn * 60 + s


class YouTubeWatcher(Platform):
    name = "youtube"

    def __init__(self, api_key: str, min_longform_seconds: int = 600) -> None:
        self.api_key = api_key
        self.min_longform_seconds = min_longform_seconds
        self._channel_id_cache: dict[str, str] = {}
        self._seen_video_ids: set[str] = set()

    async def _resolve_channel_id(self, client: httpx.AsyncClient, handle: str) -> str | None:
        if handle in self._channel_id_cache:
            return self._channel_id_cache[handle]
        if handle.startswith("UC") and len(handle) == 24:
            self._channel_id_cache[handle] = handle
            return handle
        try:
            r = await client.get(
                HANDLE_PAGE.format(handle=handle),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (clip-notifier)"},
            )
            if r.status_code != 200:
                return None
            m = CHANNEL_ID_RE.search(r.text)
            if not m:
                return None
            cid = m.group(1)
            self._channel_id_cache[handle] = cid
            return cid
        except Exception:
            return None

    async def _fetch_rss(
        self, client: httpx.AsyncClient, channel_id: str
    ) -> list[tuple[str, str, str]]:
        """Return (video_id, title, channel_title) tuples for recent entries."""
        try:
            r = await client.get(RSS_URL.format(channel_id=channel_id))
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.text)
        except Exception:
            return []
        ct_elem = root.find("atom:title", NS)
        channel_title = ct_elem.text if ct_elem is not None else ""
        out: list[tuple[str, str, str]] = []
        for entry in root.findall("atom:entry", NS):
            vid = entry.find("yt:videoId", NS)
            title = entry.find("atom:title", NS)
            if vid is None or title is None or not vid.text:
                continue
            out.append((vid.text, title.text or "", channel_title or ""))
        return out

    async def _classify(
        self, client: httpx.AsyncClient, video_ids: list[str]
    ) -> dict[str, dict]:
        """Batch-classify video IDs via videos.list (1 unit per call, up to 50 IDs)."""
        if not video_ids or not self.api_key:
            return {}
        out: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            try:
                r = await client.get(
                    VIDEOS_API,
                    params={
                        "part": "snippet,contentDetails,liveStreamingDetails",
                        "id": ",".join(chunk),
                        "key": self.api_key,
                    },
                )
                r.raise_for_status()
                for item in r.json().get("items", []):
                    out[item["id"]] = item
            except Exception:
                continue
        return out

    async def poll(self, handles: list[str]) -> list[Event]:
        if not handles:
            return []

        async with httpx.AsyncClient(timeout=20) as client:
            # Resolve handles → channel IDs (free, cached)
            cid_by_handle: dict[str, str] = {}
            for h in handles:
                cid = await self._resolve_channel_id(client, h)
                if cid:
                    cid_by_handle[h] = cid

            # Collect new video IDs via RSS (free)
            new_entries: list[tuple[str, str, str]] = []  # (video_id, rss_title, channel_title)
            for cid in cid_by_handle.values():
                for vid, title, channel_title in await self._fetch_rss(client, cid):
                    if vid in self._seen_video_ids:
                        continue
                    self._seen_video_ids.add(vid)
                    new_entries.append((vid, title, channel_title))

            if not new_entries:
                return []

            # Classify new IDs (1 unit per ≤50 IDs)
            meta = await self._classify(client, [e[0] for e in new_entries])

            events: list[Event] = []
            for vid, rss_title, channel_title in new_entries:
                info = meta.get(vid)
                if not info:
                    continue
                sn = info.get("snippet", {})
                cd = info.get("contentDetails", {})
                live_state = sn.get("liveBroadcastContent", "none")
                duration = _iso_to_seconds(cd.get("duration", ""))
                url = f"https://youtube.com/watch?v={vid}"
                creator = sn.get("channelTitle") or channel_title or ""
                title = sn.get("title") or rss_title

                if live_state == "live":
                    events.append(
                        Event(
                            platform="youtube",
                            kind="live",
                            creator=creator,
                            title=title,
                            url=url,
                        )
                    )
                elif live_state == "none" and duration >= self.min_longform_seconds:
                    events.append(
                        Event(
                            platform="youtube",
                            kind="upload",
                            creator=creator,
                            title=title,
                            url=url,
                            duration_seconds=duration,
                        )
                    )
                # skip "upcoming" (scheduled) and shorts (< min_longform_seconds)

        return events
