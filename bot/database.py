from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ISO_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_TIME_FORMAT)


def parse_iso_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, ISO_TIME_FORMAT).replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class MemberState:
    user_id: int
    username: str | None
    first_name: str | None
    main_chat_id: int | None
    status: str
    joined_at: datetime | None
    intro_chat_id: int | None
    intro_message_id: int | None
    introduced_at: datetime | None
    last_reminded_at: datetime | None
    last_seen_at: datetime | None

    @property
    def is_introduced(self) -> bool:
        return self.status == "introduced"


class MemberRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS members (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    main_chat_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    joined_at TEXT,
                    intro_chat_id INTEGER,
                    intro_message_id INTEGER,
                    introduced_at TEXT,
                    last_reminded_at TEXT,
                    last_seen_at TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_members_status ON members(status)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert_join(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        main_chat_id: int,
    ) -> MemberState:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO members (
                    user_id,
                    username,
                    first_name,
                    main_chat_id,
                    status,
                    joined_at,
                    last_seen_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    main_chat_id = excluded.main_chat_id,
                    joined_at = CASE
                        WHEN members.joined_at IS NULL THEN excluded.joined_at
                        ELSE members.joined_at
                    END,
                    last_seen_at = excluded.last_seen_at,
                    status = CASE
                        WHEN members.status = 'introduced' THEN 'introduced'
                        ELSE 'pending'
                    END
                """,
                (user_id, username, first_name, main_chat_id, now, now),
            )
            self._conn.commit()
        member = self.get_member(user_id)
        if member is None:
            raise RuntimeError("failed to upsert member join")
        return member

    def mark_introduced(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        intro_chat_id: int,
        intro_message_id: int,
    ) -> MemberState:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO members (
                    user_id,
                    username,
                    first_name,
                    status,
                    intro_chat_id,
                    intro_message_id,
                    introduced_at,
                    last_seen_at
                ) VALUES (?, ?, ?, 'introduced', ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    status = 'introduced',
                    intro_chat_id = excluded.intro_chat_id,
                    intro_message_id = excluded.intro_message_id,
                    introduced_at = excluded.introduced_at,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, username, first_name, intro_chat_id, intro_message_id, now, now),
            )
            self._conn.commit()
        member = self.get_member(user_id)
        if member is None:
            raise RuntimeError("failed to mark member introduced")
        return member

    def mark_pending(self, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE members
                SET status = 'pending',
                    intro_chat_id = NULL,
                    intro_message_id = NULL,
                    introduced_at = NULL,
                    last_reminded_at = NULL
                WHERE user_id = ?
                """,
                (user_id,),
            )
            self._conn.commit()

    def delete_member(self, user_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM members WHERE user_id = ?",
                (user_id,),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def set_last_reminded(self, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE members SET last_reminded_at = ? WHERE user_id = ?",
                (utc_now_iso(), user_id),
            )
            self._conn.commit()

    def get_member(self, user_id: int) -> MemberState | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM members WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_member(row) if row else None

    def list_pending(self, limit: int = 100) -> list[MemberState]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM members
                WHERE status = 'pending'
                ORDER BY joined_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_member(row) for row in rows]

    def list_pending_ready_for_reminder(self, cooldown_minutes: int, limit: int = 100) -> list[MemberState]:
        pending = self.list_pending(limit=limit)
        now = datetime.now(timezone.utc)
        ready: list[MemberState] = []
        for member in pending:
            if member.last_reminded_at is None:
                ready.append(member)
                continue
            elapsed = now - member.last_reminded_at
            if elapsed.total_seconds() >= cooldown_minutes * 60:
                ready.append(member)
        return ready

    def count_pending(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(1) AS count FROM members WHERE status = 'pending'"
            ).fetchone()
        return int(row["count"]) if row else 0

    def count_introduced(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(1) AS count FROM members WHERE status = 'introduced'"
            ).fetchone()
        return int(row["count"]) if row else 0

    @staticmethod
    def _row_to_member(row: sqlite3.Row) -> MemberState:
        return MemberState(
            user_id=row["user_id"],
            username=row["username"],
            first_name=row["first_name"],
            main_chat_id=row["main_chat_id"],
            status=row["status"],
            joined_at=parse_iso_or_none(row["joined_at"]),
            intro_chat_id=row["intro_chat_id"],
            intro_message_id=row["intro_message_id"],
            introduced_at=parse_iso_or_none(row["introduced_at"]),
            last_reminded_at=parse_iso_or_none(row["last_reminded_at"]),
            last_seen_at=parse_iso_or_none(row["last_seen_at"]),
        )
