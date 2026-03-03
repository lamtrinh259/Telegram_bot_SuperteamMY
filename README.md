# Superteam MY Intro Gatekeeper Bot

Telegram bot for the **Build a Telegram Intro Gatekeeper Bot for Superteam** challenge.

## What It Does

- Gates new members in the main group until they introduce themselves in the dedicated `#intro` channel/topic.
- In forum-topic mode, enforces pending-user reminders in all topics except `Intro`.
- Uses flexible NLP validation (not strict templates):
  - Accepts long-enough intros directly (>= `MIN_INTRO_WORDS`).
  - Accepts medium-length intros when self/role signals are present (>= `MIN_INTRO_WORDS_WITH_SIGNALS`).
  - Rejects copy-paste of the example intro using trigram-based similarity detection.
- Supports DM onboarding, with automatic in-group fallback when DMs are blocked.
- Pending users who spam outside Intro are temporarily muted (default: 5 messages in 60 seconds -> 30-minute mute).
- Introduced non-admin users are also rate-limited and temporarily muted on spam bursts.
- Handles key edge cases:
  - Rejoin behavior (already introduced users are not re-gated).
  - Persistence across bot restarts (SQLite).
  - Intro in wrong place (reminder/redirection).
  - Already-introduced users can chat freely in `#intro` without re-triggering validation.
  - Admins are auto-recognized and never gated.
