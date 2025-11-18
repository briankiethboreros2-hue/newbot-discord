# Render Start Command: python3 "DiscordOnlineTracker/main.py"
# Full main.py with all stability fixes applied - functionality remains identical

import threading
import discord
import os
import time
import json
import asyncio
import sys
import traceback
from datetime import datetime, timezone

# IMPORT keep_alive (must exist)
from keep_alive import app, ping_self

# -----------------------
# GLOBAL ERROR HANDLER
# -----------------------
def handle_global_error(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        return
    print("💥 CRITICAL ERROR - Bot crashing:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print("🔄 Bot will restart...")
    os._exit(1)

sys.excepthook = handle_global_error

# -----------------------
# CONFIG (leave as-is)
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
    "og_impedance": 1437572916005834793,
    "impedance": 1437570031822176408
}

REMINDER_THRESHOLD = 50
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"

RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ We require at least **Major 🎖 rank**. Are you Major First Class or above?",
    "4️⃣ Is the account you're using to apply in our main account?",
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
pending_recruits = {}  # keyed by string user id -> dict

# -----------------------
# UTILITIES
# -----------------------
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"⚠️ Failed to load {path}: {e}")
        return default

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"⚠️ Failed to save {path}: {e}")

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_admin(member: discord.Member):
    """Return True if member has one of the special roles."""
    if not member:
        return False
    ids = [r.id for r in member.roles]
    return any(ROLES.get(k) in ids for k in ("queen", "clan_master", "og_impedance"))

def admin_label(member: discord.Member):
    """Return the string label required in logs (OG-, Clan Master, Queen)."""
    if not member:
        return "Unknown"
    ids = [r.id for r in member.roles]
    # Priority: OG, Clan Master, Queen (per your requests)
    if ROLES.get("og_impedance") and ROLES["og_impedance"] in ids:
        return f"OG-{member.display_name}"
    if ROLES.get("clan_master") and ROLES["clan_master"] in ids:
        return f"Clan Master {member.display_name}"
    if ROLES.get("queen") and ROLES["queen"] in ids:
        return f"Queen {member.display_name}"
    return member.display_name

THUMBS_UP = "👍"
THUMBS_DOWN = "👎"

# -----------------------
# MEMORY CLEANUP TASK
# -----------------------
async def memory_cleanup():
    """Clean up memory and log usage periodically"""
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            # Clean up resolved pending recruits
            global pending_recruits
            current_time = now_ts()
            
            # Remove stale entries (over 1 hour old) and resolved entries
            initial_count = len(pending_recruits)
            pending_recruits = {k: v for k, v in pending_recruits.items() 
                              if not v.get("resolved") and 
                              current_time - v.get("started", current_time) < 3600}
            
            if len(pending_recruits) != initial_count:
                save_json(PENDING_FILE, pending_recruits)
                print(f"🧹 Cleaned {initial_count - len(pending_recruits)} stale entries")
            
            # Simple memory logging
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            print(f"🧠 Memory usage: {memory_mb:.1f}MB - Active recruits: {len(pending_recruits)}")
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except Exception as e:
            print(f"⚠️ Error in memory_cleanup: {e}")
            await asyncio.sleep(60)

# -----------------------
# EVENTS
# -----------------------
@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)
    client.loop.create_task(inactivity_checker())
    client.loop.create_task(memory_cleanup())  # New memory cleanup task
    print(f"✅ Logged in as {client.user} at {readable_now()}")

@client.event
async def on_disconnect():
    print(f"🔌 Bot disconnected at {readable_now()}")

@client.event
async def on_resumed():
    print(f"🔁 Bot reconnected at {readable_now()}")

