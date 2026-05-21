"""Raw websocket-client probe — bypass NorenApi to see server responses."""
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
access = os.getenv("TB2_FINVASIA_ACCESS_TOKEN", "").strip()
sus = os.getenv("TB2_FINVASIA_SUSER_TOKEN", "").strip()
actid = os.getenv("TB2_FINVASIA_ACTID", "").strip() or uid
url = "wss://api.shoonya.com/NorenWSTP/"
msgs: list[str] = []


def run_auth(tok: str, label: str) -> None:
    global msgs
    msgs = []

    def on_open(ws):
        payload = json.dumps(
            {"t": "a", "uid": uid, "actid": actid, "accesstoken": tok, "source": "API"}
        )
        print(f"[{label}] SEND {payload}")
        ws.send(payload)

    def on_message(ws, message):
        msgs.append(message)
        print(f"[{label}] MSG {message[:400]}")

    def on_error(ws, error):
        print(f"[{label}] ERR {error}")

    def on_close(ws, code, msg):
        print(f"[{label}] CLOSE code={code} msg={msg}")

    ws = websocket.WebSocketApp(
        url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close
    )
    t = threading.Thread(
        target=lambda: ws.run_forever(ping_interval=3, ping_payload='{"t":"h"}'),
        daemon=True,
    )
    t.start()
    time.sleep(12)
    ws.close()
    time.sleep(0.5)
    print(f"[{label}] total msgs={len(msgs)}")


print(f"uid={uid!r} actid={actid!r} access_len={len(access)} sus_len={len(sus)}")

variants = [
    ("access uid=actid", access, uid, actid),
    ("sus uid=actid", sus, uid, actid),
    ("access actid=uid_U", access, uid, uid + "_U"),
    ("sus actid=uid_U", sus, uid, uid + "_U"),
    ("access uid=actid_U", access, uid + "_U", uid + "_U"),
]

for label, tok, ws_uid, ws_actid in variants:
    if not tok:
        continue
    msgs = []

    def on_open(ws, _tok=tok, _uid=ws_uid, _actid=ws_actid, _label=label):
        payload = json.dumps(
            {"t": "a", "uid": _uid, "actid": _actid, "accesstoken": _tok, "source": "API"}
        )
        print(f"[{_label}] SEND {payload}")
        ws.send(payload)

    def on_message(ws, message, _label=label):
        msgs.append(message)
        print(f"[{_label}] MSG {message[:400]}")

    def on_error(ws, error, _label=label):
        print(f"[{_label}] ERR {error}")

    def on_close(ws, code, msg, _label=label):
        print(f"[{_label}] CLOSE code={code} msg={msg}")

    ws = websocket.WebSocketApp(
        url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close
    )
    t = threading.Thread(
        target=lambda w=ws: w.run_forever(ping_interval=3, ping_payload='{"t":"h"}'),
        daemon=True,
    )
    t.start()
    time.sleep(10)
    ws.close()
    time.sleep(0.5)
    print(f"[{label}] total msgs={len(msgs)}")
