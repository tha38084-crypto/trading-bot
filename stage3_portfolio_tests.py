"""
===============================================================================
TRADING BOT - STAGE 3: 4-TEST PORTFOLIO & STRATEGY OPTIMIZER
===============================================================================
Goal: Backtest and compare 4 distinct trading models over 2 Years (730 Days):
      - TEST 1: Forex Fader (EUR/USD 1:2 R/R)
      - TEST 2: Forex Fader (EUR/USD 1:3.5 R/R)
      - TEST 3: Crypto Momentum (BTC-USD 1:3 R/R)
      - TEST 4: Combined Multi-Asset Portfolio (50% Forex Fader + 50% Crypto Momentum)

Target Audience: Non-coders (heavily documented in plain English).
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
INITIAL_BALANCE = 10000.0   # $10,000 Starting Account Capital
LONDON_TZ = pytz.timezone("Europe/London")

print("=" * 90)
print(f"[START] INITIALIZING 4-TEST PORTFOLIO & STRATEGY EXPERIMENTS")
print(f"• Initial Capital  : ${INITIAL_BALANCE:,.2f}")
print(f"• Backtest Period  : 2 Years (730 Days)")
print("=" * 90)


# =============================================================================
# STEP 2: DOWNLOAD 2-YEAR MARKET DATA FOR FOREX & CRYPTO
# =============================================================================
print("[FETCH] Downloading 2 Years (730 Days) of 1-Hour data for EURUSD=X and BTC-USD...")

df_forex = yf.download(tickers="EURUSD=X", period="730d", interval="1h", progress=False)
df_crypto = yf.download(tickers="BTC-USD", period="730d", interval="1h", progress=False)

if df_forex.empty or df_crypto.empty:
    raise ValueError("[ERROR] Could not fetch market data for EURUSD=X or BTC-USD.")

# Clean MultiIndex columns
for df_item in [df_forex, df_crypto]:
    if isinstance(df_item.columns, pd.MultiIndex):
        df_item.columns = df_item.columns.get_level_values(0)
    if df_item.index.tzinfo is None:
        df_item.index = df_item.index.tz_localize('UTC')
    else:
        df_item.index = df_item.index.tz_convert('UTC')
    df_item['London_Time'] = df_item.index.tz_convert(LONDON_TZ)

print(f"[OK] Downloaded {len(df_forex)} Forex candles and {len(df_crypto)} Crypto candles!")


# =============================================================================
# STEP 3: CALCULATE INDICATORS FOR FOREX & CRYPTO
# =============================================================================
def add_indicators(df, is_forex=True):
    # 200-EMA
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # RSI-14
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=14, adjust=False).mean()
    avg_loss = loss.ewm(span=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # ATR-14
    high_low = df['High'] - df['Low']
    high_close_prev = (df['High'] - df['Close'].shift(1)).abs()
    low_close_prev = (df['Low'] - df['Close'].shift(1)).abs()
    df['True_Range'] = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    df['ATR_14'] = df['True_Range'].ewm(span=14, adjust=False).mean()
    
    # ADX-14
    high_diff = df['High'] - df['High'].shift(1)
    low_diff = df['Low'].shift(1) - df['Low']
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    atr_series = df['True_Range'].ewm(span=14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr_series)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df['ADX_14'] = dx.ewm(span=14, adjust=False).mean()
    
    # 5-Day High & Low (120 1-hour candles lookback)
    df['High_5D'] = df['High'].shift(1).rolling(window=120).max()
    df['Low_5D'] = df['Low'].shift(1).rolling(window=120).min()
    
    return df

df_forex = add_indicators(df_forex, is_forex=True)
df_crypto = add_indicators(df_crypto, is_forex=False)


# =============================================================================
# STEP 4: REUSABLE BACKTEST ENGINE FOR FOREX FADER & CRYPTO MOMENTUM
# =============================================================================
def run_single_backtest(df_input, mode="FADER", rr_ratio=2.0, risk_pct=0.02, pip_size=0.0001):
    current_balance = INITIAL_BALANCE
    equity_curve = [INITIAL_BALANCE]
    equity_times = [df_input['London_Time'].iloc[0]]
    
    trades = []
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
            sl_dist = active_trade['sl_distance']
            tp_p = active_trade['tp_price']
            
            if t_type == "BUY":
                if row['High'] >= entry_p + sl_dist and active_trade['trailing_stage'] < 1:
                    active_trade['sl_price'] = entry_p
                    active_trade['trailing_stage'] = 1
                if row['High'] >= entry_p + (1.5 * sl_dist) and active_trade['trailing_stage'] < 2:
                    active_trade['sl_price'] = entry_p + (0.75 * sl_dist)
                    active_trade['trailing_stage'] = 2
                    
                if row['High'] >= tp_p:
                    pnl = risk_dollar * rr_ratio
                    current_balance += pnl
                    trades.append({'result': 'WIN', 'pnl': pnl, 'time': candle_time})
                    in_position = False
                    active_trade = None
                elif row['Low'] <= active_trade['sl_price']:
                    pnl = ((active_trade['sl_price'] - entry_p) / sl_dist) * risk_dollar
                    current_balance += pnl
                    res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                    trades.append({'result': res, 'pnl': pnl, 'time': candle_time})
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
                    trades.append({'result': 'WIN', 'pnl': pnl, 'time': candle_time})
                    in_position = False
                    active_trade = None
                elif row['High'] >= active_trade['sl_price']:
                    pnl = ((entry_p - active_trade['sl_price']) / sl_dist) * risk_dollar
                    current_balance += pnl
                    res = 'WIN' if pnl > 0 else ('BREAKEVEN' if pnl == 0 else 'LOSS')
                    trades.append({'result': res, 'pnl': pnl, 'time': candle_time})
                    in_position = False
                    active_trade = None

        equity_curve.append(current_balance)
        equity_times.append(candle_time)
        
        # ENTRY LOGIC
        if not in_position:
            if mode == "FADER":
                # Forex Fader: Fade 5D High/Low, RSI >70/<30, ADX <25 (Ranging)
                f_buy = not pd.isna(row['Low_5D']) and row['Low'] <= row['Low_5D'] and row['RSI_14'] < 30.0 and row['ADX_14'] < 25.0
                f_sell = not pd.isna(row['High_5D']) and row['High'] >= row['High_5D'] and row['RSI_14'] > 70.0 and row['ADX_14'] < 25.0
                
                if f_buy:
                    sl_dist = max(1.5 * row['ATR_14'], 10 * pip_size)
                    risk_dollar = current_balance * risk_pct
                    in_position = True
                    active_trade = {'type': 'BUY', 'entry_price': row['Close'], 'sl_price': row['Close'] - sl_dist, 'tp_price': row['Close'] + (rr_ratio * sl_dist), 'sl_distance': sl_dist, 'risk_dollar': risk_dollar, 'trailing_stage': 0}
                elif f_sell:
                    sl_dist = max(1.5 * row['ATR_14'], 10 * pip_size)
                    risk_dollar = current_balance * risk_pct
                    in_position = True
                    active_trade = {'type': 'SELL', 'entry_price': row['Close'], 'sl_price': row['Close'] + sl_dist, 'tp_price': row['Close'] - (rr_ratio * sl_dist), 'sl_distance': sl_dist, 'risk_dollar': risk_dollar, 'trailing_stage': 0}

            elif mode == "MOMENTUM":
                # Crypto Momentum: Trade 5D High/Low Breakout, RSI >55/<45, ADX >30 (Trending)
                m_buy = not pd.isna(row['High_5D']) and row['Close'] > row['High_5D'] and row['RSI_14'] > 55.0 and row['ADX_14'] > 30.0
                m_sell = not pd.isna(row['Low_5D']) and row['Close'] < row['Low_5D'] and row['RSI_14'] < 45.0 and row['ADX_14'] > 30.0
                
                if m_buy:
                    sl_dist = max(1.5 * row['ATR_14'], 10 * pip_size)
                    risk_dollar = current_balance * risk_pct
                    in_position = True
                    active_trade = {'type': 'BUY', 'entry_price': row['Close'], 'sl_price': row['Close'] - sl_dist, 'tp_price': row['Close'] + (rr_ratio * sl_dist), 'sl_distance': sl_dist, 'risk_dollar': risk_dollar, 'trailing_stage': 0}
                elif m_sell:
                    sl_dist = max(1.5 * row['ATR_14'], 10 * pip_size)
                    risk_dollar = current_balance * risk_pct
                    in_position = True
                    active_trade = {'type': 'SELL', 'entry_price': row['Close'], 'sl_price': row['Close'] + sl_dist, 'tp_price': row['Close'] - (rr_ratio * sl_dist), 'sl_distance': sl_dist, 'risk_dollar': risk_dollar, 'trailing_stage': 0}

    # Metrics
    df_tr = pd.DataFrame(trades)
    tot = len(df_tr)
    if tot > 0:
        wins = df_tr[df_tr['result'] == 'WIN']
        losses = df_tr[df_tr['result'] == 'LOSS']
        win_rate = (len(wins) / tot) * 100
        gp = wins['pnl'].sum() if not wins.empty else 0.0
        gl = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        net = current_balance - INITIAL_BALANCE
        pf = (gp / gl) if gl > 0 else (gp if gp > 0 else 0.0)
        eq_ser = pd.Series(equity_curve)
        run_max = eq_ser.cummax()
        dd = abs(((eq_ser - run_max) / run_max).min()) * 100
        exp = net / tot
    else:
        win_rate = gp = gl = net = pf = dd = exp = 0.0

    return {
        'total_trades': tot, 'win_rate': win_rate, 'profit_factor': pf,
        'net_profit': net, 'max_dd': dd, 'expectancy': exp,
        'final_balance': current_balance, 'equity_curve': equity_curve,
        'equity_times': equity_times, 'trades': trades
    }


# =============================================================================
# STEP 5: RUN TESTS 1, 2, 3 AND COMBINED TEST 4
# =============================================================================
print("[RUNNER] Executing Backtests for Tests 1, 2, 3, and Combined Test 4...")

# TEST 1: Forex Fader (1:2 R/R)
t1 = run_single_backtest(df_forex, mode="FADER", rr_ratio=2.0, risk_pct=0.02, pip_size=0.0001)

# TEST 2: Forex Fader (1:3.5 R/R)
t2 = run_single_backtest(df_forex, mode="FADER", rr_ratio=3.5, risk_pct=0.02, pip_size=0.0001)

# TEST 3: Crypto Momentum (1:3 R/R)
t3 = run_single_backtest(df_crypto, mode="MOMENTUM", rr_ratio=3.0, risk_pct=0.02, pip_size=1.0)

# TEST 4: Combined Portfolio (50% Forex Fader 1:3.5 + 50% Crypto Momentum, 1% risk each)
t4_forex = run_single_backtest(df_forex, mode="FADER", rr_ratio=3.5, risk_pct=0.01, pip_size=0.0001)
t4_crypto = run_single_backtest(df_crypto, mode="MOMENTUM", rr_ratio=3.0, risk_pct=0.01, pip_size=1.0)

# Aggregate Test 4 Combined Portfolio Equity Curve
min_len = min(len(t4_forex['equity_curve']), len(t4_crypto['equity_curve']))
comb_equity = [ (t4_forex['equity_curve'][k] + t4_crypto['equity_curve'][k]) / 2.0 for k in range(min_len) ]
comb_times = t4_forex['equity_times'][:min_len]

comb_net = comb_equity[-1] - INITIAL_BALANCE
comb_tot = t4_forex['total_trades'] + t4_crypto['total_trades']
comb_win_rate = (t4_forex['win_rate'] + t4_crypto['win_rate']) / 2.0 if comb_tot > 0 else 0.0

eq_ser4 = pd.Series(comb_equity)
run_max4 = eq_ser4.cummax()
comb_dd = abs(((eq_ser4 - run_max4) / run_max4).min()) * 100

comb_gp = (t4_forex['net_profit'] if t4_forex['net_profit'] > 0 else 0) + (t4_crypto['net_profit'] if t4_crypto['net_profit'] > 0 else 0)
comb_gl = abs((t4_forex['net_profit'] if t4_forex['net_profit'] < 0 else 0) + (t4_crypto['net_profit'] if t4_crypto['net_profit'] < 0 else 0))
comb_pf = (comb_gp / comb_gl) if comb_gl > 0 else (comb_gp if comb_gp > 0 else 0.0)
comb_exp = comb_net / comb_tot if comb_tot > 0 else 0.0

t4 = {
    'total_trades': comb_tot, 'win_rate': comb_win_rate, 'profit_factor': comb_pf,
    'net_profit': comb_net, 'max_dd': comb_dd, 'expectancy': comb_exp,
    'final_balance': comb_equity[-1], 'equity_curve': comb_equity, 'equity_times': comb_times
}


# =============================================================================
# STEP 6: COMPARISON DASHBOARD & RECOMMENDATION
# =============================================================================
test_results = [
    {"name": "Test 1: Forex Fader (1:2 R/R)", "res": t1},
    {"name": "Test 2: Forex Fader (1:3.5 R/R)", "res": t2},
    {"name": "Test 3: Crypto Momentum (1:3 R/R)", "res": t3},
    {"name": "Test 4: Combined Portfolio (50/50)", "res": t4},
]

print("\n" + "=" * 95)
print("📊 2-YEAR EXPERIMENTS COMPARISON DASHBOARD")
print("=" * 95)
print(f"{'Test Name':<38} | {'Trades':<7} | {'Win %':<7} | {'Profit Factor':<13} | {'Net Profit ($)':<14} | {'Max DD %':<8} | {'Expectancy ($)':<12}")
print("-" * 95)

best_test = test_results[0]
for tr in test_results:
    r = tr['res']
    if r['net_profit'] > best_test['res']['net_profit']:
        best_test = tr
    print(f"{tr['name']:<38} | {r['total_trades']:<7} | {r['win_rate']:<6.1f}% | {r['profit_factor']:<13.2f} | ${r['net_profit']:<13.2f} | {r['max_dd']:<7.2f}% | ${r['expectancy']:<11.2f}")

print("=" * 95 + "\n")

# =============================================================================
# STEP 7: VISUAL PLOT GENERATION
# =============================================================================
print("[PLOTS] Generating Multi-Strategy Equity Curve Comparison Chart...")

fig, ax = plt.subplots(figsize=(14, 8))

colors = ['#E53935', '#FB8C00', '#1E88E5', '#43A047']

for idx, tr in enumerate(test_results):
    r = tr['res']
    ax.plot(r['equity_times'], r['equity_curve'], label=f"{tr['name']} (${r['net_profit']:+,.2f})", color=colors[idx], linewidth=2.2 if tr == best_test else 1.5)

ax.axhline(INITIAL_BALANCE, color='#333333', linestyle='--', linewidth=1.2, label=f"Starting Capital (${INITIAL_BALANCE:,.0f})")
ax.set_title("2-Year Strategy Experiments - Account Equity Curve Comparison", fontsize=14, fontweight='bold')
ax.set_ylabel("Account Balance (USD)", fontsize=12)
ax.set_xlabel("Date (2024 - 2026)", fontsize=12)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
plt.tight_layout()

chart_name = "stage3_portfolio_comparison.png"
plt.savefig(chart_name, dpi=150)
print(f"[SAVE] Multi-Strategy comparison chart saved to: {os.path.abspath(chart_name)}")

print("\n" + "=" * 80)
print("🏆 FINAL STRATEGY RECOMMENDATION")
print("=" * 80)
print(f"• WINNING MODEL         : {best_test['name']}")
print(f"• Total Net Profit      : ${best_test['res']['net_profit']:+,.2f}")
print(f"• Profit Factor         : {best_test['res']['profit_factor']:.2f}")
print(f"• Win Rate              : {best_test['res']['win_rate']:.1f}% ({best_test['res']['total_trades']} Trades)")
print(f"• Max Drawdown          : {best_test['res']['max_dd']:.2f}%")
print(f"• Expectancy per Trade  : ${best_test['res']['expectancy']:+,.2f}")
print("=" * 80 + "\n")

print("✨ 4-Test Portfolio & Strategy Experiments completed successfully!")
