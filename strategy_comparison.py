"""
===============================================================================
STRATEGY COMPARISON MASTER RUNNER
===============================================================================
Runs both strategies head-to-head on 2 Years (730 Days) of EUR/USD data
and produces a side-by-side comparison table + dual equity curve chart.

Strategy A: Refined Forex Fader  (improved from our profitable Test 1)
Strategy B: SMC Order Block Engine (new institutional Smart Money approach)

Run this file to see the full comparison:
    python strategy_comparison.py
===============================================================================
"""

import sys
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pytz

# Import both strategy modules
from strategy_a_refined_fader import run_strategy_a
from strategy_b_smc_engine import run_strategy_b

TICKER          = "EURUSD=X"
INITIAL_BALANCE = 10_000.0

# =============================================================================
# STEP 1: DOWNLOAD SHARED DATA (one download, two strategies)
# =============================================================================
print("=" * 75)
print("  STRATEGY BATTLE: REFINED FOREX FADER  vs  SMC ORDER BLOCK ENGINE")
print("  Asset: EURUSD=X  |  Period: 2 Years (730 Days)  |  Interval: 1H")
print("=" * 75)
print("\n[FETCH] Downloading 2-Year 1H EUR/USD data from Yahoo Finance...")

raw = yf.download(tickers=TICKER, period="730d", interval="1h", progress=False)
if raw.empty:
    raise ValueError("[ERROR] Could not download EUR/USD data. Check your internet connection.")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(0)

print(f"[OK] Downloaded {len(raw):,} 1-Hour candles.\n")

# =============================================================================
# STEP 2: RUN BOTH STRATEGIES
# =============================================================================
print("[RUN A] Executing Strategy A — Refined Forex Fader...")
result_a = run_strategy_a(raw.copy())
print(f"       Done. Trades: {result_a['total_trades']}  |  Net Profit: ${result_a['net_profit']:,.2f}\n")

print("[RUN B] Executing Strategy B — SMC Order Block Engine...")
result_b = run_strategy_b(raw.copy())
print(f"       Done. Trades: {result_b['total_trades']}  |  Net Profit: ${result_b['net_profit']:,.2f}\n")

# =============================================================================
# STEP 3: HEAD-TO-HEAD COMPARISON TABLE
# =============================================================================
def status_label(net):
    if net > 0:
        return "PROFITABLE"
    elif net == 0:
        return "BREAKEVEN"
    else:
        return "LOSS"

results = [result_a, result_b]

print("=" * 78)
print("  STRATEGY COMPARISON — 2-YEAR BACKTEST RESULTS")
print("=" * 78)

header = f"{'Metric':<26} | {'Strategy A: Fader':>22} | {'Strategy B: SMC':>22}"
print(header)
print("-" * 78)

metrics = [
    ("Total Trades",        f"{result_a['total_trades']}",                     f"{result_b['total_trades']}"),
    ("Win Rate (%)",        f"{result_a['win_rate']:.1f}%",                    f"{result_b['win_rate']:.1f}%"),
    ("Profit Factor",       f"{result_a['profit_factor']:.2f}",                f"{result_b['profit_factor']:.2f}"),
    ("Net Profit ($)",      f"${result_a['net_profit']:,.2f}",                 f"${result_b['net_profit']:,.2f}"),
    ("Final Balance ($)",   f"${result_a['final_balance']:,.2f}",              f"${result_b['final_balance']:,.2f}"),
    ("Max Drawdown (%)",    f"{result_a['max_drawdown']:.2f}%",                f"{result_b['max_drawdown']:.2f}%"),
    ("Expectancy ($/trade)",f"${result_a['expectancy']:,.2f}",                 f"${result_b['expectancy']:,.2f}"),
    ("Return on $10k (%)",  f"{result_a['net_profit']/INITIAL_BALANCE*100:+.1f}%", f"{result_b['net_profit']/INITIAL_BALANCE*100:+.1f}%"),
    ("Overall Status",      status_label(result_a['net_profit']),              status_label(result_b['net_profit'])),
]

for name, val_a, val_b in metrics:
    print(f"  {name:<24} | {val_a:>22} | {val_b:>22}")

