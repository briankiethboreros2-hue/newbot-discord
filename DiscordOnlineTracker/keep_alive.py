from flask import Flask
import threading, requests, time

app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def ping_self():
    # Use the permanent Render URL
    url = "https://discord-bot-0ssb.onrender.com"
    print(f"🔄 Self-pinger starting. Will ping: {url}")

    while True:
        try:
            requests.get(url)
            print(f"✅ Self-ping successful to {url}")
        except Exception as e:
            print("Ping failed:", e)
        time.sleep(240)  # every 4 minutes

def start_keep_alive():
    # Launch the self-pinger in background
    threading.Thread(target=ping_self, daemon=True).start()
    # Run Flask as the main process
    app.run(host='0.0.0.0', port=8080)
