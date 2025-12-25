# STABLE VERSION - BOT IN MAIN THREAD
import threading
import discord
import os
import time
import json
import asyncio
import sys
import traceback
from datetime import datetime, timezone
from collections import defaultdict

from keep_alive import app, ping_self

# -----------------------
# 🛡️ SAFETY CONFIGURATION
# -----------------------
CLEANUP_ENABLED = True  # Set to False to disable message cleanup if issues arise
CLEANUP_RATE_LIMIT = 1.0  # Seconds between message deletions (increase if rate limited)
MAX_CLEANUP_RETRIES = 3  # Maximum retries for failed deletions
SAVE_RETRY_COUNT = 3  # Retry count for file saves

# -----------------------
# ENHANCED ERROR HANDLING
# -----------------------
def log_error(where, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"💥 [{timestamp}] CRASH in {where}: {str(error)}"
    print(error_msg)
    
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
JOIN_TRACKING_FILE = "member_join_tracking.json"  # 🆕 Persistent tracking

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
# 🛡️ SAFETY WRAPPERS
# -----------------------
class SafetyWrappers:
    def __init__(self, client):
        self.client = client
        self.last_kick_time = 0
        self.kick_cooldown = 2.0  # 2 seconds between kicks
        self.last_role_assignment = 0
        self.role_cooldown = 1.0  # 1 second between role assignments
        
    async def assign_role_safe(self, member, role_id, reason=""):
        """Safely assign role with all necessary checks"""
        try:
            if not member or not role_id:
                return False, "Invalid parameters"
            
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_role_assignment < self.role_cooldown:
                await asyncio.sleep(self.role_cooldown)
            
            guild = member.guild
            role = guild.get_role(int(role_id))
            
            if not role:
                return False, f"Role not found (ID: {role_id})"
            
            # Check if member already has the role
            if role in member.roles:
                return True, "Already has role"
            
            # Check bot's permissions
            bot_member = guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.manage_roles:
                return False, "Bot lacks manage_roles permission"
            
            # Check role hierarchy
            if role.position >= bot_member.top_role.position:
                return False, f"Bot's role is not high enough to assign {role.name}"
            
            # Assign the role
            await member.add_roles(role, reason=reason)
            self.last_role_assignment = time.time()
            
            return True, f"Assigned role {role.name}"
            
        except discord.Forbidden:
            return False, "Bot lacks permissions"
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                wait_time = 5
                print(f"⏰ Rate limited assigning role, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                try:
                    await member.add_roles(role, reason=reason)
                    return True, f"Assigned role after cooldown"
                except Exception as retry_error:
                    return False, f"Rate limited on retry: {retry_error}"
            else:
                return False, f"HTTP error {e.status}: {e.text}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)[:100]}"
    
    async def kick_member_safe(self, member, reason=""):
        """Safely kick a member with all necessary checks"""
        try:
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
                return False, "Bot lacks kick_members permission"
            
            # Check role hierarchy
            if member.top_role.position >= bot_member.top_role.position:
                return False, f"Cannot kick member with equal or higher role"
            
            # Kick the member
            await member.kick(reason=reason)
            self.last_kick_time = time.time()
            
            return True, f"Kicked {member.display_name}"
            
        except discord.Forbidden:
            return False, "Bot lacks permissions to kick"
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                wait_time = 5
                print(f"⏰ Rate limited kicking, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                return False, "Rate limited - try again"
            else:
                return False, f"HTTP error {e.status}: {e.text}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)[:100]}"
    
    async def get_admin_roles(self, guild):
        """Get all admin roles consistently"""
        admin_roles = []
        for role_key in ["queen", "clan_master", "og_imperius"]:
            role_id = ROLES.get(role_key)
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    admin_roles.append(role)
        return admin_roles
    
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
# STATE
# -----------------------
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}
# Add a cooldown system to prevent duplicate member join events
recent_joins = {}

# Rate limiting for presence updates
presence_cooldown = {}  # {user_id: timestamp}
PRESENCE_COOLDOWN_TIME = 300  # 5 minutes in seconds

# 🆕 Persistent join tracking (never gets cleaned up)
member_join_tracking = {}

# -----------------------
# 🛡️ ENHANCED LOAD/SAVE WITH ATOMIC OPERATIONS
# -----------------------
def load_json(path, default):
    """Safely load JSON file with fallback"""
    for attempt in range(SAVE_RETRY_COUNT):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError:
            if attempt == SAVE_RETRY_COUNT - 1:  # Last attempt failed
                print(f"⚠️ Corrupted JSON in {path}, restoring from backup if available")
                # Try backup
                backup_path = path + ".backup"
                if os.path.exists(backup_path):
                    try:
                        with open(backup_path, "r") as f:
                            return json.load(f)
                    except:
                        return default
                return default
            time.sleep(0.1)  # Brief delay before retry
        except Exception as e:
            if attempt == SAVE_RETRY_COUNT - 1:
                print(f"⚠️ Failed to load {path}: {e}")
                return default
            time.sleep(0.1)
    return default

def atomic_save_json(path, data):
    """Save JSON file atomically to prevent corruption"""
    for attempt in range(SAVE_RETRY_COUNT):
        try:
            # Create backup first
            if os.path.exists(path):
                try:
                    import shutil
                    shutil.copy2(path, path + ".backup")
                except:
                    pass
            
            # Save to temp file first
            temp_file = path + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            
            # Atomic replace
            os.replace(temp_file, path)
            return True
            
        except Exception as e:
            if attempt == SAVE_RETRY_COUNT - 1:  # Last attempt
                print(f"⚠️ Failed to save {path} after {SAVE_RETRY_COUNT} attempts: {e}")
                # Clean up temp file
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
                return False
            time.sleep(0.2)  # Delay before retry
    return False

def save_json(path, data):
    """Wrapper for atomic save"""
    return atomic_save_json(path, data)

# 🆕 Load join tracking
def load_join_tracking():
    return load_json(JOIN_TRACKING_FILE, {})

def save_join_tracking(data):
    return atomic_save_json(JOIN_TRACKING_FILE, data)

# -----------------------
# 🛡️ SAFE MESSAGE CLEANUP HELPERS
# -----------------------
async def safe_delete_message(channel, msg_id, max_retries=MAX_CLEANUP_RETRIES):
    """Safely delete a single message with retry logic"""
    if not channel or not msg_id:
        return False
    
    # Validate message ID
    try:
        msg_id_int = int(msg_id)
    except (ValueError, TypeError):
        print(f"⚠️ Invalid message ID format: {msg_id}")
        return False
    
    for attempt in range(max_retries):
        try:
            msg = await channel.fetch_message(msg_id_int)
            
            # Safety check: only delete bot's own messages
            if msg.author.id != client.user.id:
                print(f"⚠️ Won't delete message {msg_id} - not from bot (author: {msg.author.id})")
                return False
                
            await msg.delete()
            return True
            
        except discord.NotFound:
            # Message already deleted - this is OK
            return True
        except discord.Forbidden:
            print(f"⚠️ No permission to delete message {msg_id} in #{channel.name}")
            return False
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                wait_time = (2 ** attempt) + 1  # Exponential backoff
                print(f"⏰ Rate limited deleting message {msg_id}, waiting {wait_time}s...")
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
    """Safely clean up messages by their IDs with comprehensive error handling"""
    if not CLEANUP_ENABLED or not channel or not message_ids:
        return 0
    
    # Remove duplicates and invalid IDs
    unique_ids = []
    seen = set()
    for msg_id in message_ids:
        if msg_id and msg_id not in seen:
            try:
                int(msg_id)  # Validate it's a number
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
        
        # Rate limiting between deletions
        if i < len(unique_ids) - 1:  # Not the last one
            await asyncio.sleep(CLEANUP_RATE_LIMIT)
    
    return deleted_count

async def safe_cleanup_recruit_messages(uid, recruit_ch):
    """Safely clean up all messages related to a recruit with transaction-like safety"""
    if not CLEANUP_ENABLED or uid not in pending_recruits or not recruit_ch:
        return 0
    
    try:
        # 🛡️ Get message IDs BEFORE attempting deletion
        message_ids = []
        entry = pending_recruits[uid]
        
        # Collect all message IDs to delete
        for key in ["welcome_msg", "announce", "pause_msg"]:
            msg_id = entry.get(key)
            if msg_id:
                message_ids.append(msg_id)
        
        if not message_ids:
            return 0
        
        # 🛡️ Attempt cleanup
        deleted = await safe_cleanup_messages(recruit_ch, message_ids)
        
        if deleted > 0:
            print(f"✅ Successfully deleted {deleted}/{len(message_ids)} messages for recruit {uid}")
        
        # 🛡️ Clear message IDs from entry even if some failed
        # This prevents repeated attempts on same messages
        if uid in pending_recruits:
            pending_recruits[uid]["welcome_msg"] = None
            pending_recruits[uid]["announce"] = None
            pending_recruits[uid]["pause_msg"] = None
            # Don't save here - let caller handle saving
        
        return deleted
        
    except Exception as e:
        print(f"⚠️ Critical error in cleanup for recruit {uid}: {e}")
        # 🛡️ DON'T crash - log error and continue
        log_error("SAFE_CLEANUP", f"Failed cleanup for {uid}: {e}")
        return 0

# -----------------------
# NEW: CLEANUP FUNCTION FOR STUCK RECRUITS
# -----------------------
def cleanup_stuck_recruits():
    """Clean up stuck recruits from previous runs"""
    try:
        stuck_cleaned = 0
        now = int(time.time())
        for uid, entry in list(pending_recruits.items()):
            # Remove entries older than 24 hours
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
# EVENTS WITH DEBUGGING & STABILITY
# -----------------------
@client.event
async def on_ready():
    try:
        print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Bot is READY! Logged in as {client.user}")
        print(f"⚙️  Cleanup feature: {'ENABLED' if CLEANUP_ENABLED else 'DISABLED'}")
        
        global state, pending_recruits, member_join_tracking, safety_wrappers
        state = load_json(STATE_FILE, state)
        pending_recruits = load_json(PENDING_FILE, pending_recruits)
        member_join_tracking = load_join_tracking()  # 🆕 Load persistent tracking
        
        # Initialize safety wrappers
        safety_wrappers = SafetyWrappers(client)
        
        # 🆕 Clean up stuck recruits from previous runs
        cleanup_stuck_recruits()
        
        print(f"📊 [{datetime.now().strftime('%H:%M:%S')}] Loaded state: {len(pending_recruits)} pending recruits")
        print(f"📈 [{datetime.now().strftime('%H:%M:%S')}] Loaded tracking: {len(member_join_tracking)} members tracked")
        
        # Start background tasks
        client.loop.create_task(safe_inactivity_checker())
        client.loop.create_task(weekly_role_checker())  # 🆕 Start weekly checker
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Background tasks started")
        
    except Exception as e:
        log_error("ON_READY", e)
        raise

@client.event
async def on_connect():
    print(f"🔗 [{datetime.now().strftime('%H:%M:%S')}] Bot connected to Discord")

@client.event
async def on_disconnect():
    print(f"🔌 [{datetime.now().strftime('%H:%M:%S')}] Bot disconnected")

@client.event
async def on_resumed():
    print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Bot session resumed")

@client.event
async def on_error(event, *args, **kwargs):
    print(f"💥 Error in {event}: {args} {kwargs}")
    traceback.print_exc()

@client.event
async def on_member_join(member):
    try:
        # COOLDOWN CHECK - Prevent duplicate events
        current_time = time.time()
        member_id = str(member.id)
        
        if member_id in recent_joins:
            # If member joined less than 30 seconds ago, ignore this event
            if current_time - recent_joins[member_id] < 30:
                print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] Ignoring duplicate join event for {member.display_name}")
                return
        
        # Update cooldown
        recent_joins[member_id] = current_time
        
        print(f"👤 [{datetime.now().strftime('%H:%M:%S')}] Member joined: {member.display_name}")
        
        recruit_ch = client.get_channel(CHANNELS["recruit"])
        staff_ch = client.get_channel(CHANNELS["staff_review"])

        # Check if this user is already being processed
        uid = str(member.id)
        if uid in pending_recruits and pending_recruits[uid].get("started", 0) > current_time - 300:  # 5 minutes
            print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Member {member.display_name} already in pending, skipping")
            return

        # 🛡️ Store message IDs for cleanup
        welcome_msg_id = None
        notice_msg_id = None
        pause_msg_id = None

        # welcome (best-effort) - ONLY ONCE
        welcome_sent = False
        try:
            if recruit_ch:
                welcome_msg = await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Imperius!")
                welcome_msg_id = welcome_msg.id
                welcome_sent = True
        except Exception as e:
            print(f"⚠️ Failed to send welcome: {e}")

        # public notice to be deleted later - ONLY ONCE
        try:
            if recruit_ch:
                notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
                notice_msg_id = notice.id
        except Exception as e:
            print(f"⚠️ Failed to send notice: {e}")

        # Initialize pending recruit WITH MESSAGE IDs
        pending_recruits[uid] = {
            "started": int(current_time),
            "last": int(current_time),
            "answers": [],
            "announce": notice_msg_id,
            "welcome_msg": welcome_msg_id,
            "pause_msg": None,  # Will be set if DM fails
            "under_review": False,
            "review_message_id": None,
            "resolved": False,
            "additional_info": {},
            "welcome_sent": welcome_sent,
            "dm_failed_reason": None
        }
        save_json(PENDING_FILE, pending_recruits)

        # 🆕 ENHANCED: Track ALL member joins (for long-term monitoring)
        member_join_tracking[uid] = {
            "joined_at": int(current_time),
            "username": member.name,
            "display_name": member.display_name,
            "has_roles": False,  # Will be updated when roles are assigned
            "last_checked": int(current_time),
            "status": "pending_verification",
            "verification_attempts": 1,
            "dm_success": False,  # Updated based on DM flow
            "notes": [f"Joined server at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
        }
        save_join_tracking(member_join_tracking)
        
        print(f"📝 [{datetime.now().strftime('%H:%M:%S')}] Added {member.display_name} to long-term tracking")

        # NEW ENHANCED DM FLOW - UPDATED QUESTIONS
        try:
            dm = await member.create_dm()
            
            # Send initial DM with new questions
            embed = discord.Embed(
                title="🎮 Impèrius Clan Recruitment",
                description="Welcome to Impèrius! Please answer the following questions to apply for tryouts.\nYou have 5 minutes to answer each question.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Type 'cancel' at any time to stop the application")
            
            await dm.send(embed=embed)
            await asyncio.sleep(2)
            
            # Ask the updated questions
            for i, question in enumerate(RECRUIT_QUESTIONS):
                await dm.send(f"**Question {i+1}/{len(RECRUIT_QUESTIONS)}**\n{question}")
                
                try:
                    reply = await client.wait_for(
                        "message",
                        timeout=300.0,
                        check=lambda m: m.author.id == member.id and m.channel.id == dm.id
                    )
                    
                    # Check for cancellation
                    if reply.content.lower() == 'cancel':
                        await dm.send("❌ Application cancelled.")
                        
                        # Clean up messages
                        if CLEANUP_ENABLED and recruit_ch:
                            await safe_cleanup_recruit_messages(uid, recruit_ch)
                        
                        # Remove from pending
                        if uid in pending_recruits:
                            del pending_recruits[uid]
                            save_json(PENDING_FILE, pending_recruits)
                        
                        return
                    
                    pending_recruits[uid]["answers"].append(reply.content.strip())
                    pending_recruits[uid]["last"] = int(time.time())
                    save_json(PENDING_FILE, pending_recruits)
                    
                    # Update tracking
                    member_join_tracking[uid]["dm_success"] = True
                    member_join_tracking[uid]["notes"].append(f"Answered question {i+1}")
                    save_join_tracking(member_join_tracking)
                    
                except asyncio.TimeoutError:
                    await dm.send("⏰ Timeout! You took too long to respond. Application cancelled.")
                    
                    # Update tracking
                    member_join_tracking[uid]["status"] = "timed_out"
                    member_join_tracking[uid]["last_checked"] = int(time.time())
                    member_join_tracking[uid]["notes"].append("Timed out during interview")
                    save_join_tracking(member_join_tracking)
                    
                    # Send to admin channel for review
                    if staff_ch:
                        embed = discord.Embed(
                            title="⚠️ Recruit Timed Out",
                            description=f"{member.mention} timed out during DM interview.",
                            color=discord.Color.orange()
                        )
                        await staff_ch.send(embed=embed)
                    
                    return

            # All questions answered successfully
            await dm.send("✅ Thank you! Your answers have been submitted for review. The admins will review your application soon.")
            
            # 🛡️ DELETE ALL RECRUIT CHANNEL MESSAGES
            if CLEANUP_ENABLED and recruit_ch:
                deleted = await safe_cleanup_recruit_messages(uid, recruit_ch)
                if deleted > 0:
                    print(f"✅ Cleaned up {deleted} messages for {member.display_name}")
                save_json(PENDING_FILE, pending_recruits)

            # Send formatted answers to admin review channel with voting system
            try:
                if staff_ch:
                    # Format answers
                    formatted = ""
                    for i, (question, answer) in enumerate(zip(RECRUIT_QUESTIONS, pending_recruits[uid]["answers"])):
                        short_q = question.split('\n')[0][:100] + "..."
                        formatted += f"**Q{i+1}:** {short_q}\n**A:** {answer[:500]}\n\n"
                    
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    
                    # Create voting embed
                    embed = discord.Embed(
                        title=":military_helmet: Cadet on tryout process",
                        description=f"**Applicant:** {member.mention} ({member.id})\n\n**Answers:**\n{formatted}",
                        color=discord.Color.gold(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    # Add voting instructions
                    voting_text = (
                        f"**Vote:**\n"
                        f"{UPVOTE_EMOJI} = User passed tryout (Grant 'Impèrius🔥' role)\n"
                        f"{DOWNVOTE_EMOJI} = User did not pass (Kick from server)\n"
                        f"{CLOCK_EMOJI} = Conditional process (Keep without roles)"
                    )
                    
                    embed.add_field(name="Decision", value=voting_text, inline=False)
                    embed.set_footer(text=f"Submitted: {now_str}")
                    embed.set_thumbnail(url=member.display_avatar.url if member.avatar else member.default_avatar.url)
                    
                    # Send to admin channel
                    review_msg = await staff_ch.send(embed=embed)
                    
                    # Add voting reactions
                    await review_msg.add_reaction(UPVOTE_EMOJI)
                    await review_msg.add_reaction(DOWNVOTE_EMOJI)
                    await review_msg.add_reaction(CLOCK_EMOJI)
                    
                    # Update pending record
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    save_json(PENDING_FILE, pending_recruits)
                    
            except Exception as e:
                print(f"⚠️ Failed to post to admin channel: {e}")
                
        except discord.Forbidden:
            # DM failed - user blocked DMs
            print(f"⚠️ Could not DM {member.display_name}: DMs blocked")
            
            # Update tracking
            member_join_tracking[uid]["status"] = "dm_failed"
            member_join_tracking[uid]["last_checked"] = int(time.time())
            member_join_tracking[uid]["notes"].append("User blocked DMs")
            save_join_tracking(member_join_tracking)
            
            try:
                if recruit_ch:
                    # Send pause message
                    pause_msg = await recruit_ch.send(f"⚠️ {member.mention} verification paused. Admins will review manually.")
                    pending_recruits[uid]["pause_msg"] = pause_msg.id
                    save_json(PENDING_FILE, pending_recruits)
                    
            except Exception as pause_error:
                print(f"⚠️ Failed to send pause message: {pause_error}")
            
            try:
                if staff_ch:
                    # Create failed DM review message
                    embed = discord.Embed(
                        title=":military_helmet: Cadet failed to respond (DMs blocked)",
                        description=f"**Applicant:** {member.mention} ({member.id})\n**Status:** User blocked DMs or didn't respond\n\n",
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
                    
                    # Add voting reactions
                    await review_msg.add_reaction(UPVOTE_EMOJI)
                    await review_msg.add_reaction(DOWNVOTE_EMOJI)
                    await review_msg.add_reaction(CLOCK_EMOJI)
                    
                    # Update pending record
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    pending_recruits[uid]["dm_failed_reason"] = "DMs blocked"
                    save_json(PENDING_FILE, pending_recruits)
                    
            except Exception as e:
                print(f"⚠️ Failed to create admin review post for DM-blocked recruit: {e}")
                
        except Exception as e:
            # Other DM error
            print(f"⚠️ Could not complete DM flow for {member.display_name}: {e}")
            
            # Update tracking
            member_join_tracking[uid]["status"] = "dm_failed"
            member_join_tracking[uid]["last_checked"] = int(time.time())
            member_join_tracking[uid]["notes"].append(f"DM error: {str(e)[:100]}")
            save_join_tracking(member_join_tracking)
            
            # Still send to admin channel for review
            if staff_ch:
                try:
                    embed = discord.Embed(
                        title=":military_helmet: Cadet - DM Error",
                        description=f"**Applicant:** {member.mention} ({member.id})\n**Error:** {str(e)[:200]}\n\n",
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
                    
                    # Add voting reactions
                    await review_msg.add_reaction(UPVOTE_EMOJI)
                    await review_msg.add_reaction(DOWNVOTE_EMOJI)
                    await review_msg.add_reaction(CLOCK_EMOJI)
                    
                    # Update pending record
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    pending_recruits[uid]["dm_failed_reason"] = str(e)[:100]
                    save_json(PENDING_FILE, pending_recruits)
                    
                except Exception as e2:
                    print(f"⚠️ Failed to create error review post: {e2}")
                
    except Exception as e:
        log_error("ON_MEMBER_JOIN", e)

@client.event
async def on_message(message):
    try:
        if message.author.id == client.user.id:
            return

        # Check for admin verification command
        if message.content.startswith("!verify"):
            # Check if author is admin
            if not safety_wrappers or not safety_wrappers.is_admin(message.author):
                await message.channel.send("❌ You don't have permission to use this command.")
                return
                
            # Extract user mention
            if len(message.mentions) > 0:
                member = message.mentions[0]
                uid = str(member.id)
                
                if uid in pending_recruits and pending_recruits[uid].get("under_review"):
                    try:
                        dm = await member.create_dm()
                        await dm.send("🪖 An admin has requested manual verification. Please answer:")
                        await dm.send(RECRUIT_QUESTIONS[0])
                        
                        # Store that manual verification started
                        pending_recruits[uid]["manual_verify_started"] = time.time()
                        save_json(PENDING_FILE, pending_recruits)
                        
                        # Update tracking
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

        # Reminder channel message counting
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

@client.event
async def on_presence_update(before, after):
    try:
        # ✅ FIXED: Global declaration at the VERY BEGINNING
        global presence_cooldown
        
        # Rate limiting - check if user is on cooldown
        current_time = time.time()
        user_id = after.id
        
        if user_id in presence_cooldown:
            if current_time - presence_cooldown[user_id] < PRESENCE_COOLDOWN_TIME:
                # User is on cooldown, skip this update
                return
        
        # Only announce when coming from offline to online/idle/dnd
        if before.status != after.status:
            # Only announce when going from offline to online/idle/dnd
            if str(before.status) == "offline" and str(after.status) in ["online", "idle", "dnd"]:
                m = after
                ids = [r.id for r in m.roles]
                ch = client.get_channel(CHANNELS["main"])
                
                if not ch:
                    return
                
                # Check roles and send appropriate message
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
                
                # Add small delay to prevent rate limits
                await asyncio.sleep(0.5)
                
                try:
                    await ch.send(embed=embed)
                    # Update cooldown
                    presence_cooldown[user_id] = current_time
                    
                    # Clean up old cooldown entries periodically
                    if len(presence_cooldown) > 1000:  # Prevent memory leak
                        old_time = current_time - PRESENCE_COOLDOWN_TIME
                        presence_cooldown = {k: v for k, v in presence_cooldown.items() if v > old_time}
                        
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] Rate limited on presence update, backing off...")
                        # Increase cooldown when rate limited
                        presence_cooldown[user_id] = current_time + 60  # Add extra minute
                        await asyncio.sleep(5)  # Wait before trying again
                    else:
                        log_error("ON_PRESENCE_UPDATE", e)
                except Exception as e:
                    log_error("ON_PRESENCE_UPDATE", e)
    except Exception as e:
        log_error("ON_PRESENCE_UPDATE", e)

@client.event
async def on_raw_reaction_add(payload):
    try:
        if payload.user_id == client.user.id:
            return
            
        msg_id = payload.message_id
        uid = None
        entry = None
        
        # Find which entry this reaction belongs to
        for k, v in pending_recruits.items():
            if v.get("review_message_id") == msg_id and not v.get("resolved") and v.get("under_review"):
                uid = k
                entry = v
                break
        
        if not uid or not entry:
            return

        # Get emoji string
        emoji_str = str(payload.emoji)
        
        # Only accept specific vote emojis
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

        # Check if reactor has admin role using safety wrapper
        if not safety_wrappers or not safety_wrappers.is_admin(reactor):
            # Remove reaction if not authorized
            try:
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    message = await channel.fetch_message(msg_id)
                    await message.remove_reaction(payload.emoji, reactor)
            except:
                pass
            return

        if entry.get("resolved"):
            return

        # Mark as resolved immediately to prevent multiple votes
        entry["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)

        # Get the applicant member
        applicant = guild.get_member(int(uid))
        
        # Get staff channel
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        
        # Admin label for logging
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
        
        # Process based on vote
        if emoji_str == UPVOTE_EMOJI:
            # Grant Impèrius🔥 role
            if applicant:
                success, message = await safety_wrappers.assign_role_safe(
                    applicant, 
                    ROLES["imperius"], 
                    f"Passed tryout - voted by {reactor.display_name}"
                )
                
                if success:
                    # Send result message
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
                    # Send result message
                    if staff_ch:
                        result_msg = f":military_helmet: Cadet {applicant.mention} ({applicant.id}) was rejected and removed from server with the permission of: {reactor.mention}"
                        await staff_ch.send(result_msg)
                    
                    # Update tracking
                    if uid in member_join_tracking:
                        member_join_tracking[uid]["status"] = "rejected_kicked"
                        member_join_tracking[uid]["last_checked"] = int(time.time())
                        save_join_tracking(member_join_tracking)
                        
                    # Try to send DM notification
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
                # Send result message
                if staff_ch:
                    result_msg = f":military_helmet: Cadet {applicant.mention} ({applicant.id}) was conditional and will remain in this server until the admins final decisions ⚖️ by: {reactor.mention}"
                    await staff_ch.send(result_msg)
                
                # Update tracking
                if uid in member_join_tracking:
                    member_join_tracking[uid]["status"] = "conditional"
                    member_join_tracking[uid]["last_checked"] = int(time.time())
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
        
        # 🛡️ CLEAN UP RECRUIT CHANNEL MESSAGES
        recruit_ch = client.get_channel(CHANNELS["recruit"])
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

# -----------------------
# SAFE INACTIVITY CHECKER WITH MEMORY CLEANUP
# -----------------------
async def safe_inactivity_checker():
    await client.wait_until_ready()
    cleanup_counter = 0
    while not client.is_closed():
        try:
            now = int(time.time())
            cleanup_counter += 1
            
            # 🆕 Periodic cleanup of old entries (every 10 minutes) - WITH BETTER ERROR HANDLING
            if cleanup_counter % 30 == 0:  # 30 * 20 seconds = 10 minutes
                try:
                    stuck_cleaned = 0
                    entries_to_remove = []
                    
                    # First, identify entries to remove (don't modify while iterating)
                    for uid, entry in pending_recruits.items():
                        started = entry.get("started", now)
                        if not entry.get("under_review") and now - started > 10800:  # 3 hours
                            entries_to_remove.append(uid)
                    
                    # Then remove them
                    for uid in entries_to_remove:
                        del pending_recruits[uid]
                        stuck_cleaned += 1
                        
                    if stuck_cleaned > 0:
                        print(f"🧹 Cleaned up {stuck_cleaned} old pending recruits")
                        save_json(PENDING_FILE, pending_recruits)
                            
                except Exception as e:
                    log_error("PERIODIC_CLEANUP", e)
            
            # Clean up old recent_joins to prevent memory leaks
            global recent_joins, presence_cooldown  # ✅ FIXED: Both declared together
            
            # Clean up old presence cooldown entries
            old_time = now - PRESENCE_COOLDOWN_TIME
            presence_cooldown = {k: v for k, v in presence_cooldown.items() if v > old_time}
            
            # Check for recruits pending >24 hours (STUCK RECRUITS)
            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                    
                started = entry.get("started", now)
                # If pending for 24+ hours and NOT under review
                if now - started >= 86400:  # 24 hours
                    print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] Found recruit pending >24 hours: {uid}")
                    
                    staff_ch = client.get_channel(CHANNELS["staff_review"])
                    if staff_ch:
                        # Get member info
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
                        
                        # Create urgent alert for admins with new voting system
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
                            
                            # Mark as under review to prevent duplicate alerts
                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            entry["is_24h_alert"] = True
                            save_json(PENDING_FILE, pending_recruits)
                            
                            print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Sent 24h alert for recruit {uid}")
                            
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
                            # Create voting embed for inactive recruits
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
            await asyncio.sleep(60)

# -----------------------
# 🆕 WEEKLY ROLE CHECKER FOR GHOST MEMBERS (SIMPLIFIED REACTION-BASED)
# -----------------------
async def weekly_role_checker():
    """Check weekly for members without roles who joined >7 days ago"""
    await client.wait_until_ready()
    
    # Run every 24 hours
    while not client.is_closed():
        try:
            await asyncio.sleep(24 * 3600)  # 24 hours
            
            now = int(time.time())
            print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Running weekly role check...")
            
            guild = None
            for g in client.guilds:
                guild = g
                break
            
            if not guild:
                continue
            
            # Get staff channel
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
            
            # Find members without clan roles who joined >7 days ago
            old_members_without_roles = []
            
            async for member in guild.fetch_members(limit=None):
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
                if not has_clan_role:
                    joined_at = member.joined_at
                    if joined_at:
                        days_since_join = (datetime.now(timezone.utc) - joined_at).days
                        if days_since_join >= 7:  # 7+ days old
                            old_members_without_roles.append({
                                "member": member,
                                "days_since_join": days_since_join,
                                "join_date": joined_at.strftime("%Y-%m-%d"),
                                "tracking_data": member_join_tracking.get(str(member.id), {})
                            })
            
            if old_members_without_roles:
                print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] Found {len(old_members_without_roles)} members >7 days old without roles!")
                
                # Group members into batches of 10 (Discord embed limits)
                for batch_num in range(0, len(old_members_without_roles), 10):
                    batch = old_members_without_roles[batch_num:batch_num + 10]
                    
                    # Create alert embed for this batch
                    embed = discord.Embed(
                        title=f"🚨 WEEKLY CLEANUP ALERT (Batch {batch_num//10 + 1})",
                        description=f"**Found {len(batch)} member(s) in server for 7+ days WITHOUT CLAN ROLES**\n\n"
                                  f"These members likely never completed verification.",
                        color=0xff0000,
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    # Add each member in batch
                    for i, data in enumerate(batch):
                        member = data["member"]
                        embed.add_field(
                            name=f"{i+1}. {member.display_name}",
                            value=f"**Joined:** {data['days_since_join']} days ago\n**ID:** `{member.id}`\n**Mention:** {member.mention}",
                            inline=False
                        )
                    
                    embed.add_field(
                        name="🛠️ Admin Actions",
                        value=(
                            f"**React with:**\n"
                            f"• {UPVOTE_EMOJI} = Kick all members in this batch\n"
                            f"• {DOWNVOTE_EMOJI} = Pardon all members (grant Impèrius🔥 role)\n"
                            f"• {CLOCK_EMOJI} = Mark as reviewed (no action)\n\n"
                            "*(Only admins with special roles may decide.)*"
                        ),
                        inline=False
                    )
                    
                    # Send alert with reactions
                    alert_msg = await staff_ch.send(embed=embed)
                    await alert_msg.add_reaction(UPVOTE_EMOJI)
                    await alert_msg.add_reaction(DOWNVOTE_EMOJI)
                    await alert_msg.add_reaction(CLOCK_EMOJI)
                    
                    # Store batch info for reaction handling
                    for i, data in enumerate(batch):
                        member_id = str(data["member"].id)
                        if member_id not in pending_recruits:
                            pending_recruits[member_id] = {
                                "started": int(time.time()),
                                "under_review": True,
                                "review_message_id": alert_msg.id,
                                "is_weekly_cleanup": True,
                                "batch_number": batch_num // 10 + 1,
                                "member_info": {
                                    "display_name": data["member"].display_name,
                                    "days_since_join": data["days_since_join"]
                                }
                            }
                    
                    save_json(PENDING_FILE, pending_recruits)
                    
            else:
                print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] No members >7 days old without roles")
                
        except Exception as e:
            log_error("WEEKLY_ROLE_CHECKER", e)
            await asyncio.sleep(3600)  # Wait 1 hour on error

# -----------------------
# SUPERVISED STARTUP
# -----------------------
def run_bot_forever():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ No token!")
        return

    restart_count = 0
    while restart_count < 20:
        try:
            print(f"🚀 Starting bot (attempt {restart_count + 1})...")
            print(f"⚙️  Cleanup feature: {'ENABLED' if CLEANUP_ENABLED else 'DISABLED'}")
            client.run(token, reconnect=True)
        except Exception as e:
            restart_count += 1
            log_error("BOT_STARTUP", e)
            print(f"🔄 Restarting in 15 seconds...")
            time.sleep(15)
    
    print("💀 Too many restarts. Giving up.")

# -----------------------
# START - SIMPLE & STABLE (BOT IN MAIN THREAD)
# -----------------------
if __name__ == "__main__":
    print("🎯 Starting bot (MAIN THREAD)...")
    print(f"🔧 Python version: {sys.version}")
    print(f"🔧 Discord.py version: {discord.__version__}")
    
    # Start Flask in background thread
    def start_flask():
        port = int(os.environ.get("PORT", 8080))
        print(f"🌐 Starting Flask server on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask server started in background")
    
    # Start pinger
    threading.Thread(target=ping_self, daemon=True).start()
    print("✅ Self-pinger started")
    
    # Start bot in MAIN THREAD (this blocks - Render will restart if bot crashes)
    print("🤖 Starting Discord bot in main thread...")
    run_bot_forever()
