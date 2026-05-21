"""SQLite persistence for ticks and candles (all brokers in one database)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


def sqlite_path_from_env() -> Path:
    raw = os.getenv("TB2_SQLITE_PATH", "").strip()
    if raw:
        return Path(raw).resolve()
    root = Path(__file__).resolve().parents[4]
    return (root / "data" / "trading_bot_v2.db").resolve()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteEventStore:
    """Thread-safe SQLite writer for tick and candle events."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = (db_path or sqlite_path_from_env()).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._path

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    broker TEXT NOT NULL,
                    token TEXT,
                    exchange_token TEXT,
                    instrument_token TEXT,
                    symbol_name TEXT,
                    timestamp TEXT,
                    last_price REAL,
                    event_id TEXT,
                    payload_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ticks_broker ON ticks(broker);
                CREATE INDEX IF NOT EXISTS idx_ticks_inserted ON ticks(inserted_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ticks_event_id ON ticks(event_id)
                    WHERE event_id IS NOT NULL AND event_id != '';

                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    broker TEXT NOT NULL,
                    token TEXT NOT NULL,
                    candle_start TEXT NOT NULL,
                    candle_end TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    oi REAL,
                    payload_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    UNIQUE(broker, token, candle_start)
                );
                CREATE INDEX IF NOT EXISTS idx_candles_broker ON candles(broker);
                CREATE INDEX IF NOT EXISTS idx_candles_inserted ON candles(inserted_at);

                CREATE TABLE IF NOT EXISTS store_counters (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO store_counters(key, value) VALUES ('ticks', 0);
                INSERT OR IGNORE INTO store_counters(key, value) VALUES ('candles', 0);
                """
            )
            self._conn.commit()

    def _increment_counter(self, key: str, *, conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE store_counters SET value = value + 1 WHERE key = ?",
            (key,),
        )

    def insert_tick(self, event: Mapping[str, Any]) -> bool:
        payload = event.get("payload", event)
        if not isinstance(payload, dict):
            return False
        broker = str(payload.get("broker", "unknown"))
        token = payload.get("token") or payload.get("exchange_token")
        row = (
            broker,
            str(token) if token is not None else None,
            str(payload.get("exchange_token")) if payload.get("exchange_token") is not None else None,
            str(payload.get("instrument_token")) if payload.get("instrument_token") is not None else None,
            payload.get("symbol_name"),
            str(payload.get("timestamp")) if payload.get("timestamp") is not None else None,
            _safe_float(payload.get("last_price")),
            str(event.get("event_id", "")) or None,
            json.dumps(dict(payload), separators=(",", ":"), default=str),
            _utc_now_iso(),
        )
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO ticks (
                    broker, token, exchange_token, instrument_token, symbol_name,
                    timestamp, last_price, event_id, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            if cur.rowcount > 0:
                self._increment_counter("ticks", conn=self._conn)
            self._conn.commit()
            return cur.rowcount > 0

    def insert_candle(self, event: Mapping[str, Any]) -> bool:
        payload = event.get("payload", event)
        if not isinstance(payload, dict):
            return False
        broker = str(payload.get("broker", "unknown"))
        token = str(payload.get("token", payload.get("instrument_id", "UNKNOWN")))
        candle_start = str(payload.get("candle_start", ""))
        if not candle_start:
            return False
        row = (
            broker,
            token,
            candle_start,
            str(payload.get("candle_end")) if payload.get("candle_end") is not None else None,
            _safe_float(payload.get("open")),
            _safe_float(payload.get("high")),
            _safe_float(payload.get("low")),
            _safe_float(payload.get("close")),
            int(float(payload.get("volume", 0) or 0)),
            _safe_float(payload.get("oi")) if payload.get("oi") is not None else None,
            json.dumps(dict(payload), separators=(",", ":"), default=str),
            _utc_now_iso(),
        )
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO candles (
                    broker, token, candle_start, candle_end,
                    open, high, low, close, volume, oi, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            if cur.rowcount > 0:
                self._increment_counter("candles", conn=self._conn)
            self._conn.commit()
            return cur.rowcount > 0

    def count_ticks(self) -> int:
        return self._counter_value("ticks")

    def count_candles(self) -> int:
        return self._counter_value("candles")

    def _counter_value(self, key: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM store_counters WHERE key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                return int(row[0])
            row = self._conn.execute(f"SELECT COUNT(*) FROM {key}").fetchone()
            return int(row[0]) if row else 0

    def counts_by_broker(self) -> dict[str, dict[str, int]]:
        with self._lock:
            tick_rows = self._conn.execute(
                "SELECT broker, COUNT(*) FROM ticks GROUP BY broker"
            ).fetchall()
            candle_rows = self._conn.execute(
                "SELECT broker, COUNT(*) FROM candles GROUP BY broker"
            ).fetchall()
        return {
            "ticks": {str(b): int(c) for b, c in tick_rows},
            "candles": {str(b): int(c) for b, c in candle_rows},
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
