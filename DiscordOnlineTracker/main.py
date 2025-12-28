# STABLE VERSION - BOT IN MAIN THREAD WITH ALL STABILITY FIXES
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
import signal
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from keep_alive import app, ping_self, start_keep_alive

# Import modules
try:
    from cleanup_system import CleanupSystem
    from poll_voting import PollVoting
    print("✅ Successfully loaded modules")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("📁 Make sure you have the modules folder with required files")
    sys.exit(1)

# -----------------------
# 🛡️ STABILITY CONFIGURATION
# -----------------------
CLEANUP_ENABLED = True
MAX_CLEANUP_RETRIES = 3
SAVE_RETRY_COUNT = 3

# Global shutdown flag
shutdown_flag = False

def handle_shutdown(signum, frame):
    """Handle graceful shutdown"""
    global shutdown_flag
    print(f"\n🛑 Received shutdown signal ({signum}), saving data...")
    shutdown_flag = True

# Register signal handlers
signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# -----------------------
# ENHANCED ERROR HANDLING
# -----------------------
def log_error(where, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] ERROR in {where}: {str(error)}"
    print(error_msg)
    
    # Log to file with rotation
    try:
        log_file = "bot_errors.log"
        if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:
            rotate_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(log_file, f"bot_errors_{rotate_time}.log")
        
        with open(log_file, "a") as f:
            f.write(error_msg + "\n")
            traceback.print_exc(file=f)
            f.write("-" * 50 + "\n")
    except:
        pass
    
    traceback.print_exc()

def global_error_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        return
    log_error("GLOBAL", f"{exc_type.__name__}: {exc_value}")
    print("🔄 Attempting to restart in 30 seconds...")
    time.sleep(30)
    os._exit(1)

sys.excepthook = global_error_handler

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
    1389835747040694332,  # clan_master
    1437578521374363769,  # queen
    1437572916005834793,  # og_imperius
    1438420490455613540   # Additional admin role
]

# Configuration for modules
CLEANUP_CONFIG = {
    'channels': CHANNELS,
    'roles': ROLES,
    'admin_roles': ADMIN_ROLES
}

REMINDER_THRESHOLD = 50
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"
JOIN_TRACKING_FILE = "member_join_tracking.json"

# Recruitment questions
RECRUIT_QUESTIONS = [
    "1️⃣ Since you agreed to our terms and have read the rules, that also states we conduct clan tryouts. Do you agree to participate? (yes or no)",
    "2️⃣ We require CCN 1 week after the day you joined or got accepted, failed to comply with the requirements might face with penalty, What will be your future in-game name? (e.g., IM-Ryze)",
    "3️⃣ Our clan encourage members to improve, our members, OGs and Admins are always vocal when it comes to play making and correction of members. We are open so you can express yourself and also suggest, Are you open to communication about your personal gameplay and others suggestions? (yes or no)",
    "4️⃣ We value team chemistry, communication and overall team improvements so we prioritize playing with clan members than playing with others. so are you? (yes or no)",
    "5️⃣ We understand that sometimes there will be busy days and other priorities, we do have members who are working and also studying, are you working or a student?"
]

UPVOTE_EMOJI = "👍🏻"
DOWNVOTE_EMOJI = "👎🏻"

REMINDERS = [
    {"title": "🟢 Activity Reminder", "description": "Members must keep their status set only to \"Online\" while active."},
    {"title": "🧩 IGN Format", "description": "All members must use the official clan format: IM-(Your IGN)."},
    {"title": "🔊 Voice Channel Reminder", "description": "Members online must join the Public Call channel."}
]

