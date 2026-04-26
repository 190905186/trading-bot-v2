"""Zerodha KiteTicker-based market data adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from trading_bot_v2.interfaces.broker import MarketDataAdapter, TickCallback


class ZerodhaMarketDataAdapter(MarketDataAdapter):
    """Connects to Zerodha websocket and emits normalized tick payloads."""

    def __init__(self, api_key: str, access_token: str) -> None:
        if not api_key:
            raise ValueError("Missing Zerodha api_key")
        if not access_token:
            raise ValueError("Missing Zerodha access_token")

        try:
            from kiteconnect import KiteTicker  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "kiteconnect is required for Zerodha adapter. Install dependencies in .venv."
            ) from exc

        self._broker_name = "zerodha"
        self._handler: TickCallback | None = None
        self._tokens_to_subscribe: list[int] = []
        self._kws = KiteTicker(api_key, access_token)
        self._wire_callbacks()

    @property
    def broker_name(self) -> str:
        return self._broker_name

    def _wire_callbacks(self) -> None:
        self._kws.on_connect = self._on_connect
        self._kws.on_ticks = self._on_ticks
        self._kws.on_close = self._on_close
        self._kws.on_error = self._on_error

    def set_tick_handler(self, handler: TickCallback) -> None:
        self._handler = handler

    def subscribe(self, instruments: Iterable[str]) -> None:
        tokens: list[int] = []
        for instrument in instruments:
            raw = str(instrument).strip()
            if not raw:
                continue
            try:
                tokens.append(int(raw))
            except ValueError:
                # Zerodha websocket requires instrument_token ints.
                continue
        self._tokens_to_subscribe = tokens

    def connect(self) -> None:
        self._kws.connect(threaded=True)

    def disconnect(self) -> None:
        self._kws.close()

    def _on_connect(self, ws, response) -> None:  # pragma: no cover - network callback
        if not self._tokens_to_subscribe:
            return
        ws.subscribe(self._tokens_to_subscribe)
        ws.set_mode(ws.MODE_FULL, self._tokens_to_subscribe)

    def _on_close(self, ws, code, reason) -> None:  # pragma: no cover - network callback
        return

    def _on_error(self, ws, code, reason) -> None:  # pragma: no cover - network callback
        return

    def _on_ticks(self, ws, ticks: list[dict]) -> None:  # pragma: no cover - network callback
        if not self._handler:
            return
        for raw_tick in ticks:
            instrument_token = raw_tick.get("instrument_token")
            depth = raw_tick.get("depth") or {}
            buy_depth = depth.get("buy") or []
            sell_depth = depth.get("sell") or []
            best_bid = buy_depth[0].get("price") if buy_depth else None
            best_ask = sell_depth[0].get("price") if sell_depth else None

            ts = raw_tick.get("exchange_timestamp") or raw_tick.get("last_trade_time")
            if isinstance(ts, datetime):
                ts_iso = ts.astimezone(timezone.utc).isoformat()
            else:
                ts_iso = datetime.now(timezone.utc).isoformat()

            payload = {
                "broker": self._broker_name,
                "token": str(instrument_token),
                "instrument_id": str(instrument_token),
                "timestamp": ts_iso,
                "last_price": raw_tick.get("last_price"),
                "volume": raw_tick.get("volume_traded", 0),
                "bid": best_bid,
                "ask": best_ask,
                "ohlc": raw_tick.get("ohlc", {}),
            }
            self._handler(payload)
