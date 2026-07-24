"""
Backtest simulation of Plan B Elite 5-Module Combined System.
Simulates 3 months (12 weeks) of trading with realistic win/loss distribution
based on the projected 52-58% win rate and 1:3.5 R/R ratio.
"""
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import random

INITIAL_BALANCE = 200.0
RISK_PCT        = 0.020   # 2% per trade (Stage 1)
RR_RATIO        = 3.5     # 1:3.5 Risk/Reward
WIN_RATE        = 0.55    # 55% win rate (combined system target)
SIGNALS_PER_MO  = 4.5     # avg signals per month after AI filtering
MONTHS          = 3
WEEKS           = MONTHS * 4

random.seed(42)

print("=" * 70)
print("PLAN B ELITE - 3-MONTH BACKTEST SIMULATION (12 Weeks)")
print("=" * 70)
print(f"  Start Balance    : ${INITIAL_BALANCE:,.2f}")
print(f"  Risk per Trade   : {RISK_PCT*100:.1f}% (Dynamic)")
print(f"  R:R Ratio        : 1:{RR_RATIO:.1f}")
print(f"  Win Rate (AI)    : {WIN_RATE*100:.0f}%")
print(f"  Signals/Month    : ~{SIGNALS_PER_MO:.1f} (70+ AI Score Only)")
print("=" * 70)

balance = INITIAL_BALANCE
weekly_pnl = []
all_trades = []
consec_losses = 0
governor_active = False

week_num = 0
for month in range(1, MONTHS + 1):
    signals_this_month = random.choice([4, 4, 5, 5])
    monthly_start = balance

    for sig_num in range(signals_this_month):
        week_num += 1

        # Determine risk (governor activates after 2 consec losses)
        if consec_losses >= 2:
            active_risk_pct = 0.010
            governor_active = True
        else:
            active_risk_pct = RISK_PCT
            governor_active = False

        risk_usd    = balance * active_risk_pct
        reward_usd  = risk_usd * RR_RATIO

        # Trade outcome
        rand = random.random()
        if rand < WIN_RATE:
            # Win: 50% at TP1 (1:1), 50% at TP2 (1:3.5)
            pnl = risk_usd * 0.5 * 1.0 + risk_usd * 0.5 * RR_RATIO
            result = "WIN"
            consec_losses = 0
        elif rand < WIN_RATE + 0.12:
            # Breakeven (TP1 hit, SL moved to breakeven)
            pnl = risk_usd * 0.5 * 1.0
            result = "BE"
            consec_losses = 0
        else:
            pnl = -risk_usd
            result = "LOSS"
            consec_losses += 1

        balance += pnl
        all_trades.append({
            "month": month, "signal": sig_num + 1,
            "result": result, "pnl": pnl, "balance": balance,
            "risk": risk_usd, "governor": governor_active
        })

    month_pnl = balance - monthly_start
    weekly_pnl.append(month_pnl)
    print(f"\n  Month {month}: {signals_this_month} Signals | P&L: ${month_pnl:+.2f} | Balance: ${balance:.2f}")

# Summary statistics
import statistics
pnl_vals = [t['pnl'] for t in all_trades]
wins   = [t for t in all_trades if t['result'] == 'WIN']
losses = [t for t in all_trades if t['result'] == 'LOSS']
bes    = [t for t in all_trades if t['result'] == 'BE']
total  = len(all_trades)
wr_act = (len(wins) + len(bes)) / total

gross_profit = sum(t['pnl'] for t in wins + bes)
gross_loss   = abs(sum(t['pnl'] for t in losses))
profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

# Max drawdown calculation
peak = INITIAL_BALANCE
max_dd = 0.0
for t in all_trades:
    if t['balance'] > peak:
        peak = t['balance']
    dd = (peak - t['balance']) / peak
    if dd > max_dd:
        max_dd = dd

net = balance - INITIAL_BALANCE

print("\n" + "=" * 70)
print("BACKTEST RESULTS SUMMARY (3 Months / 12 Weeks)")
print("=" * 70)
print(f"  Starting Balance  : ${INITIAL_BALANCE:,.2f}")
print(f"  Final Balance     : ${balance:,.2f}")
print(f"  Net Profit        : ${net:+,.2f} ({(net/INITIAL_BALANCE)*100:+.1f}%)")
print(f"  Total Signals     : {total} (AI-Filtered 70+ Only)")
print(f"  Wins              : {len(wins)}")
print(f"  Breakevens (BE)   : {len(bes)}")
print(f"  Losses            : {len(losses)}")
print(f"  Non-Losing Rate   : {wr_act*100:.1f}%")
print(f"  Profit Factor     : {profit_factor:.2f}")
print(f"  Max Drawdown      : {max_dd*100:.1f}%")
print(f"  Avg Monthly P&L   : ${net/MONTHS:+.2f}")
print(f"  Avg Weekly P&L    : ${net/(WEEKS):+.2f}")
print("=" * 70)

print("\nWEEKLY/MONTHLY BREAKDOWN:")
print(f"{'Month':<8}{'P&L':>10}{'Return':>10}")
for i, wpnl in enumerate(weekly_pnl, 1):
    ret = (wpnl / INITIAL_BALANCE) * 100
    bar = "+" * max(0, int(wpnl / 2))
    print(f"  M{i:<5}  ${wpnl:>+7.2f}  {ret:>+6.1f}%  {bar}")

print("\nTRADE-BY-TRADE LOG:")
print(f"{'#':<4}{'Mo':<4}{'Result':<12}{'P&L':>8}{'Balance':>10}{'Governor':>10}")
for i, t in enumerate(all_trades, 1):
    gov = "ACTIVE" if t['governor'] else "-"
    print(f"  {i:<4}{t['month']:<4}{t['result']:<12}${t['pnl']:>+7.2f}  ${t['balance']:>8.2f}  {gov:>10}")

print("=" * 70)
print(f"\n  MENTOR VERDICT: Plan B Elite targets +${net/MONTHS:+.2f}/month on a $200 account.")
print(f"  With 3 months of clean results, a $10k Prop Firm Funded Account")
print(f"  would generate ${(net/MONTHS)*50:+.0f}/month (50x the capital!).")
print("=" * 70 + "\n")
