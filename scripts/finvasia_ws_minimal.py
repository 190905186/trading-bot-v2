"""Minimal WS — no callback wrapping."""
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
pwd = os.getenv("TB2_FINVASIA_PASSWORD", "").strip()
access = os.getenv("TB2_FINVASIA_ACCESS_TOKEN", "").strip()
sus = os.getenv("TB2_FINVASIA_SUSER_TOKEN", "").strip()

api = NorenApi(
    host="https://api.shoonya.com/NorenWClientAPI/",
    websocket="wss://api.shoonya.com/NorenWSTP/",
)

# set_session path (v2 style)
api.set_session(uid, pwd, sus, sus)
api.injectOAuthHeader(access, uid, uid)

state = {"ticks": 0, "errs": []}


def on_tick(r):
    state["ticks"] += 1
    print("TICK", r.get("t"), r.get("tk"), r.get("lp"))


def on_open():
    print("OPEN subscribe")
    api.subscribe(["NSE|1594"], feed_type="d")


def on_err(e):
    state["errs"].append(e)
    print("ERR", e)
    if isinstance(e, dict) and e.get("t") == "ak" and str(e.get("s", "")).lower() == "ok":
        on_open()


print("start ws uid=", uid)
threading.Thread(
    target=lambda: api.start_websocket(
        subscribe_callback=on_tick,
        socket_open_callback=on_open,
        socket_error_callback=on_err,
    ),
    daemon=True,
).start()
time.sleep(20)
print("done ticks=", state["ticks"], "errs=", len(state["errs"]))
