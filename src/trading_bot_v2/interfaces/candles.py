"""Port for historical OHLC candle fetches (backfill / analytics)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List


class CandleProvider(ABC):
    """
    Minimal contract for minute (or sub-daily) historical candles.

    Implementations should run blocking HTTP/SDK work in a thread
    (for example ``asyncio.to_thread``) so callers can stay async.
    """

    @property
    @abstractmethod
    def broker_instance_id(self) -> str:
        """Unique id for this connection (metrics / logging keys)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider type, e.g. ``zerodha``, ``finvasia``."""

    @abstractmethod
    async def fetch_minute_candles(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Return candles between ``from_dt`` and ``to_dt`` (broker semantics apply).

        Each item should include at least: ``date`` (datetime), ``open``, ``high``,
        ``low``, ``close``, ``volume`` (and ``oi`` if available). Implementations may
        add optional analytics fields (for example ``close_eq``, rolling averages, and
        ``premium_discount``) when aligned cash and futures history is available.
        """
