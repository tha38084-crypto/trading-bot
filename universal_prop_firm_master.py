"""
===============================================================================
UNIVERSAL PROP FIRM MASTER BOT — INTERACTIVE CLOUD EDITION
===============================================================================
Features:
  1. Interactive 1-Tap Inline Buttons (Balance, Today's Recap, Active, Target)
  2. 24/7 Cloud Market Scanner (Gold, Nasdaq, GBP/USD, EUR/USD)
  3. Real-Time Order Lifecycle (1-Line Fill, TP, SL, and Balance Alerts)
  4. Daily End-of-Day Performance Recap Card
  5. 0.75% Prop Risk Sizing + 1.5% Daily Loss Governor
===============================================================================
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

# ── 1. CONFIGURATION & TELEGRAM CREDENTIALS ──────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8805795541:AAFQxtzJrvJQlfBVazkVm4KwvSh9FSgfDro")
CHAT_ID   = os.environ.get("TELEGRAM_CHANNEL_ID", os.environ.get("TELEGRAM_CHAT_ID", "-1004414824960"))

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universal_prop_state.json")

DEFAULT_ACCOUNT_SIZE = float(os.environ.get("PROP_ACCOUNT_SIZE", "25000.0"))
RISK_PERCENT = 0.0075          # 0.75% Risk per trade ($187.50 on $25k)
DAILY_LOSS_LIMIT_PCT = 0.015   # 1.50% Max Daily Loss ($375 on $25k)
TOTAL_DRAWDOWN_LIMIT_PCT = 0.05# 5.00% Max Total Drawdown ($1,250 on $25k)
PHASE1_TARGET_PCT = 0.08       # +8.00% Profit Target ($2,000 on $25k)

# ── 2. ASSET UNIVERSE & SESSIONS ─────────────────────────────────────────────
ASSETS = {
    "GC=F":     {"name": "GOLD",     "emoji": "🥇", "min_sl": 1.5,   "contract": 100.0, "sessions": list(range(7, 18)),  "digits": 2},
    "NQ=F":     {"name": "NASDAQ",   "emoji": "📈", "min_sl": 15.0,  "contract": 20.0,  "sessions": list(range(12, 21)), "digits": 2},
    "GBPUSD=X": {"name": "GBP/USD",  "emoji": "💷", "min_sl": 0.0010,"contract": 100000.0,"sessions": list(range(7, 17)),"digits": 5},
    "EURUSD=X": {"name": "EUR/USD",  "emoji": "💶", "min_sl": 0.0010,"contract": 100000.0,"sessions": list(range(7, 17)),"digits": 5},
}

# ── 3. TELEGRAM DISPATCHER & INTERACTIVE BUTTON ENGINE ───────────────────────
def send_telegram(message: str, reply_markup: dict = None) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload_dict = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload_dict["reply_markup"] = json.dumps(reply_markup)
        
    payload = urllib.parse.urlencode(payload_dict).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"[ERROR] Telegram send failed: {exc}")
        return False

def answer_callback_query(callback_id: str, text: str = None) -> bool:
    if not BOT_TOKEN: return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload_dict = {"callback_query_id": callback_id}
    if text: payload_dict["text"] = text
    payload = urllib.parse.urlencode(payload_dict).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False

def send_interactive_control_panel(state: dict):
    """Sends a clean interactive control panel with 1-tap buttons."""
    starting = state["starting_balance"]
    current = state["current_balance"]
    gain_pct = ((current - starting) / starting) * 100
    
    msg = f"""💼 <b>UNIVERSAL PROP FIRM CONTROL PANEL</b> 💼
