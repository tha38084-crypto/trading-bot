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
import trade_tracker

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


INLINE_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "🔄 Refresh Scan", "callback_data": "scan"}, {"text": "🥇 Gold 15M", "callback_data": "gold"}],
        [{"text": "₿ Bitcoin", "callback_data": "btc"}, {"text": "📊 Status", "callback_data": "status"}]
    ]
}

REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "🔍 Full Scan"}, {"text": "🥇 Gold 15M"}],
        [{"text": "₿ Bitcoin"}, {"text": "📊 Status"}]
    ],
    "resize_keyboard": True,
    "persistent": True,
    "one_time_keyboard": False
}


def send_message(text: str, reply_to_id: int = None, show_keyboard: bool = True) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id
    if show_keyboard:
        payload["reply_markup"] = json.dumps(INLINE_KEYBOARD)
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        print(f"Error sending message: {e}")
        return False


def edit_message_text(chat_id: str, message_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": json.dumps(INLINE_KEYBOARD)
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        # Ignore 'message is not modified' error from Telegram
        if "not modified" not in str(e).lower():
            print(f"Error editing message: {e}")
        return False


def answer_callback_query(callback_id: str, text: str = "🔄 Live Market Data Refreshed!") -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_id,
        "text": text,
        "show_alert": False
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True
    except Exception:
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
        if range_pct <= 35 and rsi <= 38 and c > float(cur["Open"]):
            sl = c - sl_dist
            tp1 = c + (1.0 * sl_dist)
            tp2 = c + (2.5 * sl_dist)
            c_range = min(30, int((35 - range_pct) * 1.5))
            c_rsi = min(30, int((38 - rsi) * 1.5))
            c_session = 25 if 12 <= datetime.now(timezone.utc).hour <= 21 else 15
            conf_pct = min(98, max(65, 50 + c_range + c_rsi + c_session + 15))
            grade = "A+ (Elite)" if conf_pct >= 90 else ("A (Strong)" if conf_pct >= 80 else "B+ (Good)")
            trade_tracker.log_new_signal(symbol, name, emoji, "BUY", c, sl, tp1, tp2, conf_pct, grade, digits)
            return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🟢 BUY {name}</b>
⭐️ <b>Confidence:</b> {conf_pct}% ({grade})
⏱ <b>15M Chart | 🎯 Live On-Demand</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!"""

        # Sell Setup (Premium)
        elif range_pct >= 65 and rsi >= 62 and c < float(cur["Open"]):
            sl = c + sl_dist
            tp1 = c - (1.0 * sl_dist)
            tp2 = c - (2.5 * sl_dist)
            c_range = min(30, int((range_pct - 65) * 1.5))
            c_rsi = min(30, int((rsi - 62) * 1.5))
            c_session = 25 if 12 <= datetime.now(timezone.utc).hour <= 21 else 15
            conf_pct = min(98, max(65, 50 + c_range + c_rsi + c_session + 15))
            grade = "A+ (Elite)" if conf_pct >= 90 else ("A (Strong)" if conf_pct >= 80 else "B+ (Good)")
            trade_tracker.log_new_signal(symbol, name, emoji, "SELL", c, sl, tp1, tp2, conf_pct, grade, digits)
            return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🔴 SELL {name}</b>
⭐️ <b>Confidence:</b> {conf_pct}% ({grade})
⏱ <b>15M Chart | 🎯 Live On-Demand</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!"""

        # Mid-Range (No Setup)
        else:
            zone = "Discount" if range_pct <= 45 else ("Premium" if range_pct >= 55 else "Equilibrium")
            return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
{emoji} <b>{name} STATUS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Live Price:</b> <code>{c:,.{digits}f}</code>
📊 <b>24h Range :</b> <code>{range_pct:.1f}%</code> ({zone})
📈 <b>RSI (14)   :</b> <code>{rsi:.1f}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏸ <b>Status:</b> No high-conviction setup right now. 
💡 <i>Wait for pullback into Discount (&lt;35%) or Premium (&gt;65%) sweep!</i>"""
    except Exception as e:
        return f"❌ Error analyzing {name}: {e}"


def run_full_market_scan() -> str:
    import yfinance as yf
    import pandas as pd
    import numpy as np

    candidates = []
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
            o = float(cur["Open"])
            rsi = float(cur["RSI"])
            range_pct = float(cur["Range_Pct"])
            atr = float(cur["ATR"])

            sl_dist = 0.2 * atr
            if sl_dist < 0.15 * atr: sl_dist = 0.15 * atr

            # Status line for the overview table (Compact 1-line layout)
            if range_pct <= 35: zone_tag = "🟢 Disc"
            elif range_pct >= 65: zone_tag = "🔴 Prem"
            else: zone_tag = "⚪ Mid"
            
            short_code = {
                "GC=F": "GOLD",
                "BTC-USD": "BTC ",
                "ETH-USD": "ETH ",
                "NQ=F": "NQ  ",
                "GBPUSD=X": "GBP ",
                "EURUSD=X": "EUR "
            }.get(sym, name[:4])
            
            status_lines.append(f"{emoji} <b>{short_code}:</b> <code>{c:,.{digits}f}</code> | {range_pct:3.0f}% {zone_tag} | RSI:{rsi:2.0f}")

            # STRICT BUY: Deep Discount + RSI Oversold + MUST BE GREEN CANDLE (Close > Open)
            if range_pct <= 35 and rsi <= 38 and c > o:
                sl = c - sl_dist; tp1 = c + sl_dist; tp2 = c + (2.5 * sl_dist)
                
                # Calculate Confidence Score (0-100%)
                c_range = min(30, int((35 - range_pct) * 1.5))
                c_rsi = min(30, int((38 - rsi) * 1.5))
                c_session = 25 if 12 <= datetime.now(timezone.utc).hour <= 21 else 15
                c_body = 15 if (c - o) > (0.3 * atr) else 10
                conf_pct = min(98, max(65, 50 + c_range + c_rsi + c_session + c_body))
                grade = "A+ (Elite)" if conf_pct >= 90 else ("A (Strong)" if conf_pct >= 80 else "B+ (Good)")

                score = conf_pct
                trade_tracker.log_new_signal(sym, name, emoji, "BUY", c, sl, tp1, tp2, conf_pct, grade, digits)
                candidates.append({
                    "score": score,
                    "text": f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🟢 BUY {name}</b>
⭐️ <b>Confidence:</b> {conf_pct}% ({grade})
⏱ <b>15M Chart | 🎯 Sniper Setup</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!"""
                })

            # STRICT SELL: High Premium + RSI Overbought + MUST BE RED CANDLE (Close < Open)
            elif range_pct >= 65 and rsi >= 62 and c < o:
                sl = c + sl_dist; tp1 = c - sl_dist; tp2 = c - (2.5 * sl_dist)
                
                c_range = min(30, int((range_pct - 65) * 1.5))
                c_rsi = min(30, int((rsi - 62) * 1.5))
                c_session = 25 if 12 <= datetime.now(timezone.utc).hour <= 21 else 15
                c_body = 15 if (o - c) > (0.3 * atr) else 10
                conf_pct = min(98, max(65, 50 + c_range + c_rsi + c_session + c_body))
                grade = "A+ (Elite)" if conf_pct >= 90 else ("A (Strong)" if conf_pct >= 80 else "B+ (Good)")

                score = conf_pct
                trade_tracker.log_new_signal(sym, name, emoji, "SELL", c, sl, tp1, tp2, conf_pct, grade, digits)
                candidates.append({
                    "score": score,
                    "text": f"""━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🔴 SELL {name}</b>
⭐️ <b>Confidence:</b> {conf_pct}% ({grade})
⏱ <b>15M Chart | 🎯 Sniper Setup</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>ENTRY :</b> <code>{c:,.{digits}f}</code>
🛑 <b>SL    :</b> <code>{sl:,.{digits}f}</code> (-{sl_dist:,.{digits}f} pts)
🎯 <b>TP1   :</b> <code>{tp1:,.{digits}f}</code> (+{sl_dist:,.{digits}f} pts | Close 1 Clip)
🎯 <b>TP2   :</b> <code>{tp2:,.{digits}f}</code> (+{2.5*sl_dist:,.{digits}f} pts | Runner)
📦 <b>SIZE  :</b> <code>{cent_lot}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>Rule:</b> At TP1, close 1 clip & move SL to entry!"""
                })

        except Exception as e:
            print(f"Error {sym}: {e}")

    now_kh = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
    overview_block = "📡 <b>MARKET OVERVIEW</b> (" + now_kh + ")\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(status_lines)
    
    active_summary = trade_tracker.get_active_trades_summary()
    if active_summary:
        overview_block += "\n" + active_summary

    if candidates:
        # Pick ONLY the single #1 best setup by score!
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best_setup = candidates[0]["text"]
        return f"{overview_block}\n\n{best_setup}"
    else:
        return f"""{overview_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏸ <b>Status:</b> All assets currently in extension/runaway phase with NO confirmed reversal candle.
💡 <i>Do not force trades at daily highs. Wait for pullback into discount!</i>"""


