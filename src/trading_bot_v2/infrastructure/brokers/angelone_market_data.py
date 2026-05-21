"""AngelOne websocket market data adapter."""

from __future__ import annotations

from typing import Iterable, Optional

from trading_bot_v2.interfaces.broker import MarketDataAdapter, TickCallback
from trading_bot_v2.services.ticks.serialize import prepare_tick_payload
from trading_bot_v2.services.ticks.tick_context import TickMappingContext
from trading_bot_v2.services.ticks.unified_mapper import map_angelone_tick


class AngelOneMarketDataAdapter(MarketDataAdapter):
    """Connects to AngelOne SmartWebSocketV2 and emits normalized tick payloads."""

    def __init__(
        self,
        *,
        api_key: str,
        client_code: str,
        password: str,
        totp_secret: str,
        feed_token: str = "",
        jwt_token: str = "",
        tick_context: Optional[TickMappingContext] = None,
        batch: str | int | None = None,
    ) -> None:
        try:
            from SmartApi import SmartConnect  # type: ignore
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "smartapi-python is required for AngelOne adapter. Install dependencies in .venv."
            ) from exc

        self._SmartConnect = SmartConnect
        self._SmartWebSocketV2 = SmartWebSocketV2
        self._broker_name = "angelone"
        self._api_key = api_key
        self._client_code = client_code
        self._password = password
        self._totp_secret = totp_secret
        self._feed_token = feed_token
        self._jwt_token = jwt_token
        self._handler: TickCallback | None = None
        self._token_list: list[dict] = []
        self._sws = None
        self._ctx = tick_context or TickMappingContext()
        self._batch = batch

    @property
    def broker_name(self) -> str:
        return self._broker_name

    def set_tick_handler(self, handler: TickCallback) -> None:
        self._handler = handler

    def subscribe(self, instruments: Iterable[str]) -> None:
        grouped: dict[int, list[str]] = {}
        for instrument in instruments:
            raw = str(instrument).strip()
            if not raw:
                continue
            if "|" in raw:
                exch_raw, token = raw.split("|", 1)
                try:
                    exch_type = int(exch_raw)
                except ValueError:
                    exch_type = 1
            elif ":" in raw:
                exch_name, token = raw.split(":", 1)
                exch_type = 2 if exch_name.upper() == "NFO" else 1
            else:
                exch_type, token = 1, raw
            grouped.setdefault(exch_type, []).append(token)
        self._token_list = [{"exchangeType": exch, "tokens": tokens} for exch, tokens in grouped.items()]

    def _ensure_session(self) -> None:
        if self._jwt_token and self._feed_token:
            return
        if not all([self._api_key, self._client_code, self._password, self._totp_secret]):
            raise RuntimeError(
                "Missing AngelOne credentials. Need API key, client code, password, and TOTP secret."
            )
        try:
            from pyotp import TOTP  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pyotp is required to login AngelOne.") from exc

        sc = self._SmartConnect(api_key=self._api_key)
        session = sc.generateSession(self._client_code, self._password, TOTP(self._totp_secret).now())
        data = session.get("data", {}) if isinstance(session, dict) else {}
        self._jwt_token = data.get("jwtToken", "") or self._jwt_token
        self._feed_token = data.get("feedToken", "") or self._feed_token or sc.getfeedToken()
        if not self._jwt_token or not self._feed_token:
            raise RuntimeError(f"AngelOne login failed to return tokens: {session}")

    def connect(self) -> None:
        self._ensure_session()
        self._sws = self._SmartWebSocketV2(
            self._jwt_token,
            api_key=self._api_key,
            client_code=self._client_code,
            feed_token=self._feed_token,
        )
        self._sws.on_open = self._on_open
        self._sws.on_data = self._on_data
        self._sws.on_error = self._on_error
        self._sws.connect()

    def disconnect(self) -> None:
        if not self._sws:
            return
        for method_name in ("close_connection", "close"):
            method = getattr(self._sws, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def _on_open(self, wsapp) -> None:  # pragma: no cover - network callback
        if not self._token_list:
            return
        correlation_id = "tb2_stream"
        mode = 3
        self._sws.subscribe(correlation_id, mode, self._token_list)

    def _on_error(self, wsapp, error) -> None:  # pragma: no cover - network callback
        return

    def _on_data(self, wsapp, message) -> None:  # pragma: no cover - network callback
        if not self._handler:
            return
        if not isinstance(message, dict):
            return

        unified = map_angelone_tick(message, self._ctx, batch=self._batch)
        self._handler(prepare_tick_payload(unified))
