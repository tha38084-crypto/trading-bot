"""
===============================================================================
TRADING BOT - STAGE 3: EUR/USD FOREX FADER FINE-TUNING OPTIMIZER
===============================================================================
Goal: Fine-tune our winning Forex Fader strategy on EUR/USD (EURUSD=X) across
      6 parameter variations over 2 Years (730 Days) of 1-Hour market data.

Target Goal: Push Net Profit from +$800.86 (Baseline) to +$1,000+.

Tested Variations:
  - Baseline   : RSI 70/30, ADX < 25, SL 15p, TP 30p, 6 AM - 4 PM London
  - Variation 1: RSI 68/32 (Slightly looser RSI threshold)
  - Variation 2: ADX < 28 (Looser trend filter)
  - Variation 3: Stop-Loss 12 pips beyond 5D level (Tighter SL)
  - Variation 4: Take-Profit 26 pips (Shorter TP target)
  - Variation 5: Time Window 8 AM - 12 PM London (Narrower session)
  - Variation 6: Combined Best-Performing Variations
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
# STEP 1: CONFIGURATION & SETUP
# =============================================================================
TICKER_SYMBOL = "EURUSD=X"
INITIAL_BALANCE = 10000.0   # $10,000 Starting Account Capital
RISK_PERCENT = 0.02         # 2% Risk per trade
LOOKBACK_BARS = 120         # 5 Days = 120 1-hour candles
PIP_SIZE = 0.0001           # 1 pip = 0.0001 for EUR/USD
LONDON_TZ = pytz.timezone("Europe/London")

print("=" * 90)
print(f"[START] INITIALIZING EUR/USD FOREX FADER FINE-TUNING OPTIMIZER")
print(f"• Ticker Symbol     : {TICKER_SYMBOL}")
print(f"• Backtest Period   : 2 Years (730 Days)")
print(f"• Starting Balance  : ${INITIAL_BALANCE:,.2f}")
print("=" * 90)


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
# STEP 3: CALCULATE BASE INDICATORS
# =============================================================================
print("[CALC] Calculating RSI-14, ATR-14, ADX-14, and 5-Day High/Low Channels...")

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

# 3. ATR-14 & True Range
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
df['High_5D'] = df['High'].shift(1).rolling(window=LOOKBACK_BARS).max()
df['Low_5D'] = df['Low'].shift(1).rolling(window=LOOKBACK_BARS).min()

print("[OK] Indicator calculations complete!")


# =============================================================================
# STEP 4: REUSABLE BACKTEST ENGINE FOR VARIATIONS
# =============================================================================
def run_fader_simulation(df_input, rsi_buy=30.0, rsi_sell=70.0, adx_max=25.0, sl_pips=15, tp_pips=30, start_hour=6, end_hour=16):
    current_balance = INITIAL_BALANCE
    equity_curve = [INITIAL_BALANCE]
    equity_times = [df_input['London_Time'].iloc[0]]

    trades_history = []
    in_position = False
    active_trade = None

    for i in range(200, len(df_input)):
        row = df_input.iloc[i]
        candle_time = row['London_Time']

        # MANAGE POSITION
        if in_position and active_trade:
            t_type = active_trade['type']
            entry_p = active_trade['entry_price']
            risk_dollar = active_trade['risk_dollar']
            sl_p = active_trade['sl_price']
            tp_p = active_trade['tp_price']
            sl_dist = active_trade['sl_distance']
            tp_dist = active_trade['tp_distance']

            if t_type == "BUY":
                if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                    active_trade['sl_price'] = entry_p
                    active_trade['trailing_stage'] = 1
                if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                    active_trade['sl_price'] = entry_p + (0.75 * sl_dist)
                    active_trade['trailing_stage'] = 2

                if row['High'] >= tp_p:
                    reward_ratio = tp_dist / sl_dist
                    pnl = risk_dollar * reward_ratio
                    current_balance += pnl
                    trades_history.append({'pnl': pnl, 'result': 'WIN'})
                    in_position = False
                    active_trade = None
                elif row['Low'] <= active_trade['sl_price']:
                    pnl = ((active_trade['sl_price'] - entry_p) / sl_dist) * risk_dollar
                    current_balance += pnl
                    res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                    trades_history.append({'pnl': pnl, 'result': res})
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
                    reward_ratio = tp_dist / sl_dist
                    pnl = risk_dollar * reward_ratio
                    current_balance += pnl
                    trades_history.append({'pnl': pnl, 'result': 'WIN'})
                    in_position = False
                    active_trade = None
                elif row['High'] >= active_trade['sl_price']:
                    pnl = ((entry_p - active_trade['sl_price']) / sl_dist) * risk_dollar
                    current_balance += pnl
                    res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                    trades_history.append({'pnl': pnl, 'result': res})
                    in_position = False
                    active_trade = None

        equity_curve.append(current_balance)
        equity_times.append(candle_time)

        # ENTRY EVALUATION
        if not in_position:
            in_time = (start_hour <= candle_time.hour < end_hour) or (candle_time.hour == end_hour and candle_time.minute == 0)
            if not in_time:
                continue

            adx_val = row['ADX_14']
            rsi_val = row['RSI_14']
            h5 = row['High_5D']
            l5 = row['Low_5D']

            if pd.isna(adx_val) or pd.isna(rsi_val) or pd.isna(h5) or pd.isna(l5):
                continue

            if adx_val >= adx_max:
                continue

            buy_signal = (row['Low'] <= l5) and (rsi_val < rsi_buy)
            sell_signal = (row['High'] >= h5) and (rsi_val > rsi_sell)

            risk_dollar = current_balance * RISK_PERCENT
            tp_dist = tp_pips * PIP_SIZE

            if buy_signal:
                sl_price = l5 - (sl_pips * PIP_SIZE)
                sl_dist = abs(row['Close'] - sl_price)
                if sl_dist < (5 * PIP_SIZE):
                    sl_dist = 5 * PIP_SIZE
                    sl_price = row['Close'] - sl_dist

                tp_price = row['Close'] + tp_dist
                in_position = True
                active_trade = {
                    'type': 'BUY', 'entry_price': row['Close'], 'sl_price': sl_price, 'tp_price': tp_price,
                    'sl_distance': sl_dist, 'tp_distance': tp_dist, 'risk_dollar': risk_dollar, 'trailing_stage': 0
                }

            elif sell_signal:
                sl_price = h5 + (sl_pips * PIP_SIZE)
                sl_dist = abs(sl_price - row['Close'])
                if sl_dist < (5 * PIP_SIZE):
                    sl_dist = 5 * PIP_SIZE
                    sl_price = row['Close'] + sl_dist

                tp_price = row['Close'] - tp_dist
                in_position = True
                active_trade = {
                    'type': 'SELL', 'entry_price': row['Close'], 'sl_price': sl_price, 'tp_price': tp_price,
                    'sl_distance': sl_dist, 'tp_distance': tp_dist, 'risk_dollar': risk_dollar, 'trailing_stage': 0
                }

    # METRICS
    df_tr = pd.DataFrame(trades_history)
    tot = len(df_tr)
    if tot > 0:
        wins = df_tr[df_tr['result'] == 'WIN']
        losses = df_tr[df_tr['result'] == 'LOSS']
        win_rate = (len(wins) / tot) * 100
        gp = wins['pnl'].sum() if not wins.empty else 0.0
        gl = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        net = df_tr['pnl'].sum()
        pf = (gp / gl) if gl > 0 else (gp if gp > 0 else 0.0)
        exp = net / tot
        eq_ser = pd.Series(equity_curve)
        run_max = eq_ser.cummax()
        dd = abs(((eq_ser - run_max) / run_max).min()) * 100
    else:
        win_rate = gp = gl = net = pf = exp = dd = 0.0

    return {
        'total_trades': tot, 'win_rate': win_rate, 'profit_factor': pf,
        'net_profit': net, 'max_dd': dd, 'expectancy': exp,
        'final_balance': current_balance, 'equity_curve': equity_curve, 'equity_times': equity_times
    }


# =============================================================================
# STEP 5: RUN ALL 6 VARIATIONS
# =============================================================================
print("[RUNNER] Running Backtests across Baseline and Variations 1 to 5...")

# Baseline: RSI 70/30, ADX < 25, SL 15p, TP 30p, 6 AM - 4 PM London
base_res = run_fader_simulation(df, rsi_buy=30.0, rsi_sell=70.0, adx_max=25.0, sl_pips=15, tp_pips=30, start_hour=6, end_hour=16)

# Variation 1: RSI 68/32
v1_res = run_fader_simulation(df, rsi_buy=32.0, rsi_sell=68.0, adx_max=25.0, sl_pips=15, tp_pips=30, start_hour=6, end_hour=16)

# Variation 2: ADX < 28
v2_res = run_fader_simulation(df, rsi_buy=30.0, rsi_sell=70.0, adx_max=28.0, sl_pips=15, tp_pips=30, start_hour=6, end_hour=16)

# Variation 3: Stop-Loss 12 pips
v3_res = run_fader_simulation(df, rsi_buy=30.0, rsi_sell=70.0, adx_max=25.0, sl_pips=12, tp_pips=30, start_hour=6, end_hour=16)

# Variation 4: Take-Profit 26 pips
v4_res = run_fader_simulation(df, rsi_buy=30.0, rsi_sell=70.0, adx_max=25.0, sl_pips=15, tp_pips=26, start_hour=6, end_hour=16)

# Variation 5: Time 8 AM - 12 PM
v5_res = run_fader_simulation(df, rsi_buy=30.0, rsi_sell=70.0, adx_max=25.0, sl_pips=15, tp_pips=30, start_hour=8, end_hour=12)

# Determine best parameter tweaks to construct Variation 6
# Check individual improvements vs Baseline
best_rsi_buy = 32.0 if v1_res['net_profit'] > base_res['net_profit'] else 30.0
best_rsi_sell = 68.0 if v1_res['net_profit'] > base_res['net_profit'] else 70.0
best_adx = 28.0 if v2_res['net_profit'] > base_res['net_profit'] else 25.0
best_sl = 12 if v3_res['net_profit'] > base_res['net_profit'] else 15
best_tp = 26 if v4_res['net_profit'] > base_res['net_profit'] else 30
best_sh = 8 if v5_res['net_profit'] > base_res['net_profit'] else 6
best_eh = 12 if v5_res['net_profit'] > base_res['net_profit'] else 16

# Variation 6: Combined Best
v6_res = run_fader_simulation(df, rsi_buy=best_rsi_buy, rsi_sell=best_rsi_sell, adx_max=best_adx, sl_pips=best_sl, tp_pips=best_tp, start_hour=best_sh, end_hour=best_eh)

variations_list = [
    {"name": "Baseline (Original Winner)", "res": base_res},
    {"name": "Variation 1: RSI 68/32", "res": v1_res},
    {"name": "Variation 2: ADX < 28", "res": v2_res},
    {"name": "Variation 3: Stop-Loss 12 pips", "res": v3_res},
    {"name": "Variation 4: Take-Profit 26 pips", "res": v4_res},
    {"name": "Variation 5: Time 8 AM - 12 PM", "res": v5_res},
    {"name": "Variation 6: Combined Best Tweaks", "res": v6_res},
]


# =============================================================================
# STEP 6: COMPARISON DASHBOARD & WINNER IDENTIFICATION
# =============================================================================
print("\n" + "=" * 95)
print("📊 EUR/USD FOREX FADER FINE-TUNING COMPARISON DASHBOARD")
print("=" * 95)
print(f"{'Variation Name':<34} | {'Trades':<7} | {'Win %':<7} | {'Profit Factor':<13} | {'Net Profit ($)':<14} | {'Max DD %':<8} | {'Expectancy ($)':<12}")
print("-" * 95)

best_var = variations_list[0]
for v in variations_list:
    r = v['res']
    if r['net_profit'] > best_var['res']['net_profit']:
        best_var = v
    print(f"{v['name']:<34} | {r['total_trades']:<7} | {r['win_rate']:<6.1f}% | {r['profit_factor']:<13.2f} | ${r['net_profit']:<13.2f} | {r['max_dd']:<7.2f}% | ${r['expectancy']:<11.2f}")

print("=" * 95 + "\n")


# =============================================================================
# STEP 7: VISUALIZATION (MULTI-VARIATION EQUITY PLOT)
# =============================================================================
print("[PLOTS] Generating Multi-Variation Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(14, 8))

colors = ['#1E88E5', '#43A047', '#FB8C00', '#8E24AA', '#00ACC1', '#E53935', '#D81B60']

for idx, v in enumerate(variations_list):
    r = v['res']
    is_winner = (v == best_var)
    ax.plot(r['equity_times'], r['equity_curve'], label=f"{v['name']} (${r['net_profit']:+,.2f})", color=colors[idx], linewidth=2.5 if is_winner else 1.2, alpha=1.0 if is_winner else 0.7)

ax.axhline(INITIAL_BALANCE, color='#333333', linestyle='--', linewidth=1.2, label=f"Starting Capital (${INITIAL_BALANCE:,.0f})")
ax.set_title("EUR/USD Forex Fader Strategy - 2-Year Fine-Tuning Equity Curve Comparison", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_name = "stage3_fader_tuning_comparison.png"
plt.savefig(chart_name, dpi=150)
print(f"[SAVE] Multi-Variation comparison chart saved to: {os.path.abspath(chart_name)}")

print("\n" + "=" * 80)
print("🏆 WINNING VARIATION & FINAL RECOMMENDATION")
print("=" * 80)
print(f"• BEST VARIATION        : {best_var['name']}")
print(f"• Total Net Profit      : ${best_var['res']['net_profit']:+,.2f} (Goal: > +$1,000.00)")
print(f"• Profit Factor         : {best_var['res']['profit_factor']:.2f}")
print(f"• Win Rate              : {best_var['res']['win_rate']:.1f}% ({best_var['res']['total_trades']} Trades)")
print(f"• Max Drawdown          : {best_var['res']['max_dd']:.2f}%")
print(f"• Expectancy per Trade  : ${best_var['res']['expectancy']:+,.2f}")
print("=" * 80 + "\n")

print("✨ EUR/USD Forex Fader fine-tuning optimization completed successfully!")