# -----------------------
# 🛡️ ENHANCED SAFETY WRAPPERS
# -----------------------
class CircuitBreaker:
    """Circuit breaker for rate-limited operations"""
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
    
    def can_execute(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True
    
    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            print(f"⚠️ CIRCUIT BREAKER OPENED due to {self.failures} failures")
            self.state = "OPEN"

class SafetyWrappers:
    def __init__(self, client):
        self.client = client
        self.last_kick_time = 0
        self.kick_cooldown = 2.0
        self.last_role_assignment = 0
        self.role_cooldown = 1.0
        
        self.kick_circuit = CircuitBreaker(failure_threshold=3, reset_timeout=30)
        self.role_circuit = CircuitBreaker(failure_threshold=5, reset_timeout=30)
        
        # API rate limiting
        self.api_calls = []
        self.max_api_calls = 45  # Stay under Discord's 50/5 second limit
        self.api_window = 5  # seconds
        
        # Operations tracking
        self.in_progress_operations = {}
        
    async def check_rate_limit(self):
        """Check and enforce Discord API rate limits"""
        current_time = time.time()
        
        # Remove calls older than our window
        self.api_calls = [t for t in self.api_calls if current_time - t < self.api_window]
        
        # If we're approaching the limit, wait
        if len(self.api_calls) >= self.max_api_calls:
            oldest_call = self.api_calls[0]
            wait_time = self.api_window - (current_time - oldest_call)
            if wait_time > 0:
                print(f"⏱️ Rate limit approaching, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        # Record this call
        self.api_calls.append(current_time)
    
    async def assign_role_safe(self, member, role_id, reason=""):
        operation_key = f"role_{member.id}_{role_id}"
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
            
        self.in_progress_operations[operation_key] = True
        
        try:
            # Check rate limits
            await self.check_rate_limit()
            
            if not self.role_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
                
            if not member or not role_id:
                return False, "Invalid parameters"
            
            # Rate limiting between operations
            current_time = time.time()
            if current_time - self.last_role_assignment < self.role_cooldown:
                await asyncio.sleep(self.role_cooldown)
                
            guild = member.guild
            role = guild.get_role(int(role_id))
            
            if not role:
                self.role_circuit.record_failure()
                return False, f"Role not found (ID: {role_id})"
                
            if role in member.roles:
                self.role_circuit.record_success()
                return True, "Already has role"
                
            # Permission checks
            bot_member = guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.manage_roles:
                self.role_circuit.record_failure()
                return False, "Bot lacks manage_roles permission"
                
            if role.position >= bot_member.top_role.position:
                self.role_circuit.record_failure()
                return False, f"Bot's role is not high enough to assign {role.name}"
                
            await member.add_roles(role, reason=reason)
            self.last_role_assignment = time.time()
            self.role_circuit.record_success()
            return True, f"Successfully assigned role {role.name} to {member.display_name}"
            
        except discord.Forbidden:
            self.role_circuit.record_failure()
            return False, "Bot lacks permissions (403 Forbidden)"
        except discord.HTTPException as e:
            self.role_circuit.record_failure()
            if e.status == 429:
                print(f"🛑 Discord Rate Limit hit! Waiting...")
                wait_time = random.uniform(5, 10)
                await asyncio.sleep(wait_time)
                try:
                    await member.add_roles(role, reason=reason)
                    self.role_circuit.record_success()
                    return True, "Assigned role after cooldown retry"
                except:
                    return False, "Rate limited again on retry"
            return False, f"HTTP error {e.status}: {e.text}"
        except Exception as e:
            self.role_circuit.record_failure()
            log_error("assign_role_safe", e)
            return False, f"Unexpected error: {str(e)[:100]}"
        finally:
            if operation_key in self.in_progress_operations:
                del self.in_progress_operations[operation_key]

    async def kick_member_safe(self, member, reason=""):
        operation_key = f"kick_{member.id}"
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
            
        self.in_progress_operations[operation_key] = True
        
        try:
            # Check rate limits
            await self.check_rate_limit()
            
            if not self.kick_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
                
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_kick_time < self.kick_cooldown:
                await asyncio.sleep(self.kick_cooldown)
                
            guild = member.guild
            bot_member = guild.get_member(self.client.user.id)
            
            # Hierarchy checks
            if member.id == guild.owner_id:
                return False, "Cannot kick server owner"
            if member.top_role.position >= bot_member.top_role.position:
                return False, f"Cannot kick {member.display_name} - role too high"
            if not bot_member.guild_permissions.kick_members:
                return False, "Bot lacks kick_members permission"
                
            await member.kick(reason=reason)
            self.last_kick_time = time.time()
            self.kick_circuit.record_success()
            return True, f"Successfully kicked {member.display_name}"
            
        except Exception as e:
            self.kick_circuit.record_failure()
            log_error("kick_member_safe", e)
            return False, f"Failed to kick: {str(e)[:100]}"
        finally:
            if operation_key in self.in_progress_operations:
                del self.in_progress_operations[operation_key]

    def is_admin(self, member):
        if not member: 
            return False
        member_role_ids = [r.id for r in member.roles]
        return any(role_id in ADMIN_ROLES for role_id in member_role_ids)

# -----------------------
# CLIENT + INTENTS
# -----------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)
safety_wrappers = SafetyWrappers(client)

# -----------------------
# MODULE INSTANCES
# -----------------------
cleanup_system = None
poll_voting = None

# -----------------------
# STATE & PERSISTENCE WITH STABILITY
# -----------------------
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}
recent_joins = {}
presence_cooldown = {}
member_join_tracking = {}

PRESENCE_COOLDOWN_TIME = 300

class AtomicJSONManager:
    @staticmethod
    def load_json(path, default):
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
            return default
        except Exception as e:
            log_error(f"LOAD_{path}", e)
            return default

    @staticmethod
    def atomic_save(path, data):
        for i in range(SAVE_RETRY_COUNT):
            try:
                temp_file = path + ".tmp"
                backup_file = path + f".backup.{int(time.time())}"
                
                # Create backup first
                if os.path.exists(path):
                    import shutil
                    shutil.copy2(path, backup_file)
                
                # Save to temp file
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Verify JSON is valid
                with open(temp_file, "r") as f:
                    json.load(f)
                
                # Atomic replace
                os.replace(temp_file, path)
                
                # Clean up old backups
                AtomicJSONManager._cleanup_old_backups(path)
                
                return True
            except Exception as e:
                log_error(f"SAVE_{path}_TRY_{i}", e)
                time.sleep(1)
        return False
    
    @staticmethod
    def _cleanup_old_backups(base_path):
        import glob
        backups = glob.glob(f"{base_path}.backup.*")
        backups.sort(key=os.path.getmtime)
        
        # Keep only last 5 backups
        for backup in backups[:-5]:
            try:
                os.remove(backup)
            except:
                pass

json_manager = AtomicJSONManager()

# -----------------------
# UTILS
# -----------------------
def load_data():
    global state, pending_recruits, member_join_tracking
    state = json_manager.load_json(STATE_FILE, {"message_counter": 0, "current_reminder": 0})
    pending_recruits = json_manager.load_json(PENDING_FILE, {})
    member_join_tracking = json_manager.load_json(JOIN_TRACKING_FILE, {})
    print(f"📂 Data loaded: {len(pending_recruits)} recruits, {len(member_join_tracking)} tracked members")

def save_data():
    success1 = json_manager.atomic_save(STATE_FILE, state)
    success2 = json_manager.atomic_save(PENDING_FILE, pending_recruits)
    success3 = json_manager.atomic_save(JOIN_TRACKING_FILE, member_join_tracking)
    return success1 and success2 and success3

def update_member_tracking(member, status):
    uid = str(member.id)
    now = datetime.now(timezone.utc).isoformat()
    
    if uid not in member_join_tracking:
        member_join_tracking[uid] = {
            "name": member.display_name,
            "join_date": member.joined_at.isoformat() if member.joined_at else now,
            "status": "active",
            "last_seen": now,
            "events": []
        }
    
    member_join_tracking[uid]["last_seen"] = now
    member_join_tracking[uid]["events"].append({"type": status, "time": now})
    
    # Limit events history
    if len(member_join_tracking[uid]["events"]) > 20:
        member_join_tracking[uid]["events"] = member_join_tracking[uid]["events"][-20:]

# -----------------------
# BACKGROUND TASKS WITH STABILITY
# -----------------------
async def cleanup_background_task():
    """Background task for cleanup system with stability"""
    await client.wait_until_ready()
    
    print("🔄 Starting cleanup background task...")
    
    # Initial delay
    await asyncio.sleep(10)
    
    while not client.is_closed() and not shutdown_flag:
        try:
            if cleanup_system and CLEANUP_ENABLED:
                # Run cleanup every 6 hours
                for guild in client.guilds:
                    await cleanup_system.run_cleanup_check(guild)
                
                # Clean old data once a day at 3 AM
                if datetime.now().hour == 3:
                    await cleanup_system.cleanup_old_data()
            
            # Check for expired polls if using poll system
            if poll_voting and hasattr(poll_voting, 'cleanup_expired_polls'):
                await poll_voting.cleanup_expired_polls()
            
            # Sleep for 6 hours
            for _ in range(6 * 60):  # Check every minute for shutdown
                if shutdown_flag:
                    break
                await asyncio.sleep(60)
            
        except Exception as e:
            log_error("cleanup_background_task", e)
            await asyncio.sleep(300)

async def resource_monitor():
    """Monitor resource usage"""
    await client.wait_until_ready()
    
    while not client.is_closed() and not shutdown_flag:
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > 400:  # Warning at 400MB
                print(f"⚠️ High memory usage: {memory_mb:.1f}MB")
                
                # Try to clear some caches
                if cleanup_system:
                    cleanup_system.cleanup_old_views()
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except ImportError:
            # psutil not available
            break
        except Exception as e:
            print(f"⚠️ Resource monitor error: {e}")
            await asyncio.sleep(300)

# -----------------------
# BOT EVENTS
# -----------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as: {client.user} (ID: {client.user.id})")
    print(f"👑 Bot is in {len(client.guilds)} guild(s)")
    
    for guild in client.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")
        print(f"    Members: {guild.member_count}")
    
    load_data()
    
    # Initialize modules
    global cleanup_system, poll_voting
    
    try:
        cleanup_system = CleanupSystem(client, CLEANUP_CONFIG)
        poll_voting = PollVoting(client)
        print("✅ Modules initialized successfully")
    except Exception as e:
        log_error("module_init", e)
        print("⚠️ Modules failed to initialize, but bot will continue")
    
    # Start background tasks
    asyncio.create_task(cleanup_background_task())
    asyncio.create_task(resource_monitor())
    
    print("--- Bot is ready with stability fixes ---")
    print("Commands available:")
    print("  !stats - Show bot statistics")
    print("  !cleanup - Run manual cleanup check")

@client.event
async def on_member_join(member):
    if shutdown_flag:
        return
    
    uid = str(member.id)
    current_time = time.time()
    
    # Anti-spam join protection
    if uid in recent_joins and current_time - recent_joins[uid] < 60:
        print(f"⚠️ Rapid rejoin detected for {member.display_name}")
        return
    
    recent_joins[uid] = current_time
    print(f"👤 Member joined: {member.display_name} (ID: {member.id})")
    
    update_member_tracking(member, "joined")
    
    # Track activity
    if cleanup_system:
        await cleanup_system.track_user_activity(member.id, "joined")
    
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])
    
    # Initialize recruit state
    pending_recruits[uid] = {
        "started": int(current_time),
        "answers": [],
        "under_review": False,
        "resolved": False,
        "name": member.display_name
    }
    save_data()

    try:
        dm = await member.create_dm()
        await dm.send("👋 Welcome to **Impèrius🔥**! To join our ranks, please answer these recruitment questions.")
        
        for i, question in enumerate(RECRUIT_QUESTIONS):
            await dm.send(f"**Question {i+1}/{len(RECRUIT_QUESTIONS)}**:\n{question}")
            
            def check(m):
                return m.author.id == member.id and isinstance(m.channel, discord.DMChannel)

            try:
                reply = await client.wait_for("message", timeout=600.0, check=check)
                pending_recruits[uid]["answers"].append(reply.content)
                save_data()
            except asyncio.TimeoutError:
                await dm.send("⏳ Recruitment timed out. Please rejoin and try again.")
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_data()
                return

        await dm.send("✅ Thank you! Your application has been sent to our Staff. Please wait for review.")
        
        if staff_ch:
            embed = discord.Embed(
                title="📋 New Recruit Application",
                description=f"**Applicant:** {member.mention}\n**ID:** `{member.id}`",
                color=discord.Color.blue()
            )
            for i, ans in enumerate(pending_recruits[uid]["answers"]):
                q_text = RECRUIT_QUESTIONS[i].split("?")[0] + "?"
                embed.add_field(name=f"Q{i+1}: {q_text}", value=ans[:1024] or "No answer", inline=False)
            
            embed.set_footer(text="React with 👍 to Accept, 👎 to Reject")
            
            msg = await staff_ch.send(embed=embed)
            await msg.add_reaction(UPVOTE_EMOJI)
            await msg.add_reaction(DOWNVOTE_EMOJI)
            
            pending_recruits[uid]["review_message_id"] = msg.id
            pending_recruits[uid]["under_review"] = True
            save_data()

    except discord.Forbidden:
        print(f"❌ Could not DM {member.display_name}")
        if recruit_ch:
            await recruit_ch.send(f"❌ {member.mention}, I couldn't DM you! Please open your DMs.")
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_data()
    except Exception as e:
        log_error("on_member_join", e)
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_data()

