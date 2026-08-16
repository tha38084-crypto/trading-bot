"""
SEND LIVE TELEGRAM SIGNAL DEMO
Dispatches a sample Apex FVG Signal directly to the user's Telegram.
"""
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BOT_TOKEN = "8805795541:AAFQxtzJrvJQlfBVazkVm4KwvSh9FSgfDro"
CHAT_ID = "5477873575"

now_utc = datetime.now(timezone.utc)

msg = (
    f"🎯 <b>[ APEX ORDER FLOW & FVG SIGNAL ]</b> 🎯\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"Asset: 🥇 <b>GOLD (XAU/USD)</b>\n"
    f"Direction: 🟢 <b>BUY</b> (Bullish Liquidity Sweep & Displacement)\n"
    f"Session: 🇬🇧 <b>London Open</b>\n"
    f"\n"
    f"📍 <b>FVG Entry Zone:</b> 2,428.50 — 2,430.00\n"
    f"💰 <b>Entry Price:</b> 2,429.20\n"
    f"🎯 <b>Take Profit (1:2.2 R:R):</b> 2,442.00 (+128 Pips)\n"
    f"🛑 <b>Stop Loss (Invalidation):</b> 2,424.00 (-52 Pips)\n"
    f"\n"
    f"💡 <i>Price swept the Asian session low at 2,425.00, trapped breakout sellers, and created an aggressive Bullish FVG displacement on the chart.</i>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"⏰ <b>Time:</b> {now_utc.strftime('%Y-%m-%d %H:%M UTC')}\n"
    f"🤖 <i>Apex V8.5 Cloud Radar Active</i>"
)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": msg,
    "parse_mode": "HTML",
}).encode()

req = urllib.request.Request(url, data=payload, method="POST")
with urllib.request.urlopen(req, timeout=15) as resp:
    if resp.status == 200:
        print("[SUCCESS] Test signal message sent to Telegram successfully!")
    else:
        print(f"[FAIL] HTTP Status: {resp.status}")