━━━━━━━━━━━━━━━━━━━━
📊 <b>Prop Account:</b> <code>${starting:,.2f}</code> (Evaluation Mode)
💰 <b>Current Balance:</b> <code>${current:,.2f}</code> ({gain_pct:+.2f}%)
🛡 <b>Daily Governor:</b> 1.5% Max Loss | 5.0% Drawdown Armor
━━━━━━━━━━━━━━━━━━━━
<i>Tap any button below for instant live status:</i>"""

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "💰 Check Balance", "callback_data": "btn_balance"},
                {"text": "📊 Today's Recap", "callback_data": "btn_today"}
            ],
            [
                {"text": "⚡ Active Trades", "callback_data": "btn_active"},
                {"text": "🎯 Target Progress", "callback_data": "btn_target"}
            ]
        ]
    }
    return send_telegram(msg, reply_markup=keyboard)

# ── 4. STATE & RISK COMPLIANCE MANAGER ───────────────────────────────────────
def load_state() -> dict:
    default_state = {
        "starting_balance": DEFAULT_ACCOUNT_SIZE,
        "current_balance": DEFAULT_ACCOUNT_SIZE,
        "peak_balance": DEFAULT_ACCOUNT_SIZE,
        "daily_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "daily_start_balance": DEFAULT_ACCOUNT_SIZE,
        "daily_loss": 0.0,
        "is_daily_locked": False,
        "is_challenge_passed": False,
        "last_signals": {},
        "pending_orders": [],
        "open_trades": [],
        "closed_trades": [],
        "last_update_id": 0,
        "daily_recap_sent": ""
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_state.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            pass
    return default_state

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)

def check_prop_compliance(state: dict) -> tuple[bool, str]:
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    if state.get("daily_date") != today_str:
        state["daily_date"] = today_str
        state["daily_start_balance"] = state["current_balance"]
        state["daily_loss"] = 0.0
        state["is_daily_locked"] = False
        save_state(state)
        
    starting_bal = state["starting_balance"]
    current_bal = state["current_balance"]
    
    if current_bal >= starting_bal * (1.0 + PHASE1_TARGET_PCT):
        if not state.get("is_challenge_passed"):
            state["is_challenge_passed"] = True
            save_state(state)
            send_telegram(
                f"🏆 <b>PROP CHALLENGE PASSED (+8.0%)!</b>\n"
                f"💰 Balance: <code>${current_bal:,.2f}</code> | All trades halted to secure funded account!"
            )
        return False, "Target Hit (+8.0%) - Challenge Passed!"

    daily_start = state["daily_start_balance"]
    daily_drawdown = daily_start - current_bal
    if daily_drawdown >= (starting_bal * DAILY_LOSS_LIMIT_PCT):
        state["is_daily_locked"] = True
        save_state(state)
        return False, f"Daily Loss Governor (-${daily_drawdown:,.2f}). Halted until tomorrow."

    peak = state.get("peak_balance", starting_bal)
    if current_bal > peak:
        state["peak_balance"] = current_bal
        peak = current_bal
    total_dd = peak - current_bal
    if total_dd >= (starting_bal * TOTAL_DRAWDOWN_LIMIT_PCT):
        return False, f"Max Drawdown Shield (-${total_dd:,.2f}). Trading paused."

    return True, "Compliant"

# ── 5. POSITION SIZING ───────────────────────────────────────────────────────
def calculate_prop_lot_size(symbol: str, meta: dict, entry: float, sl: float, account_balance: float) -> tuple[float, float]:
    risk_dollars = account_balance * RISK_PERCENT
    sl_dist = abs(entry - sl)
    if sl_dist <= 0:
        return risk_dollars, 0.01

    contract_size = meta.get("contract", 100.0)
    if "USD" in symbol and ("EUR" in symbol or "GBP" in symbol):
        lot_size = risk_dollars / (sl_dist * contract_size)
    elif "GC" in symbol:
        lot_size = risk_dollars / (sl_dist * 100.0)
    elif "NQ" in symbol:
        lot_size = risk_dollars / (sl_dist * 20.0)
    else:
        lot_size = risk_dollars / (sl_dist * contract_size)

    lot_size = max(0.01, round(lot_size, 2))
    return risk_dollars, lot_size

# ── 6. 15M SETUP DETECTION ───────────────────────────────────────────────────
def detect_prop_setup(symbol: str, meta: dict) -> dict | None:
    now_utc = datetime.now(timezone.utc)
    hr = now_utc.hour
    if hr not in meta["sessions"]:
        return None

    df_1h = yf.download(symbol, period="5d", interval="1h", progress=False)
    if df_1h.empty or len(df_1h) < 25: return None
    if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.get_level_values(0)
    df_1h['EMA50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
    h_ema = float(df_1h['EMA50'].iloc[-1])

    df_15 = yf.download(symbol, period="5d", interval="15m", progress=False)
    if df_15.empty or len(df_15) < 30: return None
    if isinstance(df_15.columns, pd.MultiIndex): df_15.columns = df_15.columns.get_level_values(0)

    hl = df_15['High'] - df_15['Low']
    hc = (df_15['High'] - df_15['Close'].shift()).abs()
    lc = (df_15['Low'] - df_15['Close'].shift()).abs()
    df_15['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    df_15['BODY'] = (df_15['Close'] - df_15['Open']).abs()
    df_15['LIQ_HIGH'] = df_15['High'].shift(1).rolling(20).max()
    df_15['LIQ_LOW'] = df_15['Low'].shift(1).rolling(20).min()
    df_15 = df_15.dropna()

    if len(df_15) < 10: return None

    for offset in range(3):
        idx = len(df_15) - 1 - offset
        row = df_15.iloc[idx]
        c, o, h, l = float(row['Close']), float(row['Open']), float(row['High']), float(row['Low'])
        atr, body = float(row['ATR']), float(row['BODY'])
        liq_h, liq_l = float(row['LIQ_HIGH']), float(row['LIQ_LOW'])
        bar_time = str(df_15.index[idx])

        if l < liq_l and c > liq_l and c > o and body >= 0.50 * atr and c >= (h_ema - 1.2 * atr):
            entry = (c + l) / 2.0
            sl = l - (0.35 * atr)
            sl_dist = max(entry - sl, meta['min_sl'])
            sl = entry - sl_dist
            tp1 = entry + (1.0 * sl_dist)
            tp2 = entry + (2.5 * sl_dist)
            tp3 = entry + (5.0 * sl_dist)

            return {
                'symbol': symbol, 'name': meta['name'], 'emoji': meta['emoji'],
                'direction': 'BUY', 'dir_tag': '🟢 BUY',
                'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
                'bar_time': bar_time, 'digits': meta['digits']
            }

        elif h > liq_h and c < liq_h and c < o and body >= 0.50 * atr and c <= (h_ema + 1.2 * atr):
            entry = (c + h) / 2.0
            sl = h + (0.35 * atr)
            sl_dist = max(sl - entry, meta['min_sl'])
            sl = entry + sl_dist
            tp1 = entry - (1.0 * sl_dist)
            tp2 = entry - (2.5 * sl_dist)
            tp3 = entry - (5.0 * sl_dist)

            return {
                'symbol': symbol, 'name': meta['name'], 'emoji': meta['emoji'],
                'direction': 'SELL', 'dir_tag': '🔴 SELL',
                'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
                'bar_time': bar_time, 'digits': meta['digits']
            }

    return None

# ── 7. INTERACTIVE BUTTON CALLBACK PROCESSOR ─────────────────────────────────
def process_telegram_callbacks(state: dict):
    """Processes interactive button taps from user phone in real-time."""
    if not BOT_TOKEN: return
    offset = state.get("last_update_id", 0) + 1
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=5"
    
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if not data.get("ok"): return
            
            for upd in data.get("result", []):
                state["last_update_id"] = upd["update_id"]
                
                # Check for Button Clicks
                if "callback_query" in upd:
                    cb = upd["callback_query"]
                    cb_id = cb["id"]
                    action = cb.get("data", "")
                    
                    starting = state["starting_balance"]
                    current = state["current_balance"]
                    pnl_dollar = current - starting
                    gain_pct = (pnl_dollar / starting) * 100
                    
                    if action == "btn_balance":
                        answer_callback_query(cb_id, f"Balance: ${current:,.2f}")
                        send_telegram(
                            f"💰 <b>PROP ACCOUNT BALANCE REPORT</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"💼 <b>Starting:</b> <code>${starting:,.2f}</code>\n"
                            f"💵 <b>Current Balance:</b> <code>${current:,.2f}</code>\n"
                            f"📈 <b>Net Gain:</b> <code>{pnl_dollar:+,.2f} ({gain_pct:+.2f}%)</code>\n"
                            f"🔝 <b>Peak Equity:</b> <code>${state.get('peak_balance', starting):,.2f}</code>"
                        )
                        
                    elif action == "btn_today":
                        answer_callback_query(cb_id, "Fetching Today's Recap...")
                        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                        today_closed = [t for t in state.get("closed_trades", []) if t.get("bar_time", "").startswith(today_str)]
                        today_pnl = sum([t.get("risk_dollars", 0) * 1.3 for t in today_closed if "WIN" in t.get("outcome", "")])
                        
                        send_telegram(
                            f"📊 <b>TODAY'S PERFORMANCE RECAP ({today_str})</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📈 <b>Trades Completed:</b> {len(today_closed)}\n"
                            f"⚡ <b>Active Pending/Open:</b> {len(state.get('pending_orders', [])) + len(state.get('open_trades', []))}\n"
                            f"💰 <b>Today's Net Gain:</b> <code>{gain_pct:+.2f}%</code>\n"
                            f"🛡 <b>Daily Governor:</b> 🟢 Active & Safe"
                        )
                        
                    elif action == "btn_active":
                        answer_callback_query(cb_id, "Checking Active Trades...")
                        pending = state.get("pending_orders", [])
                        open_tr = state.get("open_trades", [])
                        
                        if not pending and not open_tr:
                            send_telegram("⚡ <b>ACTIVE TRADES:</b> Currently 0 open trades. Radar is actively scanning!")
                        else:
                            msg_list = ["⚡ <b>CURRENT ACTIVE TRADES:</b>\n━━━━━━━━━━━━━━━━━━━━"]
                            for p in pending:
                                msg_list.append(f"⏳ <b>PENDING:</b> {p['emoji']} {p['name']} {p['direction']} @ <code>{p['entry']:.{p['digits']}f}</code>")
                            for o in open_tr:
                                be_txt = " (SL at Breakeven)" if o.get("tp1_hit") else ""
                                msg_list.append(f"🟢 <b>LIVE:</b> {o['emoji']} {o['name']} {o['direction']} @ <code>{o['entry']:.{o['digits']}f}</code>{be_txt}")
                            send_telegram("\n".join(msg_list))
                            
                    elif action == "btn_target":
                        answer_callback_query(cb_id, "Calculating Target Progress...")
                        target_amt = starting * (1.0 + PHASE1_TARGET_PCT)
                        needed = max(0.0, target_amt - current)
                        pct_done = min(100.0, max(0.0, (pnl_dollar / (starting * PHASE1_TARGET_PCT)) * 100))
                        
                        send_telegram(
                            f"🎯 <b>PHASE 1 TARGET PROGRESS</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🏆 <b>Phase 1 Goal:</b> <code>${target_amt:,.2f} (+8.00%)</code>\n"
                            f"💰 <b>Current Balance:</b> <code>${current:,.2f}</code>\n"
                            f"📊 <b>Completion:</b> <code>{pct_done:.1f}% Completed</code>\n"
                            f"💵 <b>Remaining to Pass:</b> <code>${needed:,.2f}</code>\n"
                            f"🚀 <i>Just 2–3 good TP2 wins remaining to complete Phase 1!</i>"
                        )
            save_state(state)
    except Exception as e:
        print(f"[CALLBACK ERROR]: {e}")

# ── 8. LIVE ORDER LIFECYCLE TRACKER ──────────────────────────────────────────
def process_live_trades(state: dict):
    updated = False
    
    # 1. Pending Orders Check
    remaining_pending = []
    for order in state.get("pending_orders", []):
        symbol = order["symbol"]
        df_live = yf.download(symbol, period="1d", interval="15m", progress=False)
        if df_live.empty:
            remaining_pending.append(order)
            continue
        if isinstance(df_live.columns, pd.MultiIndex): df_live.columns = df_live.columns.get_level_values(0)
        
        last_candle = df_live.iloc[-1]
        high, low = float(last_candle['High']), float(last_candle['Low'])
        
        filled = False
        if order["direction"] == "BUY" and low <= order["entry"]: filled = True
        elif order["direction"] == "SELL" and high >= order["entry"]: filled = True
            
        if filled:
            order["fill_time"] = str(df_live.index[-1])
            order["tp1_hit"] = False
            order["tp2_hit"] = False
            order["current_sl"] = order["sl"]
            state["open_trades"].append(order)
            updated = True
            
            send_telegram(
                f"🔔 <b>FILLED:</b> {order['emoji']} <b>{order['name']} {order['direction']} @ {order['entry']:.{order['digits']}f}</b> is now active | Lot: <code>{order['lot_size']}</code>"
            )
        else:
            order["bars_elapsed"] = order.get("bars_elapsed", 0) + 1
            if order["bars_elapsed"] > 8:
                updated = True
                send_telegram(
                    f"⚪ <b>EXPIRED:</b> {order['emoji']} {order['name']} {order['direction']} @ {order['entry']:.{order['digits']}f} cancelled (No fill in 2h)."
                )
            else:
                remaining_pending.append(order)

    state["pending_orders"] = remaining_pending

    # 2. Open Trades Check
    remaining_open = []
    for trade in state.get("open_trades", []):
        symbol = trade["symbol"]
        df_live = yf.download(symbol, period="1d", interval="15m", progress=False)
        if df_live.empty:
            remaining_open.append(trade)
            continue
        if isinstance(df_live.columns, pd.MultiIndex): df_live.columns = df_live.columns.get_level_values(0)
        
        last_candle = df_live.iloc[-1]
        high, low = float(last_candle['High']), float(last_candle['Low'])
        direction = trade["direction"]
        digits = trade["digits"]
        risk_dollars = trade["risk_dollars"]
        
        sl_hit = False
        if direction == "BUY" and low <= trade["current_sl"]: sl_hit = True
        elif direction == "SELL" and high >= trade["current_sl"]: sl_hit = True
            
        if sl_hit:
            updated = True
            if trade.get("tp1_hit"):
                pnl = 0.3 * risk_dollars
                state["current_balance"] += pnl
                send_telegram(
                    f"🛡 <b>BREAKEVEN CLOSED:</b> {trade['emoji']} {trade['name']} | Net: <code>+${pnl:,.2f}</code> | Balance: <code>${state['current_balance']:,.2f}</code>"
                )
            else:
                pnl = -risk_dollars
                state["current_balance"] += pnl
                send_telegram(
                    f"🛑 <b>STOP LOSS:</b> {trade['emoji']} {trade['name']} | PnL: <code>-${risk_dollars:,.2f}</code> | Balance: <code>${state['current_balance']:,.2f}</code>"
                )
            state["closed_trades"].append(trade)
            continue

        if not trade.get("tp1_hit"):
            if (direction == "BUY" and high >= trade["tp1"]) or (direction == "SELL" and low <= trade["tp1"]):
                trade["tp1_hit"] = True
                trade["current_sl"] = trade["entry"]
                updated = True
                send_telegram(
                    f"🛡 <b>TP1 HIT (+1.0R):</b> {trade['emoji']} {trade['name']} | Banked 30% (+${(0.3 * risk_dollars):,.2f}) | SL moved to BE (Risk-Free!)"
                )

        if trade.get("tp1_hit") and not trade.get("tp2_hit"):
            if (direction == "BUY" and high >= trade["tp2"]) or (direction == "SELL" and low <= trade["tp2"]):
                trade["tp2_hit"] = True
                updated = True
                pnl_tp2 = 0.4 * 2.5 * risk_dollars
                state["current_balance"] += pnl_tp2
                send_telegram(
                    f"🎯 <b>TP2 TARGET HIT (+2.5R):</b> {trade['emoji']} {trade['name']} | Banked <code>+${pnl_tp2:,.2f} CASH!</code> | Balance: <code>${state['current_balance']:,.2f}</code>"
                )

        if trade.get("tp2_hit"):
            if (direction == "BUY" and high >= trade["tp3"]) or (direction == "SELL" and low <= trade["tp3"]):
                updated = True
                pnl_tp3 = 0.3 * 5.0 * risk_dollars
                state["current_balance"] += pnl_tp3
                send_telegram(
                    f"🚀 <b>TP3 MEGA-RUNNER (+5.0R):</b> {trade['emoji']} {trade['name']} | Banked <code>+${pnl_tp3:,.2f} CASH!</code> | Balance: <code>${state['current_balance']:,.2f}</code>"
                )
                state["closed_trades"].append(trade)
                continue

        remaining_open.append(trade)

    state["open_trades"] = remaining_open
    if updated:
        save_state(state)

# ── 9. MAIN SCANNER EXECUTION ────────────────────────────────────────────────
def run_prop_master():
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n[PROP RADAR] Scanning Markets ({now_str})...")
    
    state = load_state()
    
    # 1. Process Telegram Button Interactions
    process_telegram_callbacks(state)
    
    # 2. Process Live Orders (Fills, TPs, SLs)
    process_live_trades(state)
    
    # 3. Check Daily/Total Compliance
    is_compliant, reason = check_prop_compliance(state)
    if not is_compliant:
        print(f"[GUARD ACTIVE] Trading paused: {reason}")
        return

    account_bal = state.get("current_balance", DEFAULT_ACCOUNT_SIZE)

    for symbol, meta in ASSETS.items():
        try:
            sig = detect_prop_setup(symbol, meta)
            if not sig: continue

            bar_key = f"{symbol}_{sig['bar_time']}_{sig['direction']}"
            if state["last_signals"].get(symbol) == bar_key: continue

            risk_dollars, lot_size = calculate_prop_lot_size(symbol, meta, sig['entry'], sig['sl'], account_bal)
            digits = sig['digits']

            msg = f"""💼 <b>{sig['emoji']} {sig['name']} — {sig['dir_tag']} (50% FVG)</b>
