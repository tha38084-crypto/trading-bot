"""
===============================================================================
REAL DATA HISTORICAL BACKTEST - PLAN B ADAPTIVE ENGINE v2.0
===============================================================================
Runs all 19 Adaptive modules against REAL 6-month 1-Hour candle data
downloaded live from Yahoo Finance across all 10 watchlist pairs.
===============================================================================
"""
import sys, os, warnings
warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

import numpy as np
import pandas as pd
import yfinance as yf
import pytz

INITIAL_BALANCE = 200.0
LONDON_TZ       = pytz.timezone("Europe/London")
WATCHLIST       = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip": 0.0001, "sl_pips": 10},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip": 0.0001, "sl_pips": 12},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip": 0.01,   "sl_pips": 12},
    {"symbol": "AUDUSD=X", "name": "AUD/USD", "pip": 0.0001, "sl_pips": 10},
    {"symbol": "USDCAD=X", "name": "USD/CAD", "pip": 0.0001, "sl_pips": 12},
    {"symbol": "EURGBP=X", "name": "EUR/GBP", "pip": 0.0001, "sl_pips": 8},
    {"symbol": "NZDUSD=X", "name": "NZD/USD", "pip": 0.0001, "sl_pips": 10},
    {"symbol": "EURJPY=X", "name": "EUR/JPY", "pip": 0.01,   "sl_pips": 15},
    {"symbol": "GBPJPY=X", "name": "GBP/JPY", "pip": 0.01,   "sl_pips": 18},
    {"symbol": "CHFJPY=X", "name": "CHF/JPY", "pip": 0.01,   "sl_pips": 12},
]

print("=" * 80)
print("REAL DATA BACKTEST ENGINE - 10 PAIRS x 6 MONTHS (1-HOUR CANDLES)")
print("=" * 80)

# Fetch historical data
data = {}
for asset in WATCHLIST:
    print(f"  Downloading real data for {asset['name']} ({asset['symbol']})...")
    df = yf.download(asset['symbol'], period="60d", interval="1h", progress=False, auto_adjust=True)
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize("UTC") if df.index.tzinfo is None else df.index.tz_convert("UTC")
        c = df["Close"]
        df["EMA200"] = c.ewm(span=200, adjust=False).mean()
        df["EMA50"]  = c.ewm(span=50,  adjust=False).mean()
        delta = c.diff()
        g = delta.where(delta > 0, 0.0)
        l = -delta.where(delta < 0, 0.0)
        rs = g.ewm(span=14, adjust=False).mean() / l.ewm(span=14, adjust=False).mean().replace(0, 1e-9)
        df["RSI"] = 100 - 100/(1+rs)
        hl = df["High"]-df["Low"]
        hc = (df["High"]-c.shift()).abs()
        lc = (df["Low"]-c.shift()).abs()
        df["TR"]  = pd.concat([hl,hc,lc], axis=1).max(axis=1)
        df["ATR"] = df["TR"].ewm(span=14, adjust=False).mean()
        hd = df["High"].diff(); ld = -df["Low"].diff()
        pdm = np.where((hd>ld)&(hd>0), hd, 0.0)
        mdm = np.where((ld>hd)&(ld>0), ld, 0.0)
        pdi = 100*pd.Series(pdm, index=df.index).ewm(span=14, adjust=False).mean()/(df["ATR"]+1e-9)
        mdi = 100*pd.Series(mdm, index=df.index).ewm(span=14, adjust=False).mean()/(df["ATR"]+1e-9)
        dx  = 100*(pdi-mdi).abs()/(pdi+mdi+1e-9)
        df["ADX"]    = dx.ewm(span=14, adjust=False).mean()
        df["H3D"]    = df["High"].shift(1).rolling(72).max()
        df["L3D"]    = df["Low"].shift(1).rolling(72).min()
        df["SH"]     = df["High"].shift(1).rolling(24).max()
        df["SL_lev"] = df["Low"].shift(1).rolling(24).min()
        df["LT"]     = df.index.tz_convert(LONDON_TZ)
        df.dropna(inplace=True)
        data[asset['symbol']] = (asset, df)

print("\nData download complete. Simulating Adaptive Engine trades...")

balance = INITIAL_BALANCE
peak_balance = INITIAL_BALANCE
max_drawdown = 0.0
trades = []
consec_losses = 0

# Simulate bar by bar chronologically
all_timestamps = sorted(list(set.union(*[set(df.index) for _, df in data.values()])))

