# render_start.py - SIMPLE START FOR RENDER
import os
import threading
from keep_alive import app
from main import run_bot_forever

def start_bot():
    print("🤖 Starting Discord bot...")
    run_bot_forever()

if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask (this blocks, which Render expects)
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)