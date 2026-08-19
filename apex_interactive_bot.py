"""
APEX INTERACTIVE TELEGRAM AI ASSISTANT (V1.0)
Allows the user to send commands (/scan, /gold, /btc, /eth, /status) directly from their phone!

Commands:
  /scan   -> Scans Gold, BTC, ETH, Nasdaq, EUR, GBP for live institutional setups.
  /gold   -> Instant Gold (XAU/USD) 15M live analysis & trade recommendation.
  /btc    -> Instant Bitcoin (BTC/USD) 15M live analysis & trade recommendation.
  /eth    -> Instant Ethereum (ETH/USD) 15M live analysis & trade recommendation.
  /status -> System status, session clock, and market regime.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8805795541:AAFQxtzJrvJQlfBVazkVm4KwvSh9FSgfDro")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5477873575")

if not BOT_TOKEN or not CHAT_ID:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not BOT_TOKEN:
                    BOT_TOKEN = line.split("=", 1)[1]
                elif line.startswith("TELEGRAM_CHAT_ID=") and not CHAT_ID:
                    CHAT_ID = line.split("=", 1)[1]

ASSETS = {
    "GC=F":     {"name": "GOLD (XAU/USD)", "emoji": "🥇", "digits": 2, "cent_lot": "3 clips of 0.05 lots"},
    "BTC-USD":  {"name": "BITCOIN (BTC/USD)", "emoji": "₿", "digits": 2, "cent_lot": "3 clips of 0.05 lots"},
    "ETH-USD":  {"name": "ETHEREUM (ETH/USD)", "emoji": "⟠", "digits": 2, "cent_lot": "3 clips of 0.05 lots"},
    "NQ=F":     {"name": "NASDAQ (US100)", "emoji": "📈", "digits": 2, "cent_lot": "3 clips of 0.05 lots"},
    "GBPUSD=X": {"name": "GBP/USD", "emoji": "💷", "digits": 5, "cent_lot": "3 clips of 0.05 lots"},
    "EURUSD=X": {"name": "EUR/USD", "emoji": "💶", "digits": 5, "cent_lot": "3 clips of 0.05 lots"},
}


def send_message(text: str, reply_to_id: int = None) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        print(f"Error sending message: {e}")
        return False


def run_single_asset_analysis(symbol: str) -> str:
    import yfinance as yf
    import pandas as pd
    import numpy as np

    meta = ASSETS.get(symbol)
    if not meta:
        return "⚠️ Asset not recognized."

    name = meta["name"]
    emoji = meta["emoji"]
    digits = meta["digits"]
    cent_lot = meta["cent_lot"]

    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 50:
            return f"⚠️ Insufficient data for {name}."
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        hl = df["High"] - df["Low"]
        hc = np.abs(df["High"] - df["Close"].shift())
        lc = np.abs(df["Low"] - df["Close"].shift())
        df["ATR"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

        df["H24"] = df["High"].shift(1).rolling(96).max()
        df["L24"] = df["Low"].shift(1).rolling(96).min()
        df["Range_Pct"] = ((df["Close"] - df["L24"]) / (df["H24"] - df["L24"])) * 100

        df = df.dropna()
        cur = df.iloc[-1]
        c = float(cur["Close"])
        rsi = float(cur["RSI"])
        range_pct = float(cur["Range_Pct"])
        atr = float(cur["ATR"])

        sl_dist = 0.2 * atr
        if sl_dist < 0.15 * atr: sl_dist = 0.15 * atr

        # Buy Setup (Discount)
        if range_pct <= 35 and rsi <= 38:
            sl = c - sl_dist
            tp1 = c + (1.0 * sl_dist)
            tp2 = c + (2.5 * sl_dist)
            return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🟢 BUY {name}</b>
⏱ <b>15-Minute Chart | 🎯 On-Demand Scan</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!
📊 <b>Rationale:</b> {range_pct:.1f}% 24h Discount + RSI {rsi:.1f} Oversold"""

        # Sell Setup (Premium)
        elif range_pct >= 65 and rsi >= 62:
            sl = c + sl_dist
            tp1 = c - (1.0 * sl_dist)
            tp2 = c - (2.5 * sl_dist)
            return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🔴 SELL {name}</b>
⏱ <b>15-Minute Chart | 🎯 On-Demand Scan</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!
📊 <b>Rationale:</b> {range_pct:.1f}% 24h Premium + RSI {rsi:.1f} Overbought"""

        # Mid-Range (No Setup)
        else:
            zone = "Discount" if range_pct <= 45 else ("Premium" if range_pct >= 55 else "Equilibrium")
            return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
{emoji} <b>{name} STATUS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Price:</b> <code>{c:,.{digits}f}</code>
📊 <b>24h Range:</b> <code>{range_pct:.1f}%</code> ({zone})
📈 <b>RSI (14):</b> <code>{rsi:.1f}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏸ <b>Status:</b> No high-conviction setup right now. Price is in mid-range. Wait for discount (<35%) or premium (>65%) sweep!"""
    except Exception as e:
        return f"❌ Error analyzing {name}: {e}"


