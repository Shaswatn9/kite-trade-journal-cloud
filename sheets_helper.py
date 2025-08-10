import os, gspread
from google.oauth2.service_account import Credentials

# Journal headers (added Holding time at end)
HEADERS_JOURNAL = ["Serial No.","Stock","Date and Time","Price","Qty",
                   "Sell Date and Time","Price","Qty","PnL","Setup","Remarks","Holding time (days)"]
HEADERS_OPEN = ["Stock","Buy DateTime","Buy Price","Remaining Qty","Order IDs","Holding (days)"]
HEADERS_CONFIG = ["Key","Value"]

def sheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(os.environ["GSPREAD_SERVICE_JSON"], scopes=scopes)
    return gspread.authorize(creds)

def get_spreadsheet():
    gc = sheets_client()
    return gc.open(os.environ["SHEET_NAME"])

def ensure_sheets(sh):
    try:
        j = sh.worksheet("TradeJournal")
    except gspread.WorksheetNotFound:
        j = sh.add_worksheet("TradeJournal", rows=2, cols=30)
        j.append_row(HEADERS_JOURNAL)
    try:
        o = sh.worksheet("_OpenLots")
    except gspread.WorksheetNotFound:
        o = sh.add_worksheet("_OpenLots", rows=2, cols=20)
        o.append_row(HEADERS_OPEN)
    try:
        c = sh.worksheet("_Config")
    except gspread.WorksheetNotFound:
        c = sh.add_worksheet("_Config", rows=5, cols=2)
        c.append_row(HEADERS_CONFIG)
        c.append_row(["KITE_ACCESS_TOKEN",""])
    return j, o, c

def get_ws():
    sh = get_spreadsheet()
    return ensure_sheets(sh)

def get_next_serial(ws_journal):
    vals = ws_journal.col_values(1)
    if len(vals) <= 1:
        return 1
    for v in reversed(vals[1:]):
        try: return int(v) + 1
        except: pass
    return 1

def append_journal_rows(ws_journal, rows):
    ws_journal.append_rows(rows, value_input_option="USER_ENTERED")

def config_get_token(ws_config):
    # expects a row with Key="KITE_ACCESS_TOKEN"
    rows = ws_config.get_all_records()
    for r in rows:
        if r.get("Key") == "KITE_ACCESS_TOKEN":
            return r.get("Value") or ""
    return ""

def config_set_token(ws_config, token: str):
    data = ws_config.get_all_values()
    # header at row 1
    found = False
    for idx in range(2, len(data)+1):
        if ws_config.cell(idx,1).value == "KITE_ACCESS_TOKEN":
            ws_config.update_cell(idx, 2, token)
            found = True
            break
    if not found:
        ws_config.append_row(["KITE_ACCESS_TOKEN", token])
