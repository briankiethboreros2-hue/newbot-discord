# keep_alive.py — FIXED FOR RENDER
from flask import Flask
import threading
import time
import requests
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def ping_self():
    """Continuously ping the Render URL to keep the service alive."""
    url = "https://newbot-discord.onrender.com"
    print(f"🔄 Self-pinger starting. Will ping: {url}")

    while True:
        try:
            r = requests.get(url, timeout=10)
            print(f"✅ Self-ping OK ({r.status_code}) at {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")

        time.sleep(300)  # 5 minutes

def run_flask():
    """Run Flask on the correct port for Render"""
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_keep_alive():
    """Start Flask and the ping thread."""
    # Start pinger in background
    threading.Thread(target=ping_self, daemon=True).start()
    # Start Flask server (this will block)
    run_flask()

# Export objects used by main.py
__all__ = ["app", "ping_self", "start_keep_alive"]