- Dynamic clickable `#intro` deep link in welcome/reminder/acceptance messages (forum-topic mode).
- Admin utilities for managing member states (see [Commands](#commands)).

## Architecture

```text
bot/
├── app.py            # Application builder, handler registration, custom filters
├── auth.py           # Admin authorization checks
├── config.py         # Environment-based configuration
├── database.py       # SQLite repository (MemberRepository)
├── runtime.py        # Runtime context (config + repo)
├── utils.py          # Constants, formatting helpers, deep links
├── validation.py     # Intro text validation + anti-copy-paste
└── handlers/
    ├── join.py       # New member join handling, lock/unlock, reminders
    ├── intro.py      # Intro message validation, main-group gating
    ├── admin.py      # Admin commands (pending, approve, reject, etc.)
    ├── rate_limit.py # Rate limiting + temporary mute/unmute jobs
    └── jobs.py       # Scheduled auto-reminder job
main.py               # Entry point
Dockerfile
docker-compose.yml
.env.example
tests/
├── test_validation.py
├── test_database.py
└── test_handler_smoke.py
```

## Bot Permissions Required

In the **main group**, the bot should be admin with at least:
- `Delete messages`
- `Restrict members`
- `Invite users` (optional)

In the **intro channel/topic**, the bot needs permission to read and send messages.

**Important (forum-topic mode):** If `#intro` is a topic inside the main group, you must disable bot privacy mode in BotFather (`/setprivacy` -> select this bot -> `Disable`) so the bot can see non-command messages in all topics.

## Environment Variables

Copy `.env.example` to `.env` and set values:

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Telegram bot token from BotFather |
| `MAIN_GROUP_ID` | Yes | — | Chat ID of the main group (e.g. `-100...`) |
| `INTRO_CHAT_ID` | Yes | — | Chat ID where intros are posted |
| `INTRO_THREAD_ID` | No | — | Topic ID if `#intro` is a forum topic |
| `ADMIN_USER_IDS` | No | — | Comma-separated Telegram user IDs |
| `DATABASE_PATH` | No | `data/bot.sqlite3` | Path to SQLite database |
| `MIN_INTRO_WORDS` | No | `20` | Min words for unconditional acceptance |
| `MIN_INTRO_WORDS_WITH_SIGNALS` | No | `12` | Min words when self+role signals present |
| `REMINDER_COOLDOWN_MINUTES` | No | `30` | Cooldown between reminder DMs per user |
| `AUTO_REMINDER_HOURS` | No | `0` (disabled) | Interval for automatic batch reminders |
| `RATE_LIMIT_MAX_MESSAGES` | No | `5` | Mute threshold within rate-limit window (`>=` this count) |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Rate-limit sliding window size (seconds) |
| `RATE_LIMIT_MUTE_MINUTES` | No | `30` | Temporary mute duration when limit is exceeded |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, etc.) |

### Configuration Modes

- **Separate intro chat:** Set `INTRO_CHAT_ID` to a different chat than `MAIN_GROUP_ID`. Leave `INTRO_THREAD_ID` empty. The bot mutes pending users in the main group.
- **Forum topic mode:** Set `INTRO_CHAT_ID` = `MAIN_GROUP_ID` and set `INTRO_THREAD_ID` to the topic ID. The bot uses delete-and-remind enforcement (instead of global mute) so pending users can still post in the Intro topic.

## Commands

### User Commands

| Command | Description |
|---|---|
| `/start` | Get intro instructions and onboarding reminder |
| `/example` | Show a sample intro format |

### Admin Commands

| Command | Description |
|---|---|
| `/pending` | List all pending (un-introduced) members |
| `/status [user_id]` | Show bot summary, or a specific member's state |
| `/remind [user_id]` | Send reminder to one user immediately, or all users currently due |
| `/approve <user_id \| @username>` | Mark user as introduced and unlock main-group access |
| `/reject <user_id \| @username>` | Mark user pending, re-apply gate, and send reminder |
| `/reset <user_id \| @username>` | Reset to pending + clear intro/reminder state, then re-apply gate (forum-topic mode: unmuted; separate-intro mode: muted) |
| `/diag` | Show bot diagnostics (privacy mode, permissions) |

Admin commands accept a numeric `user_id` or `@username`. You can also reply to a user's message and run the command without arguments.

### Hidden Debug Commands

| Command | Description |
|---|---|
| `/ids` | Print current `chat_id`, `message_thread_id`, and your `user_id` |

## Validation Logic

The bot uses flexible NLP-style validation (no rigid templates):

1. **Anti-copy-paste check** — Trigram-based similarity detection rejects intros that are too similar to the `/example` text (>45% trigram overlap with example answers).
2. **Length check** — Accepted if word count >= `MIN_INTRO_WORDS` (default 20).
3. **Signal check** — Accepted if word count >= `MIN_INTRO_WORDS_WITH_SIGNALS` (default 12) AND the message contains both:
   - A self signal (`I`, `my`, `me`, etc.)
   - A role/work signal (`work`, `developer`, `build`, `founder`, etc.)
4. **Too short** — Rejected with a helpful message showing current word count.

## Core Flow

1. User joins main group.
2. Bot records user in SQLite as "pending".
3. Bot restricts their messaging permissions (mute mode) or monitors messages (delete mode in forum-topic mode).
4. Bot sends onboarding instructions via DM; falls back to in-group message if DMs are blocked.
5. User posts intro in `#intro`.
6. Bot validates intro text (length, signals, anti-copy-paste).
7. On acceptance: marks user as "introduced", unlocks main-group access, posts announcement with clickable `#intro` link.
8. If a pending user tries to post outside Intro, the bot deletes the message and sends a cooldown-limited reminder.
9. If a non-admin user exceeds the message rate limit outside Intro, the bot temporarily mutes them and auto-unmutes after the configured duration.

## Muting Logic

- Threshold: mute is triggered when a user sends `RATE_LIMIT_MAX_MESSAGES` or more messages within `RATE_LIMIT_WINDOW_SECONDS`.
- Pending users:
  - Applies when they post outside Intro (the same path that deletes/reminds).
  - They are muted for `RATE_LIMIT_MUTE_MINUTES`.
  - In forum-topic mode, they are auto-unmuted after timer so onboarding can continue.
- Introduced users:
  - Applies to non-admin users posting outside Intro in the main supergroup.
  - They are muted for `RATE_LIMIT_MUTE_MINUTES` and auto-unmuted via job queue.
- Admin users are exempt.
- Rate-limit counters are in-memory and reset on bot restart.

### Forum Topic Mode Details

When `INTRO_CHAT_ID` equals `MAIN_GROUP_ID` and `INTRO_THREAD_ID` is set:

- Telegram applies permissions at the chat level, not per-topic. Muting a user would block them from posting in the Intro topic too.
- The bot uses **delete-and-remind** enforcement: pending users' messages outside the Intro topic are deleted, and the user receives a DM reminder.
- If a pending user repeatedly spams outside Intro, the bot temporarily mutes them based on the configured rate-limit threshold.
- **Privacy mode must be OFF** (BotFather: `/setprivacy` -> Disable) so the bot can intercept non-command messages.
- On startup, the bot clears stale mute restrictions for all pending users (in case the bot was previously running in mute mode).

## Recommended Telegram Group Settings

- Set your group history visibility so new members **cannot read old messages** before onboarding. This reduces copy-paste intros from previous accepted examples.
- Keep Intro instructions pinned in the Intro topic.
- The bot's Intro deep link is generated dynamically from `INTRO_CHAT_ID` + `INTRO_THREAD_ID`, so keep those IDs accurate in `.env`.

## Local Run (Without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values
python main.py
```

## Run With Docker

```bash
cp .env.example .env
# Edit .env with your values

docker compose up --build -d
```

View logs:

```bash
docker compose logs -f bot
```

## Testing

Run unit tests:

```bash
python -m unittest discover -s tests
```

Tests cover:
- Intro validation logic (including anti-copy-paste detection and copied-bot-text rejection).
- Database lifecycle behavior (join/introduce/rejoin/pending reset).
- Handler helper logic (target resolution, reminder cooldown, topic matching, rate-limit threshold helper).

## Quick Troubleshooting

| Problem | Fix |
|---|---|
| Bot replies with example chat IDs | Replace placeholder values in `.env` with real IDs |
| Bot doesn't validate intros in Intro topic | Disable privacy mode in BotFather (`/setprivacy` -> Disable) and restart |
| Bot can't delete messages | Grant the bot "Delete messages" admin permission |
| Bot can't restrict members | Grant the bot "Restrict members" admin permission |
| Users are muted too aggressively | Increase `RATE_LIMIT_MAX_MESSAGES` or `RATE_LIMIT_WINDOW_SECONDS` |
| Pending users are not muted in General | Ensure bot can read non-command messages (privacy mode OFF) and has `Restrict members` |
| `/reject @username` targets wrong user | Ensure the user has sent at least one message so their username is in the database |
| Admin is being gated | Add your user ID to `ADMIN_USER_IDS` in `.env` and restart |

Use `/ids` in any chat or topic to find the real `chat_id`, `message_thread_id`, and your `user_id`.

## VPS Deployment Notes

- Recommended: Docker-based deployment for simplicity.
- Mount `data/` directory so SQLite persists across container restarts.
- Use restart policy `unless-stopped` in docker-compose.
- For production, add log rotation and uptime monitoring.

## Demo Checklist

- [ ] User joins main group -> restricted/gated state
- [ ] Bot sends onboarding message (DM or in-group fallback)
- [ ] `/example` shows sample intro format
- [ ] Copy-paste of example intro is rejected
- [ ] Valid original intro -> accepted, main-group access unlocked
- [ ] Acceptance announcement shows clickable `#intro` link
- [ ] Already-introduced user chats freely in `#intro` without validation prompts
- [ ] Pending user's message in General or other non-Intro topics is deleted with reminder
- [ ] Pending spam outside Intro triggers temporary mute and later auto-unmute
- [ ] Introduced user spam triggers temporary mute and later auto-unmute
- [ ] `/pending`, `/status`, `/approve`, `/reject`, `/reset`, `/diag` work correctly
- [ ] Auto-reminders fire on schedule (if configured)
