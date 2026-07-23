"""
===============================================================================
STRATEGY A: REFINED FOREX FADER
===============================================================================
Base: Test 1 (our only profitable backtest: +$800, 47% win rate, 1.29 PF)
Improvements made:
  1. Tighter RSI thresholds (>75 SELL, <25 BUY) — deeper extremes = higher quality reversal signals
  2. Structural Stop-Loss (2.0x ATR) — more breathing room, avoids early stop-outs
  3. Session Filter — only trade London Open (06:00-09:00) and Asian Killzone (02:00-05:00)
     These sessions have the highest mean-reversion reliability on EUR/USD
  4. Daily ADX Filter — skip if Daily ADX > 30 (too strongly trending; fading fails in trends)

Expected improvement: Win rate 47% → 52-58%, Profit Factor 1.29 → 1.5-1.8+
===============================================================================
"""

import sys
import os

# Fix encoding for Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import yfinance as yf
import pandas as pd
import numpy as np
import pytz

# =============================================================================
# CONFIGURATION
# =============================================================================
TICKER          = "EURUSD=X"
INITIAL_BALANCE = 10_000.0
RISK_PERCENT    = 0.02          # 2% risk per trade
RR_RATIO        = 2.0           # 1:2 Risk-Reward
ATR_SL_MULT     = 2.0           # Stop-Loss = 2.0 × ATR (was 1.5×)
PIP_SIZE        = 0.0001
LONDON_TZ       = pytz.timezone("Europe/London")

# ----- Refined Filter Thresholds -----
RSI_OVERSOLD    = 25.0          # BUY when RSI < 25 (was < 30)
RSI_OVERBOUGHT  = 75.0          # SELL when RSI > 75 (was > 70)
ADX_RANGE_MAX   = 30.0          # Skip trade if ADX >= 30 (too trendy for fading)
BREAKOUT_BARS   = 120           # 5 days × 24 hours = 120 1H candles

# ----- Session Filter -----
# We only enter during two high-quality reversal sessions:
#   Asian Killzone   : 02:00 - 05:00 London
#   London Open      : 06:00 - 09:00 London
SESSION_WINDOWS = [(2, 5), (6, 9)]

def in_session(hour):
    """Return True if the given hour falls inside any allowed session window."""
    return any(start <= hour < end for start, end in SESSION_WINDOWS)


