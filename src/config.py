"""Load settings from .env and channels.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PLATFORMS = ("youtube", "twitch", "kick", "x")


@dataclass
class Config:
    telegram_token: str
    telegram_user_id: int
    youtube_api_key: str
    twitch_client_id: str
    twitch_client_secret: str
    poll_interval: int
    min_longform_seconds: int
    dedup_window_hours: int
    channels: dict[str, list[str]] = field(default_factory=dict)
    channels_path: Path = ROOT / "channels.yaml"

    def handles(self, platform: str) -> list[str]:
        return list(self.channels.get(platform, []))


def load_config() -> Config:
    channels_path = ROOT / "channels.yaml"
    with channels_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    settings = raw.get("settings", {}) or {}
    raw_channels = raw.get("channels", {}) or {}
    channels = {p: list(raw_channels.get(p, []) or []) for p in PLATFORMS}

    def req(key: str) -> str:
        val = os.getenv(key, "").strip()
        if not val:
            raise RuntimeError(f"Missing required env var: {key}")
        return val

    return Config(
        telegram_token=req("TELEGRAM_BOT_TOKEN"),
        telegram_user_id=int(req("TELEGRAM_USER_ID")),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip(),
        twitch_client_id=os.getenv("TWITCH_CLIENT_ID", "").strip(),
        twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", "").strip(),
        poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
        min_longform_seconds=int(settings.get("min_longform_seconds", 600)),
        dedup_window_hours=int(settings.get("dedup_window_hours", 168)),
        channels=channels,
        channels_path=channels_path,
    )


def save_channels(config: Config) -> None:
    """Persist channels + settings back to channels.yaml."""
    out = {
        "channels": {p: config.channels.get(p, []) for p in PLATFORMS},
        "settings": {
            "min_longform_seconds": config.min_longform_seconds,
            "dedup_window_hours": config.dedup_window_hours,
        },
    }
    with config.channels_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True)
