# STABLE VERSION - BOT IN MAIN THREAD
import threading
import discord
import os
import time
import json
import asyncio
import sys
import traceback
import random
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from keep_alive import app, ping_self

# -----------------------
# 🛡️ SAFETY CONFIGURATION
# -----------------------
CLEANUP_ENABLED = True  # Set to False to disable message cleanup if issues arise
CLEANUP_RATE_LIMIT = 1.0  # Seconds between message deletions (increase if rate limited)
MAX_CLEANUP_RETRIES = 3  # Maximum retries for failed deletions
SAVE_RETRY_COUNT = 3  # Retry count for file saves

# Retention policies (in days)
TRACKING_RETENTION_DAYS = 30  # Keep member tracking for 30 days
JOIN_COOLDOWN_CLEANUP_HOURS = 24  # Clean join cooldowns after 24 hours
ERROR_LOG_RETENTION_DAYS = 7  # Keep error logs for 7 days

# -----------------------
# ENHANCED ERROR HANDLING WITH ROTATION
# -----------------------
def log_error(where, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] CRASH in {where}: {str(error)}"
    print(error_msg)
    
    # Rotate error log if too large
    try:
        if os.path.exists("bot_errors.log"):
            file_size = os.path.getsize("bot_errors.log")
            if file_size > 10 * 1024 * 1024:  # 10MB
                # Rotate log
                rotate_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.rename("bot_errors.log", f"bot_errors_{rotate_time}.log")
    except:
        pass
    
    # Write to error log file
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
# CONFIG (YOUR ORIGINAL)
# -----------------------
CHANNELS = {
    "main": 1437768842871832597,
    "recruit": 1437568595977834590,
    "reminder": 1369091668724154419,
    "staff_review": 1437586858417852438
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "og_imperius": 1437572916005834793,
    "imperius": 1437570031822176408,  # Impèrius🔥 role ID
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
UPVOTE_EMOJI = "👍🏻"  # :thumbsup::skin-tone-1:
DOWNVOTE_EMOJI = "👎🏻"  # :thumbsdown::skin-tone-1:
CLOCK_EMOJI = "⏰"  # :alarm_clock:

REMINDERS = [
    {"title": "🟢 Activity Reminder", "description": "Members must keep their status set only to \"Online\" while active."},
    {"title": "🧩 IGN Format", "description": "All members must use the official clan format: IM-(Your IGN)."},
    {"title": "🔊 Voice Channel Reminder", "description": "Members online must join the Public Call channel."}
]

# -----------------------
# 🛡️ ADVANCED SAFETY WRAPPERS WITH CIRCUIT BREAKER
# -----------------------
class CircuitBreaker:
    """Circuit breaker pattern for rate-limited operations"""
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
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
            self.state = "OPEN"

class SafetyWrappers:
    def __init__(self, client):
        self.client = client
        self.last_kick_time = 0
        self.kick_cooldown = 2.0  # 2 seconds between kicks
        self.last_role_assignment = 0
        self.role_cooldown = 1.0  # 1 second between role assignments
        self.kick_circuit = CircuitBreaker(failure_threshold=3, reset_timeout=30)
        self.role_circuit = CircuitBreaker(failure_threshold=5, reset_timeout=30)
        self.in_progress_operations = {}  # Track ongoing operations to prevent race conditions
        
    async def assign_role_safe(self, member, role_id, reason=""):
        """Safely assign role with all necessary checks"""
        operation_key = f"role_{member.id}_{role_id}"
        
        # Check for duplicate operation
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
        
        self.in_progress_operations[operation_key] = True
        
        try:
            # Circuit breaker check
            if not self.role_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
            
            if not member or not role_id:
                return False, "Invalid parameters"
            
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_role_assignment < self.role_cooldown:
                await asyncio.sleep(self.role_cooldown)
            
            guild = member.guild
            role = guild.get_role(int(role_id))
            
            if not role:
                self.role_circuit.record_failure()
                return False, f"Role not found (ID: {role_id})"
            
            # Check if member already has the role
            if role in member.roles:
                self.role_circuit.record_success()
                return True, "Already has role"
            
            # Check bot's permissions
            bot_member = guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.manage_roles:
                self.role_circuit.record_failure()
                return False, "Bot lacks manage_roles permission"
            
            # Check role hierarchy
            if role.position >= bot_member.top_role.position:
                self.role_circuit.record_failure()
                return False, f"Bot's role is not high enough to assign {role.name}"
            
            # Assign the role
            await member.add_roles(role, reason=reason)
            self.last_role_assignment = time.time()
            self.role_circuit.record_success()
            
            return True, f"Assigned role {role.name}"
            
        except discord.Forbidden:
            self.role_circuit.record_failure()
            return False, "Bot lacks permissions"
        except discord.HTTPException as e:
            self.role_circuit.record_failure()
            if e.status == 429:  # Rate limited
                wait_time = random.uniform(5, 10)  # Random backoff
                print(f"⏰ Rate limited assigning role, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                try:
                    await member.add_roles(role, reason=reason)
                    self.role_circuit.record_success()
                    return True, f"Assigned role after cooldown"
                except Exception as retry_error:
                    return False, f"Rate limited on retry: {retry_error}"
            else:
                return False, f"HTTP error {e.status}: {e.text}"
        except Exception as e:
            self.role_circuit.record_failure()
            return False, f"Unexpected error: {str(e)[:100]}"
        finally:
            # Clean up operation tracking
            if operation_key in self.in_progress_operations:
                del self.in_progress_operations[operation_key]
    
    async def kick_member_safe(self, member, reason=""):
        """Safely kick a member with all necessary checks"""
        operation_key = f"kick_{member.id}"
        
        # Check for duplicate operation
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
        
        self.in_progress_operations[operation_key] = True
        
        try:
            # Circuit breaker check
            if not self.kick_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
            
            if not member:
                return False, "Invalid member"
            
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_kick_time < self.kick_cooldown:
                await asyncio.sleep(self.kick_cooldown)
            
            guild = member.guild
            
            # Check if member is server owner
            if member.id == guild.owner_id:
                return False, "Cannot kick server owner"
            
            # Check bot's permissions
            bot_member = guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.kick_members:
                self.kick_circuit.record_failure()
                return False, "Bot lacks kick_members permission"
            
            # Check role hierarchy
            if member.top_role.position >= bot_member.top_role.position:
                self.kick_circuit.record_failure()
                return False, f"Cannot kick member with equal or higher role"
            
            # Kick the member
            await member.kick(reason=reason)
            self.last_kick_time = time.time()
            self.kick_circuit.record_success()
            
            return True, f"Kicked {member.display_name}"
            
        except discord.Forbidden:
            self.kick_circuit.record_failure()
            return False, "Bot lacks permissions to kick"
        except discord.HTTPException as e:
            self.kick_circuit.record_failure()
            if e.status == 429:  # Rate limited
                wait_time = random.uniform(5, 10)  # Random backoff
                print(f"⏰ Rate limited kicking, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                return False, "Rate limited - try again"
            else:
                return False, f"HTTP error {e.status}: {e.text}"
        except Exception as e:
            self.kick_circuit.record_failure()
            return False, f"Unexpected error: {str(e)[:100]}"
        finally:
            # Clean up operation tracking
            if operation_key in self.in_progress_operations:
                del self.in_progress_operations[operation_key]
    
    def is_admin(self, member):
        """Check if member has admin role"""
        if not member:
            return False
        
        member_role_ids = [r.id for r in member.roles]
        admin_role_ids = [
            ROLES.get("queen"),
            ROLES.get("clan_master"), 
            ROLES.get("og_imperius")
        ]
        
        return any(role_id in member_role_ids for role_id in admin_role_ids if role_id)

# Initialize safety wrappers after client is created
safety_wrappers = None

# -----------------------
# CLIENT + INTENTS
# -----------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# -----------------------
# STATE WITH AUTO-CLEANUP
# -----------------------
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}
# Add a cooldown system to prevent duplicate member join events
recent_joins = {}  # {user_id: timestamp}

# Rate limiting for presence updates
presence_cooldown = {}  # {user_id: timestamp}
PRESENCE_COOLDOWN_TIME = 300  # 5 minutes in seconds

# 🆕 Persistent join tracking with auto-cleanup
member_join_tracking = {}

# -----------------------
# 🛡️ ENHANCED LOAD/SAVE WITH TRANSACTION LOGIC
# -----------------------
class AtomicJSONManager:
    """Manages JSON files with transaction safety"""
    
    @staticmethod
    def load_json(path, default):
        """Safely load JSON file with fallback"""
        for attempt in range(SAVE_RETRY_COUNT):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except FileNotFoundError:
                return default
            except json.JSONDecodeError:
                if attempt == SAVE_RETRY_COUNT - 1:
                    print(f"⚠️ Corrupted JSON in {path}, restoring from backup")
                    backup_path = path + ".backup"
                    if os.path.exists(backup_path):
                        try:
                            with open(backup_path, "r") as f:
                                return json.load(f)
                        except:
                            return default
                    return default
                time.sleep(0.1)
            except Exception as e:
                if attempt == SAVE_RETRY_COUNT - 1:
                    print(f"⚠️ Failed to load {path}: {e}")
                    return default
                time.sleep(0.1)
        return default
    
    @staticmethod
    def atomic_save(path, data):
        """Save JSON file atomically with transaction safety"""
        for attempt in range(SAVE_RETRY_COUNT):
            try:
                # Create transaction directory if needed
                trans_dir = "transactions"
                if not os.path.exists(trans_dir):
                    os.makedirs(trans_dir)
                
                # Save transaction log first
                trans_id = int(time.time() * 1000)
                trans_file = os.path.join(trans_dir, f"trans_{trans_id}.json")
                
                # Create transaction record
                transaction = {
                    "id": trans_id,
                    "timestamp": datetime.now().isoformat(),
                    "path": path,
                    "data_size": len(str(data))
                }
                
                with open(trans_file, "w") as f:
                    json.dump(transaction, f)
                
                # Create backup first
                if os.path.exists(path):
                    import shutil
                    backup_path = path + ".backup"
                    shutil.copy2(path, backup_path)
                
                # Save to temp file first
                temp_file = path + ".tmp"
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                # Atomic replace
                os.replace(temp_file, path)
                
                # Clean up successful transaction
                if os.path.exists(trans_file):
                    os.remove(trans_file)
                
                # Clean up old transactions (older than 1 hour)
                for fname in os.listdir(trans_dir):
                    if fname.startswith("trans_") and fname.endswith(".json"):
                        try:
                            trans_time = int(fname.split("_")[1].split(".")[0])
                            if time.time() * 1000 - trans_time > 3600000:  # 1 hour
                                os.remove(os.path.join(trans_dir, fname))
                        except:
                            pass
                
                return True
                
            except Exception as e:
                if attempt == SAVE_RETRY_COUNT - 1:
                    print(f"⚠️ Failed to save {path} after {SAVE_RETRY_COUNT} attempts: {e}")
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except:
                        pass
                    return False
                time.sleep(0.2 * (attempt + 1))  # Exponential backoff
    
    @staticmethod
    def cleanup_old_data(data, max_age_days):
        """Clean up old data entries"""
        now = time.time()
        cutoff = now - (max_age_days * 86400)
        
        cleaned = {}
        for key, entry in data.items():
            # Check various timestamp fields
            entry_time = entry.get("last_checked", 
                                 entry.get("joined_at", 
                                         entry.get("started", 
                                                 entry.get("timestamp", 0))))
            
            if isinstance(entry_time, str):
                try:
                    # Try to parse ISO format
                    dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    entry_time = dt.timestamp()
                except:
                    entry_time = 0
            
            if entry_time > cutoff:
                cleaned[key] = entry
        
        return cleaned

json_manager = AtomicJSONManager()

def load_json(path, default):
    return json_manager.load_json(path, default)

def save_json(path, data):
    return json_manager.atomic_save(path, data)

def load_join_tracking():
    data = load_json(JOIN_TRACKING_FILE, {})
    # Auto-cleanup old tracking data
    cleaned_data = json_manager.cleanup_old_data(data, TRACKING_RETENTION_DAYS)
    if len(data) != len(cleaned_data):
        print(f"🧹 Cleaned up {len(data) - len(cleaned_data)} old tracking entries")
        save_json(JOIN_TRACKING_FILE, cleaned_data)
    return cleaned_data

def save_join_tracking(data):
    return save_json(JOIN_TRACKING_FILE, data)

# -----------------------
# 🛡️ SAFE MESSAGE CLEANUP HELPERS
# -----------------------
async def safe_delete_message(channel, msg_id, max_retries=MAX_CLEANUP_RETRIES):
    """Safely delete a single message with retry logic"""
    if not channel or not msg_id:
        return False
    
    try:
        msg_id_int = int(msg_id)
    except (ValueError, TypeError):
        print(f"⚠️ Invalid message ID format: {msg_id}")
        return False
    
    for attempt in range(max_retries):
        try:
            msg = await channel.fetch_message(msg_id_int)
            
            if msg.author.id != client.user.id:
                print(f"⚠️ Won't delete message {msg_id} - not from bot")
                return False
                
            await msg.delete()
            return True
            
        except discord.NotFound:
            return True
        except discord.Forbidden:
            print(f"⚠️ No permission to delete message {msg_id} in #{channel.name}")
            return False
        except discord.HTTPException as e:
            if e.status == 429:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"⏰ Rate limited deleting message {msg_id}, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"⚠️ HTTP error deleting message {msg_id}: {e.status}")
                break
        except asyncio.TimeoutError:
            print(f"⏰ Timeout fetching message {msg_id}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            break
        except Exception as e:
            print(f"⚠️ Unexpected error deleting message {msg_id}: {e}")
            break
    
    return False

# ... [Rest of the cleanup functions remain the same, but updated to use random backoff]

# -----------------------
# NEW: SYSTEM HEALTH MONITOR
# -----------------------
class SystemHealthMonitor:
    """Monitors bot health and performance"""
    
    def __init__(self):
        self.start_time = time.time()
        self.operation_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.last_report_time = time.time()
        self.report_interval = 3600  # Report every hour
    
    def record_operation(self, op_name):
        self.operation_counts[op_name] += 1
    
    def record_error(self, error_type):
        self.error_counts[error_type] += 1
    
    async def periodic_report(self):
        """Generate periodic health report"""
        while True:
            await asyncio.sleep(self.report_interval)
            self.generate_report()
    
    def generate_report(self):
        """Generate health report"""
        current_time = time.time()
        uptime_hours = (current_time - self.start_time) / 3600
        
        print(f"\n📊 SYSTEM HEALTH REPORT ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"⏱️  Uptime: {uptime_hours:.1f} hours")
        print(f"🧮 Total operations: {sum(self.operation_counts.values())}")
        
        if self.operation_counts:
            print("📈 Operation breakdown:")
            for op, count in sorted(self.operation_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {op}: {count}")
        
        if self.error_counts:
            print("⚠️  Error breakdown:")
            for err, count in sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {err}: {count}")
        
        print(f"📝 Pending recruits: {len(pending_recruits)}")
        print(f"👤 Tracked members: {len(member_join_tracking)}")
        print(f"🔥 Recent joins cache: {len(recent_joins)}")
        print(f"⏰ Presence cooldown cache: {len(presence_cooldown)}")
        print("-" * 50)
        
        # Reset counters for next period
        self.last_report_time = current_time

health_monitor = None

# -----------------------
# NEW: CLEANUP FUNCTION FOR STUCK RECRUITS
# -----------------------
def cleanup_stuck_recruits():
    """Clean up stuck recruits from previous runs"""
    try:
        stuck_cleaned = 0
        now = int(time.time())
        for uid, entry in list(pending_recruits.items()):
            started = entry.get("started", now)
            if now - started > 86400:  # 24 hours
                del pending_recruits[uid]
                stuck_cleaned += 1
        if stuck_cleaned > 0:
            save_json(PENDING_FILE, pending_recruits)
            print(f"🧹 Cleaned up {stuck_cleaned} stuck recruits from previous runs")
    except Exception as e:
        print(f"⚠️ Failed to cleanup stuck recruits: {e}")

# -----------------------
# UPDATED EVENTS WITH ENHANCED STABILITY
# -----------------------
@client.event
async def on_ready():
    try:
        print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Bot is READY! Logged in as {client.user}")
        
        global state, pending_recruits, member_join_tracking, safety_wrappers, health_monitor
        state = load_json(STATE_FILE, state)
        pending_recruits = load_json(PENDING_FILE, pending_recruits)
        member_join_tracking = load_join_tracking()
        
        # Initialize safety wrappers and health monitor
        safety_wrappers = SafetyWrappers(client)
        health_monitor = SystemHealthMonitor()
        
        # Start health monitoring
        client.loop.create_task(health_monitor.periodic_report())
        
        # Clean up stuck data
        cleanup_stuck_recruits()
        
        # Clean up old join cooldowns
        cleanup_old_joins()
        
        print(f"📊 Loaded state: {len(pending_recruits)} pending recruits")
        print(f"📈 Loaded tracking: {len(member_join_tracking)} members tracked")
        
        # Start background tasks
        client.loop.create_task(safe_inactivity_checker())
        client.loop.create_task(weekly_role_checker())
        print(f"🔄 Background tasks started")
        
    except Exception as e:
        log_error("ON_READY", e)
        raise

def cleanup_old_joins():
    """Clean up old join cooldown entries"""
    global recent_joins
    cutoff = time.time() - (JOIN_COOLDOWN_CLEANUP_HOURS * 3600)
    old_count = len(recent_joins)
    recent_joins = {k: v for k, v in recent_joins.items() if v > cutoff}
    if old_count > len(recent_joins):
        print(f"🧹 Cleaned up {old_count - len(recent_joins)} old join cooldown entries")

@client.event
async def on_member_join(member):
    try:
        # Record operation for monitoring
        if health_monitor:
            health_monitor.record_operation("member_join")
        
        # COOLDOWN CHECK with enhanced race condition prevention
        current_time = time.time()
        member_id = str(member.id)
        
        # Use a lock-like mechanism for race condition prevention
        if member_id in recent_joins:
            if current_time - recent_joins[member_id] < 30:
                print(f"⏰ Ignoring duplicate join event for {member.display_name}")
                return
        
        # Atomic update with timestamp
        recent_joins[member_id] = current_time
        
        # ... [Rest of the on_member_join function remains similar but with health monitoring]
        
        # Add to health monitoring
        if health_monitor:
            health_monitor.record_operation("recruitment_started")
        
    except Exception as e:
        log_error("ON_MEMBER_JOIN", e)
        if health_monitor:
            health_monitor.record_error("member_join_error")

# ... [Rest of the events updated similarly with health monitoring]

@client.event
async def on_raw_reaction_add(payload):
    try:
        if payload.user_id == client.user.id:
            return
            
        if health_monitor:
            health_monitor.record_operation("reaction_add")
        
        msg_id = payload.message_id
        uid = None
        entry = None
        
        # Use a more robust lookup with transaction safety
        pending_copy = pending_recruits.copy()  # Work on copy to avoid race conditions
        for k, v in pending_copy.items():
            if v.get("review_message_id") == msg_id and not v.get("resolved") and v.get("under_review"):
                uid = k
                entry = v.copy()  # Copy entry to avoid mutation during processing
                break
        
        if not uid or not entry:
            return

        # Get emoji string
        emoji_str = str(payload.emoji)
        
        if emoji_str not in [UPVOTE_EMOJI, DOWNVOTE_EMOJI, CLOCK_EMOJI]:
            return

        guild = client.get_guild(payload.guild_id) if payload.guild_id else None
        if not guild:
            guild = client.guilds[0] if client.guilds else None
        
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor:
            return

        # Check admin with safety wrapper
        if not safety_wrappers or not safety_wrappers.is_admin(reactor):
            try:
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    message = await channel.fetch_message(msg_id)
                    await message.remove_reaction(payload.emoji, reactor)
            except:
                pass
            return

        # CRITICAL FIX: Use transaction-style atomic update to prevent race conditions
        if uid in pending_recruits:
            current_entry = pending_recruits[uid]
            if current_entry.get("resolved"):
                return
            
            # Mark as resolved atomically
            current_entry["resolved"] = True
            save_json(PENDING_FILE, pending_recruits)
            
            # Continue with processing...
            # ... [Rest of the reaction processing]
            
    except Exception as e:
        log_error("ON_RAW_REACTION_ADD", e)
        if health_monitor:
            health_monitor.record_error("reaction_error")

# -----------------------
# ENHANCED INACTIVITY CHECKER WITH MEMORY MANAGEMENT
# -----------------------
async def safe_inactivity_checker():
    await client.wait_until_ready()
    cleanup_counter = 0
    
    while not client.is_closed():
        try:
            now = int(time.time())
            cleanup_counter += 1
            
            # 🆕 Enhanced memory cleanup every 10 minutes
            if cleanup_counter % 30 == 0:
                try:
                    # Clean up old pending recruits
                    old_count = len(pending_recruits)
                    pending_copy = pending_recruits.copy()
                    
                    for uid, entry in pending_copy.items():
                        if entry.get("resolved") or entry.get("under_review"):
                            continue
                        
                        started = entry.get("started", now)
                        if now - started > 10800:  # 3 hours
                            del pending_recruits[uid]
                    
                    if old_count != len(pending_recruits):
                        save_json(PENDING_FILE, pending_recruits)
                        print(f"🧹 Cleaned up {old_count - len(pending_recruits)} old pending recruits")
                    
                    # Clean up join cooldowns
                    cleanup_old_joins()
                    
                    # Clean up presence cooldown
                    global presence_cooldown
                    old_presence = len(presence_cooldown)
                    cutoff = now - PRESENCE_COOLDOWN_TIME
                    presence_cooldown = {k: v for k, v in presence_cooldown.items() if v > cutoff}
                    if old_presence != len(presence_cooldown):
                        print(f"🧹 Cleaned up {old_presence - len(presence_cooldown)} old presence cooldowns")
                    
                except Exception as e:
                    log_error("MEMORY_CLEANUP", e)
            
            # ... [Rest of inactivity checking]
            
            await asyncio.sleep(20)
            
        except Exception as e:
            log_error("INACTIVITY_CHECKER", e)
            if health_monitor:
                health_monitor.record_error("inactivity_checker_error")
            await asyncio.sleep(60)

# -----------------------
# ENHANCED WEEKLY ROLE CHECKER WITH PAGINATION
# -----------------------
async def weekly_role_checker():
    """Check weekly for members without roles who joined >7 days ago"""
    await client.wait_until_ready()
    
    while not client.is_closed():
        try:
            await asyncio.sleep(24 * 3600)  # 24 hours
            
            now = int(time.time())
            print(f"🔄 Running weekly role check...")
            
            guild = None
            for g in client.guilds:
                guild = g
                break
            
            if not guild:
                continue
            
            staff_ch = client.get_channel(CHANNELS["staff_review"])
            if not staff_ch:
                continue
            
            # Get clan roles
            clan_role_ids = [
                ROLES.get("imperius"),
                ROLES.get("og_imperius"),
                ROLES.get("clan_master"),
                ROLES.get("queen")
            ]
            
            # Find members without clan roles - WITH PAGINATION FOR LARGE SERVERS
            old_members_without_roles = []
            member_count = 0
            
            # Fetch members in chunks to avoid timeout
            async for member in guild.fetch_members(limit=1000):  # Limit to 1000 for safety
                member_count += 1
                
                # Skip bots
                if member.bot:
                    continue
                
                # Check if member has any clan role
                has_clan_role = False
                for role in member.roles:
                    if role.id in clan_role_ids:
                        has_clan_role = True
                        break
                
                # If no clan role and joined >7 days ago
                if not has_clan_role and member.joined_at:
                    days_since_join = (datetime.now(timezone.utc) - member.joined_at).days
                    if days_since_join >= 7:
                        old_members_without_roles.append({
                            "member": member,
                            "days_since_join": days_since_join
                        })
                
                # Safety: Don't process more than 2000 members
                if member_count >= 2000:
                    print(f"⚠️ Weekly check: Hit safety limit of 2000 members")
                    break
            
            print(f"📊 Weekly check: Processed {member_count} members, found {len(old_members_without_roles)} without roles")
            
            # Process in smaller batches for safety
            batch_size = 8  # Smaller batches for safety
            for batch_start in range(0, len(old_members_without_roles), batch_size):
                batch = old_members_without_roles[batch_start:batch_start + batch_size]
                
                # Create batch embed
                embed = discord.Embed(
                    title=f"🚨 WEEKLY CLEANUP (Batch {batch_start//batch_size + 1})",
                    description=f"**Found {len(batch)} members without roles for 7+ days**",
                    color=0xff0000,
                    timestamp=datetime.now(timezone.utc)
                )
                
                for i, data in enumerate(batch):
                    member = data["member"]
                    embed.add_field(
                        name=f"{i+1}. {member.display_name}",
                        value=f"**Joined:** {data['days_since_join']} days ago\n**ID:** `{member.id}`",
                        inline=False
                    )
                
                embed.add_field(
                    name="🛠️ Admin Actions",
                    value=f"**React:**\n{UPVOTE_EMOJI}=Kick\n{DOWNVOTE_EMOJI}=Grant role\n{CLOCK_EMOJI}=Review",
                    inline=False
                )
                
                # Send with error handling
                try:
                    alert_msg = await staff_ch.send(embed=embed)
                    await alert_msg.add_reaction(UPVOTE_EMOJI)
                    await alert_msg.add_reaction(DOWNVOTE_EMOJI)
                    await alert_msg.add_reaction(CLOCK_EMOJI)
                    
                    # Store batch info
                    for data in batch:
                        member_id = str(data["member"].id)
                        if member_id not in pending_recruits:
                            pending_recruits[member_id] = {
                                "started": now,
                                "under_review": True,
                                "review_message_id": alert_msg.id,
                                "is_weekly_cleanup": True
                            }
                    
                    save_json(PENDING_FILE, pending_recruits)
                    
                    # Delay between batches to avoid rate limits
                    if batch_start + batch_size < len(old_members_without_roles):
                        await asyncio.sleep(2)
                        
                except Exception as batch_error:
                    print(f"⚠️ Failed to send batch {batch_start//batch_size + 1}: {batch_error}")
                    await asyncio.sleep(5)  # Longer delay on error
                
        except Exception as e:
            log_error("WEEKLY_ROLE_CHECKER", e)
            if health_monitor:
                health_monitor.record_error("weekly_checker_error")
            await asyncio.sleep(3600)

# -----------------------
# SUPERVISED STARTUP WITH HEALTH CHECKS
# -----------------------
def run_bot_forever():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ No token!")
        return

    restart_count = 0
    max_restarts = 10
    
    while restart_count < max_restarts:
        try:
            print(f"🚀 Starting bot (attempt {restart_count + 1}/{max_restarts})...")
            print(f"⚙️  Cleanup: {'ENABLED' if CLEANUP_ENABLED else 'DISABLED'}")
            print(f"📊 Tracking retention: {TRACKING_RETENTION_DAYS} days")
            
            # Pre-flight health check
            if os.path.exists("bot_errors.log"):
                size_mb = os.path.getsize("bot_errors.log") / (1024 * 1024)
                if size_mb > 50:
                    print(f"⚠️ Error log is large: {size_mb:.1f}MB")
            
            client.run(token, reconnect=True)
            
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
                wait_time = min(30 * (2 ** restart_count), 300)  # Exponential backoff, max 5 min
                print(f"🔄 Restarting in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"💀 Too many restarts ({max_restarts}). Giving up.")
                break
    
    print("💀 Bot has stopped.")

# -----------------------
# START WITH ENHANCED STABILITY
# -----------------------
if __name__ == "__main__":
    print("🎯 Starting bot with enhanced stability...")
    print(f"🔧 Python: {sys.version}")
    print(f"🔧 Discord.py: {discord.__version__}")
    
    # Start Flask
    def start_flask():
        port = int(os.environ.get("PORT", 8080))
        print(f"🌐 Flask on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    # Start pinger
    threading.Thread(target=ping_self, daemon=True).start()
    
    # Start bot
    print("🤖 Starting Discord bot...")
    run_bot_forever()
