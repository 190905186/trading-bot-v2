"""Unit tests for Angel margin CSV resolver and session-date planning."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from zoneinfo import ZoneInfo

from trading_bot_v2.infrastructure.candles.margin_contract_index import (
    InstrumentKind,
    MarginContractIndex,
    iter_session_dates,
    parse_margin_expiry,
)


def test_parse_margin_expiry() -> None:
    assert parse_margin_expiry("28APR2026") == date(2026, 4, 28)
    assert parse_margin_expiry("") is None
    assert parse_margin_expiry(None) is None


@pytest.fixture
def tiny_margin_csv(tmp_path):
    p = tmp_path / "margin.csv"
    p.write_text(
        "\n".join(
            [
                "token,symbol,name,expiry,strike,lotsize,instrumenttype,exch_seg,tick_size",
                "13061,360ONE-EQ,360ONE,,0,1,,NSE,5",
                "66693,360ONE28APR26FUT,360ONE,28APR2026,-1,500,FUTSTK,NFO,5",
                "62331,360ONE30JUN26FUT,360ONE,30JUN2026,-1,500,FUTSTK,NFO,5",
            ]
        ),
        encoding="utf-8",
    )
    return p


def test_margin_index_classify_and_pick_fut(tiny_margin_csv) -> None:
    idx = MarginContractIndex.from_csv_path(tiny_margin_csv)
    assert idx.classify(13061)[0] == InstrumentKind.EQ
    assert idx.classify(66693)[0] == InstrumentKind.FUT
    assert idx.pick_fut_token_for_session_date("360ONE", date(2026, 4, 10)) == 66693
    assert idx.pick_fut_token_for_session_date("360ONE", date(2026, 5, 30)) == 62331


def test_iter_session_dates_half_open() -> None:
    tz = ZoneInfo("Asia/Kolkata")
    fr = datetime(2026, 4, 28, 9, 15, tzinfo=tz)
    to_excl = datetime(2026, 4, 29, 0, 0, tzinfo=tz)
    assert list(iter_session_dates(fr, to_excl, tz)) == [date(2026, 4, 28)]


def test_plan_fut_segments_across_roll(tiny_margin_csv) -> None:
    tz = ZoneInfo("Asia/Kolkata")
    idx = MarginContractIndex.from_csv_path(tiny_margin_csv)
    ef = datetime(2026, 4, 27, 9, 0, tzinfo=tz)
    et = datetime(2026, 5, 1, 15, 0, tzinfo=tz)
    segs = idx.plan_fut_segments_for_range("360ONE", ef, et, tz)
    uniq = {s.fut_token for s in segs}
    assert 66693 in uniq
    assert 62331 in uniq
