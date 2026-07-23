"""
===============================================================================
TRADING BOT - STAGE 2: ENTRY & EXIT LOGIC
===============================================================================
Goal: Combine Stage 1 Data Engine with automated Trendline Detection, 
      Pullback Identification, Engulfing Candlestick Confirmation, 
      Dynamic SL/TP Exits, Trailing Stop Rules, and 2% Risk Position Sizing.

Target Audience: Non-coders (every section is heavily commented in plain English).
Safety Mode: READ-ONLY / DEMO MODE (Zero financial risk - paper trading simulator).
===============================================================================
"""

import sys
import os

# Fix encoding for Windows Terminal console output
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz
from datetime import datetime

# =============================================================================
# STEP 1: CONFIGURATION & PARAMETERS
# =============================================================================
# Ticker symbol (e.g., "EURUSD=X" for Forex EUR/USD, "BTC-USD" for Bitcoin)
TICKER_SYMBOL = "EURUSD=X"

# Candle timeframe ('15m' = 15-minute candles)
TIMEFRAME = "15m"
PERIOD = "5d"

# Demo Account Balance & Risk Settings
ACCOUNT_BALANCE = 10000.0  # $10,000 Demo Account
RISK_PERCENT = 0.02         # 2% Risk Per Trade ($200)

# Timezone Configurations
LONDON_TZ = pytz.timezone("Europe/London")
LOCAL_TZ = pytz.timezone("Asia/Bangkok")  # Change to your local timezone if desired

# Pip Definition based on asset type
# For Forex (EUR/USD), 1 pip = 0.0001. For Crypto (BTC-USD), 1 point/pip = $1.00
IS_FOREX = "USD=X" in TICKER_SYMBOL or "=X" in TICKER_SYMBOL
PIP_SIZE = 0.0001 if IS_FOREX else 1.0

print("=" * 70)
print(f"[START] INITIALIZING STAGE 2 ENTRY & EXIT ENGINE FOR: {TICKER_SYMBOL}")
print(f"• Account Balance : ${ACCOUNT_BALANCE:,.2f}")
print(f"• Risk Per Trade  : {RISK_PERCENT * 100:.1f}% (${ACCOUNT_BALANCE * RISK_PERCENT:,.2f})")
print("=" * 70)


# =============================================================================
# STEP 2: DATA ENGINE & INDICATOR CALCULATIONS (FROM STAGE 1)
# =============================================================================
print(f"[FETCH] Downloading last {PERIOD} of {TIMEFRAME} market data...")
df = yf.download(tickers=TICKER_SYMBOL, period=PERIOD, interval=TIMEFRAME, progress=False)

if df.empty:
    raise ValueError(f"[ERROR] Could not fetch market data for '{TICKER_SYMBOL}'. Check internet connection or symbol.")

# Flatten MultiIndex columns if returned by yfinance
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Localize timestamps to London Time
if df.index.tzinfo is None:
    df.index = df.index.tz_localize('UTC')
else:
    df.index = df.index.tz_convert('UTC')

df['London_Time'] = df.index.tz_convert(LONDON_TZ)

# Calculate Core Indicators
# 1. 200-EMA Trend Filter
df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

