# Superteam MY Intro Gatekeeper Bot

Telegram bot for the **Build a Telegram Intro Gatekeeper Bot for Superteam** challenge.

## What It Does

- Gates new members in the main group until they introduce themselves in the dedicated `#intro` channel.
- Uses flexible validation (not strict templates):
  - Accepts long-enough intros directly.
  - Accepts medium-length intros when self/role signals are present.
- Supports DM onboarding, with automatic in-group fallback when DMs are blocked.
- Handles key edge cases:
  - Rejoin behavior (already introduced users are not re-gated)
  - Persistence across bot restarts (SQLite)
  - Intro in wrong place (reminder/redirection)
- Includes required intro example via `/example`.
- Admin utilities:
  - `/pending`
  - `/status [user_id]`
  - `/remind [user_id]`
  - `/approve [user_id]` (optional/manual)
  - `/reject [user_id]` (optional/manual)
  - `/gate [user_id]` / `/ungate [user_id]` (fast test controls)
  - `/reset [user_id]` / `/wipe [user_id]` (state reset tools)
  - `/diag` / `/adminhelp` (debug and command reference)

## Architecture

```text
bot/
├── app.py
├── auth.py
├── config.py
├── database.py
├── runtime.py
├── utils.py
└── handlers/
    ├── join.py
    ├── intro.py
    ├── admin.py
    └── jobs.py
main.py
Dockerfile
docker-compose.yml
.env.example
```

## Bot Permissions Required

In the **main group**, the bot should be admin with at least:
- `Delete messages`
- `Restrict members`
- `Invite users` (optional)

In the **intro channel/group**, the bot needs permission to read messages.

## Environment Variables

Copy `.env.example` to `.env` and set values:

- `BOT_TOKEN` (required)
- `MAIN_GROUP_ID` (required, e.g. `-100...`)
- `INTRO_CHAT_ID` (required, e.g. `-100...`)
- `INTRO_THREAD_ID` (optional, required only if `#intro` is a topic in a forum group)
- `ADMIN_USER_IDS` (comma-separated Telegram user IDs)
- `DATABASE_PATH` (default `data/bot.sqlite3`)
- `MIN_INTRO_WORDS` (default `20`)
- `MIN_INTRO_WORDS_WITH_SIGNALS` (default `12`)
- `REMINDER_COOLDOWN_MINUTES` (default `30`)
- `AUTO_REMINDER_HOURS` (default `0`, disabled)
- `LOG_LEVEL` (default `INFO`)

## Quick Troubleshooting

- If bot replies with `chat ID: -1001234567891`, you are still using example values from `.env.example`.
- If `#intro` is a separate chat/channel: set `INTRO_CHAT_ID` to that chat ID and leave `INTRO_THREAD_ID` empty.
- If `#intro` is a topic in the same forum group: set `INTRO_CHAT_ID=MAIN_GROUP_ID` and set `INTRO_THREAD_ID`.
- Use `/ids` in each chat/topic to copy real `chat_id` and `message_thread_id`, and add your own `user_id` to `ADMIN_USER_IDS`.
- Admins should not be gated; if you are an admin and still see lock behavior, restart bot after pulling latest changes so admin-bypass logic is active.

## Local Run (Without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Run With Docker

```bash
cp .env.example .env
# update .env values first

docker compose up --build -d
```

Logs:

```bash
docker compose logs -f bot
```

## Core Flow

1. User joins main group.
2. Bot records user in SQLite.
3. If user is not introduced yet:
   - Bot restricts their messaging permissions in main group.
   - Bot posts onboarding instructions.
   - Bot tries DM; if blocked, onboarding continues in-group.
4. User posts intro in `#intro`.
5. Bot validates intro message.
6. Bot marks user as introduced + unlocks main-group access.

### Forum Topic Mode Note

If `INTRO_CHAT_ID` equals `MAIN_GROUP_ID` and `INTRO_THREAD_ID` is set, Telegram applies permissions at chat level, not per-topic.  
So the bot uses delete-and-remind enforcement outside Intro topic (instead of global mute) to ensure pending users can still post in Intro.
For this to work, disable bot privacy mode in BotFather (`/setprivacy -> Disable`) so the bot can receive normal group messages.

## Validation Logic (Flexible)

- Valid if word count >= `MIN_INTRO_WORDS`.
- Also valid if word count >= `MIN_INTRO_WORDS_WITH_SIGNALS` and message contains both:
  - self signal (`I`, `my`, etc.)
  - role/work signal (`work`, `developer`, `build`, etc.)

## Commands

- `/start` - onboarding reminder text
- `/example` - sample intro format required by the bounty
- `/ids` - print current `chat_id`, `message_thread_id` (if in topic), and your `user_id`
- `/pending` - list pending members (admin)
- `/status [user_id]` - bot summary or per-user state (admin)
- `/remind [user_id]` - send reminders (admin)
- `/approve [user_id]` - manual override to introduced (admin)
- `/reject [user_id]` - keep user gated + reminder (admin)
- `/gate [user_id]` - force user into pending state (admin)
- `/ungate [user_id]` - force user into introduced state (admin)
- `/reset [user_id]` - reset user to pending and clear intro/reminder state (admin)
- `/wipe [user_id]` - delete user row from DB and clear restrictions (admin)
- `/diag` - print privacy-mode + permission diagnostics (admin)
- `/adminhelp` - list all admin/testing commands

## Testing

Run unit tests:

```bash
python -m unittest discover -s tests
```

## VPS Deployment Notes

- Recommended for speed: Docker-based deployment.
- Keep `data/` mounted so SQLite persists.
- Use process restart policy (`unless-stopped`).
- For production hardening, place bot behind monitoring and log rotation.

## Demo Checklist

- Show user join -> muted state in main group.
- Show onboarding message and `/example` output.
- Show intro message in `#intro` -> automatic unlock.
- Show fallback behavior when DM is blocked.
- Show `/pending`, `/status`, `/remind`, `/diag`.
