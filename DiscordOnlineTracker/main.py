# STABLE VERSION - BOT IN MAIN THREAD WITH MODULAR SYSTEM
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

from keep_alive import app, ping_self

# Import modules
try:
    from modules.cleanup_system import CleanupSystem
    from modules.poll_voting import PollVoting
    print("✅ Successfully loaded modules")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("📁 Make sure you have the modules folder with:")
    print("   - cleanup_system.py")
    print("   - poll_voting.py")
    print("   - button_views.py")
    sys.exit(1)

# -----------------------
# 🛡️ SAFETY CONFIGURATION
# -----------------------
CLEANUP_ENABLED = True
CLEANUP_RATE_LIMIT = 1.0
MAX_CLEANUP_RETRIES = 3
SAVE_RETRY_COUNT = 3

# Retention policies
TRACKING_RETENTION_DAYS = 30
JOIN_COOLDOWN_CLEANUP_HOURS = 24
ERROR_LOG_RETENTION_DAYS = 7

# -----------------------
# ENHANCED ERROR HANDLING
# -----------------------
def log_error(where, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] CRASH in {where}: {str(error)}"
    print(error_msg)
    
    # Rotate error log if too large
    try:
        if os.path.exists("bot_errors.log"):
            file_size = os.path.getsize("bot_errors.log")
            if file_size > 10 * 1024 * 1024:
                rotate_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.rename("bot_errors.log", f"bot_errors_{rotate_time}.log")
    except:
        pass
    
    try:
        with open("bot_errors.log", "a") as f:
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
# CONFIG - UPDATED WITH NEW CHANNELS/ROLES
# -----------------------
CHANNELS = {
    "main": 1437768842871832597,
    "recruit": 1437568595977834590,
    "reminder": 1369091668724154419,
    "staff_review": 1437586858417852438,
    "cleanup": 1454802873300025396,      # NEW: Cleanup channel
    "admin": 1437586858417852438,        # Admin channel
    "welcome": 1369091668724154419,      # Welcome channel (same as reminder)
    "call": 1437575744824934531          # Call channel
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "og_imperius": 1437572916005834793,
    "imperius": 1437570031822176408,     # Impèrius🔥 role ID
    "demoted": 1454803208995340328       # NEW: Demoted role ID
}