# 2. 14-ATR Volatility Filter
high_low = df['High'] - df['Low']
high_close_prev = (df['High'] - df['Close'].shift(1)).abs()
low_close_prev = (df['Low'] - df['Close'].shift(1)).abs()
df['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
df['ATR_14'] = df['True_Range'].ewm(span=14, adjust=False).mean()

# 3. 20-Period Volume Average
df['Volume_Avg_20'] = df['Volume'].rolling(window=20).mean()

# 4. London Session Filter (8:00 AM - 12:00 PM London Time)
def is_london_session(dt):
    hour = dt.hour
    minute = dt.minute
    return 8 <= hour < 12 or (hour == 12 and minute == 0)

df['Is_London_Session'] = df['London_Time'].apply(is_london_session)


# =============================================================================
# STEP 3: SWING POINT & TRENDLINE DETECTION (PURE NUMPY)
# =============================================================================
print("[ANALYSIS] Detecting Swing Highs, Swing Lows, and Fitting Trendlines...")

# Identify local swing highs and swing lows using a 3-candle window
window = 2
df['is_swing_low'] = False
df['is_swing_high'] = False

for i in range(window, len(df) - window):
    lows = df['Low'].iloc[i - window : i + window + 1]
    highs = df['High'].iloc[i - window : i + window + 1]
    
    if df['Low'].iloc[i] == lows.min():
        df.iloc[i, df.columns.get_loc('is_swing_low')] = True
        
    if df['High'].iloc[i] == highs.max():
        df.iloc[i, df.columns.get_loc('is_swing_high')] = True

# Extract swing low points for Uptrend trendline
swing_lows = df[df['is_swing_low']].copy()
swing_highs = df[df['is_swing_high']].copy()

trendline_series = pd.Series(index=df.index, dtype=float)
trendline_type = "NONE"

if len(swing_lows) >= 3:
    recent_lows = swing_lows.tail(3)
    x_indices = np.array([df.index.get_loc(idx) for idx in recent_lows.index])
    y_values = recent_lows['Low'].values
    
    # Check if swing lows are making higher lows (UPTREND)
    if y_values[0] < y_values[1] < y_values[2]:
        slope, intercept = np.polyfit(x_indices, y_values, 1)
        if slope > 0: # Upward sloping trendline
            trendline_type = "UPTREND"
            full_x = np.arange(len(df))
            trendline_series = pd.Series(slope * full_x + intercept, index=df.index)

# Fallback: Fit a Downtrend Line connecting 3 lower swing highs if Uptrend not active
if trendline_type == "NONE" and len(swing_highs) >= 3:
    recent_highs = swing_highs.tail(3)
    x_indices = np.array([df.index.get_loc(idx) for idx in recent_highs.index])
    y_values = recent_highs['High'].values
    
    if y_values[0] > y_values[1] > y_values[2]:
        slope, intercept = np.polyfit(x_indices, y_values, 1)
        if slope < 0: # Downward sloping trendline
            trendline_type = "DOWNTREND"
            full_x = np.arange(len(df))
            trendline_series = pd.Series(slope * full_x + intercept, index=df.index)

df['Trendline'] = trendline_series


# =============================================================================
# STEP 4: PULLBACK & ENGULFING CANDLESTICK SIGNAL DETECTION
# =============================================================================
print("[SIGNAL] Scanning for Pullback Touches & Engulfing Confirmation Signals...")

# Bullish Engulfing Pattern: Current candle close > open, close > prev high, body engulfs prev body
df['is_bullish_engulfing'] = (
    (df['Close'] > df['Open']) & 
    (df['Close'] > df['High'].shift(1)) & 
    (df['Open'] < df['Close'].shift(1))
)

# Bearish Engulfing Pattern: Current candle close < open, close < prev low, body engulfs prev body
df['is_bearish_engulfing'] = (
    (df['Close'] < df['Open']) & 
    (df['Close'] < df['Low'].shift(1)) & 
    (df['Open'] > df['Close'].shift(1))
)

# Distance to trendline tolerance: 5 pips (or 0.5 * ATR)
tolerance = 5 * PIP_SIZE

df['signal'] = 0  # 0 = Hold, 1 = BUY Signal, -1 = SELL Signal

signals = []
for i in range(1, len(df)):
    row = df.iloc[i]
    prev_row = df.iloc[i - 1]
    
    # Must be in London Trading Session (8 AM - 12 PM London time)
    if not row['Is_London_Session']:
        continue
        
    trendline_val = row['Trendline']
    if pd.isna(trendline_val):
        continue
        
    # Check Pullback Touch
    touch_buy = abs(row['Low'] - trendline_val) <= tolerance or abs(prev_row['Low'] - trendline_val) <= tolerance
    touch_sell = abs(row['High'] - trendline_val) <= tolerance or abs(prev_row['High'] - trendline_val) <= tolerance
    
    # 1. BUY SIGNAL CONDITION:
    if row['Close'] > row['EMA_200'] and touch_buy and row['is_bullish_engulfing']:
        df.iloc[i, df.columns.get_loc('signal')] = 1
        signals.append((i, "BUY", row))
        
    # 2. SELL SIGNAL CONDITION:
    elif row['Close'] < row['EMA_200'] and touch_sell and row['is_bearish_engulfing']:
        df.iloc[i, df.columns.get_loc('signal')] = -1
        signals.append((i, "SELL", row))


# =============================================================================
# STEP 5: RISK MANAGEMENT & POSITION SIZING (SL, TP, TRAILING STOPS)
# =============================================================================
print("[RISK] Calculating Position Sizes & Exit Targets...")

active_trade = None

if len(signals) > 0:
    sig_idx, sig_type, sig_row = signals[-1]
    entry_price = float(sig_row['Close'])
    atr_val = float(sig_row['ATR_14'])
    
    if sig_type == "BUY":
        sl_distance = max(1.5 * atr_val, 10 * PIP_SIZE)
        sl_price = entry_price - sl_distance
        tp_price = entry_price + (2.0 * sl_distance) # 1:2 Risk-Reward
        
        breakeven_target = entry_price + (1.0 * sl_distance)
        lock50_target = entry_price + (1.5 * sl_distance)
        
    else: # SELL
        sl_distance = max(1.5 * atr_val, 10 * PIP_SIZE)
        sl_price = entry_price + sl_distance
        tp_price = entry_price - (2.0 * sl_distance) # 1:2 Risk-Reward
        
        breakeven_target = entry_price - (1.0 * sl_distance)
        lock50_target = entry_price - (1.5 * sl_distance)
        
    risk_amount = ACCOUNT_BALANCE * RISK_PERCENT
    position_units = risk_amount / sl_distance
    
    standard_lots = position_units / 100000.0 if IS_FOREX else position_units
    micro_lots = position_units / 1000.0 if IS_FOREX else position_units

    active_trade = {
        "type": sig_type,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_distance_pips": sl_distance / PIP_SIZE,
        "risk_amount": risk_amount,
        "position_units": position_units,
        "standard_lots": standard_lots,
        "micro_lots": micro_lots,
        "breakeven_target": breakeven_target,
        "lock50_target": lock50_target,
        "timestamp": sig_row['London_Time']
    }
else:
    # If no active signal triggered on recent history, demonstrate with current candle state
    latest = df.iloc[-1]
    entry_price = float(latest['Close'])
    atr_val = float(latest['ATR_14'])
    sl_distance = max(1.5 * atr_val, 10 * PIP_SIZE)
    sl_price = entry_price - sl_distance
    tp_price = entry_price + (2.0 * sl_distance)
    risk_amount = ACCOUNT_BALANCE * RISK_PERCENT
    position_units = risk_amount / sl_distance
    
    active_trade = {
        "type": "DEMO SCENARIO (WATCHLIST)",
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_distance_pips": sl_distance / PIP_SIZE,
        "risk_amount": risk_amount,
        "position_units": position_units,
        "standard_lots": position_units / 100000.0 if IS_FOREX else position_units,
        "micro_lots": position_units / 1000.0 if IS_FOREX else position_units,
        "breakeven_target": entry_price + (1.0 * sl_distance),
        "lock50_target": entry_price + (1.5 * sl_distance),
        "timestamp": latest['London_Time']
    }


# =============================================================================
# STEP 6: CONSOLE DASHBOARD SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("📌 STAGE 2 ENTRY, EXIT & RISK MANAGEMENT SUMMARY")
print("=" * 70)
print(f"• Asset Ticker       : {TICKER_SYMBOL}")
print(f"• Active Signal      : {active_trade['type']}")
print(f"• Entry Price        : ${active_trade['entry_price']:,.4f}")
print(f"• Stop-Loss (SL)     : ${active_trade['sl_price']:,.4f} ({active_trade['sl_distance_pips']:.1f} pips)")
print(f"• Take-Profit (TP)   : ${active_trade['tp_price']:,.4f} (1:2 Risk-Reward)")
print(f"• Account Risk (2%)  : ${active_trade['risk_amount']:,.2f}")
if IS_FOREX:
    print(f"• Position Size      : {active_trade['position_units']:,.0f} units ({active_trade['micro_lots']:.2f} Micro Lots / {active_trade['standard_lots']:.4f} Standard Lots)")
else:
    print(f"• Position Size      : {active_trade['position_units']:.4f} units")
print(f"• Trailing SL Step 1 : Move to Breakeven at ${active_trade['breakeven_target']:,.4f} (1:1 R)")
print(f"• Trailing SL Step 2 : Lock 50% Profit at ${active_trade['lock50_target']:,.4f} (1.5:1 R)")
print("=" * 70 + "\n")


# =============================================================================
# STEP 7: VISUAL CHART GENERATION
# =============================================================================
print("[CHART] Generating Stage 2 Visual Chart with Trendline, Signals & SL/TP Lines...")

plot_df = df.tail(120).copy()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)

