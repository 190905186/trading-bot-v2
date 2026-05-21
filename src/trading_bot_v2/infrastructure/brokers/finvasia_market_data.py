"""Finvasia (Shoonya) websocket market data adapter."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import types
from typing import Iterable, Optional

from trading_bot_v2.interfaces.broker import MarketDataAdapter, TickCallback
from trading_bot_v2.services.ticks.serialize import prepare_tick_payload
from trading_bot_v2.services.ticks.tick_context import TickMappingContext
from trading_bot_v2.services.ticks.unified_mapper import map_finvasia_tick

logger = logging.getLogger("trading_bot_v2.brokers.finvasia_market_data")


class FinvasiaMarketDataAdapter(MarketDataAdapter):
    """Connects to Finvasia websocket and emits normalized tick payloads."""

    def __init__(
        self,
        *,
        user_id: str,
        password: str,
        twofa: str,
        api_key: str,
        access_token: str = "",
        susertoken: str = "",
        account_id: str = "",
        feed_type: str = "t",
        tick_context: Optional[TickMappingContext] = None,
        batch: str | int | None = None,
    ) -> None:
        try:
            from NorenRestApiPy.NorenApi import NorenApi  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "NorenRestApiPy is required for Finvasia adapter. Install dependencies in .venv."
            ) from exc

        self._broker_name = "finvasia"
        self._user_id = user_id
        self._password = password
        self._twofa = twofa
        self._api_key = api_key
        self._access_token = access_token
        self._susertoken = susertoken
        self._account_id = account_id.strip()
        self._feed_type = feed_type or "t"
        self._handler: TickCallback | None = None
        self._ctx = tick_context or TickMappingContext()
        self._batch = batch
        self._subscribed_tokens: list[str] = []
        self._latest_by_token: dict[str, dict] = {}
        host = os.getenv("TB2_FINVASIA_HOST", "https://api.shoonya.com/NorenWClientAPI").strip()
        if not host.endswith("/"):
            host += "/"
        # OAuth accounts must use NorenWSAPI (not legacy NorenWSTP used by QuickAuth sessions).
        websocket = os.getenv(
            "TB2_FINVASIA_WEBSOCKET", "wss://api.shoonya.com/NorenWSAPI/"
        ).strip()
        self._api = NorenApi(host=host, websocket=websocket)
        logger.info("Finvasia NorenApi host=%r websocket=%r", host, websocket)
        self._ws_thread: threading.Thread | None = None
        self._ticks_emitted: int = 0
        # Noren calls socket_open_callback only for s=='OK'; Shoonya often sends 'Ok' (error path).
        self._finvasia_ws_subscribed: bool = False

    @property
    def broker_name(self) -> str:
        return self._broker_name

    def set_tick_handler(self, handler: TickCallback) -> None:
        self._handler = handler

    def subscribe(self, instruments: Iterable[str]) -> None:
        # Finvasia websocket expects strings like "NSE|1594" or "NFO|12345".
        tokens: list[str] = []
        for instrument in instruments:
            raw = str(instrument).strip()
            if not raw:
                continue
            if "|" in raw:
                tokens.append(raw)
            else:
                tokens.append(f"NSE|{raw}")
        self._subscribed_tokens = tokens
        if not tokens:
            logger.warning(
                "Finvasia subscribe list is empty after parsing TB2_INSTRUMENTS; "
                "no symbols will be requested and ticks.raw will stay empty."
            )

    def _authenticate(self) -> None:
        """Configure Noren session.

        The vendored NorenRestApiPy wheel often ships with ``login()`` commented out, so
        password + TOTP cannot be used from this adapter. Use OAuth access token and/or
        susertoken from Shoonya (see TB2_FINVASIA_* env vars).

        WebSocket handshake sends ``self.__access_token`` inside NorenApi (name-mangled to
        ``_NorenApi__access_token``). Assigning ``api.__access_token = x`` from outside does
        **not** touch that field—``accesstoken`` becomes null and the server never acks.
        Always use ``set_session`` / ``set_credentials`` on ``NorenApi`` instead.

        WebSocket payload historically uses the session/susertoken while REST may use a
        separate OAuth JWT in ``Authorization`` (``injectOAuthHeader``).

        Noren's bundled ``__on_open_callback`` sets websocket ``actid`` equal to ``uid``.
        Shoonya expects ``actid`` to be the OAuth ``actid`` (often equal to ``uid``, but not
        always). We patch the open handler and pass the right ``AID`` into ``injectOAuthHeader``.
        """
        access = self._access_token.strip()
        sus = self._susertoken.strip()
        act_id = (self._account_id or self._user_id).strip()

        if access:
            session_tok = sus or access
            self._api.set_session(act_id, self._password, session_tok, session_tok)
            self._api.injectOAuthHeader(access, act_id, act_id)
            self._patch_shoonya_websocket_handshake()
            logger.info(
                "Finvasia authenticated with OAuth header; ws session token from %s; actid=%r",
                "TB2_FINVASIA_SUSER_TOKEN" if sus else "TB2_FINVASIA_ACCESS_TOKEN",
                act_id,
            )
            return

        if sus:
            # self._api.set_session(self._user_id, self._password, sus, sus)
            self._api.injectOAuthHeader(sus, self._user_id, act_id)
            # self._patch_shoonya_websocket_handshake()
            logger.info(
                "Finvasia authenticated with TB2_FINVASIA_SUSER_TOKEN via set_session; actid=%r",
                act_id,
            )
            return

        raise RuntimeError(
            "Finvasia market data requires TB2_FINVASIA_ACCESS_TOKEN (OAuth JWT) and/or "
            "TB2_FINVASIA_SUSER_TOKEN. The installed NorenRestApiPy build does not expose "
            "password login, so credentials alone are not enough. After OAuth, set both "
            "tokens in .env if your flow returns them separately."
        )

    def _patch_shoonya_websocket_handshake(self) -> None:
        """Replace Noren ``__on_open_callback`` so ``actid`` is ``__accountid``, not ``uid``."""

        api = self._api

        def shoonya_open(noren_self, ws=None):  # noqa: ARG001
            noren_self._NorenApi__websocket_connected = True
            uid = noren_self._NorenApi__username
            actid = noren_self._NorenApi__accountid or uid
            tok = noren_self._NorenApi__access_token
            values = {"t": "a", "uid": uid, "actid": actid, "accesstoken": tok, "source": "API"}
            payload = json.dumps(values)
            try:
                from NorenRestApiPy.NorenApi import reportmsg  # type: ignore

                reportmsg(payload)
            except Exception:
                logger.debug("Finvasia ws auth payload: %s", payload)
            logger.info(
                "Finvasia websocket auth: uid=%r actid=%r accesstoken_set=%s",
                uid,
                actid,
                bool(tok),
            )
            noren_self._NorenApi__ws_send(payload)

        api._NorenApi__on_open_callback = types.MethodType(shoonya_open, api)  # type: ignore[method-assign]

    def connect(self) -> None:
        self._authenticate()

        def run_ws() -> None:
            try:
                self._api.start_websocket(
                    order_update_callback=self._on_order_update,
                    subscribe_callback=self._on_tick,
                    socket_open_callback=self._on_open,
                    socket_error_callback=self._on_ws_error,
                )
            except Exception:
                logger.exception("Finvasia start_websocket failed")

        self._ws_thread = threading.Thread(target=run_ws, daemon=True, name="finvasia-ws")
        self._ws_thread.start()

    def disconnect(self) -> None:
        self._finvasia_ws_subscribed = False
        # Noren API may expose different close methods by version.
        for method_name in ("close_websocket", "close_socket"):
            method = getattr(self._api, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        if self._ws_thread and self._ws_thread.is_alive():
            time.sleep(0.2)

    def _on_ws_error(self, err: object = None) -> None:  # pragma: no cover - network callback
        """NorenRestApiPy mis-classifies Shoonya acks: ``s == 'Ok'`` is routed here because
        the library only treats exact ``s == 'OK'`` as success, then returns without calling
        ``socket_open_callback``—so no subscribe runs and only pings are seen.
        """
        if isinstance(err, dict):
            t = str(err.get("t", "")).lower()
            raw_status = err.get("s", err.get("stat", ""))
            ok = str(raw_status).strip().lower() in {"ok", "okay"}
            if t in {"ak", "ck"} and ok:
                logger.info("Finvasia websocket session ack (%s, stat=%r); proceeding to subscribe", t, raw_status)
                self._on_open()
                return
        logger.error("Finvasia websocket reported error: %s", err)

    def _on_open(self) -> None:  # pragma: no cover - network callback
        if self._finvasia_ws_subscribed:
            logger.debug("Finvasia: subscribe already sent; skipping duplicate _on_open")
            return
        if not self._subscribed_tokens:
            logger.error(
                "Finvasia WebSocket session acknowledged but subscription list is empty; "
                "check TB2_INSTRUMENTS (expect EXCHANGE|token, e.g. NSE|22)."
            )
            return
        try:
            self._api.subscribe(self._subscribed_tokens, feed_type=self._feed_type)
            self._finvasia_ws_subscribed = True
            logger.info(
                "Finvasia subscribed %d scrip(s) (feed_type=%r): %s",
                len(self._subscribed_tokens),
                self._feed_type,
                ", ".join(self._subscribed_tokens[:12])
                + ("…" if len(self._subscribed_tokens) > 12 else ""),
            )
        except Exception:
            logger.exception("Finvasia subscribe failed")

    def _on_order_update(self, raw_order: dict) -> None:  # pragma: no cover - network callback
        return

    def _on_tick(self, raw_tick: dict) -> None:  # pragma: no cover - network callback
        if not self._handler:
            return
        try:
            if not isinstance(raw_tick, dict):
                logger.warning("Finvasia tick ignored (not a dict): %r", raw_tick)
                return
            token = str(raw_tick.get("tk", ""))
            previous = self._latest_by_token.get(token, {})
            merged = {**previous, **raw_tick}
            self._latest_by_token[token] = merged

            unified = map_finvasia_tick(merged, self._ctx, batch=self._batch)
            self._handler(prepare_tick_payload(unified))
            self._ticks_emitted += 1
            if self._ticks_emitted == 1:
                logger.info("Finvasia first tick emitted for token=%s", token)
        except Exception:
            logger.exception("Finvasia tick handler failed")
