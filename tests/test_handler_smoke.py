from __future__ import annotations

import unittest
from collections import deque
from datetime import datetime, timedelta, timezone

from bot.handler_helpers import (
    build_progress_hint,
    is_intro_message,
    record_message_and_check_limit,
    resolve_target_user_id,
    should_remind,
)


class HandlerSmokeTests(unittest.TestCase):
    def test_resolve_target_user_id_from_integer_arg(self) -> None:
        resolved = resolve_target_user_id(
            message_text="/reject 123456",
            reply_user_id=None,
            reply_is_service=False,
        )
        self.assertEqual(123456, resolved)

    def test_resolve_target_user_id_from_reply_message(self) -> None:
        resolved = resolve_target_user_id(
            message_text="/reject",
            reply_user_id=8888,
            reply_is_service=False,
        )
        self.assertEqual(8888, resolved)

    def test_service_reply_is_ignored_then_arg_used(self) -> None:
        resolved = resolve_target_user_id(
            message_text="/reject 7777",
            reply_user_id=9999,
            reply_is_service=True,
        )
        self.assertEqual(7777, resolved)

    def test_resolve_target_user_id_from_username_lookup(self) -> None:
        resolved = resolve_target_user_id(
            message_text="/reject @alice",
            reply_user_id=None,
            reply_is_service=False,
            username_lookup=lambda username: 4444 if username.lower() == "alice" else None,
        )
        self.assertEqual(4444, resolved)

    def test_intro_message_topic_matching(self) -> None:
        self.assertTrue(is_intro_message(-1001, 4, -1001, 4))
        self.assertFalse(is_intro_message(-1001, 3, -1001, 4))
        self.assertFalse(is_intro_message(-1002, 4, -1001, 4))
        self.assertTrue(is_intro_message(-1001, None, -1001, None))

    def test_reminder_helpers(self) -> None:
        self.assertTrue(should_remind(None, cooldown_minutes=30))

        recent = datetime.now(timezone.utc) - timedelta(minutes=2)
        old = datetime.now(timezone.utc) - timedelta(minutes=45)
        self.assertFalse(should_remind(recent, cooldown_minutes=30))
        self.assertTrue(should_remind(old, cooldown_minutes=30))

        self.assertIn("Progress", build_progress_hint(word_count=8, min_words=20))

    def test_record_message_and_check_limit(self) -> None:
        now = datetime.now(timezone.utc)
        history = deque(
            [
                now - timedelta(seconds=50),
                now - timedelta(seconds=40),
                now - timedelta(seconds=20),
                now - timedelta(seconds=10),
                now - timedelta(seconds=5),
            ]
        )
        is_limited = record_message_and_check_limit(
            history=history,
            now=now,
            window_seconds=60,
            max_messages=5,
        )
        self.assertTrue(is_limited)


if __name__ == "__main__":
    unittest.main()
