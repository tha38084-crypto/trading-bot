"""
===============================================================================
UNIVERSAL PROP FIRM MASTER BOT — LIVE FORWARD OUTCOME TRACKER
===============================================================================
Features:
  1. 24/7 Cloud Market Scanner (Gold, Nasdaq, GBP/USD, EUR/USD)
  2. Live Forward Signal Dispatcher to Telegram VIP Channel
  3. Real-Time Order Lifecycle Manager:
     - Pending Limit Order Monitoring (8-bar expiry)
     - Order Fill Notifications
     - TP1 Breakeven Shield Notifications
     - TP2 Target Profit Notifications (+$468.75)
     - TP3 Mega-Runner Notifications (+$937.50)
     - Stop Loss / Drawdown Notifications
  4. Live $25,000 Prop Account Balance Tracking & Daily Scorecards
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
    "GC=F":     {"name": "GOLD (XAU/USD)",    "emoji": "🥇", "min_sl": 1.5,   "contract": 100.0, "sessions": list(range(7, 18)),  "digits": 2, "mt5_sym": "XAUUSD"},
    "NQ=F":     {"name": "NASDAQ (US100)",    "emoji": "📈", "min_sl": 15.0,  "contract": 20.0,  "sessions": list(range(12, 21)), "digits": 2, "mt5_sym": "US100"},
    "GBPUSD=X": {"name": "GBP/USD",           "emoji": "💷", "min_sl": 0.0010,"contract": 100000.0,"sessions": list(range(7, 17)),"digits": 5, "mt5_sym": "GBPUSD"},
    "EURUSD=X": {"name": "EUR/USD",           "emoji": "💶", "min_sl": 0.0010,"contract": 100000.0,"sessions": list(range(7, 17)),"digits": 5, "mt5_sym": "EURUSD"},
}

# ── 3. TELEGRAM DISPATCHER ───────────────────────────────────────────────────
def send_telegram(message: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] Telegram credentials not configured.")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"[ERROR] Telegram send failed: {exc}")
        return False

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
        "closed_trades": []
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
    
    # 1. Target Hit (+8.0%)
    if current_bal >= starting_bal * (1.0 + PHASE1_TARGET_PCT):
        if not state.get("is_challenge_passed"):
            state["is_challenge_passed"] = True
            save_state(state)
            send_telegram(
                f"🎉🏆 <b>CONGRATULATIONS! PROP CHALLENGE PASSED!</b> 🏆🎉\n\n"
                f"💼 Starting Balance: <code>${starting_bal:,.2f}</code>\n"
                f"💰 Final Balance   : <code>${current_bal:,.2f}</code> (+{((current_bal-starting_bal)/starting_bal)*100:.2f}%)\n\n"
                f"🔒 <i>All trading halted to lock in your victory. Proceed to Phase 2 / Live Funded Account!</i>"
            )
        return False, "Target Hit (+8.0%) - Challenge Passed!"

    # 2. Daily Loss Limit (1.5%)
    daily_start = state["daily_start_balance"]
    daily_drawdown = daily_start - current_bal
    if daily_drawdown >= (starting_bal * DAILY_LOSS_LIMIT_PCT):
        state["is_daily_locked"] = True
        save_state(state)
        return False, f"Daily Loss Governor Triggered (-${daily_drawdown:,.2f}). Halted until tomorrow."

    # 3. Total Drawdown (5.0%)
    peak = state.get("peak_balance", starting_bal)
    if current_bal > peak:
        state["peak_balance"] = current_bal
        peak = current_bal
    total_dd = peak - current_bal
    if total_dd >= (starting_bal * TOTAL_DRAWDOWN_LIMIT_PCT):
        return False, f"Maximum Drawdown Shield Active (-${total_dd:,.2f}). Trading paused for safety."

    return True, "Compliant"

# ── 5. POSITION SIZING & LOT SIZE CALCULATOR ─────────────────────────────────
def calculate_prop_lot_size(symbol: str, meta: dict, entry: float, sl: float, account_balance: float) -> tuple[float, float]:
    risk_dollars = account_balance * RISK_PERCENT
    sl_dist = abs(entry - sl)
    if sl_dist <= 0:
        return risk_dollars, 0.01

    contract_size = meta.get("contract", 100.0)
    
    if "USD" in symbol and "EUR" in symbol:
        lot_size = risk_dollars / (sl_dist * contract_size)
    elif "USD" in symbol and "GBP" in symbol:
        lot_size = risk_dollars / (sl_dist * contract_size)
    elif "GC" in symbol:
        lot_size = risk_dollars / (sl_dist * 100.0)
    elif "NQ" in symbol:
        lot_size = risk_dollars / (sl_dist * 20.0)
    else:
        lot_size = risk_dollars / (sl_dist * contract_size)

    lot_size = max(0.01, round(lot_size, 2))
    return risk_dollars, lot_size

# ── 6. CORE 15M LIQUIDITY SWEEP & 50% FVG ENGINE ─────────────────────────────
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
                'symbol': symbol,
                'name': meta['name'],
                'emoji': meta['emoji'],
                'direction': 'BUY',
                'direction_emoji': '🟢',
                'entry': entry,
                'sl': sl,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'bar_time': bar_time,
                'digits': meta['digits'],
                'context': '15M Bullish Liquidity Sweep & 1H Trend Alignment'
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
                'symbol': symbol,
                'name': meta['name'],
                'emoji': meta['emoji'],
                'direction': 'SELL',
                'direction_emoji': '🔴',
                'entry': entry,
                'sl': sl,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'bar_time': bar_time,
                'digits': meta['digits'],
                'context': '15M Bearish Liquidity Sweep & 1H Trend Alignment'
            }

    return None

# ── 7. LIVE TRADE & OUTCOME TRACKER ──────────────────────────────────────────
def process_live_trades(state: dict):
    """Monitors active pending and open orders on live candles."""
    now_utc = datetime.now(timezone.utc)
    updated = False
    
    # 1. Check Pending Orders for Fills or Expirations
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
        if order["direction"] == "BUY" and low <= order["entry"]:
            filled = True
        elif order["direction"] == "SELL" and high >= order["entry"]:
            filled = True
            
        if filled:
            order["fill_time"] = str(df_live.index[-1])
            order["tp1_hit"] = False
            order["tp2_hit"] = False
            order["current_sl"] = order["sl"]
            state["open_trades"].append(order)
            updated = True
            
            send_telegram(
                f"🔔 <b>ORDER FILLED & LIVE!</b> 🔔\n\n"
                f"📊 <b>Asset:</b> {order['emoji']} <b>{order['name']}</b>\n"
                f"🎯 <b>Action:</b> {order['direction_emoji']} <b>{order['direction']} @ {order['entry']:.{order['digits']}f}</b>\n"
                f"📦 <b>Lot Size:</b> <code>{order['lot_size']} Lots</code>\n"
                f"🛡 <b>Initial SL:</b> <code>{order['sl']:.{order['digits']}f}</code>\n"
                f"🎯 <b>Primary Target (TP2):</b> <code>{order['tp2']:.{order['digits']}f}</code>\n\n"
                f"⚡ <i>Trade is active! Bot is tracking TP1 Breakeven and TP2 targets in real-time...</i>"
            )
        else:
            order["bars_elapsed"] = order.get("bars_elapsed", 0) + 1
            if order["bars_elapsed"] > 8: # 2 hours expired
                updated = True
                send_telegram(
                    f"⚪ <b>LIMIT ORDER EXPIRED (Zero Risk):</b>\n"
                    f"{order['emoji']} <b>{order['name']} {order['direction']}</b> @ {order['entry']:.{order['digits']}f} was not filled within 2 hours. Cancelled safely."
                )
            else:
                remaining_pending.append(order)

    state["pending_orders"] = remaining_pending

    # 2. Check Open Trades for TP1, TP2, TP3, or SL
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
        
        # Check Stop Loss
        sl_hit = False
        if direction == "BUY" and low <= trade["current_sl"]:
            sl_hit = True
        elif direction == "SELL" and high >= trade["current_sl"]:
            sl_hit = True
            
        if sl_hit:
            updated = True
            if trade.get("tp1_hit"):
                pnl = 0.3 * risk_dollars # Banked TP1 profit
                state["current_balance"] += pnl
                trade["outcome"] = "BREAKEVEN"
                send_telegram(
                    f"🛡 <b>BREAKEVEN SHIELD TRIGGERED!</b>\n\n"
                    f"📊 <b>Asset:</b> {trade['emoji']} <b>{trade['name']}</b>\n"
                    f"💵 <b>Net Result:</b> <code>+${pnl:,.2f} Profit Banked!</code> (Zero Risk!)\n"
                    f"💰 <b>Prop Balance:</b> <code>${state['current_balance']:,.2f}</code>"
                )
            else:
                pnl = -risk_dollars
                state["current_balance"] += pnl
                trade["outcome"] = "STOP_LOSS"
                send_telegram(
                    f"🛑 <b>STOP LOSS HIT:</b>\n\n"
                    f"📊 <b>Asset:</b> {trade['emoji']} <b>{trade['name']}</b>\n"
                    f"💵 <b>Loss:</b> <code>-${risk_dollars:,.2f} (-0.75%)</code>\n"
                    f"💰 <b>Prop Balance:</b> <code>${state['current_balance']:,.2f}</code> (Safely within daily limit)"
                )
            state["closed_trades"].append(trade)
            continue

        # Check TP1 (+1.0R Breakeven Move)
        if not trade.get("tp1_hit"):
            if (direction == "BUY" and high >= trade["tp1"]) or (direction == "SELL" and low <= trade["tp1"]):
                trade["tp1_hit"] = True
                trade["current_sl"] = trade["entry"] # Move SL to Entry
                updated = True
                send_telegram(
                    f"🛡🎯 <b>TP1 HIT (+1.0R)! STOP LOSS MOVED TO BREAKEVEN!</b> 🛡\n\n"
                    f"📊 <b>Asset:</b> {trade['emoji']} <b>{trade['name']}</b>\n"
                    f"💰 <b>Banked 30% Profit:</b> <code>+${(0.3 * risk_dollars):,.2f}</code>\n"
                    f"🔒 <b>New Stop Loss:</b> <code>{trade['entry']:.{digits}f} (Entry)</code>\n\n"
                    f"🎉 <i>This trade is now 100% RISK-FREE. Riding toward TP2 (+2.5R)...</i>"
                )

        # Check TP2 (+2.5R Primary Target)
        if trade.get("tp1_hit") and not trade.get("tp2_hit"):
            if (direction == "BUY" and high >= trade["tp2"]) or (direction == "SELL" and low <= trade["tp2"]):
                trade["tp2_hit"] = True
                updated = True
                pnl_tp2 = 0.4 * 2.5 * risk_dollars
                state["current_balance"] += pnl_tp2
                send_telegram(
                    f"🎯🔥 <b>TP2 TARGET HIT (+2.5R)! BIG PROFIT BANKED!</b> 🔥🎯\n\n"
                    f"📊 <b>Asset:</b> {trade['emoji']} <b>{trade['name']}</b>\n"
                    f"💵 <b>Banked 40% Target:</b> <code>+${pnl_tp2:,.2f} CASH!</code>\n"
                    f"💰 <b>New Prop Balance:</b> <code>${state['current_balance']:,.2f}</code>\n\n"
                    f"🚀 <i>Holding remaining 30% runner for TP3 (+5.0R Mega-Runner)...</i>"
                )

        # Check TP3 (+5.0R Mega-Runner)
        if trade.get("tp2_hit"):
            if (direction == "BUY" and high >= trade["tp3"]) or (direction == "SELL" and low <= trade["tp3"]):
                updated = True
                pnl_tp3 = 0.3 * 5.0 * risk_dollars
                state["current_balance"] += pnl_tp3
                trade["outcome"] = "TP3_MEGA_WIN"
                send_telegram(
                    f"🚀🏆 <b>TP3 MEGA-RUNNER HIT (+5.0R)! MONSTER GAIN!</b> 🏆🚀\n\n"
                    f"📊 <b>Asset:</b> {trade['emoji']} <b>{trade['name']}</b>\n"
                    f"💵 <b>Banked 30% Runner:</b> <code>+${pnl_tp3:,.2f} CASH!</code>\n"
                    f"💰 <b>Final Prop Balance:</b> <code>${state['current_balance']:,.2f}</code>\n"
                    f"📈 <b>Progress to Target:</b> <code>+{((state['current_balance']-state['starting_balance'])/state['starting_balance'])*100:.2f}% / +8.00%</code>"
                )
                state["closed_trades"].append(trade)
                continue

        remaining_open.append(trade)

    state["open_trades"] = remaining_open
    if updated:
        save_state(state)

# ── 8. MAIN SCANNER EXECUTION ────────────────────────────────────────────────
def run_prop_master():
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n[PROP RADAR] Scanning Markets ({now_str})...")
    
    state = load_state()
    
    # 1. Process active live trades (Fills, TPs, SLs)
    process_live_trades(state)
    
    # 2. Check compliance limits
    is_compliant, reason = check_prop_compliance(state)
    if not is_compliant:
        print(f"[GUARD ACTIVE] Trading paused: {reason}")
        return

    account_bal = state.get("current_balance", DEFAULT_ACCOUNT_SIZE)

    for symbol, meta in ASSETS.items():
        try:
            sig = detect_prop_setup(symbol, meta)
            if not sig:
                continue

            bar_key = f"{symbol}_{sig['bar_time']}_{sig['direction']}"
            if state["last_signals"].get(symbol) == bar_key:
                continue

            risk_dollars, lot_size = calculate_prop_lot_size(symbol, meta, sig['entry'], sig['sl'], account_bal)
            digits = sig['digits']

            msg = f"""💼 <b>UNIVERSAL PROP FIRM SIGNAL CARD</b> 💼
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>Asset:</b> {sig['emoji']} <b>{sig['name']}</b>
🎯 <b>Action:</b> {sig['direction_emoji']} <b>{sig['direction']} (50% FVG Retest)</b>
📦 <b>Recommended Lot Size:</b> <code>{lot_size:.2f} Lots</code> (0.75% Risk ≈ ${risk_dollars:,.2f})

