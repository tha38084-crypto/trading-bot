"""
===============================================================================
TRADING BOT - STAGE 3 OPTIMIZER: MULTI-VARIATION COMPARISON ENGINE
===============================================================================
Goal: Backtest and compare 5 strategy variations over 90 days of market data
      to find the optimal combination of Time, Touch Tolerance, Volume, and ATR filters.

Variations Tested:
- Variation A: Loosen Time Filter (6 AM - 4 PM London)
- Variation B: Loosen Trendline Touch (10 pips tolerance)
- Variation C: Remove Volume Filter entirely
- Variation D: Lower ATR Volatility Threshold (5.0 pips)
- Variation E: Combined Optimization (All 4 improvements combined)

Target Audience: Non-coders (every section is heavily commented in plain English).
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
# STEP 1: CONFIGURATION & INITIAL SETUP
# =============================================================================
TICKER_SYMBOL = "EURUSD=X"
INITIAL_BALANCE = 10000.0   # $10,000 Starting Account
RISK_PERCENT = 0.02         # 2% Risk per trade ($200 per trade)
RISK_REWARD_RATIO = 2.0     # 1:2 Risk-Reward ratio

LONDON_TZ = pytz.timezone("Europe/London")
IS_FOREX = "USD=X" in TICKER_SYMBOL or "=X" in TICKER_SYMBOL
PIP_SIZE = 0.0001 if IS_FOREX else 1.0

print("=" * 80)
print(f"[START] MULTI-VARIATION STRATEGY OPTIMIZER FOR: {TICKER_SYMBOL}")
print("=" * 80)

# =============================================================================
# STEP 2: LOAD 90-DAY MARKET DATA (1D, 4H, 1H)
# =============================================================================
print("[FETCH] Downloading 90 days of multi-timeframe candle data from Yahoo Finance...")

df_1h = yf.download(tickers=TICKER_SYMBOL, period="90d", interval="1h", progress=False)
df_1d = yf.download(tickers=TICKER_SYMBOL, period="1y", interval="1d", progress=False)
df_4h = yf.download(tickers=TICKER_SYMBOL, period="90d", interval="1h", progress=False)

if df_1h.empty:
    raise ValueError(f"[ERROR] Could not fetch 1H data for symbol '{TICKER_SYMBOL}'.")

# Clean MultiIndex columns
for df_item in [df_1h, df_1d, df_4h]:
    if isinstance(df_item.columns, pd.MultiIndex):
        df_item.columns = df_item.columns.get_level_values(0)

# Resample 4H candles
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

# Calculate 14-ATR & 20-Volume SMA on 1H timeframe
high_low = df_1h['High'] - df_1h['Low']
high_close_prev = (df_1h['High'] - df_1h['Close'].shift(1)).abs()
low_close_prev = (df_1h['Low'] - df_1h['Close'].shift(1)).abs()
df_1h['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
df_1h['ATR_14'] = df_1h['True_Range'].ewm(span=14, adjust=False).mean()
df_1h['Volume_Avg_20'] = df_1h['Volume'].rolling(window=20).mean()

# Detect Engulfing Patterns
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

# Detect Swing Points & Trendlines
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

# Construct Trendline Series
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

print("[OK] Data preparation & indicator calculations complete!")


# =============================================================================
# STEP 3: REUSABLE BACKTEST ENGINE FUNCTION
# =============================================================================
def run_backtest_simulation(var_name, start_hour, end_hour, touch_pips, use_volume, min_atr_pips):
    """
    Executes a 90-day backtest simulation for a specific strategy variation config.
    """
    current_balance = INITIAL_BALANCE
    equity_curve = [INITIAL_BALANCE]
    equity_times = [df_1h['London_Time'].iloc[0]]
    
    trades = []
    in_position = False
    active_trade = None
    
    tolerance = touch_pips * PIP_SIZE
    
    for i in range(200, len(df_1h)):
        row = df_1h.iloc[i]
        prev_row = df_1h.iloc[i - 1]
        candle_time = row['London_Time']
        
        # ---------------------------------------------------------------------
        # MANAGE OPEN POSITION
        # ---------------------------------------------------------------------
        if in_position and active_trade:
            t_type = active_trade['type']
            entry_p = active_trade['entry_price']
            risk_dollar = active_trade['risk_dollar']
            sl_dist = active_trade['sl_distance']
            tp_p = active_trade['tp_price']
            
            if t_type == "BUY":
                # Trailing stop adjustments
                if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                    active_trade['sl_price'] = entry_p
                    active_trade['trailing_stage'] = 1
                if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                    active_trade['sl_price'] = entry_p + (0.75 * sl_dist)
                    active_trade['trailing_stage'] = 2
                    
                if row['High'] >= tp_p: # TP Hit
                    pnl = risk_dollar * RISK_REWARD_RATIO
                    current_balance += pnl
                    trades.append({'result': 'WIN', 'pnl': pnl})
                    in_position = False
                    active_trade = None
                elif row['Low'] <= active_trade['sl_price']: # SL Hit
                    pnl = ((active_trade['sl_price'] - entry_p) / sl_dist) * risk_dollar
                    current_balance += pnl
                    res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                    trades.append({'result': res, 'pnl': pnl})
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
                    trades.append({'result': 'WIN', 'pnl': pnl})
                    in_position = False
                    active_trade = None
                elif row['High'] >= active_trade['sl_price']:
                    pnl = ((entry_p - active_trade['sl_price']) / sl_dist) * risk_dollar
                    current_balance += pnl
                    res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                    trades.append({'result': res, 'pnl': pnl})
                    in_position = False
                    active_trade = None
                    
        equity_curve.append(current_balance)
        equity_times.append(candle_time)
        
        # ---------------------------------------------------------------------
        # CHECK ENTRY CONDITIONS FOR NEW TRADE
        # ---------------------------------------------------------------------
        if not in_position:
            # Time Filter
            in_time_window = (start_hour <= candle_time.hour < end_hour) or (candle_time.hour == end_hour and candle_time.minute == 0)
            if not in_time_window:
                continue
                
            # Trend Filter (1H 200-EMA)
            buy_trend = row['Close'] > row['EMA_200']
            sell_trend = row['Close'] < row['EMA_200']
            
            # Volatility Filter
            atr_ok = (row['ATR_14'] / PIP_SIZE) >= min_atr_pips
            
            # Volume Filter
            vol_ok = (row['Volume'] >= row['Volume_Avg_20']) if use_volume and not pd.isna(row['Volume_Avg_20']) else True
            
            # MTF Alignment (1D, 4H)
            d1_match = df_1d[df_1d['London_Time'] <= candle_time]
            d1_bull = d1_match.iloc[-1]['Close'] > d1_match.iloc[-1]['EMA_200'] if not d1_match.empty else True
            d1_bear = d1_match.iloc[-1]['Close'] < d1_match.iloc[-1]['EMA_200'] if not d1_match.empty else True
            
            h4_match = df_4h_resampled[df_4h_resampled['London_Time'] <= candle_time]
            h4_bull = h4_match.iloc[-1]['Close'] > h4_match.iloc[-1]['EMA_200'] if not h4_match.empty else True
            h4_bear = h4_match.iloc[-1]['Close'] < h4_match.iloc[-1]['EMA_200'] if not h4_match.empty else True

            # Pullback Trendline Touch check
            trend_val = row['Trendline']
            touch_buy = True if pd.isna(trend_val) else (abs(row['Low'] - trend_val) <= tolerance or abs(prev_row['Low'] - trend_val) <= tolerance)
            touch_sell = True if pd.isna(trend_val) else (abs(row['High'] - trend_val) <= tolerance or abs(prev_row['High'] - trend_val) <= tolerance)

            # BUY Trigger
            if buy_trend and atr_ok and vol_ok and d1_bull and h4_bull and touch_buy and row['is_bullish_engulfing']:
                sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
                risk_dollar = current_balance * RISK_PERCENT
                in_position = True
                active_trade = {
                    'type': 'BUY',
                    'entry_price': row['Close'],
                    'sl_price': row['Close'] - sl_dist,
                    'tp_price': row['Close'] + (RISK_REWARD_RATIO * sl_dist),
                    'sl_distance': sl_dist,
                    'risk_dollar': risk_dollar,
                    'trailing_stage': 0
                }
            # SELL Trigger
            elif sell_trend and atr_ok and vol_ok and d1_bear and h4_bear and touch_sell and row['is_bearish_engulfing']:
                sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
                risk_dollar = current_balance * RISK_PERCENT
                in_position = True
                active_trade = {
                    'type': 'SELL',
                    'entry_price': row['Close'],
                    'sl_price': row['Close'] + sl_dist,
                    'tp_price': row['Close'] - (RISK_REWARD_RATIO * sl_dist),
                    'sl_distance': sl_dist,
                    'risk_dollar': risk_dollar,
                    'trailing_stage': 0
                }

    # Calculate metrics
    df_tr = pd.DataFrame(trades)
    total_trades = len(df_tr)
    if total_trades > 0:
        wins = df_tr[df_tr['result'] == 'WIN']
        losses = df_tr[df_tr['result'] == 'LOSS']
        win_rate = (len(wins) / total_trades) * 100
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
        win_rate = gross_profit = gross_loss = net_profit = profit_factor = max_dd_pct = expectancy = 0.0
        
    return {
        'var_name': var_name,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'net_profit': net_profit,
        'max_dd_pct': max_dd_pct,
        'expectancy': expectancy,
        'final_balance': current_balance,
        'equity_curve': equity_curve,
        'equity_times': equity_times
    }


# =============================================================================
# STEP 4: RUN ALL 5 VARIATIONS SEQUENTIALLY
# =============================================================================
print("[RUNNER] Executing Backtests for All 5 Strategy Variations...")

variations_configs = [
    {"name": "Baseline (Stage 3)", "start_h": 8, "end_h": 12, "touch": 5, "vol": True, "atr": 10.0},
    {"name": "Variation A (6 AM-4 PM Time)", "start_h": 6, "end_h": 16, "touch": 5, "vol": True, "atr": 10.0},
    {"name": "Variation B (10 Pip Touch)", "start_h": 8, "end_h": 12, "touch": 10, "vol": True, "atr": 10.0},
    {"name": "Variation C (No Volume Filter)", "start_h": 8, "end_h": 12, "touch": 5, "vol": False, "atr": 10.0},
    {"name": "Variation D (5 Pip ATR Threshold)", "start_h": 8, "end_h": 12, "touch": 5, "vol": True, "atr": 5.0},
    {"name": "Variation E (Combined All Changes)", "start_h": 6, "end_h": 16, "touch": 10, "vol": False, "atr": 5.0},
]

results = []
for config in variations_configs:
    res = run_backtest_simulation(
        var_name=config["name"],
        start_hour=config["start_h"],
        end_hour=config["end_h"],
        touch_pips=config["touch"],
        use_volume=config["vol"],
        min_atr_pips=config["atr"]
    )
    results.append(res)


# =============================================================================
# STEP 5: COMPARISON TABLE DASHBOARD OUTPUT
# =============================================================================
print("\n" + "=" * 95)
print("📊 90-DAY STRATEGY OPTIMIZATION COMPARISON TABLE")
print("=" * 95)
print(f"{'Variation Name':<35} | {'Trades':<7} | {'Win %':<7} | {'Profit Factor':<13} | {'Net Profit ($)':<14} | {'Max DD %':<8} | {'Expectancy ($)':<12}")
print("-" * 95)

best_res = results[0]

for r in results:
    if r['net_profit'] > best_res['net_profit']:
        best_res = r
    print(f"{r['var_name']:<35} | {r['total_trades']:<7} | {r['win_rate']:<6.1f}% | {r['profit_factor']:<13.2f} | ${r['net_profit']:<13.2f} | {r['max_dd_pct']:<7.2f}% | ${r['expectancy']:<11.2f}")

print("=" * 95 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (EQUITY CURVES OVERLAY CHART)
# =============================================================================
print("[PLOTS] Generating Multi-Variation Equity Curve Overlay Chart...")

fig, ax = plt.subplots(figsize=(14, 8))

colors = ['#757575', '#1E88E5', '#D81B60', '#FB8C00', '#8E24AA', '#43A047']

for idx, r in enumerate(results):
    ax.plot(r['equity_times'], r['equity_curve'], label=f"{r['var_name']} (${r['net_profit']:+,.2f})", color=colors[idx], linewidth=2.0 if r == best_res else 1.2)

ax.axhline(INITIAL_BALANCE, color='#333333', linestyle='--', linewidth=1.2, label=f"Starting Capital (${INITIAL_BALANCE:,.0f})")
ax.set_title("90-Day Strategy Optimization - Equity Curve Comparison", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_name = "stage3_optimization_comparison.png"
plt.savefig(chart_name, dpi=150)
print(f"[SAVE] Multi-Variation comparison chart saved to: {os.path.abspath(chart_name)}")

print("\n" + "=" * 80)
print("🏆 OPTIMAL STRATEGY RECOMMENDATION")
print("=" * 80)
print(f"• BEST PERFORMING VARIATION : {best_res['var_name']}")
print(f"• Total Net Profit          : ${best_res['net_profit']:+,.2f}")
print(f"• Profit Factor             : {best_res['profit_factor']:.2f}")
print(f"• Win Rate                  : {best_res['win_rate']:.1f}% ({best_res['total_trades']} Trades)")
print(f"• Max Drawdown              : {best_res['max_dd_pct']:.2f}%")
print(f"• Expectancy per Trade      : ${best_res['expectancy']:+,.2f}")
print("=" * 80 + "\n")

print("✨ Multi-Variation Optimization execution completed successfully!")
