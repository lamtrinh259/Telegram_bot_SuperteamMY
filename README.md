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
- `ADMIN_USER_IDS` (comma-separated Telegram user IDs)
- `DATABASE_PATH` (default `data/bot.sqlite3`)
- `MIN_INTRO_WORDS` (default `20`)
- `MIN_INTRO_WORDS_WITH_SIGNALS` (default `12`)
- `REMINDER_COOLDOWN_MINUTES` (default `30`)
- `AUTO_REMINDER_HOURS` (default `0`, disabled)
- `LOG_LEVEL` (default `INFO`)

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

## Validation Logic (Flexible)

- Valid if word count >= `MIN_INTRO_WORDS`.
- Also valid if word count >= `MIN_INTRO_WORDS_WITH_SIGNALS` and message contains both:
  - self signal (`I`, `my`, etc.)
  - role/work signal (`work`, `developer`, `build`, etc.)

## Commands

- `/start` - onboarding reminder text
- `/example` - sample intro format required by the bounty
- `/pending` - list pending members (admin)
- `/status [user_id]` - bot summary or per-user state (admin)
- `/remind [user_id]` - send reminders (admin)
- `/approve [user_id]` - manual override to introduced (admin)
- `/reject [user_id]` - keep user gated + reminder (admin)

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
- Show `/pending`, `/status`, `/remind`.