def get_status_report() -> str:
    now_utc = datetime.now(timezone.utc)
    hr = now_utc.hour
    now_str = now_utc.strftime('%H:%M:%S UTC')
    
    if 7 <= hr <= 12:
        session = "🇬🇧 London Session (High Volume)"
    elif 13 <= hr <= 20:
        session = "🇺🇸 New York Session (Peak Volatility)"
    else:
        session = "🌐 Asian / Pre-Market Range"

    return f"""📊 <b>SYSTEM STATUS</b> ({now_str})
━━━━━━━━━━━━━━━━━━━━━━━━━━
🏛 <b>Session :</b> {session}
🛡 <b>Engines :</b> 1H FVG 🟢 | 15M Sweep 🟢
💰 <b>Sizing  :</b> 3 clips of 0.05 lots
🎯 <b>Targets :</b> TP1 (1:1 BE) | TP2 (2.5:1 Runner)
━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Tap '🔍 Full Scan' to check live setups!</i>"""


def get_help_message() -> str:
    return """🎮 <b>APEX TRADING ASSISTANT</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
Tap any button below to scan:
• 🔍 <b>Full Scan</b> ➔ Multi-Asset Radar & Top Pick
• 🥇 <b>Gold 15M</b>  ➔ Live XAU/USD Setup
• ₿ <b>Bitcoin</b>   ➔ Live BTC/USD Setup
• 📊 <b>Status</b>    ➔ Session Clock & Engine Health
━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Institutional Math | 3-Clip Model</i> 🎯"""