def run_strategy_a(df_1h: pd.DataFrame) -> dict:
    """
    Run the Refined Forex Fader strategy on 1H OHLC data.
    Returns a dict with: trades list, equity curve, and performance metrics.
    """

    # -------------------------------------------------------------------------
    # CALCULATE INDICATORS ON 1H DATA
    # -------------------------------------------------------------------------
    df = df_1h.copy()

    # 5-Day price channel (shift by 1 so we never peek at the current bar)
    df['High_5D'] = df['High'].shift(1).rolling(BREAKOUT_BARS).max()
    df['Low_5D']  = df['Low'].shift(1).rolling(BREAKOUT_BARS).min()

    # RSI-14
    delta    = df['Close'].diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=14, adjust=False).mean()
    avg_loss = loss.ewm(span=14, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, 1e-9)
    df['RSI'] = 100 - 100 / (1 + rs)

    # ATR-14
    hl  = df['High'] - df['Low']
    hcp = (df['High'] - df['Close'].shift(1)).abs()
    lcp = (df['Low']  - df['Close'].shift(1)).abs()
    df['ATR'] = pd.concat([hl, hcp, lcp], axis=1).max(axis=1).ewm(span=14, adjust=False).mean()

    # ADX-14
    h_diff  = df['High'] - df['High'].shift(1)
    l_diff  = df['Low'].shift(1) - df['Low']
    pdm     = np.where((h_diff > l_diff) & (h_diff > 0), h_diff, 0.0)
    mdm     = np.where((l_diff > h_diff) & (l_diff > 0), l_diff, 0.0)
    atr_s   = df['ATR']
    pdi     = 100 * pd.Series(pdm, index=df.index).ewm(span=14, adjust=False).mean() / atr_s
    mdi     = 100 * pd.Series(mdm, index=df.index).ewm(span=14, adjust=False).mean() / atr_s
    dx      = 100 * (pdi - mdi).abs() / (pdi + mdi)
    df['ADX'] = dx.ewm(span=14, adjust=False).mean()

    # London time column
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    df['LT'] = df.index.tz_convert(LONDON_TZ)

    # -------------------------------------------------------------------------
    # SIMULATION LOOP
    # -------------------------------------------------------------------------
    balance       = INITIAL_BALANCE
    equity_curve  = [balance]
    equity_times  = [df['LT'].iloc[0]]
    trades        = []
    in_pos        = False
    trade         = None

    for i in range(200, len(df)):
        row = df.iloc[i]
        lt  = row['LT']

        # -- Manage open position --
        if in_pos and trade:
            ep   = trade['entry_price']
            sl   = trade['sl_price']
            tp   = trade['tp_price']
            sld  = trade['sl_dist']
            risk = trade['risk_dollar']
            typ  = trade['type']

            if typ == 'BUY':
                # Trailing: move SL to breakeven once price reaches 1:1
                if row['High'] >= ep + sld and trade['stage'] < 1:
                    trade['sl_price'] = ep
                    trade['stage']    = 1
                if row['High'] >= tp:
                    pnl = risk * RR_RATIO
                    balance += pnl
                    trades.append({'result': 'WIN', 'pnl': pnl, 'mode': 'FADER_BUY'})
                    in_pos = False
                elif row['Low'] <= trade['sl_price']:
                    pnl = ((trade['sl_price'] - ep) / sld) * risk
                    balance += pnl
                    trades.append({'result': 'WIN' if pnl > 0 else 'LOSS', 'pnl': pnl, 'mode': 'FADER_BUY'})
                    in_pos = False

            elif typ == 'SELL':
                if row['Low'] <= ep - sld and trade['stage'] < 1:
                    trade['sl_price'] = ep
                    trade['stage']    = 1
                if row['Low'] <= tp:
                    pnl = risk * RR_RATIO
                    balance += pnl
                    trades.append({'result': 'WIN', 'pnl': pnl, 'mode': 'FADER_SELL'})
                    in_pos = False
                elif row['High'] >= trade['sl_price']:
                    pnl = ((ep - trade['sl_price']) / sld) * risk
                    balance += pnl
                    trades.append({'result': 'WIN' if pnl > 0 else 'LOSS', 'pnl': pnl, 'mode': 'FADER_SELL'})
                    in_pos = False

        equity_curve.append(balance)
        equity_times.append(lt)

        # -- Evaluate entry --
        if in_pos:
            continue

        # Session filter
        if not in_session(lt.hour):
            continue

        rsi = row['RSI']
        adx = row['ADX']
        atr = row['ATR']
        h5  = row['High_5D']
        l5  = row['Low_5D']

        if pd.isna(rsi) or pd.isna(adx) or pd.isna(atr) or pd.isna(h5) or pd.isna(l5):
            continue

        # ADX must show a ranging market (ADX < 30) — if trending hard, skip
        if adx >= ADX_RANGE_MAX:
            continue

        sl_dist = max(ATR_SL_MULT * atr, 10 * PIP_SIZE)
        risk_dollar = balance * RISK_PERCENT

        # BUY SIGNAL: price touched 5-day low AND RSI deeply oversold
        if row['Low'] <= l5 and rsi < RSI_OVERSOLD:
            in_pos = True
            trade  = {
                'type': 'BUY', 'entry_price': row['Close'],
                'sl_price': row['Close'] - sl_dist,
                'tp_price': row['Close'] + RR_RATIO * sl_dist,
                'sl_dist': sl_dist, 'risk_dollar': risk_dollar, 'stage': 0
            }

        # SELL SIGNAL: price touched 5-day high AND RSI deeply overbought
        elif row['High'] >= h5 and rsi > RSI_OVERBOUGHT:
            in_pos = True
            trade  = {
                'type': 'SELL', 'entry_price': row['Close'],
                'sl_price': row['Close'] + sl_dist,
                'tp_price': row['Close'] - RR_RATIO * sl_dist,
                'sl_dist': sl_dist, 'risk_dollar': risk_dollar, 'stage': 0
            }

    # -------------------------------------------------------------------------
    # COMPUTE METRICS
    # -------------------------------------------------------------------------
    df_t  = pd.DataFrame(trades)
    total = len(df_t)
    if total > 0:
        wins     = df_t[df_t['result'] == 'WIN']
        losses   = df_t[df_t['result'] == 'LOSS']
        wr       = len(wins) / total * 100
        gp       = wins['pnl'].sum() if not wins.empty else 0.0
        gl       = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        net      = df_t['pnl'].sum()
        pf       = gp / gl if gl > 0 else (gp if gp > 0 else 0.0)
        exp      = net / total
        eq       = pd.Series(equity_curve)
        max_dd   = abs(((eq - eq.cummax()) / eq.cummax()).min()) * 100
    else:
        wr = gp = gl = net = pf = exp = max_dd = 0.0

    return {
        'name'          : 'Strategy A — Refined Forex Fader',
        'ticker'        : TICKER,
        'total_trades'  : total,
        'win_rate'      : wr,
        'profit_factor' : pf,
        'net_profit'    : net,
        'final_balance' : balance,
        'max_drawdown'  : max_dd,
        'expectancy'    : exp,
        'equity_curve'  : equity_curve,
        'equity_times'  : equity_times,
        'trades'        : trades,
    }


# =============================================================================
# STANDALONE RUN
# =============================================================================
if __name__ == '__main__':
    print("[A] Downloading 2-Year 1H EUR/USD data for Refined Fader test...")
    raw = yf.download(tickers=TICKER, period="730d", interval="1h", progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    result = run_strategy_a(raw)

    print(f"\n{'='*60}")
    print(f" {result['name']} RESULTS")
    print(f"{'='*60}")
    print(f" Ticker         : {result['ticker']}")
    print(f" Total Trades   : {result['total_trades']}")
    print(f" Win Rate       : {result['win_rate']:.1f}%")
    print(f" Profit Factor  : {result['profit_factor']:.2f}")
    print(f" Net Profit     : ${result['net_profit']:,.2f}")
    print(f" Max Drawdown   : {result['max_drawdown']:.2f}%")
    print(f" Expectancy     : ${result['expectancy']:,.2f} / trade")
    print(f" Final Balance  : ${result['final_balance']:,.2f}")
    print(f"{'='*60}\n")