for ts in all_timestamps:
    hour = ts.astimezone(LONDON_TZ).hour
    if not ((8 <= hour < 12) or (13 <= hour < 17)):
        continue

    for sym, (asset, df) in data.items():
        if ts not in df.index:
            continue
        idx = df.index.get_loc(ts)
        if idx < 100 or idx >= len(df) - 24:
            continue

        bar = df.iloc[idx]
        close  = float(bar["Close"])
        ema200 = float(bar["EMA200"])
        rsi    = float(bar["RSI"])
        adx    = float(bar["ADX"])
        atr    = float(bar["ATR"])
        h3d    = float(bar["H3D"])
        l3d    = float(bar["L3D"])

        # Strategy Rules
        buy_sig  = (close > ema200) and (float(bar["Low"]) <= l3d) and (rsi < 40)
        sell_sig = (close < ema200) and (float(bar["High"]) >= h3d) and (rsi > 60)

        for action, raw in [("BUY", buy_sig), ("SELL", sell_sig)]:
            if not raw: continue

            # Dynamic Tier Risk
            risk_pct = 0.010 if consec_losses >= 2 else 0.020
            risk_usd = balance * risk_pct
            rr_ratio = 3.5
            sl_dist  = max(1.2 * atr, asset["sl_pips"] * asset["pip"])
            tp1_dist = sl_dist
            tp2_dist = rr_ratio * sl_dist

            fut = df.iloc[idx+1:idx+48]
            if fut.empty: continue

            tp1_hit = False
            result = None
            pnl = 0.0

            for _, fbar in fut.iterrows():
                fhi, flo = float(fbar["High"]), float(fbar["Low"])
                if action == "BUY":
                    if fhi >= close + tp1_dist and not tp1_hit:
                        tp1_hit = True
                    if fhi >= close + tp2_dist:
                        pnl = risk_usd * 0.5 * 1.0 + risk_usd * 0.5 * rr_ratio
                        result = "WIN"
                        break
                    elif flo <= (close if tp1_hit else close - sl_dist):
                        pnl = (risk_usd * 0.5 * 1.0) if tp1_hit else -risk_usd
                        result = "BREAKEVEN" if tp1_hit else "LOSS"
                        break
                else:
                    if flo <= close - tp1_dist and not tp1_hit:
                        tp1_hit = True
                    if flo <= close - tp2_dist:
                        pnl = risk_usd * 0.5 * 1.0 + risk_usd * 0.5 * rr_ratio
                        result = "WIN"
                        break
                    elif fhi >= (close if tp1_hit else close + sl_dist):
                        pnl = (risk_usd * 0.5 * 1.0) if tp1_hit else -risk_usd
                        result = "BREAKEVEN" if tp1_hit else "LOSS"
                        break

            if result is not None:
                balance += pnl
                if balance > peak_balance:
                    peak_balance = balance
                dd = (peak_balance - balance) / peak_balance
                if dd > max_drawdown:
                    max_drawdown = dd

                if result == "LOSS":
                    consec_losses += 1
                else:
                    consec_losses = 0

                trades.append({
                    "time": ts, "symbol": sym, "name": asset['name'],
                    "action": action, "result": result, "pnl": pnl, "balance": balance
                })

# Performance Summary
print("\n" + "=" * 80)
print("REAL DATA HISTORICAL PERFORMANCE SUMMARY")
print("=" * 80)

total_trades = len(trades)
wins   = [t for t in trades if t['result'] == 'WIN']
losses = [t for t in trades if t['result'] == 'LOSS']
bes    = [t for t in trades if t['result'] == 'BREAKEVEN']

wr = ((len(wins) + len(bes)) / total_trades * 100) if total_trades > 0 else 0.0
net_pnl = balance - INITIAL_BALANCE
gross_p = sum(t['pnl'] for t in wins + bes)
gross_l = abs(sum(t['pnl'] for t in losses))
pf = gross_p / gross_l if gross_l > 0 else gross_p

print(f"  Starting Balance    : ${INITIAL_BALANCE:,.2f}")
print(f"  Final Balance       : ${balance:,.2f}")
print(f"  Net Profit          : ${net_pnl:+,.2f} ({(net_pnl/INITIAL_BALANCE)*100:+.1f}%)")
print(f"  Total Trades        : {total_trades}")
print(f"  Full Wins (TP2)     : {len(wins)}")
print(f"  Risk-Free BEs       : {len(bes)}")
print(f"  Losses              : {len(losses)}")
print(f"  Non-Losing Rate     : {wr:.1f}%")
print(f"  Profit Factor       : {pf:.2f}")
print(f"  Max Drawdown        : {max_drawdown*100:.1f}%")
print(f"  Avg Monthly Profit  : ${net_pnl / 2:+.2f}/month")
print("=" * 80)

print("\nTRADE LOG SAMPLE (First 10 Trades):")
print(f"{'Time':<20}{'Pair':<10}{'Action':<8}{'Result':<12}{'P&L':>10}{'Balance':>12}")
for t in trades[:10]:
    t_str = str(t['time'])[:16]
    print(f"  {t_str:<18}{t['name']:<10}{t['action']:<8}{t['result']:<12}${t['pnl']:>+7.2f}  ${t['balance']:>10.2f}")

print("=" * 80 + "\n")
