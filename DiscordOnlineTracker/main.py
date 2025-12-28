import threading
import discord
import os
import time
import json
import asyncio
import sys
import traceback
import random
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# IMPORT LOCAL FILES
from keep_alive import app, ping_self

# -----------------------
# 🛡️ INTERNAL LOGGING & SAFETY
# -----------------------
def log_error(where, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] CRASH in {where}: {str(error)}"
    print(error_msg)
    try:
        with open("bot_errors.log", "a") as f:
            f.write(error_msg + "\n")
            traceback.print_exc(file=f)
    except: pass

# -----------------------
# 🤖 BOT CONFIGURATION
# -----------------------
TOKEN = os.environ.get('DISCORD_TOKEN')
ANNOUNCEMENT_CHANNEL_ID = 123456789012345678 # <-- UPDATE THIS ID!

intents = discord.Intents.default()
intents.presences = True
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)

# -----------------------
# 🎭 ROLE DETECTION LOGIC
# -----------------------
def get_member_role_category(member):
    role_names = [role.name.lower() for role in member.roles]
    
    if any(name in role_names for name in ["queen", "queen👑"]):
        return "👑 **Queen**"
    elif "cᥣᥲᥒ mᥲstᥱr🌟" in role_names:
        return "🌟 **Clan Master**"
    elif "og-impedance🔫" in role_names:
        return "🔫 **OG-Impedance**"
    elif "impedance⭐" in role_names:
        return "⭐ **Impedance**"
    return "🙂 **Member**"

@client.event
async def on_ready():
    print(f'✅ Bot is online as {client.user}')
    print(f'🔧 Python: {sys.version}')
    print('------')

@client.event
async def on_presence_update(before, after):
    # Detect when someone goes from offline to online
    if before.status == discord.Status.offline and after.status != discord.Status.offline:
        channel = client.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if channel:
            category = get_member_role_category(after)
            msgs = [
                f"{category} {after.display_name} has arrived!",
                f"Welcome back, {category} {after.display_name}!",
                f"Look out! {category} {after.display_name} is online."
            ]
            await channel.send(random.choice(msgs))

# -----------------------
# 🚀 RENDER-FRIENDLY RUNNER
# -----------------------
def run_bot_forever():
    max_restarts = 10
    restart_count = 0
    while restart_count < max_restarts:
        try:
            if not TOKEN:
                print("❌ ERROR: No DISCORD_TOKEN found.")
                return
            client.run(TOKEN)
        except Exception as e:
            restart_count += 1
            log_error("STARTUP", e)
            time.sleep(15)

if __name__ == "__main__":
    # Start Flask/Keep-Alive in background
    def start_flask():
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)

    threading.Thread(target=start_flask, daemon=True).start()
    threading.Thread(target=ping_self, daemon=True).start()
    
    run_bot_forever()