ADMIN_ROLES = [
    1389835747040694332,  # clan_master
    1437578521374363769,  # queen
    1437572916005834793,  # og_imperius (FIXED: was missing the last digit)
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

# UPDATED RECRUITMENT QUESTIONS
RECRUIT_QUESTIONS = [
    "1️⃣ Since you agreed to our terms and have read the rules, that also states we conduct clan tryouts. Do you agree to participate? (yes or no)",
    "2️⃣ We require CCN 1 week after the day you joined or got accepted, failed to comply with the requirements might face with penalty, What will be your future in-game name? (e.g., IM-Ryze)",
    "3️⃣ Our clan encourage members to improve, our members, OGs and Admins are always vocal when it comes to play making and correction of members. We are open so you can express yourself and also suggest, Are you open to communication about your personal gameplay and others suggestions? (yes or no)",
    "4️⃣ We value team chemistry, communication and overall team improvements so we prioritize playing with clan members than playing with others. so are you? (yes or no)",
    "5️⃣ We understand that sometimes there will be busy days and other priorities, we do have members who are working and also studying, are you working or a student?"
]

# Voting emojis
UPVOTE_EMOJI = "👍🏻"
DOWNVOTE_EMOJI = "👎🏻"
CLOCK_EMOJI = "⏰"

# 🆕 WEEKLY CLEANUP EMOJIS
KICK_EMOJI = "🦶"
GRANT_ROLE_EMOJI = "👑"
REVIEW_EMOJI = "🔍"

REMINDERS = [
    {"title": "🟢 Activity Reminder", "description": "Members must keep their status set only to \"Online\" while active."},
    {"title": "🧩 IGN Format", "description": "All members must use the official clan format: IM-(Your IGN)."},
    {"title": "🔊 Voice Channel Reminder", "description": "Members online must join the Public Call channel."}
]

# -----------------------
# 🛡️ ADVANCED SAFETY WRAPPERS
# -----------------------
class CircuitBreaker:
    """Circuit breaker pattern for rate-limited operations"""
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED" # CLOSED, OPEN, HALF_OPEN
    
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
        self.kick_cooldown = 2.0 # Seconds between kicks
        self.last_role_assignment = 0
        self.role_cooldown = 1.0 # Seconds between role assignments
        
        self.kick_circuit = CircuitBreaker(failure_threshold=3, reset_timeout=30)
        self.role_circuit = CircuitBreaker(failure_threshold=5, reset_timeout=30)
        
        # Track operations in progress to avoid double-processing
        self.in_progress_operations = {}
        
    async def assign_role_safe(self, member, role_id, reason=""):
        operation_key = f"role_{member.id}_{role_id}"
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
            
        self.in_progress_operations[operation_key] = True
        
        try:
            if not self.role_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
                
            if not member or not role_id:
                return False, "Invalid parameters"
            
            # Check rate limiting
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
                
            # Permission check
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
            if e.status == 429: # Rate limit
                print(f"🛑 Discord Rate Limit hit on role assignment! Waiting...")
                wait_time = random.uniform(5, 10)
                await asyncio.sleep(wait_time)
                # One retry
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
            if not self.kick_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
                
            # Check rate limiting
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
        if not member: return False
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
# STATE & PERSISTENCE
# -----------------------
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}
recent_joins = {}
presence_cooldown = {}
member_join_tracking = {}

PRESENCE_COOLDOWN_TIME = 300 # 5 minutes

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
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)
                # Atomic replace
                os.replace(temp_file, path)
                return True
            except Exception as e:
                log_error(f"SAVE_{path}_TRY_{i}", e)
                time.sleep(1)
        return False

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
    json_manager.atomic_save(STATE_FILE, state)
    json_manager.atomic_save(PENDING_FILE, pending_recruits)
    json_manager.atomic_save(JOIN_TRACKING_FILE, member_join_tracking)

# -----------------------
# TRACKING HELPERS
# -----------------------
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
    
    save_data()

# -----------------------
# BACKGROUND TASKS
# -----------------------
async def cleanup_background_task():
    """Background task for cleanup system"""
    await client.wait_until_ready()
    
    print("🔄 Starting cleanup background task...")
    
    # Initial delay to let everything load
    await asyncio.sleep(10)
    
    while not client.is_closed():
        try:
            if cleanup_system and CLEANUP_ENABLED:
                # Run cleanup every 6 hours
                for guild in client.guilds:
                    await cleanup_system.run_cleanup_check(guild)
                
                # Clean old data once a day at 3 AM
                if datetime.now().hour == 3:
                    await cleanup_system.cleanup_old_data()
            
            # Check for expired polls
            if poll_voting:
                await poll_voting.cleanup_expired_polls()
            
            # Sleep for 6 hours
            await asyncio.sleep(6 * 3600)
            
        except Exception as e:
            log_error("cleanup_background_task", e)
            await asyncio.sleep(300)  # Wait 5 minutes on error

# -----------------------
# BOT EVENTS - UPDATED WITH MODULES
# -----------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as: {client.user} (ID: {client.user.id})")
    print(f"👑 Bot is in {len(client.guilds)} guild(s)")
    
    for guild in client.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")
    
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
    
    print("--- Bot is ready with modular system ---")
    print("Commands available:")
    print("  !stats - Show bot statistics")
    print("  !cleanup - Run manual cleanup check")
    print("  !poll \"Question?\" \"Option 1\" \"Option 2\" - Create a poll")

