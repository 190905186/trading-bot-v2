"""Strategy interfaces and plugin registry contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional, Sequence


class TradingStrategy(ABC):
    """Strategy contract consumed by signal service."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy identifier."""

    @abstractmethod
    def on_candle(self, candle_event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Process candle event and optionally return a signal payload."""

    def on_tick(self, tick_event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Optional tick-driven hook; default no signal."""
        return None

    def configure(self, options: Mapping[str, Any]) -> None:
        """Optional runtime config hook."""


class StrategyFactory(ABC):
    """Factory interface for building strategy plugins."""

    @abstractmethod
    def build(self, strategy_id: str, options: Mapping[str, Any]) -> TradingStrategy:
        """Instantiate a strategy by id."""

    @abstractmethod
    def available(self) -> Sequence[str]:
        """List available strategy ids."""
