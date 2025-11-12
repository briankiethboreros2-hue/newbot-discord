# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime
from keep_alive import app  # import the Flask app instead of start_keep_alive

# -----------------------
# === CONFIGURATION ===
# -----------------------
CHANNELS = {
    "main": 1437768842871832597,        # Main announcements
    "recruit": 1437568595977834590,     # Recruit channel (where bot notifies & DM prompt)
    "reminder": 1369091668724154419,    # Reminder channel (tracked for message count)
    "staff_review": 1437586858417852438 # Admin review channel (applications & inactivity)
}

ROLES = {
    "queen": 1437578521374363769,        # Queen👑
    "clan_master": 1389835747040694332,  # Cᥣᥲᥒ  Mᥲstᥱr🌟
    "impedance": 1437570031822176408,    # Impedance⭐
    "og_impedance": 1437572916005834793  # OG-Impedance🔫 (optional)
}

# How many messages in REMINDER channel before sending reminder (persisted)
REMINDER_THRESHOLD = 50

# Files for persistent state
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"

# Interview questions (DM)
RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member invite you? If yes, who?",
    "3️⃣ Is the account you're using to apply in our clan your main account?",
    "4️⃣ Are you willing to change your in-game name to our clan format? (IM-Name)"
]

# Reminder messages (embeds)
REMINDERS = [
    {
        "title": "🟢 Activity Reminder",
        "description": "Members must keep their status set only to “Online” while active.\nInactive members without notice may lose their role or be suspended."
    },
    {
        "title": "🧩 IGN Format",
        "description": "All members must use the official clan format: `IM-(Your IGN)`\nExample: IM-Ryze or IM-Reaper."
    },
    {
        "title": "🔊 Voice Channel Reminder",
        "description": "When online, you must join the **Public Call** channel.\nOpen mic is required — we value real-time communication.\nStay respectful and avoid mic spamming or toxic behavior."
    }
]

# -----------------------
# === END CONFIGURATION ===
# -----------------------

# --- Intents ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# --- Persistent state defaults ---
state = {
    "message_counter": 0,
    "current_reminder": 0
}

# pending_recruits structure:
# { str(user_id): {
#       "step": int, "answers": [str,...],
#       "started_at": timestamp, "last_active": timestamp,
#       "notify_message_id": int (id of message in recruit channel),
#       "under_review": bool,
#       "review_message_id": int (in staff channel),
#       "resolved": bool
#   }, ...
# }
pending_recruits = {}

# -----------------------
# --- Utility functions
# -----------------------
def load_state():
    global state
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        print(f"🔁 Loaded reminder state: {state}")
    except FileNotFoundError:
        print("ℹ️ No previous reminder state found; starting fresh.")
    except Exception as e:
        print(f"⚠️ Failed to load reminder state: {e}")

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        # print(f"💾 Saved reminder state: {state}")
    except Exception as e:
        print(f"⚠️ Failed to save reminder state: {e}")

def load_pending():
    global pending_recruits
    try:
        with open(PENDING_FILE, "r") as f:
            raw = json.load(f)
            # convert keys to str to be safe
            pending_recruits = {k: v for k, v in raw.items()}
        print(f"🔁 Loaded pending recruits: {len(pending_recruits)}")
    except FileNotFoundError:
        print("ℹ️ No pending recruits file found; starting fresh.")
    except Exception as e:
        print(f"⚠️ Failed to load pending recruits: {e}")

def save_pending():
    try:
        with open(PENDING_FILE, "w") as f:
            json.dump(pending_recruits, f)
        # print("💾 Saved pending recruits.")
    except Exception as e:
        print(f"⚠️ Failed to save pending recruits: {e}")

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

# Check whether a reactor (Member) has any of the special roles
def is_authorized_reactor(member: discord.Member):
    role_ids = [r.id for r in member.roles]
    return any(role_id for role_id in (ROLES["queen"], ROLES["clan_master"], ROLES["og_impedance"]) if role_id and role_id in role_ids)

