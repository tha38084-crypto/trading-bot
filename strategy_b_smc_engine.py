"""
===============================================================================
STRATEGY B: SMC ORDER BLOCK ENGINE
===============================================================================
Smart Money Concepts (SMC) — Institutional-Grade Strategy

Core Logic (3 signals must ALIGN):
  1. LIQUIDITY SWEEP: Price breaks above a 10-bar swing high then closes back
     below (bearish reversal), or breaks below a 10-bar swing low then closes
     back above (bullish reversal). This is institutions hunting stop-losses.

  2. ORDER BLOCK (OB): After the sweep, price returns to the last
     bearish candle before a bullish impulse (Bullish OB for BUY), or
     last bullish candle before a bearish impulse (Bearish OB for SELL).
     These are the candles where institutions placed their bulk orders.

  3. FAIR VALUE GAP (FVG): A 3-candle imbalance pattern.
     - Bullish FVG: candle[i-2].High < candle[i].Low  → gap = price must fill upward
     - Bearish FVG: candle[i-2].Low  > candle[i].High → gap = price must fill downward
     Price always returns to fill these gaps — this is our entry zone.

Stop-Loss: 2 pips BEYOND the Order Block boundary (very tight = better R/R)
Take-Profit: Split:
  - TP1 = 1.5× SL distance (close 50% of trade at 1:1.5)
  - TP2 = 3.0× SL distance (close remaining 50% at 1:3)
  Average R/R per trade = 2.25×
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

# =============================================================================
# CONFIGURATION
# =============================================================================
TICKER          = "EURUSD=X"
INITIAL_BALANCE = 10_000.0
RISK_PERCENT    = 0.02
PIP_SIZE        = 0.0001
LONDON_TZ       = pytz.timezone("Europe/London")

# SMC Parameters
SWING_LOOKBACK  = 10    # How many bars to look back for a swing high/low
IMPULSE_BARS    = 3     # How many consecutive candles = a "strong impulse"
OB_VALID_BARS   = 50    # Order block remains valid for up to 50 bars (50 hours)
SWEEP_VALID_BARS= 30    # Liquidity sweep remains "active" for up to 30 bars

TP1_MULT        = 1.5   # Take-Profit 1: 1.5× SL distance (close 50%)
TP2_MULT        = 3.0   # Take-Profit 2: 3.0× SL distance (close remaining 50%)
AVG_RR          = (TP1_MULT + TP2_MULT) / 2   # = 2.25 average R/R

# Session: 06:00–16:00 London (broad window to catch OB retests)
SESSION_START   = 6
SESSION_END     = 16


# =============================================================================
# INDICATOR HELPERS
# =============================================================================
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI-14, ATR-14, and London Time column to the DataFrame."""
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

    # Timezone
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    df['LT'] = df.index.tz_convert(LONDON_TZ)

    return df


def detect_swing_highs_lows(df: pd.DataFrame, lookback: int) -> tuple:
    """
    For each bar, compute the rolling swing high (max of last N bars)
    and swing low (min of last N bars). Shifted by 1 to avoid lookahead.
    """
    swing_high = df['High'].shift(1).rolling(lookback).max()
    swing_low  = df['Low'].shift(1).rolling(lookback).min()
    return swing_high, swing_low


