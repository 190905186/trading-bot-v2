# Trading Bot V2 - Daily Context (2026-04-26)

## What we completed today

- Implemented new tick market data adapters:
  - `src/trading_bot_v2/infrastructure/brokers/finvasia_market_data.py`
  - `src/trading_bot_v2/infrastructure/brokers/angelone_market_data.py`
- Updated broker exports in:
  - `src/trading_bot_v2/infrastructure/brokers/__init__.py`
- Extended tick service source routing in:
  - `scripts/run_ticks_service.py`
  - Added support for `TB2_MARKET_DATA_SOURCE=finvasia|angelone|zerodha|mock`
  - Added source-specific default instrument formats
- Fixed tick service startup sequencing:
  - `src/trading_bot_v2/services/ticks/service.py`
  - Changed order to `set handler -> subscribe -> connect` (important for websocket `on_open` subscription behavior)
- Added Finvasia feed-type control:
  - `TB2_FINVASIA_FEED_TYPE` (`t` trade, `d` depth)
- Updated docs in `README.md` with Finvasia/AngelOne setup and instrument formats.
- Updated dependencies in `pyproject.toml`:
  - Added `NorenRestApiOAuth`, `smartapi-python`, `logzero`
- Validation completed:
  - `python -m compileall src scripts` passed
  - Lint check passed for edited files

## Smoke test status

### AngelOne

- **Status: SUCCESS**
- Live smoke test received first tick for `1|1594` (INFY).
- Adapter parsing and callback flow are working.

### Finvasia

- **Status: PARTIAL / BLOCKED**
- OAuth token refresh script runs and updates `.env`.
- REST auth check works (`get_limits` returns `stat=Ok`).
- Websocket transport handshake succeeds (`101 Switching Protocols`) and heartbeat works.
- But websocket app-level auth/subscription ack/ticks are not arriving (`socket_open_callback` not triggered, no tick callback), then connection closes.

## Key finding likely causing Finvasia websocket issue

- In `trading-bot/finvasia_access_token.py`, `main()` currently sets:
  - `susertoken, access_token = result[0], result[0]`
- This likely writes incorrect token mapping to `.env` for websocket session usage.
- The same file already contains helper logic `_extract_finvasia_tokens(...)`, but it is not used in `main()`.

## Pending for tomorrow (priority order)

1. Fix `trading-bot/finvasia_access_token.py` token extraction/writing:
   - Use `_extract_finvasia_tokens(result)` in `main()`
   - Persist proper `FINVASIA_SUSER_TOKEN` and `FINVASIA_ACCESS_TOKEN`
2. Regenerate Finvasia tokens and re-run websocket smoke test immediately.
3. If still blocked, compare with known working flow from `trading-bot/scripts/finvasia/test_single_token.py`:
   - Check session initialization path
   - Check subscription timing and feed mode
4. Validate Finvasia first tick ingestion through `trading-bot-v2` tick service into Redis stream.
5. After Finvasia tick path is stable, continue with next broker rollout tasks (execution/risk harmonization as planned).

## Useful env reminders

- `TB2_MARKET_DATA_SOURCE=angelone|finvasia|zerodha|mock`
- `TB2_INSTRUMENTS` formats:
  - Zerodha: `256265,738561`
  - Finvasia: `NSE|22,NFO|12345`
  - AngelOne: `1|1594,2|12345`
- Finvasia optional:
  - `TB2_FINVASIA_FEED_TYPE=t` (or `d`)

## Tomorrow quick start

1. Activate venv and install deps (if needed):
   - `.\.venv\Scripts\python -m pip install -e .`
2. Fix token script in `trading-bot/finvasia_access_token.py`.
3. Refresh token, then run Finvasia adapter smoke test.
4. Run `scripts/run_ticks_service.py` with `TB2_MARKET_DATA_SOURCE=finvasia` and verify first tick event published.

