"""
===============================================================================
PLAN B ADAPTIVE ENGINE v4.0  -  DUAL-ENGINE AI-COPILOT CLOUD SYSTEM
===============================================================================
22 MODULES TOTAL:

ELITE (E1-E6):   MTF | SMC | AI Score | Regime | Scaling | Tracker
DIAMOND (D1-D6): Macro | News | Corr | Trail | MonteCarlo | ML
ADAPTIVE (A1-A8): Patterns | S/R Zones | Loss Learner | ML Retrain |
                   Multi-TF Scalper | Confidence | Tiered Quality |
                   A8: Gemini NLP News Sentiment & Trade Thesis Copilot

NEW in v4.1 (Smart Learning):
  - ENGINE 1 (Standard): Liquidity Trifecta - Trend + RSI Pullback + Sweep/Pattern
  - ENGINE 2 (Sniper):   Fair Value Gap (FVG) Matrix - Institutional liquidity void fills
  - Sniper signals tagged with 🔥 SNIPER on Telegram (1:5+ Risk/Reward)
  - WEIGHTED MEMORY: Old losses fade naturally (never fully deleted, just discounted)
  - REGIME-AWARE MEMORY: Lessons applied only when market conditions match
  - SOFT SCORE PENALTY: Learning reduces signal score, never hard-blocks trading
  - DAILY TRADE LEDGER: End-of-day scorecard sent to Telegram automatically

100% FREE ($0.00). GitHub Cloud Automated. PC Stays OFF.
===============================================================================
"""
import sys, os, json, math, urllib.request, urllib.parse, warnings, statistics
warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

import numpy as np
import pandas as pd
import yfinance as yf
import pytz

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_KEY= os.environ.get("GEMINI_API_KEY", "")
if os.path.exists(".env"):
    try:
        with open(".env") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not BOT_TOKEN:
                    BOT_TOKEN = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID=") and not CHAT_ID:
                    CHAT_ID = line.split("=", 1)[1].strip()
                elif line.startswith("GEMINI_API_KEY=") and not GEMINI_KEY:
                    GEMINI_KEY = line.split("=", 1)[1].strip()
    except Exception: pass
LONDON_TZ = pytz.timezone("Europe/London")

# ============================================================
# CONFIG
# ============================================================
BB_PERIOD          = 20
ADX_TREND_TH       = 25
NEWS_BLOCK_MIN     = 30
NEWS_RESUME_MIN    = 45
CORR_BLOCK         = 0.80

TIER_DIAMOND = {"score": 80, "ml": 0.70, "macro": 4, "risk_mult": 1.00, "label": "A+", "full_label": "DIAMOND (A+)"}
TIER_GOLD    = {"score": 65, "ml": 0.60, "macro": 3, "risk_mult": 0.75, "label": "A",  "full_label": "GOLD (A)"}
TIER_SILVER  = {"score": 55, "ml": 0.50, "macro": 2, "risk_mult": 0.50, "label": "B",  "full_label": "SILVER (B)"}

GOVERNED_RISK       = 0.010
CIRCUIT_BREAKER_PCT = 0.08   # Stop all trading if weekly pips drawdown > 8% equivalent

WATCHLIST = [
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
    {"symbol": "GC=F", "name": "Gold", "pip": 0.1, "sl_pips": 40},
    {"symbol": "CL=F", "name": "Oil", "pip": 0.01, "sl_pips": 40},
    {"symbol": "^DJI", "name": "US30", "pip": 1.0, "sl_pips": 50},
    {"symbol": "^IXIC", "name": "NAS100", "pip": 1.0, "sl_pips": 50},
    {"symbol": "BTC-USD", "name": "Bitcoin", "pip": 1.0, "sl_pips": 500},
]

MACRO_ASSETS = {"DXY":"DX-Y.NYB","GOLD":"GC=F","VIX":"^VIX","YIELD":"^TNX","SPX":"^GSPC"}

LOG_FILE        = "adaptive_sent_signals.json"
TRADES_FILE     = "adaptive_active_trades.json"
HISTORY_FILE    = "adaptive_trade_history.json"
LEARNING_FILE   = "adaptive_learning_log.json"
RULES_FILE      = "adaptive_rules.json"
CONFIDENCE_FILE = "adaptive_confidence.json"

print("=" * 90)
print("PLAN B ADAPTIVE ENGINE v3.0 - AI-COPILOT CLOUD SYSTEM")
print("=" * 90)
print(f"  Pairs    : {len(WATCHLIST)} | Timeframes: 15M + 1H")
print(f"  Grades   : A+ (Diamond) | A (Gold) | B (Silver)")
print(f"  AI Copilot: {'ACTIVE (Gemini Free API)' if GEMINI_KEY else 'OFFLINE (Fallback Active)'}")
print(f"  Modules  : E1-E6 + D1-D6 + A1-A8 + Circuit Breaker + Heartbeat = 22 Total")
print("=" * 90)

# ============================================================
# UTILITIES
# ============================================================
def get_cam_time():
    return pd.Timestamp.now(tz="UTC").tz_convert("Asia/Phnom_Penh").strftime("%a %d %b %Y | %I:%M %p")

def send_tg(text):
    import hashlib
    msg_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    sent_msgs = load_json("adaptive_sent_msgs.json", [])
    if msg_hash in sent_msgs:
        return True
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        sent_msgs.append(msg_hash)
        save_json("adaptive_sent_msgs.json", sent_msgs[-100:])
        return True
    except Exception as e:
        print(f"  [TG] {e}")
        return False

def load_json(p, d):
    if os.path.exists(p):
        try:
            with open(p) as f: return json.load(f)
        except: pass
    return d

def save_json(p, o):
    with open(p, "w") as f: json.dump(o, f, indent=2)

