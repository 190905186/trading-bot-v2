"""Risk and trailing-stop interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional


class RiskManager(ABC):
    """Risk guardrails applied before and during execution."""

    @abstractmethod
    def validate_order_intent(self, signal_event: Mapping[str, Any]) -> tuple[bool, str]:
        """Return (is_allowed, reason)."""

    @abstractmethod
    def is_kill_switch_active(self) -> bool:
        """Return True if new entries must be blocked."""


class TrailingStopManager(ABC):
    """Manages SL updates and exit conditions."""

    @abstractmethod
    def add_position(self, position_payload: Mapping[str, Any]) -> str:
        """Register new filled position; return position key."""

    @abstractmethod
    def update_price(self, instrument_id: str, last_price: float, **kwargs: Any) -> None:
        """Update position mark and evaluate trailing logic."""

    @abstractmethod
    def close_position(self, position_key: str, reason: str) -> None:
        """Close tracked position."""

    @abstractmethod
    def get_snapshot(self) -> Mapping[str, Any]:
        """Return risk/TSL state for dashboard."""
