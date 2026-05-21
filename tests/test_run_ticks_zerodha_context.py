"""Regression: Zerodha adapter must receive loaded tick context."""

from __future__ import annotations

from unittest.mock import patch

from trading_bot_v2.services.ticks.tick_context import TickMappingContext


def test_build_adapter_passes_tick_context_to_zerodha():
    import scripts.run_ticks_service as mod

    ctx = TickMappingContext(
        instrument_to_exchange_token={91393: "357"},
        token_symbol_map={"357": "NAM-INDIA-EQ"},
    )
    with patch.dict(
        "os.environ",
        {
            "TB2_ZERODHA_API_KEY": "k",
            "TB2_ZERODHA_ACCESS_TOKEN": "t",
        },
        clear=False,
    ):
        with patch.object(mod, "ZerodhaMarketDataAdapter") as mock_cls:
            mod._build_adapter(
                "zerodha",
                "zerodha",
                0.2,
                session_label="batch1",
                tick_context=ctx,
                batch="batch1",
            )
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["tick_context"] is ctx
    assert kwargs["batch"] == "batch1"