# 1. Price & 200-EMA
ax1.plot(plot_df['London_Time'], plot_df['Close'], label='Close Price', color='#1E88E5', linewidth=1.5)
ax1.plot(plot_df['London_Time'], plot_df['EMA_200'], label='200-EMA (Trend Filter)', color='#FF6D00', linewidth=2.0, linestyle='--')

# 2. Trendline (BLUE)
if 'Trendline' in plot_df.columns and not plot_df['Trendline'].isna().all():
    ax1.plot(plot_df['London_Time'], plot_df['Trendline'], label=f'Trendline ({trendline_type})', color='#29B6F6', linewidth=2.2, linestyle='-')

# 3. Highlight London Session Shading
for i in range(len(plot_df) - 1):
    t_start = plot_df['London_Time'].iloc[i]
    t_end = plot_df['London_Time'].iloc[i + 1]
    is_london = plot_df['Is_London_Session'].iloc[i]
    bg_color = '#C8E6C9' if is_london else '#FFCDD2'
    ax1.axvspan(t_start, t_end, color=bg_color, alpha=0.3)
    ax2.axvspan(t_start, t_end, color=bg_color, alpha=0.3)

# 4. Mark Entry Signals
buy_signals = plot_df[plot_df['signal'] == 1]
sell_signals = plot_df[plot_df['signal'] == -1]

