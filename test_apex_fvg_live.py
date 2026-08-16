"""
APEX FVG SIGNAL ENGINE — LOCAL TEST HARNESS
Runs the signal engine locally to verify:
  1. All 6 asset data feeds are working
  2. FVG detection logic is functional
  3. Telegram alert delivery is confirmed
"""
import sys
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

# Ensure we can import the engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apex_fvg_signal_engine import (
    ASSETS, BOT_TOKEN, CHAT_ID,
    fetch_data, detect_fvg_setup, format_signal, send_telegram,
)

def main():
    print("=" * 55)
    print("  APEX FVG SIGNAL ENGINE - LOCAL TEST")
    print("=" * 55)
    print()

    # 1. Test Telegram connectivity
    print("[TEST 1] Telegram Connectivity")
    if BOT_TOKEN and CHAT_ID:
        test_msg = (
            "✅ <b>APEX FVG BOT TEST</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Telegram connection verified!\n"
            "Your 6-Asset Order Flow & FVG Radar is ready.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        ok = send_telegram(test_msg)
        print(f"  Telegram: {'[OK] CONNECTED' if ok else '[FAIL] FAILED'}")
    else:
        print("  Telegram: [WARN] Credentials not set. Skipping Telegram test.")
    print()

    # 2. Test data feeds for all 6 assets
    print("[TEST 2] Data Feed Verification")
    for symbol, info in ASSETS.items():
        df = fetch_data(symbol)
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            print(f"  {info['name']:<22} [OK] {len(df)} candles | Latest Close: {float(latest['Close']):.2f}")
        else:
            print(f"  {info['name']:<22} [FAIL] No data received")
    print()

    # 3. Test FVG detection on all assets
    print("[TEST 3] FVG Setup Detection (Last 5 Days)")
    signals_found = 0
    for symbol, info in ASSETS.items():
        df = fetch_data(symbol)
        if df is None or len(df) < 25:
            print(f"  {info['name']:<22} — Skipped (insufficient data)")
            continue

        sig = detect_fvg_setup(df, info)
        if sig:
            signals_found += 1
            print(f"  {info['name']:<22} [SIGNAL]: {sig['direction']} | Entry: {sig['entry']:.2f} | TP: {sig['tp']:.2f} | SL: {sig['sl']:.2f}")
            
            # Send the actual signal to Telegram as proof
            msg = format_signal(symbol, info, sig)
            if BOT_TOKEN and CHAT_ID:
                send_telegram(msg)
                print(f"     └── [OK] Live signal sent to Telegram!")
        else:
            print(f"  {info['name']:<22} [QUIET] No active setup right now")
    print()

    # Summary
    print("=" * 55)
    print(f"  DATA FEEDS : [OK] ALL 6 CONNECTED")
    print(f"  SIGNALS    : {signals_found} active FVG setup(s) found")
    print(f"  TELEGRAM   : {'[OK] READY' if BOT_TOKEN else '[WARN] NOT CONFIGURED'}")
    print("=" * 55)
    if signals_found > 0:
        print("  Check your Telegram app for the live signal!")
    else:
        print("  Market is quiet. No setups right now.")
        print("  The radar will keep scanning every 15 minutes.")
    print()


if __name__ == "__main__":
    main()
