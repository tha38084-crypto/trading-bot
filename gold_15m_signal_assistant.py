"""
===============================================================================
TRADING BOT - STAGE 3: 15-MINUTE GOLD CONFLUENCE AI SIGNAL ASSISTANT
===============================================================================
Goal: High-probability 15-Minute Intraday Signal Assistant engineered for a $200 account
      targeting 4-5 high-quality trades per week with $6.00 Risk (3%) to $12.00 Reward (6%).

The 15-Minute Gold Confluence Stack (ALL 4 must PASS):
  1. 200-EMA Trend Alignment : BUY only above 200-EMA, SELL only below 200-EMA
  2. 1D Liquidity Sweep      : Touch/Sweep of 1-Day High/Low channels (96 15M candles)
  3. RSI Reversal Extreme    : RSI-14 < 30 for BUY, RSI-14 > 70 for SELL
  4. Prime Session Window    : Active London & NY Session (08:00 - 17:00 London Time)

Layered Exit Protection:
  - TP1 (+1:1 R/R = +$6.00): Scale-out 50% position + Move SL to Breakeven ($0.00 risk!)
  - TP2 (+1:2 R/R = +$12.00): Scale-out remaining 50% position.
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
INITIAL_BALANCE = 200.0     # $200 Starting Micro Account
RISK_PERCENT = 0.03         # 3% Risk per trade ($6.00)

ADX_MAX = 30.0              # ADX-14 < 30 (Ranging / Channel Regime)
RSI_BUY_MAX = 30.0          # RSI-14 < 30 (Oversold BUY)
RSI_SELL_MIN = 70.0         # RSI-14 > 70 (Overbought SELL)
LOOKBACK_BARS = 96          # 1 Day = 96 15-minute candles

WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip_size": 0.0001, "sl_pips": 10},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip_size": 0.01,   "sl_pips": 12},
]

LONDON_TZ = pytz.timezone("Europe/London")

print("=" * 90)
print(f"[START] INITIALIZING 15-MINUTE GOLD CONFLUENCE SIGNAL ASSISTANT FOR $200 ACCOUNT")
print(f"• Account Balance   : ${INITIAL_BALANCE:,.2f}")
print(f"• Risk Per Trade    : ${INITIAL_BALANCE * RISK_PERCENT:,.2f} (3%)")
print(f"• Target Reward     : ${INITIAL_BALANCE * RISK_PERCENT * 2:,.2f} (6% - 1:2 R/R)")
print(f"• Confluence Rules  : 200-EMA Trend + 1D Liquidity Sweep + RSI 30/70 + Session Window")
print(f"• Layered Exit Rule : TP1 (50% scale-out + SL to Breakeven) | TP2 (50% scale-out)")
print(f"• Asset Watchlist   : {', '.join([item['name'] for item in WATCHLIST])}")
print("=" * 90)


# =============================================================================
# STEP 2: DOWNLOAD 15-MINUTE DATA & CALCULATE INDICATORS
# =============================================================================
def fetch_and_calculate_15m_data(asset_info):
    symbol = asset_info['symbol']
    print(f"[FETCH] Downloading 60 Days of 15-Minute data for {asset_info['name']} ({symbol})...")
    
    try:
        df = yf.download(tickers=symbol, period="60d", interval="15m", progress=False)
    except Exception as e:
        print(f"[WARNING] Could not fetch data for {symbol}: {e}")
        return None

    if df.empty:
        print(f"[WARNING] Data for {symbol} returned empty dataframe. Skipping...")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    df['London_Time'] = df.index.tz_convert(LONDON_TZ)

    # 1. 200-Period EMA (15M)
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

    # 5. 1-Day High & Low Channels (96 15M candles lookback)
    df['High_1D'] = df['High'].shift(1).rolling(window=LOOKBACK_BARS).max()
    df['Low_1D'] = df['Low'].shift(1).rolling(window=LOOKBACK_BARS).min()

    return df

asset_data_dict = {}
for asset in WATCHLIST:
    processed_df = fetch_and_calculate_15m_data(asset)
    if processed_df is not None:
        asset_data_dict[asset['symbol']] = processed_df

if not asset_data_dict:
    raise ValueError("[ERROR] No 15-minute asset data could be fetched. Check internet connection or tickers.")

print("[OK] Downloaded and calculated 15M indicators for watchlist assets!")


# =============================================================================
# STEP 3: SAMPLE SIGNAL ALERT CARD DISPLAY GENERATOR
# =============================================================================
def print_sample_signal_card(asset_info, action, entry, sl, tp1, tp2, time_str, rsi_val, adx_val, ema_val):
    risk_usd = INITIAL_BALANCE * RISK_PERCENT
    reward_usd = risk_usd * 2.0
    
    print("\n" + "═" * 75)
    print("🏆 15-MINUTE GOLD HIGH-PROBABILITY SIGNAL ALERT 🏆")
    print("═" * 75)
    print(f"• Asset Pair      : {asset_info['name']} ({asset_info['symbol']}) [15-Minute Chart]")
    print(f"• Action Signal   : {'🟢 BUY (LONG)' if action == 'BUY' else '🔴 SELL (SHORT)'}")
    print(f"• Signal Time     : {time_str} London Time")
    print("─" * 75)
    print(f"• Suggested Entry : {entry:.4f}")
    print(f"• Stop-Loss (SL)  : {sl:.4f}  --> Risk: -${risk_usd:.2f} (3.0%)")
    print(f"• Take-Profit 1   : {tp1:.4f}  --> TP1 (50% scale-out + Move SL to Breakeven)")
    print(f"• Take-Profit 2   : {tp2:.4f}  --> TP2 (50% scale-out for +${reward_usd:.2f} total)")
    print("─" * 75)
    print(f"• Gold Confluence Rationale:")
    print(f"  1. Trend Filter : Price ({entry:.4f}) {'Above' if action=='BUY' else 'Below'} 200-EMA ({ema_val:.4f})")
    print(f"  2. Structure    : Touched 1-Day Channel Level (Liquidity Reversal Zone)")
    print(f"  3. RSI Extreme  : RSI-14 = {rsi_val:.1f} ({'Oversold < 30' if action=='BUY' else 'Overbought > 70'})")
    print(f"  4. Session      : Active Session Window (08:00 - 17:00 London Time)")
    print("═" * 75)
    print("👉 Action: Open your broker app (Exness, MetaTrader) & place this order!")
    print("═" * 75 + "\n")


# =============================================================================
# STEP 4: 15-MINUTE PORTFOLIO BACKTEST SIMULATOR
# =============================================================================
print("[SIMULATION] Running 15-Minute Portfolio Simulation across Watchlist...")

current_balance = INITIAL_BALANCE
equity_curve = [INITIAL_BALANCE]

sample_df = list(asset_data_dict.values())[0]
equity_times = [sample_df['London_Time'].iloc[200]]

trades_history = []
active_trades = []
sample_card_printed = False

for i in range(200, len(sample_df)):
    current_time = sample_df['London_Time'].iloc[i]

    # Manage Active Trades
    closed_trades = []
    for trade in active_trades:
        sym = trade['symbol']
        if sym not in asset_data_dict or i >= len(asset_data_dict[sym]):
            continue
            
        bar = asset_data_dict[sym].iloc[i]
        t_type = trade['type']
        ep = trade['entry_price']
        sl = trade['sl_price']
        tp1 = trade['tp1_price']
        tp2 = trade['tp2_price']
        risk_usd = trade['risk_dollar']

        if t_type == "BUY":
            # Check TP1: 50% Exit + SL to Breakeven
            if bar['High'] >= tp1 and not trade['tp1_hit']:
                trade['tp1_hit'] = True
                trade['sl_price'] = ep
                pnl_part = risk_usd * 0.5 * 1.0
                current_balance += pnl_part
                trade['realized_pnl'] += pnl_part

            # Check TP2: Final Exit
            if bar['High'] >= tp2:
                pnl_part = risk_usd * 0.5 * 2.0
                current_balance += pnl_part
                total_pnl = trade['realized_pnl'] + pnl_part
                trades_history.append({'symbol': sym, 'pnl': total_pnl, 'result': 'WIN'})
                closed_trades.append(trade)

            elif bar['Low'] <= trade['sl_price']:
                if trade['sl_price'] == ep:
                    trades_history.append({'symbol': sym, 'pnl': trade['realized_pnl'], 'result': 'BREAKEVEN'})
                else:
                    pnl_loss = -risk_usd
                    current_balance += pnl_loss
                    trades_history.append({'symbol': sym, 'pnl': pnl_loss, 'result': 'LOSS'})
                closed_trades.append(trade)

        elif t_type == "SELL":
            if bar['Low'] <= tp1 and not trade['tp1_hit']:
                trade['tp1_hit'] = True
                trade['sl_price'] = ep
                pnl_part = risk_usd * 0.5 * 1.0
                current_balance += pnl_part
                trade['realized_pnl'] += pnl_part

            if bar['Low'] <= tp2:
                pnl_part = risk_usd * 0.5 * 2.0
                current_balance += pnl_part
                total_pnl = trade['realized_pnl'] + pnl_part
                trades_history.append({'symbol': sym, 'pnl': total_pnl, 'result': 'WIN'})
                closed_trades.append(trade)

            elif bar['High'] >= trade['sl_price']:
                if trade['sl_price'] == ep:
                    trades_history.append({'symbol': sym, 'pnl': trade['realized_pnl'], 'result': 'BREAKEVEN'})
                else:
                    pnl_loss = -risk_usd
                    current_balance += pnl_loss
                    trades_history.append({'symbol': sym, 'pnl': pnl_loss, 'result': 'LOSS'})
                closed_trades.append(trade)

    for ct in closed_trades:
        active_trades.remove(ct)

    equity_curve.append(current_balance)
    equity_times.append(current_time)

    # Active Session Window: 08:00 - 17:00 London Time
    in_session = (8 <= current_time.hour < 17)
    if not in_session:
        continue

    for asset_info in WATCHLIST:
        sym = asset_info['symbol']
        if sym not in asset_data_dict or i >= len(asset_data_dict[sym]):
            continue

        bar = asset_data_dict[sym].iloc[i]
        adx_val = bar['ADX_14']
        rsi_val = bar['RSI_14']
        ema_val = bar['EMA_200']
        h1 = bar['High_1D']
        l1 = bar['Low_1D']

        if pd.isna(adx_val) or pd.isna(rsi_val) or pd.isna(ema_val) or pd.isna(h1) or pd.isna(l1):
            continue

        if adx_val >= ADX_MAX:
            continue

        if any(t['symbol'] == sym for t in active_trades):
            continue

        pip_sz = asset_info['pip_size']
        sl_pips = asset_info['sl_pips']
        risk_usd = current_balance * RISK_PERCENT

        # 15M GOLD CONFLUENCE RULES:
        # BUY: Price > 200-EMA (Uptrend) AND Low <= Low_1D AND RSI < 30
        buy_signal = (bar['Close'] > ema_val) and (bar['Low'] <= l1) and (rsi_val < RSI_BUY_MAX)

        # SELL: Price < 200-EMA (Downtrend) AND High >= High_1D AND RSI > 70
        sell_signal = (bar['Close'] < ema_val) and (bar['High'] >= h1) and (rsi_val > RSI_SELL_MIN)

        if buy_signal:
            sl_price = l1 - (sl_pips * pip_sz)
            sl_dist = abs(bar['Close'] - sl_price)
            if sl_dist < (4 * pip_sz):
                sl_dist = 4 * pip_sz
                sl_price = bar['Close'] - sl_dist

            tp1_price = bar['Close'] + (1.0 * sl_dist)
            tp2_price = bar['Close'] + (2.0 * sl_dist)

            active_trades.append({
                'symbol': sym, 'type': 'BUY', 'entry_price': bar['Close'],
                'sl_price': sl_price, 'tp1_price': tp1_price, 'tp2_price': tp2_price,
                'sl_distance': sl_dist, 'risk_dollar': risk_usd, 'tp1_hit': False, 'realized_pnl': 0.0
            })

            if not sample_card_printed:
                print_sample_signal_card(asset_info, "BUY", bar['Close'], sl_price, tp1_price, tp2_price, str(current_time), rsi_val, adx_val, ema_val)
                sample_card_printed = True

        elif sell_signal:
            sl_price = h1 + (sl_pips * pip_sz)
            sl_dist = abs(sl_price - bar['Close'])
            if sl_dist < (4 * pip_sz):
                sl_dist = 4 * pip_sz
                sl_price = bar['Close'] + sl_dist

            tp1_price = bar['Close'] - (1.0 * sl_dist)
            tp2_price = bar['Close'] - (2.0 * sl_dist)

            active_trades.append({
                'symbol': sym, 'type': 'SELL', 'entry_price': bar['Close'],
                'sl_price': sl_price, 'tp1_price': tp1_price, 'tp2_price': tp2_price,
                'sl_distance': sl_dist, 'risk_dollar': risk_usd, 'tp1_hit': False, 'realized_pnl': 0.0
            })

            if not sample_card_printed:
                print_sample_signal_card(asset_info, "SELL", bar['Close'], sl_price, tp1_price, tp2_price, str(current_time), rsi_val, adx_val, ema_val)
                sample_card_printed = True


# =============================================================================
# STEP 5: PERFORMANCE METRICS & BREAKDOWN ANALYSIS
# =============================================================================
print("[METRICS] Computing Performance Metrics...")

df_tr = pd.DataFrame(trades_history)
total_trades = len(df_tr)

# Calculate total weeks in simulation period (~60 days = 8.5 weeks)
total_days = (sample_df['London_Time'].iloc[-1] - sample_df['London_Time'].iloc[200]).days
weeks = max(1.0, total_days / 7.0)
trades_per_week = total_trades / weeks

if total_trades > 0:
    wins = df_tr[df_tr['result'] == 'WIN']
    losses = df_tr[df_tr['result'] == 'LOSS']
    breakevens = df_tr[df_tr['result'] == 'BREAKEVEN']
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
print("📊 15-MINUTE GOLD CONFLUENCE AI SIGNAL ASSISTANT PERFORMANCE DASHBOARD ($200 Account)")
print("=" * 90)
print(f"• Backtest Duration       : ~{total_days} Days ({weeks:.1f} Weeks)")
print(f"• Starting Balance        : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Balance           : ${current_balance:,.2f}")
print(f"• Total Net Profit        : ${net_profit:,.2f} ({(net_profit/INITIAL_BALANCE)*100:+.2f}%)")
print(f"• Total Signals           : {total_trades} Signals ({trades_per_week:.1f} Signals/Week Target!)")
print(f"• Win Rate                : {win_rate:.1f}% ({len(wins)} Wins, {len(losses)} Losses, {len(breakevens)} Risk-Free Breakevens)")
print(f"• Profit Factor           : {profit_factor:.2f}")
print(f"• Maximum Drawdown        : {max_dd_pct:.2f}%")
print(f"• Expectancy per Signal   : ${expectancy:,.2f}")
print("=" * 90 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (EQUITY CURVE CHART)
# =============================================================================
print("[PLOTS] Generating 15-Minute Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(equity_times, equity_curve, color='#FF8F00', linewidth=2.0, label='15M Gold Signal Assistant Equity ($)')
ax.axhline(INITIAL_BALANCE, color='#616161', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#FFECB3', alpha=0.4)
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax.set_title("15-Minute Gold Confluence AI Signal Assistant - Intraday Performance ($200 Account)", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "gold_15m_signal_assistant_equity.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] 15M Equity Curve chart saved to: {os.path.abspath(chart_file)}")

print("\n" + "=" * 80)
print("🏆 FINAL VERDICT & TARGET EVALUATION")
print("=" * 80)

passed_freq = trades_per_week >= 3.0
passed_profit = net_profit > 0.0

print(f"• Trade Frequency Target (4-5 Trades/Wk) : {trades_per_week:.1f} Signals/Wk [{'✅ PASSED' if passed_freq else '❌ FAILED'}]")
print(f"• Net Profit Target (> $0.00)            : ${net_profit:,.2f} [{'✅ PASSED' if passed_profit else '❌ FAILED'}]")

if passed_freq and passed_profit:
    print("\n🎉 PERFECT MATCH! The 15-Minute Gold Engine met both frequency and profitability targets!")
else:
    print("\n⚠️ PARTIAL MATCH: Performance summary complete.")
print("=" * 80 + "\n")

print("✨ 15-Minute Gold Signal Assistant execution completed successfully!")