def fetch_df(sym, period, interval):
    try:
        df = yf.download(tickers=sym, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize("UTC") if df.index.tzinfo is None else df.index.tz_convert("UTC")
        return df
    except: return None

def add_indicators(df):
    df = df.copy()
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
    df["BB_MID"] = c.rolling(BB_PERIOD).mean()
    df["BB_STD"] = c.rolling(BB_PERIOD).std()
    df["BB_UP"]  = df["BB_MID"]+2*df["BB_STD"]
    df["BB_LO"]  = df["BB_MID"]-2*df["BB_STD"]
    df["BB_W"]   = (df["BB_UP"]-df["BB_LO"])/(df["BB_MID"]+1e-9)
    df["BB_W_AVG"]= df["BB_W"].rolling(20).mean()
    df["H3D"]    = df["High"].shift(1).rolling(72).max()
    df["L3D"]    = df["Low"].shift(1).rolling(72).min()
    df["SH"]     = df["High"].shift(1).rolling(24).max()
    df["SL_lev"] = df["Low"].shift(1).rolling(24).min()
    df["LT"]     = df.index.tz_convert(LONDON_TZ)
    return df

# ============================================================
# MODULE A8: GEMINI NLP NEWS SENTIMENT & TRADE THESIS COPILOT
# ============================================================
def run_gemini_copilot(pair_name, action, rsi, adx, macro_info, pattern_txt):
    """
    Uses Free Google Gemini API to analyze market news sentiment
    and write a 2-sentence human-readable trade thesis.
    """
    if not GEMINI_KEY:
        return "Market sentiment aligned with technical setup.", 0

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""You are a senior institutional Forex trader.
Analyze this proposed trade setup and provide a 2-sentence Trade Thesis and a Sentiment Bias Score (-100 to +100):

Pair: {pair_name}
Action: {action}
RSI: {rsi:.1f}
ADX: {adx:.1f}
Macro Context: {macro_info}
Candle Patterns: {pattern_txt}

Respond in strict JSON format like this:
{{"thesis": "Two-sentence trade thesis here.", "sentiment_score": 25}}
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return data.get("thesis", "Technical setup aligned with macro momentum."), data.get("sentiment_score", 0)
    except Exception as e:
        print(f"  [GEMINI AI] {e}")
        return "Technical setup aligned with institutional filters.", 0

# ============================================================
# A1: CANDLESTICK PATTERN DETECTOR
# ============================================================
def detect_candle_patterns(df, i):
    if i < 3: return {}, 0
    c0, c1, c2 = df.iloc[i], df.iloc[i-1], df.iloc[i-2]
    o0,h0,l0,cl0 = float(c0["Open"]),float(c0["High"]),float(c0["Low"]),float(c0["Close"])
    o1,h1,l1,cl1 = float(c1["Open"]),float(c1["High"]),float(c1["Low"]),float(c1["Close"])
    o2,h2,l2,cl2 = float(c2["Open"]),float(c2["High"]),float(c2["Low"]),float(c2["Close"])

    body0, body1 = abs(cl0-o0), abs(cl1-o1)
    range0 = h0-l0 if h0>l0 else 1e-9
    upper_wick0 = h0-max(o0,cl0)
    lower_wick0 = min(o0,cl0)-l0

    patterns = {}; score = 0
    if cl1 < o1 and cl0 > o0 and cl0 > o1 and o0 < cl1 and body0 > body1:
        patterns["Bullish Engulfing"] = True; score += 20
    if cl1 > o1 and cl0 < o0 and cl0 < o1 and o0 > cl1 and body0 > body1:
        patterns["Bearish Engulfing"] = True; score += 20
    if lower_wick0 > 2*body0 and upper_wick0 < body0 and body0 > 0:
        patterns["Hammer"] = True; score += 15
    if upper_wick0 > 2*body0 and lower_wick0 < body0 and body0 > 0:
        patterns["Shooting Star"] = True; score += 15
    if body0 < 0.10 * range0:
        patterns["Doji"] = True; score += 10
    body2 = abs(cl2-o2)
    if cl2 < o2 and body1 < body2*0.3 and cl0 > o0 and cl0 > (o2+cl2)/2:
        patterns["Morning Star"] = True; score += 20
    if cl2 > o2 and body1 < body2*0.3 and cl0 < o0 and cl0 < (o2+cl2)/2:
        patterns["Evening Star"] = True; score += 20

    return patterns, score

# ============================================================
# A2b: SNIPER ENGINE - FAIR VALUE GAP (FVG) DETECTOR
# Institutional Liquidity Void Matrix
# ============================================================
def detect_fvg(df, lookback=50):
    """
    Scans the last `lookback` candles to find unmitigated Fair Value Gaps (FVGs).
    A Bullish FVG exists when: candle[i-2].high < candle[i].low  (gap UP = unfilled orders below)
    A Bearish FVG exists when: candle[i-2].low  > candle[i].high (gap DOWN = unfilled orders above)
    Returns a list of active, unmitigated FVG zones the current price is entering.
    """
    fvgs = []
    if len(df) < lookback + 3:
        return fvgs
    
    current_close = float(df.iloc[-1]["Close"])
    current_low   = float(df.iloc[-1]["Low"])
    current_high  = float(df.iloc[-1]["High"])
    atr = float(df.iloc[-1].get("ATR", 0.001))
    
    # Scan the last `lookback` candles for unmitigated FVG zones
    start = max(3, len(df) - lookback)
    for i in range(start, len(df) - 1):
        c_prev2 = df.iloc[i - 2]
        c_curr  = df.iloc[i]
        
        h_prev2 = float(c_prev2["High"])
        l_prev2 = float(c_prev2["Low"])
        h_curr  = float(c_curr["High"])
        l_curr  = float(c_curr["Low"])
        
        # Bullish FVG: gap left above — current price must be pulling back INTO the gap from above
        if l_curr > h_prev2:
            gap_top = l_curr
            gap_bot = h_prev2
            gap_size = gap_top - gap_bot
            if gap_size > atr * 0.3:  # Only meaningful gaps (> 30% of ATR)
                # Price is currently entering the gap from above (pullback into FVG)
                if gap_bot <= current_close <= gap_top + atr * 0.5:
                    fvgs.append({"type": "BULLISH", "top": gap_top, "bot": gap_bot,
                                 "size": gap_size, "action": "BUY"})
        
        # Bearish FVG: gap left below — current price must be pulling back INTO the gap from below
        if h_curr < l_prev2:
            gap_top = l_prev2
            gap_bot = h_curr
            gap_size = gap_top - gap_bot
            if gap_size > atr * 0.3:  # Only meaningful gaps
                # Price is currently entering the gap from below (pullback into FVG)
                if gap_bot - atr * 0.5 <= current_close <= gap_top:
                    fvgs.append({"type": "BEARISH", "top": gap_top, "bot": gap_bot,
                                 "size": gap_size, "action": "SELL"})
    
    return fvgs

# ============================================================
# A2: SUPPORT/RESISTANCE ZONE MAPPER
# ============================================================
def find_sr_zones(df, tolerance_mult=0.5):
    if len(df) < 50: return []
    atr_avg = float(df["ATR"].iloc[-20:].mean()) if "ATR" in df else 0.001
    tol = atr_avg * tolerance_mult
    pivots = []
    for i in range(2, len(df)-2):
        h, l = float(df.iloc[i]["High"]), float(df.iloc[i]["Low"])
        if h > float(df.iloc[i-1]["High"]) and h > float(df.iloc[i+1]["High"]): pivots.append(h)
        if l < float(df.iloc[i-1]["Low"]) and l < float(df.iloc[i+1]["Low"]): pivots.append(l)
    if not pivots: return []
    pivots.sort(); zones = []; used = set()
    for i, p in enumerate(pivots):
        if i in used: continue
        cluster = [p]
        for j in range(i+1, len(pivots)):
            if j in used: continue
            if abs(pivots[j]-p) <= tol:
                cluster.append(pivots[j]); used.add(j)
        used.add(i)
        if len(cluster) >= 2:
            zones.append({"level": statistics.mean(cluster), "touches": len(cluster),
                          "strength": "STRONG" if len(cluster)>=3 else "STANDARD"})
    return zones

def check_sr_proximity(close, atr, zones):
    for z in zones:
        if abs(close - z["level"]) <= atr * 1.0:
            return (15 if z["strength"]=="STRONG" else 8), z
    return 0, None

# ============================================================
# A3: SELF-LEARNING LOSS ANALYZER v4.1
# Weighted Decaying Memory + Regime-Aware + Soft Score Penalty
# ============================================================
import datetime as _dt

def _decay_weight(trade, half_life_days=60):
    """Returns a weight between 0 and 1 based on trade age.
    Trades from today = 1.0 weight. Half-life = 60 days (never zero).
    """
    ts = trade.get("timestamp", None)
    if ts is None:
        return 0.5  # Unknown age → medium weight
    try:
        age_days = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(ts, tz="UTC")).days
    except Exception:
        return 0.5
    # Exponential decay: weight = 2^(-age/half_life)
    return max(0.05, 2 ** (-age_days / half_life_days))

