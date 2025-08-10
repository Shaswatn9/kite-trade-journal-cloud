from datetime import datetime, timezone
from typing import List, Any
import pytz, math

IST = pytz.timezone("Asia/Kolkata")

def to_ist_str(dt_utc: datetime) -> str:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")

def days_between_strs(buy_str: str, sell_str: str) -> int:
    # "YYYY-MM-DD HH:MM:SS" in IST
    dt_fmt = "%Y-%m-%d %H:%M:%S"
    b = datetime.strptime(buy_str, dt_fmt)
    s = datetime.strptime(sell_str, dt_fmt)
    return max(0, (s - b).days)

def load_open(ws_open) -> List[List[Any]]:
    return ws_open.get_all_values()[1:]  # skip header

def save_open(ws_open, rows: List[List[Any]]):
    ws_open.clear()
    ws_open.append_row(["Stock","Buy DateTime","Buy Price","Remaining Qty","Order IDs","Holding (days)"])
    if rows:
        # recompute holding days using today in IST
        from datetime import datetime as dt
        now_ist = IST.localize(dt.utcnow().replace(tzinfo=timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
        fresh = []
        for r in rows:
            stock, bdt, bpx, rqty, bids = r[0], r[1], float(r[2]), int(r[3]), r[4]
            # compute holding days vs today
            try:
                hd = days_between_strs(bdt, now_ist)
            except:
                hd = ""
            fresh.append([stock, bdt, bpx, rqty, bids, hd])
        ws_open.append_rows(fresh, value_input_option="USER_ENTERED")

def add_buy(ws_open, stock: str, buy_dt: str, buy_px: float, qty: int, order_id: str):
    rows = load_open(ws_open)
    rows.append([stock, buy_dt, buy_px, qty, order_id])
    save_open(ws_open, rows)

def consume_sell(ws_open, ws_journal, stock: str, sell_dt: str, sell_px: float, qty: int, sell_oid: str):
    rows = load_open(ws_open)
    remaining = qty
    new_open = []
    out_rows = []

    for r in rows:
        s, bdt, bpx, rqty, bids, *_ = r + [""]  # tolerate missing last col
        bpx, rqty = float(bpx), int(rqty)
        if s != stock:
            new_open.append(r[:5])  # keep original; will recompute holding days
            continue
        if remaining <= 0:
            new_open.append(r[:5]); continue

        take = min(remaining, rqty)
        rqty -= take
        pnl = round((sell_px - bpx) * take, 2)
        hold_days = days_between_strs(bdt, sell_dt)

        out_rows.append([
            "",       # Serial No. (filled later)
            s,        # Stock
            bdt,      # Date and Time (BUY)
            bpx,      # Price (BUY)
            take,     # Qty (BUY matched)
            sell_dt,  # Sell Date and Time
            sell_px,  # Price (SELL)
            take,     # Qty (SELL matched)
            pnl,      # PnL
            "",       # Setup
            "",       # Remarks
            hold_days # Holding time (days)
        ])
        remaining -= take
        if rqty > 0:
            new_open.append([s, bdt, bpx, rqty, bids])

    # write journal rows with serials
    from sheets_helper import get_next_serial, append_journal_rows
    if out_rows:
        serial_start = get_next_serial(ws_journal)
        for i, row in enumerate(out_rows):
            row[0] = serial_start + i
        append_journal_rows(ws_journal, out_rows)

    save_open(ws_open, new_open)
