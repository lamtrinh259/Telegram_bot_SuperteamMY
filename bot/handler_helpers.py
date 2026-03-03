from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


def is_intro_message(
    chat_id: int,
    message_thread_id: int | None,
    intro_chat_id: int,
    intro_thread_id: int | None,
) -> bool:
    if chat_id != intro_chat_id:
        return False
    if intro_thread_id is None:
        return True
    return message_thread_id == intro_thread_id


def should_remind(last_reminded_at: datetime | None, cooldown_minutes: int) -> bool:
    if last_reminded_at is None:
        return True
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - last_reminded_at).total_seconds()
    return elapsed_seconds >= cooldown_minutes * 60


def build_progress_hint(word_count: int, min_words: int) -> str:
    if word_count >= min_words:
        return "Please add more specific detail about your background and what you do."
    missing = min_words - word_count
    noun = "word" if missing == 1 else "words"
    return f"Progress: {word_count}/{min_words} words. Add {missing} more {noun}."


def resolve_target_user_id(
    message_text: str | None,
    reply_user_id: int | None,
    reply_is_service: bool,
    username_lookup: Callable[[str], int | None] | None = None,
) -> int | None:
    if reply_user_id is not None and not reply_is_service:
        return reply_user_id

    if not message_text:
        return None

    parts = message_text.split(maxsplit=1)
    if len(parts) < 2:
        return None

    raw = parts[1].strip()
    try:
        return int(raw)
    except ValueError:
        pass

    username = raw.lstrip("@")
    if username and username_lookup is not None:
        return username_lookup(username)

    return None
