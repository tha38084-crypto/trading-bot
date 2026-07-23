"""
===============================================================================
PLAN B 24/7 BACKGROUND DAEMON LOOP SCANNER
===============================================================================
Runs continuously in the background, checking market data every 15 minutes,
and sending live alerts to your Telegram app!
===============================================================================
"""

import sys
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import subprocess

print("=" * 80)
print("🚀 PLAN B 24/7 BACKGROUND DAEMON LOOP ACTIVE")
print("• Will automatically run 'plan_b_telegram_scanner.py' every 15 minutes.")
print("• Sent alerts will arrive directly on Kai's Telegram phone app.")
print("=" * 80 + "\n")

counter = 1
while True:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Executing Loop Scan #{counter}...")
    try:
        res = subprocess.run([sys.executable, "plan_b_telegram_scanner.py"], capture_output=True, text=True)
        print(res.stdout)
    except Exception as e:
        print(f"Loop error: {e}")
        
    counter += 1
    print("[WAITING] Sleeping 15 minutes until next market scan...\n")
    time.sleep(900)  # 15 minutes = 900 seconds
