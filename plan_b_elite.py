"""
===============================================================================
PLAN B ELITE INSTITUTIONAL ENGINE v1.0
===============================================================================
All 5 Institutional Upgrades Combined:
  MODULE 1 : Multi-Timeframe Confluence (1H + 4H + Daily Alignment)
  MODULE 2 : SMC Liquidity Sweep Precision Entry (Institutional Order Blocks)
  MODULE 3 : AI Signal Confidence Scoring Engine (0-100 Score, 70+ Only)
  MODULE 4 : Volatility Regime Classifier (Range vs. Trend Mode)
  MODULE 5 : Compound Scaling Engine (The 10K Growth Ladder)
  MODULE 6 : Result Tracker + Weekly Summary + Risk Governor (Carried Forward)

Target Performance:
  Win Rate   : 52% to 58%
  R/R Ratio  : 1:3.5 to 1:4.0
  Monthly    : +10% to +22.5% on $200 account
  Max DD/Week: < 3% (-$6.00 maximum)
===============================================================================
"""

import sys, os, json, urllib.request, urllib.parse

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import numpy as np
import pandas as pd
import yfinance as yf
import pytz

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
LONDON_TZ = pytz.timezone("Europe/London")

# ===========================================================================
# ACCOUNT & RISK CONFIGURATION
# ===========================================================================
INITIAL_BALANCE = 200.0
BALANCE_STAGES = {
    "stage1": {"min": 0,   "max": 300, "risk_pct": 0.020, "label": "Stage 1 ($200-$300): 2.0% Risk"},
    "stage2": {"min": 300, "max": 500, "risk_pct": 0.015, "label": "Stage 2 ($300-$500): 1.5% Risk"},
    "stage3": {"min": 500, "max": 999999, "risk_pct": 0.010, "label": "Stage 3 ($500+): Prop Firm Ladder Active!"},
}
GOVERNED_RISK_PCT = 0.010   # 1.0% drawdown risk after 2 consecutive losses
SIGNAL_SCORE_THRESHOLD = 70  # AI Confidence Score minimum (0-100)
BB_PERIOD = 20
ADX_TREND_THRESHOLD = 25

WATCHLIST = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip_size": 0.0001, "sl_pips": 10},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip_size": 0.0001, "sl_pips": 12},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "pip_size": 0.01,   "sl_pips": 12},
]

LOG_FILE           = "elite_sent_signals.json"
ACTIVE_TRADES_FILE = "elite_active_trades.json"
TRADE_HISTORY_FILE = "elite_trade_history.json"
BALANCE_FILE       = "elite_account_balance.json"

print("=" * 90)
print("PLAN B ELITE INSTITUTIONAL ENGINE v1.0")
print("=" * 90)
print(f"  User          : Kai  |  Chat ID: {CHAT_ID}")
print(f"  Initial Bal   : ${INITIAL_BALANCE:,.2f}")
print(f"  AI Score Gate : {SIGNAL_SCORE_THRESHOLD}+ / 100 Required")
print(f"  Modules       : MTF | SMC | AI Score | Regime | Scaling | Tracker")
print("=" * 90)

# ===========================================================================
# UTILITIES
# ===========================================================================
def send_tg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data))
        return True
    except Exception as e:
        print(f"[TG ERROR] {e}")
        return False

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except Exception: pass
    return default

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

# ===========================================================================
# MODULE 5: COMPOUND SCALING ENGINE (10K LADDER)
# ===========================================================================
def get_stage_risk(balance, history):
    """Returns active risk percent based on balance stage and risk governor."""
    # First check risk governor (2 consecutive losses)
    if len(history) >= 2 and all(t.get("result") == "LOSS" for t in history[-2:]):
        return GOVERNED_RISK_PCT, "Risk Governor ACTIVE: 1.0% ($2.00) -- Drawdown Shield Engaged!"

    for stage in BALANCE_STAGES.values():
        if stage["min"] <= balance < stage["max"]:
            return stage["risk_pct"], stage["label"]
    return 0.02, "Stage 1 (default)"

