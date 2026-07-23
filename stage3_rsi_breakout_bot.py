"""
===============================================================================
TRADING BOT - NEW STRATEGY: 200-EMA + RSI MOMENTUM BREAKOUT ENGINE
===============================================================================
Goal: Test a brand new Breakout Strategy with 6 Confirmation Filters:
      1. Trend Filter: Price vs 200-EMA (Above for BUY, Below for SELL)
      2. Momentum Filter: RSI-14 > 55 for BUY, RSI-14 < 45 for SELL
      3. Donchian Breakout: Close > 5-Day High for BUY, Close < 5-Day Low for SELL
      4. Volume Filter: Volume > 20-period Volume SMA
      5. Trend Strength Filter: ADX-14 > 30 (Strong Trend)
      6. Time Filter: 6:00 AM - 4:00 PM London Time

Target Audience: Non-coders (heavily documented in plain English).
Dataset: 2 Years (730 Days) of 1-Hour market data.
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

# =============================================================================
# STEP 1: CONFIGURATION & INITIAL PARAMETERS
# =============================================================================
TICKER_SYMBOL = "EURUSD=X" # Asset to backtest
INITIAL_BALANCE = 10000.0   # $10,000 Demo Account Balance
RISK_PERCENT = 0.02         # 2% Risk per trade ($200)
RISK_REWARD_RATIO = 2.0     # 1:2 Risk-Reward ratio

# Strategy Thresholds
RSI_BUY_THRESHOLD = 55.0    # RSI > 55 for Bullish Momentum
RSI_SELL_THRESHOLD = 45.0   # RSI < 45 for Bearish Momentum
ADX_THRESHOLD = 25.0        # ADX > 25 for Strong Trend
BREAKOUT_LOOKBACK_HOURS = 120 # 5 Days = 120 1-hour candles

START_HOUR = 6              # 6:00 AM London Time
END_HOUR = 16               # 4:00 PM (16:00) London Time

LONDON_TZ = pytz.timezone("Europe/London")
IS_FOREX = "USD=X" in TICKER_SYMBOL or "=X" in TICKER_SYMBOL
PIP_SIZE = 0.0001 if IS_FOREX else 1.0

print("=" * 80)
print(f"[START] INITIALIZING 200-EMA + RSI BREAKOUT ENGINE FOR: {TICKER_SYMBOL}")
print(f"• Account Capital  : ${INITIAL_BALANCE:,.2f}")
print(f"• Trading Window   : {START_HOUR}:00 AM - {END_HOUR}:00 PM London Time")
print(f"• RSI Thresholds   : Buy > {RSI_BUY_THRESHOLD}, Sell < {RSI_SELL_THRESHOLD}")
print(f"• ADX Threshold    : > {ADX_THRESHOLD}")
print(f"• Breakout Window  : 5-Day High/Low ({BREAKOUT_LOOKBACK_HOURS} candles)")
print("=" * 80)


# =============================================================================
# STEP 2: DOWNLOAD 2-YEAR MARKET DATA (730 DAYS)
# =============================================================================
print("[FETCH] Downloading 2 Years (730 Days) of 1-Hour candle data from Yahoo Finance...")

df = yf.download(tickers=TICKER_SYMBOL, period="730d", interval="1h", progress=False)

if df.empty:
    raise ValueError(f"[ERROR] Could not fetch 2-year 1H data for ticker '{TICKER_SYMBOL}'.")

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Localize Timezone to London Time
if df.index.tzinfo is None:
    df.index = df.index.tz_localize('UTC')
else:
    df.index = df.index.tz_convert('UTC')
df['London_Time'] = df.index.tz_convert(LONDON_TZ)

print(f"[OK] Downloaded {len(df)} 1-Hour candles successfully!")


# =============================================================================
# STEP 3: CALCULATE ALL TECHNICAL INDICATORS
# =============================================================================
print("[CALC] Calculating 200-EMA, RSI-14, ADX-14, 20-Volume SMA, and 5-Day Breakout Levels...")

# 1. 200-Period Exponential Moving Average (200-EMA Trend Filter)
df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

# 2. 14-Period Relative Strength Index (RSI-14 Momentum Filter)
delta = df['Close'].diff()
gain = delta.where(delta > 0, 0.0)
loss = -delta.where(delta < 0, 0.0)
avg_gain = gain.ewm(span=14, adjust=False).mean()
avg_loss = loss.ewm(span=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, 0.00001)
df['RSI_14'] = 100 - (100 / (1 + rs))

# 3. 14-Period Average True Range (14-ATR Volatility)
high_low = df['High'] - df['Low']
high_close_prev = (df['High'] - df['Close'].shift(1)).abs()
low_close_prev = (df['Low'] - df['Close'].shift(1)).abs()
df['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
df['ATR_14'] = df['True_Range'].ewm(span=14, adjust=False).mean()

# 4. 14-Period Average Directional Index (ADX-14 Trend Strength Filter)
high_diff = df['High'] - df['High'].shift(1)
low_diff = df['Low'].shift(1) - df['Low']
plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)

atr_series = df['True_Range'].ewm(span=14, adjust=False).mean()
plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
df['ADX_14'] = dx.ewm(span=14, adjust=False).mean()

# 5. 20-Period Volume Simple Moving Average (Volume Filter)
df['Volume_Avg_20'] = df['Volume'].rolling(window=20).mean()

# 6. 5-Day High & Low Breakout Channels (120 candles lookback)
# Shifted by 1 so we compare current close against previous 5-day extremes
df['High_5D'] = df['High'].shift(1).rolling(window=BREAKOUT_LOOKBACK_HOURS).max()
df['Low_5D'] = df['Low'].shift(1).rolling(window=BREAKOUT_LOOKBACK_HOURS).min()

print("[OK] All indicators calculated successfully!")


# =============================================================================
# STEP 4: 2-YEAR HISTORICAL BACKTEST SIMULATION ENGINE
# =============================================================================
print("[SIMULATION] Running 2-Year trade simulation across 12,000+ candles...")

current_balance = INITIAL_BALANCE
equity_curve = [INITIAL_BALANCE]
equity_times = [df['London_Time'].iloc[0]]

trades_history = []
in_position = False
active_trade = None

for i in range(200, len(df)):
    row = df.iloc[i]
    candle_time = row['London_Time']
    
    # -------------------------------------------------------------------------
    # PART A: MANAGE OPEN POSITION (CHECK EXITS & TRAILING STOPS)
    # -------------------------------------------------------------------------
    if in_position and active_trade:
        t_type = active_trade['type']
        entry_p = active_trade['entry_price']
        risk_dollar = active_trade['risk_dollar']
        sl_dist = active_trade['sl_distance']
        tp_p = active_trade['tp_price']
        
        if t_type == "BUY":
            # Trailing stop milestone 1: Reached 1:1 R/R -> Move SL to Breakeven
            if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                active_trade['sl_price'] = entry_p
                active_trade['trailing_stage'] = 1
            # Trailing stop milestone 2: Reached 1.5:1 R/R -> Lock 50% Profit
            if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                active_trade['sl_price'] = entry_p + (0.75 * sl_dist)
                active_trade['trailing_stage'] = 2
                
            if row['High'] >= tp_p: # Take-Profit Hit
                pnl = risk_dollar * RISK_REWARD_RATIO
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['Low'] <= active_trade['sl_price']: # Stop-Loss Hit
                pnl = ((active_trade['sl_price'] - entry_p) / sl_dist) * risk_dollar
                current_balance += pnl
                res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': active_trade['sl_price'], 'pnl': pnl, 'result': res, 'balance': current_balance})
                in_position = False
                active_trade = None

        elif t_type == "SELL":
            if row['Low'] <= entry_p - sl_dist and active_trade['trailing_stage'] < 1:
                active_trade['sl_price'] = entry_p
                active_trade['trailing_stage'] = 1
            if row['Low'] <= entry_p - (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                active_trade['sl_price'] = entry_p - (0.75 * sl_dist)
                active_trade['trailing_stage'] = 2
                
            if row['Low'] <= tp_p:
                pnl = risk_dollar * RISK_REWARD_RATIO
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'SELL', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['High'] >= active_trade['sl_price']:
                pnl = ((entry_p - active_trade['sl_price']) / sl_dist) * risk_dollar
                current_balance += pnl
                res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'SELL', 'entry_price': entry_p, 'exit_price': active_trade['sl_price'], 'pnl': pnl, 'result': res, 'balance': current_balance})
                in_position = False
                active_trade = None

    equity_curve.append(current_balance)
    equity_times.append(candle_time)

    # -------------------------------------------------------------------------
    # PART B: EVALUATE 6-FILTER BREAKOUT ENTRY CONDITIONS
    # -------------------------------------------------------------------------
    if not in_position:
        # Filter 1: Time Window (6:00 AM - 4:00 PM London Time)
        in_time_window = (START_HOUR <= candle_time.hour < END_HOUR) or (candle_time.hour == END_HOUR and candle_time.minute == 0)
        if not in_time_window:
            continue
            
        # Filter 2: 200-EMA Trend Filter
        f_trend_buy = row['Close'] > row['EMA_200']
        f_trend_sell = row['Close'] < row['EMA_200']
        
        # Filter 3: RSI-14 Momentum Filter
        f_rsi_buy = row['RSI_14'] > RSI_BUY_THRESHOLD
        f_rsi_sell = row['RSI_14'] < RSI_SELL_THRESHOLD
        
        # Filter 4: 5-Day Donchian Breakout Filter
        f_breakout_buy = not pd.isna(row['High_5D']) and row['Close'] > row['High_5D']
        f_breakout_sell = not pd.isna(row['Low_5D']) and row['Close'] < row['Low_5D']
        
        # Filter 5: Volume Filter (Volume > 20-period Volume SMA)
        f_volume = (row['Volume'] >= row['Volume_Avg_20']) if not pd.isna(row['Volume_Avg_20']) else True
        
        # Filter 6: ADX-14 Trend Strength Filter (> 25)
        f_adx = row['ADX_14'] >= ADX_THRESHOLD if not pd.isna(row['ADX_14']) else True

        # BUY ENTRY: ALL 6 FILTERS PASS
        if f_trend_buy and f_rsi_buy and f_breakout_buy and f_volume and f_adx:
            sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
            risk_dollar = current_balance * RISK_PERCENT
            in_position = True
            active_trade = {
                'type': 'BUY',
                'entry_time': candle_time,
                'entry_price': row['Close'],
                'sl_price': row['Close'] - sl_dist,
                'tp_price': row['Close'] + (RISK_REWARD_RATIO * sl_dist),
                'sl_distance': sl_dist,
                'risk_dollar': risk_dollar,
                'trailing_stage': 0
            }
        # SELL ENTRY: ALL 6 FILTERS PASS
        elif f_trend_sell and f_rsi_sell and f_breakout_sell and f_volume and f_adx:
            sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
            risk_dollar = current_balance * RISK_PERCENT
            in_position = True
            active_trade = {
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
# STEP 5: COMPUTE PERFORMANCE METRICS & DASHBOARD
# =============================================================================
print("[METRICS] Computing 2-Year Performance Metrics...")

df_tr = pd.DataFrame(trades_history)
total_trades = len(df_tr)

if total_trades > 0:
    wins = df_tr[df_tr['result'] == 'WIN']
    losses = df_tr[df_tr['result'] == 'LOSS']

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100
    loss_rate = (loss_count / total_trades) * 100

    gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
    gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 0.0
    net_profit = current_balance - INITIAL_BALANCE
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    eq_ser = pd.Series(equity_curve)
    run_max = eq_ser.cummax()
    drawdown = (eq_ser - run_max) / run_max
    max_dd_pct = abs(drawdown.min()) * 100

    expectancy = net_profit / total_trades
else:
    win_count = loss_count = 0
    win_rate = loss_rate = 0.0
    gross_profit = gross_loss = net_profit = profit_factor = max_dd_pct = expectancy = 0.0

is_profitable = net_profit > 0 and profit_factor > 1.0

print("\n" + "=" * 80)
print("📊 200-EMA + RSI MOMENTUM BREAKOUT 2-YEAR PERFORMANCE DASHBOARD")
print("=" * 80)
print(f"• Ticker Symbol           : {TICKER_SYMBOL}")
print(f"• Strategy Type           : 200-EMA + RSI Momentum Breakout")
print(f"• Backtest Period         : 2 Years (730 Days)")
print(f"• Starting Balance        : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Balance           : ${current_balance:,.2f}")
print(f"• Total Net Profit        : ${net_profit:,.2f} ({(net_profit/INITIAL_BALANCE)*100:+.2f}%)")
print("-" * 80)
print(f"• Total Trades Taken      : {total_trades}")
print(f"• Winning Trades          : {win_count} ({win_rate:.1f}%)")
print(f"• Losing Trades           : {loss_count} ({loss_rate:.1f}%)")
print(f"• Gross Profit            : ${gross_profit:,.2f}")
print(f"• Gross Loss              : ${gross_loss:,.2f}")
print(f"• Profit Factor           : {profit_factor:.2f}")
print(f"• Maximum Drawdown        : {max_dd_pct:.2f}%")
print(f"• Expectancy per Trade    : ${expectancy:,.2f}")
print("=" * 80)

print("\n" + "=" * 80)
print("📌 STRATEGY VERDICT: IS THIS NEW BREAKOUT STRATEGY PROFITABLE?")
print("=" * 80)
if is_profitable:
    print(f"✅ YES! The 200-EMA + RSI Momentum Breakout strategy is PROFITABLE!")
    print(f"   Net Profit: ${net_profit:,.2f} | Profit Factor: {profit_factor:.2f} | Win Rate: {win_rate:.1f}%")
else:
    print(f"❌ NO: Net Profit is ${net_profit:,.2f} (Profit Factor: {profit_factor:.2f}). Adjustments required.")
print("=" * 80 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (EQUITY CURVE CHART)
# =============================================================================
print("[PLOTS] Generating 2-Year Account Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(equity_times, equity_curve, color='#00897B', linewidth=2.0, label='RSI Breakout Account Equity ($)')
ax.axhline(INITIAL_BALANCE, color='#757575', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#C8E6C9', alpha=0.4)
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax.set_title(f"2-Year Account Equity Curve - 200-EMA + RSI Breakout Strategy ({TICKER_SYMBOL})", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "stage3_rsi_breakout_equity.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] Equity Curve chart saved to: {os.path.abspath(chart_file)}")

print("✨ 200-EMA + RSI Momentum Breakout Backtest completed successfully!")