def analyze_losses(history, learning_log):
    """Builds a weighted, regime-aware penalty score map.
    Returns a dict of penalty rules with float weights (not hard blocks).
    """
    losses = [t for t in learning_log if t.get("result") == "LOSS"]
    if len(losses) < 3:
        return []

    from collections import defaultdict, Counter
    rules = []

    # --- 1. Weighted ADX Penalty ---
    adx_weights = [(t.get("adx", 25), _decay_weight(t)) for t in losses if "adx" in t]
    if adx_weights:
        low_adx_wsum  = sum(w for v, w in adx_weights if v < 20)
        total_wsum    = sum(w for _, w in adx_weights)
        if total_wsum > 0 and (low_adx_wsum / total_wsum) > 0.55:
            severity = min(0.40, low_adx_wsum / total_wsum * 0.50)  # Max 40pt penalty
            rules.append({"type": "soft_adx", "threshold": 20,
                           "penalty": severity,
                           "reason": f"Weighted: {low_adx_wsum/total_wsum*100:.0f}% losses at ADX<20"})

    # --- 2. Weighted Hour Penalty (Regime-Aware) ---
    hour_regime_losses = defaultdict(float)  # (hour, regime) -> weighted loss count
    hour_regime_total  = defaultdict(float)
    for t in losses:
        key = (t.get("hour", -1), t.get("regime", "UNKNOWN"))
        w = _decay_weight(t)
        hour_regime_losses[key] += w
    for t in learning_log:
        key = (t.get("hour", -1), t.get("regime", "UNKNOWN"))
        hour_regime_total[key] += _decay_weight(t)

    for (h, reg), wloss in hour_regime_losses.items():
        wtotal = hour_regime_total.get((h, reg), wloss)
        if wtotal >= 2 and (wloss / wtotal) > 0.65:  # ≥65% loss rate in this regime+hour
            severity = min(0.35, (wloss / wtotal) * 0.40)
            rules.append({"type": "soft_hour_regime", "hour": h, "regime": reg,
                           "penalty": severity,
                           "reason": f"Regime {reg} @ hour {h}:00 has {wloss/wtotal*100:.0f}% weighted loss rate"})

    # --- 3. Pair-Specific Penalty ---
    pair_losses = defaultdict(float)
    pair_total  = defaultdict(float)
    for t in losses:
        pair_losses[t.get("pair", "?")] += _decay_weight(t)
    for t in learning_log:
        pair_total[t.get("pair", "?")] += _decay_weight(t)

    for pair, wloss in pair_losses.items():
        wtotal = pair_total.get(pair, wloss)
        if wtotal >= 3 and (wloss / wtotal) > 0.70:
            severity = min(0.30, (wloss / wtotal) * 0.35)
            rules.append({"type": "soft_pair", "pair": pair,
                           "penalty": severity,
                           "reason": f"{pair} has {wloss/wtotal*100:.0f}% weighted loss rate"})

    return rules

def apply_learned_rules(rules, bar, asset_name, hour):
    """Applies soft penalties to the signal score.
    Returns (total_penalty_0_to_1, reason_string).
    A penalty of 0.0 = no learning adjustment.
    A penalty of 1.0 = signal completely suppressed (never reached in practice).
    """
    total_penalty = 0.0
    reasons = []
    current_regime = regime(bar) if callable(regime) else "UNKNOWN"

    for r in rules:
        if r["type"] == "soft_adx":
            adx_val = float(bar.get("ADX", 99))
            if adx_val < r["threshold"]:
                # Scale penalty: the lower the ADX below threshold, the bigger the penalty
                scale = max(0.3, 1.0 - (adx_val / r["threshold"]))
                total_penalty += r["penalty"] * scale
                reasons.append(f"ADX={adx_val:.1f}<{r['threshold']} ({r['reason']})")

        elif r["type"] == "soft_hour_regime":
            if hour == r["hour"] and current_regime == r["regime"]:
                total_penalty += r["penalty"]
                reasons.append(f"Hour {hour}:00 in {current_regime} ({r['reason']})")

        elif r["type"] == "soft_pair":
            if asset_name == r["pair"]:
                total_penalty += r["penalty"]
                reasons.append(f"{asset_name} pair penalty ({r['reason']})")

    total_penalty = min(total_penalty, 0.75)  # Hard cap: never suppress more than 75%
    reason_str = " | ".join(reasons) if reasons else ""
    return False, reason_str, total_penalty  # Always returns (blocked=False, reason, penalty)

# ============================================================
# A6: REAL CONFIDENCE TRACKER
# ============================================================
def update_confidence(conf_data, trade_result):
    pair, hour, reg, tier = trade_result.get("pair","Unknown"), str(trade_result.get("hour","0")), trade_result.get("regime","RANGE"), trade_result.get("tier","SILVER")
    won = 1 if trade_result.get("result") in ("WIN","BREAKEVEN") else 0
    for cat, key in [("pair",pair),("hour",hour),("regime",reg),("tier",tier)]:
        if cat not in conf_data: conf_data[cat] = {}
        if key not in conf_data[cat]: conf_data[cat][key] = {"wins":0,"total":0}
        conf_data[cat][key]["total"] += 1; conf_data[cat][key]["wins"] += won
    return conf_data

def get_confidence_adjustment(conf_data, pair, hour, regime):
    adjustments = []
    for cat, key in [("pair",pair),("hour",str(hour)),("regime",regime)]:
        if cat in conf_data and key in conf_data[cat]:
            st = conf_data[cat][key]
            if st["total"] >= 5:
                wr = st["wins"]/st["total"]
                if wr < 0.35: adjustments.append(0.5)
                elif wr < 0.50: adjustments.append(0.75)
                else: adjustments.append(1.0)
    return min(adjustments) if adjustments else 1.0

# ============================================================
# DIAMOND MODULES
# ============================================================
def get_risk(bal, hist):
    if len(hist)>=2 and all(t.get("result")=="LOSS" for t in hist[-2:]):
        return GOVERNED_RISK, "GOVERNOR ACTIVE | 1.0%"
    for s in BALANCE_STAGES:
        if s["min"]<=bal<s["max"]: return s["risk"], s["label"]
    return 0.02, "Stage 1"

