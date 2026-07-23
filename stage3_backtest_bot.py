"""
===============================================================================
TRADING BOT - STAGE 3: MULTI-FILTER CONFIRMATION & 90-DAY BACKTESTING ENGINE
===============================================================================
Goal: Combine Stage 1 & 2 with a 5-Filter Confirmation Ruleset, 
      Multi-Timeframe Trend Alignment (1D, 4H, 1H), a 90-Day Backtesting Engine,
      Performance Metrics (Win-Rate, Profit Factor, Max Drawdown, Expectancy),
      and Account Equity Curve plotting.

Target Audience: Non-coders (every section is heavily documented in plain English).
Safety Mode: READ-ONLY / HISTORICAL BACKTEST (Zero financial risk).
===============================================================================
"""

import sys
import os

# Fix encoding for Windows console output
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
from datetime import datetime, timedelta

# =============================================================================
# STEP 1: CONFIGURATION & INITIAL PARAMETERS
# =============================================================================
TICKER_SYMBOL = "EURUSD=X" # Asset to backtest (Forex EUR/USD or "BTC-USD")
INITIAL_BALANCE = 10000.0   # Initial Account Capital ($10,000 Demo)
RISK_PERCENT = 0.02         # 2% Risk per trade ($200 per initial trade)
RISK_REWARD_RATIO = 2.0     # 1:2 Risk-to-Reward ratio

# Timezone Configurations
LONDON_TZ = pytz.timezone("Europe/London")
LOCAL_TZ = pytz.timezone("Asia/Bangkok")

IS_FOREX = "USD=X" in TICKER_SYMBOL or "=X" in TICKER_SYMBOL
PIP_SIZE = 0.0001 if IS_FOREX else 1.0

# Minimum Volatility Filter Threshold (in Pips)
MIN_ATR_PIPS = 10.0 if IS_FOREX else 50.0

print("=" * 75)
print(f"[START] INITIALIZING STAGE 3 BACKTESTING ENGINE FOR: {TICKER_SYMBOL}")
print(f"• Starting Balance : ${INITIAL_BALANCE:,.2f}")
print(f"• Risk Per Trade   : {RISK_PERCENT * 100:.1f}%")
print(f"• Risk-Reward      : 1:{RISK_REWARD_RATIO:.1f}")
print("=" * 75)


# =============================================================================
# STEP 2: MULTI-TIMEFRAME DATA FEED ENGINE (1D, 4H, 1H)
# =============================================================================
print("[FETCH] Downloading 90 days of multi-timeframe market data (1D, 4H, 1H)...")

# Download 1-Hour candles (Primary entry timeframe - 90 days)
df_1h = yf.download(tickers=TICKER_SYMBOL, period="90d", interval="1h", progress=False)

if df_1h.empty:
    raise ValueError(f"[ERROR] Could not fetch 1H data for ticker '{TICKER_SYMBOL}'. Check internet connection.")

# Download Daily (1D) and 4-Hour (4H) data for trend alignment
df_1d = yf.download(tickers=TICKER_SYMBOL, period="1y", interval="1d", progress=False)
df_4h = yf.download(tickers=TICKER_SYMBOL, period="90d", interval="1h", progress=False) # Resampled to 4H

# Clean columns
for df_item in [df_1h, df_1d, df_4h]:
    if isinstance(df_item.columns, pd.MultiIndex):
        df_item.columns = df_item.columns.get_level_values(0)

# Resample 1H to 4H candles properly
df_4h_resampled = df_4h.resample('4h').agg({
    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
}).dropna()

# Standardize Timezones to London Time
for df_item in [df_1h, df_1d, df_4h_resampled]:
    if df_item.index.tzinfo is None:
        df_item.index = df_item.index.tz_localize('UTC')
    else:
        df_item.index = df_item.index.tz_convert('UTC')
    df_item['London_Time'] = df_item.index.tz_convert(LONDON_TZ)

