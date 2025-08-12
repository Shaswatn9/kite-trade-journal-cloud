from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}
import os
from threading import Thread
from fastapi.responses import RedirectResponse, PlainTextResponse, JSONResponse
from kiteconnect import KiteConnect, KiteTicker

API_KEY = os.environ["KITE_API_KEY"]
API_SECRET = os.environ["KITE_API_SECRET"]

_access_token = None
_listener_active = False

def _run_listener(token):
    global _listener_active
    _listener_active = True
    try:
        # Adjust to call your existing listener
        self_obj = type("OrderListener", (), {"stop_flag": False, "start_ticker": start_ticker})()
        self_obj.start_ticker(token)
    finally:
        _listener_active = False

@app.get("/login")
def login():
    kite = KiteConnect(api_key=API_KEY)
    return RedirectResponse(url=kite.login_url())

@app.get("/callback")
def callback(request_token: str):
    global _access_token
    kite = KiteConnect(api_key=API_KEY)
    data = kite.generate_session(request_token=request_token, api_secret=API_SECRET)
    _access_token = data["access_token"]

    if not _listener_active:
        t = Thread(target=_run_listener, args=(_access_token,), daemon=True)
        t.start()

    return PlainTextResponse("Access token saved. Listener started.")

@app.get("/status")
def status():
    return JSONResponse({
        "token_loaded": bool(_access_token),
        "listener_active": _listener_active
    })
def start_ticker(self, access_token):
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(access_token)

    def on_connect(ws, resp):
        print("[listener] Connected. Waiting for order updates...")
        try:
            ws.subscribe_orders()  # ✅ Subscribes to order updates
            print("[listener] Subscribed to order updates")
        except Exception as e:
            print("[listener] subscribe_orders failed:", e)

    def on_order_update(ws, data):
        try:
            print("[listener] raw order_update:", data)
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
        # Don't raise SystemExit here; let the loop below notice the disconnect
        print("[listener] websocket closed:", code, reason)

    ticker = KiteTicker(API_KEY, access_token,reconnect=True,reconnect_tries=100,reconnect_delay=5)
    ticker.on_connect = on_connect
    ticker.on_close   = on_close
    ticker.on_error   = on_error
    ticker.on_order_update = on_order_update

    # ✅ Run Twisted/KiteTicker in its own internal thread
    ticker.connect(threaded=True)

    # Keep this OrderListener thread alive while the ws thread is connected.
    # When it disconnects, we exit and the outer run() loop restarts and reloads token.
    while not self.stop_flag:
        try:
            # if ws attribute missing or socket closed, break to restart
            if not getattr(ticker, "ws", None) or not getattr(ticker.ws, "sock", None) or not ticker.ws.sock.connected:
                print("[listener] detected disconnect; breaking to restart")
                break
        except Exception:
            break
        time.sleep(2)