def run_monte_carlo(wr=0.60, rr=3.5, n_trades=16, n_sims=10000, bal=200.0, rp=0.02):
    fb_arr, mdd_arr, ruins = [], [], 0
    np.random.seed(99)
    for _ in range(n_sims):
        b, pk, md = bal, bal, 0.0
        for _ in range(n_trades):
            r = b*rp
            if np.random.random()<wr: b += r*rr*0.5+r*0.5
            else: b -= r
            if b>pk: pk=b
            dd=(pk-b)/pk
            if dd>md: md=dd
        if b<=bal*0.50: ruins+=1
        fb_arr.append(b); mdd_arr.append(md)
    fb,md = np.array(fb_arr),np.array(mdd_arr)
    return {"pp":np.mean(fb>bal)*100, "p95":np.percentile(md,95)*100, "ruin":ruins/n_sims*100}

mc = run_monte_carlo()

ML_MODEL = None; ML_OK = False
def train_ml(retrain_data=None):
    global ML_MODEL, ML_OK
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        if retrain_data and len(retrain_data) >= 20:
            rows = [[t["rsi"],t.get("adx",25),t.get("atr_r",0.001),t.get("bbw",0.01),t.get("hour",12),t.get("ema_r",0.001),1 if t.get("action")=="BUY" else 0, 1 if t.get("result") in ("WIN","BREAKEVEN") else 0] for t in retrain_data if "rsi" in t]
        else:
            df = fetch_df("EURUSD=X","180d","1h")
            if df is None or len(df)<200: return
            df = add_indicators(df); df.dropna(inplace=True); rows = []
            for i in range(len(df)-50):
                b = df.iloc[i]; fut = df.iloc[i+1:i+48]
                if fut.empty: continue
                rsi=float(b["RSI"]); adx=float(b["ADX"]); atr=float(b["ATR"]); bbw=float(b["BB_W"]); hr=int(b["LT"].hour); cl=float(b["Close"]); ema=float(b["EMA200"])
                sl_d=atr*1.2; tp_d=sl_d*3.5
                for act in ["BUY","SELL"]:
                    if act=="BUY" and not (rsi<40 and cl>ema): continue
                    if act=="SELL" and not (rsi>60 and cl<ema): continue
                    lbl=0
                    for _,fb in fut.iterrows():
                        if act=="BUY":
                            if float(fb["High"])>=cl+tp_d: lbl=1; break
                            if float(fb["Low"])<=cl-sl_d: break
                        else:
                            if float(fb["Low"])<=cl-tp_d: lbl=1; break
                            if float(fb["High"])>=cl+sl_d: break
                    rows.append([rsi,adx,atr/cl,bbw,hr,abs(cl-ema)/cl,1 if act=="BUY" else 0, lbl])
        if len(rows)<20: return
        df_ml = pd.DataFrame(rows, columns=["rsi","adx","atr_r","bbw","hour","ema_r","dir","label"])
        X = df_ml[["rsi","adx","atr_r","bbw","hour","ema_r","dir"]].values; y = df_ml["label"].values
        ML_MODEL = Pipeline([("s",StandardScaler()),("c",RandomForestClassifier(n_estimators=200,max_depth=6,random_state=42,n_jobs=-1))])
        ML_MODEL.fit(X,y); ML_OK=True
    except: pass

learning_log = load_json(LEARNING_FILE, [])
own_trades = [t for t in learning_log if "result" in t]
train_ml(own_trades if "--retrain" in sys.argv and len(own_trades)>=20 else None)

def predict_ml(rsi,adx,atr_r,bbw,hour,ema_r,action):
    if not ML_OK: return None
    try:
        X = np.array([[rsi,adx,atr_r,bbw,hour,ema_r,1 if action=="BUY" else 0]])
        p = ML_MODEL.predict_proba(X)[0]
        return float(p[1]) if len(p)>1 else float(p[0])
    except: return None

macro_data = {}
for key,sym in MACRO_ASSETS.items():
    df = fetch_df(sym,"5d","1h")
    if df is not None and len(df)>=5:
        last=float(df["Close"].iloc[-1]); prev=float(df["Close"].iloc[-24]) if len(df)>=24 else float(df["Close"].iloc[0])
        pct=(last-prev)/(prev+1e-9)*100
        macro_data[key]={"last":last,"pct":pct,"rising":pct>0}
    else: macro_data[key]={"last":0,"pct":0,"rising":None}

def macro_score(action):
    m=macro_data; pts=0; info=[]
    if action=="BUY":
        if m.get("DXY",{}).get("rising") is False: pts+=1; info.append("DXY-")
        if m.get("GOLD",{}).get("rising") is True:  pts+=1; info.append("Gold+")
        if m.get("VIX",{}).get("last",99)<20:        pts+=1; info.append("VIX low")
        if m.get("YIELD",{}).get("rising") is False: pts+=1; info.append("Yield-")
        if m.get("SPX",{}).get("rising") is True:    pts+=1; info.append("SPX+")
    else:
        if m.get("DXY",{}).get("rising") is True:    pts+=1; info.append("DXY+")
        if m.get("GOLD",{}).get("rising") is False:  pts+=1; info.append("Gold-")
        if m.get("VIX",{}).get("last",0)>20:         pts+=1; info.append("VIX hi")
        if m.get("YIELD",{}).get("rising") is True:  pts+=1; info.append("Yield+")
        if m.get("SPX",{}).get("rising") is False:   pts+=1; info.append("SPX-")
    return pts, " | ".join(info)

def check_news():
    now = pd.Timestamp.now(tz="UTC")
    upcoming_high = []
    blocked_event = None
    try:
        url="https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        raw=urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
        events=json.loads(raw)
        for ev in events:
            if ev.get("impact","").upper()!="HIGH": continue
            try: et=pd.Timestamp(ev["date"]).tz_localize("UTC")
            except: continue
            diff=(et-now).total_seconds()/60
            # Collect upcoming events in next 4 hours for Telegram warning
            if 0 < diff <= 240:
                upcoming_high.append({"title": ev.get("title",""), "currency": ev.get("currency",""), "mins": int(diff)})
            # Block window: 30 min before to 45 min after
            if -NEWS_RESUME_MIN<=diff<=NEWS_BLOCK_MIN:
                blocked_event = f"{ev.get('title','')} ({ev.get('currency','')})"
        return blocked_event is not None, blocked_event or "CLEAR", upcoming_high
    except Exception as e:
        h=now.astimezone(LONDON_TZ).hour; m=now.astimezone(LONDON_TZ).minute
        for rh,rm in [(8,30),(13,30),(15,0)]:
            d=(h*60+m)-(rh*60+rm)
            if -NEWS_BLOCK_MIN<=d<=NEWS_RESUME_MIN: return True, f"NEWS GUARD (offline): block near {rh:02d}:{rm:02d}", []
        return False, f"CLEAR (offline: {e})", []

