"""Entry point: starts the Telegram bot and the polling loop together."""
from __future__ import annotations

import asyncio
import logging

from telegram.ext import Application

from . import db
from .bot import register_handlers
from .config import Config, load_config
from .notifier import Notifier
from .platforms.base import Event, Platform
from .platforms.kick import KickWatcher
from .platforms.twitch import TwitchWatcher
from .platforms.x import XWatcher
from .platforms.youtube import YouTubeWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("clip-notifier")


def build_watchers(config: Config) -> list[Platform]:
    watchers: list[Platform] = []
    if config.youtube_api_key:
        watchers.append(YouTubeWatcher(config.youtube_api_key, config.min_longform_seconds))
    if config.twitch_client_id and config.twitch_client_secret:
        watchers.append(TwitchWatcher(config.twitch_client_id, config.twitch_client_secret))
    watchers.append(KickWatcher())
    watchers.append(XWatcher())
    return watchers


async def _poll_once(watcher: Platform, config: Config, notifier: Notifier) -> None:
    try:
        events: list[Event] = await watcher.poll(config.handles(watcher.name))
        db.record_status(watcher.name, ok=True)
    except Exception as e:
        log.exception("%s poll failed", watcher.name)
        db.record_status(watcher.name, ok=False, err=str(e))
        return

    for ev in events:
        if db.already_notified(ev.event_id):
            continue
        await notifier.send_event(ev)
        db.mark_notified(ev.event_id)


async def polling_loop(watchers: list[Platform], config: Config, notifier: Notifier) -> None:
    log.info("polling loop started (interval=%ss)", config.poll_interval)
    while True:
        try:
            await asyncio.gather(
                *[_poll_once(w, config, notifier) for w in watchers],
                return_exceptions=True,
            )
            db.prune_old(config.dedup_window_hours)
        except Exception:
            log.exception("poll cycle error")
        await asyncio.sleep(config.poll_interval)


async def run() -> None:
    config = load_config()
    app = Application.builder().token(config.telegram_token).build()
    notifier = Notifier(app.bot, config.telegram_user_id)
    register_handlers(app, config, notifier)

    watchers = build_watchers(config)
    log.info("watchers: %s", [w.name for w in watchers])

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await notifier.send_text("🟢 clip-notifier started.")
    except Exception:
        log.warning("could not send startup message — check TELEGRAM_USER_ID")

    try:
        await polling_loop(watchers, config, notifier)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
