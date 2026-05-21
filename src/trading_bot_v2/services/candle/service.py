"""Candle production service: live aggregation envelope + optional historical backfill."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from trading_bot_v2.domain.contracts import CandleEvent
from trading_bot_v2.interfaces.candles import CandleProvider
from trading_bot_v2.interfaces.messaging import EventPublisher
from trading_bot_v2.services.candle.payloads import normalized_ohlc_row_to_closed_payload


class CandleService:
    """Publishes closed candle events from tick aggregation and/or broker candle APIs."""

    def __init__(
        self,
        publisher: EventPublisher,
        *,
        provider: Optional[CandleProvider] = None,
        producer_label: str = "candle-service",
    ) -> None:
        self._publisher = publisher
        self._provider = provider
        self._producer_label = producer_label
        self._closed_candles_published_total = 0
        self._backfill_bars_total = 0
        self._last_backfill: Optional[Dict[str, Any]] = None

    @property
    def provider(self) -> Optional[CandleProvider]:
        """Historical fetcher, if configured."""
        return self._provider

    def publish_closed_candle(self, candle_payload: Dict[str, Any]) -> None:
        self._closed_candles_published_total += 1
        event = CandleEvent(producer=self._producer_label, payload=candle_payload)
        self._publisher.publish(event.event_name, event.to_dict())

    async def backfill_closed_minute_candles(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> int:
        """
        Pull 1-minute history from :attr:`provider` and publish each bar as ``candles.1m.closed``.

        Rows are normalized to the same payload shape as :class:`MinuteCandleAggregator`.
        """
        if self._provider is None:
            raise RuntimeError("No CandleProvider configured; cannot backfill.")
        rows = await self._provider.fetch_minute_candles(instrument_token, from_dt, to_dt)
        broker = self._provider.provider_name
        count = 0
        for row in rows:
            # AngelOne may tag each merged futures bar with publish token after EQ→FUT stitching.
            if isinstance(row, dict):
                pub = row.pop("__publish_token__", None)
            else:
                pub = None
            tok = pub if isinstance(pub, str) and pub else str(instrument_token)
            payload = normalized_ohlc_row_to_closed_payload(row, broker=broker, token=tok)
            if payload is None:
                continue
            self.publish_closed_candle(payload)
            count += 1
        self._backfill_bars_total += count
        self._last_backfill = {
            "instrument_token": instrument_token,
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "bars_published": count,
        }
        return count

    def dashboard_runtime_metadata(self) -> Dict[str, Any]:
        """Slow-changing and counters for dashboard heartbeats (``metadata`` on ``service.heartbeat``)."""
        info: Dict[str, Any] = {
            "role": "candles",
            "closed_candles_published_total": self._closed_candles_published_total,
            "backfill_bars_published_total": self._backfill_bars_total,
        }
        if self._provider is not None:
            info["candle_historical_provider"] = self._provider.provider_name
            info["candle_broker_instance_id"] = self._provider.broker_instance_id
        else:
            info["candle_historical_provider"] = "none"
        if self._last_backfill is not None:
            info["candle_last_backfill"] = dict(self._last_backfill)
        return info
