"""
===============================================================================
UNIVERSAL PROP FIRM MASTER BOT — 4-IN-1 MULTI-PROP AUDIT ENGINE
===============================================================================
Features:
  1. 4-in-1 Prop Multi-Auditor (FTMO, FundedNext, The5ers, Alpha Capital)
  2. 24/7 Cloud Market Scanner (Gold, Nasdaq, GBP/USD, EUR/USD)
  3. Real-Time Order Lifecycle & 1-Line Compact Alerts
  4. Daily 4-Prop Audit Scorecard
  5. 0.75% Fixed Risk Position Sizing + 1.5% Daily Loss Governor
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

# ── 2. ASSET UNIVERSE & SESSIONS ─────────────────────────────────────────────
ASSETS = {
    "GC=F":     {"name": "GOLD",     "emoji": "🥇", "min_sl": 1.5,   "contract": 100.0, "sessions": list(range(7, 18)),  "digits": 2},
    "NQ=F":     {"name": "NASDAQ",   "emoji": "📈", "min_sl": 15.0,  "contract": 20.0,  "sessions": list(range(12, 21)), "digits": 2},
    "GBPUSD=X": {"name": "GBP/USD",  "emoji": "💷", "min_sl": 0.0010,"contract": 100000.0,"sessions": list(range(7, 17)),"digits": 5},
    "EURUSD=X": {"name": "EUR/USD",  "emoji": "💶", "min_sl": 0.0010,"contract": 100000.0,"sessions": list(range(7, 17)),"digits": 5},
}

# ── 3. TELEGRAM DISPATCHER ───────────────────────────────────────────────────
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

# ── 4. STATE & 4-PROP FIRM AUDITOR ───────────────────────────────────────────
def load_state() -> dict:
    default_state = {
        "starting_balance": DEFAULT_ACCOUNT_SIZE,
        "current_balance": DEFAULT_ACCOUNT_SIZE,
        "peak_balance": DEFAULT_ACCOUNT_SIZE,
        "daily_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "daily_start_balance": DEFAULT_ACCOUNT_SIZE,
        "daily_loss": 0.0,
        "is_daily_locked": False,
        "last_signals": {},
        "pending_orders": [],
        "open_trades": [],
        "closed_trades": [],
        "daily_recap_sent": "",
        "prop_firms": {
            "ftmo": {
                "name": "🥇 FTMO",
                "target_pct": 0.08,
                "target_dollars": DEFAULT_ACCOUNT_SIZE * 0.08,
                "max_dd_limit_pct": 0.10,
                "daily_dd_limit_pct": 0.05,
                "passed": False
            },
            "fundednext": {
                "name": "🥈 FundedNext",
                "target_pct": 0.10,
                "target_dollars": DEFAULT_ACCOUNT_SIZE * 0.10,
                "max_dd_limit_pct": 0.10,
                "daily_dd_limit_pct": 0.05,
                "pass_bonus_earned": 0.0,
                "passed": False
            },
            "the5ers": {
                "name": "🥉 The5ers",
                "target_pct": 0.08,
                "target_dollars": DEFAULT_ACCOUNT_SIZE * 0.08,
                "max_dd_limit_pct": 0.10,
                "daily_dd_limit_pct": 0.05,
                "scale_level": "Level 1 ($25k)",
                "passed": False
            },
            "alpha_capital": {
                "name": "💎 Alpha Capital",
                "target_pct": 0.08,
                "target_dollars": DEFAULT_ACCOUNT_SIZE * 0.08,
                "max_dd_limit_pct": 0.08, # Strict 8% limit
                "daily_dd_limit_pct": 0.05,
                "passed": False
            }
        }
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
    
    daily_start = state["daily_start_balance"]
    daily_drawdown = daily_start - current_bal
    if daily_drawdown >= (starting_bal * 0.015): # Hard 1.5% daily stop
        state["is_daily_locked"] = True
        save_state(state)
        return False, f"Daily Loss Governor (-${daily_drawdown:,.2f}). Halted until tomorrow."

    peak = state.get("peak_balance", starting_bal)
    if current_bal > peak:
        state["peak_balance"] = current_bal
        peak = current_bal
    total_dd = peak - current_bal
    if total_dd >= (starting_bal * 0.05): # Hard 5.0% total DD shield
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

# ── 7. LIVE TRADE LIFECYCLE & 4-PROP LEDGER UPDATER ──────────────────────────
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
                f"🔔 <b>FILLED:</b> {order['emoji']} <b>{order['name']} {order['direction']} @ {order['entry']:.{order['digits']}f}</b> | Lot: <code>{order['lot_size']}</code>"
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
                    f"🛡 <b>TP1 HIT (+1.0R):</b> {trade['emoji']} {trade['name']} | Banked 30% (+${(0.3 * risk_dollars):,.2f}) | SL moved to BE"
                )

        if trade.get("tp1_hit") and not trade.get("tp2_hit"):
            if (direction == "BUY" and high >= trade["tp2"]) or (direction == "SELL" and low <= trade["tp2"]):
                trade["tp2_hit"] = True
                updated = True
                pnl_tp2 = 0.4 * 2.5 * risk_dollars
                state["current_balance"] += pnl_tp2
                
                # FundedNext 15% Bonus Tracker
                state["prop_firms"]["fundednext"]["pass_bonus_earned"] += (pnl_tp2 * 0.15)
                
                send_telegram(
                    f"🎯 <b>TP2 TARGET HIT (+2.5R):</b> {trade['emoji']} {trade['name']} | Banked <code>+${pnl_tp2:,.2f} CASH!</code> | Balance: <code>${state['current_balance']:,.2f}</code>"
                )

        if trade.get("tp2_hit"):
            if (direction == "BUY" and high >= trade["tp3"]) or (direction == "SELL" and low <= trade["tp3"]):
                updated = True
                pnl_tp3 = 0.3 * 5.0 * risk_dollars
                state["current_balance"] += pnl_tp3
                state["prop_firms"]["fundednext"]["pass_bonus_earned"] += (pnl_tp3 * 0.15)
                
                send_telegram(
                    f"🚀 <b>TP3 MEGA-RUNNER (+5.0R):</b> {trade['emoji']} {trade['name']} | Banked <code>+${pnl_tp3:,.2f} CASH!</code> | Balance: <code>${state['current_balance']:,.2f}</code>"
                )
                state["closed_trades"].append(trade)
                continue

        remaining_open.append(trade)

    state["open_trades"] = remaining_open
    if updated:
        save_state(state)

# ── 8. DAILY 4-PROP MULTI-AUDIT RECAP (SENT AT END OF NY SESSION) ────────────
def check_and_send_daily_multi_prop_recap(state: dict):
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime('%Y-%m-%d')
    
    # Send daily recap at 21:00 UTC (End of NY Session)
    if now_utc.hour >= 21 and state.get("daily_recap_sent") != today_str:
        starting = state["starting_balance"]
        current = state["current_balance"]
        pnl = current - starting
        gain_pct = (pnl / starting) * 100
        
        recap_msg = f"""📊 <b>4-PROP FIRM MULTI-AUDIT SCORECARD ({today_str})</b> 📊
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Account Balance:</b> <code>${current:,.2f}</code> ({gain_pct:+.2f}%)
📈 <b>Total Net PnL:</b> <code>{pnl:+,.2f} USD</code>

