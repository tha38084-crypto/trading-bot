"""
Send Live Test Signal Card to User's Telegram Phone App
"""
import sys
import urllib.request
import urllib.parse
import json

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

message_text = """
=========================================
🏆 PLAN B HIGH-PROBABILITY SIGNAL ALERT 🏆
=========================================
• Asset Pair      : EUR/USD (1-Hour Chart)
• Action Signal   : 🟢 BUY (LONG)
• Signal Time     : Live Test Signal
-----------------------------------------
• Suggested Entry : 1.0850
• Stop-Loss (SL)  : 1.0838  --> Risk: -$4.00 (2.0% STRICT RISK)
• Take-Profit 1   : 1.0862  --> TP1 (50% exit + Move SL to Breakeven $0.00)
• Take-Profit 2   : 1.0880  --> TP2 (50% exit for +$10.00 total win)
=========================================
👉 Action: Open your Exness / MT5 Demo app & place this order!
=========================================
"""

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
params = {
    "chat_id": CHAT_ID,
    "text": message_text
}

data = urllib.parse.urlencode(params).encode('utf-8')

print("[SENDING] Transmitting test Plan B Signal Card to your Telegram phone app...")

try:
    req = urllib.request.Request(url, data=data)
    response = urllib.request.urlopen(req)
    res_data = json.loads(response.read().decode('utf-8'))
    if res_data.get("ok"):
        print("\n🎉 SUCCESS! Test Signal Card delivered to your Telegram app!")
    else:
        print(f"\n⚠️ Telegram Delivery Error: {res_data}")
except Exception as e:
    print(f"Error sending message: {e}")