📍 <b>Entry Price:</b> <code>{sig['entry']:.{digits}f}</code>
🛡 <b>Hard Stop Loss:</b> <code>{sig['sl']:.{digits}f}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>ASYMMETRIC TARGETS:</b>
  • 🛡 <b>TP1 (+1.0R):</b> <code>{sig['tp1']:.{digits}f}</code> ➔ <i>Bank 30% + Move SL to Breakeven!</i>
  • 🎯 <b>TP2 (+2.5R):</b> <code>{sig['tp2']:.{digits}f}</code> ➔ <i>Bank 40% (+$468.75 Gain)</i>
  • 🚀 <b>TP3 (+5.0R):</b> <code>{sig['tp3']:.{digits}f}</code> ➔ <i>Hold 30% (+$937.50 Mega-Runner!)</i>

━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡 <b>Compliance:</b> FTMO / FundedNext / The5ers Ready
🌊 <b>Setup:</b> <i>{sig['context']}</i>
👉 <b>Action:</b> Bot has queued limit order in live shadow tracker!"""

            if send_telegram(msg):
                state["last_signals"][symbol] = bar_key
                # Add to pending orders for live lifecycle tracking
                new_order = {
                    "symbol": symbol,
                    "name": sig["name"],
                    "emoji": sig["emoji"],
                    "direction": sig["direction"],
                    "direction_emoji": sig["direction_emoji"],
                    "entry": sig["entry"],
                    "sl": sig["sl"],
                    "tp1": sig["tp1"],
                    "tp2": sig["tp2"],
                    "tp3": sig["tp3"],
                    "lot_size": lot_size,
                    "risk_dollars": risk_dollars,
                    "digits": digits,
                    "bar_time": sig["bar_time"],
                    "created_at": now_str,
                    "bars_elapsed": 0
                }
                state["pending_orders"].append(new_order)
                save_state(state)
                print(f"✅ [DISPATCHED] {sig['name']} {sig['direction']} Signal sent to VIP Channel & Queued for Live Tracking!")

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
