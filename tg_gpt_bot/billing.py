from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import AppSettings


PAYMENT_CURRENCY = "XTR"


@dataclass(frozen=True)
class ReserveResult:
    allowed: bool
    charged: bool
    free: bool
    balance: int
    cost: int


@dataclass(frozen=True)
class PaymentResult:
    inserted: bool
    balance: int


@dataclass(frozen=True)
class FreeUser:
    user_id: int
    note: str
    created_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def payment_payload(settings: AppSettings) -> str:
    return f"credits:v1:{settings.stars_price}:{settings.credits_per_purchase}"


class BillingService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._ready = False

    @property
    def enabled(self) -> bool:
        return self.settings.payments_enabled

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.settings.admin_user_ids

    async def ensure_ready(self) -> None:
        if self._ready:
            return

        await asyncio.to_thread(self._initialize)

    async def has_free_access(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True

        await self.ensure_ready()
        return await asyncio.to_thread(self._has_free_access, user_id)

    async def get_balance(self, user_id: int) -> int:
        await self.ensure_ready()
        return await asyncio.to_thread(self._get_balance, user_id)

    async def reserve(self, user_id: int, cost: int, kind: str, prompt: str) -> ReserveResult:
        if not self.enabled:
            return ReserveResult(True, False, True, 0, 0)

        if await self.has_free_access(user_id):
            return ReserveResult(True, False, True, 0, 0)

        await self.ensure_ready()
        return await asyncio.to_thread(self._reserve, user_id, cost, kind, prompt)

    async def refund(self, user_id: int, cost: int, kind: str) -> None:
        if not self.enabled or cost <= 0:
            return

        if await self.has_free_access(user_id):
            return

        await self.ensure_ready()
        await asyncio.to_thread(self._refund, user_id, cost, kind)

    async def record_payment(
        self,
        user_id: int,
        charge_id: str,
        payload: str,
        stars: int,
        credits: int,
    ) -> PaymentResult:
        await self.ensure_ready()
        return await asyncio.to_thread(
            self._record_payment,
            user_id,
            charge_id,
            payload,
            stars,
            credits,
        )

    async def add_free_user(self, user_id: int, note: str) -> None:
        await self.ensure_ready()
        await asyncio.to_thread(self._add_free_user, user_id, note)

    async def remove_free_user(self, user_id: int) -> None:
        await self.ensure_ready()
        await asyncio.to_thread(self._remove_free_user, user_id)

    async def list_free_users(self) -> list[FreeUser]:
        await self.ensure_ready()
        return await asyncio.to_thread(self._list_free_users)

    def validate_payment(self, payload: str, currency: str, total_amount: int) -> bool:
        return (
            self.enabled
            and payload == payment_payload(self.settings)
            and currency == PAYMENT_CURRENCY
            and total_amount == self.settings.stars_price
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.state_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._lock:
            if self._ready:
                return

            db_path = Path(self.settings.state_db_path)
            if db_path.parent != Path("."):
                db_path.parent.mkdir(parents=True, exist_ok=True)

            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        credits INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS payments (
                        telegram_payment_charge_id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        payload TEXT NOT NULL,
                        stars INTEGER NOT NULL,
                        credits INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS free_users (
                        user_id INTEGER PRIMARY KEY,
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS usage_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        credits_delta INTEGER NOT NULL,
                        kind TEXT NOT NULL,
                        prompt_preview TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    );
                    """
                )
                now = utc_now()
                for user_id in self.settings.free_user_ids:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO free_users (user_id, note, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (user_id, "seeded from FREE_USER_IDS", now),
                    )

            self._ready = True

    def _ensure_user(self, conn: sqlite3.Connection, user_id: int) -> None:
        now = utc_now()
        conn.execute(
            """
            INSERT OR IGNORE INTO users (user_id, credits, created_at, updated_at)
            VALUES (?, 0, ?, ?)
            """,
            (user_id, now, now),
        )

    def _has_free_access(self, user_id: int) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM free_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row is not None

    def _get_balance(self, user_id: int) -> int:
        with self._lock, self._connect() as conn:
            self._ensure_user(conn, user_id)
            row = conn.execute(
                "SELECT credits FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["credits"])

    def _reserve(self, user_id: int, cost: int, kind: str, prompt: str) -> ReserveResult:
        with self._lock, self._connect() as conn:
            self._ensure_user(conn, user_id)
            row = conn.execute(
                "SELECT credits FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            balance = int(row["credits"])
            if balance < cost:
                return ReserveResult(False, False, False, balance, cost)

            new_balance = balance - cost
            now = utc_now()
            conn.execute(
                "UPDATE users SET credits = ?, updated_at = ? WHERE user_id = ?",
                (new_balance, now, user_id),
            )
            conn.execute(
                """
                INSERT INTO usage_events (user_id, credits_delta, kind, prompt_preview, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, -cost, kind, prompt[:180], now),
            )
            return ReserveResult(True, True, False, new_balance, cost)

    def _refund(self, user_id: int, cost: int, kind: str) -> None:
        with self._lock, self._connect() as conn:
            self._ensure_user(conn, user_id)
            now = utc_now()
            conn.execute(
                """
                UPDATE users
                SET credits = credits + ?, updated_at = ?
                WHERE user_id = ?
                """,
                (cost, now, user_id),
            )
            conn.execute(
                """
                INSERT INTO usage_events (user_id, credits_delta, kind, prompt_preview, created_at)
                VALUES (?, ?, ?, '', ?)
                """,
                (user_id, cost, f"refund:{kind}", now),
            )

    def _record_payment(
        self,
        user_id: int,
        charge_id: str,
        payload: str,
        stars: int,
        credits: int,
    ) -> PaymentResult:
        with self._lock, self._connect() as conn:
            self._ensure_user(conn, user_id)
            now = utc_now()
            try:
                conn.execute(
                    """
                    INSERT INTO payments (
                        telegram_payment_charge_id,
                        user_id,
                        payload,
                        stars,
                        credits,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (charge_id, user_id, payload, stars, credits, now),
                )
            except sqlite3.IntegrityError:
                return PaymentResult(False, self._get_balance_in_conn(conn, user_id))

            conn.execute(
                """
                UPDATE users
                SET credits = credits + ?, updated_at = ?
                WHERE user_id = ?
                """,
                (credits, now, user_id),
            )
            conn.execute(
                """
                INSERT INTO usage_events (user_id, credits_delta, kind, prompt_preview, created_at)
                VALUES (?, ?, 'payment', ?, ?)
                """,
                (user_id, credits, charge_id, now),
            )
            return PaymentResult(True, self._get_balance_in_conn(conn, user_id))

    def _get_balance_in_conn(self, conn: sqlite3.Connection, user_id: int) -> int:
        row = conn.execute(
            "SELECT credits FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["credits"]) if row else 0

    def _add_free_user(self, user_id: int, note: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO free_users (user_id, note, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET note = excluded.note
                """,
                (user_id, note, utc_now()),
            )

    def _remove_free_user(self, user_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM free_users WHERE user_id = ?", (user_id,))

    def _list_free_users(self) -> list[FreeUser]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, note, created_at
                FROM free_users
                ORDER BY user_id
                """
            ).fetchall()
            return [
                FreeUser(
                    user_id=int(row["user_id"]),
                    note=str(row["note"]),
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]