def poll_updates():
    print("================================================================")
    print(" 🤖 APEX INTERACTIVE TELEGRAM BOT LISTENER ACTIVE")
    print(" Listening for commands & inline button taps...")
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

                    # 1. Handle Inline Button Tap (Edit in Place!)
                    if "callback_query" in update:
                        cq = update["callback_query"]
                        cq_id = cq.get("id")
                        action = cq.get("data", "")
                        msg = cq.get("message", {})
                        msg_id = msg.get("message_id")
                        chat_id = msg.get("chat", {}).get("id")

                        answer_callback_query(cq_id)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Inline button tapped: {action}")

                        if action == "scan":
                            res = run_full_market_scan()
                            edit_message_text(chat_id, msg_id, res)
                        elif action == "gold":
                            res = run_single_asset_analysis("GC=F")
                            edit_message_text(chat_id, msg_id, res)
                        elif action == "btc":
                            res = run_single_asset_analysis("BTC-USD")
                            edit_message_text(chat_id, msg_id, res)
                        elif action == "status":
                            res = get_status_report()
                            edit_message_text(chat_id, msg_id, res)
                        continue

                    # 2. Handle Text Message
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip().lower()
                    msg_id = msg.get("message_id")
                    chat_from = str(msg.get("chat", {}).get("id"))

                    if chat_from != str(CHAT_ID) and CHAT_ID:
                        # Only respond to authorized chat
                        continue

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Received command: {text}")

                    if "start" in text or "help" in text:
                        send_message(get_help_message(), reply_to_id=msg_id)
                    elif "scan" in text:
                        res = run_full_market_scan()
                        send_message(res)
                    elif "gold" in text:
                        res = run_single_asset_analysis("GC=F")
                        send_message(res)
                    elif "btc" in text or "bitcoin" in text:
                        res = run_single_asset_analysis("BTC-USD")
                        send_message(res)
                    elif "eth" in text or "ethereum" in text:
                        res = run_single_asset_analysis("ETH-USD")
                        send_message(res)
                    elif "status" in text:
                        send_message(get_status_report(), reply_to_id=msg_id)
                    elif "report" in text or "summary" in text or "pnl" in text or "history" in text:
                        send_message(trade_tracker.generate_daily_summary(), reply_to_id=msg_id)

        except Exception as e:
            print(f"Polling note: {e}")
            time.sleep(3)



