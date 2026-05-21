"""Compare websocket accesstoken = JWT vs susertoken."""
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


def run_probe(label: str, ws_token: str) -> None:
    api = NorenApi(
        host="https://api.shoonya.com/NorenWClientAPI/",
        websocket="wss://api.shoonya.com/NorenWSTP/",
    )
    api._NorenApi__username = uid
    api._NorenApi__accountid = uid
    api._NorenApi__access_token = ws_token
    api.injectOAuthHeader(access, uid, uid)

    tick_count = 0
    msg_count = 0
    subscribed = False

    orig = api._NorenApi__on_data_callback.__get__(api, type(api))

    def wrap(ws=None, message=None, data_type=None, continue_flag=None):
        nonlocal msg_count
        if message:
            msg_count += 1
            print(f"[{label}] MSG: {str(message)[:160]}")
        return orig(ws, message, data_type, continue_flag)

    api._NorenApi__on_data_callback = wrap

    def subscribe_now():
        nonlocal subscribed
        if subscribed:
            return
        subscribed = True
        api.subscribe(["NSE|1594"], feed_type="d")
        print(f"[{label}] subscribed")

    def on_open():
        print(f"[{label}] on_open (OK path)")
        subscribe_now()

    def on_err(err):
        print(f"[{label}] on_err: {err}")
        if isinstance(err, dict):
            t = str(err.get("t", "")).lower()
            s = str(err.get("s", err.get("stat", ""))).lower()
            if t == "ak" and s in {"ok", "okay"}:
                print(f"[{label}] Ok ack -> subscribe")
                subscribe_now()

    def on_tick(res):
        nonlocal tick_count
        tick_count += 1
        print(f"[{label}] TICK lp={res.get('lp')} t={res.get('t')}")

    threading.Thread(
        target=lambda: api.start_websocket(
            subscribe_callback=on_tick,
            socket_open_callback=on_open,
            socket_error_callback=on_err,
        ),
        daemon=True,
    ).start()
    time.sleep(15)
    print(f"[{label}] summary msgs={msg_count} ticks={tick_count} subscribed={subscribed}\n")


if __name__ == "__main__":
    print(f"uid={uid!r}\n")
    run_probe("jwt_ws_token", access)
    run_probe("sus_ws_token", sus)
