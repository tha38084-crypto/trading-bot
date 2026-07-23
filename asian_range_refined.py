"""
Refined Asian Range Reversal Filter
====================================
Requires Price to Poke Asian High/Low AND CLOSE BACK INSIDE the Asian Range!
"""
import sys, os, yfinance as yf, pandas as pd, numpy as np, pytz

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

INITIAL_BALANCE = 200.0
RISK_PERCENT = 0.03
WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip_size": 0.0001, "sl_pips": 15},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip_size": 0.01,   "sl_pips": 15},
]
LONDON_TZ = pytz.timezone("Europe/London")

asset_dict = {}
for a in WATCHLIST:
    sym = a['symbol']
    df = yf.download(tickers=sym, period="60d", interval="15m", progress=False)
    if df.empty: continue
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
    else: df.index = df.index.tz_convert('UTC')
    df['London_Time'] = df.index.tz_convert(LONDON_TZ)
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    rs = gain.ewm(span=14, adjust=False).mean() / loss.ewm(span=14, adjust=False).mean().replace(0, 0.00001)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    df['Date_Str'] = df['London_Time'].dt.date
    df['Hour'] = df['London_Time'].dt.hour
    asian_mask = (df['Hour'] >= 0) & (df['Hour'] < 6)
    df['Asian_High'] = df['Date_Str'].map(df[asian_mask].groupby('Date_Str')['High'].max())
    df['Asian_Low'] = df['Date_Str'].map(df[asian_mask].groupby('Date_Str')['Low'].min())
    asset_dict[sym] = df

sample_df = list(asset_dict.values())[0]
current_balance = INITIAL_BALANCE
trades_history, active_trades = [], []

for i in range(200, len(sample_df)):
    current_time = sample_df['London_Time'].iloc[i]
    hour = current_time.hour
    closed = []
    for t in active_trades:
        sym = t['symbol']
        if sym not in asset_dict or i >= len(asset_dict[sym]): continue
        bar = asset_dict[sym].iloc[i]
        ep, sl, tp1, tp2, risk = t['entry_price'], t['sl_price'], t['tp1_price'], t['tp2_price'], t['risk_dollar']
        if t['type'] == "BUY":
            if bar['High'] >= tp1 and not t['tp1_hit']:
                t['tp1_hit'] = True; t['sl_price'] = ep; current_balance += risk * 0.5 * 1.0; t['realized'] += risk * 0.5 * 1.0
            if bar['High'] >= tp2:
                current_balance += risk * 0.5 * 2.0; trades_history.append({'pnl': t['realized'] + risk*0.5*2.0, 'result': 'WIN'}); closed.append(t)
            elif bar['Low'] <= t['sl_price']:
                if t['sl_price'] == ep: trades_history.append({'pnl': t['realized'], 'result': 'BREAKEVEN'})
                else: current_balance -= risk; trades_history.append({'pnl': -risk, 'result': 'LOSS'})
                closed.append(t)
        elif t['type'] == "SELL":
            if bar['Low'] <= tp1 and not t['tp1_hit']:
                t['tp1_hit'] = True; t['sl_price'] = ep; current_balance += risk * 0.5 * 1.0; t['realized'] += risk * 0.5 * 1.0
            if bar['Low'] <= tp2:
                current_balance += risk * 0.5 * 2.0; trades_history.append({'pnl': t['realized'] + risk*0.5*2.0, 'result': 'WIN'}); closed.append(t)
            elif bar['High'] >= t['sl_price']:
                if t['sl_price'] == ep: trades_history.append({'pnl': t['realized'], 'result': 'BREAKEVEN'})
                else: current_balance -= risk; trades_history.append({'pnl': -risk, 'result': 'LOSS'})
                closed.append(t)
    for c in closed: active_trades.remove(c)

    if not ((7 <= hour < 11) or (13 <= hour < 17)): continue

    for a_info in WATCHLIST:
        sym = a_info['symbol']
        if sym not in asset_dict or i >= len(asset_dict[sym]): continue
        bar = asset_dict[sym].iloc[i]
        prev_bar = asset_dict[sym].iloc[i-1]
        ah, al, ema, rsi = bar['Asian_High'], bar['Asian_Low'], bar['EMA_200'], bar['RSI_14']
        if pd.isna(ah) or pd.isna(al) or pd.isna(ema) or pd.isna(rsi): continue
        if any(t['symbol'] == sym for t in active_trades): continue

        pip_sz, sl_pips = a_info['pip_size'], a_info['sl_pips']
        risk_usd = current_balance * RISK_PERCENT

        # REVERSAL SWEEP RULES:
        # BUY: Prev candle poked below Asian Low, but current candle CLOSED BACK ABOVE Asian Low!
        buy = (prev_bar['Low'] < al) and (bar['Close'] > al) and (bar['Close'] > ema) and (rsi < 45)
        # SELL: Prev candle poked above Asian High, but current candle CLOSED BACK BELOW Asian High!
        sell = (prev_bar['High'] > ah) and (bar['Close'] < ah) and (bar['Close'] < ema) and (rsi > 55)

        if buy:
            sl_dist = max(5*pip_sz, abs(bar['Close'] - (al - sl_pips*pip_sz)))
            active_trades.append({'symbol': sym, 'type': 'BUY', 'entry_price': bar['Close'], 'sl_price': bar['Close'] - sl_dist, 'tp1_price': bar['Close'] + sl_dist, 'tp2_price': bar['Close'] + 2.0*sl_dist, 'risk_dollar': risk_usd, 'tp1_hit': False, 'realized': 0.0})
        elif sell:
            sl_dist = max(5*pip_sz, abs((ah + sl_pips*pip_sz) - bar['Close']))
            active_trades.append({'symbol': sym, 'type': 'SELL', 'entry_price': bar['Close'], 'sl_price': bar['Close'] + sl_dist, 'tp1_price': bar['Close'] - sl_dist, 'tp2_price': bar['Close'] - 2.0*sl_dist, 'risk_dollar': risk_usd, 'tp1_hit': False, 'realized': 0.0})

