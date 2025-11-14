# keep_alive.py — CLEAN & FIXED

from flask import Flask
import threading
import time
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def ping_self():
    """Continuously ping the Render URL to keep the service alive."""
    url = "https://newbot-discord.onrender.com"  # your actual Render URL
    print(f"🔄 Self-pinger starting. Will ping: {url}")

    while True:
        try:
            r = requests.get(url, timeout=10)
            print(f"✅ Self-ping OK ({r.status_code})")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")

        time.sleep(240)   # every 4 minutes

def start_keep_alive():
    """Start Flask and the ping thread."""
    threading.Thread(target=ping_self, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, debug=False)

# Export objects used by main.py
__all__ = ["app", "ping_self"]
