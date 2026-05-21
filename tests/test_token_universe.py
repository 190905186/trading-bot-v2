"""Tests for token batch rules and loader helpers."""

from __future__ import annotations

import pickle
import tempfile
from pathlib import Path

import pytest

from trading_bot_v2.token_universe.batch_rules import (
    build_token_batches,
    validate_batches_no_overlap,
    validate_batches_no_overlap_within_broker,
)
from trading_bot_v2.token_universe.loader import (
    _angelone_subscribe_strings,
    _finvasia_subscribe_strings,
    batch_token_ints,
)


def test_build_production_batches_per_broker_disjoint():
    tokens = list(range(10_000))
    batches = build_token_batches(tokens, profile="production")
    validate_batches_no_overlap_within_broker(batches)
    assert len(batches["batch1"]) + len(batches["batch2"]) + len(batches["batch3"]) <= 1141
    assert len(batches["batch4"]) == 1000


def test_overlap_raises():
    batches = {"batch1": [1, 2], "batch2": [2, 3]}
    with pytest.raises(ValueError, match="disjoint"):
        validate_batches_no_overlap(batches)


def test_loader_batch_roundtrip():
    tokens = list(range(100))
    batches = build_token_batches(tokens, profile="test")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        with (d / "tokens.pkl").open("wb") as f:
            pickle.dump(tokens, f)
        with (d / "token_batches.pkl").open("wb") as f:
            pickle.dump(batches, f)
        with (d / "subscribe_list.pkl").open("wb") as f:
            pickle.dump(["NSE|1", "NFO|50"], f)
        assert batch_token_ints("batch1", d) == batches["batch1"]


def test_finvasia_filter_subscribe_list():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        with (d / "subscribe_list.pkl").open("wb") as f:
            pickle.dump(["NSE|10", "NFO|20", "NSE|99"], f)
        out = _finvasia_subscribe_strings([10, 20], d)
        assert out == ["NSE|10", "NFO|20"]


def test_angelone_maps_exchange_type():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        with (d / "subscribe_list.pkl").open("wb") as f:
            pickle.dump(["NSE|10", "NFO|20"], f)
        out = _angelone_subscribe_strings([10, 20], d)
        assert "1|10" in out
        assert "2|20" in out
