"""Unified tick field map across brokers (ported from trading-bot v1)."""

from __future__ import annotations

UNIFIED_SCHEMA: dict[str, dict[str, str | None]] = {
    "tick_id": {"zerodha": None, "angelone": None, "finvasia": None},
    "token": {"zerodha": "instrument_token", "angelone": "token", "finvasia": "Scrip Token"},
    "symbol_name": {"zerodha": None, "angelone": None, "finvasia": None},
    "tick_size": {"zerodha": None, "angelone": None, "finvasia": None},
    "timestamp": {
        "zerodha": "exchange_timestamp",
        "angelone": "exchange_timestamp",
        "finvasia": "Feed time",
    },
    "last_price": {
        "zerodha": "last_price",
        "angelone": "last_traded_price",
        "finvasia": "Last Traded Price (LTP)",
    },
    "last_traded_quantity": {
        "zerodha": "last_traded_quantity",
        "angelone": "last_traded_quantity",
        "finvasia": "Last trade quantity",
    },
    "average_traded_price": {
        "zerodha": "average_traded_price",
        "angelone": "average_traded_price",
        "finvasia": "Average trade price",
    },
    "volume_traded": {
        "zerodha": "volume_traded",
        "angelone": "volume_trade_for_the_day",
        "finvasia": "Volume",
    },
    "total_buy_quantity": {
        "zerodha": "total_buy_quantity",
        "angelone": "total_buy_quantity",
        "finvasia": "Total Buy Quantity",
    },
    "total_sell_quantity": {
        "zerodha": "total_sell_quantity",
        "angelone": "total_sell_quantity",
        "finvasia": "Total Sell Quantity",
    },
    "open_price": {
        "zerodha": "ohlc_open",
        "angelone": "open_price_of_the_day",
        "finvasia": "Open price",
    },
    "high_price": {
        "zerodha": "ohlc_high",
        "angelone": "high_price_of_the_day",
        "finvasia": "High price",
    },
    "low_price": {
        "zerodha": "ohlc_low",
        "angelone": "low_price_of_the_day",
        "finvasia": "Low price",
    },
    "close_price": {
        "zerodha": "ohlc_close",
        "angelone": "closed_price",
        "finvasia": "Close price",
    },
    "oi": {"zerodha": "oi", "angelone": "open_interest", "finvasia": "Open interest"},
    "last_trade_time": {
        "zerodha": "last_trade_time",
        "angelone": "last_traded_timestamp",
        "finvasia": "Last trade time",
    },
}

for i in range(1, 6):
    UNIFIED_SCHEMA[f"depth_buy_{i}_quantity"] = {
        "zerodha": f"depth_buy_{i}_quantity",
        "angelone": f"best_5_buy_data_{i}_quantity",
        "finvasia": f"Best Buy Quantity {i}",
    }
    UNIFIED_SCHEMA[f"depth_buy_{i}_price"] = {
        "zerodha": f"depth_buy_{i}_price",
        "angelone": f"best_5_buy_data_{i}_price",
        "finvasia": f"Best Buy Price {i}",
    }
    UNIFIED_SCHEMA[f"depth_buy_{i}_orders"] = {
        "zerodha": f"depth_buy_{i}_orders",
        "angelone": f"best_5_buy_data_{i}_no_of_orders",
        "finvasia": f"Best Buy Orders {i}",
    }
    UNIFIED_SCHEMA[f"depth_sell_{i}_quantity"] = {
        "zerodha": f"depth_sell_{i}_quantity",
        "angelone": f"best_5_sell_data_{i}_quantity",
        "finvasia": f"Best Sell Quantity {i}",
    }
    UNIFIED_SCHEMA[f"depth_sell_{i}_price"] = {
        "zerodha": f"depth_sell_{i}_price",
        "angelone": f"best_5_sell_data_{i}_price",
        "finvasia": f"Best Sell Price {i}",
    }
    UNIFIED_SCHEMA[f"depth_sell_{i}_orders"] = {
        "zerodha": f"depth_sell_{i}_orders",
        "angelone": f"best_5_sell_data_{i}_no_of_orders",
        "finvasia": f"Best Sell Orders {i}",
    }

UNIFIED_SCHEMA["change"] = {
    "zerodha": "change",
    "angelone": None,
    "finvasia": "Percentage change",
}
UNIFIED_SCHEMA["exchange"] = {
    "zerodha": None,
    "angelone": "exchange_type",
    "finvasia": "Exchange name (NSE, BSE, NFO ..)",
}
UNIFIED_SCHEMA["upper_circuit_limit"] = {
    "zerodha": None,
    "angelone": "upper_circuit_limit",
    "finvasia": "Upper Circuit Limit",
}
UNIFIED_SCHEMA["lower_circuit_limit"] = {
    "zerodha": None,
    "angelone": "lower_circuit_limit",
    "finvasia": "Lower Circuit Limit",
}
UNIFIED_SCHEMA["week_52_high"] = {
    "zerodha": None,
    "angelone": "52_week_high_price",
    "finvasia": "52 week high (other exchanges), Life time high (mcx)",
}
UNIFIED_SCHEMA["week_52_low"] = {
    "zerodha": None,
    "angelone": "52_week_low_price",
    "finvasia": "52 week low (other exchanges), Life time low (mcx)",
}
UNIFIED_SCHEMA["previous_day_closing_open_interest"] = {
    "zerodha": None,
    "angelone": None,
    "finvasia": "Previous day closing Open Interest",
}
UNIFIED_SCHEMA["total_open_interest_for_underlying"] = {
    "zerodha": None,
    "angelone": None,
    "finvasia": "Total open interest for underlying",
}
UNIFIED_SCHEMA["sequence_number"] = {
    "zerodha": None,
    "angelone": "sequence_number",
    "finvasia": None,
}
UNIFIED_SCHEMA["open_interest_change_percentage"] = {
    "zerodha": None,
    "angelone": "open_interest_change_percentage",
    "finvasia": None,
}
UNIFIED_SCHEMA["oi_day_high"] = {"zerodha": "oi_day_high", "angelone": None, "finvasia": None}
UNIFIED_SCHEMA["oi_day_low"] = {"zerodha": "oi_day_low", "angelone": None, "finvasia": None}
UNIFIED_SCHEMA["batch"] = {"zerodha": None, "angelone": None, "finvasia": None}
UNIFIED_SCHEMA["broker"] = {"zerodha": "zerodha", "angelone": "angelone", "finvasia": "finvasia"}

UNIFIED_COLUMNS: tuple[str, ...] = tuple(UNIFIED_SCHEMA.keys())
