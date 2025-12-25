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
    "imperius": 1437570031822176408,
    "imperius_star": "Imperius🔥"
}

REMINDER_THRESHOLD = 50
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"
JOIN_TRACKING_FILE = "member_join_tracking.json"  # 🆕 Persistent tracking

RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Imperius Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ We require at least **Major 🎖 rank**. Are you Major First Class or above?",
    "4️⃣ Is the account you're using to apply your main account?",
    "5️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

REMINDERS = [
    {"title": "🟢 Activity Reminder", "description": "Members must keep their status set only to \"Online\" while active."},
    {"title": "🧩 IGN Format", "description": "All members must use the official clan format: IM-(Your IGN)."},
    {"title": "🔊 Voice Channel Reminder", "description": "Members online must join the Public Call channel."}
]

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
# LOAD/SAVE
# -----------------------
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"⚠️ Save failed: {e}")

# 🆕 Load join tracking
def load_join_tracking():
    return load_json(JOIN_TRACKING_FILE, {})

def save_join_tracking(data):
    save_json(JOIN_TRACKING_FILE, data)

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
        global state, pending_recruits, member_join_tracking
        state = load_json(STATE_FILE, state)
        pending_recruits = load_json(PENDING_FILE, pending_recruits)
        member_join_tracking = load_join_tracking()  # 🆕 Load persistent tracking
        
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

        # welcome (best-effort) - ONLY ONCE
        welcome_sent = False
        try:
            if recruit_ch:
                await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Imperius!")
                welcome_sent = True
        except Exception as e:
            print(f"⚠️ Failed to send welcome: {e}")

        # public notice to be deleted later - ONLY ONCE
        notice_id = None
        try:
            if recruit_ch:
                notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
                notice_id = notice.id
        except Exception as e:
            print(f"⚠️ Failed to send notice: {e}")

        # Initialize pending recruit
        pending_recruits[uid] = {
            "started": int(current_time),
            "last": int(current_time),
            "answers": [],
            "announce": notice_id,
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

        # NEW ENHANCED DM FLOW - NO DUPLICATES
        try:
            dm = await member.create_dm()
            await dm.send("🪖 Welcome to Imperius! Please answer the verification questions one by one:")
            
            additional_info = {
                "is_former_member": False,
                "former_reason": None,
                "is_current_member": False,
                "ign": None
            }
            
            # Question 1: Former member check
            await dm.send("**Are you a former member of our clan?** (yes/no)")
            former_member_msg = await client.wait_for(
                "message",
                timeout=300.0,
                check=lambda m: m.author.id == member.id and m.channel.id == dm.id
            )
            former_member_response = former_member_msg.content.lower()
            
            # If former member, ask reason and notify admins, then skip current member question
            if former_member_response in ['yes', 'y']:
                additional_info["is_former_member"] = True
                await dm.send("**What was the reason for leaving the clan previously?**")
                reason_msg = await client.wait_for(
                    "message",
                    timeout=300.0,
                    check=lambda m: m.author.id == member.id and m.channel.id == dm.id
                )
                additional_info["former_reason"] = reason_msg.content
                
                # Post to admin channel for former member info
                if staff_ch:
                    embed = discord.Embed(
                        title="🪖 Former Member Info",
                        description=f"**{member.display_name}** (`{member.name}`) claimed to be a former member of the clan.\n\nThe user stated that: {additional_info['former_reason']}",
                        color=0xffa500
                    )
                    await staff_ch.send(embed=embed)
                
                # Skip the "current member" question and proceed to regular questions
                await dm.send("✅ I have sent your statement to the admins of Imperius, please wait for their response.")
                
                # Update pending_recruits with additional info
                pending_recruits[uid]["additional_info"] = additional_info
                pending_recruits[uid]["last"] = int(time.time())
                save_json(PENDING_FILE, pending_recruits)
                
                # Update tracking
                member_join_tracking[uid]["dm_success"] = True
                member_join_tracking[uid]["notes"].append("Responded to DM: Former member check")
                save_join_tracking(member_join_tracking)
                
                # Proceed with regular questions for former members
                await dm.send("**Now proceeding with regular recruitment questions:**")
                
                for q in RECRUIT_QUESTIONS:
                    await dm.send(q)
                    try:
                        reply = await client.wait_for(
                            "message",
                            timeout=600,
                            check=lambda m: m.author.id == member.id and m.channel.id == dm.id
                        )
                    except asyncio.TimeoutError:
                        pending_recruits[uid]["last"] = int(time.time())
                        save_json(PENDING_FILE, pending_recruits)
                        
                        # Update tracking
                        member_join_tracking[uid]["status"] = "timed_out"
                        member_join_tracking[uid]["last_checked"] = int(time.time())
                        member_join_tracking[uid]["notes"].append("Timed out during interview")
                        save_join_tracking(member_join_tracking)
                        
                        try:
                            await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                        except Exception:
                            pass
                        print(f"⌛ Recruit {member.display_name} timed out during interview.")
                        return

                    pending_recruits[uid]["answers"].append(reply.content.strip())
                    pending_recruits[uid]["last"] = int(time.time())
                    save_json(PENDING_FILE, pending_recruits)
                    
                    # Update tracking
                    member_join_tracking[uid]["notes"].append(f"Answered question: {q[:50]}...")
                    save_join_tracking(member_join_tracking)

                # Completed regular questions
                try:
                    await dm.send("✅ Thank you! Your answers will be reviewed by the admins. Please wait for further instructions.")
                except Exception:
                    pass

                # delete announce message
                try:
                    if notice_id and recruit_ch:
                        msg = await recruit_ch.fetch_message(notice_id)
                        await msg.delete()
                except Exception:
                    pass

                # Send formatted answers to admin review channel for record
                try:
                    if staff_ch:
                        labels = [
                            "Purpose of joining:",
                            "Invited by an Imperius member, and who:",
                            "At least Major rank:",
                            "Is the account you're using to apply your main account:",
                            "Willing to CCN:"
                        ]
                        formatted = ""
                        answers = pending_recruits[uid]["answers"]
                        for i, ans in enumerate(answers):
                            label = labels[i] if i < len(labels) else f"Question {i+1}:"
                            formatted += f"**{label}**\n{ans}\n\n"
                        
                        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        embed = discord.Embed(
                            title=f"🪖 Recruit {member.display_name} for approval.",
                            description=f"{formatted}📅 **Date answered:** `{now_str}`",
                            color=discord.Color.blurple()
                        )
                        await staff_ch.send(embed=embed)
                except Exception:
                    pass

                # resolved (remove pending) - ADD PROPER CLEANUP AND RETURN
                try:
                    if uid in pending_recruits:
                        del pending_recruits[uid]
                        save_json(PENDING_FILE, pending_recruits)
                except Exception:
                    pass
                
                return  # Exit the function for former members

            # If NOT a former member, proceed to current member check
            # Question 2: Current member check  
            await dm.send("**Are you currently a member of Imperius?** (yes/no)")
            current_member_msg = await client.wait_for(
                "message",
                timeout=300.0,
                check=lambda m: m.author.id == member.id and m.channel.id == dm.id
            )
            current_member_response = current_member_msg.content.lower()
            
            # Update pending_recruits with additional info
            pending_recruits[uid]["additional_info"] = additional_info
            pending_recruits[uid]["last"] = int(time.time())
            save_json(PENDING_FILE, pending_recruits)
            
            # Update tracking
            member_join_tracking[uid]["dm_success"] = True
            member_join_tracking[uid]["notes"].append("Responded to DM: Current member check")
            save_join_tracking(member_join_tracking)
            
            # If current member, ask for IGN and start verification process
            if current_member_response in ['yes', 'y']:
                additional_info["is_current_member"] = True
                await dm.send("**Please provide your in-game name (IGN) for verification:**")
                ign_msg = await client.wait_for(
                    "message",
                    timeout=300.0,
                    check=lambda m: m.author.id == member.id and m.channel.id == dm.id
                )
                additional_info["ign"] = ign_msg.content
                
                pending_recruits[uid]["additional_info"] = additional_info
                pending_recruits[uid]["last"] = int(time.time())
                save_json(PENDING_FILE, pending_recruits)
                
                # Update tracking
                member_join_tracking[uid]["notes"].append(f"Claimed to be current member. IGN: {additional_info['ign']}")
                save_join_tracking(member_join_tracking)
                
                # Post to admin channel for member verification
                if staff_ch:
                    embed = discord.Embed(
                        title="🪖 Member Access Request",
                        description=f"**{member.display_name}** stated that he/she is a member and would like to gain full access in this server as a member.",
                        color=0x00ff00
                    )
                    embed.add_field(name="In-Game Name", value=additional_info["ign"], inline=False)
                    embed.add_field(name="Status", value="Awaiting verification", inline=True)
                    
                    verification_msg = await staff_ch.send(embed=embed)
                    await verification_msg.add_reaction("👍")
                    await verification_msg.add_reaction("👎")
                    
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = verification_msg.id
                    save_json(PENDING_FILE, pending_recruits)
                    
                    await dm.send("✅ Your membership verification has been sent to admins. Please wait for approval.")
                    
                # Skip remaining questions for current members
                # Delete announce message
                try:
                    if notice_id and recruit_ch:
                        msg = await recruit_ch.fetch_message(notice_id)
                        await msg.delete()
                except Exception:
                    pass
                return

            # If NOT a current member AND NOT a former member, proceed with original 5 questions
            await dm.send("**Now proceeding with regular recruitment questions:**")
            
            for q in RECRUIT_QUESTIONS:
                await dm.send(q)
                try:
                    reply = await client.wait_for(
                        "message",
                        timeout=600,
                        check=lambda m: m.author.id == member.id and m.channel.id == dm.id
                    )
                except asyncio.TimeoutError:
                    pending_recruits[uid]["last"] = int(time.time())
                    save_json(PENDING_FILE, pending_recruits)
                    
                    # Update tracking
                    member_join_tracking[uid]["status"] = "timed_out"
                    member_join_tracking[uid]["last_checked"] = int(time.time())
                    member_join_tracking[uid]["notes"].append("Timed out during interview")
                    save_join_tracking(member_join_tracking)
                    
                    try:
                        await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                    except Exception:
                        pass
                    print(f"⌛ Recruit {member.display_name} timed out during interview.")
                    return

                pending_recruits[uid]["answers"].append(reply.content.strip())
                pending_recruits[uid]["last"] = int(time.time())
                save_json(PENDING_FILE, pending_recruits)
                
                # Update tracking
                member_join_tracking[uid]["notes"].append(f"Answered question: {q[:50]}...")
                save_join_tracking(member_join_tracking)

            # Completed regular questions
            try:
                await dm.send("✅ Thank you! Your answers will be reviewed by the admins. Please wait for further instructions.")
            except Exception:
                pass

            # delete announce message
            try:
                if notice_id and recruit_ch:
                    msg = await recruit_ch.fetch_message(notice_id)
                    await msg.delete()
            except Exception:
                pass

            # Send formatted answers to admin review channel for record
            try:
                if staff_ch:
                    labels = [
                        "Purpose of joining:",
                        "Invited by an Imperius member, and who:",
                        "At least Major rank:",
                        "Is the account you're using to apply your main account:",
                        "Willing to CCN:"
                    ]
                    formatted = ""
                    answers = pending_recruits[uid]["answers"]
                    for i, ans in enumerate(answers):
                        label = labels[i] if i < len(labels) else f"Question {i+1}:"
                        formatted += f"**{label}**\n{ans}\n\n"
                    
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    embed = discord.Embed(
                        title=f"🪖 Recruit {member.display_name} for approval.",
                        description=f"{formatted}📅 **Date answered:** `{now_str}`",
                        color=discord.Color.blurple()
                    )
                    await staff_ch.send(embed=embed)
            except Exception:
                pass

            # resolved (remove pending) - ADD PROPER CLEANUP AND RETURN
            try:
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_json(PENDING_FILE, pending_recruits)
            except Exception:
                pass
            
            return  # 🆕 ADD THIS RETURN STATEMENT

        except Exception as e:
            # DM failed (blocked or error) - create admin review message
            print(f"⚠️ Could not complete DM flow for {member.display_name}: {e}")
            
            # Update tracking
            member_join_tracking[uid]["status"] = "dm_failed"
            member_join_tracking[uid]["last_checked"] = int(time.time())
            member_join_tracking[uid]["notes"].append(f"DM failed: {str(e)[:100]}")
            save_join_tracking(member_join_tracking)
            
            # Determine the likely reason for DM failure
            error_type = "DM Error"
            if "Cannot send messages to this user" in str(e) or "403" in str(e):
                error_type = "User blocked DMs"
            elif "timeout" in str(e).lower():
                error_type = "No response timeout"
            
            try:
                if staff_ch:
                    display_name = f"{member.display_name} (@{member.name})"
                    embed = discord.Embed(
                        title=f"🪖 Recruit {display_name} - DM Failed",
                        description=(
                            f"**Could not complete DM verification:** {error_type}\n\n"
                            "**Options:**\n"
                            "• 👍 = Kick recruit (failed verification)\n"
                            "• 👎 = Keep recruit (try manual verification)\n\n"
                            "*(Only admins with special roles may decide.)*"
                        ),
                        color=discord.Color.dark_gold()
                    )
                    # Add user info to embed
                    embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
                    embed.add_field(name="Joined", value=f"<t:{int(time.time())}:R>", inline=True)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    
                    review_msg = await staff_ch.send(embed=embed)
                    # auto-add thumb reactions
                    try:
                        await review_msg.add_reaction("👍")
                        await review_msg.add_reaction("👎")
                    except Exception:
                        pass

                    # mark under review
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = review_msg.id
                    pending_recruits[uid]["dm_failed_reason"] = error_type
                    save_json(PENDING_FILE, pending_recruits)

                # notify recruit channel with clearer message
                if recruit_ch:
                    if error_type == "User blocked DMs":
                        await recruit_ch.send(f"⚠️ {member.mention} has DMs disabled. Please enable DMs to complete verification or contact staff.")
                    else:
                        await recruit_ch.send(f"⚠️ {member.mention} verification paused. Admins will review manually.")
                    
            except Exception as e2:
                print(f"⚠️ Failed to create admin review post for DM-blocked recruit: {e2}")
                
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
            author_roles = [r.id for r in message.author.roles]
            if any(ROLES.get(k) in author_roles for k in ("queen", "clan_master", "og_imperius")):
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
        # 🆕 ADD THIS LINE - declare global variable
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

        emoji_name = getattr(payload.emoji, "name", None)
        if emoji_name not in ("👍", "👎", "⏰"):
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

        def is_admin(member):
            if not member:
                return False
            ids = [r.id for r in member.roles]
            return any(ROLES.get(k) in ids for k in ("queen", "clan_master", "og_imperius"))

        if not is_admin(reactor):
            return

        if entry.get("resolved"):
            return

        entry["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)

        # Check if this is a member verification request
        additional_info = entry.get("additional_info", {})
        is_member_verification = additional_info.get("is_current_member", False)
        
        # Check if this is a weekly cleanup batch
        is_weekly_cleanup = entry.get("is_weekly_cleanup", False)

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

        recruit_member = None
        try:
            recruit_member = guild.get_member(int(uid))
        except Exception:
            recruit_member = None

        staff_ch = client.get_channel(CHANNELS["staff_review"])

        # Handle weekly cleanup batch reactions
        if is_weekly_cleanup:
            # Find all members in this batch
            members_in_batch = []
            for batch_uid, batch_entry in pending_recruits.items():
                if batch_entry.get("review_message_id") == msg_id and batch_entry.get("is_weekly_cleanup"):
                    member = guild.get_member(int(batch_uid))
                    if member:
                        members_in_batch.append((batch_uid, member, batch_entry))
            
            if emoji_name == "👍":  # KICK all in batch
                kicked_count = 0
                for batch_uid, member, batch_entry in members_in_batch:
                    try:
                        await member.kick(reason=f"Weekly cleanup - kicked by {reactor.display_name}")
                        kicked_count += 1
                        
                        # Update tracking
                        if batch_uid in member_join_tracking:
                            member_join_tracking[batch_uid]["status"] = "kicked_weekly_cleanup"
                            member_join_tracking[batch_uid]["last_checked"] = int(time.time())
                            save_join_tracking(member_join_tracking)
                            
                        # Mark as resolved
                        batch_entry["resolved"] = True
                        
                        await asyncio.sleep(1)  # Rate limiting
                    except Exception as e:
                        print(f"Failed to kick {member.display_name}: {e}")
                
                if staff_ch:
                    await staff_ch.send(f"👢 {reactor.mention} kicked {kicked_count} members from weekly cleanup.")
                
            elif emoji_name == "👎":  # PARDON all in batch (grant roles)
                imperius_star_role = discord.utils.get(guild.roles, name=ROLES["imperius_star"])
                pardoned_count = 0
                
                if imperius_star_role:
                    for batch_uid, member, batch_entry in members_in_batch:
                        try:
                            await member.add_roles(imperius_star_role, reason=f"Weekly cleanup - pardoned by {reactor.display_name}")
                            pardoned_count += 1
                            
                            # Update tracking
                            if batch_uid in member_join_tracking:
                                member_join_tracking[batch_uid]["status"] = "pardoned_weekly_cleanup"
                                member_join_tracking[batch_uid]["has_roles"] = True
                                member_join_tracking[batch_uid]["last_checked"] = int(time.time())
                                save_join_tracking(member_join_tracking)
                                
                            # Mark as resolved
                            batch_entry["resolved"] = True
                            
                            await asyncio.sleep(1)  # Rate limiting
                        except Exception as e:
                            print(f"Failed to pardon {member.display_name}: {e}")
                    
                    if staff_ch:
                        await staff_ch.send(f"🛡️ {reactor.mention} pardoned {pardoned_count} members (granted Imperius🔥 role).")
                else:
                    if staff_ch:
                        await staff_ch.send(f"❌ Could not find Imperius🔥 role!")
                
            elif emoji_name == "⏰":  # Mark as reviewed (no action)
                reviewed_count = 0
                for batch_uid, member, batch_entry in members_in_batch:
                    batch_entry["resolved"] = True
                    reviewed_count += 1
                    
                    # Update tracking
                    if batch_uid in member_join_tracking:
                        member_join_tracking[batch_uid]["status"] = "reviewed_no_action"
                        member_join_tracking[batch_uid]["last_checked"] = int(time.time())
                        save_join_tracking(member_join_tracking)
                
                if staff_ch:
                    await staff_ch.send(f"⏰ {reactor.mention} marked {reviewed_count} members as reviewed (no action taken).")
            
            # Clean up all resolved entries in this batch
            for batch_uid, member, batch_entry in members_in_batch:
                if batch_entry.get("resolved"):
                    if batch_uid in pending_recruits:
                        del pending_recruits[batch_uid]
            
            save_json(PENDING_FILE, pending_recruits)
            
            # Delete the alert message
            try:
                ch_for_msg = client.get_channel(payload.channel_id)
                if ch_for_msg:
                    msg = await ch_for_msg.fetch_message(msg_id)
                    await msg.delete()
            except Exception:
                pass
            
            return  # Exit after handling weekly cleanup

        # Handle 24h alert reactions
        elif entry.get("is_24h_alert"):
            if emoji_name == "⏰":  # Extend deadline
                # Reset the start time to now (give them 24 more hours)
                entry["started"] = int(time.time())
                entry["under_review"] = False
                entry["is_24h_alert"] = False
                entry["resolved"] = False
                save_json(PENDING_FILE, pending_recruits)
                
                if staff_ch:
                    await staff_ch.send(
                        f"⏰ {reactor.mention} extended deadline for recruit {recruit_member.mention if recruit_member else 'Unknown'}. "
                        f"Will check again in 24 hours."
                    )
                
                # Delete the alert message
                try:
                    ch_for_msg = client.get_channel(payload.channel_id)
                    if ch_for_msg:
                        msg = await ch_for_msg.fetch_message(msg_id)
                        await msg.delete()
                except Exception:
                    pass
                return

        # Delete the original verification message (for non-weekly-cleanup)
        if not is_weekly_cleanup:
            try:
                ch_for_msg = client.get_channel(payload.channel_id)
                if ch_for_msg:
                    msg = await ch_for_msg.fetch_message(msg_id)
                    await msg.delete()
            except Exception:
                pass

        # Handle member verification requests (current members)
        if is_member_verification:
            if emoji_name == "👍":  # APPROVE member
                try:
                    imperius_star_role = discord.utils.get(guild.roles, name=ROLES["imperius_star"])
                    if imperius_star_role and recruit_member:
                        await recruit_member.add_roles(imperius_star_role)
                        
                        # Update tracking - member got roles!
                        if uid in member_join_tracking:
                            member_join_tracking[uid]["status"] = "verified_member"
                            member_join_tracking[uid]["has_roles"] = True
                            member_join_tracking[uid]["last_checked"] = int(time.time())
                            member_join_tracking[uid]["notes"].append(f"Granted {ROLES['imperius_star']} role by {approver_text}")
                            save_join_tracking(member_join_tracking)
                        
                        # Send approval notification
                        if staff_ch:
                            embed = discord.Embed(
                                title="✅ Member Access Approved",
                                description=f"**{recruit_member.display_name}** added to the Imperius🔥 approved by {approver_text}",
                                color=0x00ff00
                            )
                            await staff_ch.send(embed=embed)
                            
                        # Notify user
                        try:
                            dm = await recruit_member.create_dm()
                            await dm.send("✅ Your membership has been verified! You've been granted full access to the server.")
                        except Exception:
                            pass
                    else:
                        if staff_ch:
                            await staff_ch.send(f"❌ Error: {ROLES['imperius_star']} role not found. Please assign manually to {recruit_member.mention if recruit_member else 'the member'}")
                            
                except Exception as e:
                    print(f"⚠️ Failed to assign role to member {uid}: {e}")
                    if staff_ch:
                        await staff_ch.send(f"❌ Error assigning role: {e}")
                        
            elif emoji_name == "👎":  # DENY member verification
                if staff_ch:
                    denial_embed = discord.Embed(
                        title="❌ Member Access Denied",
                        description=f"**{recruit_member.display_name if recruit_member else 'Unknown'}** claimed to be an Imperius member and requesting full access to this server as a member, but denied by {approver_text}",
                        color=0xff0000
                    )
                    await staff_ch.send(embed=denial_embed)
                    
                    # Update tracking
                    if uid in member_join_tracking:
                        member_join_tracking[uid]["status"] = "member_verification_denied"
                        member_join_tracking[uid]["last_checked"] = int(time.time())
                        save_join_tracking(member_join_tracking)
                    
                    # Notify user
                    try:
                        if recruit_member:
                            dm = await recruit_member.create_dm()
                            await dm.send("❌ Your membership verification was not approved. Please contact admins for more information.")
                    except Exception:
                        pass
                        
        else:
            # Original kick/pardon logic for regular recruits (not weekly cleanup)
            if emoji_name == "👍":  # KICK regular recruit
                kicked_display = recruit_member.display_name if recruit_member else f"ID {uid}"
                try:
                    if recruit_member:
                        await guild.kick(recruit_member, reason="Rejected by admin reaction decision")
                        
                        # Update tracking
                        if uid in member_join_tracking:
                            member_join_tracking[uid]["status"] = "kicked"
                            member_join_tracking[uid]["last_checked"] = int(time.time())
                            save_join_tracking(member_join_tracking)
                        
                        try:
                            dm = await recruit_member.create_dm()
                            await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Imperius.")
                        except Exception:
                            pass
                except Exception as e:
                    print(f"⚠️ Failed to kick recruit {uid}: {e}")

                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {kicked_display} kicked out of Imperius",
                        description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver_text}",
                        color=discord.Color.red()
                    )
                    try:
                        await staff_ch.send(embed=embed)
                    except Exception:
                        pass

            else:  # PARDON regular recruit
                pardoned_display = recruit_member.display_name if recruit_member else f"ID {uid}"
                
                # Update tracking
                if uid in member_join_tracking:
                    member_join_tracking[uid]["status"] = "pardoned"
                    member_join_tracking[uid]["last_checked"] = int(time.time())
                    save_join_tracking(member_join_tracking)
                
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {pardoned_display} pardoned",
                        description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver_text}",
                        color=discord.Color.green()
                    )
                    try:
                        await staff_ch.send(embed=embed)
                    except Exception:
                        pass

        # Remove from pending (for non-weekly-cleanup, weekly cleanup already handled this)
        if not is_weekly_cleanup:
            try:
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_json(PENDING_FILE, pending_recruits)
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
                        # Use atomic save to prevent corruption
                        temp_file = PENDING_FILE + ".tmp"
                        try:
                            with open(temp_file, "w") as f:
                                json.dump(pending_recruits, f)
                            os.replace(temp_file, PENDING_FILE)  # Atomic replace
                            print(f"🧹 Cleaned up {stuck_cleaned} old pending recruits")
                        except Exception as save_error:
                            print(f"⚠️ Failed to save pending recruits: {save_error}")
                            # Restore removed entries to avoid data loss
                            # (In practice, entries_to_remove is already lost, but they were old anyway)
                            
                except Exception as e:
                    log_error("PERIODIC_CLEANUP", e)
            
            # Clean up old recent_joins to prevent memory leaks
            global recent_joins  # ✅ Should already be here
            recent_joins = {k: v for k, v in recent_joins.items() if now - v < 3600}  # Keep only last hour
            
            # Clean up old presence cooldown entries
            global presence_cooldown  # ✅ Should already be here
            old_time = now - PRESENCE_COOLDOWN_TIME
            presence_cooldown = {k: v for k, v in presence_cooldown.items() if v > old_time}
            
            # Rest of the function...
            
            # Clean up old presence cooldown entries
            global presence_cooldown
            old_time = now - PRESENCE_COOLDOWN_TIME
            presence_cooldown = {k: v for k, v in presence_cooldown.items() if v > old_time}
            
            # 🆕 Check for recruits pending >24 hours (STUCK RECRUITS)
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
                        
                        # Create urgent alert for admins
                        embed = discord.Embed(
                            title="🚨 URGENT: Stuck Recruit (>24 hours)",
                            description=(
                                f"**Recruit {display_name} has been pending for OVER 24 HOURS!**\n\n"
                                f"**Status:** Never responded to DMs\n"
                                f"**Time pending:** {(now - started) // 3600} hours\n\n"
                                f"**Options:**\n"
                                f"• 👍 = Kick recruit (failed to respond)\n"
                                f"• 👎 = Keep and try manual verification\n"
                                f"• ⏰ = Extend deadline (wait longer)\n\n"
                                f"*(This is an automated alert for long-pending recruits)*"
                            ),
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        embed.add_field(name="User ID", value=f"`{uid}`", inline=True)
                        embed.add_field(name="Started", value=f"<t:{started}:R>", inline=True)
                        
                        try:
                            review_msg = await staff_ch.send(embed=embed)
                            await review_msg.add_reaction("👍")
                            await review_msg.add_reaction("👎")
                            await review_msg.add_reaction("⏰")
                            
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
                            embed = discord.Embed(
                                title=f"🪖 Recruit {display_name} requires decision",
                                description="Recruit ignored approval questions.\nReact 👍 to kick, 👎 to pardon. (Only admins with special roles may decide.)",
                                color=discord.Color.dark_gold()
                            )
                            review_msg = await staff_ch.send(embed=embed)
                            try:
                                await review_msg.add_reaction("👍")
                                await review_msg.add_reaction("👎")
                            except Exception:
                                pass

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
            
            # Get all clan roles
            imperius_star_role = discord.utils.get(guild.roles, name=ROLES["imperius_star"])
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
                    if role == imperius_star_role or role.id in clan_role_ids:
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
                            "**React with:**\n"
                            "• 👍 = Kick all members in this batch\n"
                            "• 👎 = Pardon all members (grant Imperius🔥 role)\n"
                            "• ⏰ = Mark as reviewed (no action)\n\n"
                            "*(Only admins with special roles may decide.)*"
                        ),
                        inline=False
                    )
                    
                    # Send alert with reactions
                    alert_msg = await staff_ch.send(embed=embed)
                    await alert_msg.add_reaction("👍")
                    await alert_msg.add_reaction("👎")
                    await alert_msg.add_reaction("⏰")
                    
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
