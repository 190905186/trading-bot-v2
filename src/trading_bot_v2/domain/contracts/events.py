"""Core event contracts exchanged between independent services."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class EventName(str, Enum):
    """Canonical event names shared across services."""

    TICKS_RAW = "ticks.raw"
    CANDLES_1M_CLOSED = "candles.1m.closed"
    SIGNALS_GENERATED = "signals.generated"
    ORDERS_INTENT = "orders.intent"
    ORDERS_UPDATES = "orders.updates"
    SERVICE_HEARTBEAT = "service.heartbeat"
    PIPELINE_LATENCY = "pipeline.latency"
    DASHBOARD_METRIC_DEFINITION = "dashboard.metric.definition"
    DASHBOARD_METRIC_VALUE = "dashboard.metric.value"


@dataclass(slots=True)
class BaseEvent:
    """Base transport envelope for all events."""

    event_name: str
    event_version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: Optional[str] = None
    producer: str = ""
    published_at: datetime = field(default_factory=utc_now)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event for message bus publishing."""
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data


@dataclass(slots=True)
class TickEvent(BaseEvent):
    """Tick event contract from websocket/tick services."""

    event_name: str = EventName.TICKS_RAW.value


@dataclass(slots=True)
class CandleEvent(BaseEvent):
    """Closed minute candle event consumed by signal service."""

    event_name: str = EventName.CANDLES_1M_CLOSED.value


@dataclass(slots=True)
class SignalEvent(BaseEvent):
    """Signal event produced by strategy pipelines."""

    event_name: str = EventName.SIGNALS_GENERATED.value


@dataclass(slots=True)
class OrderIntentEvent(BaseEvent):
    """Order intent event produced by signal->execution bridge."""

    event_name: str = EventName.ORDERS_INTENT.value


@dataclass(slots=True)
class OrderUpdateEvent(BaseEvent):
    """Order lifecycle update event emitted by execution service."""

    event_name: str = EventName.ORDERS_UPDATES.value


@dataclass(slots=True)
class ServiceHeartbeatEvent(BaseEvent):
    """Heartbeat from each process for dashboard/system health."""

    event_name: str = EventName.SERVICE_HEARTBEAT.value


@dataclass(slots=True)
class PipelineLatencyEvent(BaseEvent):
    """Latency measurement for stage-to-stage observability."""

    event_name: str = EventName.PIPELINE_LATENCY.value
