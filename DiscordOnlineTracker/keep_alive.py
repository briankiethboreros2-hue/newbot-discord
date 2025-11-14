from flask import Flask
import threading
import requests
import time

app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"


def ping_self():
    """Continuously pings the Render URL to keep the service awake."""
    url = "https://newbot-discord.onrender.com"  # Replace with your exact Render URL
    print(f"🔄 Self-pinger active. Pinging: {url}")

    while True:
        try:
            # Timeout prevents thread deadlock if Render stalls
            res = requests.get(url, timeout=10)
            print(f"✅ Ping OK ({res.status_code}) → {url}")
        except Exception as e:
            print(f"⚠️ Ping error: {e}")

        time.sleep(240)  # 4 minutes interval (safe for Render free tier)
