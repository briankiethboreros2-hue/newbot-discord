# STABLE VERSION - BOT IN MAIN THREAD WITH ALL STABILITY FIXES
import discord
import os
import time
import json
import asyncio
import sys
import traceback
import signal
from datetime import datetime, timezone
from collections import defaultdict

from keep_alive import start_keep_alive

# Import modules
try:
    from modules.cleanup_system import CleanupSystem
    from modules.poll_voting import PollVoting
    print("✅ Successfully loaded modules")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    sys.exit(1)

# -----------------------
# 🛡️ STABILITY CONFIGURATION
# -----------------------
CLEANUP_ENABLED = True
MAX_CLEANUP_RETRIES = 3
SAVE_RETRY_COUNT = 3
shutdown_flag = False

def handle_shutdown(signum, frame):
    """Handle graceful shutdown"""
    global shutdown_flag
    print(f"\n🛑 Shutdown signal received ({signum}), saving data...")
    shutdown_flag = True
    save_data()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# -----------------------
# ERROR LOGGING
# -----------------------
def log_error(where, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] ERROR in {where}: {error}"
    print(error_msg)
    traceback.print_exc()

# -----------------------
# CONFIGURATION
# -----------------------
CHANNELS = {
    "main": 1437768842871832597,
    "recruit": 1437568595977834590,
    "reminder": 1369091668724154419,
    "staff_review": 1437586858417852438,
    "cleanup": 1454802873300025396,
    "admin": 1437586858417852438,
    "welcome": 1369091668724154419,
    "call": 1437575744824934531
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "og_imperius": 1437572916005834793,
    "imperius": 1437570031822176408,
    "demoted": 1454803208995340328
}

ADMIN_ROLES = [
    1389835747040694332,
    1437578521374363769,
    1437572916005834793,
    1438420490455613540
]

CLEANUP_CONFIG = {'channels': CHANNELS, 'roles': ROLES, 'admin_roles': ADMIN_ROLES}

STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"
JOIN_TRACKING_FILE = "member_join_tracking.json"

# -----------------------
# LOAD & SAVE JSON (ATOMIC)
# -----------------------
class AtomicJSONManager:
    @staticmethod
    def load_json(path, default):
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
            return default
        except:
            return default

    @staticmethod
    def atomic_save(path, data):
        try:
            temp = path + ".tmp"
            with open(temp, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp, path)
            return True
        except:
            return False

json_manager = AtomicJSONManager()

def load_data():
    global state, pending_recruits, member_join_tracking
    state = json_manager.load_json(STATE_FILE, {"message_counter": 0, "current_reminder": 0})
    pending_recruits = json_manager.load_json(PENDING_FILE, {})
    member_join_tracking = json_manager.load_json(JOIN_TRACKING_FILE, {})
    print(f"📂 Loaded {len(pending_recruits)} pending recruits")

def save_data():
    json_manager.atomic_save(STATE_FILE, state)
    json_manager.atomic_save(PENDING_FILE, pending_recruits)
    json_manager.atomic_save(JOIN_TRACKING_FILE, member_join_tracking)

# -----------------------
# BOT SETUP
# -----------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)
cleanup_system = None
poll_voting = None

# -----------------------
# EVENTS
# -----------------------
@client.event
async def on_ready():
    print(f"🚀 Bot online as {client.user}")
    load_data()

    global cleanup_system, poll_voting
    try:
        cleanup_system = CleanupSystem(client, CLEANUP_CONFIG)
        poll_voting = PollVoting(client)
        print("🧠 Modules initialized")
    except Exception as e:
        log_error("MODULE_INIT", e)

@client.event
async def on_presence_update(before, after):
    if shutdown_flag or after.bot:
        return
    
    if after.id in ADMIN_ROLES:
        print(f"👑 {after.name} is now {after.status}")

    if cleanup_system:
        await cleanup_system.track_user_activity(after.id, "presence_update")

@client.event
async def on_message(message):
    if shutdown_flag or message.author.bot:
        return
    
    if cleanup_system:
        await cleanup_system.track_user_activity(message.author.id, "message")

# -----------------------
# START KEEP-ALIVE + BOT
# -----------------------
if __name__ == "__main__":
    print("🎯 Booting bot...")

    # Start Flask uptime system in background thread
    flask = asyncio.to_thread(start_keep_alive)
    asyncio.run(flask)  # launches Flask without blocking bot

    # Start Discord bot (auto reconnect enabled)
    try:
        TOKEN = os.getenv("DISCORD_TOKEN")
        if not TOKEN:
            print("❌ No bot token found in DISCORD_TOKEN env var")
            sys.exit(1)
        
        client.run(TOKEN, reconnect=True)
    except Exception as e:
        log_error("BOT_START", e)