# Build approver label based on roles and nickname preference
def approver_label(member: discord.Member):
    # prefer OG, then Clan Master, then Queen (as per your earlier mapping)
    role_ids = [r.id for r in member.roles]
    if ROLES.get("og_impedance") and ROLES["og_impedance"] in role_ids:
        return f"OG-{member.display_name}"
    if ROLES.get("clan_master") and ROLES["clan_master"] in role_ids:
        return f"Clan Master {member.display_name}"
    if ROLES.get("queen") and ROLES["queen"] in role_ids:
        return f"Queen {member.display_name}"
    # fallback to display name
    return member.display_name

# -----------------------
# --- Bot events
# -----------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    load_state()
    load_pending()
    # start background checker for inactivity
    client.loop.create_task(inactivity_checker_loop())
    print("🕓 Ready and monitoring recruits, reminders, and presence updates.")

@client.event
async def on_member_join(member):
    """Start DM interview and notify in recruit channel."""
    try:
        recruit_ch = client.get_channel(CHANNELS["recruit"])
        # send notice in recruit channel (we'll delete later if successful)
        if recruit_ch and isinstance(recruit_ch, discord.TextChannel):
            notice = await recruit_ch.send(f"🪖 {member.display_name}, I have sent you a DM — please check your DMs.")
            notice_id = notice.id
        else:
            notice_id = None
            print("⚠️ Recruit channel not found to send notice.")

        # initialize pending state
        pending_recruits[str(member.id)] = {
            "step": 0,
            "answers": [],
            "started_at": now_ts(),
            "last_active": now_ts(),
            "notify_message_id": notice_id,
            "under_review": False,
            "review_message_id": None,
            "resolved": False
        }
        save_pending()
        print(f"📋 Started interview for {member.display_name} (id={member.id})")

        # DM first question
        try:
            dm = await member.create_dm()
            await dm.send("Welcome to Impedance! Please answer the following questions for your application:")
            await dm.send(RECRUIT_QUESTIONS[0])
        except Exception as e:
            print(f"⚠️ Could not send DM to {member.display_name}: {e}")
            # If cannot DM, post a message in recruit channel informing staff
            staff = client.get_channel(CHANNELS["staff_review"])
            if staff and isinstance(staff, discord.TextChannel):
                await staff.send(f"⚠️ Could not DM recruit {member.display_name} (id:{member.id}). Please contact them manually.")
    except Exception as e:
        print(f"⚠️ Error in on_member_join: {e}")