print("=" * 78)

# Determine the winner
if result_a['net_profit'] > result_b['net_profit']:
    winner = result_a
    winner_label = "Strategy A — Refined Forex Fader"
    loser  = result_b
    loser_label  = "Strategy B — SMC Order Block Engine"
elif result_b['net_profit'] > result_a['net_profit']:
    winner = result_b
    winner_label = "Strategy B — SMC Order Block Engine"
    loser  = result_a
    loser_label  = "Strategy A — Refined Forex Fader"
else:
    winner = None
    winner_label = "TIE"

print()
if winner:
    print(f"  WINNER : {winner_label}")
    print(f"           Net Profit: ${winner['net_profit']:,.2f}  |  Profit Factor: {winner['profit_factor']:.2f}  |  Win Rate: {winner['win_rate']:.1f}%")
    margin = winner['net_profit'] - loser['net_profit']
    print(f"           Outperformed {loser_label} by ${margin:,.2f}")
else:
    print("  RESULT : Both strategies tied exactly!")
print()

# =============================================================================
# STEP 4: EXPECTANCY MATH CHECK
# =============================================================================
print("=" * 78)
print("  EXPECTANCY FORMULA CHECK")
print("  Formula: (Win Rate × Avg Win) − (Loss Rate × Avg Loss)")
print("=" * 78)

for r in results:
    tr = pd.DataFrame(r['trades'])
    if len(tr) > 0:
        wins   = tr[tr['result'] == 'WIN']['pnl']
        losses = tr[tr['result'] == 'LOSS']['pnl']
        avg_w  = wins.mean() if len(wins) > 0 else 0.0
        avg_l  = abs(losses.mean()) if len(losses) > 0 else 0.0
        wr_dec = r['win_rate'] / 100.0
        lr_dec = 1.0 - wr_dec
        exp    = (wr_dec * avg_w) - (lr_dec * avg_l)
        verdict = "POSITIVE EDGE" if exp > 0 else "NEGATIVE EDGE"
        print(f"  {r['name'][:38]:<38}")
        print(f"    ({wr_dec:.2f} × ${avg_w:.2f}) − ({lr_dec:.2f} × ${avg_l:.2f}) = ${exp:.2f}/trade  [{verdict}]")
        print()

# =============================================================================
# STEP 5: DUAL EQUITY CURVE CHART
# =============================================================================
print("[PLOTS] Generating dual equity curve comparison chart...")

fig, axes = plt.subplots(3, 1, figsize=(14, 13), gridspec_kw={'height_ratios': [3, 3, 1.5]})
fig.suptitle(
    "Strategy Battle: Refined Forex Fader vs SMC Order Block Engine\n"
    "EUR/USD — 2-Year Backtest (730 Days, 1-Hour Data)",
    fontsize=14, fontweight='bold', y=0.99
)

COLOR_A = '#1565C0'   # Deep blue for Strategy A
COLOR_B = '#B71C1C'   # Deep red for Strategy B
COLOR_BASE = '#616161'

# ---- Panel 1: Strategy A equity ----
ax_a = axes[0]
eq_a = result_a['equity_curve']
et_a = result_a['equity_times']
ax_a.plot(et_a, eq_a, color=COLOR_A, linewidth=2.0, label=f"Strategy A — Refined Fader (${result_a['net_profit']:+,.0f})")
ax_a.axhline(INITIAL_BALANCE, color=COLOR_BASE, linestyle='--', linewidth=1.0, alpha=0.7)
ax_a.fill_between(et_a, INITIAL_BALANCE, eq_a,
                   where=(np.array(eq_a) >= INITIAL_BALANCE), color=COLOR_A, alpha=0.15)
ax_a.fill_between(et_a, INITIAL_BALANCE, eq_a,
                   where=(np.array(eq_a) < INITIAL_BALANCE), color='#F44336', alpha=0.15)
ax_a.set_title(f"Strategy A: Refined Forex Fader  |  Trades: {result_a['total_trades']}  |  "
               f"Win Rate: {result_a['win_rate']:.1f}%  |  PF: {result_a['profit_factor']:.2f}  |  "
               f"Net: ${result_a['net_profit']:+,.0f}", fontsize=10)
