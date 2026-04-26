"""Mock market-data adapter for local end-to-end testing."""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, Mapping

from trading_bot_v2.interfaces.broker import MarketDataAdapter, TickCallback


class MockMarketDataAdapter(MarketDataAdapter):
    """Generates synthetic ticks for configured instruments."""

    def __init__(self, broker_name: str = "zerodha", tick_interval_seconds: float = 0.2) -> None:
        self._broker_name = broker_name
        self._tick_interval_seconds = max(0.01, tick_interval_seconds)
        self._handler: TickCallback | None = None
        self._instruments: list[str] = []
        self._prices: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def broker_name(self) -> str:
        return self._broker_name

    def set_tick_handler(self, handler: TickCallback) -> None:
        self._handler = handler

    def subscribe(self, instruments: Iterable[str]) -> None:
        self._instruments = [str(ins).strip() for ins in instruments if str(ins).strip()]
        for instrument in self._instruments:
            self._prices.setdefault(instrument, random.uniform(80.0, 450.0))

    def connect(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"mock-md-{self._broker_name}")
        self._thread.start()

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _next_price(self, instrument: str) -> float:
        last = self._prices.get(instrument, 100.0)
        jump = random.uniform(-0.7, 0.7)
        new_price = max(1.0, last + jump)
        self._prices[instrument] = new_price
        return round(new_price, 2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if not self._handler or not self._instruments:
                time.sleep(self._tick_interval_seconds)
                continue

            now = datetime.now(timezone.utc).isoformat()
            for instrument in self._instruments:
                last_price = self._next_price(instrument)
                volume = random.randint(1, 250)
                tick_payload: Mapping[str, object] = {
                    "broker": self._broker_name,
                    "token": instrument,
                    "instrument_id": instrument,
                    "timestamp": now,
                    "last_price": last_price,
                    "volume": volume,
                    "bid": round(last_price - random.uniform(0.01, 0.15), 2),
                    "ask": round(last_price + random.uniform(0.01, 0.15), 2),
                }
                self._handler(tick_payload)
            time.sleep(self._tick_interval_seconds)
