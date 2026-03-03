from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.config import Config


class ConfigTests(unittest.TestCase):
    def _base_env(self, db_path: Path) -> dict[str, str]:
        return {
            "BOT_TOKEN": "123:abc",
            "MAIN_GROUP_ID": "-100111",
            "INTRO_CHAT_ID": "-100111",
            "INTRO_THREAD_ID": "4",
            "DATABASE_PATH": str(db_path),
        }

    def test_main_group_is_always_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "bot.sqlite3"
            env = self._base_env(db_path)

            with patch.dict(os.environ, env, clear=True):
                config = Config.from_env()

            self.assertEqual((-100111,), config.protected_chat_ids)

    def test_parses_extra_protected_chat_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "bot.sqlite3"
            env = self._base_env(db_path)
            env["PROTECTED_CHAT_IDS"] = "-100222, -100333, -100111, -100222"

            with patch.dict(os.environ, env, clear=True):
                config = Config.from_env()

            self.assertEqual((-100111, -100222, -100333), config.protected_chat_ids)


if __name__ == "__main__":
    unittest.main()
