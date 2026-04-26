"""Broker adapter interfaces for market-data and execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable, Mapping, Optional


TickCallback = Callable[[Mapping[str, Any]], None]


class MarketDataAdapter(ABC):
    """Contract for broker websocket/tick adapters."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Return provider identifier (e.g. zerodha)."""

    @abstractmethod
    def connect(self) -> None:
        """Open market-data session."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close market-data session."""

    @abstractmethod
    def subscribe(self, instruments: Iterable[str]) -> None:
        """Subscribe instrument universe."""

    @abstractmethod
    def set_tick_handler(self, handler: TickCallback) -> None:
        """Register callback for each normalized tick."""


class ExecutionAdapter(ABC):
    """Contract for broker order management actions."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Return provider identifier."""

    @abstractmethod
    def place_order(self, order_request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Submit order request to broker."""

    @abstractmethod
    def modify_order(self, order_id: str, updates: Mapping[str, Any]) -> Mapping[str, Any]:
        """Modify an open order."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> Mapping[str, Any]:
        """Cancel an order."""

    @abstractmethod
    def get_order_status(self, order_id: str) -> Mapping[str, Any]:
        """Fetch latest order status."""

    @abstractmethod
    def get_position_pnl(self, instrument_id: Optional[str] = None) -> Mapping[str, Any]:
        """Fetch PnL snapshot used by dashboard/risk services."""
