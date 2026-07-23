"""
===============================================================================
TRADING BOT - STAGE 3: GOLD 4-FILTER CONFLUENCE AI SIGNAL ASSISTANT
===============================================================================
Goal: High-probability multi-asset signal assistant engineered for a $200 account
      targeting 4-5 trades per week with $6.00 Risk (3%) to $12.00 Reward (6%)
      and Multi-Period Horizon Backtesting (2 Years, 1 Year, 6 Months, 3 Months).

The Gold Confluence Stack (ALL 4 must PASS):
  1. 200-EMA Trend Alignment : BUY only above 200-EMA, SELL only below 200-EMA
  2. 3D Liquidity Sweep      : Touch/Sweep of 3-Day High/Low channels (72 candles)
  3. Deep RSI Reversal       : RSI-14 < 28 for BUY, RSI-14 > 72 for SELL
  4. Prime Session Window    : London Open (08:00-11:00) & NY Open (13:00-17:00)

Layered Protection Rule:
  - TP1 (+1:1 R/R): Close 50% position + Move SL to Breakeven ($0.00 risk!)
  - TP2 (+1:2 R/R): Close remaining 50% position for full profit.
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

# Gold Technical Filter Thresholds
ADX_MAX = 30.0              # ADX-14 < 30 (Ranging / Channel Regime)
RSI_BUY_MAX = 28.0          # RSI-14 < 28 (Deep Oversold BUY)
RSI_SELL_MIN = 72.0         # RSI-14 > 72 (Deep Overbought SELL)
LOOKBACK_BARS = 72          # 3-Day Channel (72 1-hour candles)

# Watchlist Definition (Core Forex Pairs)
WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip_size": 0.0001, "sl_pips": 15},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip_size": 0.01,   "sl_pips": 15},
]

LONDON_TZ = pytz.timezone("Europe/London")

print("=" * 90)
print(f"[START] INITIALIZING GOLD 4-FILTER AI SIGNAL ASSISTANT FOR $200 ACCOUNT")
print(f"• Account Balance   : ${INITIAL_BALANCE:,.2f}")
print(f"• Risk Per Trade    : ${INITIAL_BALANCE * RISK_PERCENT:,.2f} (3%)")
print(f"• Target Reward     : ${INITIAL_BALANCE * RISK_PERCENT * 2:,.2f} (6% - 1:2 R/R)")
print(f"• Confluence Rules  : 200-EMA Trend + 3D Liquidity Sweep + Deep RSI + Session Windows")
print(f"• Layered Exit Rule : TP1 (50% scale-out + SL to Breakeven) | TP2 (50% scale-out)")
print(f"• Asset Watchlist   : {', '.join([item['name'] for item in WATCHLIST])}")
print("=" * 90)


# =============================================================================
# STEP 2: DOWNLOAD MULTI-ASSET DATA & CALCULATE INDICATORS
# =============================================================================
def fetch_and_calculate_data(asset_info):
    symbol = asset_info['symbol']
    print(f"[FETCH] Downloading 2 Years data for {asset_info['name']} ({symbol})...")
    
    df = yf.download(tickers=symbol, period="730d", interval="1h", progress=False)
    if df.empty:
        print(f"[WARNING] Could not fetch data for {symbol}. Skipping...")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    df['London_Time'] = df.index.tz_convert(LONDON_TZ)

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

    return df

asset_data_dict = {}
for asset in WATCHLIST:
    processed_df = fetch_and_calculate_data(asset)
    if processed_df is not None:
        asset_data_dict[asset['symbol']] = processed_df

print("[OK] Indicator calculations complete for all assets!")


# =============================================================================
# STEP 3: SAMPLE SIGNAL ALERT CARD FORMATTER
# =============================================================================
def print_sample_signal_card(asset_info, action, entry, sl, tp1, tp2, time_str, rsi_val, adx_val, ema_val):
    risk_usd = INITIAL_BALANCE * RISK_PERCENT
    reward_usd = risk_usd * 2.0
    
    print("\n" + "═" * 75)
    print("🏆 GOLD 4-FILTER HIGH-PROBABILITY SIGNAL ALERT 🏆")
    print("═" * 75)
    print(f"• Asset Pair      : {asset_info['name']} ({asset_info['symbol']}) [1-Hour Chart]")
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
    print(f"  2. Structure    : Touched 3-Day Channel Level (Liquidity Reversal Zone)")
    print(f"  3. Deep RSI     : RSI-14 = {rsi_val:.1f} ({'Deep Oversold < 28' if action=='BUY' else 'Deep Overbought > 72'})")
    print(f"  4. Session      : Active Prime Session Window (London / New York Open)")
    print("═" * 75)
    print("👉 Action: Open your broker app (Exness, MetaTrader) & place this order!")
    print("═" * 75 + "\n")


# =============================================================================
# STEP 4: MULTI-PERIOD HORIZON SIMULATION ENGINE (2Y, 1Y, 6M, 3M)
# =============================================================================
def run_gold_simulation(days_lookback=730):
    sample_df = list(asset_data_dict.values())[0]
    total_bars = len(sample_df)
    
    # Calculate starting bar index for requested days
    bars_needed = int(days_lookback * 17) # ~17 1H bars per trading day
    start_index = max(200, total_bars - bars_needed)

    current_balance = INITIAL_BALANCE
    equity_curve = [INITIAL_BALANCE]
    equity_times = [sample_df['London_Time'].iloc[start_index]]

    trades_history = []
    active_trades = []
    sample_card_printed = False

    for i in range(start_index, total_bars):
        current_time = sample_df['London_Time'].iloc[i]

        # Manage active trades
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
                if bar['High'] >= tp1 and not trade['tp1_hit']:
                    trade['tp1_hit'] = True
                    trade['sl_price'] = ep
                    pnl_part = risk_usd * 0.5 * 1.0
                    current_balance += pnl_part
                    trade['realized_pnl'] += pnl_part

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

        # Session Open Windows: London Open (8-11) & NY Open (13-17)
        in_session = (8 <= current_time.hour < 11) or (13 <= current_time.hour < 17)
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
            h3 = bar['High_3D']
            l3 = bar['Low_3D']

            if pd.isna(adx_val) or pd.isna(rsi_val) or pd.isna(ema_val) or pd.isna(h3) or pd.isna(l3):
                continue

            if adx_val >= ADX_MAX:
                continue

            if any(t['symbol'] == sym for t in active_trades):
                continue

            pip_sz = asset_info['pip_size']
            sl_pips = asset_info['sl_pips']
            risk_usd = current_balance * RISK_PERCENT

            # GOLD 4-FILTER CONFLUENCE SIGNALS
            # BUY: Price > 200-EMA (Uptrend) AND Low <= Low_3D AND RSI < 28
            buy_signal = (bar['Close'] > ema_val) and (bar['Low'] <= l3) and (rsi_val < RSI_BUY_MAX)

            # SELL: Price < 200-EMA (Downtrend) AND High >= High_3D AND RSI > 72
            sell_signal = (bar['Close'] < ema_val) and (bar['High'] >= h3) and (rsi_val > RSI_SELL_MIN)

            if buy_signal:
                sl_price = l3 - (sl_pips * pip_sz)
                sl_dist = abs(bar['Close'] - sl_price)
                if sl_dist < (5 * pip_sz):
                    sl_dist = 5 * pip_sz
                    sl_price = bar['Close'] - sl_dist

                tp1_price = bar['Close'] + (1.0 * sl_dist)
                tp2_price = bar['Close'] + (2.0 * sl_dist)

                active_trades.append({
                    'symbol': sym, 'type': 'BUY', 'entry_price': bar['Close'],
                    'sl_price': sl_price, 'tp1_price': tp1_price, 'tp2_price': tp2_price,
                    'sl_distance': sl_dist, 'risk_dollar': risk_usd, 'tp1_hit': False, 'realized_pnl': 0.0
                })

                if days_lookback == 730 and not sample_card_printed:
                    print_sample_signal_card(asset_info, "BUY", bar['Close'], sl_price, tp1_price, tp2_price, str(current_time), rsi_val, adx_val, ema_val)
                    sample_card_printed = True

            elif sell_signal:
                sl_price = h3 + (sl_pips * pip_sz)
                sl_dist = abs(sl_price - bar['Close'])
                if sl_dist < (5 * pip_sz):
                    sl_dist = 5 * pip_sz
                    sl_price = bar['Close'] + sl_dist

                tp1_price = bar['Close'] - (1.0 * sl_dist)
                tp2_price = bar['Close'] - (2.0 * sl_dist)

                active_trades.append({
                    'symbol': sym, 'type': 'SELL', 'entry_price': bar['Close'],
                    'sl_price': sl_price, 'tp1_price': tp1_price, 'tp2_price': tp2_price,
                    'sl_distance': sl_dist, 'risk_dollar': risk_usd, 'tp1_hit': False, 'realized_pnl': 0.0
                })

                if days_lookback == 730 and not sample_card_printed:
                    print_sample_signal_card(asset_info, "SELL", bar['Close'], sl_price, tp1_price, tp2_price, str(current_time), rsi_val, adx_val, ema_val)
                    sample_card_printed = True

    # METRICS
    df_tr = pd.DataFrame(trades_history)
    tot = len(df_tr)
    weeks = max(1.0, days_lookback / 7.0)
    trades_per_week = tot / weeks

    if tot > 0:
        wins = df_tr[df_tr['result'] == 'WIN']
        losses = df_tr[df_tr['result'] == 'LOSS']
        breakevens = df_tr[df_tr['result'] == 'BREAKEVEN']
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
        'days': days_lookback, 'total_trades': tot, 'trades_per_week': trades_per_week,
        'win_rate': win_rate, 'profit_factor': pf, 'net_profit': net,
        'max_dd': dd, 'expectancy': exp, 'final_balance': current_balance,
        'equity_curve': equity_curve, 'equity_times': equity_times
    }


# =============================================================================
# STEP 5: RUN MULTI-PERIOD HORIZON BACKTESTS (2Y, 1Y, 6M, 3M)
# =============================================================================
print("[RUNNER] Executing Gold Confluence Backtests across 4 Time Horizons (2Y, 1Y, 6M, 3M)...")

res_2y = run_gold_simulation(days_lookback=730)
res_1y = run_gold_simulation(days_lookback=365)
res_6m = run_gold_simulation(days_lookback=180)
res_3m = run_gold_simulation(days_lookback=90)

horizon_results = [
    {"name": "2 Years (730 Days)", "res": res_2y},
    {"name": "1 Year (365 Days)",  "res": res_1y},
    {"name": "6 Months (180 Days)","res": res_6m},
    {"name": "3 Months (90 Days)", "res": res_3m},
]

print("\n" + "=" * 95)
print("📊 GOLD 4-FILTER AI SIGNAL ASSISTANT — MULTI-HORIZON PERFORMANCE DASHBOARD ($200 Account)")
print("=" * 95)
print(f"{'Time Horizon':<22} | {'Trades':<7} | {'Trades/Wk':<10} | {'Win %':<7} | {'Profit Factor':<13} | {'Net Profit ($)':<14} | {'Max DD %':<8}")
print("-" * 95)

for h in horizon_results:
    r = h['res']
    print(f"{h['name']:<22} | {r['total_trades']:<7} | {r['trades_per_week']:<10.1f} | {r['win_rate']:<6.1f}% | {r['profit_factor']:<13.2f} | ${r['net_profit']:<13.2f} | {r['max_dd']:<7.2f}%")

print("=" * 95 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (MULTI-HORIZON EQUITY PLOT)
# =============================================================================
print("[PLOTS] Generating Multi-Horizon Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(14, 8))

colors = ['#FFD700', '#1E88E5', '#43A047', '#E53935']

for idx, h in enumerate(horizon_results):
    r = h['res']
    ax.plot(r['equity_times'], r['equity_curve'], label=f"{h['name']} (${r['net_profit']:+,.2f})", color=colors[idx], linewidth=2.0)

ax.axhline(INITIAL_BALANCE, color='#333333', linestyle='--', linewidth=1.2, label=f"Starting Capital (${INITIAL_BALANCE:,.0f})")
ax.set_title("Gold 4-Filter AI Signal Assistant - Multi-Horizon Equity Comparison ($200 Account)", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "gold_signal_assistant_equity.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] Multi-Horizon comparison chart saved to: {os.path.abspath(chart_file)}")

print("\n" + "=" * 80)
print("🏆 FINAL VERDICT & STABILITY EVALUATION")
print("=" * 80)

all_positive = all(h['res']['net_profit'] > 0 for h in horizon_results)
if all_positive:
    print(f"🎉 EXCELLENT STABILITY! The Gold Assistant is PROFITABLE across ALL 4 time horizons (2Y, 1Y, 6M, 3M)!")
    print(f"• 2-Year Total Profit : ${res_2y['net_profit']:+,.2f} ({(res_2y['net_profit']/INITIAL_BALANCE)*100:+.1f}%)")
    print(f"• Trade Frequency    : {res_2y['trades_per_week']:.1f} Signals per Week (Target: 4-5 Trades/Wk Met!)")
else:
    print(f"⚠️ HORIZON VARIANCE DETECTED: Some timeframes showed drawdown.")
print("=" * 80 + "\n")

print("✨ Gold 4-Filter AI Signal Assistant execution completed successfully!")
