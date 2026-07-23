"""
===============================================================================
PLAN B AUTOMATED TELEGRAM PHONE SIGNAL SCANNER
===============================================================================
Scans live EUR/USD, GBP/USD, and USD/JPY market feeds and automatically
transmits live Plan B Trade Alert Cards to Kai's Telegram app!

Configuration:
  - Telegram Bot Token : 8805795541:AAGtovTXglTg22QjEV875FbVzXHvNOWI5Zc
  - Chat ID            : 5477873575 (Kai)
  - Account Capital    : $200.00
  - Risk / Reward      : -$4.00 Risk (2%) / +$10.00 Reward (5%)
===============================================================================
"""

import sys
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import json
import urllib.request
import urllib.parse
import numpy as np
import pandas as pd
import yfinance as yf
import pytz

BOT_TOKEN = "8805795541:AAGtovTXglTg22QjEV875FbVzXHvNOWI5Zc"
CHAT_ID = "5477873575"
INITIAL_BALANCE = 200.0
RISK_PERCENT = 0.02

ADX_MAX = 30.0
RSI_BUY_MAX = 30.0
RSI_SELL_MIN = 70.0
LOOKBACK_BARS = 72

WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip_size": 0.0001, "sl_pips": 15},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip_size": 0.01,   "sl_pips": 15},
]

LONDON_TZ = pytz.timezone("Europe/London")
LOG_FILE = "sent_telegram_signals.json"

print("=" * 90)
print("🚀 PLAN B AUTOMATED TELEGRAM PHONE SIGNAL SCANNER")
print("=" * 90)
print(f"• User / Chat ID   : Kai ({CHAT_ID})")
print(f"• Account Balance  : ${INITIAL_BALANCE:,.2f}")
print(f"• Risk / Reward    : -$4.00 Risk (2%) | +$10.00 Reward (5% - 1:2.5 R/R)")
print(f"• Watchlist        : {', '.join([item['name'] for item in WATCHLIST])}")
print("=" * 90)

def send_telegram_alert(message_text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message_text}
    data = urllib.parse.urlencode(params).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=data)
        res = urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")
        return False

