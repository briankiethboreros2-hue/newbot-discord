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

# Import keep_alive FIRST
try:
    from keep_alive import app, start_keep_alive
    KEEP_ALIVE_AVAILABLE = True
except ImportError:
    print("⚠️ Keep alive module not found, will run without web server")
    KEEP_ALIVE_AVAILABLE = False

# -----------------------
# 🛡️ STABILITY CONFIGURATION
# -----------------------
CLEANUP_ENABLED = True
MAX_CLEANUP_RETRIES = 3
SAVE_RETRY_COUNT = 3

# Global shutdown flag
shutdown_flag = False
connection_attempts = 0
MAX_CONNECTION_ATTEMPTS = 3

def handle_shutdown(signum, frame):
    """Handle graceful shutdown"""
    global shutdown_flag
    print(f"\n🛑 Received shutdown signal ({signum}), saving data...")
    shutdown_flag = True
    # Don't exit immediately, let the bot clean up

# Register signal handlers
signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# -----------------------
# ENHANCED ERROR HANDLING
# -----------------------
def log_error(where, error, critical=False):
    """Enhanced error logging with backoff recommendations"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] ERROR in {where}: {str(error)[:200]}"
    print(error_msg)
    
    # Add recommendation for rate limits
    if "429" in str(error) or "rate limit" in str(error).lower():
        print("⚠️  RATE LIMIT DETECTED - Recommendations:")
        print("    1. Wait at least 5 minutes before restarting")
        print("    2. Check if multiple bot instances are running")
        print("    3. Reduce API call frequency")
    
    # Log to file with rotation
    try:
        log_file = "bot_errors.log"
        if os.path.exists(log_file) and os.path.getsize(log_file) > 5 * 1024 * 1024:  # 5MB
            rotate_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(log_file, f"bot_errors_{rotate_time}.log")
        
        with open(log_file, "a") as f:
            f.write(error_msg + "\n")
            if critical:
                traceback.print_exc(file=f)
            f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")
    
    if critical:
        traceback.print_exc()

def global_error_handler(exc_type, exc_value, exc_traceback):
    """Global exception handler"""
    if issubclass(exc_type, KeyboardInterrupt):
        return
    log_error("GLOBAL", f"{exc_type.__name__}: {exc_value}", critical=True)

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
    def __init__(self, failure_threshold=3, reset_timeout=300):  # Increased to 5 minutes
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
    
    def can_execute(self):
        if self.state == "OPEN":
            current_time = time.time()
            if current_time - self.last_failure_time > self.reset_timeout:
                print(f"🔁 Circuit breaker reset after {self.reset_timeout}s")
                self.state = "HALF_OPEN"
                self.failures = 0
                return True
            print(f"⏳ Circuit breaker OPEN - {int(self.reset_timeout - (current_time - self.last_failure_time))}s remaining")
            return False
        return True
    
    def record_success(self):
        if self.state == "HALF_OPEN":
            print("✅ Circuit breaker CLOSED - success after reset")
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
        self.kick_cooldown = 5.0  # Increased cooldown
        self.last_role_assignment = 0
        self.role_cooldown = 2.0  # Increased cooldown
        
        # Circuit breakers
        self.kick_circuit = CircuitBreaker(failure_threshold=2, reset_timeout=300)
        self.role_circuit = CircuitBreaker(failure_threshold=3, reset_timeout=300)
        self.api_circuit = CircuitBreaker(failure_threshold=5, reset_timeout=600)  # 10 minutes for API
        
        # API rate limiting
        self.api_calls = []
        self.max_api_calls = 40  # Reduced from 45 to stay safer
        self.api_window = 5
        
        # Operations tracking
        self.in_progress_operations = {}
        self.last_operation_time = 0
        self.operation_cooldown = 1.0  # Minimum time between any operations
    
    async def check_rate_limit(self):
        """Check and enforce Discord API rate limits with cooldown"""
        if not self.api_circuit.can_execute():
            raise Exception("API circuit breaker is open")
        
        current_time = time.time()
        
        # Cooldown between operations
        if current_time - self.last_operation_time < self.operation_cooldown:
            await asyncio.sleep(self.operation_cooldown - (current_time - self.last_operation_time))
        
        # Remove calls older than our window
        self.api_calls = [t for t in self.api_calls if current_time - t < self.api_window]
        
        # If we're approaching the limit, wait
        if len(self.api_calls) >= self.max_api_calls:
            oldest_call = self.api_calls[0]
            wait_time = self.api_window - (current_time - oldest_call) + 0.1  # Add buffer
            if wait_time > 0:
                print(f"⏱️ Rate limit approaching, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.api_calls = []  # Reset after waiting
        
        # Record this call
        self.api_calls.append(current_time)
        self.last_operation_time = current_time
        self.api_circuit.record_success()
    
    async def safe_operation(self, operation_key, timeout=30):
        """Ensure only one operation of each type runs at a time"""
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
        
        self.in_progress_operations[operation_key] = True
        start_time = time.time()
        
        try:
            # Check rate limits
            await self.check_rate_limit()
            return True, "Ready"
        except Exception as e:
            return False, str(e)
        finally:
            # Cleanup if operation takes too long
            if time.time() - start_time > timeout:
                print(f"⚠️ Operation {operation_key} took too long, cleaning up")
                if operation_key in self.in_progress_operations:
                    del self.in_progress_operations[operation_key]
    
    async def assign_role_safe(self, member, role_id, reason=""):
        """Safely assign role with enhanced error handling"""
        if not member or not role_id:
            return False, "Invalid parameters"
        
        operation_key = f"role_{member.id}_{role_id}"
        can_proceed, msg = await self.safe_operation(operation_key)
        if not can_proceed:
            return False, msg
        
        try:
            if not self.role_circuit.can_execute():
                return False, "Role circuit breaker open - too many failures"
            
            guild = member.guild
            role = guild.get_role(int(role_id))
            if not role:
                self.role_circuit.record_failure()
                return False, f"Role not found (ID: {role_id})"
            
            if role in member.roles:
                return True, "Already has role"
            
            # Permission checks
            bot_member = guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.manage_roles:
                return False, "Bot lacks manage_roles permission"
            
            if role.position >= bot_member.top_role.position:
                return False, f"Bot's role is not high enough to assign {role.name}"
            
            # Rate limiting between operations
            current_time = time.time()
            if current_time - self.last_role_assignment < self.role_cooldown:
                wait = self.role_cooldown - (current_time - self.last_role_assignment)
                await asyncio.sleep(wait)
            
            await member.add_roles(role, reason=reason)
            self.last_role_assignment = time.time()
            self.role_circuit.record_success()
            return True, f"Successfully assigned role {role.name}"
            
        except discord.Forbidden:
            self.role_circuit.record_failure()
            return False, "Bot lacks permissions"
        except discord.HTTPException as e:
            self.role_circuit.record_failure()
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 5)
                print(f"🛑 Discord Rate Limit hit! Waiting {retry_after}s...")
                await asyncio.sleep(retry_after)
                try:
                    await member.add_roles(role, reason=reason)
                    return True, "Assigned role after cooldown"
                except:
                    return False, "Rate limited again on retry"
            return False, f"HTTP error {e.status}"
        except Exception as e:
            self.role_circuit.record_failure()
            log_error("assign_role_safe", e)
            return False, f"Error: {str(e)[:100]}"
        finally:
            if operation_key in self.in_progress_operations:
                del self.in_progress_operations[operation_key]
    
    async def kick_member_safe(self, member, reason=""):
        """Safely kick member with enhanced error handling"""
        if not member:
            return False, "Invalid member"
        
        operation_key = f"kick_{member.id}"
        can_proceed, msg = await self.safe_operation(operation_key)
        if not can_proceed:
            return False, msg
        
        try:
            if not self.kick_circuit.can_execute():
                return False, "Kick circuit breaker open"
            
            guild = member.guild
            bot_member = guild.get_member(self.client.user.id)
            
            # Hierarchy checks
            if member.id == guild.owner_id:
                return False, "Cannot kick server owner"
            if member.top_role.position >= bot_member.top_role.position:
                return False, f"Cannot kick {member.display_name} - role too high"
            if not bot_member.guild_permissions.kick_members:
                return False, "Bot lacks kick_members permission"
            
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_kick_time < self.kick_cooldown:
                wait = self.kick_cooldown - (current_time - self.last_kick_time)
                await asyncio.sleep(wait)
            
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

# Configure client with rate limiting
class RateLimitedClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http.max_retries = 2  # Reduced retries
        self.connect_timeout = 30  # 30 second connection timeout
    
    async def setup_hook(self):
        # Reduce heartbeat interval to be less aggressive
        self._connection._keep_alive_timeout = 60.0

client = RateLimitedClient(intents=intents)
safety_wrappers = SafetyWrappers(client)

# -----------------------
# MODULE INSTANCES (Loaded dynamically)
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
        """Safe JSON loading with corruption recovery"""
        try:
            if os.path.exists(path):
                for attempt in range(2):
                    try:
                        with open(path, "r") as f:
                            return json.load(f)
                    except json.JSONDecodeError:
                        if attempt == 0:
                            # Try to fix common issues
                            with open(path, "r") as f:
                                content = f.read()
                                # Remove trailing commas
                                content = re.sub(r',\s*}', '}', content)
                                content = re.sub(r',\s*]', ']', content)
                            with open(path, "w") as f:
                                f.write(content)
                            continue
                        else:
                            print(f"⚠️ JSON corrupted: {path}, using default")
                            return default
            return default
        except Exception as e:
            log_error(f"LOAD_{path}", e)
            return default
    
    @staticmethod
    def atomic_save(path, data):
        """Atomic save with retries and verification"""
        for i in range(SAVE_RETRY_COUNT):
            try:
                temp_file = path + ".tmp"
                # Save to temp file
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Verify JSON is valid
                with open(temp_file, "r") as f:
                    json.load(f)
                
                # Atomic replace
                os.replace(temp_file, path)
                return True
            except Exception as e:
                log_error(f"SAVE_{path}_TRY_{i}", e)
                if i < SAVE_RETRY_COUNT - 1:
                    time.sleep(1)
                else:
                    # Last attempt failed, create emergency backup
                    emergency_file = path + ".emergency"
                    try:
                        with open(emergency_file, "w") as f:
                            json.dump(data, f)
                    except:
                        pass
        return False

json_manager = AtomicJSONManager()

# -----------------------
# UTILS
# -----------------------
def load_data():
    """Load all data files"""
    global state, pending_recruits, member_join_tracking
    try:
        state = json_manager.load_json(STATE_FILE, {"message_counter": 0, "current_reminder": 0})
        pending_recruits = json_manager.load_json(PENDING_FILE, {})
        member_join_tracking = json_manager.load_json(JOIN_TRACKING_FILE, {})
        
        # Validate loaded data
        if not isinstance(state, dict):
            state = {"message_counter": 0, "current_reminder": 0}
        if not isinstance(pending_recruits, dict):
            pending_recruits = {}
        if not isinstance(member_join_tracking, dict):
            member_join_tracking = {}
        
        print(f"📂 Data loaded: {len(pending_recruits)} recruits, {len(member_join_tracking)} tracked members")
    except Exception as e:
        log_error("load_data", e)
        # Reset to defaults on critical error
        state = {"message_counter": 0, "current_reminder": 0}
        pending_recruits = {}
        member_join_tracking = {}

def save_data():
    """Save all data with error handling"""
    try:
        success1 = json_manager.atomic_save(STATE_FILE, state)
        success2 = json_manager.atomic_save(PENDING_FILE, pending_recruits)
        success3 = json_manager.atomic_save(JOIN_TRACKING_FILE, member_join_tracking)
        
        if not (success1 and success2 and success3):
            print("⚠️ Some data failed to save")
        return success1 and success2 and success3
    except Exception as e:
        log_error("save_data", e)
        return False

def update_member_tracking(member, status):
    """Update member tracking with limits"""
    try:
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
        
        # Limit events history (keep only last 10 events)
        if len(member_join_tracking[uid]["events"]) > 10:
            member_join_tracking[uid]["events"] = member_join_tracking[uid]["events"][-10:]
    except Exception as e:
        log_error("update_member_tracking", e)

# -----------------------
# BACKGROUND TASKS WITH STABILITY
# -----------------------
async def cleanup_background_task():
    """Background task for cleanup system with stability"""
    await client.wait_until_ready()
    print("🔄 Starting cleanup background task...")
    
    # Initial delay to let bot stabilize
    await asyncio.sleep(30)
    
    while not client.is_closed() and not shutdown_flag:
        try:
            if cleanup_system and CLEANUP_ENABLED:
                # Run cleanup every 12 hours (reduced frequency)
                for guild in client.guilds:
                    await cleanup_system.run_cleanup_check(guild)
            
            # Sleep for 12 hours, checking for shutdown every minute
            for _ in range(12 * 60):
                if shutdown_flag or client.is_closed():
                    break
                await asyncio.sleep(60)
                
        except Exception as e:
            log_error("cleanup_background_task", e)
            await asyncio.sleep(600)  # Wait 10 minutes on error

async def auto_save_task():
    """Auto-save data periodically"""
    await client.wait_until_ready()
    print("💾 Starting auto-save task...")
    
    while not client.is_closed() and not shutdown_flag:
        try:
            await asyncio.sleep(300)  # Save every 5 minutes
            if save_data():
                print("💾 Auto-save completed")
        except Exception as e:
            log_error("auto_save_task", e)
        finally:
            # Always check for shutdown
            if shutdown_flag:
                break

# -----------------------
# BOT EVENTS
# -----------------------
@client.event
async def on_ready():
    """Bot is ready - initialize everything"""
    print(f"✅ Logged in as: {client.user} (ID: {client.user.id})")
    print(f"👑 Bot is in {len(client.guilds)} guild(s)")
    
    for guild in client.guilds:
        print(f" - {guild.name} (ID: {guild.id}) - Members: {guild.member_count}")
    
    # Load data
    load_data()
    
    # Initialize modules dynamically (to avoid startup failures)
    global cleanup_system, poll_voting
    try:
        # Try to import modules
        from modules.cleanup_system import CleanupSystem
        cleanup_system = CleanupSystem(client, CLEANUP_CONFIG)
        print("✅ Cleanup system initialized")
    except ImportError as e:
        print(f"⚠️ Could not load cleanup system: {e}")
        cleanup_system = None
    except Exception as e:
        log_error("cleanup_init", e)
        cleanup_system = None
    
    try:
        from modules.poll_voting import PollVoting
        poll_voting = PollVoting(client)
        print("✅ Poll voting system initialized")
    except ImportError as e:
        print(f"⚠️ Could not load poll voting: {e}")
        poll_voting = None
    except Exception as e:
        log_error("poll_init", e)
        poll_voting = None
    
    # Start background tasks
    asyncio.create_task(cleanup_background_task())
    asyncio.create_task(auto_save_task())
    
    print("--- Bot is ready with stability fixes ---")
    print("Commands available:")
    print(" !stats - Show bot statistics")
    print(" !cleanup - Run manual cleanup check")

@client.event
async def on_member_join(member):
    """Handle member join with timeout protection"""
    if shutdown_flag or member.bot:
        return
    
    uid = str(member.id)
    current_time = time.time()
    
    # Anti-spam join protection
    if uid in recent_joins and current_time - recent_joins[uid] < 120:  # 2 minutes
        print(f"⚠️ Rapid rejoin detected for {member.display_name}, ignoring")
        return
    
    recent_joins[uid] = current_time
    print(f"👤 Member joined: {member.display_name} (ID: {member.id})")
    
    # Clean old entries from recent_joins
    old_keys = [k for k, v in recent_joins.items() if current_time - v > 300]
    for k in old_keys:
        del recent_joins[k]
    
    update_member_tracking(member, "joined")
    
    # Initialize recruit state with timeout
    pending_recruits[uid] = {
        "started": int(current_time),
        "answers": [],
        "under_review": False,
        "resolved": False,
        "name": member.display_name,
        "timeout": int(current_time) + 600  # 10 minute timeout
    }
    
    # Clean expired pending recruits
    current_time_int = int(current_time)
    expired = [uid for uid, data in pending_recruits.items() 
               if data.get('timeout', 0) < current_time_int and not data.get('resolved', False)]
    for exp_uid in expired:
        del pending_recruits[exp_uid]
    
    save_data()
    
    # Try to DM with timeout
    try:
        dm_timeout = 30  # 30 second timeout for DM
        async def dm_task():
            dm = await member.create_dm()
            await dm.send("👋 Welcome to **Impèrius🔥**! To join our ranks, please answer these recruitment questions.")
            
            for i, question in enumerate(RECRUIT_QUESTIONS):
                if shutdown_flag:
                    return
                await dm.send(f"**Question {i+1}/{len(RECRUIT_QUESTIONS)}**:\n{question}")
                
                def check(m):
                    return m.author.id == member.id and isinstance(m.channel, discord.DMChannel)
                
                try:
                    reply = await client.wait_for("message", timeout=120.0, check=check)
                    pending_recruits[uid]["answers"].append(reply.content[:500])  # Limit length
                    save_data()
                except asyncio.TimeoutError:
                    await dm.send("⏳ Question timed out. Please rejoin and try again.")
                    if uid in pending_recruits:
                        del pending_recruits[uid]
                        save_data()
                    return
            
            await dm.send("✅ Thank you! Your application has been sent to our Staff. Please wait for review.")
            
            # Send to staff channel
            staff_ch = client.get_channel(CHANNELS["staff_review"])
            if staff_ch:
                embed = discord.Embed(
                    title="📋 New Recruit Application",
                    description=f"**Applicant:** {member.mention}\n**ID:** {member.id}",
                    color=discord.Color.blue()
                )
                
                for i, ans in enumerate(pending_recruits[uid]["answers"]):
                    q_text = RECRUIT_QUESTIONS[i].split("?")[0] + "?"
                    embed.add_field(
                        name=f"Q{i+1}: {q_text}",
                        value=ans[:1024] or "No answer",
                        inline=False
                    )
                
                embed.set_footer(text="React with 👍 to Accept, 👎 to Reject")
                msg = await staff_ch.send(embed=embed)
                await msg.add_reaction(UPVOTE_EMOJI)
                await msg.add_reaction(DOWNVOTE_EMOJI)
                
                pending_recruits[uid]["review_message_id"] = msg.id
                pending_recruits[uid]["under_review"] = True
                save_data()
        
        # Run DM task with timeout
        try:
            await asyncio.wait_for(dm_task(), timeout=dm_timeout)
        except asyncio.TimeoutError:
            print(f"⚠️ DM process timed out for {member.display_name}")
            recruit_ch = client.get_channel(CHANNELS["recruit"])
            if recruit_ch:
                await recruit_ch.send(f"{member.mention}, please check your DMs to complete recruitment!")
        
    except discord.Forbidden:
        print(f"❌ Could not DM {member.display_name}")
        recruit_ch = client.get_channel(CHANNELS["recruit"])
        if recruit_ch:
            await recruit_ch.send(f"{member.mention}, please enable DMs to complete recruitment!")
        
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
    """Handle reaction voting with safety"""
    if shutdown_flag or payload.user_id == client.user.id:
        return
    
    guild = client.get_guild(payload.guild_id)
    if not guild:
        return
    
    reactor = guild.get_member(payload.user_id)
    if not reactor or not safety_wrappers.is_admin(reactor):
        return
    
    # Handle Recruitment Voting
    emoji_str = str(payload.emoji)
    if emoji_str not in [UPVOTE_EMOJI, DOWNVOTE_EMOJI]:
        return
    
    for uid, entry in list(pending_recruits.items()):
        if (entry.get("review_message_id") == payload.message_id and 
            not entry.get("resolved", False) and
            entry.get("under_review", False)):
            
            applicant = guild.get_member(int(uid))
            staff_ch = client.get_channel(CHANNELS["staff_review"])
            
            if not applicant:
                print(f"⚠️ Applicant {uid} not found in guild")
                entry["resolved"] = True
                entry["status"] = "left_guild"
                save_data()
                continue
            
            if emoji_str == UPVOTE_EMOJI:
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
                            f"✅ {applicant.mention} has been **ACCEPTED** by {reactor.mention}."
                        )
                    try:
                        await applicant.send("🎉 **Congratulations!** You have been accepted into **Impèrius🔥**!")
                    except:
                        pass
                else:
                    if staff_ch:
                        await staff_ch.send(
                            f"❌ Failed to assign role to {applicant.mention}: {msg}"
                        )
            
            elif emoji_str == DOWNVOTE_EMOJI:
                success, msg = await safety_wrappers.kick_member_safe(
                    applicant,
                    reason=f"Rejected by {reactor.display_name}"
                )
                
                if success:
                    entry["resolved"] = True
                    entry["status"] = "rejected"
                    if staff_ch:
                        await staff_ch.send(
                            f"❌ {applicant.mention} was **REJECTED** by {reactor.mention}."
                        )
                else:
                    if staff_ch:
                        await staff_ch.send(
                            f"⚠️ Failed to kick {applicant.mention}: {msg}"
                        )
            
            save_data()
            break

@client.event
async def on_presence_update(before, after):
    """Handle presence updates with cooldown"""
    if shutdown_flag or after.bot:
        return
    
    # Track activity if cleanup system exists
    if cleanup_system:
        try:
            await cleanup_system.track_user_activity(after.id, "presence_update")
        except Exception as e:
            log_error("presence_tracking", e)
    
    # Check if user returned from being offline
    uid = str(after.id)
    if (before.status in [discord.Status.offline, discord.Status.invisible] and 
        after.status == discord.Status.online):
        
        # Check cooldown
        current_time = time.time()
        if uid in presence_cooldown and current_time - presence_cooldown[uid] < PRESENCE_COOLDOWN_TIME:
            return
        
        presence_cooldown[uid] = current_time
        
        # Clean old cooldown entries
        old_keys = [k for k, v in presence_cooldown.items() 
                   if current_time - v > PRESENCE_COOLDOWN_TIME * 2]
        for k in old_keys:
            del presence_cooldown[k]
        
        # Check if user has demoted role
        if cleanup_system:
            demoted_role = after.guild.get_role(ROLES["demoted"])
            if demoted_role and demoted_role in after.roles:
                await cleanup_system.handle_user_return(after)
    
    # Track going offline
    if str(after.status) in ["offline", "invisible"]:
        presence_cooldown[uid] = time.time()

@client.event
async def on_message(message):
    """Handle messages with rate limiting"""
    if shutdown_flag or message.author.bot:
        return
    
    # Track activity
    if cleanup_system:
        try:
            await cleanup_system.track_user_activity(message.author.id, "message")
        except Exception as e:
            log_error("message_tracking", e)
    
    # Admin Commands
    if safety_wrappers.is_admin(message.author):
        if message.content.lower().startswith("!stats"):
            try:
                embed = discord.Embed(
                    title="📊 Bot Statistics",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                active_recruits = len([r for r in pending_recruits.values() 
                                      if not r.get('resolved', False)])
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
                        value=f"Users: {len(getattr(cleanup_system, 'user_activity', {}))}\n"
                              f"Demoted: {len(getattr(cleanup_system, 'demoted_users', {}))}",
                        inline=False
                    )
                
                await message.channel.send(embed=embed)
                return
            except Exception as e:
                log_error("stats_command", e)
                await message.channel.send("❌ Error generating statistics")
        
        elif message.content.lower().startswith("!cleanup"):
            await message.channel.send("🧹 Starting manual cleanup check...")
            if cleanup_system:
                try:
                    for guild in client.guilds:
                        await cleanup_system.run_cleanup_check(guild)
                    await message.channel.send("✅ Cleanup check completed!")
                except Exception as e:
                    log_error("manual_cleanup", e)
                    await message.channel.send("❌ Error during cleanup")
            else:
                await message.channel.send("❌ Cleanup system not available")
            return
    
    # Counter-based Reminders
    if message.channel.id == CHANNELS["main"]:
        state["message_counter"] += 1
        
        if state["message_counter"] >= REMINDER_THRESHOLD:
            state["message_counter"] = 0
            reminder_ch = client.get_channel(CHANNELS["reminder"])
            
            if reminder_ch:
                try:
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
                except Exception as e:
                    log_error("reminder_send", e)

@client.event
async def on_interaction(interaction):
    """Handle interactions with error handling"""
    if shutdown_flag:
        return
    
    try:
        if interaction.type == discord.InteractionType.component:
            if not interaction.response.is_done():
                await interaction.response.defer()
    except Exception as e:
        log_error("on_interaction", e)

@client.event
async def on_error(event, *args, **kwargs):
    """Global error handler for discord events"""
    error_msg = f"Discord event error in {event}: {args[0] if args else 'Unknown'}"
    log_error("DISCORD_EVENT", error_msg)

# -----------------------
# MAIN BOT LOOP WITH STABILITY
# -----------------------
async def main_bot_loop():
    """Main bot loop with enhanced stability"""
    global connection_attempts
    
    while not shutdown_flag and connection_attempts < MAX_CONNECTION_ATTEMPTS:
        connection_attempts += 1
        print(f"\n🚀 Connection attempt {connection_attempts}/{MAX_CONNECTION_ATTEMPTS}")
        
        token = os.environ.get("DISCORD_TOKEN")
        if not token or token == "YOUR_BOT_TOKEN_HERE":
            print("❌ ERROR: DISCORD_TOKEN not set or invalid!")
            print("Please set your bot token as an environment variable")
            break
        
        try:
            print("⏳ Connecting to Discord...")
            
            # Connect with timeout
            connect_task = asyncio.create_task(client.start(token))
            
            try:
                # Wait for connection or timeout
                await asyncio.wait_for(connect_task, timeout=45)
                print("✅ Connected successfully!")
                
                # Run until shutdown
                while not shutdown_flag:
                    await asyncio.sleep(1)
                
                print("🛑 Shutdown requested, disconnecting...")
                break
                
            except asyncio.TimeoutError:
                print("⏱️ Connection timeout")
                connect_task.cancel()
                await asyncio.sleep(5)
                continue
                
        except discord.LoginFailure:
            print("❌ Invalid Discord token!")
            print("Please check your DISCORD_TOKEN environment variable")
            break
            
        except discord.HTTPException as e:
            if e.status == 429:
                wait_time = getattr(e, 'retry_after', 30)
                print(f"🛑 Rate limited! Waiting {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                continue
            else:
                log_error("CONNECTION_HTTP", e)
                await asyncio.sleep(10)
                continue
                
        except Exception as e:
            log_error("MAIN_LOOP", e)
            
            # Calculate backoff time
            backoff_time = min(60 * (2 ** (connection_attempts - 1)), 300)
            print(f"💤 Backing off for {backoff_time} seconds...")
            await asyncio.sleep(backoff_time)
            
            if connection_attempts >= MAX_CONNECTION_ATTEMPTS:
                print(f"💀 Too many connection attempts ({MAX_CONNECTION_ATTEMPTS})")
                print("Please check your internet connection and Discord token")
                break
    
    # Graceful shutdown
    print("\n💾 Performing graceful shutdown...")
    
    # Save all data
    try:
        if cleanup_system and hasattr(cleanup_system, 'save_all_data'):
            cleanup_system.save_all_data()
        save_data()
        print("✅ Data saved")
    except Exception as e:
        log_error("SHUTDOWN_SAVE", e)
    
    # Close client if still connected
    if not client.is_closed():
        try:
            await client.close()
            print("✅ Discord connection closed")
        except Exception as e:
            log_error("SHUTDOWN_CLOSE", e)
    
    print("👋 Bot shutdown complete")

# -----------------------
# STARTUP
# -----------------------
if __name__ == "__main__":
    print("🎯 Starting bot with enhanced stability fixes...")
    print(f"🔧 Python: {sys.version}")
    print(f"🔧 Discord.py: {discord.__version__}")
    print(f"🔧 Running on: {os.name}")
    
    # Create necessary directories
    os.makedirs("modules", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    # Emergency recovery for corrupted data
    def emergency_recovery():
        """Recover from corrupted data files"""
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
                        content = f.read()
                        if not content.strip():
                            print(f"⚠️ {filename} empty, resetting")
                            raise ValueError("Empty file")
                        json.loads(content)
                except:
                    print(f"⚠️ {filename} corrupted, resetting")
                    with open(filepath, 'w') as f:
                        json.dump({} if "json" in filename else [], f, indent=2)
    
    emergency_recovery()
    
    # Start Flask keep-alive if available
    if KEEP_ALIVE_AVAILABLE:
        print("🌐 Starting keep-alive server...")
        flask_thread = threading.Thread(target=start_keep_alive, daemon=True)
        flask_thread.start()
        print("✅ Keep-alive server started")
    else:
        print("⚠️ Running without keep-alive server")
    
    # Start Bot
    try:
        asyncio.run(main_bot_loop())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
        shutdown_flag = True
    except Exception as e:
        log_error("MAIN_STARTUP", e, critical=True)
    finally:
        print("\n💫 Bot process ending...")
        if shutdown_flag:
            print("🛑 Shutdown flag was set")
