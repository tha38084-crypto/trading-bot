"""
===============================================================================
TRADING BOT - STAGE 3: MOMENTUM + MEAN-REVERSION HYBRID ENGINE
===============================================================================
Goal: Test a Hybrid Trading Strategy that dynamically routes market regimes:
      1. MOMENTUM MODE (ADX > 30): Trend breakouts, 1:3.0 Risk-Reward
      2. MEAN-REVERSION MODE (ADX < 25): Counter-trend fades, 1:2.0 Risk-Reward

Target Audience: Non-coders (heavily documented in plain English).
Dataset: 2 Years (730 Days) of 1-Hour market data for EUR/USD.
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
TICKER_SYMBOL = "EURUSD=X" # Primary asset
INITIAL_BALANCE = 10000.0   # $10,000 Starting Account
RISK_PERCENT = 0.02         # 2% Risk per trade ($200 per initial trade)

# Mode Specific Parameters
MOMENTUM_ADX_MIN = 30.0     # ADX > 30 triggers Momentum Mode
MOMENTUM_RR = 3.0           # 1:3.0 Risk-Reward for Momentum

REVERSION_ADX_MAX = 25.0    # ADX < 25 triggers Mean-Reversion Mode
REVERSION_RR = 2.0          # 1:2.0 Risk-Reward for Mean-Reversion

START_HOUR = 6              # 6:00 AM London Time
END_HOUR = 16               # 4:00 PM (16:00) London Time
BREAKOUT_LOOKBACK = 120     # 5 Days = 120 1-hour candles

LONDON_TZ = pytz.timezone("Europe/London")
IS_FOREX = "USD=X" in TICKER_SYMBOL or "=X" in TICKER_SYMBOL
PIP_SIZE = 0.0001 if IS_FOREX else 1.0

print("=" * 85)
print(f"[START] INITIALIZING HYBRID MOMENTUM + MEAN-REVERSION ENGINE FOR: {TICKER_SYMBOL}")
print(f"• Account Balance   : ${INITIAL_BALANCE:,.2f}")
print(f"• Trading Window    : {START_HOUR}:00 AM - {END_HOUR}:00 PM London Time")
print(f"• Momentum Mode     : ADX > {MOMENTUM_ADX_MIN:.0f} | 1:{MOMENTUM_RR:.1f} R/R")
print(f"• Reversion Mode    : ADX < {REVERSION_ADX_MAX:.0f} | 1:{REVERSION_RR:.1f} R/R")
print("=" * 85)


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
# STEP 3: CALCULATE ALL INDICATORS
# =============================================================================
print("[CALC] Calculating 200-EMA, RSI-14, ATR-14, ADX-14, and 5-Day High/Low Channels...")

# 1. 200-Period EMA
df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

# 2. RSI-14
delta = df['Close'].diff()
gain = delta.where(delta > 0, 0.0)
loss = -delta.where(delta < 0, 0.0)
avg_gain = gain.ewm(span=14, adjust=False).mean()
avg_loss = loss.ewm(span=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, 0.00001)
df['RSI_14'] = 100 - (100 / (1 + rs))

# 3. ATR-14
high_low = df['High'] - df['Low']
high_close_prev = (df['High'] - df['Close'].shift(1)).abs()
low_close_prev = (df['Low'] - df['Close'].shift(1)).abs()
df['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
df['ATR_14'] = df['True_Range'].ewm(span=14, adjust=False).mean()

# 4. ADX-14
high_diff = df['High'] - df['High'].shift(1)
low_diff = df['Low'].shift(1) - df['Low']
plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
atr_series = df['True_Range'].ewm(span=14, adjust=False).mean()
plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
df['ADX_14'] = dx.ewm(span=14, adjust=False).mean()

# 5. 5-Day High & Low Channels (120 candles lookback)
df['High_5D'] = df['High'].shift(1).rolling(window=BREAKOUT_LOOKBACK).max()
df['Low_5D'] = df['Low'].shift(1).rolling(window=BREAKOUT_LOOKBACK).min()

print("[OK] Indicator calculations complete!")


# =============================================================================
# STEP 4: 2-YEAR HYBRID BACKTEST SIMULATOR ENGINE
# =============================================================================
print("[SIMULATION] Running 2-Year trade simulation across 17,000+ candles...")

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
    # PART A: MANAGE OPEN POSITION
    # -------------------------------------------------------------------------
    if in_position and active_trade:
        t_type = active_trade['type']
        entry_p = active_trade['entry_price']
        risk_dollar = active_trade['risk_dollar']
        sl_dist = active_trade['sl_distance']
        tp_p = active_trade['tp_price']
        rr_ratio = active_trade['rr_ratio']
        mode_tag = active_trade['mode']
        
        if t_type == "BUY":
            # Trailing stop step 1: Move to Breakeven at 1:1 R/R
            if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                active_trade['sl_price'] = entry_p
                active_trade['trailing_stage'] = 1
            # Trailing stop step 2: Lock 50% profit at 1.5:1 R/R
            if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                active_trade['sl_price'] = entry_p + (0.75 * sl_dist)
                active_trade['trailing_stage'] = 2
                
            if row['High'] >= tp_p: # Take-Profit Hit
                pnl = risk_dollar * rr_ratio
                current_balance += pnl
                trades_history.append({'mode': mode_tag, 'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['Low'] <= active_trade['sl_price']: # Stop-Loss Hit
                pnl = ((active_trade['sl_price'] - entry_p) / sl_dist) * risk_dollar
                current_balance += pnl
                res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                trades_history.append({'mode': mode_tag, 'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': active_trade['sl_price'], 'pnl': pnl, 'result': res, 'balance': current_balance})
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
                pnl = risk_dollar * rr_ratio
                current_balance += pnl
                trades_history.append({'mode': mode_tag, 'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'SELL', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['High'] >= active_trade['sl_price']:
                pnl = ((entry_p - active_trade['sl_price']) / sl_dist) * risk_dollar
                current_balance += pnl
                res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                trades_history.append({'mode': mode_tag, 'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'SELL', 'entry_price': entry_p, 'exit_price': active_trade['sl_price'], 'pnl': pnl, 'result': res, 'balance': current_balance})
                in_position = False
                active_trade = None

    equity_curve.append(current_balance)
    equity_times.append(candle_time)

    # -------------------------------------------------------------------------
    # PART B: EVALUATE HYBRID ENTRY CONDITIONS
    # -------------------------------------------------------------------------
    if not in_position:
        # Time Filter: 6 AM - 4 PM London Time
        in_time_window = (START_HOUR <= candle_time.hour < END_HOUR) or (candle_time.hour == END_HOUR and candle_time.minute == 0)
        if not in_time_window:
            continue

        adx_val = row['ADX_14']
        rsi_val = row['RSI_14']
        if pd.isna(adx_val) or pd.isna(rsi_val):
            continue

        # =====================================================================
        # MODE 1: MOMENTUM MODE (ADX > 30) - TREND BREAKOUT
        # =====================================================================
        if adx_val > MOMENTUM_ADX_MIN:
            mom_buy = not pd.isna(row['High_5D']) and row['Close'] > row['High_5D'] and rsi_val > 55.0
            mom_sell = not pd.isna(row['Low_5D']) and row['Close'] < row['Low_5D'] and rsi_val < 45.0
            
            if mom_buy:
                sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
                risk_dollar = current_balance * RISK_PERCENT
                in_position = True
                active_trade = {
                    'mode': 'MOMENTUM',
                    'type': 'BUY',
                    'entry_time': candle_time,
                    'entry_price': row['Close'],
                    'sl_price': row['Close'] - sl_dist,
                    'tp_price': row['Close'] + (MOMENTUM_RR * sl_dist),
                    'sl_distance': sl_dist,
                    'risk_dollar': risk_dollar,
                    'rr_ratio': MOMENTUM_RR,
                    'trailing_stage': 0
                }
            elif mom_sell:
                sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
                risk_dollar = current_balance * RISK_PERCENT
                in_position = True
                active_trade = {
                    'mode': 'MOMENTUM',
                    'type': 'SELL',
                    'entry_time': candle_time,
                    'entry_price': row['Close'],
                    'sl_price': row['Close'] + sl_dist,
                    'tp_price': row['Close'] - (MOMENTUM_RR * sl_dist),
                    'sl_distance': sl_dist,
                    'risk_dollar': risk_dollar,
                    'rr_ratio': MOMENTUM_RR,
                    'trailing_stage': 0
                }

        # =====================================================================
        # MODE 2: MEAN-REVERSION MODE (ADX < 25) - COUNTER-TREND FADE
        # =====================================================================
        elif adx_val < REVERSION_ADX_MAX:
            rev_buy = not pd.isna(row['Low_5D']) and row['Low'] <= row['Low_5D'] and rsi_val < 30.0
            rev_sell = not pd.isna(row['High_5D']) and row['High'] >= row['High_5D'] and rsi_val > 70.0
            
            if rev_buy:
                sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
                risk_dollar = current_balance * RISK_PERCENT
                in_position = True
                active_trade = {
                    'mode': 'MEAN_REVERSION',
                    'type': 'BUY',
                    'entry_time': candle_time,
                    'entry_price': row['Close'],
                    'sl_price': row['Close'] - sl_dist,
                    'tp_price': row['Close'] + (REVERSION_RR * sl_dist),
                    'sl_distance': sl_dist,
                    'risk_dollar': risk_dollar,
                    'rr_ratio': REVERSION_RR,
                    'trailing_stage': 0
                }
            elif rev_sell:
                sl_dist = max(1.5 * row['ATR_14'], 10 * PIP_SIZE)
                risk_dollar = current_balance * RISK_PERCENT
                in_position = True
                active_trade = {
                    'mode': 'MEAN_REVERSION',
                    'type': 'SELL',
                    'entry_time': candle_time,
                    'entry_price': row['Close'],
                    'sl_price': row['Close'] + sl_dist,
                    'tp_price': row['Close'] - (REVERSION_RR * sl_dist),
                    'sl_distance': sl_dist,
                    'risk_dollar': risk_dollar,
                    'rr_ratio': REVERSION_RR,
                    'trailing_stage': 0
                }


# =============================================================================
# STEP 5: PERFORMANCE METRICS & BREAKDOWN ANALYSIS
# =============================================================================
print("[METRICS] Computing Performance Metrics & Mode Breakdown...")

df_tr = pd.DataFrame(trades_history)
total_trades = len(df_tr)

def calculate_metrics_for_df(df_subset, starting_cap=INITIAL_BALANCE):
    tot = len(df_subset)
    if tot > 0:
        wins = df_subset[df_subset['result'] == 'WIN']
        losses = df_subset[df_subset['result'] == 'LOSS']
        win_rate = (len(wins) / tot) * 100
        gp = wins['pnl'].sum() if not wins.empty else 0.0
        gl = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        net = df_subset['pnl'].sum()
        pf = (gp / gl) if gl > 0 else (gp if gp > 0 else 0.0)
        exp = net / tot
        return tot, len(wins), len(losses), win_rate, gp, gl, net, pf, exp
    else:
        return 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

tot_all, w_all, l_all, wr_all, gp_all, gl_all, net_all, pf_all, exp_all = calculate_metrics_for_df(df_tr)

# Sub-metrics for Momentum Mode vs Mean-Reversion Mode
df_mom = df_tr[df_tr['mode'] == 'MOMENTUM'] if not df_tr.empty else pd.DataFrame()
df_rev = df_tr[df_tr['mode'] == 'MEAN_REVERSION'] if not df_tr.empty else pd.DataFrame()

tot_m, w_m, l_m, wr_m, gp_m, gl_m, net_m, pf_m, exp_m = calculate_metrics_for_df(df_mom)
tot_r, w_r, l_r, wr_r, gp_r, gl_r, net_r, pf_r, exp_r = calculate_metrics_for_df(df_rev)

# Calculate Overall Max Drawdown
eq_ser = pd.Series(equity_curve)
run_max = eq_ser.cummax()
drawdown = (eq_ser - run_max) / run_max
max_dd_pct = abs(drawdown.min()) * 100

print("\n" + "=" * 90)
print("📊 HYBRID STRATEGY 2-YEAR PERFORMANCE DASHBOARD")
print("=" * 90)
print(f"• Ticker Symbol           : {TICKER_SYMBOL}")
print(f"• Strategy Type           : Momentum + Mean-Reversion Hybrid")
print(f"• Backtest Period         : 2 Years (730 Days)")
print(f"• Initial Balance         : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Balance           : ${current_balance:,.2f}")
print(f"• Total Net Profit        : ${net_all:,.2f} ({(net_all/INITIAL_BALANCE)*100:+.2f}%)")
print(f"• Overall Profit Factor   : {pf_all:.2f}")
print(f"• Maximum Drawdown        : {max_dd_pct:.2f}%")
print("=" * 90 + "\n")

# Print Side-by-Side Breakdown Table
print("=" * 95)
print("📌 PERFORMANCE BREAKDOWN: MOMENTUM MODE VS MEAN-REVERSION MODE")
print("=" * 95)
print(f"{'Strategy Mode':<25} | {'Trades':<7} | {'Win %':<7} | {'Profit Factor':<13} | {'Net Profit ($)':<14} | {'Expectancy ($)':<12}")
print("-" * 95)
print(f"{'Momentum Mode (ADX > 30)':<25} | {tot_m:<7} | {wr_m:<6.1f}% | {pf_m:<13.2f} | ${net_m:<13.2f} | ${exp_m:<11.2f}")
print(f"{'Reversion Mode (ADX < 25)':<25} | {tot_r:<7} | {wr_r:<6.1f}% | {pf_r:<13.2f} | ${net_r:<13.2f} | ${exp_r:<11.2f}")
print(f"{'OVERALL HYBRID SYSTEM':<25} | {tot_all:<7} | {wr_all:<6.1f}% | {pf_all:<13.2f} | ${net_all:<13.2f} | ${exp_all:<11.2f}")
print("=" * 95 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (EQUITY CURVE CHART)
# =============================================================================
print("[PLOTS] Generating 2-Year Account Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(equity_times, equity_curve, color='#7B1FA2', linewidth=2.0, label='Hybrid System Account Equity ($)')
ax.axhline(INITIAL_BALANCE, color='#757575', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#E1BEE7', alpha=0.4)
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax.set_title(f"2-Year Account Equity Curve - Momentum + Mean-Reversion Hybrid ({TICKER_SYMBOL})", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "stage3_hybrid_equity.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] Hybrid Equity Curve chart saved to: {os.path.abspath(chart_file)}")

print("\n" + "=" * 80)
print("🏆 FINAL VERDICT & RECOMMENDATION")
print("=" * 80)
if net_all > 0 and pf_all > 1.0:
    print(f"✅ PROFITABLE! The Hybrid strategy generated ${net_all:,.2f} Net Profit with a {pf_all:.2f} Profit Factor.")
else:
    print(f"❌ NOT PROFITABLE OVERALL: Net Profit is ${net_all:,.2f} (Profit Factor: {pf_all:.2f}).")

if net_r > net_m:
    print(f"💡 MODE WINNER: Mean-Reversion Mode outperformed Momentum Mode on EUR/USD (${net_r:,.2f} vs ${net_m:,.2f}).")
else:
    print(f"💡 MODE WINNER: Momentum Mode outperformed Mean-Reversion Mode on EUR/USD (${net_m:,.2f} vs ${net_r:,.2f}).")
print("=" * 80 + "\n")

print("✨ Momentum + Mean-Reversion Hybrid execution completed successfully!")