@client.event
async def on_message(message):
    """Handle DM answers, reminder counting, and other message events."""
    # ignore bot messages
    if message.author == client.user:
        return

    # --- Handle DM answers from recruits ---
    if isinstance(message.channel, discord.DMChannel):
        uid = str(message.author.id)
        if uid in pending_recruits and not pending_recruits[uid].get("under_review") and not pending_recruits[uid].get("resolved"):
            entry = pending_recruits[uid]
            # record answer
            entry["answers"].append(message.content.strip())
            entry["step"] += 1
            entry["last_active"] = now_ts()
            save_pending()
            print(f"✉️ Received answer step {entry['step']} from {message.author.display_name}")

            # If more questions, ask next
            if entry["step"] < len(RECRUIT_QUESTIONS):
                try:
                    await message.channel.send(RECRUIT_QUESTIONS[entry["step"]])
                except Exception as e:
                    print(f"⚠️ Failed to send next DM to {message.author.display_name}: {e}")
            else:
                # Completed all questions
                # Send thank you DM
                try:
                    await message.channel.send(
                        "✅ Thank you for your cooperation! We are looking forward to welcoming you to Impedance.\n"
                        "Your answers will be reviewed by the admins. Please wait for further instructions."
                    )
                except Exception:
                    pass

                # send answers to staff review channel
                staff = client.get_channel(CHANNELS["staff_review"])
                if staff and isinstance(staff, discord.TextChannel):
                    now_str = readable_now()
                    formatted = "\n".join(f"**{i+1}.** {a}" for i, a in enumerate(entry["answers"]))
                    embed = discord.Embed(
                        title=f"🪖 Recruit {message.author.display_name} for approval.",
                        description=f"{formatted}\n\n📅 Date answered: `{now_str}`",
                        color=discord.Color.blurple()
                    )
                    try:
                        await staff.send(embed=embed)
                    except Exception as e:
                        print(f"⚠️ Failed to send application embed to staff: {e}")

                # delete the recruit-channel notice if exists
                try:
                    notice_id = entry.get("notify_message_id")
                    if notice_id:
                        rc = client.get_channel(CHANNELS["recruit"])
                        if rc and isinstance(rc, discord.TextChannel):
                            msg = await rc.fetch_message(notice_id)
                            await msg.delete()
                except Exception as e:
                    print(f"⚠️ Could not delete recruit notice: {e}")

                # mark resolved and save
                entry["resolved"] = True
                save_pending()
                # cleanup from memory (optional keep history)
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_pending()
            return

    # --- Handle reminder channel counting ---
    if message.channel.id == CHANNELS["reminder"]:
        state["message_counter"] += 1
        print(f"💬 Reminder channel message count: {state['message_counter']}")
        save_state()
        if state["message_counter"] >= REMINDER_THRESHOLD:
            state["message_counter"] = 0
            reminder = REMINDERS[state["current_reminder"]]
            embed = discord.Embed(
                title="Reminders Impedance!",
                description=f"**{reminder['title']}**\n\n{reminder['description']}",
                color=discord.Color.orange()
            )
            try:
                await message.channel.send(embed=embed)
                print(f"📢 Sent reminder: {reminder['title']}")
            except Exception as e:
                print(f"⚠️ Failed to send reminder embed: {e}")
            state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
            save_state()
        return

@client.event
async def on_raw_reaction_add(payload):
    """
    Handle reaction on admin review message.
    Only reactions from users with special roles count.
    """
    try:
        # Only care about reactions in the staff review channel
        if payload.channel_id != CHANNELS["staff_review"]:
            return

        # find which pending recruit this review message belongs to
        for uid, entry in list(pending_recruits.items()):
            if entry.get("under_review") and entry.get("review_message_id") == payload.message_id and not entry.get("resolved"):
                # check reactor
                guild = client.get_guild(payload.guild_id)
                reactor = guild.get_member(payload.user_id)
                if not reactor:
                    # couldn't find reactor
                    return

                if not is_authorized_reactor(reactor):
                    print(f"🚫 Reactor {reactor.display_name} not authorized to decide.")
                    return

                # determine emoji (support variants)
                emoji_char = str(payload.emoji)
                is_yes = emoji_char.startswith("👍")
                is_no = emoji_char.startswith("👎")

                # only act on first valid vote for that recruit
                if entry.get("resolved"):
                    return

                # mark resolved to avoid double-processing
                entry["resolved"] = True
                save_pending()

                recruit_id = int(uid)
                recruit_member = None
                try:
                    recruit_member = guild.get_member(recruit_id) or await guild.fetch_member(recruit_id)
                except Exception:
                    recruit_member = None

                approver = reactor
                approver_label_text = approver_label(approver)

                staff_channel = client.get_channel(CHANNELS["staff_review"])

                if is_yes:
                    # Kick the recruit if present
                    kicked_name = None
                    try:
                        if recruit_member:
                            await guild.kick(recruit_member, reason="Rejected by staff vote")
                            kicked_name = recruit_member.display_name
                        else:
                            # not in guild or already left
                            kicked_name = str(recruit_id)
                    except Exception as e:
                        print(f"⚠️ Failed to kick recruit {recruit_id}: {e}")
                    # send DM to recruit if possible
                    try:
                        if recruit_member:
                            dm = await recruit_member.create_dm()
                            await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                    except Exception as e:
                        print(f"⚠️ Could not DM kicked recruit: {e}")

                    # post final log to staff channel (permanent)
                    if staff_channel:
                        embed = discord.Embed(
                            title=f"🪖 Recruit {kicked_name} kicked out of Impedance",
                            description=(
                                "Recruit was removed due to unwillingness to cooperate with the application protocol.\n\n"
                                f"Action approved by: {approver_label_text}"
                            ),
                            color=discord.Color.red()
                        )
                        await staff_channel.send(embed=embed)
                        print(f"📢 Recruit {kicked_name} kicked; approved by {approver_label_text}")

                elif is_no:
                    # pardoned
                    pardoned_name = None
                    if recruit_member:
                        pardoned_name = recruit_member.display_name
                    else:
                        pardoned_name = str(recruit_id)

                    if staff_channel:
                        embed = discord.Embed(
                            title=f"🪖 Recruit {pardoned_name} pardoned",
                            description=(
                                f"Despite not answering or refusing to cooperate, the recruit was pardoned.\n\n"
                                f"Approved by: {approver_label_text}"
                            ),
                            color=discord.Color.green()
                        )
                        await staff_channel.send(embed=embed)
                        print(f"📢 Recruit {pardoned_name} pardoned; approved by {approver_label_text}")

                # cleanup: remove pending entry, keep review message visible for history
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_pending()
                return
    except Exception as e:
        print(f"⚠️ Error in on_raw_reaction_add: {e}")

