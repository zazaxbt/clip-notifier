"""YouTube watcher: detects live streams and long-form uploads."""
from __future__ import annotations

import re

import httpx

from .base import Event, Platform

API = "https://www.googleapis.com/youtube/v3"
ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


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
        self._uploads_playlist_cache: dict[str, str] = {}

    async def _resolve_channel_id(self, client: httpx.AsyncClient, handle: str) -> str | None:
        if handle in self._channel_id_cache:
            return self._channel_id_cache[handle]
        if handle.startswith("UC") and len(handle) == 24:
            self._channel_id_cache[handle] = handle
            return handle
        r = await client.get(
            f"{API}/search",
            params={
                "part": "snippet",
                "q": handle,
                "type": "channel",
                "maxResults": 1,
                "key": self.api_key,
            },
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None
        cid = items[0]["snippet"]["channelId"]
        self._channel_id_cache[handle] = cid
        return cid

    async def _uploads_playlist(self, client: httpx.AsyncClient, channel_id: str) -> str | None:
        if channel_id in self._uploads_playlist_cache:
            return self._uploads_playlist_cache[channel_id]
        r = await client.get(
            f"{API}/channels",
            params={"part": "contentDetails", "id": channel_id, "key": self.api_key},
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None
        pid = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        self._uploads_playlist_cache[channel_id] = pid
        return pid

    async def _check_live(
        self, client: httpx.AsyncClient, handle: str, channel_id: str
    ) -> list[Event]:
        r = await client.get(
            f"{API}/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "eventType": "live",
                "type": "video",
                "maxResults": 3,
                "key": self.api_key,
            },
        )
        r.raise_for_status()
        events: list[Event] = []
        for item in r.json().get("items", []):
            vid = item["id"]["videoId"]
            sn = item["snippet"]
            events.append(
                Event(
                    platform="youtube",
                    kind="live",
                    creator=sn.get("channelTitle", handle),
                    title=sn.get("title", ""),
                    url=f"https://youtube.com/watch?v={vid}",
                    thumbnail=sn.get("thumbnails", {}).get("high", {}).get("url"),
                )
            )
        return events

    async def _check_uploads(
        self, client: httpx.AsyncClient, handle: str, channel_id: str
    ) -> list[Event]:
        playlist_id = await self._uploads_playlist(client, channel_id)
        if not playlist_id:
            return []
        r = await client.get(
            f"{API}/playlistItems",
            params={
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 5,
                "key": self.api_key,
            },
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return []
        video_ids = [i["contentDetails"]["videoId"] for i in items]

        d = await client.get(
            f"{API}/videos",
            params={"part": "contentDetails,snippet", "id": ",".join(video_ids), "key": self.api_key},
        )
        d.raise_for_status()
        meta = {v["id"]: v for v in d.json().get("items", [])}

        events: list[Event] = []
        for vid in video_ids:
            v = meta.get(vid)
            if not v:
                continue
            dur = _iso_to_seconds(v["contentDetails"]["duration"])
            if dur < self.min_longform_seconds:
                continue
            events.append(
                Event(
                    platform="youtube",
                    kind="upload",
                    creator=v["snippet"].get("channelTitle", handle),
                    title=v["snippet"].get("title", ""),
                    url=f"https://youtube.com/watch?v={vid}",
                    duration_seconds=dur,
                )
            )
        return events

    async def poll(self, handles: list[str]) -> list[Event]:
        if not self.api_key or not handles:
            return []
        out: list[Event] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for handle in handles:
                cid = await self._resolve_channel_id(client, handle)
                if not cid:
                    continue
                out.extend(await self._check_live(client, handle, cid))
                out.extend(await self._check_uploads(client, handle, cid))
        return out
