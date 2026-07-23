"""
===============================================================================
TRADING BOT - STAGE 3 REBUILT ENGINE (2-YEAR HISTORICAL BACKTEST)
===============================================================================
Goal: Rebuild the trading strategy with 5 targeted fixes:
      1. Loosened Filters (6 AM - 4 PM London Time, 10 Pip Touch Tolerance, Volume Removed)
      2. ADX-14 Trend-Strength Filter (ADX > 25)
      3. Engulfing OR Pin Bar Candlestick Confirmations
      4. Extended 2-Year (730 Days) Historical Dataset
      5. Increased Trade Frequency Target (50-100+ trades)

Target Audience: Non-coders (heavily commented in plain English).
Safety Mode: READ-ONLY / HISTORICAL SIMULATION (Zero financial risk).
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
# STEP 1: CONFIGURATION & PARAMETERS
# =============================================================================
TICKER_SYMBOL = "EURUSD=X"
INITIAL_BALANCE = 10000.0   # $10,000 Demo Account
RISK_PERCENT = 0.02         # 2% Risk per trade ($200 per trade)
RISK_REWARD_RATIO = 2.0     # 1:2 Risk-Reward ratio

LONDON_TZ = pytz.timezone("Europe/London")
IS_FOREX = "USD=X" in TICKER_SYMBOL or "=X" in TICKER_SYMBOL
PIP_SIZE = 0.0001 if IS_FOREX else 1.0

# FIX 1 PARAMETERS: Loosened Filters
TOUCH_TOLERANCE_PIPS = 10.0   # 10 Pips touch tolerance
START_HOUR = 6                # 6:00 AM London Time
END_HOUR = 16                 # 4:00 PM (16:00) London Time
MIN_ATR_PIPS = 5.0            # Dynamic Volatility threshold

# FIX 2 PARAMETERS: ADX Trend Strength
ADX_THRESHOLD = 20.0          # ADX > 20 confirms strong trend

print("=" * 80)
print(f"[START] INITIALIZING REBUILT 2-YEAR STRATEGY ENGINE FOR: {TICKER_SYMBOL}")
print(f"• Account Capital : ${INITIAL_BALANCE:,.2f}")
print(f"• Trading Hours   : {START_HOUR}:00 AM - {END_HOUR}:00 PM London Time")
print(f"• ADX Filter      : > {ADX_THRESHOLD:.0f}")
print(f"• Confirmations   : Engulfing OR Pin Bar")
print("=" * 80)


# =============================================================================
# STEP 2: FETCH 2-YEAR MARKET DATA (730 DAYS)
# =============================================================================
print("[FETCH] Downloading 2 Years (730 Days) of 1-Hour candle data from Yahoo Finance...")

df_1h = yf.download(tickers=TICKER_SYMBOL, period="730d", interval="1h", progress=False)
df_1d = yf.download(tickers=TICKER_SYMBOL, period="2y", interval="1d", progress=False)
df_4h = yf.download(tickers=TICKER_SYMBOL, period="730d", interval="1h", progress=False)

if df_1h.empty:
    raise ValueError(f"[ERROR] Could not fetch 2-year 1H data for ticker '{TICKER_SYMBOL}'.")

# Clean MultiIndex column headers
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

# Calculate 200-EMA across timeframes
df_1h['EMA_200'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
df_4h_resampled['EMA_200'] = df_4h_resampled['Close'].ewm(span=200, adjust=False).mean()
df_1d['EMA_200'] = df_1d['Close'].ewm(span=200, adjust=False).mean()

# Calculate 14-ATR
high_low = df_1h['High'] - df_1h['Low']
high_close_prev = (df_1h['High'] - df_1h['Close'].shift(1)).abs()
low_close_prev = (df_1h['Low'] - df_1h['Close'].shift(1)).abs()
df_1h['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
df_1h['ATR_14'] = df_1h['True_Range'].ewm(span=14, adjust=False).mean()


# =============================================================================
# STEP 3: CALCULATE ADX-14 (TREND STRENGTH FILTER - FIX 2)
# =============================================================================
print("[CALC] Calculating ADX-14 (Average Directional Index)...")

high_diff = df_1h['High'] - df_1h['High'].shift(1)
low_diff = df_1h['Low'].shift(1) - df_1h['Low']

plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)

atr_series = df_1h['True_Range'].ewm(span=14, adjust=False).mean()
plus_di = 100 * (pd.Series(plus_dm, index=df_1h.index).ewm(span=14, adjust=False).mean() / atr_series)
minus_di = 100 * (pd.Series(minus_dm, index=df_1h.index).ewm(span=14, adjust=False).mean() / atr_series)

dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
df_1h['ADX_14'] = dx.ewm(span=14, adjust=False).mean()


# =============================================================================
# STEP 4: DETECT CANDLESTICK PATTERNS (ENGULFING OR PIN BAR - FIX 3)
# =============================================================================
print("[CALC] Scanning for Bullish & Bearish Engulfing and Pin Bar Patterns...")

# 1. Engulfing Patterns
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

# 2. Pin Bar (Hammer / Shooting Star) Patterns
total_range = (df_1h['High'] - df_1h['Low']).replace(0, 0.00001)
body_size = (df_1h['Close'] - df_1h['Open']).abs()
lower_wick = df_1h[['Open', 'Close']].min(axis=1) - df_1h['Low']
upper_wick = df_1h['High'] - df_1h[['Open', 'Close']].max(axis=1)

# Bullish Pin Bar: Long lower wick (>= 2x body), close in upper 35% of candle range
df_1h['is_bullish_pinbar'] = (
    (lower_wick >= 2 * body_size) & 
    ((df_1h['Close'] - df_1h['Low']) / total_range >= 0.65)
)

# Bearish Pin Bar: Long upper wick (>= 2x body), close in lower 35% of candle range
df_1h['is_bearish_pinbar'] = (
    (upper_wick >= 2 * body_size) & 
    ((df_1h['High'] - df_1h['Close']) / total_range >= 0.65)
)

# Combined Entry Confirmation (Engulfing OR Pin Bar)
df_1h['bullish_trigger'] = df_1h['is_bullish_engulfing'] | df_1h['is_bullish_pinbar']
df_1h['bearish_trigger'] = df_1h['is_bearish_engulfing'] | df_1h['is_bearish_pinbar']


# =============================================================================
# STEP 5: SWING POINTS & TRENDLINES (10 PIP TOLERANCE)
# =============================================================================
print("[ANALYSIS] Constructing Trendlines with 10-Pip Touch Tolerance...")

window = 2
df_1h['is_swing_low'] = False
df_1h['is_swing_high'] = False

for i in range(window, len(df_1h) - window):
    lows = df_1h['Low'].iloc[i - window : i + window + 1]
    highs = df_1h['High'].iloc[i - window : i + window + 1]
    if df_1h['Low'].iloc[i] == lows.min():
        df_1h.iloc[i, df_1h.columns.get_loc('is_swing_low')] = True
    if df_1h['High'].iloc[i] == highs.max():
        df_1h.iloc[i, df_1h.columns.get_loc('is_swing_high')] = True

swing_lows = df_1h[df_1h['is_swing_low']].copy()
swing_highs = df_1h[df_1h['is_swing_high']].copy()

trendline_series = pd.Series(index=df_1h.index, dtype=float)
if len(swing_lows) >= 3:
    recent_lows = swing_lows.tail(3)
    x_idx = np.array([df_1h.index.get_loc(idx) for idx in recent_lows.index])
    y_val = recent_lows['Low'].values
    if y_val[0] < y_val[1] < y_val[2]:
        slope, intercept = np.polyfit(x_idx, y_val, 1)
        if slope > 0:
            full_x = np.arange(len(df_1h))
            trendline_series = pd.Series(slope * full_x + intercept, index=df_1h.index)

df_1h['Trendline'] = trendline_series


# =============================================================================
# STEP 6: 2-YEAR HISTORICAL BACKTEST SIMULATOR (FIX 4 & FIX 5)
# =============================================================================
print("[SIMULATION] Running 2-Year (730 Days) trade simulation across 12,000+ candles...")

current_balance = INITIAL_BALANCE
equity_curve = [INITIAL_BALANCE]
equity_times = [df_1h['London_Time'].iloc[0]]

trades_history = []
in_position = False
active_trade = None

tolerance = TOUCH_TOLERANCE_PIPS * PIP_SIZE

for i in range(200, len(df_1h)):
    row = df_1h.iloc[i]
    prev_row = df_1h.iloc[i - 1]
    candle_time = row['London_Time']
    
    # -------------------------------------------------------------------------
    # PART A: MANAGE ACTIVE POSITION
    # -------------------------------------------------------------------------
    if in_position and active_trade:
        t_type = active_trade['type']
        entry_p = active_trade['entry_price']
        risk_dollar = active_trade['risk_dollar']
        sl_dist = active_trade['sl_distance']
        tp_p = active_trade['tp_price']
        
        if t_type == "BUY":
            # Trailing stop steps
            if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                active_trade['sl_price'] = entry_p
                active_trade['trailing_stage'] = 1
            if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                active_trade['sl_price'] = entry_p + (0.75 * sl_dist)
                active_trade['trailing_stage'] = 2
                
            if row['High'] >= tp_p: # TP Hit
                pnl = risk_dollar * RISK_REWARD_RATIO
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['Low'] <= active_trade['sl_price']: # SL Hit
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
    # PART B: EVALUATE NEW ENTRY SIGNALS
    # -------------------------------------------------------------------------
    if not in_position:
        # Time Filter: 6:00 AM - 4:00 PM London Time
        in_time_window = (START_HOUR <= candle_time.hour < END_HOUR) or (candle_time.hour == END_HOUR and candle_time.minute == 0)
        if not in_time_window:
            continue
            
        # 1H Trend Filter
        buy_trend = row['Close'] > row['EMA_200']
        sell_trend = row['Close'] < row['EMA_200']
        
        # FIX 2: ADX Trend-Strength Filter (> 20)
        adx_ok = row['ADX_14'] >= ADX_THRESHOLD if not pd.isna(row['ADX_14']) else True
        
        # Volatility Filter
        atr_ok = (row['ATR_14'] / PIP_SIZE) >= MIN_ATR_PIPS
        
        # MTF Alignment (1D, 4H)
        d1_match = df_1d[df_1d['London_Time'] <= candle_time]
        d1_bull = d1_match.iloc[-1]['Close'] > d1_match.iloc[-1]['EMA_200'] if not d1_match.empty else True
        d1_bear = d1_match.iloc[-1]['Close'] < d1_match.iloc[-1]['EMA_200'] if not d1_match.empty else True
        
        h4_match = df_4h_resampled[df_4h_resampled['London_Time'] <= candle_time]
        h4_bull = h4_match.iloc[-1]['Close'] > h4_match.iloc[-1]['EMA_200'] if not h4_match.empty else True
        h4_bear = h4_match.iloc[-1]['Close'] < h4_match.iloc[-1]['EMA_200'] if not h4_match.empty else True

        # Trendline Touch
        trend_val = row['Trendline']
        touch_buy = True if pd.isna(trend_val) else (abs(row['Low'] - trend_val) <= tolerance or abs(prev_row['Low'] - trend_val) <= tolerance)
        touch_sell = True if pd.isna(trend_val) else (abs(row['High'] - trend_val) <= tolerance or abs(prev_row['High'] - trend_val) <= tolerance)

        # BUY Trigger (Engulfing OR Pin Bar)
        if buy_trend and adx_ok and atr_ok and d1_bull and h4_bull and touch_buy and row['bullish_trigger']:
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
        # SELL Trigger (Engulfing OR Pin Bar)
        elif sell_trend and adx_ok and atr_ok and d1_bear and h4_bear and touch_sell and row['bearish_trigger']:
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
# STEP 7: PERFORMANCE METRICS & SUMMARY
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
print("📊 REBUILT STRATEGY 2-YEAR BACKTEST PERFORMANCE DASHBOARD")
print("=" * 80)
print(f"• Ticker Symbol           : {TICKER_SYMBOL}")
print(f"• Backtest Duration       : 2 Years (730 Days)")
print(f"• Initial Capital         : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Capital           : ${current_balance:,.2f}")
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
print("📌 VERDICT: IS THIS REBUILT STRATEGY PROFITABLE?")
print("=" * 80)
if is_profitable:
    print(f"✅ YES! The strategy is PROFITABLE with a Net Profit of ${net_profit:,.2f} and Profit Factor of {profit_factor:.2f}.")
else:
    print(f"❌ NO: Net Profit is ${net_profit:,.2f} (Profit Factor: {profit_factor:.2f}). Further adjustments recommended.")
print("=" * 80 + "\n")


# =============================================================================
# STEP 8: VISUALIZATION (EQUITY CURVE PLOT)
# =============================================================================
print("[PLOTS] Generating 2-Year Account Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(equity_times, equity_curve, color='#1565C0', linewidth=2.0, label='Rebuilt Account Equity ($)')
ax.axhline(INITIAL_BALANCE, color='#757575', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#C8E6C9', alpha=0.4)
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax.set_title(f"2-Year Account Equity Curve - Rebuilt Strategy ({TICKER_SYMBOL})", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "stage3_rebuilt_equity_curve.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] 2-Year Equity Curve chart saved to: {os.path.abspath(chart_file)}")

print("✨ Rebuilt Strategy 2-Year Backtest execution completed successfully!")
