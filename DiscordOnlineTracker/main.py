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
# CONFIG
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
UPVOTE_EMOJI = "👍🏻"
DOWNVOTE_EMOJI = "👎🏻"
CLOCK_EMOJI = "⏰"

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
        self.in_progress_operations = {}
        
    async def assign_role_safe(self, member, role_id, reason=""):
        """Safely assign role with all necessary checks"""
        operation_key = f"role_{member.id}_{role_id}"
        
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
        
        self.in_progress_operations[operation_key] = True
        
        try:
            if not self.role_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
            
            if not member or not role_id:
                return False, "Invalid parameters"
            
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
            
            return True, f"Assigned role {role.name}"
            
        except discord.Forbidden:
            self.role_circuit.record_failure()
            return False, "Bot lacks permissions"
        except discord.HTTPException as e:
            self.role_circuit.record_failure()
            if e.status == 429:
                wait_time = random.uniform(5, 10)
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
            if operation_key in self.in_progress_operations:
                del self.in_progress_operations[operation_key]
    
    async def kick_member_safe(self, member, reason=""):
        """Safely kick a member with all necessary checks"""
        operation_key = f"kick_{member.id}"
        
        if operation_key in self.in_progress_operations:
            return False, "Operation already in progress"
        
        self.in_progress_operations[operation_key] = True
        
        try:
            if not self.kick_circuit.can_execute():
                return False, "Circuit breaker open - too many failures"
            
            if not member:
                return False, "Invalid member"
            
            current_time = time.time()
            if current_time - self.last_kick_time < self.kick_cooldown:
                await asyncio.sleep(self.kick_cooldown)
            
            guild = member.guild
            
            if member.id == guild.owner_id:
                return False, "Cannot kick server owner"
            
            bot_member = guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.kick_members:
                self.kick_circuit.record_failure()
                return False, "Bot lacks kick_members permission"
            
            if member.top_role.position >= bot_member.top_role.position:
                self.kick_circuit.record_failure()
                return False, f"Cannot kick member with equal or higher role"
            
            await member.kick(reason=reason)
            self.last_kick_time = time.time()
            self.kick_circuit.record_success()
            
            return True, f"Kicked {member.display_name}"
            
        except discord.Forbidden:
            self.kick_circuit.record_failure()
            return False, "Bot lacks permissions to kick"
        except discord.HTTPException as e:
            self.kick_circuit.record_failure()
            if e.status == 429:
                wait_time = random.uniform(5, 10)
                print(f"⏰ Rate limited kicking, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                return False, "Rate limited - try again"
            else:
                return False, f"HTTP error {e.status}: {e.text}"
        except Exception as e:
            self.kick_circuit.record_failure()
            return False, f"Unexpected error: {str(e)[:100]}"
        finally:
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
recent_joins = {}
presence_cooldown = {}
PRESENCE_COOLDOWN_TIME = 300
member_join_tracking = {}

# -----------------------
# 🛡️ ENHANCED LOAD/SAVE
# -----------------------
class AtomicJSONManager:
    """Manages JSON files with transaction safety"""
    
    @staticmethod
    def load_json(path, default):
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
        for attempt in range(SAVE_RETRY_COUNT):
            try:
                if os.path.exists(path):
                    import shutil
                    backup_path = path + ".backup"
                    shutil.copy2(path, backup_path)
                
                temp_file = path + ".tmp"
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                os.replace(temp_file, path)
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
                time.sleep(0.2 * (attempt + 1))

json_manager = AtomicJSONManager()

def load_json(path, default):
    return json_manager.load_json(path, default)

def save_json(path, data):
    return json_manager.atomic_save(path, data)

def load_join_tracking():
    data = load_json(JOIN_TRACKING_FILE, {})
    return data

def save_join_tracking(data):
    return save_json(JOIN_TRACKING_FILE, data)

# -----------------------
# 🛡️ SAFE MESSAGE CLEANUP
# -----------------------
async def safe_delete_message(channel, msg_id, max_retries=MAX_CLEANUP_RETRIES):
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

async def safe_cleanup_messages(channel, message_ids):
    if not CLEANUP_ENABLED or not channel or not message_ids:
        return 0
    
    unique_ids = []
    seen = set()
    for msg_id in message_ids:
        if msg_id and msg_id not in seen:
            try:
                int(msg_id)
                unique_ids.append(msg_id)
                seen.add(msg_id)
            except (ValueError, TypeError):
                print(f"⚠️ Skipping invalid message ID: {msg_id}")
    
    if not unique_ids:
        return 0
    
    print(f"🧹 Attempting to clean up {len(unique_ids)} messages in #{channel.name}")
    
    deleted_count = 0
    for i, msg_id in enumerate(unique_ids):
        success = await safe_delete_message(channel, msg_id)
        if success:
            deleted_count += 1
        
        if i < len(unique_ids) - 1:
            await asyncio.sleep(CLEANUP_RATE_LIMIT)
    
    return deleted_count

async def safe_cleanup_recruit_messages(uid, recruit_ch):
    if not CLEANUP_ENABLED or uid not in pending_recruits or not recruit_ch:
        return 0
    
    try:
        message_ids = []
        entry = pending_recruits[uid]
        
        for key in ["welcome_msg", "announce", "pause_msg"]:
            msg_id = entry.get(key)
            if msg_id:
                message_ids.append(msg_id)
        
        if not message_ids:
            return 0
        
        deleted = await safe_cleanup_messages(recruit_ch, message_ids)
        
        if deleted > 0:
            print(f"✅ Successfully deleted {deleted}/{len(message_ids)} messages for recruit {uid}")
        
        if uid in pending_recruits:
            pending_recruits[uid]["welcome_msg"] = None
            pending_recruits[uid]["announce"] = None
            pending_recruits[uid]["pause_msg"] = None
        
        return deleted
        
    except Exception as e:
        print(f"⚠️ Critical error in cleanup for recruit {uid}: {e}")
        log_error("SAFE_CLEANUP", f"Failed cleanup for {uid}: {e}")
        return 0

# -----------------------
# NEW: SYSTEM HEALTH MONITOR
# -----------------------
class SystemHealthMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.operation_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.last_report_time = time.time()
        self.report_interval = 3600
    
    def record_operation(self, op_name):
        self.operation_counts[op_name] += 1
    
    def record_error(self, error_type):
        self.error_counts[error_type] += 1
    
    async def periodic_report(self):
        while True:
            await asyncio.sleep(self.report_interval)
            self.generate_report()
    
    def generate_report(self):
        current_time = time.time()
        uptime_hours = (current_time - self.start_time) / 3600
        
        print(f"\n📊 SYSTEM HEALTH REPORT ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"⏱️  Uptime: {uptime_hours:.1f} hours")
        print(f"🧮 Total operations: {sum(self.operation_counts.values())}")
        
        if self.operation_counts:
            print("📈 Operation breakdown:")
            for op, count in sorted(self.operation_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {op}: {count}")
        
        if self.error_counts:
            print("⚠️  Error breakdown:")
            for err, count in sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {err}: {count}")
        
        print(f"📝 Pending recruits: {len(pending_recruits)}")
        print(f"👤 Tracked members: {len(member_join_tracking)}")
        print("-" * 50)

health_monitor = None

# -----------------------
# CLEANUP FUNCTIONS
# -----------------------
def cleanup_stuck_recruits():
    try:
        stuck_cleaned = 0
        now = int(time.time())
        for uid, entry in list(pending_recruits.items()):
            started = entry.get("started", now)
            if now - started > 86400:
                del pending_recruits[uid]
                stuck_cleaned += 1
        if stuck_cleaned > 0:
            save_json(PENDING_FILE, pending_recruits)
            print(f"🧹 Cleaned up {stuck_cleaned} stuck recruits from previous runs")
    except Exception as e:
        print(f"⚠️ Failed to cleanup stuck recruits: {e}")

def cleanup_old_joins():
    global recent_joins
    cutoff = time.time() - (JOIN_COOLDOWN_CLEANUP_HOURS * 3600)
    old_count = len(recent_joins)
    recent_joins = {k: v for k, v in recent_joins.items() if v > cutoff}
    if old_count > len(recent_joins):
        print(f"🧹 Cleaned up {old_count - len(recent_joins)} old join cooldown entries")

# -----------------------
# 🛠️ FIXED: ENHANCED MEMBER JOIN HANDLER
# -----------------------
@client.event
async def on_member_join(member):
    try:
        if health_monitor:
            health_monitor.record_operation("member_join")
        
        current_time = time.time()
        member_id = str(member.id)
        
        # 🛠️ FIX: Allow re-joins for kicked/returning members
        # Only block rapid duplicate joins (10 seconds)
        if member_id in recent_joins:
            if current_time - recent_joins[member_id] < 10:
                print(f"⏰ Rapid re-join detected for {member.display_name}, ignoring")
                return
        
        recent_joins[member_id] = current_time
        
        print(f"👤 [{datetime.now().strftime('%H:%M:%S')}] Member joined: {member.display_name}")
        
        recruit_ch = client.get_channel(CHANNELS["recruit"])
        staff_ch = client.get_channel(CHANNELS["staff_review"])

        # 🛠️ FIX: Check if user was previously processed
        uid = str(member.id)
        
        # Clear any old pending entries for this user (fresh start)
        if uid in pending_recruits:
            print(f"🔄 Clearing old pending entry for returning member {member.display_name}")
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)
        
        # Check tracking status for returning members
        tracking_data = member_join_tracking.get(uid, {})
        old_status = tracking_data.get("status", "")
        
        # 🛠️ FIX: Update tracking for returning members
        if old_status:
            print(f"🔄 Returning member detected: {member.display_name} (previous status: {old_status})")
            member_join_tracking[uid]["status"] = "rejoining"
            member_join_tracking[uid]["rejoin_count"] = member_join_tracking[uid].get("rejoin_count", 0) + 1
            member_join_tracking[uid]["last_rejoin"] = current_time
            member_join_tracking[uid]["notes"].append(f"Rejoined at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            save_join_tracking(member_join_tracking)
        
        # Store message IDs for cleanup
        welcome_msg_id = None
        notice_msg_id = None
        pause_msg_id = None

        # Welcome message
        welcome_sent = False
        try:
            if recruit_ch:
                welcome_msg = await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Imperius!")
                welcome_msg_id = welcome_msg.id
                welcome_sent = True
        except Exception as e:
            print(f"⚠️ Failed to send welcome: {e}")

        # Notice message
        try:
            if recruit_ch:
                notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
                notice_msg_id = notice.id
        except Exception as e:
            print(f"⚠️ Failed to send notice: {e}")

        # Initialize pending recruit
        pending_recruits[uid] = {
            "started": int(current_time),
            "last": int(current_time),
            "answers": [],
            "announce": notice_msg_id,
            "welcome_msg": welcome_msg_id,
            "pause_msg": None,
            "under_review": False,
            "review_message_id": None,
            "resolved": False,
            "additional_info": {},
            "welcome_sent": welcome_sent,
            "dm_failed_reason": None,
            "is_returning_member": bool(old_status),  # Track if returning
            "previous_status": old_status  # Store previous status
        }
        save_json(PENDING_FILE, pending_recruits)

        # Update tracking
        member_join_tracking[uid] = {
            "joined_at": int(current_time),
            "username": member.name,
            "display_name": member.display_name,
            "has_roles": False,
            "last_checked": int(current_time),
            "status": "pending_verification",
            "verification_attempts": 1,
            "dm_success": False,
            "notes": [f"Joined/rejoined at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (previous: {old_status})"]
        }
        save_join_tracking(member_join_tracking)
        
        print(f"📝 [{datetime.now().strftime('%H:%M:%S')}] Added {member.display_name} to tracking")

        # 🛠️ FIXED DM FLOW WITH RETURNING MEMBER HANDLING
        try:
            dm = await member.create_dm()
            
            # Send initial DM
            embed = discord.Embed(
                title="🎮 Impèrius Clan Recruitment",
                description="Welcome to Impèrius! Please answer the following questions.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Type 'cancel' at any time to stop the application")
            
            await dm.send(embed=embed)
            await asyncio.sleep(2)
            
            # 🛠️ ADDED: Former member check for returning users
            if old_status in ["approved", "conditional", "former_member"]:
                await dm.send("**Welcome back! Since you were previously in the server, we'll proceed with the standard questions.**")
                await asyncio.sleep(1)
            
            # Ask the 5 questions
            for i, question in enumerate(RECRUIT_QUESTIONS):
                await dm.send(f"**Question {i+1}/{len(RECRUIT_QUESTIONS)}**\n{question}")
                
                try:
                    reply = await client.wait_for(
                        "message",
                        timeout=300.0,
                        check=lambda m: m.author.id == member.id and m.channel.id == dm.id
                    )
                    
                    if reply.content.lower() == 'cancel':
                        await dm.send("❌ Application cancelled.")
                        
                        if CLEANUP_ENABLED and recruit_ch:
                            await safe_cleanup_recruit_messages(uid, recruit_ch)
                        
                        if uid in pending_recruits:
                            del pending_recruits[uid]
                            save_json(PENDING_FILE, pending_recruits)
                        
                        return
                    
                    pending_recruits[uid]["answers"].append(reply.content.strip())
                    pending_recruits[uid]["last"] = int(time.time())
                    save_json(PENDING_FILE, pending_recruits)
                    
                    member_join_tracking[uid]["dm_success"] = True
                    member_join_tracking[uid]["notes"].append(f"Answered question {i+1}")
                    save_join_tracking(member_join_tracking)
                    
                except asyncio.TimeoutError:
                    await dm.send("⏰ Timeout! You took too long to respond. Application cancelled.")
                    
                    member_join_tracking[uid]["status"] = "timed_out"
                    member_join_tracking[uid]["last_checked"] = int(time.time())
                    member_join_tracking[uid]["notes"].append("Timed out during interview")
                    save_join_tracking(member_join_tracking)
                    
                    if staff_ch:
                        embed = discord.Embed(
                            title="⚠️ Recruit Timed Out",
                            description=f"{member.mention} timed out during DM interview.",
                            color=discord.Color.orange()
                        )
                        await staff_ch.send(embed=embed)
                    
                    return

            # All questions answered
            await dm.send("✅ Thank you! Your answers have been submitted for review.")
            
            # Cleanup messages
            if CLEANUP_ENABLED and recruit_ch:
                deleted = await safe_cleanup_recruit_messages(uid, recruit_ch)
                if deleted > 0:
                    print(f"✅ Cleaned up {deleted} messages for {member.display_name}")
                save_json(PENDING_FILE, pending_recruits)

            # Send to admin channel
            try:
                if staff_ch:
                    formatted = ""
                    for i, (question, answer) in enumerate(zip(RECRUIT_QUESTIONS, pending_recruits[uid]["answers"])):
                        short_q = question.split('\n')[0][:100] + "..."
                        formatted += f"**Q{i+1}:** {short_q}\n**A:** {answer[:500]}\n\n"
                    
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    
                    # Add returning member note if applicable
                    returning_note = ""
                    if old_status:
                        returning_note = f"\n**📝 Note:** This is a returning member (previous status: {old_status})"
                    
                    embed = discord.Embed(
                        title=":military_helmet: Cadet on tryout process",
                        description=f"**Applicant:** {member.mention} ({member.id}){returning_note}\n\n**Answers:**\n{formatted}",
                        color=discord.Color.gold(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    voting_text = (
                        f"**Vote:**\n"
                        f"{UPVOTE_EMOJI} = User passed tryout (Grant 'Impèrius🔥' role)\n"
                        f"{DOWNVOTE_EMOJI} = User did not pass (Kick from server)\n"
                        f"{CLOCK_EMOJI} = Conditional process (Keep without roles)"
                    )
                    
                    embed.add_field(name="Decision", value=voting_text, inline=False)
                    embed.set_footer(text=f"Submitted: {now_str}")
                    embed.set_thumbnail(url=member.display_avatar.url if member.avatar else member.default_avatar.url)
                    
                    review_msg = await staff_ch.send(embed=embed)
                    
                    await review_msg.add_reaction(UPVOTE_EMOJI)
                    await review_msg.add_reaction(DOWNVOTE_EMOJI)
                    await review_msg.add_reaction(CLOCK_EMOJI)
                    
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    save_json(PENDING_FILE, pending_recruits)
                    
            except Exception as e:
                print(f"⚠️ Failed to post to admin channel: {e}")
                
        except discord.Forbidden:
            # DM failed
            print(f"⚠️ Could not DM {member.display_name}: DMs blocked")
            
            member_join_tracking[uid]["status"] = "dm_failed"
            member_join_tracking[uid]["last_checked"] = int(time.time())
            member_join_tracking[uid]["notes"].append("User blocked DMs")
            save_join_tracking(member_join_tracking)
            
            try:
                if recruit_ch:
                    pause_msg = await recruit_ch.send(f"⚠️ {member.mention} verification paused. Admins will review manually.")
                    pending_recruits[uid]["pause_msg"] = pause_msg.id
                    save_json(PENDING_FILE, pending_recruits)
                    
            except Exception as pause_error:
                print(f"⚠️ Failed to send pause message: {pause_error}")
            
            try:
                if staff_ch:
                    returning_note = ""
                    if old_status:
                        returning_note = f"\n**📝 Note:** Returning member (previous: {old_status})"
                    
                    embed = discord.Embed(
                        title=":military_helmet: Cadet failed to respond (DMs blocked)",
                        description=f"**Applicant:** {member.mention} ({member.id}){returning_note}\n**Status:** User blocked DMs or didn't respond\n\n",
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    voting_text = (
                        f"**Vote:**\n"
                        f"{UPVOTE_EMOJI} = Grant 'Impèrius🔥' role (pardon)\n"
                        f"{DOWNVOTE_EMOJI} = Kick from server\n"
                        f"{CLOCK_EMOJI} = Conditional (keep without roles)"
                    )
                    
                    embed.add_field(name="Decision", value=voting_text, inline=False)
                    embed.set_thumbnail(url=member.display_avatar.url if member.avatar else member.default_avatar.url)
                    
                    review_msg = await staff_ch.send(embed=embed)
                    
                    await review_msg.add_reaction(UPVOTE_EMOJI)
                    await review_msg.add_reaction(DOWNVOTE_EMOJI)
                    await review_msg.add_reaction(CLOCK_EMOJI)
                    
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    pending_recruits[uid]["dm_failed_reason"] = "DMs blocked"
                    save_json(PENDING_FILE, pending_recruits)
                    
            except Exception as e:
                print(f"⚠️ Failed to create admin review post: {e}")
                
        except Exception as e:
            # Other DM error
            print(f"⚠️ Could not complete DM flow for {member.display_name}: {e}")
            
            member_join_tracking[uid]["status"] = "dm_failed"
            member_join_tracking[uid]["last_checked"] = int(time.time())
            member_join_tracking[uid]["notes"].append(f"DM error: {str(e)[:100]}")
            save_join_tracking(member_join_tracking)
            
            if staff_ch:
                try:
                    returning_note = ""
                    if old_status:
                        returning_note = f"\n**📝 Note:** Returning member (previous: {old_status})"
                    
                    embed = discord.Embed(
                        title=":military_helmet: Cadet - DM Error",
                        description=f"**Applicant:** {member.mention} ({member.id}){returning_note}\n**Error:** {str(e)[:200]}\n\n",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    voting_text = (
                        f"**Vote:**\n"
                        f"{UPVOTE_EMOJI} = Grant 'Impèrius🔥' role (pardon)\n"
                        f"{DOWNVOTE_EMOJI} = Kick from server\n"
                        f"{CLOCK_EMOJI} = Conditional (keep without roles)"
                    )
                    
                    embed.add_field(name="Decision", value=voting_text, inline=False)
                    embed.set_thumbnail(url=member.display_avatar.url if member.avatar else member.default_avatar.url)
                    
                    review_msg = await staff_ch.send(embed=embed)
                    
                    await review_msg.add_reaction(UPVOTE_EMOJI)
                    await review_msg.add_reaction(DOWNVOTE_EMOJI)
                    await review_msg.add_reaction(CLOCK_EMOJI)
                    
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    pending_recruits[uid]["dm_failed_reason"] = str(e)[:100]
                    save_json(PENDING_FILE, pending_recruits)
                    
                except Exception as e2:
                    print(f"⚠️ Failed to create error review post: {e2}")
                
    except Exception as e:
        log_error("ON_MEMBER_JOIN", e)
        if health_monitor:
            health_monitor.record_error("member_join_error")

# -----------------------
# MESSAGE HANDLER
# -----------------------
@client.event
async def on_message(message):
    try:
        if message.author.id == client.user.id:
            return

        # Admin verification command
        if message.content.startswith("!verify"):
            if not safety_wrappers or not safety_wrappers.is_admin(message.author):
                await message.channel.send("❌ You don't have permission to use this command.")
                return
                
            if len(message.mentions) > 0:
                member = message.mentions[0]
                uid = str(member.id)
                
                if uid in pending_recruits and pending_recruits[uid].get("under_review"):
                    try:
                        dm = await member.create_dm()
                        await dm.send("🪖 An admin has requested manual verification. Please answer:")
                        await dm.send(RECRUIT_QUESTIONS[0])
                        
                        pending_recruits[uid]["manual_verify_started"] = time.time()
                        save_json(PENDING_FILE, pending_recruits)
                        
                        if uid in member_join_tracking:
                            member_join_tracking[uid]["notes"].append(f"Manual verification started by {message.author.display_name}")
                            save_join_tracking(member_join_tracking)
                        
                        await message.channel.send(f"✅ Manual verification started for {member.mention}")
                    except Exception as e:
                        await message.channel.send(f"❌ Could not DM {member.mention}: {e}")
                else:
                    await message.channel.send(f"❌ {member.mention} is not in pending review or already verified.")
            else:
                await message.channel.send("❌ Please mention a user to verify. Usage: `!verify @username`")

        # Reminder channel
        if message.channel.id == CHANNELS["reminder"]:
            state["message_counter"] = state.get("message_counter", 0) + 1
            save_json(STATE_FILE, state)
            if state["message_counter"] >= REMINDER_THRESHOLD:
                r = REMINDERS[state.get("current_reminder", 0)]
                embed = discord.Embed(
                    title="Reminders Imperius!",
                    description=f"**{r['title']}**\n\n{r['description']}",
                    color=discord.Color.orange()
                )
                await message.channel.send(embed=embed)
                state["current_reminder"] = (state.get("current_reminder", 0) + 1) % len(REMINDERS)
                state["message_counter"] = 0
                save_json(STATE_FILE, state)
    except Exception as e:
        log_error("ON_MESSAGE", e)

# -----------------------
# PRESENCE UPDATE
# -----------------------
@client.event
async def on_presence_update(before, after):
    try:
        global presence_cooldown
        
        current_time = time.time()
        user_id = after.id
        
        if user_id in presence_cooldown:
            if current_time - presence_cooldown[user_id] < PRESENCE_COOLDOWN_TIME:
                return
        
        if before.status != after.status:
            if str(before.status) == "offline" and str(after.status) in ["online", "idle", "dnd"]:
                m = after
                ids = [r.id for r in m.roles]
                ch = client.get_channel(CHANNELS["main"])
                
                if not ch:
                    return
                
                if ROLES["queen"] in ids:
                    title, color = f"❤️‍🔥 Queen {m.display_name} just came online!", discord.Color.gold()
                elif ROLES["clan_master"] in ids:
                    title, color = f"🌟 Clan Master {m.display_name} just came online!", discord.Color.blue()
                elif ROLES["og_imperius"] in ids:
                    title, color = f"🐦‍🔥 OG {m.display_name} online!", discord.Color.red()
                elif ROLES["imperius"] in ids:
                    title, color = f"🔥 Member {m.display_name} just came online!", discord.Color.purple()
                else:
                    return
                
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=after.display_avatar.url)
                
                await asyncio.sleep(0.5)
                
                try:
                    await ch.send(embed=embed)
                    presence_cooldown[user_id] = current_time
                    
                    if len(presence_cooldown) > 1000:
                        old_time = current_time - PRESENCE_COOLDOWN_TIME
                        presence_cooldown = {k: v for k, v in presence_cooldown.items() if v > old_time}
                        
                except discord.HTTPException as e:
                    if e.status == 429:
                        print(f"⚠️ Rate limited on presence update, backing off...")
                        presence_cooldown[user_id] = current_time + 60
                        await asyncio.sleep(5)
                    else:
                        log_error("ON_PRESENCE_UPDATE", e)
                except Exception as e:
                    log_error("ON_PRESENCE_UPDATE", e)
    except Exception as e:
        log_error("ON_PRESENCE_UPDATE", e)

# -----------------------
# 🛠️ FIXED: REACTION HANDLER WITH RETURNING MEMBER SUPPORT
# -----------------------
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
        
        # Find which entry this reaction belongs to
        for k, v in pending_recruits.items():
            if v.get("review_message_id") == msg_id and not v.get("resolved") and v.get("under_review"):
                uid = k
                entry = v.copy()
                break
        
        if not uid or not entry:
            return

        emoji_str = str(payload.emoji)
        
        if emoji_str not in [UPVOTE_EMOJI, DOWNVOTE_EMOJI, CLOCK_EMOJI]:
            return

        guild = None
        if payload.guild_id:
            guild = client.get_guild(payload.guild_id)
        else:
            guild = client.guilds[0] if client.guilds else None
        
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor:
            return

        # Check admin
        if not safety_wrappers or not safety_wrappers.is_admin(reactor):
            try:
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    message = await channel.fetch_message(msg_id)
                    await message.remove_reaction(payload.emoji, reactor)
            except:
                pass
            return

        # Prevent race conditions
        if uid in pending_recruits:
            current_entry = pending_recruits[uid]
            if current_entry.get("resolved"):
                return
            
            # Mark as resolved atomically
            current_entry["resolved"] = True
            save_json(PENDING_FILE, pending_recruits)
        else:
            return

        # Get applicant
        applicant = guild.get_member(int(uid))
        
        # Get channels
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        recruit_ch = client.get_channel(CHANNELS["recruit"])
        
        # Admin label
        def admin_label(member):
            if not member:
                return "Unknown"
            ids = [r.id for r in member.roles]
            if ROLES.get("og_imperius") and ROLES["og_imperius"] in ids:
                return f"OG-{member.display_name}"
            if ROLES.get("clan_master") and ROLES["clan_master"] in ids:
                return f"Clan Master {member.display_name}"
            if ROLES.get("queen") and ROLES["queen"] in ids:
                return f"Queen {member.display_name}"
            return member.display_name

        approver_text = admin_label(reactor)
        
        # Process vote
        if emoji_str == UPVOTE_EMOJI:
            # Grant Impèrius🔥 role
            if applicant:
                success, message = await safety_wrappers.assign_role_safe(
                    applicant, 
                    ROLES["imperius"], 
                    f"Passed tryout - voted by {reactor.display_name}"
                )
                
                if success:
                    if staff_ch:
                        result_msg = f":military_helmet: Cadet {applicant.mention} ({applicant.id}) was granted an 'Impèrius🔥' role by: {reactor.mention}"
                        await staff_ch.send(result_msg)
                    
                    # Update tracking
                    if uid in member_join_tracking:
                        member_join_tracking[uid]["status"] = "approved"
                        member_join_tracking[uid]["has_roles"] = True
                        member_join_tracking[uid]["last_checked"] = int(time.time())
                        member_join_tracking[uid]["notes"].append(f"Granted Impèrius🔥 role by {approver_text}")
                        save_join_tracking(member_join_tracking)
                    
                    # Notify user
                    try:
                        dm = await applicant.create_dm()
                        await dm.send("🎉 Congratulations! You have passed the tryout and been granted the 'Impèrius🔥' role!")
                    except:
                        pass
                else:
                    if staff_ch:
                        await staff_ch.send(f"❌ Failed to give role to {applicant.mention if applicant else 'applicant'}: {message}")
            else:
                if staff_ch:
                    await staff_ch.send(f"❌ Could not find applicant with ID: {uid}")
        
        elif emoji_str == DOWNVOTE_EMOJI:
            # Kick the user
            if applicant:
                success, message = await safety_wrappers.kick_member_safe(
                    applicant,
                    f"Application rejected by {reactor.display_name}"
                )
                
                if success:
                    if staff_ch:
                        result_msg = f":military_helmet: Cadet {applicant.mention} ({applicant.id}) was rejected and removed from server with the permission of: {reactor.mention}"
                        await staff_ch.send(result_msg)
                    
                    # 🛠️ FIX: Clear tracking for kicked users so they can re-join
                    if uid in member_join_tracking:
                        member_join_tracking[uid]["status"] = "kicked"
                        member_join_tracking[uid]["kicked_by"] = reactor.id
                        member_join_tracking[uid]["kicked_at"] = int(time.time())
                        member_join_tracking[uid]["last_checked"] = int(time.time())
                        member_join_tracking[uid]["notes"].append(f"Kicked by {approver_text}")
                        save_join_tracking(member_join_tracking)
                        
                    # Try to send DM
                    try:
                        dm = await applicant.create_dm()
                        await dm.send("❌ Unfortunately, your application to Impèrius has been rejected. You will be removed from the server.")
                    except:
                        pass
                else:
                    if staff_ch:
                        await staff_ch.send(f"❌ Failed to kick {applicant.mention if applicant else 'applicant'}: {message}")
            else:
                if staff_ch:
                    await staff_ch.send(f"❌ Could not find applicant to kick: {uid}")
        
        elif emoji_str == CLOCK_EMOJI:
            # Conditional - no role changes
            if applicant:
                if staff_ch:
                    result_msg = f":military_helmet: Cadet {applicant.mention} ({applicant.id}) was conditional and will remain in this server until the admins final decisions ⚖️ by: {reactor.mention}"
                    await staff_ch.send(result_msg)
                
                # 🛠️ FIX: Update tracking for conditional members
                if uid in member_join_tracking:
                    member_join_tracking[uid]["status"] = "conditional"
                    member_join_tracking[uid]["conditional_since"] = int(time.time())
                    member_join_tracking[uid]["conditional_by"] = reactor.id
                    member_join_tracking[uid]["last_checked"] = int(time.time())
                    member_join_tracking[uid]["notes"].append(f"Voted conditional by {approver_text}")
                    save_join_tracking(member_join_tracking)
                
                # Notify user
                try:
                    dm = await applicant.create_dm()
                    await dm.send("⏰ Your application is under conditional review. You will remain in the server while the admins make their final decision.")
                except:
                    pass
            else:
                if staff_ch:
                    await staff_ch.send(f"❌ Could not find applicant for conditional: {uid}")
        
        # Cleanup messages
        if CLEANUP_ENABLED and recruit_ch:
            deleted = await safe_cleanup_recruit_messages(uid, recruit_ch)
            if deleted > 0:
                print(f"✅ Cleaned up {deleted} messages for recruit {uid}")
        
        # Remove from pending
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)
            
        # Delete the review message
        try:
            channel = guild.get_channel(payload.channel_id)
            if channel:
                message = await channel.fetch_message(msg_id)
                await message.delete()
        except Exception:
            pass

    except Exception as e:
        log_error("ON_RAW_REACTION_ADD", e)
        if health_monitor:
            health_monitor.record_error("reaction_error")

# -----------------------
# SAFE INACTIVITY CHECKER
# -----------------------
async def safe_inactivity_checker():
    await client.wait_until_ready()
    cleanup_counter = 0
    
    while not client.is_closed():
        try:
            now = int(time.time())
            cleanup_counter += 1
            
            # Memory cleanup every 10 minutes
            if cleanup_counter % 30 == 0:
                try:
                    # Clean up old pending recruits
                    old_count = len(pending_recruits)
                    pending_copy = pending_recruits.copy()
                    
                    for uid, entry in pending_copy.items():
                        if entry.get("resolved") or entry.get("under_review"):
                            continue
                        
                        started = entry.get("started", now)
                        if now - started > 10800:
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
            
            # Check for 24h stuck recruits
            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                    
                started = entry.get("started", now)
                if now - started >= 86400:
                    print(f"⚠️ Found recruit pending >24 hours: {uid}")
                    
                    staff_ch = client.get_channel(CHANNELS["staff_review"])
                    if staff_ch:
                        display_name = None
                        guild = staff_ch.guild if staff_ch else (client.guilds[0] if client.guilds else None)
                        if guild:
                            try:
                                m = guild.get_member(int(uid))
                                if m:
                                    display_name = f"{m.display_name} (@{m.name})"
                            except Exception:
                                display_name = None
                        
                        if display_name is None:
                            display_name = f"ID {uid}"
                        
                        embed = discord.Embed(
                            title="🚨 URGENT: Stuck Recruit (>24 hours)",
                            description=(
                                f"**Recruit {display_name} has been pending for OVER 24 HOURS!**\n\n"
                                f"**Status:** Never responded to DMs\n"
                                f"**Time pending:** {(now - started) // 3600} hours\n\n"
                                f"**Vote:**\n"
                                f"• {UPVOTE_EMOJI} = Grant 'Impèrius🔥' role (pardon)\n"
                                f"• {DOWNVOTE_EMOJI} = Kick from server\n"
                                f"• {CLOCK_EMOJI} = Conditional (keep without roles)\n\n"
                                f"*(This is an automated alert for long-pending recruits)*"
                            ),
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        embed.add_field(name="User ID", value=f"`{uid}`", inline=True)
                        embed.add_field(name="Started", value=f"<t:{started}:R>", inline=True)
                        
                        try:
                            review_msg = await staff_ch.send(embed=embed)
                            await review_msg.add_reaction(UPVOTE_EMOJI)
                            await review_msg.add_reaction(DOWNVOTE_EMOJI)
                            await review_msg.add_reaction(CLOCK_EMOJI)
                            
                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            entry["is_24h_alert"] = True
                            save_json(PENDING_FILE, pending_recruits)
                            
                            print(f"✅ Sent 24h alert for recruit {uid}")
                            
                        except Exception as e:
                            print(f"⚠️ Failed to send 24h alert for uid {uid}: {e}")
            
            # Original inactivity checking (10 minutes)
            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last = entry.get("last", entry.get("started", now))
                if now - last >= 600:
                    try:
                        rc = client.get_channel(CHANNELS["recruit"])
                        if rc and entry.get("announce"):
                            try:
                                msg = await rc.fetch_message(entry["announce"])
                                await msg.delete()
                            except Exception:
                                pass
                    except Exception:
                        pass

                    staff_ch = client.get_channel(CHANNELS["staff_review"])
                    display_name = None
                    guild = staff_ch.guild if staff_ch else (client.guilds[0] if client.guilds else None)
                    if guild:
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                display_name = f"{m.display_name} (@{m.name})"
                        except Exception:
                            display_name = None
                    if display_name is None:
                        display_name = f"ID {uid}"

                    try:
                        if staff_ch:
                            embed = discord.Embed(
                                title=":military_helmet: Recruit requires decision (Inactive)",
                                description=f"**Applicant:** {display_name}\n**Status:** Ignored approval questions\n\n**Vote:**\n{UPVOTE_EMOJI} = Grant 'Impèrius🔥' role (pardon)\n{DOWNVOTE_EMOJI} = Kick from server\n{CLOCK_EMOJI} = Conditional (keep without roles)",
                                color=discord.Color.dark_gold(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            
                            review_msg = await staff_ch.send(embed=embed)
                            await review_msg.add_reaction(UPVOTE_EMOJI)
                            await review_msg.add_reaction(DOWNVOTE_EMOJI)
                            await review_msg.add_reaction(CLOCK_EMOJI)

                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            save_json(PENDING_FILE, pending_recruits)
                    except Exception as e:
                        print(f"⚠️ Failed to post admin review for uid {uid}: {e}")
            await asyncio.sleep(20)
        except Exception as e:
            log_error("INACTIVITY_CHECKER", e)
            if health_monitor:
                health_monitor.record_error("inactivity_checker_error")
            await asyncio.sleep(60)

# -----------------------
# WEEKLY ROLE CHECKER
# -----------------------
async def weekly_role_checker():
    await client.wait_until_ready()
    
    while not client.is_closed():
        try:
            await asyncio.sleep(24 * 3600)
            
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
            
            clan_role_ids = [
                ROLES.get("imperius"),
                ROLES.get("og_imperius"),
                ROLES.get("clan_master"),
                ROLES.get("queen")
            ]
            
            old_members_without_roles = []
            member_count = 0
            
            async for member in guild.fetch_members(limit=1000):
                member_count += 1
                
                if member.bot:
                    continue
                
                # Check if member has any clan role
                has_clan_role = False
                for role in member.roles:
                    if role.id in clan_role_ids:
                        has_clan_role = True
                        break
                
                # 🛠️ FIX: Skip conditional members
                tracking_data = member_join_tracking.get(str(member.id), {})
                if tracking_data.get("status") == "conditional":
                    continue
                
                if not has_clan_role and member.joined_at:
                    days_since_join = (datetime.now(timezone.utc) - member.joined_at).days
                    if days_since_join >= 7:
                        old_members_without_roles.append({
                            "member": member,
                            "days_since_join": days_since_join
                        })
                
                if member_count >= 2000:
                    print(f"⚠️ Weekly check: Hit safety limit of 2000 members")
                    break
            
            print(f"📊 Weekly check: Processed {member_count} members, found {len(old_members_without_roles)} without roles")
            
            batch_size = 8
            for batch_start in range(0, len(old_members_without_roles), batch_size):
                batch = old_members_without_roles[batch_start:batch_start + batch_size]
                
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
                
                try:
                    alert_msg = await staff_ch.send(embed=embed)
                    await alert_msg.add_reaction(UPVOTE_EMOJI)
                    await alert_msg.add_reaction(DOWNVOTE_EMOJI)
                    await alert_msg.add_reaction(CLOCK_EMOJI)
                    
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
                    
                    if batch_start + batch_size < len(old_members_without_roles):
                        await asyncio.sleep(2)
                        
                except Exception as batch_error:
                    print(f"⚠️ Failed to send batch {batch_start//batch_size + 1}: {batch_error}")
                    await asyncio.sleep(5)
                
        except Exception as e:
            log_error("WEEKLY_ROLE_CHECKER", e)
            if health_monitor:
                health_monitor.record_error("weekly_checker_error")
            await asyncio.sleep(3600)

# -----------------------
# ON READY
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

# -----------------------
# SUPERVISED STARTUP
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
