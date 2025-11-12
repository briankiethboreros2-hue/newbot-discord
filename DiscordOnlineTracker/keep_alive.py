from flask import Flask
import threading
import requests
import time

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
            res = requests.get(url)
            print(f"✅ Self-ping successful ({res.status_code}) to {url}")
        except Exception as e:
            print("⚠️ Ping failed:", e)
        time.sleep(240)  # wait 4 minutes between pings

def start_keep_alive():
    """Start Flask and the self-pinger."""
    threading.Thread(target=ping_self, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    start_keep_alive()
