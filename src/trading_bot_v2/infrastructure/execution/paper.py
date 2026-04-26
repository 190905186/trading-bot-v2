"""Paper execution adapter for local simulation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import uuid4

from trading_bot_v2.interfaces.broker import ExecutionAdapter


class PaperExecutionAdapter(ExecutionAdapter):
    """Simulates broker execution responses with in-memory state."""

    def __init__(self, broker_name: str = "paper") -> None:
        self._broker_name = broker_name
        self._orders: dict[str, dict[str, Any]] = {}
        self._realized_pnl = 0.0

    @property
    def broker_name(self) -> str:
        return self._broker_name

    def place_order(self, order_request: Mapping[str, Any]) -> Mapping[str, Any]:
        order_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        order = {
            "order_id": order_id,
            "status": "FILLED",
            "filled_at": now,
            "request": dict(order_request),
        }
        self._orders[order_id] = order
        return {
            "status": "SUCCESS",
            "message": "PAPER_FILLED",
            "data": order,
        }

    def modify_order(self, order_id: str, updates: Mapping[str, Any]) -> Mapping[str, Any]:
        if order_id not in self._orders:
            return {"status": "ERROR", "message": "ORDER_NOT_FOUND", "data": {"order_id": order_id}}
        self._orders[order_id]["request"].update(dict(updates))
        self._orders[order_id]["modified_at"] = datetime.now(timezone.utc).isoformat()
        return {"status": "SUCCESS", "message": "MODIFIED", "data": self._orders[order_id]}

    def cancel_order(self, order_id: str) -> Mapping[str, Any]:
        order = self._orders.get(order_id)
        if order is None:
            return {"status": "ERROR", "message": "ORDER_NOT_FOUND", "data": {"order_id": order_id}}
        order["status"] = "CANCELLED"
        order["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        return {"status": "SUCCESS", "message": "CANCELLED", "data": order}

    def get_order_status(self, order_id: str) -> Mapping[str, Any]:
        order = self._orders.get(order_id)
        if order is None:
            return {"status": "ERROR", "message": "ORDER_NOT_FOUND", "data": {"order_id": order_id}}
        return {"status": "SUCCESS", "message": "OK", "data": order}

    def get_position_pnl(self, instrument_id: Optional[str] = None) -> Mapping[str, Any]:
        return {
            "status": "SUCCESS",
            "message": "OK",
            "data": {
                "broker": self._broker_name,
                "instrument_id": instrument_id,
                "realized_pnl": self._realized_pnl,
                "positions": len(self._orders),
            },
        }
