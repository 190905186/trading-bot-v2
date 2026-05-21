"""Quick v1-style Finvasia WS test (no v2 adapter)."""
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv

load_repo_dotenv()

from NorenRestApiPy.NorenApi import NorenApi  # noqa: E402

uid = os.getenv("TB2_FINVASIA_USER_ID", "").strip()
access = os.getenv("TB2_FINVASIA_ACCESS_TOKEN", "").strip()
sus = os.getenv("TB2_FINVASIA_SUSER_TOKEN", "").strip()
instrument = "NSE|1594"
ticks = []

api = NorenApi(
    host="https://api.shoonya.com/NorenWClientAPI/",
    websocket="wss://api.shoonya.com/NorenWSTP/",
)

# v1 finvasia.py connect() — exact field assignment
api._NorenApi__susertoken = sus
api._NorenApi__username = uid
api._NorenApi__accountid = uid
api._NorenApi__access_token = access
api.injectOAuthHeader(access, uid, uid)

print(f"v1 auth uid={uid!r} access_set={bool(access)}")


def on_tick(res):
    ticks.append(res)
    print(f"TICK tk={res.get('tk')} lp={res.get('lp')} t={res.get('t')}")


def on_open():
    print("on_open -> subscribe depth feed")
    api.subscribe([instrument], feed_type="d")


def on_err(err):
    print(f"on_err: {err}")
    if isinstance(err, dict):
        t = str(err.get("t", "")).lower()
        s = str(err.get("s", err.get("stat", ""))).lower()
        if t == "ak" and s in {"ok", "okay"}:
            print("Ok ack via error path -> subscribe")
            on_open()


orig_data = api._NorenApi__on_data_callback.__get__(api, type(api))


def log_data(ws=None, message=None, data_type=None, continue_flag=None):
    if message:
        print(f"RAW: {str(message)[:200]}")
    return orig_data(ws, message, data_type, continue_flag)


api._NorenApi__on_data_callback = log_data.__get__(api, type(api))

threading.Thread(
    target=lambda: api.start_websocket(
        subscribe_callback=on_tick,
        socket_open_callback=on_open,
        socket_error_callback=on_err,
    ),
    daemon=True,
).start()

time.sleep(30)
print(f"Total ticks: {len(ticks)}")