def detect_order_blocks(df: pd.DataFrame, impulse_bars: int) -> tuple:
    """
    Detect Bullish and Bearish Order Blocks.

    Bullish OB: The last BEARISH (red) candle BEFORE a series of
                impulse_bars consecutive bullish (green) candles.
                → Price is likely to return to this candle's range.

    Bearish OB: The last BULLISH (green) candle BEFORE a series of
                impulse_bars consecutive bearish (red) candles.
                → Price is likely to return to this candle's range.

    Returns two Series:
      - bull_ob_high, bull_ob_low : high & low of each Bullish OB bar
      - bear_ob_high, bear_ob_low : high & low of each Bearish OB bar
    """
    close = df['Close'].values
    open_ = df['Open'].values
    n     = len(df)

    bull_ob_high = np.full(n, np.nan)
    bull_ob_low  = np.full(n, np.nan)
    bear_ob_high = np.full(n, np.nan)
    bear_ob_low  = np.full(n, np.nan)

    for i in range(impulse_bars + 1, n):
        # Check for bullish impulse: N consecutive bullish candles ending at i
        bullish_impulse = all(
            close[i - k] > open_[i - k] for k in range(impulse_bars)
        )
        if bullish_impulse:
            # The OB is the last BEARISH candle before this impulse
            ob_idx = i - impulse_bars - 1
            if ob_idx >= 0 and close[ob_idx] < open_[ob_idx]:  # bearish candle
                bull_ob_high[i] = df['High'].iloc[ob_idx]
                bull_ob_low[i]  = df['Low'].iloc[ob_idx]

        # Check for bearish impulse: N consecutive bearish candles ending at i
        bearish_impulse = all(
            close[i - k] < open_[i - k] for k in range(impulse_bars)
        )
        if bearish_impulse:
            # The OB is the last BULLISH candle before this impulse
            ob_idx = i - impulse_bars - 1
            if ob_idx >= 0 and close[ob_idx] > open_[ob_idx]:  # bullish candle
                bear_ob_high[i] = df['High'].iloc[ob_idx]
                bear_ob_low[i]  = df['Low'].iloc[ob_idx]

    return (
        pd.Series(bull_ob_high, index=df.index),
        pd.Series(bull_ob_low,  index=df.index),
        pd.Series(bear_ob_high, index=df.index),
        pd.Series(bear_ob_low,  index=df.index),
    )


def detect_fvg(df: pd.DataFrame) -> tuple:
    """
    Detect Fair Value Gaps (3-candle imbalance).

    Bullish FVG: candle[i-2].High < candle[i].Low
      → There is an unfilled gap between them. Price will likely return.

    Bearish FVG: candle[i-2].Low > candle[i].High
      → There is an unfilled gap between them. Price will likely return.

    Returns:
      bull_fvg_top, bull_fvg_bot : top and bottom of Bullish FVG zone
      bear_fvg_top, bear_fvg_bot : top and bottom of Bearish FVG zone
    """
    n             = len(df)
    bull_fvg_top  = np.full(n, np.nan)
    bull_fvg_bot  = np.full(n, np.nan)
    bear_fvg_top  = np.full(n, np.nan)
    bear_fvg_bot  = np.full(n, np.nan)

    high = df['High'].values
    low  = df['Low'].values

    for i in range(2, n):
        # Bullish FVG: gap between candle[i-2] high and candle[i] low
        if high[i - 2] < low[i]:
            bull_fvg_top[i] = low[i]
            bull_fvg_bot[i] = high[i - 2]

        # Bearish FVG: gap between candle[i-2] low and candle[i] high
        if low[i - 2] > high[i]:
            bear_fvg_top[i] = low[i - 2]
            bear_fvg_bot[i] = high[i]

    return (
        pd.Series(bull_fvg_top, index=df.index),
        pd.Series(bull_fvg_bot, index=df.index),
        pd.Series(bear_fvg_top, index=df.index),
        pd.Series(bear_fvg_bot, index=df.index),
    )