# -----------------------
# Inactivity checker
# -----------------------
async def inactivity_checker_loop():
    """Background loop that checks pending recruits every 60s and posts admin review if idle >= 10min."""
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = now_ts()
            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last_active = entry.get("last_active", entry.get("started_at", now))
                # 10 minutes = 600 seconds
                if now - last_active >= 600:
                    # post admin review message
                    staff = client.get_channel(CHANNELS["staff_review"])
                    recruit_member = None
                    try:
                        guilds = client.guilds
                        # find the guild where this member is (assume single guild)
                        # attempt to find member across guilds
                        for g in guilds:
                            m = g.get_member(int(uid))
                            if m:
                                recruit_member = m
                                break
                    except Exception:
                        pass

                    display_name = recruit_member.display_name if recruit_member else f"User ID {uid}"

                    if staff and isinstance(staff, discord.TextChannel):
                        embed = discord.Embed(
                            title=f"🪖 Recruit {display_name} for approval.",
                            description=(
                                "Has not answered or refused to answer the application questions within 10 minutes.\n\n"
                                "Should the recruit be rejected of application and tryout, and kicked out of the clan server?\n\n"
                                "React 👍🏻 if yes and 👎🏻 if no."
                            ),
                            color=discord.Color.dark_gold()
                        )
                        try:
                            review_msg = await staff.send(embed=embed)
                            # add reactions for convenience
                            try:
                                await review_msg.add_reaction("👍")
                                await review_msg.add_reaction("👎")
                            except Exception:
                                pass

                            # mark under review
                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            entry["review_channel_id"] = staff.id
                            save_pending()
                            print(f"📣 Posted admin review for recruit {display_name} (uid={uid})")
                        except Exception as e:
                            print(f"⚠️ Failed to post admin review for uid {uid}: {e}")
            # sleep 60s
            await asyncio.sleep(60)
        except Exception as e:
            print(f"⚠️ Error in inactivity checker loop: {e}")
            await asyncio.sleep(60)

# -----------------------
# Run bot
# -----------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

# start bot thread (so keep_alive's Flask can be the main process)
threading.Thread(target=run_bot, daemon=True).start()

# Run Flask keep-alive (Render monitors this process)
if __name__ == "__main__":
    # start self-pinger
    from keep_alive import ping_self
    threading.Thread(target=ping_self, daemon=True).start()
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