@client.event
async def on_raw_reaction_add(payload):
    if shutdown_flag or payload.user_id == client.user.id:
        return

    guild = client.get_guild(payload.guild_id)
    if not guild: 
        return
    
    reactor = guild.get_member(payload.user_id)
    if not reactor:
        return

    # Handle Recruitment Voting
    if safety_wrappers.is_admin(reactor):
        for uid, entry in list(pending_recruits.items()):
            if entry.get("review_message_id") == payload.message_id and not entry.get("resolved"):
                applicant = guild.get_member(int(uid))
                staff_ch = client.get_channel(CHANNELS["staff_review"])
                
                if str(payload.emoji) == UPVOTE_EMOJI:
                    success, msg = await safety_wrappers.assign_role_safe(
                        applicant, 
                        ROLES["imperius"], 
                        reason=f"Accepted by {reactor.display_name}"
                    )
                    if success:
                        entry["resolved"] = True
                        entry["status"] = "accepted"
                        if staff_ch: 
                            await staff_ch.send(
                                f"✅ {applicant.mention if applicant else entry.get('name')} "
                                f"has been **ACCEPTED** by {reactor.mention}."
                            )
                        try: 
                            await applicant.send("🎉 **Congratulations!** You have been accepted into **Impèrius🔥**!")
                        except: 
                            pass
                
                elif str(payload.emoji) == DOWNVOTE_EMOJI:
                    success, msg = await safety_wrappers.kick_member_safe(
                        applicant, 
                        reason=f"Rejected by {reactor.display_name}"
                    )
                    if success:
                        entry["resolved"] = True
                        entry["status"] = "rejected"
                        if staff_ch: 
                            await staff_ch.send(
                                f"❌ {applicant.mention if applicant else entry.get('name')} "
                                f"was **REJECTED** by {reactor.mention}."
                            )
                
                save_data()
                break