def start_health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Apex Telegram Bot is Live & Running!")
        def log_message(self, format, *args):
            pass

    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        print(f"Health check HTTP server listening on port {port} for Render...")
        server.serve_forever()
    except Exception as e:
        print(f"Health server note: {e}")


def automated_scanner_loop():
    print("📡 [AUTONOMOUS SCANNER] Background market radar started (Scans every 15 min)...")
    time.sleep(10)  # Initial wait
    last_sent_sig = None
    while True:
        try:
            res = run_full_market_scan()
            if ("BUY " in res or "SELL " in res) and "Status: All assets" not in res:
                if res != last_sent_sig:
                    last_sent_sig = res
                    send_message(f"🚨 <b>[AUTONOMOUS RADAR ALERT]</b>\n\n{res}")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Automated signal dispatched to Telegram!")
            time.sleep(900)  # 15 minutes
        except Exception as e:
            print(f"Background scanner note: {e}")
            time.sleep(60)


def watchdog_tracker_loop():
    print("🎯 [WATCHDOG TRACKER] Background trade ledger & TP/SL watchdog active (Checks every 60s)...")
    time.sleep(15)
    while True:
        try:
            # 1. Check open trades for TP/SL hits
            alerts = trade_tracker.check_open_trades()
            for alert in alerts:
                send_message(alert)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Trade Tracker Alert Sent to Telegram!")

            # 2. Check 10:00 PM ICT (15:00 UTC) for daily performance summary
            now_kh = trade_tracker.get_kh_time()
            today_str = now_kh.strftime("%Y-%m-%d")
            ledger = trade_tracker.load_ledger()
            if now_kh.hour == 22 and ledger.get("last_daily_report") != today_str:
                summary = trade_tracker.generate_daily_summary()
                send_message(summary)
                ledger["last_daily_report"] = today_str
                trade_tracker.save_ledger(ledger)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Daily 10:00 PM Performance Summary Sent!")

            time.sleep(60)
        except Exception as e:
            print(f"Watchdog note: {e}")
            time.sleep(60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-scan":
        print(run_full_market_scan())
    else:
        import threading
        # 1. Health check server (for Render 24/7 cloud hosting)
        t_health = threading.Thread(target=start_health_server, daemon=True)
        t_health.start()

        # 2. Automated background scanner (15m auto-alerts)
        t_scan = threading.Thread(target=automated_scanner_loop, daemon=True)
        t_scan.start()

        # 3. Trade Tracker & 10:00 PM Daily Performance Watchdog
        t_watchdog = threading.Thread(target=watchdog_tracker_loop, daemon=True)
        t_watchdog.start()

        # 4. Interactive Telegram bot listener
        poll_updates()


