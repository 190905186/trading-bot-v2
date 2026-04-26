"""Risk service skeleton."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from trading_bot_v2.interfaces.risk import RiskManager, TrailingStopManager


class RiskService:
    """Coordinates pre-trade validation and TSL state snapshots."""

    def __init__(self, risk_manager: RiskManager, tsl_manager: TrailingStopManager) -> None:
        self._risk = risk_manager
        self._tsl = tsl_manager

    def validate_signal(self, signal_payload: Mapping[str, Any]) -> tuple[bool, str]:
        return self._risk.validate_order_intent(signal_payload)

    def update_price(self, instrument_id: str, last_price: float, **kwargs: Any) -> None:
        self._tsl.update_price(instrument_id, last_price, **kwargs)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kill_switch_active": self._risk.is_kill_switch_active(),
            "tsl": dict(self._tsl.get_snapshot()),
        }
