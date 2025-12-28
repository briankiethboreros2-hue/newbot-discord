# keep_alive.py — FIXED FOR RENDER
from flask import Flask
import threading
import time
import requests
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "🎯 Discord Bot is online and running!"

@app.route('/health')
def health():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "timestamp": time.time()}, 200

@app.route('/status')
def status():
    """Status endpoint for monitoring"""
    return {
        "status": "running",
        "service": "discord-bot",
        "uptime": "active",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
    }

def ping_self():
    """Continuously ping the Render URL to keep the service alive."""
    # Use environment variable or default URL
    url = os.environ.get('RENDER_EXTERNAL_URL', 'https://newbot-discord.onrender.com')
    
    # Add /health endpoint for better monitoring
    ping_url = f"{url}/" if url.endswith('/') else f"{url}/"
    health_url = f"{url}/health" if not url.endswith('/') else f"{url}health"
    
    print(f"🔄 Self-pinger starting. Will ping: {url}")
    print(f"📡 Health check: {health_url}")

    ping_count = 0
    consecutive_failures = 0
    max_failures = 5
    
    while True:
        try:
            # Try health endpoint first
            r = requests.get(health_url, timeout=15)
            if r.status_code == 200:
                print(f"✅ Health check OK at {time.strftime('%H:%M:%S')}")
                consecutive_failures = 0
            else:
                print(f"⚠️ Health check returned {r.status_code}")
                consecutive_failures += 1
                
        except requests.exceptions.Timeout:
            print(f"⏱️ Ping timeout at {time.strftime('%H:%M:%S')}")
            consecutive_failures += 1
        except Exception as e:
            print(f"⚠️ Ping failed: {type(e).__name__}: {str(e)[:100]}")
            consecutive_failures += 1
        
        # If too many failures, try the main endpoint
        if consecutive_failures >= 3:
            try:
                r = requests.get(ping_url, timeout=10)
                print(f"🔄 Fallback ping: {r.status_code}")
                consecutive_failures = 0
            except:
                pass
        
        # Emergency restart if too many consecutive failures
        if consecutive_failures >= max_failures:
            print(f"🚨 {max_failures} consecutive ping failures! Service might be down.")
            # Could trigger a restart here if needed
            consecutive_failures = 0
        
        ping_count += 1
        if ping_count % 12 == 0:  # Every hour
            print(f"📊 Ping statistics: {ping_count} pings sent")
        
        time.sleep(300)  # 5 minutes (Render sleeps after 15 minutes of inactivity)

def run_flask():
    """Run Flask on the correct port for Render"""
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Flask server on port {port}...")
    
    # Disable Flask's development features for production
    app.run(
        host="0.0.0.0", 
        port=port, 
        debug=False, 
        use_reloader=False,
        threaded=True  # Better for handling multiple requests
    )

def start_keep_alive():
    """Start Flask and the ping thread."""
    # Start pinger in background (with small delay to let Flask start)
    time.sleep(2)
    threading.Thread(target=ping_self, daemon=True).start()
    
    # Start Flask server (this will block)
    run_flask()

# Export objects used by main.py
__all__ = ["app", "ping_self", "start_keep_alive"]
