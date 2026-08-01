"""
===============================================================================
V5.0 SHADOW BOT — ASIAN RANGE SWEEP ENGINE
===============================================================================
PROVEN STRATEGY (2-Year Unbiased Backtest):
  - Inner Asian Range (03:00-06:00 London)
  - EMA200 + RSI14 trend/momentum filter
  - Sweep entry → 1:2 Risk/Reward with TP1 partial
  - Win-Streak Anti-Martingale sizing

6 GOLDEN PAIRS: NZD/USD, EUR/USD, USD/CAD, GBP/USD, AUD/USD, NZD/CAD
SESSION: London 07-11 | NY 13-16 (EUR/USD only)

Sends [SHADOW 🔬 V5.0] signals to Telegram.
Does NOT replace the old bot. Runs in parallel.
===============================================================================
"""
import sys, os, json, hashlib, urllib.request, urllib.parse, warnings
warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

import numpy as np
import pandas as pd
import yfinance as yf
import pytz

# ── ENV ───────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
if os.path.exists(".env"):
    try:
        with open(".env") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not BOT_TOKEN:
                    BOT_TOKEN = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID=") and not CHAT_ID:
                    CHAT_ID = line.split("=", 1)[1].strip()
    except: pass

LONDON_TZ = pytz.timezone("Europe/London")
CAMBODIA_TZ = pytz.timezone("Asia/Phnom_Penh")

# ── STATE FILES ───────────────────────────────────────────────────────────────
V5_SENT_FILE    = "v5_sent_signals.json"
V5_STREAK_FILE  = "v5_streak.json"

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except: pass
    return default

def save_json(path, obj):
    with open(path, "w") as f: json.dump(obj, f, indent=2)

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_tg(text):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"  [TG] No token/chat ID — skipping")
        return False
    msg_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    sent = load_json(V5_SENT_FILE, [])
    if msg_hash in sent:
        print(f"  [TG] Duplicate — skipping")
        return True
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        sent.append(msg_hash)
        save_json(V5_SENT_FILE, sent[-200:])
        print(f"  [TG] Sent OK")
        return True
    except Exception as e:
        print(f"  [TG] Error: {e}")
        return False

def get_cam_time():
    return pd.Timestamp.now(tz="UTC").tz_convert(CAMBODIA_TZ).strftime("%a %d %b %Y | %I:%M %p")

# ── CONFIG ────────────────────────────────────────────────────────────────────
WATCHLIST = [
    {"symbol": "NZDUSD=X", "name": "NZD/USD", "pip": 0.0001, "sl_pips": 12, "dec": 5},
    {"symbol": "EURUSD=X", "name": "EUR/USD", "pip": 0.0001, "sl_pips": 10, "dec": 5},
    {"symbol": "USDCAD=X", "name": "USD/CAD", "pip": 0.0001, "sl_pips": 12, "dec": 5},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "pip": 0.0001, "sl_pips": 12, "dec": 5},
    {"symbol": "AUDUSD=X", "name": "AUD/USD", "pip": 0.0001, "sl_pips": 12, "dec": 5},
    {"symbol": "NZDCAD=X", "name": "NZD/CAD", "pip": 0.0001, "sl_pips": 12, "dec": 5},
]

# ── WIN-STREAK ANTI-MARTINGALE (Stage 2: Risk Manager) ───────────────────────
def get_risk_label():
    streak = load_json(V5_STREAK_FILE, {"wins": 0, "losses": 0})
    if streak.get("wins", 0) >= 3:
        return "3% (Win Streak 🔥)", "HIGH"
    elif streak.get("losses", 0) >= 2:
        return "1.5% (Loss Shield 🛡️)", "LOW"
    else:
        return "2% (Standard)", "NORMAL"

def update_streak(won):
    streak = load_json(V5_STREAK_FILE, {"wins": 0, "losses": 0})
    if won:
        streak["wins"] = streak.get("wins", 0) + 1
        streak["losses"] = 0
    else:
        streak["losses"] = streak.get("losses", 0) + 1
        streak["wins"] = 0
    save_json(V5_STREAK_FILE, streak)