# Calculate 200-EMA across all 3 timeframes
df_1h['EMA_200'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
df_4h_resampled['EMA_200'] = df_4h_resampled['Close'].ewm(span=200, adjust=False).mean()
df_1d['EMA_200'] = df_1d['Close'].ewm(span=200, adjust=False).mean()

# Calculate 14-ATR & 20-Volume SMA on 1H timeframe
high_low = df_1h['High'] - df_1h['Low']
high_close_prev = (df_1h['High'] - df_1h['Close'].shift(1)).abs()
low_close_prev = (df_1h['Low'] - df_1h['Close'].shift(1)).abs()
df_1h['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
df_1h['ATR_14'] = df_1h['True_Range'].ewm(span=14, adjust=False).mean()
df_1h['Volume_Avg_20'] = df_1h['Volume'].rolling(window=20).mean()

print(f"[OK] Multi-Timeframe Data Loaded: {len(df_1h)} 1-Hour candles ready for backtest!")


# =============================================================================
# STEP 3: MULTI-FILTER CONFIRMATION ENGINE (ALL 5 MUST PASS)
# =============================================================================
print("[ENGINE] Evaluating 5-Filter Confirmation Rules & MTF Alignment...")

def check_london_session(dt):
    # Filter 4: London Session (8 AM to 12 PM London time)
    return 8 <= dt.hour < 12 or (dt.hour == 12 and dt.minute == 0)

# Simulated High-Impact News Events schedule (Filter 5)
# In live trading, this checks a news API calendar. For backtesting, we simulate news blackout windows.
def is_news_event(dt):
    # Example: Skip trading during major news releases at 08:30 or 10:00 AM on Wednesdays/Fridays
    if dt.weekday() in [2, 4] and dt.hour in [8, 10] and dt.minute < 15:
        return True
    return False

# Engulfing Candlestick Detection
df_1h['is_bullish_engulfing'] = (
    (df_1h['Close'] > df_1h['Open']) & 
    (df_1h['Close'] > df_1h['High'].shift(1)) & 
    (df_1h['Open'] < df_1h['Close'].shift(1))
)

df_1h['is_bearish_engulfing'] = (
    (df_1h['Close'] < df_1h['Open']) & 
    (df_1h['Close'] < df_1h['Low'].shift(1)) & 
    (df_1h['Open'] > df_1h['Close'].shift(1))
)


# =============================================================================
# STEP 4: 90-DAY HISTORICAL BACKTEST SIMULATOR
# =============================================================================
print("[SIMULATION] Running historical trade simulation over the last 90 days...")

current_balance = INITIAL_BALANCE
equity_curve = [INITIAL_BALANCE]
equity_timestamps = [df_1h['London_Time'].iloc[0]]

trades_history = []
in_position = False
active_trade_data = None

# Iterate through each 1-hour candle
for i in range(200, len(df_1h)):
    row = df_1h.iloc[i]
    candle_time = row['London_Time']
    
    # -------------------------------------------------------------------------
    # PART A: MANAGE ACTIVE POSITION (CHECK EXIT / TRAILING STOP)
    # -------------------------------------------------------------------------
    if in_position and active_trade_data:
        t_type = active_trade_data['type']
        entry_p = active_trade_data['entry_price']
        sl_p = active_trade_data['sl_price']
        tp_p = active_trade_data['tp_price']
        risk_dollar = active_trade_data['risk_dollar']
        sl_dist = active_trade_data['sl_distance']
        
        # Check Trailing Stop rules
        if t_type == "BUY":
            # Milestone 1: Reached 1:1 R/R -> Move SL to Breakeven
            if row['High'] >= entry_p + sl_dist and active_trade_data['trailing_stage'] < 1:
                active_trade_data['sl_price'] = entry_p
                active_trade_data['trailing_stage'] = 1
                
            # Milestone 2: Reached 1.5:1 R/R -> Lock 50% Profit
            if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade_data['trailing_stage'] < 2:
                active_trade_data['sl_price'] = entry_p + (0.75 * sl_dist)
                active_trade_data['trailing_stage'] = 2

            # Check Take-Profit Hit
            if row['High'] >= tp_p:
                profit = risk_dollar * RISK_REWARD_RATIO
                current_balance += profit
                trades_history.append({
                    'entry_time': active_trade_data['entry_time'],
                    'exit_time': candle_time,
                    'type': 'BUY',
                    'entry_price': entry_p,
                    'exit_price': tp_p,
                    'pnl': profit,
                    'result': 'WIN',
                    'balance': current_balance
                })
                in_position = False
                active_trade_data = None
                
            # Check Stop-Loss Hit
            elif row['Low'] <= active_trade_data['sl_price']:
                # Calculate PnL based on current SL level (could be breakeven or profit lock)
                pnl = ((active_trade_data['sl_price'] - entry_p) / sl_dist) * risk_dollar
                current_balance += pnl
                res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                trades_history.append({
                    'entry_time': active_trade_data['entry_time'],
                    'exit_time': candle_time,
                    'type': 'BUY',
                    'entry_price': entry_p,
                    'exit_price': active_trade_data['sl_price'],
                    'pnl': pnl,
                    'result': res,
                    'balance': current_balance
                })
                in_position = False
                active_trade_data = None

        elif t_type == "SELL":
            # Milestone 1: Reached 1:1 R/R -> Move SL to Breakeven
            if row['Low'] <= entry_p - sl_dist and active_trade_data['trailing_stage'] < 1:
                active_trade_data['sl_price'] = entry_p
                active_trade_data['trailing_stage'] = 1

            # Milestone 2: Reached 1.5:1 R/R -> Lock 50% Profit
            if row['Low'] <= entry_p - (1.5 * sl_dist) and active_trade_data['trailing_stage'] < 2:
                active_trade_data['sl_price'] = entry_p - (0.75 * sl_dist)
                active_trade_data['trailing_stage'] = 2

            # Check Take-Profit Hit
            if row['Low'] <= tp_p:
                profit = risk_dollar * RISK_REWARD_RATIO
                current_balance += profit
                trades_history.append({
                    'entry_time': active_trade_data['entry_time'],
                    'exit_time': candle_time,
                    'type': 'SELL',
                    'entry_price': entry_p,
                    'exit_price': tp_p,
                    'pnl': profit,
                    'result': 'WIN',
                    'balance': current_balance
                })
                in_position = False
                active_trade_data = None

            # Check Stop-Loss Hit
            elif row['High'] >= active_trade_data['sl_price']:
                pnl = ((entry_p - active_trade_data['sl_price']) / sl_dist) * risk_dollar
                current_balance += pnl
                res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                trades_history.append({
                    'entry_time': active_trade_data['entry_time'],
                    'exit_time': candle_time,
                    'type': 'SELL',
                    'entry_price': entry_p,
                    'exit_price': active_trade_data['sl_price'],
                    'pnl': pnl,
                    'result': res,
                    'balance': current_balance
                })
                in_position = False
                active_trade_data = None

    # Track equity curve
    equity_curve.append(current_balance)
    equity_timestamps.append(candle_time)
    
    # -------------------------------------------------------------------------
    # PART B: EVALUATE NEW ENTRY SIGNALS (IF NOT ALREADY IN A TRADE)
    # -------------------------------------------------------------------------
    if not in_position:
        # Check 5 Filters:
        # Filter 1: 1H Trend (Price vs 200-EMA)
        f1_buy_trend = row['Close'] > row['EMA_200']
        f1_sell_trend = row['Close'] < row['EMA_200']
        
        # Filter 2: Volatility (14-ATR > MIN_ATR_PIPS)
        f2_volatility = (row['ATR_14'] / PIP_SIZE) >= MIN_ATR_PIPS
        
        # Filter 3: Volume (Volume > 20-period Volume SMA)
        f3_volume = row['Volume'] >= row['Volume_Avg_20'] if not pd.isna(row['Volume_Avg_20']) else True
        
        # Filter 4: Time (London Session 8 AM - 12 PM)
        f4_time = check_london_session(candle_time)
        
        # Filter 5: News (No high-impact news in window)
        f5_news = not is_news_event(candle_time)
        
        # Check Multi-Timeframe (MTF) Alignment
        # Daily Trend (1D)
        d1_match = df_1d[df_1d['London_Time'] <= candle_time]
        d1_bullish = d1_match.iloc[-1]['Close'] > d1_match.iloc[-1]['EMA_200'] if not d1_match.empty else True
        d1_bearish = d1_match.iloc[-1]['Close'] < d1_match.iloc[-1]['EMA_200'] if not d1_match.empty else True

        # 4-Hour Trend (4H)
        h4_match = df_4h_resampled[df_4h_resampled['London_Time'] <= candle_time]
        h4_bullish = h4_match.iloc[-1]['Close'] > h4_match.iloc[-1]['EMA_200'] if not h4_match.empty else True
        h4_bearish = h4_match.iloc[-1]['Close'] < h4_match.iloc[-1]['EMA_200'] if not h4_match.empty else True

        # ALL 5 FILTERS + MTF ALIGNMENT CHECK:
        # BUY ENTRY:
        if f1_buy_trend and f2_volatility and f3_volume and f4_time and f5_news and d1_bullish and h4_bullish and row['is_bullish_engulfing']:
            sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
            risk_dollar = current_balance * RISK_PERCENT
            
            in_position = True
            active_trade_data = {
                'type': 'BUY',
                'entry_time': candle_time,
                'entry_price': row['Close'],
                'sl_price': row['Close'] - sl_dist,
                'tp_price': row['Close'] + (RISK_REWARD_RATIO * sl_dist),
                'sl_distance': sl_dist,
                'risk_dollar': risk_dollar,
                'trailing_stage': 0
            }
            
        # SELL ENTRY:
        elif f1_sell_trend and f2_volatility and f3_volume and f4_time and f5_news and d1_bearish and h4_bearish and row['is_bearish_engulfing']:
            sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
            risk_dollar = current_balance * RISK_PERCENT
            
            in_position = True
            active_trade_data = {
                'type': 'SELL',
                'entry_time': candle_time,
                'entry_price': row['Close'],
                'sl_price': row['Close'] + sl_dist,
                'tp_price': row['Close'] - (RISK_REWARD_RATIO * sl_dist),
                'sl_distance': sl_dist,
                'risk_dollar': risk_dollar,
                'trailing_stage': 0
            }


# =============================================================================
# STEP 5: CALCULATE PERFORMANCE METRICS
# =============================================================================
print("[METRICS] Computing Backtest Performance Metrics...")

df_trades = pd.DataFrame(trades_history)

total_trades = len(df_trades)
if total_trades > 0:
    wins = df_trades[df_trades['result'] == 'WIN']
    losses = df_trades[df_trades['result'] == 'LOSS']
    breakevens = df_trades[df_trades['result'] == 'BREAKEVEN']

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100
    loss_rate = (loss_count / total_trades) * 100

    gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
    gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 0.0
    net_profit = current_balance - INITIAL_BALANCE
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    # Maximum Drawdown Calculation
    eq_series = pd.Series(equity_curve)
    running_max = eq_series.cummax()
    drawdown = (eq_series - running_max) / running_max
    max_drawdown_pct = abs(drawdown.min()) * 100

    expectancy = net_profit / total_trades
else:
    win_count = loss_count = 0
    win_rate = loss_rate = 0.0
    gross_profit = gross_loss = net_profit = profit_factor = max_drawdown_pct = expectancy = 0.0

# Print Performance Table to Console
print("\n" + "=" * 75)
print("📊 90-DAY BACKTEST PERFORMANCE DASHBOARD")
print("=" * 75)
print(f"• Ticker Symbol           : {TICKER_SYMBOL}")
print(f"• Backtest Period         : Last 90 Days")
print(f"• Initial Balance         : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Account Balance   : ${current_balance:,.2f}")
print(f"• Total Net Profit        : ${net_profit:,.2f} ({(net_profit/INITIAL_BALANCE)*100:+.2f}%)")
print("-" * 75)
print(f"• Total Trades Taken      : {total_trades}")
print(f"• Winning Trades          : {win_count} ({win_rate:.1f}%)")
print(f"• Losing Trades           : {loss_count} ({loss_rate:.1f}%)")
print(f"• Gross Profit            : ${gross_profit:,.2f}")
print(f"• Gross Loss              : ${gross_loss:,.2f}")
print(f"• Profit Factor           : {profit_factor:.2f}")
print(f"• Maximum Drawdown        : {max_drawdown_pct:.2f}%")
print(f"• Expectancy per Trade    : ${expectancy:,.2f}")
print("=" * 75 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (EQUITY CURVE & BACKTEST CHART)
# =============================================================================
print("[PLOTS] Generating Equity Curve & Backtest Trade Markers Charts...")

# 1. EQUITY CURVE PLOT
fig1, ax_eq = plt.subplots(figsize=(12, 6))
ax_eq.plot(equity_timestamps, equity_curve, color='#2E7D32', linewidth=2.0, label='Account Equity ($)')
ax_eq.axhline(INITIAL_BALANCE, color='#757575', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax_eq.fill_between(equity_timestamps, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#C8E6C9', alpha=0.4)
ax_eq.fill_between(equity_timestamps, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax_eq.set_title(f"90-Day Account Equity Curve ({TICKER_SYMBOL})", fontsize=14, fontweight='bold')
ax_eq.set_ylabel("Account Balance (USD)", fontsize=12)
ax_eq.set_xlabel("Date", fontsize=12)
ax_eq.grid(True, linestyle=':', alpha=0.6)
ax_eq.legend(loc='upper left', frameon=True)
plt.tight_layout()

eq_chart_name = "stage3_equity_curve.png"
plt.savefig(eq_chart_name, dpi=150)
print(f"[SAVE] Equity Curve chart saved to: {os.path.abspath(eq_chart_name)}")

# 2. BACKTEST TRADES SUMMARY CHART
fig2, ax_bt = plt.subplots(figsize=(14, 7))
plot_df = df_1h.tail(200)
ax_bt.plot(plot_df['London_Time'], plot_df['Close'], label='Price', color='#1976D2', linewidth=1.5)
ax_bt.plot(plot_df['London_Time'], plot_df['EMA_200'], label='200-EMA', color='#FF6D00', linestyle='--', linewidth=1.8)

# Mark Wins and Losses on Price Chart
if not df_trades.empty:
    win_trades = df_trades[df_trades['result'] == 'WIN']
    loss_trades = df_trades[df_trades['result'] == 'LOSS']

    if not win_trades.empty:
        ax_bt.scatter(win_trades['entry_time'], win_trades['entry_price'], color='#00E676', marker='^', s=100, label='WIN Trade', zorder=5)
    if not loss_trades.empty:
        ax_bt.scatter(loss_trades['entry_time'], loss_trades['entry_price'], color='#FF1744', marker='v', s=100, label='LOSS Trade', zorder=5)

ax_bt.set_title(f"{TICKER_SYMBOL} Backtest Trade Markers (Last 200 Candles)", fontsize=14, fontweight='bold')
ax_bt.set_ylabel("Price", fontsize=12)
ax_bt.set_xlabel("Date & Time (London Time)", fontsize=12)
ax_bt.grid(True, linestyle=':', alpha=0.6)
ax_bt.legend(loc='upper left', frameon=True)
plt.tight_layout()

bt_chart_name = "stage3_backtest_chart.png"
plt.savefig(bt_chart_name, dpi=150)
print(f"[SAVE] Backtest Summary chart saved to: {os.path.abspath(bt_chart_name)}")

print("[COMPLETE] Stage 3 Multi-Filter Confirmation & Backtesting finished successfully!")
