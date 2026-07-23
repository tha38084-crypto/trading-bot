"""
===============================================================================
TRADING BOT - STAGE 3: OPTIMIZED MEAN-REVERSION FADER 2.0
===============================================================================
Goal: Test an optimized Mean-Reversion Fader strategy on 2 Years (730 Days)
      of 1-Hour market data for EUR/USD.

Strategy Rules:
  - Asset: EUR/USD (1-Hour chart)
  - Time Filter: 8:00 AM - 12:00 PM London Time
  - ADX Filter: ADX-14 < 35 (Market is not in a runaway trend)
  - RSI Filter: RSI-14 > 60 for SELL, RSI-14 < 40 for BUY
  - Breakout Level: 3-Day High for SELL, 3-Day Low for BUY (72 1H candles lookback)
  - Stop-Loss: 20 pips beyond the 3-Day breakout level (Low_3D - 20 pips for BUY, High_3D + 20 pips for SELL)
  - Take-Profit: 50 pips fixed TP target (0.0050)
  - Risk Per Trade: 2% of current account balance
  - Max Trades Per Day: 3 trades maximum per calendar day (London time)

Target Goals:
  - Net Profit > +$500
  - Max Drawdown < 15%
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
INITIAL_BALANCE = 10000.0   # $10,000 Starting Account
RISK_PERCENT = 0.02         # 2% Risk per trade ($200 on initial trade)

START_HOUR = 8              # 8:00 AM London Time
END_HOUR = 12               # 12:00 PM London Time
MAX_TRADES_PER_DAY = 3      # Maximum 3 trades per calendar day

ADX_MAX = 35.0              # ADX must be < 35
RSI_BUY_MAX = 40.0          # RSI must be < 40 for BUY
RSI_SELL_MIN = 60.0         # RSI must be > 60 for SELL

LOOKBACK_BARS = 72          # 3 Days = 72 1-hour candles
PIP_SIZE = 0.0001           # 1 pip = 0.0001 for EUR/USD
SL_PIPS_BEYOND = 20         # 20 pips beyond the 3D level
TP_PIPS = 50                # 50 pips fixed TP target

LONDON_TZ = pytz.timezone("Europe/London")

print("=" * 85)
print(f"[START] INITIALIZING OPTIMIZED MEAN-REVERSION FADER 2.0 FOR: {TICKER_SYMBOL}")
print(f"• Account Balance   : ${INITIAL_BALANCE:,.2f}")
print(f"• Trading Window    : {START_HOUR}:00 AM - {END_HOUR}:00 PM London Time")
print(f"• ADX Filter        : ADX-14 < {ADX_MAX:.0f}")
print(f"• RSI Filters       : BUY < {RSI_BUY_MAX:.0f} | SELL > {RSI_SELL_MIN:.0f}")
print(f"• Channel Lookback  : 3 Days ({LOOKBACK_BARS} candles)")
print(f"• Stop-Loss         : 20 pips beyond 3D level")
print(f"• Take-Profit       : 50 pips fixed target")
print(f"• Max Daily Trades  : {MAX_TRADES_PER_DAY} trades/day")
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
print("[CALC] Calculating RSI-14, ATR-14, ADX-14, and 3-Day High/Low Channels...")

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

# 5. 3-Day High & Low Channels (72 candles lookback)
df['High_3D'] = df['High'].shift(1).rolling(window=LOOKBACK_BARS).max()
df['Low_3D'] = df['Low'].shift(1).rolling(window=LOOKBACK_BARS).min()

print("[OK] Indicator calculations complete!")


# =============================================================================
# STEP 4: 2-YEAR BACKTEST SIMULATOR ENGINE
# =============================================================================
print("[SIMULATION] Running 2-Year trade simulation across 17,000+ candles...")

current_balance = INITIAL_BALANCE
equity_curve = [INITIAL_BALANCE]
equity_times = [df['London_Time'].iloc[0]]

trades_history = []
in_position = False
active_trade = None

# Track daily trade limits
current_date_str = None
daily_trades_count = 0

for i in range(200, len(df)):
    row = df.iloc[i]
    candle_time = row['London_Time']
    candle_date = candle_time.date()

    # Reset daily trade counter on a new day
    if candle_date != current_date_str:
        current_date_str = candle_date
        daily_trades_count = 0

    # -------------------------------------------------------------------------
    # PART A: MANAGE OPEN POSITION
    # -------------------------------------------------------------------------
    if in_position and active_trade:
        t_type = active_trade['type']
        entry_p = active_trade['entry_price']
        risk_dollar = active_trade['risk_dollar']
        sl_p = active_trade['sl_price']
        tp_p = active_trade['tp_price']
        sl_dist = active_trade['sl_distance']
        tp_dist = active_trade['tp_distance']

        if t_type == "BUY":
            # Trailing Stop: Move to Breakeven at 1:1 Risk-Reward distance
            if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                active_trade['sl_price'] = entry_p
                active_trade['trailing_stage'] = 1

            if row['High'] >= tp_p: # Take-Profit Hit (50 pips)
                reward_ratio = tp_dist / sl_dist
                pnl = risk_dollar * reward_ratio
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['Low'] <= active_trade['sl_price']: # Stop-Loss Hit
                if active_trade['sl_price'] == entry_p:
                    pnl = 0.0
                    res = 'BREAKEVEN'
                else:
                    pnl = -risk_dollar
                    res = 'LOSS'
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'BUY', 'entry_price': entry_p, 'exit_price': active_trade['sl_price'], 'pnl': pnl, 'result': res, 'balance': current_balance})
                in_position = False
                active_trade = None

        elif t_type == "SELL":
            if row['Low'] <= entry_p - sl_dist and active_trade['trailing_stage'] < 1:
                active_trade['sl_price'] = entry_p
                active_trade['trailing_stage'] = 1

            if row['Low'] <= tp_p: # Take-Profit Hit (50 pips)
                reward_ratio = tp_dist / sl_dist
                pnl = risk_dollar * reward_ratio
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'SELL', 'entry_price': entry_p, 'exit_price': tp_p, 'pnl': pnl, 'result': 'WIN', 'balance': current_balance})
                in_position = False
                active_trade = None
            elif row['High'] >= active_trade['sl_price']: # Stop-Loss Hit
                if active_trade['sl_price'] == entry_p:
                    pnl = 0.0
                    res = 'BREAKEVEN'
                else:
                    pnl = -risk_dollar
                    res = 'LOSS'
                current_balance += pnl
                trades_history.append({'entry_time': active_trade['entry_time'], 'exit_time': candle_time, 'type': 'SELL', 'entry_price': entry_p, 'exit_price': active_trade['sl_price'], 'pnl': pnl, 'result': res, 'balance': current_balance})
                in_position = False
                active_trade = None

    equity_curve.append(current_balance)
    equity_times.append(candle_time)

    # -------------------------------------------------------------------------
    # PART B: EVALUATE ENTRY CONDITIONS
    # -------------------------------------------------------------------------
    if not in_position:
        # Check Daily Trade Limit (Max 3 per day)
        if daily_trades_count >= MAX_TRADES_PER_DAY:
            continue

        # Time Filter: 8:00 AM - 12:00 PM London Time
        in_time_window = (START_HOUR <= candle_time.hour < END_HOUR) or (candle_time.hour == END_HOUR and candle_time.minute == 0)
        if not in_time_window:
            continue

        adx_val = row['ADX_14']
        rsi_val = row['RSI_14']
        h3 = row['High_3D']
        l3 = row['Low_3D']

        if pd.isna(adx_val) or pd.isna(rsi_val) or pd.isna(h3) or pd.isna(l3):
            continue

        # Filter 1: ADX < 35
        if adx_val >= ADX_MAX:
            continue

        # Signal 1: BUY (Price touches/breaks 3-Day Low & RSI < 40)
        buy_signal = (row['Low'] <= l3) and (rsi_val < RSI_BUY_MAX)

        # Signal 2: SELL (Price touches/breaks 3-Day High & RSI > 60)
        sell_signal = (row['High'] >= h3) and (rsi_val > RSI_SELL_MIN)

        risk_dollar = current_balance * RISK_PERCENT
        tp_dist = TP_PIPS * PIP_SIZE # 50 pips = 0.0050

        if buy_signal:
            # Stop-Loss: 20 pips beyond 3-Day Low
            sl_price = l3 - (SL_PIPS_BEYOND * PIP_SIZE)
            sl_dist = abs(row['Close'] - sl_price)
            if sl_dist < (5 * PIP_SIZE): # Minimum safety distance
                sl_dist = 5 * PIP_SIZE
                sl_price = row['Close'] - sl_dist

            tp_price = row['Close'] + tp_dist

            in_position = True
            daily_trades_count += 1
            active_trade = {
                'type': 'BUY',
                'entry_time': candle_time,
                'entry_price': row['Close'],
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_distance': sl_dist,
                'tp_distance': tp_dist,
                'risk_dollar': risk_dollar,
                'trailing_stage': 0
            }

        elif sell_signal:
            # Stop-Loss: 20 pips beyond 3-Day High
            sl_price = h3 + (SL_PIPS_BEYOND * PIP_SIZE)
            sl_dist = abs(sl_price - row['Close'])
            if sl_dist < (5 * PIP_SIZE):
                sl_dist = 5 * PIP_SIZE
                sl_price = row['Close'] + sl_dist

            tp_price = row['Close'] - tp_dist

            in_position = True
            daily_trades_count += 1
            active_trade = {
                'type': 'SELL',
                'entry_time': candle_time,
                'entry_price': row['Close'],
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_distance': sl_dist,
                'tp_distance': tp_dist,
                'risk_dollar': risk_dollar,
                'trailing_stage': 0
            }


# =============================================================================
# STEP 5: PERFORMANCE METRICS CALCULATION
# =============================================================================
print("[METRICS] Calculating Performance Metrics...")

df_tr = pd.DataFrame(trades_history)
total_trades = len(df_tr)

if total_trades > 0:
    wins = df_tr[df_tr['result'] == 'WIN']
    losses = df_tr[df_tr['result'] == 'LOSS']
    win_rate = (len(wins) / total_trades) * 100
    gross_profit = wins['pnl'].sum() if not wins.empty else 0.0
    gross_loss = abs(losses['pnl'].sum()) if not losses.empty else 0.0
    net_profit = df_tr['pnl'].sum()
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    expectancy = net_profit / total_trades

    eq_ser = pd.Series(equity_curve)
    run_max = eq_ser.cummax()
    drawdown = (eq_ser - run_max) / run_max
    max_dd_pct = abs(drawdown.min()) * 100
else:
    win_rate = gross_profit = gross_loss = net_profit = profit_factor = expectancy = max_dd_pct = 0.0

print("\n" + "=" * 90)
print("📊 OPTIMIZED MEAN-REVERSION FADER 2.0 PERFORMANCE DASHBOARD")
print("=" * 90)
print(f"• Ticker Symbol           : {TICKER_SYMBOL}")
print(f"• Backtest Period         : 2 Years (730 Days)")
print(f"• Starting Balance        : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Balance           : ${current_balance:,.2f}")
print(f"• Total Trades            : {total_trades}")
print(f"• Win Rate                : {win_rate:.1f}%")
print(f"• Profit Factor           : {profit_factor:.2f}")
print(f"• Total Net Profit        : ${net_profit:,.2f} ({(net_profit/INITIAL_BALANCE)*100:+.2f}%)")
print(f"• Maximum Drawdown        : {max_dd_pct:.2f}%")
print(f"• Expectancy per Trade    : ${expectancy:,.2f}")
print("=" * 90 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (EQUITY CURVE CHART)
# =============================================================================
print("[PLOTS] Generating 2-Year Account Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(equity_times, equity_curve, color='#00897B', linewidth=2.0, label='Fader 2.0 Account Equity ($)')
ax.axhline(INITIAL_BALANCE, color='#616161', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#B2DFDB', alpha=0.4)
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax.set_title(f"2-Year Account Equity Curve - Optimized Mean-Reversion Fader 2.0 ({TICKER_SYMBOL})", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "stage3_fader_2_equity.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] Equity Curve chart saved to: {os.path.abspath(chart_file)}")

print("\n" + "=" * 80)
print("🏆 TARGET EVALUATION & FINAL VERDICT")
print("=" * 80)

passed_profit = net_profit > 500.0
passed_dd = max_dd_pct < 15.0

print(f"• Net Profit Goal (> +$500.00) : ${net_profit:,.2f} [{'✅ PASSED' if passed_profit else '❌ FAILED'}]")
print(f"• Max Drawdown Goal (< 15.0%)  : {max_dd_pct:.2f}% [{'✅ PASSED' if passed_dd else '❌ FAILED'}]")

if passed_profit and passed_dd:
    print("\n🎉 SUCCESS! All goals met. Optimized Mean-Reversion Fader 2.0 is READY for Stage 4!")
else:
    print("\n⚠️ PARTIAL SUCCESS / NEEDS TUNING: Target benchmarks were not fully satisfied.")
print("=" * 80 + "\n")

print("✨ Optimized Mean-Reversion Fader 2.0 execution completed successfully!")
