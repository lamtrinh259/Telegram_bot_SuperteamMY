from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_admin_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    ids: set[int] = set()
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        ids.add(int(raw))
    return ids


@dataclass(frozen=True)
class Config:
    bot_token: str
    main_group_id: int
    intro_chat_id: int
    database_path: Path
    admin_user_ids: set[int]
    min_intro_words: int
    min_intro_words_with_signals: int
    reminder_cooldown_minutes: int
    auto_reminder_hours: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("BOT_TOKEN is required")

        main_group = os.getenv("MAIN_GROUP_ID", "").strip()
        if not main_group:
            raise ValueError("MAIN_GROUP_ID is required")

        intro_chat = os.getenv("INTRO_CHAT_ID", "").strip()
        if not intro_chat:
            raise ValueError("INTRO_CHAT_ID is required")

        db_path = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))

        return cls(
            bot_token=token,
            main_group_id=int(main_group),
            intro_chat_id=int(intro_chat),
            database_path=db_path,
            admin_user_ids=_parse_admin_ids(os.getenv("ADMIN_USER_IDS")),
            min_intro_words=int(os.getenv("MIN_INTRO_WORDS", "20")),
            min_intro_words_with_signals=int(os.getenv("MIN_INTRO_WORDS_WITH_SIGNALS", "12")),
            reminder_cooldown_minutes=int(os.getenv("REMINDER_COOLDOWN_MINUTES", "30")),
            auto_reminder_hours=int(os.getenv("AUTO_REMINDER_HOURS", "0")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