def run_full_market_scan() -> str:
    import yfinance as yf
    import pandas as pd
    import numpy as np

    setups = []
    status_lines = []

    for sym, meta in ASSETS.items():
        name = meta["name"]
        emoji = meta["emoji"]
        digits = meta["digits"]
        cent_lot = meta["cent_lot"]

        try:
            df = yf.download(sym, period="5d", interval="15m", progress=False)
            if df.empty or len(df) < 50: continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            hl = df["High"] - df["Low"]
            hc = np.abs(df["High"] - df["Close"].shift())
            lc = np.abs(df["Low"] - df["Close"].shift())
            df["ATR"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

            df["H24"] = df["High"].shift(1).rolling(96).max()
            df["L24"] = df["Low"].shift(1).rolling(96).min()
            df["Range_Pct"] = ((df["Close"] - df["L24"]) / (df["H24"] - df["L24"])) * 100

            df = df.dropna()
            cur = df.iloc[-1]
            c = float(cur["Close"])
            rsi = float(cur["RSI"])
            range_pct = float(cur["Range_Pct"])
            atr = float(cur["ATR"])

            sl_dist = 0.2 * atr
            if sl_dist < 0.15 * atr: sl_dist = 0.15 * atr

            # Buy Setup
            if range_pct <= 35 and rsi <= 38:
                sl = c - sl_dist; tp1 = c + sl_dist; tp2 = c + (2.5 * sl_dist)
                setups.append(f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🟢 BUY {name}</b>
⏱ <b>15-Minute Chart | 🎯 Live Scan</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!
📊 <b>Rationale:</b> {range_pct:.1f}% 24h Discount + RSI {rsi:.1f} Oversold""")

            # Sell Setup
            elif range_pct >= 65 and rsi >= 62:
                sl = c + sl_dist; tp1 = c - sl_dist; tp2 = c - (2.5 * sl_dist)
                setups.append(f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🔴 SELL {name}</b>
⏱ <b>15-Minute Chart | 🎯 Live Scan</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!
📊 <b>Rationale:</b> {range_pct:.1f}% 24h Premium + RSI {rsi:.1f} Overbought""")

            else:
                zone = "🟢 Disc" if range_pct <= 35 else ("🔴 Prem" if range_pct >= 65 else "⚪ Mid")
                status_lines.append(f"• {emoji} <b>{name[:8]}:</b> <code>{c:,.{digits}f}</code> | {range_pct:.0f}% ({zone}) | RSI: {rsi:.0f}")

        except Exception as e:
            print(f"Error {sym}: {e}")

    now_kh = datetime.now(timezone.utc).strftime('%H:%M UTC')
    
    if setups:
        return "\n\n".join(setups)
    else:
        overview = "\n".join(status_lines)
        return f"""📡 <b>MARKET RADAR OVERVIEW ({now_kh})</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
{overview}
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏸ <b>Status:</b> All assets currently in mid-range or extension phase. No clean high-probability entry right now. Will alert automatically when a sweep occurs! 🎯"""


def get_status_report() -> str:
    now_utc = datetime.now(timezone.utc)
    hr = now_utc.hour
    now_str = now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    if 7 <= hr <= 12:
        session = "🇬🇧 London Session Open"
    elif 13 <= hr <= 20:
        session = "🇺🇸 New York Session (High Volatility!)"
    else:
        session = "🌐 Asian / Pre-Market Session"

    return f"""🤖 <b>APEX TRADING ENGINE STATUS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱ <b>Clock:</b> {now_str}
🏛 <b>Active Session:</b> {session}
🛡 <b>Engines Running:</b>
  • Engine 1: Macro 1H FVG Radar 🟢
  • Engine 2: 15M Institutional Discount Sweep 🟢
💰 <b>Risk Model:</b> 🏆 Champion 3-Clip Execution
━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Type /scan to run an instant multi-asset scan! 🚀</i>"""


def get_help_message() -> str:
    return """🎮 <b>APEX AI ASSISTANT COMMANDS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
👉 <b>/scan</b>  ➔ Full market institutional scan
👉 <b>/gold</b>  ➔ Gold (XAU/USD) live analysis
👉 <b>/btc</b>   ➔ Bitcoin (BTC/USD) live analysis
👉 <b>/eth</b>   ➔ Ethereum (ETH/USD) live analysis
👉 <b>/status</b>➔ System status & session clock
━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Just tap any command above to run it instantly! 🎯</i>"""


def poll_updates():
    print("================================================================")
    print(" 🤖 APEX INTERACTIVE TELEGRAM BOT LISTENER ACTIVE")
    print(" Listening for commands (/scan, /gold, /btc, /eth, /status)...")
    print("================================================================\n")

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=20"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("ok"):
                    time.sleep(2)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip().lower()
                    msg_id = msg.get("message_id")
                    chat_from = str(msg.get("chat", {}).get("id"))

                    if chat_from != str(CHAT_ID) and CHAT_ID:
                        # Only respond to authorized chat
                        continue

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Received command: {text}")

                    if text in ["/start", "/help", "help"]:
                        send_message(get_help_message(), reply_to_id=msg_id)
                    elif text in ["/scan", "scan"]:
                        send_message("⏳ <i>Scanning live market feeds (Gold, BTC, ETH, Forex)...</i>", reply_to_id=msg_id)
                        res = run_full_market_scan()
                        send_message(res)
                    elif text in ["/gold", "gold"]:
                        send_message("⏳ <i>Analyzing Gold live price action...</i>", reply_to_id=msg_id)
                        res = run_single_asset_analysis("GC=F")
                        send_message(res)
                    elif text in ["/btc", "btc", "/bitcoin"]:
                        send_message("⏳ <i>Analyzing Bitcoin live price action...</i>", reply_to_id=msg_id)
                        res = run_single_asset_analysis("BTC-USD")
                        send_message(res)
                    elif text in ["/eth", "eth", "/ethereum"]:
                        send_message("⏳ <i>Analyzing Ethereum live price action...</i>", reply_to_id=msg_id)
                        res = run_single_asset_analysis("ETH-USD")
                        send_message(res)
                    elif text in ["/status", "status"]:
                        send_message(get_status_report(), reply_to_id=msg_id)

        except Exception as e:
            print(f"Polling warning: {e}")
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-scan":
        print(run_full_market_scan())
    else:
        poll_updates()