# =============================================================================
# MAIN STRATEGY RUNNER
# =============================================================================
def run_strategy_b(df_1h: pd.DataFrame) -> dict:
    """
    Run the SMC Order Block engine on 1H OHLC data.
    Returns a dict with trades, equity curve, and performance metrics.
    """
    df = compute_indicators(df_1h.copy())

    # Pre-compute all SMC signals
    swing_high, swing_low = detect_swing_highs_lows(df, SWING_LOOKBACK)
    bull_ob_h, bull_ob_l, bear_ob_h, bear_ob_l = detect_order_blocks(df, IMPULSE_BARS)
    bull_fvg_t, bull_fvg_b, bear_fvg_t, bear_fvg_b = detect_fvg(df)

    # -------------------------------------------------------------------------
    # SIMULATION LOOP
    # -------------------------------------------------------------------------
    balance         = INITIAL_BALANCE
    equity_curve    = [balance]
    equity_times    = [df['LT'].iloc[0]]
    trades          = []
    in_pos          = False
    trade           = None

    # Track last liquidity sweep for context
    last_bull_sweep = -999   # bar index of last bullish reversal sweep
    last_bear_sweep = -999   # bar index of last bearish reversal sweep

    # Running windows of recent Order Blocks and FVGs
    recent_bull_obs = []  # list of (high, low, bar_index)
    recent_bear_obs = []
    recent_bull_fvg = []  # list of (top, bot, bar_index)
    recent_bear_fvg = []

    for i in range(SWING_LOOKBACK + IMPULSE_BARS + 5, len(df)):
        row  = df.iloc[i]
        lt   = row['LT']
        rsi  = row['RSI']
        atr  = row['ATR']

        # Skip if indicators not yet warmed up
        if pd.isna(rsi) or pd.isna(atr):
            equity_curve.append(balance)
            equity_times.append(lt)
            continue

        # -- Collect new OBs and FVGs detected at this bar --
        if not np.isnan(bull_ob_h.iloc[i]):
            recent_bull_obs.append((bull_ob_h.iloc[i], bull_ob_l.iloc[i], i))
        if not np.isnan(bear_ob_h.iloc[i]):
            recent_bear_obs.append((bear_ob_h.iloc[i], bear_ob_l.iloc[i], i))
        if not np.isnan(bull_fvg_t.iloc[i]):
            recent_bull_fvg.append((bull_fvg_t.iloc[i], bull_fvg_b.iloc[i], i))
        if not np.isnan(bear_fvg_t.iloc[i]):
            recent_bear_fvg.append((bear_fvg_t.iloc[i], bear_fvg_b.iloc[i], i))

        # Expire old OBs / FVGs (older than OB_VALID_BARS)
        recent_bull_obs = [(h, l, idx) for h, l, idx in recent_bull_obs if i - idx <= OB_VALID_BARS]
        recent_bear_obs = [(h, l, idx) for h, l, idx in recent_bear_obs if i - idx <= OB_VALID_BARS]
        recent_bull_fvg = [(t, b, idx) for t, b, idx in recent_bull_fvg if i - idx <= OB_VALID_BARS]
        recent_bear_fvg = [(t, b, idx) for t, b, idx in recent_bear_fvg if i - idx <= OB_VALID_BARS]

        # -- Detect Liquidity Sweeps at this bar --
        sh = swing_high.iloc[i]
        sl = swing_low.iloc[i]

        if not pd.isna(sh):
            # Bearish sweep: price poked ABOVE the swing high but closed BELOW it
            if row['High'] > sh and row['Close'] < sh:
                last_bear_sweep = i  # institutions swept buy stops → bearish reversal

        if not pd.isna(sl):
            # Bullish sweep: price poked BELOW the swing low but closed ABOVE it
            if row['Low'] < sl and row['Close'] > sl:
                last_bull_sweep = i  # institutions swept sell stops → bullish reversal

        # -- Manage open position --
        if in_pos and trade:
            ep   = trade['entry_price']
            sl_p = trade['sl_price']
            tp1  = trade['tp1']
            tp2  = trade['tp2']
            sld  = trade['sl_dist']
            risk = trade['risk_dollar']
            typ  = trade['type']
            tp1_hit = trade.get('tp1_hit', False)

            if typ == 'BUY':
                # Trailing SL to breakeven once TP1 hit
                if not tp1_hit and row['High'] >= tp1:
                    trade['sl_price'] = ep   # move SL to breakeven
                    trade['tp1_hit']  = True
                    tp1_hit = True

                if row['High'] >= tp2:
                    # Full exit at TP2
                    pnl = risk * TP2_MULT if not tp1_hit else risk * (TP1_MULT * 0.5 + TP2_MULT * 0.5)
                    balance += pnl
                    trades.append({'result': 'WIN', 'pnl': pnl, 'mode': 'SMC_BUY'})
                    in_pos = False
                elif row['Low'] <= trade['sl_price']:
                    # Stopped out
                    if tp1_hit:
                        pnl = 0.0  # at breakeven, no loss
                        trades.append({'result': 'BREAKEVEN', 'pnl': pnl, 'mode': 'SMC_BUY'})
                    else:
                        pnl = -risk
                        balance += pnl
                        trades.append({'result': 'LOSS', 'pnl': pnl, 'mode': 'SMC_BUY'})
                    in_pos = False

            elif typ == 'SELL':
                if not tp1_hit and row['Low'] <= tp1:
                    trade['sl_price'] = ep
                    trade['tp1_hit']  = True
                    tp1_hit = True

                if row['Low'] <= tp2:
                    pnl = risk * TP2_MULT if not tp1_hit else risk * (TP1_MULT * 0.5 + TP2_MULT * 0.5)
                    balance += pnl
                    trades.append({'result': 'WIN', 'pnl': pnl, 'mode': 'SMC_SELL'})
                    in_pos = False
                elif row['High'] >= trade['sl_price']:
                    if tp1_hit:
                        trades.append({'result': 'BREAKEVEN', 'pnl': 0.0, 'mode': 'SMC_SELL'})
                    else:
                        pnl = -risk
                        balance += pnl
                        trades.append({'result': 'LOSS', 'pnl': pnl, 'mode': 'SMC_SELL'})
                    in_pos = False

        equity_curve.append(balance)
        equity_times.append(lt)

        # -- Evaluate entry conditions --
        if in_pos:
            continue

        # Session filter
        if not (SESSION_START <= lt.hour < SESSION_END):
            continue

        risk_dollar = balance * RISK_PERCENT

        # =====================================================================
        # BULLISH SETUP (3 signals must align):
        #   1. Recent bullish liquidity sweep (last 30 bars)
        #   2. Price is inside a Bullish Order Block OR Bullish FVG zone
        #   3. RSI > 50 (momentum confirmed bullish)
        # =====================================================================
        if i - last_bull_sweep <= SWEEP_VALID_BARS and rsi > 50:
            # Check if current price touches any recent Bullish OB
            in_bull_ob = any(
                ob_l <= row['Close'] <= ob_h
                for ob_h, ob_l, _ in recent_bull_obs
            )
            # Check if current price touches any recent Bullish FVG
            in_bull_fvg = any(
                fvg_b <= row['Close'] <= fvg_t
                for fvg_t, fvg_b, _ in recent_bull_fvg
            )

            if in_bull_ob or in_bull_fvg:
                # Tight structural SL: 3 pips below the OB/FVG zone bottom
                sl_dist = max(3 * PIP_SIZE, 0.5 * atr)
                in_pos  = True
                trade   = {
                    'type': 'BUY', 'entry_price': row['Close'],
                    'sl_price': row['Close'] - sl_dist,
                    'tp1': row['Close'] + TP1_MULT * sl_dist,
                    'tp2': row['Close'] + TP2_MULT * sl_dist,
                    'sl_dist': sl_dist, 'risk_dollar': risk_dollar,
                    'tp1_hit': False
                }

        # =====================================================================
        # BEARISH SETUP (3 signals must align):
        #   1. Recent bearish liquidity sweep (last 30 bars)
        #   2. Price is inside a Bearish Order Block OR Bearish FVG zone
        #   3. RSI < 50 (momentum confirmed bearish)
        # =====================================================================
        elif i - last_bear_sweep <= SWEEP_VALID_BARS and rsi < 50:
            in_bear_ob = any(
                ob_l <= row['Close'] <= ob_h
                for ob_h, ob_l, _ in recent_bear_obs
            )
            in_bear_fvg = any(
                fvg_b <= row['Close'] <= fvg_t
                for fvg_t, fvg_b, _ in recent_bear_fvg
            )

            if in_bear_ob or in_bear_fvg:
                sl_dist = max(3 * PIP_SIZE, 0.5 * atr)
                in_pos  = True
                trade   = {
                    'type': 'SELL', 'entry_price': row['Close'],
                    'sl_price': row['Close'] + sl_dist,
                    'tp1': row['Close'] - TP1_MULT * sl_dist,
                    'tp2': row['Close'] - TP2_MULT * sl_dist,
                    'sl_dist': sl_dist, 'risk_dollar': risk_dollar,
                    'tp1_hit': False
                }

    # -------------------------------------------------------------------------
    # COMPUTE METRICS
    # -------------------------------------------------------------------------
    df_t  = pd.DataFrame(trades)
    total = len(df_t)
    if total > 0:
        wins   = df_t[df_t['result'] == 'WIN']
        losses = df_t[df_t['result'] == 'LOSS']
        wr     = len(wins) / total * 100
        gp     = wins['pnl'].sum() if not wins.empty else 0.0
        gl     = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        net    = df_t['pnl'].sum()
        pf     = gp / gl if gl > 0 else (gp if gp > 0 else 0.0)
        exp    = net / total
        eq     = pd.Series(equity_curve)
        max_dd = abs(((eq - eq.cummax()) / eq.cummax()).min()) * 100
    else:
        wr = gp = gl = net = pf = exp = max_dd = 0.0

    return {
        'name'          : 'Strategy B — SMC Order Block Engine',
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
    print("[B] Downloading 2-Year 1H EUR/USD data for SMC Engine test...")
    raw = yf.download(tickers=TICKER, period="730d", interval="1h", progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    result = run_strategy_b(raw)

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
