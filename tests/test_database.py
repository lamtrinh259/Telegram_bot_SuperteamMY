from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.database import MemberRepository


class MemberRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "bot.sqlite3"
        self.repo = MemberRepository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        self.temp_dir.cleanup()

    def test_rejoin_preserves_introduced_status(self) -> None:
        user_id = 1234

        joined = self.repo.upsert_join(
            user_id=user_id,
            username="alice",
            first_name="Alice",
            main_chat_id=-1001,
        )
        self.assertEqual("pending", joined.status)

        introduced = self.repo.mark_introduced(
            user_id=user_id,
            username="alice",
            first_name="Alice",
            intro_chat_id=-1002,
            intro_message_id=42,
        )
        self.assertEqual("introduced", introduced.status)

        rejoined = self.repo.upsert_join(
            user_id=user_id,
            username="alice2",
            first_name="Alice Updated",
            main_chat_id=-1001,
        )
        self.assertEqual("introduced", rejoined.status)
        self.assertEqual(42, rejoined.intro_message_id)
        self.assertIsNotNone(rejoined.introduced_at)

    def test_mark_pending_clears_intro_and_reminder_state(self) -> None:
        user_id = 5678
        self.repo.upsert_join(user_id, "bob", "Bob", -1001)
        self.repo.mark_introduced(user_id, "bob", "Bob", -1002, 99)
        self.repo.set_last_reminded(user_id)

        self.repo.mark_pending(user_id)
        member = self.repo.get_member(user_id)

        self.assertIsNotNone(member)
        self.assertEqual("pending", member.status)
        self.assertIsNone(member.intro_chat_id)
        self.assertIsNone(member.intro_message_id)
        self.assertIsNone(member.introduced_at)
        self.assertIsNone(member.last_reminded_at)

    def test_get_member_by_username_case_insensitive(self) -> None:
        user_id = 9999
        self.repo.upsert_join(user_id, "CamelCaseName", "User", -1001)

        lower = self.repo.get_member_by_username("camelcasename")
        upper = self.repo.get_member_by_username("CAMELCASENAME")

        self.assertIsNotNone(lower)
        self.assertIsNotNone(upper)
        self.assertEqual(user_id, lower.user_id)
        self.assertEqual(user_id, upper.user_id)


if __name__ == "__main__":
    unittest.main()