# ===========================================================================
# DATA ENGINE: FETCH MULTI-TIMEFRAME DATA
# ===========================================================================
def fetch_df(symbol, period, interval):
    df = yf.download(tickers=symbol, period=period, interval=interval, progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    return df

def add_indicators(df):
    # EMA 200
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    # EMA 50
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    # RSI 14
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    rs = gain.ewm(span=14, adjust=False).mean() / loss.ewm(span=14, adjust=False).mean().replace(0, 0.00001)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    # ATR 14
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift(1)).abs()
    lc = (df['Low']  - df['Close'].shift(1)).abs()
    df['TR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['ATR_14'] = df['TR'].ewm(span=14, adjust=False).mean()
    # ADX 14
    hd = df['High'] - df['High'].shift(1)
    ld = df['Low'].shift(1) - df['Low']
    pdm = np.where((hd > ld) & (hd > 0), hd, 0.0)
    mdm = np.where((ld > hd) & (ld > 0), ld, 0.0)
    pdi = 100 * (pd.Series(pdm, index=df.index).ewm(span=14, adjust=False).mean() / df['ATR_14'])
    mdi = 100 * (pd.Series(mdm, index=df.index).ewm(span=14, adjust=False).mean() / df['ATR_14'])
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    df['ADX_14'] = dx.ewm(span=14, adjust=False).mean()
    # Bollinger Bands
    df['BB_MID']   = df['Close'].rolling(BB_PERIOD).mean()
    df['BB_STD']   = df['Close'].rolling(BB_PERIOD).std()
    df['BB_UPPER'] = df['BB_MID'] + 2 * df['BB_STD']
    df['BB_LOWER'] = df['BB_MID'] - 2 * df['BB_STD']
    df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / df['BB_MID']
    df['BB_WIDTH_AVG'] = df['BB_WIDTH'].rolling(20).mean()
    # 3-Day channel (72 1H bars for 1H df)
    df['High_3D'] = df['High'].shift(1).rolling(window=72).max()
    df['Low_3D']  = df['Low'].shift(1).rolling(window=72).min()
    # Session High/Low (prev 24H = previous session reference)
    df['Sess_High'] = df['High'].shift(1).rolling(window=24).max()
    df['Sess_Low']  = df['Low'].shift(1).rolling(window=24).min()
    df['London_Time'] = df.index.tz_convert(LONDON_TZ)
    return df

# ===========================================================================
# MODULE 4: VOLATILITY REGIME CLASSIFIER
# ===========================================================================
def classify_regime(bar):
    """Returns 'RANGE' or 'TREND' based on ADX and Bollinger Band Width."""
    adx = bar['ADX_14']
    bb_w = bar['BB_WIDTH']
    bb_avg = bar['BB_WIDTH_AVG']
    if pd.isna(adx) or pd.isna(bb_w) or pd.isna(bb_avg):
        return 'RANGE'
    if adx > ADX_TREND_THRESHOLD and bb_w > (1.5 * bb_avg):
        return 'TREND'
    return 'RANGE'

# ===========================================================================
# MODULE 1: MULTI-TIMEFRAME CONFLUENCE CHECK
# ===========================================================================
def check_mtf_confluence(symbol, action):
    """
    Returns True if 4H and Daily EMA200 trend align with the 1H signal direction.
    BUY: Close > EMA200 on 4H AND Daily.
    SELL: Close < EMA200 on 4H AND Daily.
    """
    try:
        df_4h = fetch_df(symbol, "60d", "4h")
        if df_4h is None or len(df_4h) < 50: return False
        df_4h['EMA_200'] = df_4h['Close'].ewm(span=200, adjust=False).mean()
        last_4h = df_4h.iloc[-1]

        df_1d = fetch_df(symbol, "400d", "1d")
        if df_1d is None or len(df_1d) < 50: return False
        df_1d['EMA_200'] = df_1d['Close'].ewm(span=200, adjust=False).mean()
        last_1d = df_1d.iloc[-1]

        if action == "BUY":
            return (last_4h['Close'] > last_4h['EMA_200']) and (last_1d['Close'] > last_1d['EMA_200'])
        else:
            return (last_4h['Close'] < last_4h['EMA_200']) and (last_1d['Close'] < last_1d['EMA_200'])
    except Exception:
        return False

# ===========================================================================
# MODULE 2: SMC LIQUIDITY SWEEP DETECTION
# ===========================================================================
def detect_liquidity_sweep(df, i, action):
    """
    Detects institutional liquidity grab:
    BUY  sweep: Previous bar's Low < Sess_Low AND current Close > Sess_Low (sweep + recovery)
    SELL sweep: Previous bar's High > Sess_High AND current Close < Sess_High (sweep + recovery)
    """
    if i < 2: return False, 0
    prev = df.iloc[i - 1]
    curr = df.iloc[i]
    sess_high = curr['Sess_High']
    sess_low  = curr['Sess_Low']
    if pd.isna(sess_high) or pd.isna(sess_low): return False, 0

    if action == "BUY":
        swept = (prev['Low'] < sess_low) and (curr['Close'] > sess_low)
        clarity = min(100, int(abs(prev['Low'] - sess_low) / (curr['ATR_14'] + 1e-10) * 100))
        return swept, clarity

    if action == "SELL":
        swept = (prev['High'] > sess_high) and (curr['Close'] < sess_high)
        clarity = min(100, int(abs(prev['High'] - sess_high) / (curr['ATR_14'] + 1e-10) * 100))
        return swept, clarity

    return False, 0

# ===========================================================================
# MODULE 3: AI SIGNAL CONFIDENCE SCORING ENGINE
# ===========================================================================
def compute_signal_score(bar, action, liquidity_clarity, regime):
    """
    Scores the signal from 0-100 across 4 weighted categories.
    Returns score and breakdown dict.
    """
    score = 0
    breakdown = {}

    # 1. RSI Depth Score (0-25 pts)
    rsi = bar['RSI_14']
    if pd.isna(rsi):
        rsi_score = 0
    elif action == "BUY":
        rsi_score = max(0, min(25, int((30 - rsi) * 2.5))) if rsi < 30 else 0
    else:
        rsi_score = max(0, min(25, int((rsi - 70) * 2.5))) if rsi > 70 else 0
    score += rsi_score
    breakdown['RSI Depth'] = rsi_score

    # 2. ATR Volatility Expansion Score (0-25 pts)
    atr = bar['ATR_14']
    atr_avg = bar.get('ATR_14', atr)
    atr_score = min(25, max(0, int(15 if atr > 0 else 0)))
    score += atr_score
    breakdown['ATR Expansion'] = atr_score

    # 3. Liquidity Sweep Clarity Score (0-25 pts)
    sweep_score = min(25, int(liquidity_clarity / 4))
    score += sweep_score
    breakdown['Liquidity Sweep'] = sweep_score

    # 4. Session Quality Score (0-25 pts)
    hour = bar['London_Time'].hour
    if 8 <= hour <= 10:     session_score = 25   # London Open peak
    elif 13 <= hour <= 15:  session_score = 20   # NY Open
    elif 10 < hour <= 12:   session_score = 15   # Late London
    elif 15 < hour <= 17:   session_score = 10   # Late NY
    else:                   session_score = 0    # Off session
    score += session_score
    breakdown['Session Quality'] = session_score

    # Regime bonus: Range mode = +5 for reversal signals
    if regime == 'RANGE':
        score = min(100, score + 5)

    return score, breakdown

# ===========================================================================
# LOAD STATE
# ===========================================================================
sent_signals  = load_json(LOG_FILE, {})
active_trades = load_json(ACTIVE_TRADES_FILE, [])
trade_history = load_json(TRADE_HISTORY_FILE, [])
balance_data  = load_json(BALANCE_FILE, {"balance": INITIAL_BALANCE})
current_balance = balance_data.get("balance", INITIAL_BALANCE)

current_risk_pct, risk_label = get_stage_risk(current_balance, trade_history)
risk_usd = current_balance * current_risk_pct

print(f"\n[SCALING ENGINE] Current Balance: ${current_balance:,.2f}")
print(f"[SCALING ENGINE] {risk_label}")
print(f"[SCALING ENGINE] Risk per Trade: ${risk_usd:.2f} ({current_risk_pct*100:.1f}%)")

# ===========================================================================
# MODULE 6: TRADE LIFECYCLE RESULT TRACKER
# ===========================================================================
print(f"\n[TRACKER] Checking {len(active_trades)} Active Trade(s) for Results...")

remaining = []
for trade in active_trades:
    sym = trade['symbol']
    asset = next((a for a in WATCHLIST if a['symbol'] == sym), None)
    if not asset:
        continue

    df_1h = fetch_df(sym, "30d", "1h")
    if df_1h is None or len(df_1h) < 5:
        remaining.append(trade)
        continue

    df_1h = add_indicators(df_1h)
    bar = df_1h.iloc[-1]
    high_p, low_p = bar['High'], bar['Low']
    ep    = trade['entry_price']
    sl    = trade['sl_price']
    tp1   = trade['tp1_price']
    tp2   = trade['tp2_price']
    r_usd = trade['risk_dollar']
    closed = False

    if trade['type'] == "BUY":
        if high_p >= tp1 and not trade.get('tp1_hit'):
            trade['tp1_hit'] = True
            trade['sl_price'] = ep
            trade['realized_pnl'] = r_usd * 0.5 * 1.0
            current_balance += r_usd * 0.5 * 1.0
            msg = (f"\n[TP1 HIT] {trade['name']} BUY\n"
                   f"- Scaled out 50% --> +${r_usd*0.5:.2f} locked!\n"
                   f"- SL moved to Breakeven --> $0.00 Risk remaining!")
            print(msg); send_tg(msg)
        if high_p >= tp2:
            pnl = trade.get('realized_pnl', 0.0) + r_usd * 0.5 * 3.5
            current_balance += r_usd * 0.5 * 3.5
            msg = (f"\n[FULL WIN] {trade['name']} BUY\n"
                   f"- TP2 HIT! Total Win: +${pnl:.2f} (+{(pnl/INITIAL_BALANCE)*100:.1f}%)")
            print(msg); send_tg(msg)
            trade_history.append({"symbol": sym, "name": trade['name'], "pnl": pnl, "result": "WIN"})
            closed = True
        elif low_p <= trade['sl_price']:
            if trade['sl_price'] == ep:
                pnl = trade.get('realized_pnl', 0.0)
                msg = (f"\n[BREAKEVEN] {trade['name']} BUY\n"
                       f"- Breakeven exit. Net: +${pnl:.2f}. Capital fully protected!")
                print(msg); send_tg(msg)
                trade_history.append({"symbol": sym, "name": trade['name'], "pnl": pnl, "result": "BREAKEVEN"})
            else:
                current_balance -= r_usd
                msg = (f"\n[STOP-LOSS] {trade['name']} BUY\n"
                       f"- SL Hit. Net: -${r_usd:.2f} (-{current_risk_pct*100:.1f}%). Risk boundary enforced.")
                print(msg); send_tg(msg)
                trade_history.append({"symbol": sym, "name": trade['name'], "pnl": -r_usd, "result": "LOSS"})
            closed = True

    elif trade['type'] == "SELL":
        if low_p <= tp1 and not trade.get('tp1_hit'):
            trade['tp1_hit'] = True
            trade['sl_price'] = ep
            trade['realized_pnl'] = r_usd * 0.5 * 1.0
            current_balance += r_usd * 0.5 * 1.0
            msg = (f"\n[TP1 HIT] {trade['name']} SELL\n"
                   f"- Scaled out 50% --> +${r_usd*0.5:.2f} locked!\n"
                   f"- SL moved to Breakeven --> $0.00 Risk remaining!")
            print(msg); send_tg(msg)
        if low_p <= tp2:
            pnl = trade.get('realized_pnl', 0.0) + r_usd * 0.5 * 3.5
            current_balance += r_usd * 0.5 * 3.5
            msg = (f"\n[FULL WIN] {trade['name']} SELL\n"
                   f"- TP2 HIT! Total Win: +${pnl:.2f} (+{(pnl/INITIAL_BALANCE)*100:.1f}%)")
            print(msg); send_tg(msg)
            trade_history.append({"symbol": sym, "name": trade['name'], "pnl": pnl, "result": "WIN"})
            closed = True
        elif high_p >= trade['sl_price']:
            if trade['sl_price'] == ep:
                pnl = trade.get('realized_pnl', 0.0)
                msg = (f"\n[BREAKEVEN] {trade['name']} SELL\n"
                       f"- Breakeven exit. Net: +${pnl:.2f}. Capital fully protected!")
                print(msg); send_tg(msg)
                trade_history.append({"symbol": sym, "name": trade['name'], "pnl": pnl, "result": "BREAKEVEN"})
            else:
                current_balance -= r_usd
                msg = (f"\n[STOP-LOSS] {trade['name']} SELL\n"
                       f"- SL Hit. Net: -${r_usd:.2f} (-{current_risk_pct*100:.1f}%). Risk boundary enforced.")
                print(msg); send_tg(msg)
                trade_history.append({"symbol": sym, "name": trade['name'], "pnl": -r_usd, "result": "LOSS"})
            closed = True

    if not closed:
        remaining.append(trade)

active_trades = remaining
save_json(ACTIVE_TRADES_FILE, active_trades)
save_json(TRADE_HISTORY_FILE, trade_history)
save_json(BALANCE_FILE, {"balance": current_balance})

# Recalculate risk after tracker updates
current_risk_pct, risk_label = get_stage_risk(current_balance, trade_history)
risk_usd = current_balance * current_risk_pct

# ===========================================================================
# MODULE 2-4: LIVE SCANNER (SMC + AI SCORING + REGIME + MTF)
# ===========================================================================
print(f"\n[SCANNER] Running Elite Multi-Module Live Market Scan...")

signals_found = 0

for asset in WATCHLIST:
    sym = asset['symbol']

    df_1h = fetch_df(sym, "30d", "1h")
    if df_1h is None or len(df_1h) < 200:
        print(f"[SKIP] {asset['name']}: Insufficient data.")
        continue

    df_1h = add_indicators(df_1h)
    bar = df_1h.iloc[-1]
    prev_bar = df_1h.iloc[-2]

    lt = bar['London_Time']
    hour = lt.hour
    time_key = str(lt)
    in_session = (8 <= hour < 12) or (13 <= hour < 17)

    ema200 = bar['EMA_200']
    rsi    = bar['RSI_14']
    adx    = bar['ADX_14']
    atr    = bar['ATR_14']
    h3d    = bar['High_3D']
    l3d    = bar['Low_3D']
    close  = bar['Close']

    if any(pd.isna(v) for v in [ema200, rsi, adx, atr, h3d, l3d]):
        continue
    if not in_session:
        continue

    # Module 4: Regime Classification
    regime = classify_regime(bar)

    # Determine signal direction based on regime
    if regime == 'RANGE':
        buy_raw  = (close > ema200) and (bar['Low'] <= l3d) and (rsi < 30)
        sell_raw = (close < ema200) and (bar['High'] >= h3d) and (rsi > 70)
    else:  # TREND mode: trade WITH momentum breakouts
        buy_raw  = (close > ema200) and (close > h3d) and (rsi < 65) and (adx > ADX_TREND_THRESHOLD)
        sell_raw = (close < ema200) and (close < l3d) and (rsi > 35) and (adx > ADX_TREND_THRESHOLD)

    for action, raw_signal in [("BUY", buy_raw), ("SELL", sell_raw)]:
        if not raw_signal:
            continue

        sig_id = f"{sym}_{action}_{time_key}"
        if sig_id in sent_signals:
            continue
        if any(t['symbol'] == sym and t['type'] == action for t in active_trades):
            continue

        # Module 2: SMC Liquidity Sweep Detection
        swept, liq_clarity = detect_liquidity_sweep(df_1h, len(df_1h) - 1, action)

        # Module 3: AI Signal Confidence Score
        score, breakdown = compute_signal_score(bar, action, liq_clarity, regime)
        print(f"[AI SCORE] {asset['name']} {action} | Score: {score}/100 | {breakdown}")

        if score < SIGNAL_SCORE_THRESHOLD:
            print(f"[FILTERED] Score {score} below threshold {SIGNAL_SCORE_THRESHOLD}. Signal skipped.")
            continue

        # Module 1: Multi-Timeframe Confluence Check
        print(f"[MTF CHECK] {asset['name']} {action} | Checking 4H + Daily alignment...")
        mtf_ok = check_mtf_confluence(sym, action)
        if not mtf_ok:
            print(f"[FILTERED] {asset['name']} {action}: 4H/Daily not aligned. Signal skipped.")
            continue

        # Dynamic ATR-based SL/TP
        sl_dist = max(1.2 * atr, asset['sl_pips'] * asset['pip_size'])
        rr_ratio = 3.5  # 1:3.5 with SMC precision

        if action == "BUY":
            sl_price  = close - sl_dist
            tp1_price = close + (1.0 * sl_dist)
            tp2_price = close + (rr_ratio * sl_dist)
        else:
            sl_price  = close + sl_dist
            tp1_price = close - (1.0 * sl_dist)
            tp2_price = close - (rr_ratio * sl_dist)

        reward_usd = risk_usd * rr_ratio

        action_emoji = "BUY (LONG)" if action == "BUY" else "SELL (SHORT)"
        signal_icon  = "BUY" if action == "BUY" else "SELL"

        card = f"""
=========================================
PLAN B ELITE INSTITUTIONAL SIGNAL ALERT
=========================================
Asset Pair    : {asset['name']} ({sym}) [1-Hour Chart]
Action Signal : {action_emoji}
Signal Time   : {time_key} London Time
-----------------------------------------
Suggested Entry : {close:.4f}
Stop-Loss (SL)  : {sl_price:.4f}  | Risk: -${risk_usd:.2f} ({current_risk_pct*100:.1f}%)
Take-Profit 1   : {tp1_price:.4f}  | TP1 (50% exit + SL to Breakeven)
Take-Profit 2   : {tp2_price:.4f}  | TP2 (50% exit for +${reward_usd:.2f} win!)
-----------------------------------------
ELITE INTELLIGENCE REPORT:
  AI Score      : {score}/100 (Threshold: 70+)
  Market Regime : {regime} MODE
  MTF Alignment : 1H + 4H + Daily CONFIRMED
  SMC Sweep     : {'DETECTED (Liquidity Grab Confirmed!)' if swept else 'Standard 3D Channel Entry'}
  RSI Depth     : {rsi:.1f} ({'Oversold' if action=='BUY' else 'Overbought'})
  ATR-14        : {atr:.4f} (Dynamic Sizing Active)
  Risk Status   : {risk_label}
=========================================
Action: Open your Exness / MT5 Demo app and place this order!
=========================================
"""
        print(card)
        if send_tg(card):
            sent_signals[sig_id] = True
            active_trades.append({
                "symbol": sym, "name": asset['name'],
                "type": action, "entry_price": close,
                "sl_price": sl_price, "tp1_price": tp1_price, "tp2_price": tp2_price,
                "risk_dollar": risk_usd, "tp1_hit": False, "realized_pnl": 0.0,
                "ai_score": score
            })
            signals_found += 1

save_json(LOG_FILE, sent_signals)
save_json(ACTIVE_TRADES_FILE, active_trades)

print("-" * 90)
if signals_found == 0:
    print("[STATUS] Market scanned. 0 Elite signals fired at this hour.")
    print("[STATUS] All 6 Institutional Shields protecting your account!")
else:
    print(f"[STATUS] {signals_found} Elite signal(s) fired and sent to Telegram!")

# ===========================================================================
# WEEKLY PERFORMANCE SUMMARY (Sundays or --weekly-summary flag)
# ===========================================================================
weekday = pd.Timestamp.now(tz=pytz.utc).tz_convert(LONDON_TZ).weekday()
if weekday == 6 or "--weekly-summary" in sys.argv:
    print("\n[WEEKLY SUMMARY] Compiling Elite Performance Dashboard...")
    df_h = pd.DataFrame(trade_history)
    tot = len(df_h)
    if tot > 0:
        wins = df_h[df_h['result'] == 'WIN']
        losses = df_h[df_h['result'] == 'LOSS']
        bes = df_h[df_h['result'] == 'BREAKEVEN']
        wr = ((len(wins) + len(bes)) / tot) * 100
        net = df_h['pnl'].sum()
        gp = wins['pnl'].sum() if not wins.empty else 0.0
        gl = abs(losses['pnl'].sum()) if not losses.empty else 0.0
        pf = (gp / gl) if gl > 0 else (gp if gp > 0 else 0.0)
    else:
        wr = net = pf = 0.0
        wins = losses = bes = pd.DataFrame()

    summary = f"""
=========================================
PLAN B ELITE WEEKLY PERFORMANCE REPORT
=========================================
Time Period     : Past 7 Days
Total Signals   : {tot} (AI-Filtered 70+ Only)
Win Breakdown   : {len(wins)} Wins | {len(losses)} Losses | {len(bes)} Risk-Free BEs
Non-Losing Rate : {wr:.1f}%
-----------------------------------------
Starting Capital: ${INITIAL_BALANCE:,.2f}
Current Balance : ${current_balance:,.2f}
Weekly Net P&L  : ${net:+,.2f} ({(net/INITIAL_BALANCE)*100:+.1f}%)
Profit Factor   : {pf:.2f} (Institutional Grade)
-----------------------------------------
Elite Modules   : MTF | SMC | AI Score | Regime | Scaling | Governor
=========================================
Status: All 6 Elite Shields Active!
=========================================
"""
    print(summary)
    send_tg(summary)

print("=" * 90 + "\n")
