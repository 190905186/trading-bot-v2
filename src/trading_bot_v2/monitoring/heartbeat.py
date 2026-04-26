"""Heartbeat event publisher utilities."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping

from trading_bot_v2.domain.contracts import ServiceHeartbeatEvent
from trading_bot_v2.interfaces.messaging import EventPublisher


class HeartbeatEmitter:
    """Publishes periodic service heartbeat events."""

    def __init__(
        self,
        publisher: EventPublisher,
        service_name: str,
        resource_provider: Callable[[], Mapping[str, Any]],
    ) -> None:
        self._publisher = publisher
        self._service_name = service_name
        self._resource_provider = resource_provider

    def emit_once(self, status: str = "up", metadata: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        payload = {"service_name": self._service_name, "status": status}
        payload.update(dict(self._resource_provider()))
        if metadata:
            payload["metadata"] = dict(metadata)
        event = ServiceHeartbeatEvent(producer=f"heartbeat:{self._service_name}", payload=payload)
        self._publisher.publish(event.event_name, event.to_dict())
        return payload

    def run_forever(self, interval_seconds: float = 2.0) -> None:
        while True:
            self.emit_once()
            time.sleep(interval_seconds)
