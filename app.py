import os, threading, time
from datetime import datetime, timezone
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from kiteconnect import KiteConnect, KiteTicker
from sheets_helper import get_ws, config_get_token, config_set_token
from _fifo import to_ist_str, add_buy, consume_sell

API_KEY = os.environ["KITE_API_KEY"]
API_SECRET = os.environ["KITE_API_SECRET"]
SHEET_NAME = os.environ["SHEET_NAME"]

app = FastAPI()
ws_journal, ws_open, ws_config = get_ws()

# ---------- Login flow for phone ----------
@app.get("/login", response_class=HTMLResponse)
def login():
    kite = KiteConnect(api_key=API_KEY)
    url = kite.login_url()
    return f"""
    <html><body style="font-family:sans-serif">
      <h3>Zerodha Login</h3>
      <p>Tap below to login and refresh your access token.</p>
      <a href="{url}" style="padding:10px 16px;background:#0b5;color:#fff;text-decoration:none;border-radius:6px;">Login with Zerodha</a>
    </body></html>
    """

@app.get("/callback")
def callback(action: str = "", status: str = "", request_token: str = ""):
    if status != "success" or not request_token:
        return HTMLResponse("<h3>Login failed</h3>", status_code=400)
    kite = KiteConnect(api_key=API_KEY)
    try:
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = data["access_token"]
        config_set_token(ws_config, access_token)
        return HTMLResponse("<h3>Token saved. You can close this tab.</h3>")
    except Exception as e:
        return HTMLResponse(f"<h3>Error: {e}</h3>", status_code=400)

@app.get("/health")
def health():
    return {"status": "up"}

# ---------- Order listener ----------
class OrderListener(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.ticker = None
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            token = config_get_token(ws_config)
            if not token:
                time.sleep(5); continue
            try:
                print("[listener] starting with access token:", token[:6], "...")
                self.start_ticker(token)
            except Exception as e:
                print("[listener] crashed:", e)
                time.sleep(5)

    def start_ticker(self, access_token):
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)

        def on_connect(ws, resp):
            print("[listener] Connected. Waiting for order updates...")

        def on_order_update(ws, data):
            try:
                if data.get("status") != "COMPLETE":
                    return
                tx = data.get("transaction_type")  # BUY/SELL
                sym = data.get("tradingsymbol")
                price = float(data.get("average_price") or 0)
                qty   = int(data.get("filled_quantity") or 0)
                exch_ts = data.get("exchange_timestamp") or data.get("order_timestamp")
                dt_utc = datetime.now(timezone.utc)
                if isinstance(exch_ts, (int, float)):
                    dt_utc = datetime.fromtimestamp(float(exch_ts)/1000.0, tz=timezone.utc)
                elif isinstance(exch_ts, str):
                    try:
                        dt_utc = datetime.strptime(exch_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except:
                        pass
                ts_ist = to_ist_str(dt_utc)
                oid = data.get("order_id","")
                exch = data.get("exchange") or "NSE"

                if not (sym and price and qty):
                    return

                if tx == "BUY":
                    add_buy(ws_open, sym, ts_ist, price, qty, oid)
                    print(f"[listener] BUY logged: {sym} {qty} @ {price} ({ts_ist})")
                    # place -7% GTT
                    try:
                        trigger = round(price * 0.93, 2)
                        limit   = round(price * 0.929, 2)
                        # Single trigger GTT: sell limit when trigger hits
                        kite.place_gtt(
                            trigger_type=kite.GTT_TYPE_SINGLE,
                            tradingsymbol=sym,
                            exchange=exch,
                            trigger_values=[trigger],
                            last_price=price,
                            orders=[{
                                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                                "quantity": qty,
                                "price": limit
                            }]
                        )
                        print(f"[listener] GTT -7% placed for {sym}: trigger {trigger}, limit {limit}, qty {qty}")
                    except Exception as ge:
                        print("[listener] GTT place error:", ge)

                elif tx == "SELL":
                    consume_sell(ws_open, ws_journal, sym, ts_ist, price, qty, oid)
                    print(f"[listener] SELL logged: {sym} {qty} @ {price} ({ts_ist})")
            except Exception as e:
                print("[listener] on_order_update error:", e)

        def on_error(ws, code, reason):
            print("[listener] websocket error:", code, reason)

        def on_close(ws, code, reason):
            print("[listener] websocket closed:", code, reason)
            # force restart loop
            raise SystemExit("ws closed")

        ticker = KiteTicker(API_KEY, access_token)
        ticker.on_connect = on_connect
        ticker.on_close = on_close
        ticker.on_error = on_error
        ticker.on_order_update = on_order_update
        # blocking connect; exits on error/close → thread loop restarts and reloads token
        ticker.connect(threaded=False)

listener = OrderListener()
listener.start()