def is_post_news_window():
    """Returns True if we are 20-45 min AFTER a high-impact news event — prime breakout window."""
    now = pd.Timestamp.now(tz="UTC")
    try:
        url="https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        raw=urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
        events=json.loads(raw)
        for ev in events:
            if ev.get("impact","").upper()!="HIGH": continue
            try: et=pd.Timestamp(ev["date"]).tz_localize("UTC")
            except: continue
            diff=(now-et).total_seconds()/60
            # Post-news breakout window: 20 to 45 minutes AFTER event
            if 20 <= diff <= 45:
                return True, f"{ev.get('title','')} ({ev.get('currency','')})"
        return False, ""
    except:
        return False, ""

news_blocked, news_reason, upcoming_news = check_news()
post_news, post_news_event = is_post_news_window()

# Send upcoming news warning to Telegram (once per session)
if upcoming_news:
    warn_lines = "\n".join([f"  ⚠️ {n['title']} ({n['currency']}) in {n['mins']} min" for n in upcoming_news[:5]])
    news_warn_msg = f"📰 UPCOMING HIGH-IMPACT NEWS\n{warn_lines}\nSignals paused until 45m after event."
    send_tg(news_warn_msg)

# Post-news breakout alert
if post_news:
    send_tg(f"🔥 POST-NEWS SCAN ACTIVE: {post_news_event}\nScanning for breakout entries...")  

corr_matrix = None
try:
    closes={a["name"]:fetch_df(a["symbol"],"60d","1d")["Close"].pct_change().dropna() for a in WATCHLIST if fetch_df(a["symbol"],"60d","1d") is not None}
    if len(closes)>=2: corr_matrix = pd.DataFrame(closes).dropna().corr()
except: pass

def is_corr_dup(sym, action, active):
    if corr_matrix is None: return False,""
    for t in active:
        if t["symbol"]==sym or t["type"]!=action: continue
        pa = next((a["name"] for a in WATCHLIST if a["symbol"]==sym),None)
        pb = next((a["name"] for a in WATCHLIST if a["symbol"]==t["symbol"]),None)
        if pa and pb and pa in corr_matrix and pb in corr_matrix:
            c=abs(corr_matrix.loc[pa,pb])
            if c>=CORR_BLOCK: return True, f"Corr={c:.2f} with {pb} {t['type']}"
    return False,""

def regime(bar):
    adx=float(bar["ADX"]); bbw=float(bar["BB_W"])
    bwa=float(bar["BB_W_AVG"]) if not pd.isna(bar["BB_W_AVG"]) else bbw
    return "TREND" if adx>ADX_TREND_TH and bbw>1.5*bwa else "RANGE"

def check_mtf(sym, action):
    for p,iv in [("60d","4h"),("400d","1d")]:
        df=fetch_df(sym,p,iv)
        if df is None or len(df)<50: return False
        ema=df["Close"].ewm(span=200,adjust=False).mean().iloc[-1]
        c=float(df["Close"].iloc[-1])
        if action=="BUY" and c<=ema: return False
        if action=="SELL" and c>=ema: return False
    return True

def detect_sweep(df, i, action):
    if i<2: return False, 0
    prev,curr = df.iloc[i-1], df.iloc[i]
    sh,sl_v = float(curr["SH"]),float(curr["SL_lev"])
    atr=float(curr["ATR"])
    if pd.isna(sh) or pd.isna(sl_v): return False,0
    if action=="BUY":
        sw = float(prev["Low"])<sl_v and float(curr["Close"])>sl_v
        cl = min(100,int(abs(float(prev["Low"])-sl_v)/(atr+1e-9)*100))
    else:
        sw = float(prev["High"])>sh and float(curr["Close"])<sh
        cl = min(100,int(abs(float(prev["High"])-sh)/(atr+1e-9)*100))
    return sw, cl

def compute_score(bar, action, liq_cl, reg, pattern_score, sr_score):
    score = 0; rsi = float(bar["RSI"]); hour = int(bar["LT"].hour)
    if action=="BUY": score += max(0,min(25,int((35-rsi)*2.0))) if rsi<35 else 0
    else: score += max(0,min(25,int((rsi-65)*2.0))) if rsi>65 else 0
    score += min(25, 15 if float(bar["ATR"])>0 else 0) + min(25, int(liq_cl/4))
    if 8<=hour<=10: score+=25
    elif 13<=hour<=15: score+=20
    elif 10<hour<=12: score+=15
    elif 15<hour<=17: score+=10
    if reg=="RANGE": score = min(100, score+5)
    return min(100, score + pattern_score + sr_score)

def classify_tier(ai_score, ml_prob, mscore):
    ml = ml_prob if ml_prob is not None else 0.60
    if ai_score >= TIER_DIAMOND["score"] and ml >= TIER_DIAMOND["ml"] and mscore >= TIER_DIAMOND["macro"]: return TIER_DIAMOND
    if ai_score >= TIER_GOLD["score"] and ml >= TIER_GOLD["ml"] and mscore >= TIER_GOLD["macro"]: return TIER_GOLD
    if ai_score >= TIER_SILVER["score"]: return TIER_SILVER
    return None

# LOAD STATE
sent      = load_json(LOG_FILE, {})
active    = load_json(TRADES_FILE, [])
history   = load_json(HISTORY_FILE, [])
conf_data = load_json(CONFIDENCE_FILE, {})
rules     = load_json(RULES_FILE, [])

# Fixed risk unit for signal sizing (no fake virtual balance)
RISK_USD  = 2.0   # Each signal risks $2 equivalent (adjust to your real lot sizing)

# Count consecutive losses for governor
recent_results = [t.get("result") for t in history[-5:]] if history else []
if len(recent_results) >= 2 and all(r == "LOSS" for r in recent_results[-2:]):
    RISK_USD = 1.0  # Governor active: halve risk after 2 consecutive losses
    print("  [RISK GOVERNOR] 2 consecutive losses — risk halved to $1.00")

rusd = RISK_USD