@client.event
async def on_member_join(member):
    uid = str(member.id)
    current_time = time.time()
    
    # Anti-spam join protection
    if uid in recent_joins:
        if current_time - recent_joins[uid] < 60:
            print(f"⚠️ Rapid rejoin detected for {member.display_name}")
            return
    recent_joins[uid] = current_time
    
    print(f"👤 Member joined: {member.display_name} (ID: {member.id})")
    update_member_tracking(member, "joined")
    
    # Track activity in cleanup system
    if cleanup_system:
        await cleanup_system.track_user_activity(member.id, "joined")
    
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])
    
    # Reset/Init recruit state
    pending_recruits[uid] = {
        "started": int(current_time),
        "answers": [],
        "under_review": False,
        "resolved": False,
        "name": member.display_name
    }
    save_data()

    # Step 1: Send DM flow
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
                # Clean up pending recruit
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_data()
                return

        await dm.send("✅ Thank you! Your application has been sent to our Staff. Please wait for review.")
        
        # Step 2: Post to Staff Review
        if staff_ch:
            embed = discord.Embed(
                title="📋 New Recruit Application",
                description=f"**Applicant:** {member.mention}\n**ID:** `{member.id}`\n**Joined:** <t:{int(member.joined_at.timestamp())}:R>",
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
        print(f"❌ Could not DM {member.display_name} (DMs closed)")
        if recruit_ch:
            await recruit_ch.send(f"❌ {member.mention}, I couldn't DM you! Please open your DMs and rejoin to apply.")
        # Clean up pending recruit
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_data()
    except Exception as e:
        log_error("on_member_join", e)
        # Clean up on error
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_data()

@client.event
async def on_raw_reaction_add(payload):
    if payload.user_id == client.user.id:
        return

    guild = client.get_guild(payload.guild_id)
    if not guild: 
        return
    
    reactor = guild.get_member(payload.user_id)
    if not reactor:
        return

    # 1. Handle Recruitment Voting (admin only)
    if safety_wrappers.is_admin(reactor):
        for uid, entry in list(pending_recruits.items()):
            if entry.get("review_message_id") == payload.message_id and not entry.get("resolved"):
                applicant = guild.get_member(int(uid))
                staff_ch = client.get_channel(CHANNELS["staff_review"])
                
                if str(payload.emoji) == UPVOTE_EMOJI:
                    # Accept
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
                    # Reject
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
    
    # 2. Handle poll reactions if using poll system
    if poll_voting:
        await poll_voting.handle_reaction(payload)

@client.event
async def on_presence_update(before, after):
    if after.bot: 
        return
    
    # Track activity in cleanup system
    if cleanup_system:
        await cleanup_system.track_user_activity(after.id, "presence_update")
    
    # Check if user returned from being offline (for demoted users)
    if before.status in [discord.Status.offline, discord.Status.invisible] and after.status == discord.Status.online:
        if cleanup_system:
            await cleanup_system.handle_user_return(after)
    
    # Check for non-Online status while active
    if str(after.status) in ["offline", "invisible"]:
        # Track going offline
        presence_cooldown[str(after.id)] = time.time()

@client.event
async def on_message(message):
    if message.author.bot: 
        return
    
    # Track activity in cleanup system
    if cleanup_system:
        await cleanup_system.track_user_activity(message.author.id, "message")
    
    # Global Admin Commands
    if safety_wrappers.is_admin(message.author):
        if message.content.lower().startswith("!stats"):
            embed = discord.Embed(
                title="📊 Bot Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Active recruits
            active_recruits = len([r for r in pending_recruits.values() if not r.get('resolved')])
            total_recruits = len(pending_recruits)
            
            embed.add_field(
                name="Recruitment",
                value=f"Active: {active_recruits}\nTotal: {total_recruits}",
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
                          f"Demoted: {len(cleanup_system.demoted_users)}\n"
                          f"Under Review: {len(cleanup_system.users_under_review)}",
                    inline=False
                )
            
            embed.set_footer(text=f"Server: {message.guild.name}")
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
            
        if message.content.lower().startswith("!poll"):
            # Example: !poll "Question?" "Option 1" "Option 2" "Option 3"
            if poll_voting:
                try:
                    # Parse command: !poll "Question?" "Option 1" "Option 2"
                    content = message.content[len("!poll"):].strip()
                    
                    # Find quoted parts
                    import shlex
                    try:
                        parts = shlex.split(content)
                    except:
                        # Fallback if shlex fails
                        parts = []
                        in_quote = False
                        current = ""
                        for char in content:
                            if char == '"':
                                if in_quote and current:
                                    parts.append(current)
                                    current = ""
                                in_quote = not in_quote
                            elif in_quote:
                                current += char
                    
                    if len(parts) >= 3:
                        question = parts[0]
                        options = parts[1:]
                        
                        if len(options) >= 2 and len(options) <= 10:
                            poll_msg = await poll_voting.create_poll(
                                message.channel,
                                question,
                                options,
                                duration_minutes=60,
                                allowed_voters=ADMIN_ROLES
                            )
                            if poll_msg:
                                await message.channel.send(f"✅ Poll created! {poll_msg.jump_url}")
                            else:
                                await message.channel.send("❌ Failed to create poll")
                        else:
                            await message.channel.send("❌ Poll needs 2-10 options!")
                    else:
                        await message.channel.send(
                            "❌ Usage: `!poll \"Question?\" \"Option 1\" \"Option 2\"`\n"
                            "Example: `!poll \"Best game?\" \"Valorant\" \"MLBB\" \"COD\"`"
                        )
                except Exception as e:
                    await message.channel.send(f"❌ Error creating poll: {str(e)[:100]}")
            else:
                await message.channel.send("❌ Poll system not initialized")
            return

    # Counter-based Reminders (only in main channel)
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
    if interaction.type == discord.InteractionType.component:
        # The button views handle their own interactions
        # This is just a fallback to ensure we acknowledge all interactions
        if not interaction.response.is_done():
            await interaction.response.defer()

# -----------------------
# STABILITY WRAPPER
# -----------------------
async def main_bot_loop():
    restart_count = 0
    max_restarts = 5
    
    while True:
        try:
            token = os.environ.get("DISCORD_TOKEN")
            if not token:
                print("❌ ERROR: DISCORD_TOKEN not found in environment!")
                return
            
            print("🚀 Starting Discord bot...")
            await client.start(token)
            
        except discord.LoginFailure:
            print("❌ Invalid token! Check your DISCORD_TOKEN environment variable.")
            break
        except discord.PrivilegedIntentsRequired:
            print("❌ Privileged intents not enabled! Enable them in Discord Developer Portal.")
            break
        except Exception as e:
            restart_count += 1
            log_error("BOT_STARTUP", e)
            
            if restart_count < max_restarts:
                wait_time = min(30 * (2 ** restart_count), 300)
                print(f"🔄 Restarting in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"💀 Too many restarts ({max_restarts}). Giving up.")
                break
    
    print("💀 Bot has stopped.")

# -----------------------
# START
# -----------------------
if __name__ == "__main__":
    print("🎯 Starting bot with modular system...")
    print(f"🔧 Python: {sys.version}")
    print(f"🔧 Discord.py: {discord.__version__}")
    
    # Create modules directory if it doesn't exist
    os.makedirs("modules", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    # Start Flask
    def start_flask():
        port = int(os.environ.get("PORT", 8080))
        print(f"🌐 Flask on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    # Start pinger
    threading.Thread(target=ping_self, daemon=True).start()
    
    # Start Bot
    try:
        asyncio.run(main_bot_loop())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
        # Save data on shutdown
        if cleanup_system:
            cleanup_system.save_all_data()
        save_data()
        print("💾 Data saved successfully")
    except Exception as e:
        log_error("MAIN_BLOCK", e)