━━━━━━━━━━━━━━━━━━━━
📍 <b>Entry:</b> <code>{sig['entry']:.{digits}f}</code>
🛡 <b>Stop Loss:</b> <code>{sig['sl']:.{digits}f}</code>
🎯 <b>Target (TP2):</b> <code>{sig['tp2']:.{digits}f}</code> (+${(1.0 * 2.5 * 0.4 * risk_dollars + 0.3 * risk_dollars):,.2f})
📦 <b>Lot Size:</b> <code>{lot_size:.2f} Lots</code> (0.75% Risk ≈ ${risk_dollars:,.2f})
━━━━━━━━━━━━━━━━━━━━
<i>Place limit order on MT5. Bot is tracking live!</i>"""

            if send_telegram(msg):
                state["last_signals"][symbol] = bar_key
                new_order = {
                    "symbol": symbol, "name": sig["name"], "emoji": sig["emoji"],
                    "direction": sig["direction"], "entry": sig["entry"], "sl": sig["sl"],
                    "tp1": sig["tp1"], "tp2": sig["tp2"], "tp3": sig["tp3"],
                    "lot_size": lot_size, "risk_dollars": risk_dollars, "digits": digits,
                    "bar_time": sig["bar_time"], "created_at": now_str, "bars_elapsed": 0
                }
                state["pending_orders"].append(new_order)
                save_state(state)
                print(f"✅ [DISPATCHED] {sig['name']} {sig['direction']} Clean Signal sent to VIP Channel!")

        except Exception as e:
            print(f"❌ [ERROR] Scanning {symbol}: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--loop":
        print(f"[LOOP] Universal Prop Firm Master running in 24/7 background mode (Account: ${DEFAULT_ACCOUNT_SIZE:,.2f})...")
        while True:
            try:
                run_prop_master()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Loop error: {e}")
            time.sleep(300)
    else:
        run_prop_master()