if len(buy_signals) > 0:
    ax1.scatter(buy_signals['London_Time'], buy_signals['Low'] * 0.999, color='#00E676', marker='^', s=120, zorder=5, label='BUY Signal (Bullish Engulfing)')

if len(sell_signals) > 0:
    ax1.scatter(sell_signals['London_Time'], sell_signals['High'] * 1.001, color='#FF1744', marker='v', s=120, zorder=5, label='SELL Signal (Bearish Engulfing)')

# 5. Draw Horizontal Exit Lines (Entry = Blue, SL = Red, TP = Green)
ax1.axhline(active_trade['entry_price'], color='#2980B9', linestyle='--', linewidth=1.8, label=f"Entry: ${active_trade['entry_price']:,.4f}")
ax1.axhline(active_trade['sl_price'], color='#E74C3C', linestyle=':', linewidth=2.0, label=f"Stop-Loss: ${active_trade['sl_price']:,.4f}")
ax1.axhline(active_trade['tp_price'], color='#2ECC71', linestyle=':', linewidth=2.0, label=f"Take-Profit: ${active_trade['tp_price']:,.4f}")

# Information Box on Chart
info_box_text = (
    f"Signal: {active_trade['type']}\n"
    f"Entry: ${active_trade['entry_price']:,.4f}\n"
    f"Stop-Loss: ${active_trade['sl_price']:,.4f}\n"
    f"Take-Profit: ${active_trade['tp_price']:,.4f}\n"
    f"Risk: ${active_trade['risk_amount']:,.2f} (2%)\n"
    f"Pos Size: {active_trade['position_units']:,.0f} units"
)
ax1.text(0.98, 0.05, info_box_text, transform=ax1.transAxes, fontsize=10,
         verticalalignment='bottom', horizontalalignment='right',
         bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFFFFF', edgecolor='#333333', alpha=0.9))

ax1.set_title(f"{TICKER_SYMBOL} - Stage 2 Entry & Exit Signals", fontsize=14, fontweight='bold')
ax1.set_ylabel("Price", fontsize=12)
ax1.grid(True, linestyle=':', alpha=0.6)
ax1.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

# Panel 2: Volume Chart
colors = ['#4CAF50' if v >= a else '#E53935' for v, a in zip(plot_df['Volume'], plot_df['Volume_Avg_20'])]
ax2.bar(plot_df['London_Time'], plot_df['Volume'], color=colors, alpha=0.7, width=0.008, label='Volume')
ax2.plot(plot_df['London_Time'], plot_df['Volume_Avg_20'], color='#7C4DFF', linewidth=1.5, label='20-Period Vol Avg')
ax2.set_ylabel("Volume", fontsize=12)
ax2.set_xlabel("Time (London Time Zone)", fontsize=12)
ax2.grid(True, linestyle=':', alpha=0.6)
ax2.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M', tz=LONDON_TZ))
plt.xticks(rotation=30)
plt.tight_layout()

# Save Chart Image
chart_filename = "stage2_chart.png"
plt.savefig(chart_filename, dpi=150)
print(f"[SAVE] Stage 2 visual chart saved to: {os.path.abspath(chart_filename)}")

print("[COMPLETE] Stage 2 Entry & Exit Logic execution completed successfully!")
