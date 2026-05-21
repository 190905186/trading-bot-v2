"""Strategy implementations."""

from .ohlc_open_range import OhlcOpenRangeStrategy, generate_ohlc_open_range_signal
from .simple_candle import SimpleCandleMomentumStrategy

__all__ = [
    "SimpleCandleMomentumStrategy",
    "OhlcOpenRangeStrategy",
    "generate_ohlc_open_range_signal",
]

