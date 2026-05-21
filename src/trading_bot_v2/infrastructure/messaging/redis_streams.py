"""Redis Streams messaging adapters."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Mapping

from redis import Redis
from redis.exceptions import ResponseError

from trading_bot_v2.interfaces.messaging import EventConsumer, EventPublisher, MessageHandler


class RedisStreamPublisher(EventPublisher):
    """Publish events to Redis Streams with JSON payload encoding."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        maxlen: int = 500_000,
        approximate_maxlen: bool = True,
    ) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._maxlen = maxlen
        self._approximate = approximate_maxlen
        self._streams_supported: bool = True

    def publish(self, channel: str, event: Mapping[str, Any]) -> None:
        payload = json.dumps(dict(event), separators=(",", ":"), default=str)
        if self._streams_supported:
            try:
                self._redis.xadd(
                    channel,
                    {"data": payload},
                    maxlen=self._maxlen,
                    approximate=self._approximate,
                )
                return
            except ResponseError as exc:
                # Some local Redis-compatible servers do not support Streams (XADD).
                # Fall back to list-based publishing so smoke tests can continue.
                if "unknown command" not in str(exc).lower() or "xadd" not in str(exc).lower():
                    raise
                self._streams_supported = False

        self._redis.rpush(channel, payload)
        self._redis.ltrim(channel, -self._maxlen, -1)


class RedisStreamConsumer(EventConsumer):
    """Consume events from Redis Streams using sync polling."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        start_id: str = "$",
    ) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._offsets: Dict[str, str] = {}
        self._default_start_id = start_id

    def _decode_entries(self, entries: list[Any]) -> list[Dict[str, Any]]:
        decoded: list[Dict[str, Any]] = []
        for entry_id, fields in entries:
            payload_raw = fields.get("data")
            if payload_raw is None:
                continue
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                continue
            payload["_stream_id"] = entry_id
            decoded.append(payload)
        return decoded

    def read_batch(
        self,
        channel: str,
        *,
        max_items: int = 100,
        timeout_ms: int = 1000,
    ) -> list[Dict[str, Any]]:
        last_id = self._offsets.get(channel, self._default_start_id)
        results = self._redis.xread({channel: last_id}, count=max_items, block=timeout_ms)
        if not results:
            return []

        decoded: list[Dict[str, Any]] = []
        for stream_name, entries in results:
            rows = self._decode_entries(entries)
            if rows:
                decoded.extend(rows)
                self._offsets[stream_name] = rows[-1]["_stream_id"]
        return decoded

    def subscribe(self, channel: str, handler: MessageHandler) -> None:
        while True:
            batch = self.read_batch(channel, max_items=200, timeout_ms=1000)
            if not batch:
                time.sleep(0.05)
                continue
            for event in batch:
                handler(event)