# ── DATA FETCH + INDICATORS ──────────────────────────────────────────────────
def fetch_and_analyze(pair):
    sym = pair["symbol"]
    try:
        df = yf.download(sym, period="30d", interval="1h", progress=False)
        if df.empty or len(df) < 250:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        # Timezone
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(LONDON_TZ)

        # EMA 200
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # RSI 14
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0.0).ewm(span=14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(span=14, adjust=False).mean()
        df["RSI"] = 100 - (100 / (1 + gain / loss.replace(0, 0.00001)))

        # Inner Asian Range (03:00 - 06:00 London)
        df["date"] = df.index.date
        df["hour"] = df.index.hour
        df["wday"] = [t.weekday() for t in df.index]

        asian_inner = df[df["hour"].between(3, 5)]
        ah_map = asian_inner.groupby("date")["High"].max()
        al_map = asian_inner.groupby("date")["Low"].min()
        df["AH"] = df["date"].map(ah_map)
        df["AL"] = df["date"].map(al_map)

        df = df.dropna(subset=["EMA200", "RSI", "AH", "AL"])
        if df.empty:
            return None

        return df
    except Exception as e:
        print(f"  [ERROR] {sym}: {e}")
        return None

# ── SIGNAL SCANNER ────────────────────────────────────────────────────────────
def scan_pair(pair, df):
    last = df.iloc[-1]
    hr   = int(last["hour"])
    wd   = int(last["wday"])

    # Weekend filter
    if wd >= 5:
        return None

    # Session filter: London 07-11, NY 13-16 (EUR/USD only)
    is_london = (7 <= hr < 11)
    is_ny     = (13 <= hr < 16) and pair["symbol"] == "EURUSD=X"
    if not (is_london or is_ny):
        return None

    c   = float(last["Close"])
    h   = float(last["High"])
    l   = float(last["Low"])
    ema = float(last["EMA200"])
    rsi = float(last["RSI"])
    ah  = float(last["AH"])
    al  = float(last["AL"])

    # Validate Asian Range
    if ah <= al or (ah - al) < pair["pip"] * 3:
        return None

    # ── THE V5.0 SWEEP RULES ─────────────────────────────────────────────
    action = None
    if (c > ema) and (l <= al) and (rsi < 35.0):
        action = "BUY"
    elif (c < ema) and (h >= ah) and (rsi > 65.0):
        action = "SELL"

    if not action:
        return None

    # Calculate levels
    pip    = pair["pip"]
    sl_d   = pair["sl_pips"] * pip
    dec    = pair["dec"]

    if action == "BUY":
        sl  = round(c - sl_d, dec)
        tp1 = round(c + sl_d, dec)
        tp2 = round(c + 2.0 * sl_d, dec)
    else:
        sl  = round(c + sl_d, dec)
        tp1 = round(c - sl_d, dec)
        tp2 = round(c - 2.0 * sl_d, dec)

    session = "New York 🗽" if is_ny else "London 🇬🇧"
    trend   = "UPTREND ↗" if c > ema else "DOWNTREND ↘"
    risk_label, risk_level = get_risk_label()

    return {
        "pair": pair["name"],
        "action": action,
        "entry": round(c, dec),
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rsi": round(rsi, 1),
        "session": session,
        "trend": trend,
        "risk_label": risk_label,
        "risk_level": risk_level,
        "asian_high": round(ah, dec),
        "asian_low": round(al, dec),
    }

# ── FORMAT TELEGRAM MESSAGE ──────────────────────────────────────────────────
def format_signal(sig):
    emoji = "🟢" if sig["action"] == "BUY" else "🔴"
    return f"""
🔬 [SHADOW V5.0] SIGNAL DETECTED
━━━━━━━━━━━━━━━━━━━━━━━
{emoji} {sig['action']} {sig['pair']}
━━━━━━━━━━━━━━━━━━━━━━━
📍 Entry    : {sig['entry']}
🛑 Stop Loss: {sig['sl']}
🎯 TP1 (1:1): {sig['tp1']}  ← Close 50%, move SL to BE
🏆 TP2 (1:2): {sig['tp2']}  ← Close remaining 50%

📊 Trend    : {sig['trend']}
📈 RSI      : {sig['rsi']}
🕐 Session  : {sig['session']}
⚖️ Risk     : {sig['risk_label']}

📦 Asian Range: {sig['asian_low']} — {sig['asian_high']}
━━━━━━━━━━━━━━━━━━━━━━━
🧠 Strategy: Inner Asian Range Sweep
📅 {get_cam_time()}
━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── MAIN ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print(" V5.0 SHADOW BOT — Asian Range Sweep Engine")
print(" Mode: SHADOW (Parallel to V4.5, no replacement)")
print("=" * 60)

signals = []
for pair in WATCHLIST:
    print(f"  Scanning {pair['name']}... ", end="", flush=True)
    df = fetch_and_analyze(pair)
    if df is None:
        print("skip (no data)")
        continue

    sig = scan_pair(pair, df)
    if sig:
        signals.append(sig)
        print(f"SIGNAL! {sig['action']}")
    else:
        print("no signal")

print(f"\n  Total signals: {len(signals)}")

if signals:
    for sig in signals:
        msg = format_signal(sig)
        print(msg)
        send_tg(msg)
else:
    # Send heartbeat every 4 hours so you know the bot is alive
    import datetime
    now_utc = pd.Timestamp.now(tz="UTC")
    hr_utc = now_utc.hour
    if hr_utc % 4 == 0:
        heartbeat = f"""
🔬 [SHADOW V5.0] HEARTBEAT
━━━━━━━━━━━━━━━━━━━━━━━
✅ Bot is ALIVE and scanning
📊 Pairs monitored: {len(WATCHLIST)}
🕐 No valid setups at this scan
📅 {get_cam_time()}
━━━━━━━━━━━━━━━━━━━━━━━
"""
        send_tg(heartbeat)
        print("  Heartbeat sent to Telegram")

print("\n" + "=" * 60)
print(" V5.0 scan complete. Old bot is NOT affected.")
print("=" * 60)