ax_a.set_ylabel("Account Balance ($)")
ax_a.legend(loc='upper left', fontsize=9)
ax_a.grid(True, linestyle=':', alpha=0.5)
ax_a.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

# ---- Panel 2: Strategy B equity ----
ax_b = axes[1]
eq_b = result_b['equity_curve']
et_b = result_b['equity_times']
ax_b.plot(et_b, eq_b, color=COLOR_B, linewidth=2.0, label=f"Strategy B — SMC Engine (${result_b['net_profit']:+,.0f})")
ax_b.axhline(INITIAL_BALANCE, color=COLOR_BASE, linestyle='--', linewidth=1.0, alpha=0.7)
ax_b.fill_between(et_b, INITIAL_BALANCE, eq_b,
                   where=(np.array(eq_b) >= INITIAL_BALANCE), color=COLOR_B, alpha=0.15)
ax_b.fill_between(et_b, INITIAL_BALANCE, eq_b,
                   where=(np.array(eq_b) < INITIAL_BALANCE), color='#F44336', alpha=0.15)
ax_b.set_title(f"Strategy B: SMC Order Block Engine  |  Trades: {result_b['total_trades']}  |  "
               f"Win Rate: {result_b['win_rate']:.1f}%  |  PF: {result_b['profit_factor']:.2f}  |  "
               f"Net: ${result_b['net_profit']:+,.0f}", fontsize=10)
ax_b.set_ylabel("Account Balance ($)")
ax_b.legend(loc='upper left', fontsize=9)
ax_b.grid(True, linestyle=':', alpha=0.5)
ax_b.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

# ---- Panel 3: Metric bar chart ----
ax_c = axes[2]
categories = ['Win Rate (%)', 'Profit Factor × 10', 'Max Drawdown (%)']
vals_a = [result_a['win_rate'], result_a['profit_factor'] * 10, result_a['max_drawdown']]
vals_b = [result_b['win_rate'], result_b['profit_factor'] * 10, result_b['max_drawdown']]

x = np.arange(len(categories))
w = 0.35
bars_a = ax_c.bar(x - w/2, vals_a, w, label='Strategy A', color=COLOR_A, alpha=0.85)
bars_b = ax_c.bar(x + w/2, vals_b, w, label='Strategy B', color=COLOR_B, alpha=0.85)

for bar in bars_a:
    ax_c.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
              f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=8, color=COLOR_A, fontweight='bold')
for bar in bars_b:
    ax_c.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
              f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=8, color=COLOR_B, fontweight='bold')

ax_c.set_xticks(x)
ax_c.set_xticklabels(categories, fontsize=9)
ax_c.set_title("Key Metrics Side-by-Side (Profit Factor scaled ×10 for visibility)", fontsize=9)
ax_c.legend(loc='upper right', fontsize=9)
ax_c.grid(True, axis='y', linestyle=':', alpha=0.5)

plt.tight_layout(rect=[0, 0, 1, 0.97])

chart_file = "strategy_comparison_chart.png"
plt.savefig(chart_file, dpi=150, bbox_inches='tight')
print(f"[SAVE] Comparison chart saved to: {os.path.abspath(chart_file)}\n")

# =============================================================================
# STEP 6: FINAL VERDICT
# =============================================================================
print("=" * 78)
print("  FINAL VERDICT & STAGE 4 RECOMMENDATION")
print("=" * 78)
if winner:
    if winner['net_profit'] > 0 and winner['profit_factor'] > 1.0:
        print(f"  DEPLOY: {winner_label}")
        print(f"  This strategy has a POSITIVE MATHEMATICAL EDGE and should be")
        print(f"  used as the base for Stage 4 (Live Paper Trading).")
    else:
        print(f"  CAUTION: {winner_label} performed better but is still not profitable.")
        print(f"  Consider further parameter tuning before moving to Stage 4.")
else:
    print("  Both strategies need further optimization. Recommend combining elements.")
print()
print("  Next Step: python strategy_comparison.py to re-run anytime.")
print("=" * 78 + "\n")

print("Comparison complete! Open 'strategy_comparison_chart.png' to see the visual results.")
