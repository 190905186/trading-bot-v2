"""Zerodha KiteTicker-based market data adapter."""



from __future__ import annotations



from typing import Iterable, Optional



from trading_bot_v2.interfaces.broker import MarketDataAdapter, TickCallback

from trading_bot_v2.services.ticks.serialize import prepare_tick_payload

from trading_bot_v2.services.ticks.tick_context import TickMappingContext

from trading_bot_v2.services.ticks.unified_mapper import map_zerodha_tick





class ZerodhaMarketDataAdapter(MarketDataAdapter):

    """Connects to Zerodha websocket and emits unified-schema tick payloads."""



    def __init__(

        self,

        api_key: str,

        access_token: str,

        *,

        session_label: str = "",

        max_tokens_per_session: int = 3000,

        tick_context: Optional[TickMappingContext] = None,

        batch: str | int | None = None,

    ) -> None:

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

        self._session_label = session_label or "default"

        self._max_tokens = max(1, int(max_tokens_per_session))

        self._ctx = tick_context or TickMappingContext()

        self._batch = batch

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

                continue

        if len(tokens) > self._max_tokens:

            raise ValueError(

                f"Zerodha session {self._session_label!r}: {len(tokens)} tokens exceeds "

                f"max {self._max_tokens} per websocket (TB2_ZERODHA_MAX_TOKENS_PER_SESSION)."

            )

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

            unified = map_zerodha_tick(raw_tick, self._ctx, batch=self._batch)

            self._handler(prepare_tick_payload(unified))


