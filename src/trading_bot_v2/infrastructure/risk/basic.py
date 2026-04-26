"""Basic risk manager for local integration flow."""

from __future__ import annotations

from typing import Any, Mapping

from trading_bot_v2.interfaces.risk import RiskManager


class BasicRiskManager(RiskManager):
    """Simple risk guardrails with kill-switch support."""

    def __init__(self, max_notional: float = 1_000_000.0) -> None:
        self._max_notional = max_notional
        self._kill_switch = False

    def validate_order_intent(self, signal_event: Mapping[str, Any]) -> tuple[bool, str]:
        if self._kill_switch:
            return False, "kill_switch_active"
        order_request = signal_event.get("order_request", {})
        price = float(order_request.get("price", signal_event.get("last_price", 0.0)) or 0.0)
        quantity = int(order_request.get("quantity", 1) or 1)
        notional = price * quantity
        if notional > self._max_notional:
            return False, f"notional_limit_exceeded:{notional:.2f}"
        return True, "ok"

    def is_kill_switch_active(self) -> bool:
        return self._kill_switch

    def set_kill_switch(self, enabled: bool) -> None:
        self._kill_switch = enabled
