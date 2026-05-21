"""Load pickles and resolve broker-specific subscribe instrument strings."""

from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

logger = logging.getLogger("trading_bot_v2.token_universe.loader")

from trading_bot_v2.token_universe.batch_rules import (
    BATCH_BROKER,
    assert_batch_matches_source,
)

# Angel SmartAPI exchangeType values (see trading-bot angelone get_token_list).
_EXCH_SEG_TO_ANGEL_TYPE = {
    "NSE": 1,
    "NFO": 2,
    "BSE": 3,
    "BFO": 4,
    "MCX": 5,
    "CDS": 7,
}


def universe_dir_from_env() -> Path:
    raw = os.getenv("TB2_TOKEN_UNIVERSE_DIR", "").strip()
    if raw:
        return Path(raw).resolve()
    # Default: trading-bot-v2/data/token_universe
    root = Path(__file__).resolve().parents[3]
    return (root / "data" / "token_universe").resolve()


def _pkl_path(directory: Path, name: str) -> Path:
    return directory / name


def load_all_tokens(directory: Path | None = None) -> List[int]:
    d = directory or universe_dir_from_env()
    path = _pkl_path(d, "tokens.pkl")
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}; run scripts/generate_token_universe.py first.")
    with path.open("rb") as f:
        raw = pickle.load(f)
    return [int(x) for x in raw]


def load_batches(directory: Path | None = None) -> Dict[str, List[int]]:
    d = directory or universe_dir_from_env()
    path = _pkl_path(d, "token_batches.pkl")
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}; run scripts/build_token_batches.py first.")
    with path.open("rb") as f:
        raw = pickle.load(f)
    return {str(k): [int(x) for x in v] for k, v in raw.items()}


def load_subscribe_list(directory: Path | None = None) -> List[str]:
    d = directory or universe_dir_from_env()
    path = _pkl_path(d, "subscribe_list.pkl")
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}; run scripts/generate_token_universe.py first.")
    with path.open("rb") as f:
        raw = pickle.load(f)
    return [str(x) for x in raw]


def load_token_exch_map(directory: Path | None = None) -> Dict[str, str]:
    d = directory or universe_dir_from_env()
    path = _pkl_path(d, "token_exch_map.pkl")
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        raw = pickle.load(f)
    return {str(k): str(v) for k, v in raw.items()}


def batch_token_ints(batch_name: str, directory: Path | None = None) -> List[int]:
    batches = load_batches(directory)
    key = batch_name.strip()
    if key not in batches:
        raise KeyError(f"Batch {batch_name!r} not in token_batches.pkl (keys: {sorted(batches)})")
    return batches[key]


def resolve_tick_instruments(
    market_data_source: str,
    batch_name: str,
    *,
    directory: Path | None = None,
) -> List[str]:
    """
    Return instrument strings for :class:`MarketDataAdapter.subscribe` for one batch.
    """
    assert_batch_matches_source(batch_name, market_data_source)
    tokens = batch_token_ints(batch_name, directory)
    src = market_data_source.strip().lower()
    if src in {"angel_one"}:
        src = "angelone"

    if src == "zerodha":
        return _zerodha_subscribe_strings(tokens, directory)

    if src == "finvasia":
        return _finvasia_subscribe_strings(tokens, directory)

    if src == "angelone":
        return _angelone_subscribe_strings(tokens, directory)

    raise ValueError(f"Unsupported market data source for batches: {market_data_source!r}")


def resolve_union_instruments(
    market_data_source: str,
    batch_names: Sequence[str],
    *,
    directory: Path | None = None,
) -> List[str]:
    """Union of multiple batches (for historical one-shot); order preserved, deduped."""
    seen: set[str] = set()
    out: List[str] = []
    for name in batch_names:
        for inst in resolve_tick_instruments(market_data_source, name, directory=directory):
            if inst not in seen:
                seen.add(inst)
                out.append(inst)
    return out


def _zerodha_subscribe_strings(tokens: List[int], directory: Path | None) -> List[str]:
    """Map Angel exchange_token ints to Kite instrument_token strings for KiteTicker."""
    d = directory or universe_dir_from_env()
    api_key = os.getenv("TB2_ZERODHA_API_KEY", "").strip()
    access_token = os.getenv("TB2_ZERODHA_ACCESS_TOKEN", "").strip()
    if not api_key or not access_token:
        logger.warning(
            "TB2_ZERODHA_API_KEY/TB2_ZERODHA_ACCESS_TOKEN unset; using batch ints as instrument_token "
            "(may be wrong if universe uses exchange_token)."
        )
        return [str(t) for t in tokens]

    from trading_bot_v2.token_universe.zerodha_mapping import map_exchange_tokens_with_reverse

    instrument_tokens, _reverse = map_exchange_tokens_with_reverse(
        tokens,
        api_key=api_key,
        access_token=access_token,
        universe_dir=d,
    )
    return [str(t) for t in instrument_tokens]


def zerodha_subscribe_reverse_map(
    exchange_tokens: List[int],
    *,
    directory: Path | None = None,
) -> Dict[int, str]:
    """instrument_token -> exchange_token for instruments in this Zerodha subscribe batch."""
    d = directory or universe_dir_from_env()
    api_key = os.getenv("TB2_ZERODHA_API_KEY", "").strip()
    access_token = os.getenv("TB2_ZERODHA_ACCESS_TOKEN", "").strip()
    if not api_key or not access_token:
        return {}
    from trading_bot_v2.token_universe.zerodha_mapping import map_exchange_tokens_with_reverse

    _instruments, reverse = map_exchange_tokens_with_reverse(
        exchange_tokens,
        api_key=api_key,
        access_token=access_token,
        universe_dir=d,
    )
    return reverse


def resolve_zerodha_instrument_token_ints(
    exchange_tokens: List[int],
    *,
    directory: Path | None = None,
) -> List[int]:
    """Same mapping as tick subscribe; for historical candle fetches."""
    strings = _zerodha_subscribe_strings(exchange_tokens, directory)
    return [int(s) for s in strings]


def _finvasia_subscribe_strings(tokens: List[int], directory: Path | None) -> List[str]:
    token_set = {str(t) for t in tokens}
    subscribe_list = load_subscribe_list(directory)
    return [entry for entry in subscribe_list if entry.split("|", 1)[-1] in token_set]


def _angelone_subscribe_strings(tokens: List[int], directory: Path | None) -> List[str]:
    token_set = {str(t) for t in tokens}
    subscribe_list = load_subscribe_list(directory)
    out: List[str] = []
    for entry in subscribe_list:
        if "|" not in entry:
            continue
        exch, tok = entry.split("|", 1)
        if tok not in token_set:
            continue
        exch_type = _EXCH_SEG_TO_ANGEL_TYPE.get(exch.upper(), 1)
        out.append(f"{exch_type}|{tok}")
    if out:
        return out
    # Fallback: token_exch_map.pkl
    exch_map = load_token_exch_map(directory)
    for t in tokens:
        seg = exch_map.get(str(t), "NSE").upper()
        exch_type = _EXCH_SEG_TO_ANGEL_TYPE.get(seg, 1)
        out.append(f"{exch_type}|{t}")
    return out


def list_batches_for_broker(broker: str) -> List[str]:
    b = broker.strip().lower()
    if b in {"angel_one"}:
        b = "angelone"
    return sorted(name for name, brk in BATCH_BROKER.items() if brk == b)
