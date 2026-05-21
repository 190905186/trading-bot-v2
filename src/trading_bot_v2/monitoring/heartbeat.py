"""Heartbeat event publisher utilities."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Mapping, Optional

from trading_bot_v2.domain.contracts import ServiceHeartbeatEvent
from trading_bot_v2.interfaces.messaging import EventPublisher

logger = logging.getLogger("trading_bot_v2.monitoring.heartbeat")


class HeartbeatEmitter:
    """Publishes periodic service heartbeat events."""

    def __init__(
        self,
        publisher: EventPublisher,
        service_name: str,
        resource_provider: Callable[[], Mapping[str, Any]],
        *,
        metadata_factory: Optional[Callable[[], Mapping[str, Any]]] = None,
    ) -> None:
        self._publisher = publisher
        self._service_name = service_name
        self._resource_provider = resource_provider
        self._metadata_factory = metadata_factory

    def emit_once(self, status: str = "up", metadata: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        payload = {"service_name": self._service_name, "status": status}
        payload.update(dict(self._resource_provider()))
        merged_meta: Dict[str, Any] = {}
        if self._metadata_factory:
            try:
                merged_meta.update(dict(self._metadata_factory()))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("heartbeat metadata_factory failed: %s", exc)
        if metadata:
            merged_meta.update(dict(metadata))
        if merged_meta:
            payload["metadata"] = merged_meta
        event = ServiceHeartbeatEvent(producer=f"heartbeat:{self._service_name}", payload=payload)
        self._publisher.publish(event.event_name, event.to_dict())
        return payload

    def run_forever(self, interval_seconds: float = 2.0) -> None:
        while True:
            self.emit_once()
            time.sleep(interval_seconds)
