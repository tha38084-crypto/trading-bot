"""
===============================================================================
TRADING BOT - STAGE 1: THE DATA ENGINE
===============================================================================
Goal: Fetch price data, calculate trading indicators, filter London trading hours,
      and display visual & console outputs for demo / paper trading.

Target Audience: Non-coders (every section is documented in plain English).
Safety Mode: READ-ONLY / DEMO MODE (Zero financial risk - no real money involved).
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
# You can change the ticker symbol below to any crypto or stock on Yahoo Finance!
# Examples: "BTC-USD" (Bitcoin), "ETH-USD" (Ethereum), "AAPL" (Apple Stock)
TICKER_SYMBOL = "BTC-USD"

# Timeframe for candle data (e.g., '15m' = 15 minute candles, '5m' = 5 minute candles, '1h' = 1 hour)
TIMEFRAME = "15m"

# How many days of historical data to download
PERIOD = "5d"

# Set target trading timezone (London)
LONDON_TZ = pytz.timezone("Europe/London")

# Set your local timezone (Change this to your local timezone if needed, e.g., 'America/New_York', 'Asia/Bangkok', 'UTC')
LOCAL_TZ = pytz.timezone("Asia/Bangkok") 

print("=" * 60)
print(f"[START] INITIALIZING STAGE 1 DATA ENGINE FOR: {TICKER_SYMBOL}")
print("=" * 60)

# =============================================================================
# STEP 2: FETCH MARKET DATA (DATA FEED)
# =============================================================================
print(f"[FETCH] Downloading last {PERIOD} of {TIMEFRAME} price data from Yahoo Finance...")

# Download historical candle data using yfinance
df = yf.download(tickers=TICKER_SYMBOL, period=PERIOD, interval=TIMEFRAME, progress=False)

# Check if data was returned successfully
if df.empty:
    raise ValueError(f"[ERROR] Could not fetch data for symbol '{TICKER_SYMBOL}'. Please check your internet connection or ticker name.")

# Flatten MultiIndex columns if present (yfinance sometimes returns multi-level column names)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

print(f"[OK] Data fetched successfully! Total candles loaded: {len(df)}")


# =============================================================================
# STEP 3: CALCULATE CORE INDICATORS
# =============================================================================
print("[CALC] Calculating 200-EMA, 14-ATR, and 20-period Volume Average...")

# 1. PRICE DATA (Open, High, Low, Close, Volume)
# Already present in df['Open'], df['High'], df['Low'], df['Close'], df['Volume']

# 2. TREND FILTER: 200-period Exponential Moving Average (200-EMA)
# EMA gives more weight to recent prices, showing overall market trend direction.
df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

# 3. VOLATILITY FILTER: 14-period Average True Range (14-ATR)
# True Range measures market volatility by checking maximum candle spread.
high_low = df['High'] - df['Low']
high_close_prev = (df['High'] - df['Close'].shift(1)).abs()
low_close_prev = (df['Low'] - df['Close'].shift(1)).abs()

# Maximum of the 3 price spread metrics is the True Range (TR)
df['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)

# 14-period exponential average of True Range gives the 14-ATR
df['ATR_14'] = df['True_Range'].ewm(span=14, adjust=False).mean()

# 4. VOLUME FILTER: 20-period Average Volume (20-Volume SMA)
# Simple moving average of volume over the last 20 candles.
df['Volume_Avg_20'] = df['Volume'].rolling(window=20).mean()

print("[OK] Indicators calculated successfully!")


# =============================================================================
# STEP 4: TIME MANAGEMENT & LONDON SESSION FILTER
# =============================================================================
print("[TIME] Processing Timezone Conversions & London Trading Session Filter...")

# Ensure timestamps are localized to UTC first, then converted to London Time
if df.index.tzinfo is None:
    df.index = df.index.tz_localize('UTC')
else:
    df.index = df.index.tz_convert('UTC')

# Create a column for London Local Time
df['London_Time'] = df.index.tz_convert(LONDON_TZ)

# Check if candle falls within London Session (8:00 AM to 12:00 PM London Time)
# London trading hours: 08:00 to 11:59 (includes 8:00 AM up to 12:00 PM cutoff)
def is_london_session(dt):
    # dt is a timezone-aware datetime in London timezone
    hour = dt.hour
    minute = dt.minute
    # 8:00 AM (08:00) to 12:00 PM (12:00)
    if 8 <= hour < 12 or (hour == 12 and minute == 0):
        return True
    return False

df['Is_London_Session'] = df['London_Time'].apply(is_london_session)


# =============================================================================
# STEP 5: CONSOLE DASHBOARD SUMMARY
# =============================================================================
# Fetch latest completed candle
latest_candle = df.iloc[-1]
latest_time_london = latest_candle['London_Time']
latest_time_local = latest_candle['London_Time'].tz_convert(LOCAL_TZ)

current_price = float(latest_candle['Close'])
current_ema_200 = float(latest_candle['EMA_200'])
current_atr = float(latest_candle['ATR_14'])
current_volume = float(latest_candle['Volume'])
avg_volume_20 = float(latest_candle['Volume_Avg_20'])

is_vol_above_avg = current_volume > avg_volume_20
vol_status_text = "ABOVE 20-period Avg [HIGH VOLUME]" if is_vol_above_avg else "BELOW 20-period Avg [LOW VOLUME]"
session_status_text = "ACTIVE (London Trading Hours 8AM-12PM)" if latest_candle['Is_London_Session'] else "INACTIVE (Outside London Hours)"
trend_status_text = "BULLISH (Price above 200-EMA)" if current_price > current_ema_200 else "BEARISH (Price below 200-EMA)"

print("\n" + "=" * 60)
print("📌 LATEST MARKET DATA & ENGINE SUMMARY")
print("=" * 60)
print(f"• Ticker Symbol    : {TICKER_SYMBOL}")
print(f"• Candle Time (London) : {latest_time_london.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"• Candle Time (Local)  : {latest_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"• Current Price    : ${current_price:,.2f}")
print(f"• 200-EMA Trend    : ${current_ema_200:,.2f} -> {trend_status_text}")
print(f"• 14-ATR Volatility: ${current_atr:,.2f}")
print(f"• Current Volume   : {current_volume:,.0f}")
print(f"• 20-Vol Average   : {avg_volume_20:,.0f} -> {vol_status_text}")
print(f"• London Session   : {session_status_text}")
print("=" * 60 + "\n")


# =============================================================================
# STEP 6: VISUAL OUTPUT (CHART GENERATION)
# =============================================================================
print("[CHART] Generating visual chart with session shading and indicators...")

# Filter data to plot (last 150 candles for a clean view)
plot_df = df.tail(150).copy()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)

# --- PANEL 1: PRICE & 200-EMA CHART ---
ax1.plot(plot_df['London_Time'], plot_df['Close'], label='Close Price', color='#1E88E5', linewidth=1.5)
ax1.plot(plot_df['London_Time'], plot_df['EMA_200'], label='200-EMA (Trend Filter)', color='#FF6D00', linewidth=2.0, linestyle='--')
ax1.set_title(f"{TICKER_SYMBOL} Price & Indicators (Stage 1 Data Engine)", fontsize=14, fontweight='bold', pad=12)
ax1.set_ylabel("Price (USD)", fontsize=12)
ax1.grid(True, linestyle=':', alpha=0.6)
ax1.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

# Highlight London Session (8 AM - 12 PM) with Green / Red background shading
for i in range(len(plot_df) - 1):
    t_start = plot_df['London_Time'].iloc[i]
    t_end = plot_df['London_Time'].iloc[i + 1]
    is_london = plot_df['Is_London_Session'].iloc[i]
    
    bg_color = '#C8E6C9' if is_london else '#FFCDD2' # Soft Green (Active) vs Soft Red (Inactive)
    ax1.axvspan(t_start, t_end, color=bg_color, alpha=0.35)
    ax2.axvspan(t_start, t_end, color=bg_color, alpha=0.35)

# Add Information Label Text Box on Chart
info_box_text = (
    f"Current Price: ${current_price:,.2f}\n"
    f"200-EMA: ${current_ema_200:,.2f}\n"
    f"ATR (14): ${current_atr:,.2f}\n"
    f"Volume: {current_volume:,.0f}\n"
    f"20-Vol Avg: {avg_volume_20:,.0f} ({'ABOVE' if is_vol_above_avg else 'BELOW'})"
)
ax1.text(0.98, 0.05, info_box_text, transform=ax1.transAxes, fontsize=10,
         verticalalignment='bottom', horizontalalignment='right',
         bbox=dict(boxstyle='round,pad=0.5', facecolor='#F5F5F5', edgecolor='#BDBDBD', alpha=0.95))

# --- PANEL 2: VOLUME CHART ---
colors = ['#4CAF50' if v >= a else '#E53935' for v, a in zip(plot_df['Volume'], plot_df['Volume_Avg_20'])]
ax2.bar(plot_df['London_Time'], plot_df['Volume'], color=colors, alpha=0.7, width=0.008, label='Volume')
ax2.plot(plot_df['London_Time'], plot_df['Volume_Avg_20'], color='#7C4DFF', linewidth=1.5, label='20-Period Vol Avg')
ax2.set_ylabel("Volume", fontsize=12)
ax2.set_xlabel("Time (London Time Zone - GMT/BST)", fontsize=12)
ax2.grid(True, linestyle=':', alpha=0.6)
ax2.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

# Format X-axis Dates nicely
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M', tz=LONDON_TZ))
plt.xticks(rotation=30)
plt.tight_layout()

# Save the generated chart image
chart_filename = "stage1_chart.png"
plt.savefig(chart_filename, dpi=150)
print(f"[SAVE] Visual chart saved to: {os.path.abspath(chart_filename)}")

print("[COMPLETE] Stage 1 Data Engine execution completed successfully!")