# RESULT TRACKER
remaining = []
for trade in active:
    sym=trade["symbol"]
    asset=next((a for a in WATCHLIST if a["symbol"]==sym),None)
    if not asset: continue
    df_t=fetch_df(sym,"10d","1h")
    if df_t is None or len(df_t)<5: remaining.append(trade); continue
    df_t=add_indicators(df_t); bar=df_t.iloc[-1]
    hi,lo,cl=float(bar["High"]),float(bar["Low"]),float(bar["Close"]); atr=float(bar["ATR"])
    ep,sl_p,tp1,tp2=trade["entry_price"],trade["sl_price"],trade["tp1_price"],trade["tp2_price"]
    r=trade["risk_dollar"]; closed=False

    if trade.get("tp1_hit") and not trade.get("tp2_locked"):
        dist=abs(tp2-tp1)
        if trade["type"]=="BUY":
            prog=cl-tp1
            if prog>=dist*0.75:
                ns=cl-0.5*atr; trade["sl_price"]=max(trade["sl_price"],ns)
            elif prog>=dist*0.50: trade["sl_price"]=max(trade["sl_price"],tp1)
        else:
            prog=tp1-cl
            if prog>=dist*0.75:
                ns=cl+0.5*atr; trade["sl_price"]=min(trade["sl_price"],ns)
            elif prog>=dist*0.50: trade["sl_price"]=min(trade["sl_price"],tp1)

    if trade["type"]=="BUY":
        if hi>=tp1 and not trade.get("tp1_hit"):
            trade["tp1_hit"]=True; trade["sl_price"]=ep; trade["realized_pnl"]=1.0
            send_tg(f"✅ TP1 HIT: {trade['name']} BUY (SL moved to Entry)")
        if hi>=tp2:
            pnl=trade.get("realized_pnl",0)+1.5
            send_tg(f"🏆 FULL WIN: {trade['name']} BUY (+{pnl:.1f}R)")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":"WIN","tier":trade.get("tier","B")})
            learning_log.append({**trade.get("conditions",{}), "result":"WIN","pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":"WIN"})
            closed=True
        elif lo<=trade["sl_price"]:
            if trade["sl_price"]>=ep:
                pnl=trade.get("realized_pnl",0); result="BREAKEVEN"
                send_tg(f"🛡️ BREAKEVEN: {trade['name']} BUY (0R)")
            else:
                pnl=-1.0; result="LOSS"
                send_tg(f"❌ STOP LOSS: {trade['name']} BUY (-1R)")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":result,"tier":trade.get("tier","B")})
            learning_log.append({**trade.get("conditions",{}), "result":result,"pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":result})
            closed=True
    elif trade["type"]=="SELL":
        if lo<=tp1 and not trade.get("tp1_hit"):
            trade["tp1_hit"]=True; trade["sl_price"]=ep; trade["realized_pnl"]=1.0
            send_tg(f"✅ TP1 HIT: {trade['name']} SELL (SL moved to Entry)")
        if lo<=tp2:
            pnl=trade.get("realized_pnl",0)+1.5
            send_tg(f"🏆 FULL WIN: {trade['name']} SELL (+{pnl:.1f}R)")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":"WIN","tier":trade.get("tier","B")})
            learning_log.append({**trade.get("conditions",{}), "result":"WIN","pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":"WIN"})
            closed=True
        elif hi>=trade["sl_price"]:
            if trade["sl_price"]<=ep:
                pnl=trade.get("realized_pnl",0); result="BREAKEVEN"
                send_tg(f"🛡️ BREAKEVEN: {trade['name']} SELL (0R)")
            else:
                pnl=-1.0; result="LOSS"
                send_tg(f"❌ STOP LOSS: {trade['name']} SELL (-1R)")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":result,"tier":trade.get("tier","B")})
            learning_log.append({**trade.get("conditions",{}), "result":result,"pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":result})
            closed=True
    if not closed: remaining.append(trade)

active = remaining
save_json(TRADES_FILE, active); save_json(HISTORY_FILE, history)
save_json(LEARNING_FILE, learning_log); save_json(CONFIDENCE_FILE, conf_data)

# Circuit breaker now uses win/loss count instead of fake balance
# Trips if 4+ losses in last 5 trades
circuit_tripped = False
if len(history) >= 5:
    recent5 = [t.get("result") for t in history[-5:]]
    loss_count = recent5.count("LOSS")
    if loss_count >= 4:
        circuit_tripped = True
        send_tg(f"🚨 CIRCUIT BREAKER TRIGGERED\n4 losses in last 5 trades.\nALL NEW SIGNALS PAUSED for today.")
        print(f"  [CIRCUIT BREAKER] TRIGGERED — {loss_count}/5 recent trades were losses.")
    else:
        print(f"  [CIRCUIT BREAKER] OK — {loss_count}/5 recent trades were losses.")

# We still need rusd for scan below — use fixed risk
rusd = RISK_USD

# Remove the old circuit breaker block (replaced by win/loss based one above)

# MULTI-TIMEFRAME SCANNER
sig_count = 0
if not news_blocked and not circuit_tripped:
    scan_configs = [
        {"interval": "1h",  "period": "30d", "label": "1H Swing",  "rr": 3.5, "min_bars": 200},
        {"interval": "15m", "period": "5d",  "label": "15M Scalp", "rr": 3.0, "min_bars": 100},
    ]
elif news_blocked:
    print(f"  [NEWS BLOCK] Signals paused: {news_reason}")
    sig_count = 0
    scan_configs = []  # empty — no scan during news
else:
    scan_configs = []

# Always scan even in post-news window (breakout mode)
if post_news and not circuit_tripped:
    print(f"  [POST-NEWS BREAKOUT] Scanning all pairs in breakout mode: {post_news_event}")
    scan_configs = [
        {"interval": "15m", "period": "5d", "label": "15M Post-News Breakout", "rr": 2.5, "min_bars": 100},
    ]