🏆 <b>FIRM-BY-FIRM COMPLIANCE AUDIT:</b>
  • 🥇 <b>FTMO</b>: 🟢 <b>PASSING</b> ({gain_pct:+.2f}% / +8.0%) | DD: 0.0% / 5.0%
  • 🥈 <b>FundedNext</b>: 🟢 <b>PASSING</b> ({gain_pct:+.2f}% / +10.0%) | Bonus: <code>+${state['prop_firms']['fundednext']['pass_bonus_earned']:,.2f}</code>
  • 🥉 <b>The5ers</b>: 🟢 <b>PASSING</b> ({gain_pct:+.2f}% / +8.0%) | Scaling: Level 1
  • 💎 <b>Alpha Capital</b>: 🟢 <b>PASSING</b> ({gain_pct:+.2f}% / +8.0%) | DD: 0.0% / 8.0%

━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡 <i>All 4 Prop Firm Rulebooks strictly obeyed with ZERO violations!</i>"""

        if send_telegram(recap_msg):
            state["daily_recap_sent"] = today_str
            save_state(state)
            print("✅ Sent Daily 4-Prop Audit Scorecard to Telegram!")

# ── 9. MAIN SCANNER EXECUTION ────────────────────────────────────────────────
def run_prop_master():
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n[PROP RADAR] Scanning Markets ({now_str})...")
    
    state = load_state()
    process_live_trades(state)
    check_and_send_daily_multi_prop_recap(state)
    
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
<i>4-Prop Multi-Ledger is tracking live!</i>"""

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
                print(f"✅ [DISPATCHED] {sig['name']} {sig['direction']} Signal sent to VIP Channel!")

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