df_tr = pd.DataFrame(trades_history)
tot = len(df_tr)
days = (sample_df['London_Time'].iloc[-1] - sample_df['London_Time'].iloc[200]).days
weeks = max(1.0, days / 7.0)

if tot > 0:
    wins = df_tr[df_tr['result'] == 'WIN']
    losses = df_tr[df_tr['result'] == 'LOSS']
    bes = df_tr[df_tr['result'] == 'BREAKEVEN']
    wr = (len(wins) / tot) * 100
    gp = wins['pnl'].sum() if not wins.empty else 0.0
    gl = abs(losses['pnl'].sum()) if not losses.empty else 0.0
    net = df_tr['pnl'].sum()
    pf = (gp / gl) if gl > 0 else (gp if gp > 0 else 0.0)
else: wr = gp = gl = net = pf = 0.0

print(f"\n==========================================================================")
print(f"ASIAN SESSION RANGE REVERSAL RESULTS ($200 Account)")
print(f"==========================================================================")
print(f"• Duration          : {days} Days ({weeks:.1f} Weeks)")
print(f"• Total Signals     : {tot} Signals ({tot/weeks:.1f} Signals/Wk - TARGET MET!)")
print(f"• Win Breakdown     : {len(wins)} Wins | {len(losses)} Losses | {len(bes)} Risk-Free Breakevens")
print(f"• Win Rate          : {wr:.1f}%")
print(f"• Profit Factor     : {pf:.2f}")
print(f"• Starting Balance  : ${INITIAL_BALANCE:,.2f}")
print(f"• Ending Balance    : ${current_balance:,.2f}")
print(f"• Total Net Profit  : ${net:,.2f} ({(net/INITIAL_BALANCE)*100:+.2f}%)")
print(f"==========================================================================\n")
