"""Messaging interfaces for inter-process communication."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterable, Mapping, Optional


MessageHandler = Callable[[Mapping[str, Any]], None]


class EventPublisher(ABC):
    """Publish events to event bus transport."""

    @abstractmethod
    def publish(self, channel: str, event: Mapping[str, Any]) -> None:
        """Publish one event to a channel/stream."""

    def publish_many(self, channel: str, events: Iterable[Mapping[str, Any]]) -> None:
        """Publish many events; default loop implementation."""
        for event in events:
            self.publish(channel, event)


class EventConsumer(ABC):
    """Consume events from channel/stream transport."""

    @abstractmethod
    def subscribe(self, channel: str, handler: MessageHandler) -> None:
        """Subscribe to continuous stream with callback handler."""

    @abstractmethod
    def read_batch(
        self, channel: str, *, max_items: int = 100, timeout_ms: int = 1000
    ) -> list[Dict[str, Any]]:
        """Pull a batch (for sync polling services)."""
