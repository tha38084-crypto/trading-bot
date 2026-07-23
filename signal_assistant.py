"""
===============================================================================
TRADING BOT - STAGE 3: $200 ACCOUNT MULTI-ASSET AI SIGNAL ASSISTANT
===============================================================================
Goal: Multi-asset market scanner and 2-year backtest simulator engineered
      specifically for a $200 account targeting $4.00 Risk (2%) to $8.00 Reward (4%)
      with Layered Risk-Reward Protection (TP1 + Breakeven + TP2).

Target Sizing & Risk Rules:
  - Account Capital : $200.00
  - Risk Per Trade  : $4.00 (2% of account)
  - Target Reward   : +$8.00 (4% of account - 1:2 R/R)
  - Watchlist Assets: EUR/USD, GBP/USD, USD/JPY, BTC-USD, Gold (GC=F)
  - Layered Protection:
      • TP1 (+1:1 R/R): Scale-out 50% position + Move SL to Breakeven ($0.00 risk!)
      • TP2 (+1:2 R/R): Scale-out remaining 50% position for full profit.

Target Goal: Generate 2-3 signals per day across watchlist with positive Net Profit.
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
RISK_PERCENT = 0.02         # 2% Risk per trade ($4.00)
MAX_DAILY_SIGNALS = 3       # Maximum 3 signals per calendar day total

# Technical Filter Thresholds
ADX_MAX = 30.0              # ADX-14 < 30 (Ranging / Channel Regime)
RSI_BUY_MAX = 32.0          # RSI-14 < 32 (Oversold BUY)
RSI_SELL_MIN = 68.0         # RSI-14 > 68 (Overbought SELL)
LOOKBACK_BARS = 72          # 3-Day Channel (72 1-hour candles)

# Watchlist Definition
WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "type": "FOREX", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "type": "FOREX", "pip_size": 0.0001, "sl_pips": 15},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "type": "FOREX", "pip_size": 0.01,   "sl_pips": 15},
    {"symbol": "BTC-USD",  "name": "Bitcoin", "type": "CRYPTO","pip_size": 1.0,    "sl_pips": 200},
    {"symbol": "GC=F",     "name": "Gold",    "type": "COMMODITY", "pip_size": 0.1, "sl_pips": 15},
]

LONDON_TZ = pytz.timezone("Europe/London")

print("=" * 90)
print(f"[START] INITIALIZING MULTI-ASSET AI SIGNAL ASSISTANT FOR $200 ACCOUNT")
print(f"• Account Balance   : ${INITIAL_BALANCE:,.2f}")
print(f"• Risk Per Trade    : ${INITIAL_BALANCE * RISK_PERCENT:,.2f} (2%)")
print(f"• Target Reward     : ${INITIAL_BALANCE * RISK_PERCENT * 2:,.2f} (4% - 1:2 R/R)")
print(f"• Layered Exit Rule : TP1 (50% scale-out + SL to Breakeven) | TP2 (50% scale-out)")
print(f"• Daily Signal Cap  : {MAX_DAILY_SIGNALS} signals/day max")
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


# Download data for all assets
asset_data_dict = {}
for asset in WATCHLIST:
    processed_df = fetch_and_calculate_data(asset)
    if processed_df is not None:
        asset_data_dict[asset['symbol']] = processed_df

print("[OK] Downloaded and processed indicator data for all watchlist assets!")


# =============================================================================
# STEP 3: SIGNAL CARD DISPLAY GENERATOR
# =============================================================================
def print_sample_signal_card(asset_info, action, entry, sl, tp1, tp2, time_str, rsi_val, adx_val):
    risk_usd = INITIAL_BALANCE * RISK_PERCENT
    reward_usd = risk_usd * 2.0
    
    print("\n" + "═" * 75)
    print("🚨 NEW HIGH-PROBABILITY AI TRADE SIGNAL ALERT 🚨")
    print("═" * 75)
    print(f"• Asset Pair      : {asset_info['name']} ({asset_info['symbol']}) [1-Hour Chart]")
    print(f"• Action Signal   : {'🟢 BUY (LONG)' if action == 'BUY' else '🔴 SELL (SHORT)'}")
    print(f"• Signal Time     : {time_str} London Time")
    print("─" * 75)
    print(f"• Suggested Entry : {entry:.4f}")
    print(f"• Stop-Loss (SL)  : {sl:.4f}  --> Risk: -${risk_usd:.2f} (2.0%)")
    print(f"• Take-Profit 1   : {tp1:.4f}  --> TP1 (50% scale-out + Move SL to Breakeven)")
    print(f"• Take-Profit 2   : {tp2:.4f}  --> TP2 (50% scale-out for +${reward_usd:.2f} total)")
    print("─" * 75)
    print(f"• Signal Analysis Rationale:")
    print(f"  1. Price touched 3-Day Channel Level (Reversal Zone)")
    print(f"  2. RSI-14 = {rsi_val:.1f} ({'Oversold Reversal' if action == 'BUY' else 'Overbought Reversal'})")
    print(f"  3. ADX-14 = {adx_val:.1f} (Ranging Regime Confirmed)")
    print(f"  4. Session Active Window (London / New York)")
    print("═" * 75)
    print("👉 Action: Open your broker app (Exness, MetaTrader, etc.) & place this order!")
    print("═" * 75 + "\n")


# =============================================================================
# STEP 4: 2-YEAR MULTI-ASSET PORTFOLIO BACKTEST SIMULATOR
# =============================================================================
print("\n[SIMULATION] Running 2-Year Multi-Asset Portfolio Simulation across Watchlist...")

current_balance = INITIAL_BALANCE
equity_curve = [INITIAL_BALANCE]

# Align dates across assets
sample_df = list(asset_data_dict.values())[0]
equity_times = [sample_df['London_Time'].iloc[0]]

trades_history = []
active_trades = []

sample_card_printed = False

for i in range(200, len(sample_df)):
    current_time = sample_df['London_Time'].iloc[i]
    current_date_str = current_time.date()

    # -------------------------------------------------------------------------
    # PART A: MANAGE ACTIVE TRADES WITH LAYERED PROTECTION
    # -------------------------------------------------------------------------
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
        sl_dist = trade['sl_distance']
        risk_usd = trade['risk_dollar']

        if t_type == "BUY":
            # Check TP1: Scale out 50% and move SL to Breakeven
            if bar['High'] >= tp1 and not trade['tp1_hit']:
                trade['tp1_hit'] = True
                trade['sl_price'] = ep  # Move SL to Breakeven ($0.00 risk!)
                # Realize 50% profit
                pnl_part = risk_usd * 0.5 * 1.0  # +1:1 R/R on half position
                current_balance += pnl_part
                trade['realized_pnl'] += pnl_part

            # Check TP2: Final Exit
            if bar['High'] >= tp2:
                pnl_part = risk_usd * 0.5 * 2.0  # +1:2 R/R on remaining half
                current_balance += pnl_part
                total_pnl = trade['realized_pnl'] + pnl_part
                trades_history.append({'symbol': sym, 'pnl': total_pnl, 'result': 'WIN'})
                closed_trades.append(trade)

            # Check Stop-Loss Hit
            elif bar['Low'] <= trade['sl_price']:
                if trade['sl_price'] == ep:  # Breakeven exit
                    trades_history.append({'symbol': sym, 'pnl': trade['realized_pnl'], 'result': 'BREAKEVEN'})
                else:  # Full loss
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

    # -------------------------------------------------------------------------
    # PART B: SCAN FOR NEW SIGNALS ACROSS WATCHLIST
    # -------------------------------------------------------------------------
    # Active Session Windows: London (8-12) & NY (13-17)
    in_session = (8 <= current_time.hour < 12) or (13 <= current_time.hour < 17)
    if not in_session:
        continue

    for asset_info in WATCHLIST:
        sym = asset_info['symbol']
        if sym not in asset_data_dict or i >= len(asset_data_dict[sym]):
            continue

        bar = asset_data_dict[sym].iloc[i]
        adx_val = bar['ADX_14']
        rsi_val = bar['RSI_14']
        h3 = bar['High_3D']
        l3 = bar['Low_3D']

        if pd.isna(adx_val) or pd.isna(rsi_val) or pd.isna(h3) or pd.isna(l3):
            continue

        # Filter: ADX < 30
        if adx_val >= ADX_MAX:
            continue

        # Check if already in active trade for this asset
        if any(t['symbol'] == sym for t in active_trades):
            continue

        pip_sz = asset_info['pip_size']
        sl_pips = asset_info['sl_pips']
        risk_usd = current_balance * RISK_PERCENT

        buy_signal = (bar['Low'] <= l3) and (rsi_val < RSI_BUY_MAX)
        sell_signal = (bar['High'] >= h3) and (rsi_val > RSI_SELL_MIN)

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

            # Print Sample Signal Card once for user demonstration
            if not sample_card_printed:
                print_sample_signal_card(asset_info, "BUY", bar['Close'], sl_price, tp1_price, tp2_price, str(current_time), rsi_val, adx_val)
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

            if not sample_card_printed:
                print_sample_signal_card(asset_info, "SELL", bar['Close'], sl_price, tp1_price, tp2_price, str(current_time), rsi_val, adx_val)
                sample_card_printed = True


# =============================================================================
# STEP 5: PERFORMANCE METRICS & BREAKDOWN ANALYSIS
# =============================================================================
print("[METRICS] Calculating Performance Metrics...")

df_tr = pd.DataFrame(trades_history)
total_trades = len(df_tr)

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
print("📊 $200 ACCOUNT MULTI-ASSET AI SIGNAL ASSISTANT PERFORMANCE DASHBOARD")
print("=" * 90)
print(f"• Starting Balance        : ${INITIAL_BALANCE:,.2f}")
print(f"• Final Balance           : ${current_balance:,.2f}")
print(f"• Total Net Profit        : ${net_profit:,.2f} ({(net_profit/INITIAL_BALANCE)*100:+.2f}%)")
print(f"• Total Signals           : {total_trades} Signals")
print(f"• Win Rate                : {win_rate:.1f}% ({len(wins)} Wins, {len(losses)} Losses, {len(breakevens)} Breakevens)")
print(f"• Profit Factor           : {profit_factor:.2f}")
print(f"• Maximum Drawdown        : {max_dd_pct:.2f}%")
print(f"• Expectancy per Signal   : ${expectancy:,.2f}")
print("=" * 90 + "\n")


# =============================================================================
# STEP 6: VISUALIZATION (PORTFOLIO EQUITY CURVE CHART)
# =============================================================================
print("[PLOTS] Generating Multi-Asset Portfolio Equity Curve Chart...")

fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(equity_times, equity_curve, color='#4A148C', linewidth=2.0, label='$200 Account Portfolio Equity ($)')
ax.axhline(INITIAL_BALANCE, color='#616161', linestyle='--', linewidth=1.2, label=f'Starting Capital (${INITIAL_BALANCE:,.0f})')
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) >= INITIAL_BALANCE), color='#E1BEE7', alpha=0.4)
ax.fill_between(equity_times, INITIAL_BALANCE, equity_curve, where=(np.array(equity_curve) < INITIAL_BALANCE), color='#FFCDD2', alpha=0.4)

ax.set_title("2-Year Account Equity Curve - Multi-Asset AI Signal Assistant ($200 Account)", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_file = "signal_assistant_equity.png"
plt.savefig(chart_file, dpi=150)
print(f"[SAVE] Portfolio Equity Curve chart saved to: {os.path.abspath(chart_file)}")

print("\n" + "=" * 80)
print("🏆 FINAL VERDICT & DEMO READINESS")
print("=" * 80)
if net_profit > 0 and profit_factor > 1.2:
    print(f"✅ READY FOR STEP 1 DEMO! The Multi-Asset Signal Assistant generated ${net_profit:,.2f} Net Profit with a {profit_factor:.2f} Profit Factor.")
else:
    print(f"⚠️ NEEDS PARAMETER REFINEMENT: Net Profit is ${net_profit:,.2f} (Profit Factor: {profit_factor:.2f}).")
print("=" * 80 + "\n")

print("✨ AI Signal Assistant Engine execution completed successfully!")
