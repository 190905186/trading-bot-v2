"""Order execution service skeleton."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from trading_bot_v2.domain.contracts import OrderIntentEvent, OrderUpdateEvent
from trading_bot_v2.interfaces.broker import ExecutionAdapter
from trading_bot_v2.interfaces.messaging import EventPublisher
from trading_bot_v2.interfaces.risk import RiskManager


class OrderService:
    """Validates signal intents, places orders, and emits updates."""

    def __init__(
        self,
        execution_adapter: ExecutionAdapter,
        risk_manager: RiskManager,
        publisher: EventPublisher,
    ) -> None:
        self._adapter = execution_adapter
        self._risk = risk_manager
        self._publisher = publisher

    def place_from_signal(self, signal_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        allowed, reason = self._risk.validate_order_intent(signal_payload)
        if not allowed:
            update = OrderUpdateEvent(
                producer=f"order-service:{self._adapter.broker_name}",
                payload={"status": "REJECTED_BY_RISK", "reason": reason, "signal": dict(signal_payload)},
            )
            self._publisher.publish(update.event_name, update.to_dict())
            return update.payload

        intent = OrderIntentEvent(
            producer=f"order-service:{self._adapter.broker_name}",
            payload=dict(signal_payload),
        )
        self._publisher.publish(intent.event_name, intent.to_dict())

        order_request: Dict[str, Any] = dict(signal_payload.get("order_request", {}))
        broker_response = self._adapter.place_order(order_request)
        update = OrderUpdateEvent(
            producer=f"order-service:{self._adapter.broker_name}",
            payload={"status": "SUBMITTED", "broker_response": broker_response, "signal": dict(signal_payload)},
        )
        self._publisher.publish(update.event_name, update.to_dict())
        return broker_response