for scan in scan_configs:
    scan_rr = scan["rr"]
    for asset in WATCHLIST:
        sym = asset["symbol"]
        df = fetch_df(sym, scan["period"], scan["interval"])
        if df is None or len(df) < scan["min_bars"]: continue
        df = add_indicators(df); bar = df.iloc[-1]
        if any(pd.isna(bar.get(c, np.nan)) for c in ["EMA200","RSI","ADX","ATR"]): continue

        lt = bar["LT"]; hour = int(lt.hour)
        if not (6 <= hour < 21): continue

        close=float(bar["Close"]); ema200=float(bar["EMA200"]); rsi=float(bar["RSI"]); adx=float(bar["ADX"]); atr=float(bar["ATR"]); reg=regime(bar)

        sr_zones = find_sr_zones(df)
        sr_score, sr_zone = check_sr_proximity(close, atr, sr_zones)

        sigs = []
        buy_swept, buy_liq_cl = detect_sweep(df, len(df)-1, "BUY")
        sell_swept, sell_liq_cl = detect_sweep(df, len(df)-1, "SELL")
        patterns, pat_score = detect_candle_patterns(df, len(df)-1)
        pat_names = list(patterns.keys())
        pat_txt = ", ".join(pat_names) if pat_names else "None"
        
        has_bullish_pat = any(p in pat_names for p in ["Bullish Engulfing", "Hammer", "Morning Star", "Doji"])
        has_bearish_pat = any(p in pat_names for p in ["Bearish Engulfing", "Shooting Star", "Evening Star", "Doji"])

        if reg == "TREND" or adx > 25:
            if close > ema200 and rsi < 45 and (buy_swept or has_bullish_pat): sigs.append("BUY")
            if close < ema200 and rsi > 55 and (sell_swept or has_bearish_pat): sigs.append("SELL")
        elif reg == "RANGE":
            if sr_zone and rsi < 45 and (buy_swept or has_bullish_pat): sigs.append("BUY")
            if sr_zone and rsi > 55 and (sell_swept or has_bearish_pat): sigs.append("SELL")

        for action in sigs:
            sig_id = f"{sym}_{action}_{scan['interval']}_{str(lt)}"
            if sig_id in sent: continue
            if any(t["symbol"]==sym and t["type"]==action for t in active): continue

            swept, liq_cl = (buy_swept, buy_liq_cl) if action == "BUY" else (sell_swept, sell_liq_cl)
            ai_score = compute_score(bar, action, liq_cl, reg, pat_score, sr_score)

            atr_r = atr/(close+1e-9); bbw = float(bar["BB_W"]); ema_r = abs(close-ema200)/(close+1e-9)
            ml_prob = predict_ml(rsi, adx, atr_r, bbw, hour, ema_r, action)
            mscore, minfo = macro_score(action)

            tier = classify_tier(ai_score, ml_prob, mscore)
            if tier is None: continue

            corr_dup, corr_reason = is_corr_dup(sym, action, active)
            if corr_dup: continue

            _blocked, block_reason, learn_penalty = apply_learned_rules(rules, bar, asset["name"], hour)
            # Soft penalty: reduces confidence multiplier but never fully blocks
            if block_reason:
                print(f"  [LEARNING] Penalty {learn_penalty:.0%} on {asset['name']}: {block_reason}")

            conf_adj = get_confidence_adjustment(conf_data, asset["name"], hour, reg)
            conf_adj = conf_adj * (1.0 - learn_penalty)  # Apply learning penalty softly

            if scan["interval"] == "1h" and not check_mtf(sym, action): continue

            thesis, gemini_sentiment = run_gemini_copilot(asset["name"], action, rsi, adx, minfo, pat_txt)

            sl_dist = max(1.2*atr, asset["sl_pips"]*asset["pip"])
            rr_ratio = scan["rr"]
            final_risk_mult = tier["risk_mult"] * conf_adj
            trade_risk = rusd * final_risk_mult
            reward = trade_risk * rr_ratio

            if action=="BUY": sl_p=close-sl_dist; tp1_p=close+sl_dist; tp2_p=close+rr_ratio*sl_dist
            else: sl_p=close+sl_dist; tp1_p=close-sl_dist; tp2_p=close-rr_ratio*sl_dist

            grade_emoji = {"A+": "💎", "A": "🥇", "B": "🥈"}.get(tier["label"], "📊")
            action_emoji = "🟢" if action == "BUY" else "🔴"

            card = (
                f"{action_emoji} {action} {asset['name']} [{tier['label']}]\n"
                f"Entry: {close:.5f}\n"
                f"SL: {sl_p:.5f}\n"
                f"TP1: {tp1_p:.5f}\n"
                f"TP2: {tp2_p:.5f}\n\n"
                f"🤖 \"{thesis}\""
            )
                
            print(card)
            if send_tg(card):
                conditions = {"pair":asset["name"],"action":action,"rsi":rsi,"adx":adx,
                              "atr_r":atr_r,"bbw":bbw,"hour":hour,"ema_r":ema_r,
                              "regime":reg,"tier":tier["label"],"ai_score":ai_score,
                              "ml_prob":ml_prob,"macro":mscore,"patterns":pat_txt}
                sent[sig_id] = True
                active.append({
                    "symbol":sym,"name":asset["name"],"type":action,
                    "entry_price":close,"sl_price":sl_p,"tp1_price":tp1_p,"tp2_price":tp2_p,
                    "risk_dollar":trade_risk,"tp1_hit":False,"realized_pnl":0.0,
                    "ai_score":ai_score,"tier":tier["label"],"conditions":conditions
                })
                sig_count += 1

save_json(LOG_FILE, sent); save_json(TRADES_FILE, active)

print(f"\n[SCAN] {sig_count} signal(s) fired | Active: {len(active)} | Learned Rules: {len(rules)}")

# ============================================================
# ENGINE 2: SNIPER (Fair Value Gap / Liquidity Void Matrix)
# Runs independently of Engine 1. Targets 1:5+ RR.
# ============================================================
sniper_count = 0
SNIPER_RR = 5.0  # Sniper targets 1:5 Risk-to-Reward

if not news_blocked and not circuit_tripped:
    print("\n[SNIPER ENGINE] Scanning for Liquidity Voids (FVG)...")
    for asset in WATCHLIST:
        sym = asset["symbol"]
        # Use 15M for speed and gap frequency
        df = fetch_df(sym, "5d", "15m")
        if df is None or len(df) < 100: continue
        df = add_indicators(df)
        bar = df.iloc[-1]
        if any(pd.isna(bar.get(c, np.nan)) for c in ["EMA200", "RSI", "ADX", "ATR"]): continue

        lt = bar["LT"]; hour = int(lt.hour)
        if not (6 <= hour < 21): continue

        close = float(bar["Close"])
        ema200 = float(bar["EMA200"])
        rsi = float(bar["RSI"])
        adx = float(bar["ADX"])
        atr = float(bar["ATR"])
        reg = regime(bar)

        # Detect active FVG zones
        active_fvgs = detect_fvg(df, lookback=80)
        if not active_fvgs: continue

        for fvg in active_fvgs:
            action = fvg["action"]

            # Confluence filter: FVG must align with trend direction
            if action == "BUY" and close < ema200: continue   # Only buy FVGs in uptrends
            if action == "SELL" and close > ema200: continue  # Only sell FVGs in downtrends

            # Sniper signal ID (unique per asset + action + FVG zone)
            sniper_id = f"SNIPER_{sym}_{action}_{fvg['bot']:.5f}_{fvg['top']:.5f}"
            if sniper_id in sent: continue
            if any(t["symbol"] == sym and t["type"] == action for t in active): continue

            # ML and macro filter apply here too
            atr_r = atr / (close + 1e-9)
            bbw = float(bar.get("BB_W", 0.01))
            ema_r = abs(close - ema200) / (close + 1e-9)
            ml_prob = predict_ml(rsi, adx, atr_r, bbw, hour, ema_r, action)
            mscore, minfo = macro_score(action)

            # Sniper uses relaxed tier: only needs ML > 45% and macro > 0
            if ml_prob < 0.45: continue
            if mscore < 0: continue

            # Entry is mid-gap (best institutional fill)
            entry = (fvg["top"] + fvg["bot"]) / 2
            sl_dist = fvg["size"] * 0.5 + atr * 0.3  # Tight SL just beyond gap
            tp_dist = sl_dist * SNIPER_RR

            if action == "BUY":
                sl_p  = entry - sl_dist
                tp1_p = entry + sl_dist
                tp2_p = entry + tp_dist
            else:
                sl_p  = entry + sl_dist
                tp1_p = entry - sl_dist
                tp2_p = entry - tp_dist

            thesis, _ = run_gemini_copilot(asset["name"], action, rsi, adx, minfo,
                                           f"Bullish FVG void fill" if action=="BUY" else "Bearish FVG void fill")

            action_emoji = "🟢" if action == "BUY" else "🔴"
            sniper_card = (
                f"🔥 SNIPER {action_emoji} {action} {asset['name']} [A+]\n"
                f"(Liquidity Void Fill | 1:{int(SNIPER_RR)} RR)\n"
                f"Entry: {entry:.5f}\n"
                f"SL: {sl_p:.5f}\n"
                f"TP1: {tp1_p:.5f}\n"
                f"TP2: {tp2_p:.5f}\n\n"
                f"🤖 \"{thesis}\""
            )

            print(sniper_card)
            if send_tg(sniper_card):
                sent[sniper_id] = True
                active.append({
                    "symbol": sym, "name": asset["name"], "type": action,
                    "entry_price": entry, "sl_price": sl_p,
                    "tp1_price": tp1_p, "tp2_price": tp2_p,
                    "risk_dollar": rusd, "tp1_hit": False, "realized_pnl": 0.0,
                    "ai_score": 85, "tier": "A+", "sniper": True
                })
                sniper_count += 1

    save_json(LOG_FILE, sent); save_json(TRADES_FILE, active)
    print(f"[SNIPER ENGINE] {sniper_count} sniper signal(s) fired")