@client.event
async def on_presence_update(before, after):
    if shutdown_flag or after.bot: 
        return
    
    # Track activity
    if cleanup_system:
        await cleanup_system.track_user_activity(after.id, "presence_update")
    
    # Check if user returned from being offline
    if (before.status in [discord.Status.offline, discord.Status.invisible] and 
        after.status == discord.Status.online):
        
        # Check if user has demoted role
        demoted_role = after.guild.get_role(ROLES["demoted"])
        if demoted_role and demoted_role in after.roles:
            await cleanup_system.handle_user_return(after)
    
    # Track going offline
    if str(after.status) in ["offline", "invisible"]:
        presence_cooldown[str(after.id)] = time.time()

@client.event
async def on_message(message):
    if shutdown_flag or message.author.bot: 
        return
    
    # Track activity
    if cleanup_system:
        await cleanup_system.track_user_activity(message.author.id, "message")
    
    # Admin Commands
    if safety_wrappers.is_admin(message.author):
        if message.content.lower().startswith("!stats"):
            embed = discord.Embed(
                title="📊 Bot Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            active_recruits = len([r for r in pending_recruits.values() if not r.get('resolved')])
            
            embed.add_field(
                name="Recruitment",
                value=f"Active: {active_recruits}\nTotal: {len(pending_recruits)}",
                inline=True
            )
            
            embed.add_field(
                name="Member Tracking",
                value=f"Tracked: {len(member_join_tracking)}",
                inline=True
            )
            
            if cleanup_system:
                embed.add_field(
                    name="Cleanup System",
                    value=f"Users: {len(cleanup_system.user_activity)}\n"
                          f"Demoted: {len(cleanup_system.demoted_users)}",
                    inline=False
                )
            
            await message.channel.send(embed=embed)
            return
            
        if message.content.lower().startswith("!cleanup"):
            await message.channel.send("🧹 Starting manual cleanup check...")
            if cleanup_system:
                for guild in client.guilds:
                    await cleanup_system.run_cleanup_check(guild)
                await message.channel.send("✅ Cleanup check completed!")
            else:
                await message.channel.send("❌ Cleanup system not initialized")
            return

    # Counter-based Reminders
    if message.channel.id == CHANNELS["main"]:
        state["message_counter"] += 1
        
        if state["message_counter"] >= REMINDER_THRESHOLD:
            state["message_counter"] = 0
            
            reminder_ch = client.get_channel(CHANNELS["reminder"])
            if reminder_ch:
                rem = REMINDERS[state["current_reminder"]]
                embed = discord.Embed(
                    title=rem["title"], 
                    description=rem["description"], 
                    color=discord.Color.gold()
                )
                embed.set_footer(text="Impèrius Clan Management")
                await reminder_ch.send(embed=embed)
                
                state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
            
            save_data()

@client.event
async def on_interaction(interaction):
    """Handle button interactions"""
    if shutdown_flag:
        return
    
    if interaction.type == discord.InteractionType.component:
        if not interaction.response.is_done():
            await interaction.response.defer()

# -----------------------
# MAIN BOT LOOP WITH STABILITY
# -----------------------
async def main_bot_loop():
    restart_count = 0
    max_restarts = 5
    
    while not shutdown_flag and restart_count < max_restarts:
        try:
            token = os.environ.get("DISCORD_TOKEN")
            if not token:
                print("❌ ERROR: DISCORD_TOKEN not found!")
                break
            
            print("🚀 Starting Discord bot...")
            
            # Start with timeout
            try:
                async with asyncio.timeout(30):
                    await client.start(token)
            except asyncio.TimeoutError:
                print("⏱️ Connection timeout, restarting...")
                restart_count += 1
                continue
                
        except discord.LoginFailure:
            print("❌ Invalid token!")
            break
        except discord.PrivilegedIntentsRequired:
            print("❌ Privileged intents not enabled!")
            break
        except Exception as e:
            restart_count += 1
            log_error("BOT_STARTUP", e)
            
            if restart_count < max_restarts:
                wait_time = min(30 * (2 ** restart_count), 300)
                print(f"🔄 Restarting in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"💀 Too many restarts ({max_restarts})")
                break
    
    # Graceful shutdown
    print("💾 Saving data before exit...")
    if cleanup_system:
        cleanup_system.save_all_data()
    save_data()
    
    print("👋 Bot shutdown complete")

# -----------------------
# START
# -----------------------
# -----------------------
# START
# -----------------------
if __name__ == "__main__":
    print("🎯 Starting bot with stability fixes...")
    print(f"🔧 Python: {sys.version}")
    print(f"🔧 Discord.py: {discord.__version__}")
    
    # Create necessary directories
    os.makedirs("modules", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    # Emergency recovery for corrupted data
    def emergency_recovery():
        print("🔄 Checking for corrupted data...")
        critical_files = [
            "user_activity.json",
            "demoted_users.json", 
            "pending_recruits.json",
            "member_join_tracking.json",
            "reminder_state.json"
        ]
        
        for filename in critical_files:
            filepath = os.path.join("data", filename) if "data" in filename else filename
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        json.load(f)
                except:
                    print(f"⚠️ {filename} corrupted, resetting")
                    with open(filepath, 'w') as f:
                        json.dump({} if "json" in filename else [], f)
    
    emergency_recovery()
    
    # ✅ USE YOUR keep_alive.py FUNCTION INSTEAD
    from keep_alive import start_keep_alive
    
    # Start Flask with ping system (using your optimized function)
    flask_thread = threading.Thread(target=start_keep_alive, daemon=True)
    flask_thread.start()
    
    # Start Bot
    try:
        asyncio.run(main_bot_loop())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    except Exception as e:
        log_error("MAIN_BLOCK", e)