@client.event
async def on_member_join(member):
    """DM recruit with questions; post public notice; on failure escalate to admin review."""
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])

    # welcome (best-effort)
    try:
        if recruit_ch:
            await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Impedance!")
    except Exception:
        pass

    # public notice to be deleted later
    notice_id = None
    try:
        if recruit_ch:
            notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
            notice_id = notice.id
    except Exception:
        notice_id = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started": now_ts(),
        "last": now_ts(),
        "answers": [],
        "announce": notice_id,
        "under_review": False,
        "review_message_id": None,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM flow
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to Impedance! Please answer the approval questions one by one:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
            except asyncio.TimeoutError:
                # update last_active and let inactivity_checker escalate
                pending_recruits[uid]["last"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"⌛ Recruit {member.display_name} timed out during interview.")
                return

            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["last"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # Completed
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
                    "Invited by an Impedance member, and who:",
                    "At least Major rank:",
                    "Is the account you're using to apply your main account:",
                    "Willing to CCN:"
                ]
                formatted = ""
                answers = pending_recruits[uid]["answers"]
                for i, ans in enumerate(answers):
                    label = labels[i] if i < len(labels) else f"Question {i+1}:"
                    formatted += f"**{label}**\n{ans}\n\n"
                now_str = readable_now()
                embed = discord.Embed(
                    title=f"🪖 Recruit {member.display_name} for approval.",
                    description=f"{formatted}📅 **Date answered:** `{now_str}`",
                    color=discord.Color.blurple()
                )
                await staff_ch.send(embed=embed)
        except Exception:
            pass

        # resolved (remove pending)
        try:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)
        except Exception:
            pass

    except Exception as e:
        # DM failed (blocked) - create admin review message and add reactions
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        try:
            if staff_ch:
                display_name = f"{member.display_name} (@{member.name})"
                embed = discord.Embed(
                    title=f"🪖 Recruit {display_name} for approval.",
                    description=(
                        "Could not DM recruit or recruit blocked DMs.\n\n"
                        "React 👍 to kick, 👎 to pardon. (Only admins with special roles may decide.)"
                    ),
                    color=discord.Color.dark_gold()
                )
                review_msg = await staff_ch.send(embed=embed)
                # auto-add thumb reactions
                try:
                    await review_msg.add_reaction(THUMBS_UP)
                    await review_msg.add_reaction(THUMBS_DOWN)
                except Exception:
                    pass

                # mark under review
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = review_msg.id
                save_json(PENDING_FILE, pending_recruits)

            # notify recruit channel
            if recruit_ch:
                await recruit_ch.send(f"⚠️ {member.mention} did not respond to DMs. Admins have been notified.")
        except Exception as e2:
            print(f"⚠️ Failed to create admin review post for DM-blocked recruit: {e2}")

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    # Reminder channel counting
    try:
        if message.channel.id == CHANNELS["reminder"]:
            state["message_counter"] = state.get("message_counter", 0) + 1
            save_json(STATE_FILE, state)
            if state["message_counter"] >= REMINDER_THRESHOLD:
                r = REMINDERS[state.get("current_reminder", 0)]
                embed = discord.Embed(
                    title="Reminders Impedance!",
                    description=f"**{r['title']}**\n\n{r['description']}",
                    color=discord.Color.orange()
                )
                try:
                    await message.channel.send(embed=embed)
                except Exception:
                    pass
                state["current_reminder"] = (state.get("current_reminder", 0) + 1) % len(REMINDERS)
                state["message_counter"] = 0
                save_json(STATE_FILE, state)
    except Exception as e:
        print(f"⚠️ Error in on_message: {e}")

@client.event
async def on_presence_update(before, after):
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            m = after
            ids = [r.id for r in m.roles]
            ch = client.get_channel(CHANNELS["main"])

            if ROLES["queen"] in ids:
                title, color = f"👑 Queen {m.display_name} just came online!", discord.Color.gold()
            elif ROLES["clan_master"] in ids:
                title, color = f"🌟 Clan Master {m.display_name} just came online!", discord.Color.blue()
            elif ROLES["og_impedance"] in ids:
                title, color = f"🎉 OG {m.display_name} online!", discord.Color.red()
            elif ROLES["impedance"] in ids:
                title, color = f"⭐ Member {m.display_name} just came online!", discord.Color.purple()
            else:
                return

            embed = discord.Embed(title=title, color=color)
            embed.set_thumbnail(url=after.display_avatar.url)
            try:
                if ch:
                    await ch.send(embed=embed)
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️ Error in presence handler: {e}")

