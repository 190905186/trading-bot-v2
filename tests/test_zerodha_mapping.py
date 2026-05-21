"""Tests for exchange_token -> instrument_token mapping."""

from __future__ import annotations

import csv
import pickle
import tempfile
from pathlib import Path

from trading_bot_v2.token_universe.zerodha_mapping import map_exchange_tokens_to_instrument_tokens


def test_map_exchange_tokens_uses_csv_and_amxidx():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        csv_path = d / "instruments.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["instrument_token", "exchange_token", "tradingsymbol"],
            )
            writer.writeheader()
            writer.writerow({"instrument_token": "9001", "exchange_token": "100", "tradingsymbol": "RELIANCE-EQ"})
            writer.writerow({"instrument_token": "9002", "exchange_token": "200", "tradingsymbol": "NIFTY 50"})

        with (d / "amxidx_dict.pkl").open("wb") as f:
            pickle.dump({999: "NIFTY 50"}, f)

        out = map_exchange_tokens_to_instrument_tokens(
            [100, 200, 999],
            api_key="dummy",
            access_token="dummy",
            universe_dir=d,
            instruments_csv=csv_path,
        )
        assert 9001 in out
        assert 9002 in out
        assert 999 not in out  # amxidx keys filtered from exchange list before lookup
