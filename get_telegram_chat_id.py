"""
Fetch Telegram Chat ID for user's Bot Token
"""
import sys
import urllib.request
import json

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

print(f"[FETCHING] Contacting Telegram API to get your Chat ID...")

try:
    req = urllib.request.urlopen(url)
    data = json.loads(req.read().decode('utf-8'))
    
    results = data.get('result', [])
    if results:
        chat_id = results[-1]['message']['chat']['id']
        first_name = results[-1]['message']['chat'].get('first_name', 'User')
        print(f"\n[OK] CHAT ID FOUND! Chat ID: {chat_id} (User: {first_name})")
    else:
        print("\n[WARNING] NO MESSAGE RECEIVED YET!")
        print("👉 Please open Telegram on your phone, find your new bot, and tap START or type 'hello'.")
except Exception as e:
    print(f"Error fetching Chat ID: {e}")
