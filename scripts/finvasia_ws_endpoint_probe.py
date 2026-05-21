"""Try Shoonya websocket endpoints (legacy WSTP vs OAuth WSAPI)."""
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

import websocket  # noqa: E402

uid = os.getenv("TB2_FINVASIA_USER_ID", "").strip()
actid = os.getenv("TB2_FINVASIA_ACTID", "").strip() or uid
access = os.getenv("TB2_FINVASIA_ACCESS_TOKEN", "").strip()

ENDPOINTS = [
    "wss://api.shoonya.com/NorenWSTP/",
    "wss://api.shoonya.com/NorenWSAPI/",
    "wss://api.shoonya.com/NorenWSTP",
    "wss://api.shoonya.com/NorenWSAPI",
]

for url in ENDPOINTS:
    msgs: list[str] = []

    def on_open(ws, _url=url):
        payload = json.dumps(
            {"t": "a", "uid": uid, "actid": actid, "accesstoken": access, "source": "API"}
        )
        print(f"[{_url}] SEND {payload[:100]}...")
        ws.send(payload)

    def on_message(ws, message, _url=url):
        msgs.append(message)
        print(f"[{_url}] MSG {message[:400]}")

    def on_error(ws, error, _url=url):
        print(f"[{_url}] ERR {error}")

    def on_close(ws, code, msg, _url=url):
        print(f"[{_url}] CLOSE {code} {msg}")

    ws = websocket.WebSocketApp(
        url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close
    )
    t = threading.Thread(
        target=lambda w=ws: w.run_forever(ping_interval=3, ping_payload='{"t":"h"}'),
        daemon=True,
    )
    t.start()
    time.sleep(8)
    ws.close()
    time.sleep(0.3)
    print(f"[{url}] total msgs={len(msgs)}\n")
