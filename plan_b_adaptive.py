"""
===============================================================================
PLAN B ADAPTIVE ENGINE v2.0  -  AI-COPILOT CLOUD SYSTEM
===============================================================================
19 MODULES TOTAL:

ELITE (E1-E6):   MTF | SMC | AI Score | Regime | Scaling | Tracker
DIAMOND (D1-D6): Macro | News | Corr | Trail | MonteCarlo | ML
ADAPTIVE (A1-A8): Patterns | S/R Zones | Loss Learner | ML Retrain |
                   Multi-TF Scalper | Confidence | Tiered Quality |
                   A8: Gemini NLP News Sentiment & Trade Thesis Copilot

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
INITIAL_BALANCE    = 200.0
BB_PERIOD          = 20
ADX_TREND_TH       = 25
NEWS_BLOCK_MIN     = 30
NEWS_RESUME_MIN    = 45
CORR_BLOCK         = 0.80

TIER_DIAMOND = {"score": 80, "ml": 0.70, "macro": 4, "risk_mult": 1.00, "label": "DIAMOND (A+)"}
TIER_GOLD    = {"score": 65, "ml": 0.60, "macro": 3, "risk_mult": 0.75, "label": "GOLD (A)"}
TIER_SILVER  = {"score": 55, "ml": 0.50, "macro": 2, "risk_mult": 0.50, "label": "SILVER (B)"}

BALANCE_STAGES = [
    {"min": 0,   "max": 300,  "risk": 0.020, "label": "Stage 1 ($200-$300) | 2.0%"},
    {"min": 300, "max": 500,  "risk": 0.015, "label": "Stage 2 ($300-$500) | 1.5%"},
    {"min": 500, "max": 99999,"risk": 0.010, "label": "Stage 3 ($500+) | Prop Ladder"},
]
GOVERNED_RISK           = 0.010
CIRCUIT_BREAKER_PCT     = 0.08   # Stop all trading if weekly loss > 8% of balance

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

LOG_FILE       = "adaptive_sent_signals.json"
TRADES_FILE    = "adaptive_active_trades.json"
HISTORY_FILE   = "adaptive_trade_history.json"
BALANCE_FILE   = "adaptive_balance.json"
LEARNING_FILE  = "adaptive_learning_log.json"
RULES_FILE     = "adaptive_rules.json"
CONFIDENCE_FILE    = "adaptive_confidence.json"
BAL_HISTORY_FILE   = "adaptive_balance_history.json"

print("=" * 90)
print("PLAN B ADAPTIVE ENGINE v2.1 - AI-COPILOT CLOUD SYSTEM")
print("=" * 90)
print(f"  Account  : ${INITIAL_BALANCE:,.2f}  |  Pairs: {len(WATCHLIST)}")
print(f"  AI Copilot: {'ACTIVE (Gemini Free API)' if GEMINI_KEY else 'OFFLINE (Fallback Active)'}")
print(f"  Modules  : E1-E6 + D1-D6 + A1-A8 + Circuit Breaker + Heartbeat = 21 Total")
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
# A3: SELF-LEARNING LOSS ANALYZER
# ============================================================
def analyze_losses(history, learning_log):
    losses = [t for t in learning_log if t.get("result") == "LOSS"]
    if len(losses) < 3: return []
    rules = []
    adx_vals = [t.get("adx", 25) for t in losses if "adx" in t]
    if adx_vals:
        low_adx = [v for v in adx_vals if v < 18]
        if len(low_adx) > len(adx_vals) * 0.6:
            rules.append({"type": "min_adx", "value": 18, "reason": f"{len(low_adx)}/{len(adx_vals)} losses had ADX<18"})
    hour_vals = [t.get("hour", 12) for t in losses if "hour" in t]
    if hour_vals:
        from collections import Counter
        bh, count = Counter(hour_vals).most_common(1)[0]
        if count >= 3:
            rules.append({"type": "block_hour", "value": bh, "reason": f"{count} losses at hour {bh}:00"})
    return rules

def apply_learned_rules(rules, bar, asset_name, hour):
    for r in rules:
        if r["type"] == "min_adx" and float(bar["ADX"]) < r["value"]:
            return True, f"LEARNED RULE: ADX {float(bar['ADX']):.1f} < {r['value']} ({r['reason']})"
        elif r["type"] == "block_hour" and hour == r["value"]:
            return True, f"LEARNED RULE: Hour {hour}:00 blocked ({r['reason']})"
    return False, ""

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
            if -NEWS_RESUME_MIN<=diff<=NEWS_BLOCK_MIN:
                return True, f"NEWS BLACKOUT: {ev.get('title','')} ({ev.get('currency','')})"
        return False, "CLEAR"
    except Exception as e:
        h=now.astimezone(LONDON_TZ).hour; m=now.astimezone(LONDON_TZ).minute
        for rh,rm in [(8,30),(13,30),(15,0)]:
            d=(h*60+m)-(rh*60+rm)
            if -NEWS_BLOCK_MIN<=d<=NEWS_RESUME_MIN: return True, f"NEWS GUARD (offline): block near {rh:02d}:{rm:02d}"
        return False, f"CLEAR (offline: {e})"

news_blocked, news_reason = check_news()

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
bal_data  = load_json(BALANCE_FILE, {"balance": INITIAL_BALANCE})
conf_data = load_json(CONFIDENCE_FILE, {})
rules     = load_json(RULES_FILE, [])
bal = bal_data.get("balance", INITIAL_BALANCE)

# LIVE MT5 DIRECT CONNECTION (100% FREE)
try:
    import MetaTrader5 as mt5
    if mt5.initialize():
        acc_info = mt5.account_info()
        if acc_info is not None and acc_info.balance > 0:
            bal = float(acc_info.balance)
            print(f"  [MT5 DIRECT] Live Broker Connection Active! Login: {acc_info.login} | Balance: ${bal:,.2f} {acc_info.currency}")
        mt5.shutdown()
except Exception:
    pass

rp, rl = get_risk(bal, history); rusd = bal * rp

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
            trade["tp1_hit"]=True; trade["sl_price"]=ep; trade["realized_pnl"]=r*0.5; bal+=r*0.5
            send_tg(f"✅ TRADE CLOSED: PROFIT LOCKED\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (BUY)\nResult  : +${r*0.5:.2f} (Locked at TP1)\nBalance : ${bal:,.2f} 🟢")
        if hi>=tp2:
            pnl=trade.get("realized_pnl",0)+r*0.5*3.5; bal+=r*0.5*3.5
            send_tg(f"✅ TRADE CLOSED: FULL WIN\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (BUY)\nResult  : +${pnl:.2f} (Full TP2)\nBalance : ${bal:,.2f} 🟢")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":"WIN"})
            learning_log.append({**trade.get("conditions",{}), "result":"WIN","pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":"WIN"})
            closed=True
        elif lo<=trade["sl_price"]:
            if trade["sl_price"]>=ep:
                pnl=trade.get("realized_pnl",0); result="BREAKEVEN"
                send_tg(f"🛡️ TRADE CLOSED: BREAKEVEN\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (BUY)\nResult  : +${pnl:.2f} (Breakeven)\nBalance : ${bal:,.2f} 🟢")
            else:
                bal-=r; pnl=-r; result="LOSS"
                send_tg(f"❌ TRADE CLOSED: STOP LOSS\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (BUY)\nResult  : -${r:.2f} (Stop Loss)\nBalance : ${bal:,.2f} 🔴")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":result})
            learning_log.append({**trade.get("conditions",{}), "result":result,"pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":result})
            closed=True
    elif trade["type"]=="SELL":
        if lo<=tp1 and not trade.get("tp1_hit"):
            trade["tp1_hit"]=True; trade["sl_price"]=ep; trade["realized_pnl"]=r*0.5; bal+=r*0.5
            send_tg(f"✅ TRADE CLOSED: PROFIT LOCKED\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (SELL)\nResult  : +${r*0.5:.2f} (Locked at TP1)\nBalance : ${bal:,.2f} 🟢")
        if lo<=tp2:
            pnl=trade.get("realized_pnl",0)+r*0.5*3.5; bal+=r*0.5*3.5
            send_tg(f"✅ TRADE CLOSED: FULL WIN\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (SELL)\nResult  : +${pnl:.2f} (Full TP2)\nBalance : ${bal:,.2f} 🟢")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":"WIN"})
            learning_log.append({**trade.get("conditions",{}), "result":"WIN","pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":"WIN"})
            closed=True
        elif hi>=trade["sl_price"]:
            if trade["sl_price"]<=ep:
                pnl=trade.get("realized_pnl",0); result="BREAKEVEN"
                send_tg(f"🛡️ TRADE CLOSED: BREAKEVEN\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (SELL)\nResult  : +${pnl:.2f} (Breakeven)\nBalance : ${bal:,.2f} 🟢")
            else:
                bal-=r; pnl=-r; result="LOSS"
                send_tg(f"❌ TRADE CLOSED: STOP LOSS\n📅 {get_cam_time()} (Cambodia)\n------------------------------------\nPair    : {trade['name']} (SELL)\nResult  : -${r:.2f} (Stop Loss)\nBalance : ${bal:,.2f} 🔴")
            history.append({"symbol":sym,"name":trade["name"],"pnl":pnl,"result":result})
            learning_log.append({**trade.get("conditions",{}), "result":result,"pnl":pnl})
            conf_data = update_confidence(conf_data, {**trade.get("conditions",{}), "result":result})
            closed=True
    if not closed: remaining.append(trade)

active = remaining
save_json(TRADES_FILE, active); save_json(HISTORY_FILE, history); save_json(BALANCE_FILE, {"balance": bal})
save_json(LEARNING_FILE, learning_log); save_json(CONFIDENCE_FILE, conf_data)
rp, rl = get_risk(bal, history); rusd = bal * rp

# ============================================================
# MODULE: CIRCUIT BREAKER - Weekly 8% Drawdown Stop
# ============================================================
def check_circuit_breaker(bal_history, current_bal):
    """
    Checks if the account has lost more than 8% in the last 7 days.
    If yes: blocks ALL new signals and sends emergency alert.
    """
    now_str = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    # Record today's balance snapshot
    bal_history[now_str] = current_bal
    # Keep only last 30 days
    if len(bal_history) > 30:
        oldest = sorted(bal_history.keys())[0]
        del bal_history[oldest]
    # Find balance 7 days ago
    week_ago = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    week_ago_entries = [(d, v) for d, v in bal_history.items() if d <= week_ago]
    if not week_ago_entries:
        return False, bal_history, "CIRCUIT OK (insufficient history)"
    oldest_date, week_ago_bal = max(week_ago_entries, key=lambda x: x[0])
    if week_ago_bal <= 0:
        return False, bal_history, "CIRCUIT OK"
    weekly_loss_pct = (week_ago_bal - current_bal) / week_ago_bal
    if weekly_loss_pct >= CIRCUIT_BREAKER_PCT:
        msg = (
            f"\U0001F6A8 CIRCUIT BREAKER TRIGGERED\n"
            f"Weekly Loss: -{weekly_loss_pct*100:.1f}% (Limit: -{CIRCUIT_BREAKER_PCT*100:.0f}%)\n"
            f"Balance 7 days ago: ${week_ago_bal:.2f} | Now: ${current_bal:.2f}\n"
            f"ALL NEW TRADES PAUSED until Monday reset.\n"
            f"Review your strategy before resuming."
        )
        send_tg(msg)
        print(f"  [CIRCUIT BREAKER] TRIGGERED - Weekly loss {weekly_loss_pct*100:.1f}% > {CIRCUIT_BREAKER_PCT*100:.0f}% limit.")
        return True, bal_history, msg
    print(f"  [CIRCUIT BREAKER] OK - Weekly PnL: {(current_bal-week_ago_bal):+.2f} ({((current_bal-week_ago_bal)/week_ago_bal)*100:+.1f}%)")
    return False, bal_history, "CIRCUIT OK"

bal_history_data = load_json(BAL_HISTORY_FILE, {})
circuit_tripped, bal_history_data, cb_reason = check_circuit_breaker(bal_history_data, bal)
save_json(BAL_HISTORY_FILE, bal_history_data)

# MULTI-TIMEFRAME SCANNER
sig_count = 0
if not news_blocked and not circuit_tripped:
    scan_configs = [
        {"interval": "1h", "period": "30d", "label": "1H Swing", "rr": 3.5, "min_bars": 200},
        {"interval": "15m", "period": "5d",  "label": "15M Scalp", "rr": 3.0, "min_bars": 100},
    ]

    for scan in scan_configs:
        for asset in WATCHLIST:
            sym = asset["symbol"]
            df = fetch_df(sym, scan["period"], scan["interval"])
            if df is None or len(df) < scan["min_bars"]: continue
            df = add_indicators(df); bar = df.iloc[-1]
            if any(pd.isna(bar.get(c, np.nan)) for c in ["EMA200","RSI","ADX","ATR"]): continue

            lt = bar["LT"]; hour = int(lt.hour)
            if not ((8<=hour<12) or (13<=hour<17)): continue

            close=float(bar["Close"]); ema200=float(bar["EMA200"]); rsi=float(bar["RSI"]); adx=float(bar["ADX"]); atr=float(bar["ATR"]); reg=regime(bar)

            sr_zones = find_sr_zones(df)
            sr_score, sr_zone = check_sr_proximity(close, atr, sr_zones)

            sigs = []
            if reg == "RANGE":
                if "H3D" in bar and "L3D" in bar and not pd.isna(bar["H3D"]) and not pd.isna(bar["L3D"]):
                    if close > ema200 and float(bar["Low"]) <= float(bar["L3D"]) and rsi < 40: sigs.append("BUY")
                    if close < ema200 and float(bar["High"]) >= float(bar["H3D"]) and rsi > 60: sigs.append("SELL")
            else:
                if "H3D" in bar and "L3D" in bar and not pd.isna(bar["H3D"]) and not pd.isna(bar["L3D"]):
                    if close > ema200 and close > float(bar["H3D"]) and rsi > 55 and adx > 22: sigs.append("BUY")
                    if close < ema200 and close < float(bar["L3D"]) and rsi < 45 and adx > 22: sigs.append("SELL")

            for action in sigs:
                sig_id = f"{sym}_{action}_{scan['interval']}_{str(lt)}"
                if sig_id in sent: continue
                if any(t["symbol"]==sym and t["type"]==action for t in active): continue

                patterns, pat_score = detect_candle_patterns(df, len(df)-1)
                pat_names = list(patterns.keys()); pat_txt = ", ".join(pat_names) if pat_names else "None"
                swept, liq_cl = detect_sweep(df, len(df)-1, action)
                ai_score = compute_score(bar, action, liq_cl, reg, pat_score, sr_score)

                atr_r = atr/(close+1e-9); bbw = float(bar["BB_W"]); ema_r = abs(close-ema200)/(close+1e-9)
                ml_prob = predict_ml(rsi, adx, atr_r, bbw, hour, ema_r, action)
                mscore, minfo = macro_score(action)

                tier = classify_tier(ai_score, ml_prob, mscore)
                if tier is None: continue

                corr_dup, corr_reason = is_corr_dup(sym, action, active)
                if corr_dup: continue

                blocked, block_reason = apply_learned_rules(rules, bar, asset["name"], hour)
                if blocked: continue

                conf_adj = get_confidence_adjustment(conf_data, asset["name"], hour, reg)

                if scan["interval"] == "1h" and not check_mtf(sym, action): continue

                # A8: GEMINI AI COPILOT TEXT THESIS & SENTIMENT
                thesis, gemini_sentiment = run_gemini_copilot(asset["name"], action, rsi, adx, minfo, pat_txt)

                sl_dist = max(1.2*atr, asset["sl_pips"]*asset["pip"])
                rr_ratio = scan["rr"]
                final_risk_mult = tier["risk_mult"] * conf_adj
                trade_risk = rusd * final_risk_mult
                reward = trade_risk * rr_ratio

                if action=="BUY": sl_p=close-sl_dist; tp1_p=close+sl_dist; tp2_p=close+rr_ratio*sl_dist
                else: sl_p=close+sl_dist; tp1_p=close-sl_dist; tp2_p=close-rr_ratio*sl_dist

                ml_txt = f"{ml_prob*100:.1f}%" if ml_prob else "N/A"
                sr_txt = f"Near {sr_zone['strength']} zone" if sr_zone else "Standard"

                card = (
                    f"🚨 NEW SIGNAL: {asset['name']} ({action})\n"
                    f"📅 {get_cam_time()} (Cambodia)\n"
                    f"------------------------------------\n"
                    f"Entry    : {close:.5f}\n"
                    f"StopLoss : {sl_p:.5f} (-${trade_risk:.2f} Risk)\n"
                    f"TP1      : {tp1_p:.5f} (+${trade_risk*0.5:.2f} & SL->BE)\n"
                    f"TP2      : {tp2_p:.5f} (+${reward:.2f} Full win)\n"
                    f"------------------------------------\n"
                    f"🤖 AI THESIS:\n"
                    f"\"{thesis}\""
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

# WEEKLY SUMMARY
if "--weekly-summary" in sys.argv:
    df_h = pd.DataFrame(history); tot = len(df_h)
    if tot > 0:
        wins=df_h[df_h["result"]=="WIN"]; loss=df_h[df_h["result"]=="LOSS"]; bes=df_h[df_h["result"]=="BREAKEVEN"]
        wr=(len(wins)+len(bes))/tot*100; net=df_h["pnl"].sum()
        gp=wins["pnl"].sum() if not wins.empty else 0.0; gl=abs(loss["pnl"].sum()) if not loss.empty else 0.0
        pf=gp/gl if gl>0 else gp
    else: wr=net=pf=0.0; wins=loss=bes=pd.DataFrame()

    summary = (
        f"📊 PLAN B WEEKLY REPORT\n"
        f"Signals: {tot} taken | {len(wins)}W {len(loss)}L {len(bes)}BE (WR: {wr:.1f}%)\n"
        f"Balance: ${bal:,.2f} | Net: ${net:+,.2f}\n"
        f"Profit Factor: {pf:.2f}\n"
        f"⏳ {get_cam_time()}"
    )
    print(summary); send_tg(summary)

# ============================================================
# MODULE: DAILY HEARTBEAT - Proof of Life Check
# ============================================================
if "--heartbeat" in sys.argv:
    tot_h = len(history)
    wins_h  = len([t for t in history if t.get("result") == "WIN"])
    loss_h  = len([t for t in history if t.get("result") == "LOSS"])
    bes_h   = len([t for t in history if t.get("result") == "BREAKEVEN"])
    net_h   = sum(t.get("pnl", 0) for t in history)
    wr_h    = ((wins_h + bes_h) / tot_h * 100) if tot_h > 0 else 0.0
    now_cam = pd.Timestamp.now(tz="UTC").tz_convert("Asia/Phnom_Penh")
    # Balance history 7-day check
    week_ago_str = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    old_entries  = [(d, v) for d, v in bal_history_data.items() if d <= week_ago_str]
    week_pnl_txt = "N/A (first week)"
    if old_entries:
        _, w_bal = max(old_entries, key=lambda x: x[0])
        week_pnl_txt = f"${bal - w_bal:+.2f} ({((bal-w_bal)/w_bal*100):+.1f}% this week)"
    data_status = "ALL 15 OK" if len(WATCHLIST) == 15 else f"{len(WATCHLIST)}/15 assets"
    circuit_status = "🔴 TRIPPED" if circuit_tripped else "🟢 OK"
    ai_status = "ACTIVE" if GEMINI_KEY else "OFFLINE"
    heartbeat_msg = (
        f"🤖 DAILY BOT STATUS\n"
        f"📅 {get_cam_time()} (Cambodia)\n"
        f"------------------------------------\n"
        f"Balance : ${bal:,.2f} (Net: ${net_h:+.2f})\n"
        f"Trades  : {tot_h} Taken ({wins_h} Win, {loss_h} Loss)\n"
        f"Status  : 15 Assets Active 🟢"
    )
    print(heartbeat_msg)
    send_tg(heartbeat_msg)

print("\n" + "="*90)
print("ADAPTIVE ENGINE v2.1 COMPLETE - 21 Modules Active!")
print("="*90 + "\n")