# -----------------------
# REACTION HANDLER (raw)
# -----------------------
@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """
    Handles admin decisions via reactions. Uses raw event so it works across restarts.
    First valid admin reaction (👍=kick, 👎=pardon) decides.
    """
    try:
        # ignore bot reactions
        if payload.user_id == client.user.id:
            return

        # Only consider messages that are admin review messages
        msg_id = payload.message_id
        # Map msg_id -> pending recruit uid
        uid = None
        for k, v in pending_recruits.items():
            if v.get("review_message_id") == msg_id and not v.get("resolved") and v.get("under_review"):
                uid = k
                break
        if not uid:
            return

        # only consider thumbs up/down
        emoji_name = getattr(payload.emoji, "name", None)
        if emoji_name not in (THUMBS_UP, THUMBS_DOWN):
            return

        # find the guild to lookup member who reacted
        guild = None
        if payload.guild_id:
            guild = client.get_guild(payload.guild_id)
        else:
            # fallback to first guild
            guild = client.guilds[0] if client.guilds else None
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor:
            return

        # Only allow special-role admins to decide
        if not is_admin(reactor):
            # ignore unauthorized reactions
            return

        entry = pending_recruits.get(uid)
        if not entry:
            return
        if entry.get("resolved"):
            return

        # mark resolved immediately to prevent race
        entry["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)

        # Determine action: thumbs up => kick, thumbs down => pardon
        action = "kick" if emoji_name == THUMBS_UP else "pardon"
        approver_text = admin_label(reactor)

        # Try to fetch recruit member object (search guilds)
        recruit_member = None
        try:
            recruit_member = guild.get_member(int(uid))
        except Exception:
            recruit_member = None

        staff_ch = client.get_channel(CHANNELS["staff_review"])

        # Attempt to delete the review message (cleanup)
        try:
            ch_for_msg = client.get_channel(payload.channel_id)
            if ch_for_msg:
                msg = await ch_for_msg.fetch_message(msg_id)
                try:
                    await msg.delete()
                except Exception:
                    pass
        except Exception:
            pass

        # Execute action
        if action == "kick":
            # try to kick recruit when present
            kicked_display = recruit_member.display_name if recruit_member else f"ID {uid}"
            try:
                if recruit_member:
                    await guild.kick(recruit_member, reason="Rejected by admin reaction decision")
                    # DM them politely if possible
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                    except Exception:
                        pass
            except Exception as e:
                print(f"⚠️ Failed to kick recruit {uid}: {e}")

            # post final log to staff channel
            if staff_ch:
                embed = discord.Embed(
                    title=f"🪖 Recruit {kicked_display} kicked out of Impedance",
                    description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver_text}",
                    color=discord.Color.red()
                )
                try:
                    await staff_ch.send(embed=embed)
                except Exception:
                    pass

        else:  # pardon
            pardoned_display = recruit_member.display_name if recruit_member else f"ID {uid}"
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

        # Cleanup pending entry
        try:
            if uid in pending_recruits:
                del pending_recruits[uid]
                save_json(PENDING_FILE, pending_recruits)
        except Exception:
            pass

    except Exception as e:
        print(f"⚠️ Error in on_raw_reaction_add: {e}")

# -----------------------
# INACTIVITY CHECKER (10 minutes)
# -----------------------
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = now_ts()
            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last = entry.get("last", entry.get("started", now))
                # escalate after 10 minutes (600s)
                if now - last >= 600:
                    # delete recruit public notice if exists
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

                    # Post review message and add reactions
                    try:
                        if staff_ch:
                            embed = discord.Embed(
                                title=f"🪖 Recruit {display_name} requires decision",
                                description="Recruit ignored approval questions.\nReact 👍 to kick, 👎 to pardon. (Only admins with special roles may decide.)",
                                color=discord.Color.dark_gold()
                            )
                            review_msg = await staff_ch.send(embed=embed)
                            try:
                                await review_msg.add_reaction(THUMBS_UP)
                                await review_msg.add_reaction(THUMBS_DOWN)
                            except Exception:
                                pass

                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            save_json(PENDING_FILE, pending_recruits)
                    except Exception as e:
                        print(f"⚠️ Failed to post admin review in inactivity_checker for uid {uid}: {e}")
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker loop: {e}")
        await asyncio.sleep(20)

# -----------------------
# ROBUST BOT STARTUP
# -----------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    
    print("🤖 Starting Discord bot…")
    
    # Add reconnection logic with exponential backoff
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            client.run(token, reconnect=True)
            break
        except Exception as e:
            print(f"💥 Bot crashed on attempt {attempt + 1}: {e}")
            if attempt < max_attempts - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8, 16 seconds
                print(f"🔄 Restarting in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("❌ Max restart attempts reached. Bot is shutting down.")
                os._exit(1)

# Start bot in thread
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    # Start self-pinger
    try:
        ping_thread = threading.Thread(target=ping_self, daemon=True)
        ping_thread.start()
        print("✅ Self-pinger started")
    except Exception as e:
        print(f"⚠️ Failed to start self-pinger: {e}")
    
    print("🌐 Starting Flask keep-alive server…")
    try:
        app.run(host="0.0.0.0", port=8080, debug=False)
    except Exception as e:
        print(f"💥 Flask server crashed: {e}")
        os._exit(1)
