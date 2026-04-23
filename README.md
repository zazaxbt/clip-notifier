# clip-notifier

Telegram bot that pings you the moment a tracked creator goes live or drops a long-form video (YouTube / Twitch / Kick / X).

## What it catches

| Platform | Live | New upload | Latency |
|---|---|---|---|
| YouTube | ✅ | ✅ (≥10 min by default) | ~1 min |
| Twitch  | ✅ | — | ~1 min |
| Kick    | ✅ | — | ~1 min |
| X       | best-effort (Spaces / "live now" tweets) | — | 2–5 min |

## Setup

### 1. Get credentials

- **Telegram bot token** — message `@BotFather`, run `/newbot`, copy the token.
- **Your Telegram user ID** — message `@userinfobot`, copy your numeric ID.
- **YouTube Data API key** — [console.cloud.google.com](https://console.cloud.google.com/apis/credentials), enable "YouTube Data API v3", create API key.
- **Twitch app** — [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps), register an app, grab client ID + secret.

### 2. Configure

```bash
cp .env.example .env
# fill in .env with your tokens
```

`channels.yaml` starts empty — add creators via the bot (easiest) or edit the file directly.

### 3. Run locally

```bash
pip install -r requirements.txt
python -m src.main
```

You should get a `🟢 clip-notifier started.` message in Telegram. Send `/add youtube TJRtrades` to track your first creator.

### 4. Deploy to Railway

1. Push this folder to a GitHub repo.
2. New project on [railway.app](https://railway.app) → "Deploy from GitHub".
3. Add env vars from your `.env` in Railway's Variables tab.
4. Railway auto-detects `railway.toml` and runs it as a worker. No port / HTTP needed.

## Bot commands

```
/list                         show all tracked creators
/add <platform> <handle>      add a creator
/remove <platform> <handle>   remove a creator
/mute <minutes>               silence alerts temporarily
/status                       platform health + last poll times
```

Platforms: `youtube`, `twitch`, `kick`, `x`

Examples:
```
/add youtube TJRtrades
/add twitch kai_cenat
/add kick adinross
/add x elonmusk
/remove youtube someaccount
/mute 120
```

### Handle format

| Platform | What to use | Example |
|---|---|---|
| youtube | handle without `@`, or full `UC...` channel ID | `TJRtrades` or `UCxxxx...` |
| twitch  | login name | `kai_cenat` |
| kick    | URL slug | `adinross` |
| x       | handle without `@` | `elonmusk` |

## Example notification

```
🎬 NEW UPLOAD · Youtube
TJR — "Live trading the FOMC reaction | 2hr breakdown"
Length: 127 min
https://youtube.com/watch?v=abc123
```

## Notes & caveats

- **X (Twitter)** uses `snscrape`. Scraping breaks periodically when X changes their HTML — if `/status` shows X failing, upstream snscrape needs an update, or swap to the paid X API.
- **Kick** uses the unofficial `kick.com/api/v2` endpoint. Works today; no SLA.
- **YouTube quota** — default daily quota is 10k units. Resolving a new handle costs 100, live-check costs ~100 per channel per poll. ~30 creators at 60s poll fits fine; if you grow past that, raise `POLL_INTERVAL` to 120 or request more quota.
- **Dedup** — events are remembered in `state.db` for 7 days (`dedup_window_hours` in `channels.yaml`). Delete the db to reset.
- **Long-form threshold** — `min_longform_seconds: 600` in `channels.yaml`. Shorts and sub-10-min videos are auto-filtered.

## Project layout

```
clip-notifier/
├── channels.yaml         # tracked creators + settings
├── requirements.txt
├── railway.toml
├── Procfile
├── .env.example
└── src/
    ├── main.py           # entry: bot + polling loop
    ├── config.py         # loads .env + channels.yaml
    ├── db.py             # sqlite dedup + status
    ├── notifier.py       # telegram send
    ├── bot.py            # /add /remove /list /mute /status
    └── platforms/
        ├── base.py
        ├── youtube.py
        ├── twitch.py
        ├── kick.py
        └── x.py
```
