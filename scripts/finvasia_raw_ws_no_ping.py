"""Raw WS probe — no client pings; log every event."""
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
url = "wss://api.shoonya.com/NorenWSTP/"
events: list[str] = []


def on_open(ws):
    events.append("open")
    payload = json.dumps(
        {"t": "a", "uid": uid, "actid": uid, "accesstoken": access, "source": "API"}
    )
    print("SEND", payload)
    ws.send(payload)
    # Some clients subscribe before ack — see if server pushes anything
    sub = json.dumps({"t": "d", "k": "NSE|1594"})
    print("SEND subscribe", sub)
    ws.send(sub)


def on_message(ws, message):
    events.append(f"msg:{message[:200]}")
    print("MSG", message[:500])


def on_data(ws, data, data_type, continue_flag):
    events.append(f"data:{data!r:.200}")
    print("DATA", data_type, repr(data)[:500])


def on_error(ws, error):
    events.append(f"err:{error}")
    print("ERR", error)


def on_close(ws, code, msg):
    events.append(f"close:{code}:{msg}")
    print("CLOSE", code, msg)


ws = websocket.WebSocketApp(
    url,
    on_open=on_open,
    on_message=on_message,
    on_data=on_data,
    on_error=on_error,
    on_close=on_close,
)
threading.Thread(target=lambda: ws.run_forever(), daemon=True).start()
time.sleep(20)
ws.close()
time.sleep(0.3)
print("events", events)
