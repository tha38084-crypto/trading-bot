"""
===============================================================================
TRADING BOT - ASIAN SESSION RANGE SWEEP AI SIGNAL ASSISTANT (15-MINUTE)
===============================================================================
Engineered for a $200 account scanning EUR/USD, GBP/USD, and USD/JPY on 15M candles.
Rulebook:
  1. Asian Session Range (00:00 - 06:00 London time)
  2. Sweep of Asian High/Low during London (07:00-11:00) or NY (13:00-17:00)
  3. 200-EMA Trend Alignment
  4. RSI Oversold/Overbought Reversal
  5. Layered Exits: TP1 (+1:1 R/R, 50% exit + SL to BE) | TP2 (+1:2 R/R, 50% exit)
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
import pytz

INITIAL_BALANCE = 200.0
RISK_PERCENT = 0.03

WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip_size": 0.0001, "sl_pips": 10},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip_size": 0.01,   "sl_pips": 12},
]

LONDON_TZ = pytz.timezone("Europe/London")

def fetch_and_process(asset_info):
    sym = asset_info['symbol']
    df = yf.download(tickers=sym, period="60d", interval="15m", progress=False)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    df['London_Time'] = df.index.tz_convert(LONDON_TZ)

    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=14, adjust=False).mean()
    avg_loss = loss.ewm(span=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # Asian Range (00:00 - 06:00 London Time)
    df['Date_Str'] = df['London_Time'].dt.date
    df['Hour'] = df['London_Time'].dt.hour
    
    # Calculate Asian High & Low for each date
    asian_mask = (df['Hour'] >= 0) & (df['Hour'] < 6)
    asian_highs = df[asian_mask].groupby('Date_Str')['High'].max()
    asian_lows = df[asian_mask].groupby('Date_Str')['Low'].min()

    df['Asian_High'] = df['Date_Str'].map(asian_highs)
    df['Asian_Low'] = df['Date_Str'].map(asian_lows)

    return df

asset_dict = {}
for a in WATCHLIST:
    res = fetch_and_process(a)
    if res is not None:
        asset_dict[a['symbol']] = res

# Simulator
sample_df = list(asset_dict.values())[0]
current_balance = INITIAL_BALANCE
trades_history = []
active_trades = []

for i in range(200, len(sample_df)):
    current_time = sample_df['London_Time'].iloc[i]
    hour = current_time.hour

    # Position Management
    closed_trades = []
    for trade in active_trades:
        sym = trade['symbol']
        if sym not in asset_dict or i >= len(asset_dict[sym]):
            continue
        bar = asset_dict[sym].iloc[i]
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
                current_balance += risk_usd * 0.5 * 1.0
                trade['realized'] += risk_usd * 0.5 * 1.0

            if bar['High'] >= tp2:
                pnl = trade['realized'] + (risk_usd * 0.5 * 2.0)
                current_balance += (risk_usd * 0.5 * 2.0)
                trades_history.append({'pnl': pnl, 'result': 'WIN'})
                closed_trades.append(trade)
            elif bar['Low'] <= trade['sl_price']:
                if trade['sl_price'] == ep:
                    trades_history.append({'pnl': trade['realized'], 'result': 'BREAKEVEN'})
                else:
                    pnl = -risk_usd
                    current_balance += pnl
                    trades_history.append({'pnl': pnl, 'result': 'LOSS'})
                closed_trades.append(trade)

        elif t_type == "SELL":
            if bar['Low'] <= tp1 and not trade['tp1_hit']:
                trade['tp1_hit'] = True
                trade['sl_price'] = ep
                current_balance += risk_usd * 0.5 * 1.0
                trade['realized'] += risk_usd * 0.5 * 1.0

            if bar['Low'] <= tp2:
                pnl = trade['realized'] + (risk_usd * 0.5 * 2.0)
                current_balance += (risk_usd * 0.5 * 2.0)
                trades_history.append({'pnl': pnl, 'result': 'WIN'})
                closed_trades.append(trade)
            elif bar['High'] >= trade['sl_price']:
                if trade['sl_price'] == ep:
                    trades_history.append({'pnl': trade['realized'], 'result': 'BREAKEVEN'})
                else:
                    pnl = -risk_usd
                    current_balance += pnl
                    trades_history.append({'pnl': pnl, 'result': 'LOSS'})
                closed_trades.append(trade)

    for ct in closed_trades:
        active_trades.remove(ct)

    # Session Filter: London Open (7-11) & NY Open (13-17)
    in_window = (7 <= hour < 11) or (13 <= hour < 17)
    if not in_window:
        continue

    for a_info in WATCHLIST:
        sym = a_info['symbol']
        if sym not in asset_dict or i >= len(asset_dict[sym]):
            continue
        bar = asset_dict[sym].iloc[i]
        ah = bar['Asian_High']
        al = bar['Asian_Low']
        ema = bar['EMA_200']
        rsi = bar['RSI_14']

        if pd.isna(ah) or pd.isna(al) or pd.isna(ema) or pd.isna(rsi):
            continue

        if any(t['symbol'] == sym for t in active_trades):
            continue

        pip_sz = a_info['pip_size']
        sl_pips = a_info['sl_pips']
        risk_usd = current_balance * RISK_PERCENT

        # ASIAN SWEEP RULES
        # BUY: Price sweeps Asian Low (Low <= Asian_Low) AND Price > 200-EMA AND RSI < 35
        buy = (bar['Close'] > ema) and (bar['Low'] <= al) and (rsi < 35.0)

        # SELL: Price sweeps Asian High (High >= Asian_High) AND Price < 200-EMA AND RSI > 65
        sell = (bar['Close'] < ema) and (bar['High'] >= ah) and (rsi > 65.0)

        if buy:
            sl_price = al - (sl_pips * pip_sz)
            sl_dist = abs(bar['Close'] - sl_price)
            if sl_dist < 4 * pip_sz:
                sl_dist = 4 * pip_sz
                sl_price = bar['Close'] - sl_dist

            active_trades.append({
                'symbol': sym, 'type': 'BUY', 'entry_price': bar['Close'],
                'sl_price': sl_price, 'tp1_price': bar['Close'] + sl_dist,
                'tp2_price': bar['Close'] + (2.0 * sl_dist), 'sl_distance': sl_dist,
                'risk_dollar': risk_usd, 'tp1_hit': False, 'realized': 0.0
            })
        elif sell:
            sl_price = ah + (sl_pips * pip_sz)
            sl_dist = abs(sl_price - bar['Close'])
            if sl_dist < 4 * pip_sz:
                sl_dist = 4 * pip_sz
                sl_price = bar['Close'] + sl_dist

            active_trades.append({
                'symbol': sym, 'type': 'SELL', 'entry_price': bar['Close'],
                'sl_price': sl_price, 'tp1_price': bar['Close'] - sl_dist,
                'tp2_price': bar['Close'] - (2.0 * sl_dist), 'sl_distance': sl_dist,
                'risk_dollar': risk_usd, 'tp1_hit': False, 'realized': 0.0
            })

df_tr = pd.DataFrame(trades_history)
tot = len(df_tr)
days = (sample_df['London_Time'].iloc[-1] - sample_df['London_Time'].iloc[200]).days
weeks = max(1.0, days / 7.0)
tpw = tot / weeks

if tot > 0:
    wins = df_tr[df_tr['result'] == 'WIN']
    losses = df_tr[df_tr['result'] == 'LOSS']
    bes = df_tr[df_tr['result'] == 'BREAKEVEN']
    wr = (len(wins) / tot) * 100
    gp = wins['pnl'].sum() if not wins.empty else 0.0
    gl = abs(losses['pnl'].sum()) if not losses.empty else 0.0
    net = df_tr['pnl'].sum()
    pf = (gp / gl) if gl > 0 else (gp if gp > 0 else 0.0)
else:
    wr = gp = gl = net = pf = 0.0

print(f"\n==========================================================================")
print(f"📊 ASIAN SESSION RANGE SWEEP RESULTS ($200 Account)")
print(f"==========================================================================")
print(f"• Backtest Period     : {days} Days ({weeks:.1f} Weeks)")
print(f"• Total Signals       : {tot} Signals")
print(f"• Signal Frequency    : {tpw:.1f} Signals per Week (TARGET: 4-5/Wk!)")
print(f"• Win Breakdown       : {len(wins)} Wins | {len(losses)} Losses | {len(bes)} Risk-Free Breakevens")
print(f"• Win Rate            : {wr:.1f}%")
print(f"• Profit Factor       : {pf:.2f}")
print(f"• Starting Balance    : ${INITIAL_BALANCE:,.2f}")
print(f"• Ending Balance      : ${current_balance:,.2f}")
print(f"• Total Net Profit    : ${net:,.2f} ({(net/INITIAL_BALANCE)*100:+.2f}%)")
print(f"==========================================================================\n")
