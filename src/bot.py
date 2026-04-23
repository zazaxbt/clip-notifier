"""Telegram bot command handlers."""
from __future__ import annotations

import time

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import db
from .config import PLATFORMS, Config, save_channels
from .notifier import Notifier


def _owner_only(user_id: int):
    def decorator(handler):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_user and update.effective_user.id != user_id:
                return
            return await handler(update, context)
        return wrapper
    return decorator


def register_handlers(app: Application, config: Config, notifier: Notifier) -> None:
    owner = _owner_only(config.telegram_user_id)

    @owner
    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "clip-notifier online.\n\n"
            "Commands:\n"
            "/list — show tracked creators\n"
            "/add <platform> <handle>\n"
            "/remove <platform> <handle>\n"
            "/watch <name> — alert when tracked creators mention this name\n"
            "/unwatch <name>\n"
            "/mute <minutes>\n"
            "/status — health per platform\n\n"
            f"Platforms: {', '.join(PLATFORMS)}"
        )

    @owner
    async def list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        lines = []
        for plat in PLATFORMS:
            handles = config.channels.get(plat, [])
            lines.append(f"<b>{plat}</b> ({len(handles)})")
            for h in handles:
                lines.append(f"  • {h}")
            lines.append("")
        text = "\n".join(lines).strip() or "No creators tracked. Add one with /add."
        await update.message.reply_html(text)

    @owner
    async def add_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args or []
        if len(args) < 2:
            await update.message.reply_text("Usage: /add <platform> <handle>")
            return
        platform, handle = args[0].lower(), args[1]
        if platform not in PLATFORMS:
            await update.message.reply_text(f"platform must be one of: {', '.join(PLATFORMS)}")
            return
        lst = config.channels.setdefault(platform, [])
        if handle in lst:
            await update.message.reply_text("Already tracked.")
            return
        lst.append(handle)
        save_channels(config)
        await update.message.reply_text(f"✅ Added {handle} to {platform}.")

    @owner
    async def remove_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args or []
        if len(args) < 2:
            await update.message.reply_text("Usage: /remove <platform> <handle>")
            return
        platform, handle = args[0].lower(), args[1]
        if platform not in PLATFORMS:
            await update.message.reply_text(f"platform must be one of: {', '.join(PLATFORMS)}")
            return
        lst = config.channels.get(platform, [])
        if handle not in lst:
            await update.message.reply_text("Handle not in list.")
            return
        lst.remove(handle)
        save_channels(config)
        await update.message.reply_text(f"🗑 Removed {handle} from {platform}.")

    @owner
    async def watch_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args or []
        if not args:
            if not config.mentions:
                await update.message.reply_text("No mention keywords. Add with /watch <name>.")
                return
            await update.message.reply_text("👀 Mention watchlist:\n" + "\n".join(f"• {m}" for m in config.mentions))
            return
        name = " ".join(args)
        if name in config.mentions:
            await update.message.reply_text("Already watching.")
            return
        config.mentions.append(name)
        save_channels(config)
        await update.message.reply_text(f"👀 Now watching for mentions of: {name}")

    @owner
    async def unwatch_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args or []
        if not args:
            await update.message.reply_text("Usage: /unwatch <name>")
            return
        name = " ".join(args)
        if name not in config.mentions:
            await update.message.reply_text("Not in watchlist.")
            return
        config.mentions.remove(name)
        save_channels(config)
        await update.message.reply_text(f"Removed mention keyword: {name}")

    @owner
    async def mute_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args or []
        try:
            minutes = int(args[0]) if args else 60
        except ValueError:
            await update.message.reply_text("Usage: /mute <minutes>")
            return
        notifier.mute_for(minutes * 60)
        await update.message.reply_text(f"🔕 Muted for {minutes} min.")

    @owner
    async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        rows = db.get_status()
        if not rows:
            await update.message.reply_text("No polls recorded yet.")
            return
        now = int(time.time())
        lines = []
        for platform, last_ok, last_err in rows:
            if last_ok:
                lines.append(f"✅ {platform}: ok ({now - last_ok}s ago)")
            if last_err:
                lines.append(f"⚠️ {platform}: {last_err}")
        mute_left = max(0, int(notifier.muted_until - now))
        if mute_left:
            lines.append(f"🔕 muted for {mute_left}s")
        await update.message.reply_text("\n".join(lines))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("watch", watch_cmd))
    app.add_handler(CommandHandler("unwatch", unwatch_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
