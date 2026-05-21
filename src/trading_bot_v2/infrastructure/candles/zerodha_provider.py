"""Zerodha (Kite Connect) implementation of :class:`CandleProvider`."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from trading_bot_v2.interfaces.candles import CandleProvider

logger = logging.getLogger("trading_bot_v2.candles.zerodha")


class ZerodhaCandleProvider(CandleProvider):
    def __init__(
        self,
        broker_instance_id: str,
        api_key: str,
        access_token: str,
        *,
        continuous: bool = True,
    ) -> None:
        try:
            from kiteconnect import KiteConnect  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "kiteconnect is required for ZerodhaCandleProvider. Install project dependencies."
            ) from exc

        self._broker_instance_id = broker_instance_id
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)
        self._continuous = continuous

    @property
    def broker_instance_id(self) -> str:
        return self._broker_instance_id

    @property
    def provider_name(self) -> str:
        return "zerodha"

    async def fetch_minute_candles(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> List[Dict[str, Any]]:
        started_at = time.perf_counter()

        def _sync_call() -> List[Dict[str, Any]]:
            return self._kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval="minute",
                continuous=self._continuous,
                oi=True,
            )

        try:
            rows = await asyncio.to_thread(_sync_call)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.info(
                "[%s] token=%s from=%s to=%s rows=%s took_ms=%.1f",
                self.broker_instance_id,
                instrument_token,
                from_dt,
                to_dt,
                len(rows),
                elapsed_ms,
            )
            return rows
        except Exception as e:  # pragma: no cover - network
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.warning(
                "[%s] historical_data failed token=%s %s to %s took_ms=%.1f: %s",
                self.broker_instance_id,
                instrument_token,
                from_dt,
                to_dt,
                elapsed_ms,
                e,
            )
            return []