else:
    print("[SNIPER ENGINE] Skipped (news block or circuit breaker active)")

# ============================================================
# DAILY TRADE LEDGER - End of Day Scorecard
# Fires at 21:30 London time (after all markets close)
# ============================================================
now_london_dl = pd.Timestamp.now(tz="UTC").tz_convert(LONDON_TZ)
if now_london_dl.hour == 21 and now_london_dl.minute >= 30:
    today_str = now_london_dl.strftime("%Y-%m-%d")
    today_trades = [t for t in history if t.get("date", "")[:10] == today_str]
    if not today_trades:
        # Fallback: just use last N closed trades from history (for first few days)
        today_trades = history[-10:] if len(history) >= 10 else history

    if today_trades:
        lines = []
        net_r  = 0.0
        wins   = sum(1 for t in today_trades if t.get("result") == "WIN")
        losses = sum(1 for t in today_trades if t.get("result") == "LOSS")
        bes    = sum(1 for t in today_trades if t.get("result") == "BREAKEVEN")

        for i, t in enumerate(today_trades, 1):
            res    = t.get("result", "OPEN")
            name   = t.get("name", t.get("symbol", "?"))
            tier   = t.get("tier", "B")
            pnl    = t.get("pnl", 0.0)
            is_snp = t.get("sniper", False)
            snp_tag = "🔥 SNIPER " if is_snp else ""
            res_emoji = {"WIN": "✅", "LOSS": "❌", "BREAKEVEN": "🛡️"}.get(res, "⏳")
            pnl_txt = f"+{pnl:.1f}R" if pnl > 0 else f"{pnl:.1f}R" if pnl < 0 else "0R"
            net_r += pnl
            lines.append(f"{i}. {snp_tag}{name} [{tier}]: {res_emoji} {res} ({pnl_txt})")

        net_emoji = "🏆" if net_r > 0 else ("🛡️" if net_r == 0 else "📉")
        net_txt   = f"+{net_r:.1f}R" if net_r > 0 else f"{net_r:.1f}R"
        ledger_msg = (
            f"📋 DAILY TRADE LEDGER\n"
            f"{'-'*28}\n"
            + "\n".join(lines) +
            f"\n{'-'*28}\n"
            f"Total: {len(today_trades)} ({wins}W - {losses}L - {bes}BE)\n"
            f"Net Result: {net_txt} {net_emoji}"
        )
        print(ledger_msg)
        send_tg(ledger_msg)
    else:
        print("[DAILY LEDGER] No closed trades today.")

# ============================================================
# AUTO WEEKLY SUNDAY REPORT (No manual trigger needed)
# ============================================================
now_cam = pd.Timestamp.now(tz="UTC").tz_convert("Asia/Phnom_Penh")
if now_cam.day_of_week == 6:  # Sunday = 6
    df_h = pd.DataFrame(history); tot = len(df_h)
    if tot > 0:
        wins=df_h[df_h["result"]=="WIN"]; loss=df_h[df_h["result"]=="LOSS"]; bes=df_h[df_h["result"]=="BREAKEVEN"]
        wr=(len(wins)+len(bes))/tot*100
        gp=len(wins); gl=len(loss)
        pf=gp/gl if gl>0 else gp
        # Best and worst performing pairs
        if "name" in df_h.columns:
            pair_wins = df_h[df_h["result"]=="WIN"].groupby("name").size().sort_values(ascending=False)
            best_pair = pair_wins.index[0] if not pair_wins.empty else "N/A"
            pair_loss = df_h[df_h["result"]=="LOSS"].groupby("name").size().sort_values(ascending=False)
            worst_pair = pair_loss.index[0] if not pair_loss.empty else "N/A"
        else:
            best_pair = worst_pair = "N/A"
    else: wr=pf=0.0; wins=loss=bes=pd.DataFrame(); best_pair=worst_pair="N/A"; tot=gp=gl=0

    weekly_report = (
        f"📊 WEEKLY REPORT\n"
        f"Trades: {tot} ({gp}W - {gl}L - {len(bes)}BE)\n"
        f"Win Rate: {wr:.1f}%\n"
        f"Profit Factor: {pf:.2f}\n"
        f"Best: {best_pair} | Worst: {worst_pair}"
    )
    print(weekly_report); send_tg(weekly_report)

# ============================================================
# MODULE: DAILY HEARTBEAT - Proof of Life Check
# ============================================================
if "--heartbeat" in sys.argv:
    tot_h = len(history)
    wins_h  = len([t for t in history if t.get("result") == "WIN"])
    loss_h  = len([t for t in history if t.get("result") == "LOSS"])
    bes_h   = len([t for t in history if t.get("result") == "BREAKEVEN"])
    wr_h    = ((wins_h + bes_h) / tot_h * 100) if tot_h > 0 else 0.0
    # Best grade analysis
    diamond_c = len([t for t in history if t.get("tier") == "A+"])
    gold_c    = len([t for t in history if t.get("tier") == "A"])
    silver_c  = len([t for t in history if t.get("tier") == "B"])
    circuit_status = "🔴 TRIPPED" if circuit_tripped else "🟢 OK"
    ai_status = "ACTIVE 🤖" if GEMINI_KEY else "OFFLINE"
    heartbeat_msg = (
        f"🤖 DAILY STATUS\n"
        f"Total Trades: {tot_h} ({wins_h}W - {loss_h}L - {bes_h}BE)\n"
        f"Win Rate: {wr_h:.1f}%\n"
        f"System: {'🔴 PAUSED' if news_blocked or circuit_tripped else '🟢 Active'} ({len(WATCHLIST)} Pairs)"
    )
    print(heartbeat_msg)
    send_tg(heartbeat_msg)

print("\n" + "="*90)
print("ADAPTIVE ENGINE v4.1 COMPLETE - Dual-Engine | Smart Learning | Daily Ledger")
print("="*90 + "\n")