def fetch_live_data(asset_info):
    symbol = asset_info['symbol']
    df = yf.download(tickers=symbol, period="30d", interval="1h", progress=False)
    if df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    df['London_Time'] = df.index.tz_convert(LONDON_TZ)

    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=14, adjust=False).mean()
    avg_loss = loss.ewm(span=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    high_low = df['High'] - df['Low']
    high_close_prev = (df['High'] - df['Close'].shift(1)).abs()
    low_close_prev = (df['Low'] - df['Close'].shift(1)).abs()
    df['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    df['ATR_14'] = df['True_Range'].ewm(span=14, adjust=False).mean()

    high_diff = df['High'] - df['High'].shift(1)
    low_diff = df['Low'].shift(1) - df['Low']
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    atr_series = df['True_Range'].ewm(span=14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df['ADX_14'] = dx.ewm(span=14, adjust=False).mean()

    df['High_3D'] = df['High'].shift(1).rolling(window=LOOKBACK_BARS).max()
    df['Low_3D'] = df['Low'].shift(1).rolling(window=LOOKBACK_BARS).min()

    return df

print("\n[SCANNER] Checking Live Market Data for Active Signals...")

# Load sent signals history to prevent duplicate alerts for same candle
sent_signals = {}
if os.path.exists(LOG_FILE):
    try:
        with open(LOG_FILE, "r") as f:
            sent_signals = json.load(f)
    except Exception:
        sent_signals = {}

signals_found = 0

for asset_info in WATCHLIST:
    sym = asset_info['symbol']
    df = fetch_live_data(asset_info)
    
    if df is None or len(df) < 200:
        continue

    latest_bar = df.iloc[-1]
    current_time = latest_bar['London_Time']
    hour = current_time.hour
    time_key = str(current_time)

    # Session Window Filter: London (8-12) & NY (13-17)
    in_session = (8 <= hour < 12) or (13 <= hour < 17)
    
    adx_val = latest_bar['ADX_14']
    rsi_val = latest_bar['RSI_14']
    ema_val = latest_bar['EMA_200']
    h3 = latest_bar['High_3D']
    l3 = latest_bar['Low_3D']
    close_p = latest_bar['Close']
    low_p = latest_bar['Low']
    high_p = latest_bar['High']

    if pd.isna(adx_val) or pd.isna(rsi_val) or pd.isna(ema_val) or pd.isna(h3) or pd.isna(l3):
        continue

    pip_sz = asset_info['pip_size']
    sl_pips = asset_info['sl_pips']

    buy_signal = (close_p > ema_val) and (low_p <= l3) and (rsi_val < RSI_BUY_MAX) and (adx_val < ADX_MAX) and in_session
    sell_signal = (close_p < ema_val) and (high_p >= h3) and (rsi_val > RSI_SELL_MIN) and (adx_val < ADX_MAX) and in_session

    signal_id = f"{sym}_{time_key}"

    if buy_signal and signal_id not in sent_signals:
        sl_price = l3 - (sl_pips * pip_sz)
        sl_dist = abs(close_p - sl_price)
        if sl_dist < (5 * pip_sz):
            sl_dist = 5 * pip_sz
            sl_price = close_p - sl_dist

        tp1_price = close_p + (1.0 * sl_dist)
        tp2_price = close_p + (2.5 * sl_dist)

        risk_usd = INITIAL_BALANCE * RISK_PERCENT
        reward_usd = risk_usd * 2.5

        card_msg = f"""
=========================================
🏆 PLAN B LIVE SIGNAL ALERT 🏆
=========================================
• Asset Pair      : {asset_info['name']} ({asset_info['symbol']}) [1-Hour Chart]
• Action Signal   : 🟢 BUY (LONG)
• Signal Time     : {time_key} London Time
-----------------------------------------
• Suggested Entry : {close_p:.4f}
• Stop-Loss (SL)  : {sl_price:.4f}  --> Risk: -${risk_usd:.2f} (2.0%)
• Take-Profit 1   : {tp1_price:.4f}  --> TP1 (50% exit + SL to Breakeven)
• Take-Profit 2   : {tp2_price:.4f}  --> TP2 (50% exit for +${reward_usd:.2f} win)
=========================================
👉 Action: Open your Exness / MT5 Demo app & place this order!
=========================================
"""
        print(card_msg)
        if send_telegram_alert(card_msg):
            sent_signals[signal_id] = True
            signals_found += 1

    elif sell_signal and signal_id not in sent_signals:
        sl_price = h3 + (sl_pips * pip_sz)
        sl_dist = abs(sl_price - close_p)
        if sl_dist < (5 * pip_sz):
            sl_dist = 5 * pip_sz
            sl_price = close_p + sl_dist

        tp1_price = close_p - (1.0 * sl_dist)
        tp2_price = close_p - (2.5 * sl_dist)

        risk_usd = INITIAL_BALANCE * RISK_PERCENT
        reward_usd = risk_usd * 2.5

        card_msg = f"""
=========================================
🏆 PLAN B LIVE SIGNAL ALERT 🏆
=========================================
• Asset Pair      : {asset_info['name']} ({asset_info['symbol']}) [1-Hour Chart]
• Action Signal   : 🔴 SELL (SHORT)
• Signal Time     : {time_key} London Time
-----------------------------------------
• Suggested Entry : {close_p:.4f}
• Stop-Loss (SL)  : {sl_price:.4f}  --> Risk: -${risk_usd:.2f} (2.0%)
• Take-Profit 1   : {tp1_price:.4f}  --> TP1 (50% exit + SL to Breakeven)
• Take-Profit 2   : {tp2_price:.4f}  --> TP2 (50% exit for +${reward_usd:.2f} win)
=========================================
👉 Action: Open your Exness / MT5 Demo app & place this order!
=========================================
"""
        print(card_msg)
        if send_telegram_alert(card_msg):
            sent_signals[signal_id] = True
            signals_found += 1

with open(LOG_FILE, "w") as f:
    json.dump(sent_signals, f, indent=2)

print("-" * 90)
if signals_found == 0:
    print("ℹ️ SCANNER STATUS: Market scanned successfully. 0 signals active right now.")
    print("👉 All Plan B rules are protecting your $200 account!")
else:
    print(f"🎉 SCANNER STATUS: Found {signals_found} signal(s) & sent to your Telegram app!")

print("=" * 90 + "\n")
