# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Final fixed bot file with recruit DM interview, admin review, reminders, presence announcements.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # keep_alive.py must exist and provide ping_self()

# -------------------------
# === CONFIG (easy edit) ===
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,         # Main announcements
    "recruit": 1437568595977834590,      # Recruit channel (public notice)
    "reminder": 1369091668724154419,     # Reminder message channel (tracked)
    "staff_review": 1437586858417852438  # Admin review channel
}

ROLES = {
    "queen": 1437578521374363769,        # Queen👑
    "clan_master": 1389835747040694332,  # Cᥣᥲᥒ  Mᥲstᥱr🌟
    "impedance": 1437570031822176408,    # Impedance⭐
    "og_impedance": 1437572916005834793  # OG-Impedance🔫 (optional)
}

REMINDER_THRESHOLD = 50  # number of messages before posting next reminder

# Persistent files
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"

# Recruit DM questions (in order)
RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ Is the account you're using to apply in our clan your main account?",
    "4️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

# Reminder entries (embeds)
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

# -------------------------
# === End CONFIG ===
# -------------------------

# Intents
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# State
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}  # dict keyed by str(user_id) -> metadata dict

# Utility: load/save
def load_state():
    global state
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        print(f"🔁 Loaded reminder state: {state}")
    except FileNotFoundError:
        print("ℹ️ No reminder state found; starting fresh.")
    except Exception as e:
        print(f"⚠️ Error loading reminder state: {e}")

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"⚠️ Error saving reminder state: {e}")

def load_pending():
    global pending_recruits
    try:
        with open(PENDING_FILE, "r") as f:
            pending_recruits = json.load(f)
        print(f"🔁 Loaded pending recruits: {len(pending_recruits)}")
    except FileNotFoundError:
        print("ℹ️ No pending recruits file; starting fresh.")
    except Exception as e:
        print(f"⚠️ Error loading pending recruits: {e}")

def save_pending():
    try:
        with open(PENDING_FILE, "w") as f:
            json.dump(pending_recruits, f)
    except Exception as e:
        print(f"⚠️ Error saving pending recruits: {e}")

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

# Check reactor has one of special roles
def is_authorized_reactor(member: discord.Member):
    if member is None:
        return False
    role_ids = [r.id for r in member.roles]
    for key in ("queen", "clan_master", "og_impedance"):
        rid = ROLES.get(key)
        if rid and rid in role_ids:
            return True
    return False

def approver_label(member: discord.Member):
    if member is None:
        return "Unknown"
    role_ids = [r.id for r in member.roles]
    if ROLES.get("og_impedance") and ROLES["og_impedance"] in role_ids:
        return f"OG-{member.display_name}"
    if ROLES.get("clan_master") and ROLES["clan_master"] in role_ids:
        return f"Clan Master {member.display_name}"
    if ROLES.get("queen") and ROLES["queen"] in role_ids:
        return f"Queen {member.display_name}"
    return member.display_name

# ---------- Events ----------
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    load_state()
    load_pending()
    # start background inactivity checker
    client.loop.create_task(inactivity_checker())
    print("🕓 Bot ready: tracking reminders, recruits, presence.")

@client.event
async def on_member_join(member):
    """Start DM interview and post public notice in recruit channel (deleted on success)."""
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if recruit_ch is None:
        print("⚠️ Recruit channel not found.")
        return

    # send public notification (will be deleted on success)
    try:
        notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
        notice_id = notice.id
    except Exception:
        notice_id = None

    uid = str(member.id)
    # create pending entry
    pending_recruits[uid] = {
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

    # DM interview flow
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer the following approval questions one by one:")

        for q_idx, q in enumerate(RECRUIT_QUESTIONS):
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600  # 10 minutes to answer each question
                )
            except asyncio.TimeoutError:
                # didn't answer within 10 minutes for this question -> mark last_active and let inactivity checker handle
                pending_recruits[uid]["last_active"] = now_ts()
                save_pending()
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"ℹ️ Member {member.display_name} timed out during interview (q {q_idx+1}).")
                return  # stop DM flow; inactivity checker will escalate

            # record answer
            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["step"] = q_idx + 1
            pending_recruits[uid]["last_active"] = now_ts()
            save_pending()

        # completed all questions
        try:
            await dm.send(
                "✅ Thank you for your cooperation! We are looking forward to welcoming you to Impedance.\n"
                "Your answers will be reviewed by the admins. Please wait for further instructions."
            )
        except Exception:
            pass

        # delete the public notice in recruit channel if present
        try:
            nid = pending_recruits[uid].get("notify_message_id")
            if nid:
                msg = await recruit_ch.fetch_message(nid)
                await msg.delete()
        except Exception:
            pass

        # send to admin review channel (formatted)
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        if admin_ch:
            now_str = readable_now()
            labels = [
                "Purpose of joining:",
                "Invited by an Impedance member, and who:",
                "Main Crossfire account:",
                "Willing to CCN:"
            ]
            formatted = ""
            answers = pending_recruits[uid]["answers"]
            for i, ans in enumerate(answers):
                label = labels[i] if i < len(labels) else f"Question {i+1}:"
                formatted += f"**{label}**\n{ans}\n\n"
            embed = discord.Embed(
                title=f"🪖 Recruit {member.display_name} for approval.",
                description=f"{formatted}📅 **Date answered:** `{now_str}`",
                color=discord.Color.blurple()
            )
            await admin_ch.send(embed=embed)

        # mark resolved and remove pending
        pending_recruits[uid]["resolved"] = True
        save_pending()
        # remove from dict (keep history in file if you prefer)
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_pending()
        print(f"✅ Completed interview for {member.display_name}")

    except Exception as e:
        # DM failed (blocked) or other error: escalate immediately to admin review
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        # mark last_active and keep pending entry
        pending_recruits[uid]["last_active"] = now_ts()
        save_pending()

        admin_ch = client.get_channel(CHANNELS["staff_review"])
        display_name = member.display_name
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {display_name} for approval.",
                description=(
                    "Could not DM recruit or recruit blocked DMs. Recruit did not respond.\n\n"
                    "Should the recruit be rejected and kicked out of the clan server?\nReact 👍 to **kick**, 👎 to **pardon**."
                ),
                color=discord.Color.dark_gold()
            )
            try:
                review_msg = await admin_ch.send(embed=embed)
                try:
                    await review_msg.add_reaction("👍")
                    await review_msg.add_reaction("👎")
                except Exception:
                    pass
                # mark this pending as under review immediately
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = review_msg.id
                pending_recruits[uid]["review_channel_id"] = admin_ch.id
                save_pending()
            except Exception as e2:
                print(f"⚠️ Failed to post admin review for DM-blocked recruit: {e2}")

        # also inform recruit channel (short notice)
        try:
            await recruit_ch.send(f"⚠️ {member.mention} did not respond to DM or blocked DMs. Admins have been notified.")
        except Exception:
            pass

@client.event
async def on_message(message):
    # ignore bot
    if message.author.id == client.user.id:
        return

    # Reminder channel counting
    try:
        if message.channel.id == CHANNELS["reminder"]:
            state["message_counter"] += 1
            save_state()
            if state["message_counter"] >= REMINDER_THRESHOLD:
                reminder = REMINDERS[state["current_reminder"]]
                embed = discord.Embed(
                    title="Reminders Impedance!",
                    description=f"**{reminder['title']}**\n\n{reminder['description']}",
                    color=discord.Color.orange()
                )
                try:
                    await message.channel.send(embed=embed)
                except Exception as e:
                    print(f"⚠️ Failed to send reminder: {e}")
                state["message_counter"] = 0
                state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
                save_state()
    except Exception as e:
        print(f"⚠️ Error in on_message: {e}")

@client.event
async def on_presence_update(before, after):
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            member = after
            role_ids = [r.id for r in member.roles]
            if ROLES["queen"] in role_ids:
                title, color = f"👑 Queen {member.display_name} just came online!", discord.Color.gold()
            elif ROLES["clan_master"] in role_ids:
                title, color = f"🌟 Clan Master {member.display_name} just came online!", discord.Color.blue()
            elif ROLES["impedance"] in role_ids:
                title, color = f"⭐ Impedance {member.display_name} just came online!", discord.Color.purple()
            elif ROLES.get("og_impedance") and ROLES["og_impedance"] in role_ids:
                title, color = f"🎉 OG 🎉 {member.display_name} just came online!", discord.Color.red()
            else:
                return
            ch = client.get_channel(CHANNELS["main"])
            if ch:
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=after.display_avatar.url)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Error in on_presence_update: {e}")

# Reaction handling (raw) for admin review decisions
@client.event
async def on_raw_reaction_add(payload):
    try:
        # only care reactions in staff review channel
        if payload.channel_id != CHANNELS["staff_review"]:
            return
        # ignore bot reactions
        if payload.user_id == client.user.id:
            return

        # find pending entry whose review_message_id matches this payload
        for uid, entry in list(pending_recruits.items()):
            if not entry.get("under_review") or entry.get("resolved"):
                continue
            if entry.get("review_message_id") != payload.message_id:
                continue

            # find reactor member
            guild = None
            if payload.guild_id:
                guild = client.get_guild(payload.guild_id)
            if guild is None:
                return
            reactor = guild.get_member(payload.user_id)
            if reactor is None:
                return

            # only allow special-role reactors
            if not is_authorized_reactor(reactor):
                print(f"🚫 Unauthorized reactor {reactor.display_name}; ignored.")
                return

            emoji = str(payload.emoji)
            is_yes = emoji.startswith("👍")
            is_no = emoji.startswith("👎")

            # only consider first valid response
            if entry.get("resolved"):
                return

            entry["resolved"] = True
            save_pending()

            # Attempt to fetch recruit member from guild
            recruit_member = None
            try:
                recruit_member = guild.get_member(int(uid))
            except Exception:
                recruit_member = None

            approver_text = approver_label(reactor)
            staff_ch = client.get_channel(CHANNELS["staff_review"])

            if is_yes:
                # kick
                kicked_display = None
                try:
                    if recruit_member:
                        kicked_display = recruit_member.display_name
                        await guild.kick(recruit_member, reason="Rejected by admin vote")
                    else:
                        kicked_display = f"User ID {uid}"
                except Exception as e:
                    print(f"⚠️ Failed to kick recruit {uid}: {e}")

                # DM recruit if possible
                try:
                    if recruit_member:
                        dm = await recruit_member.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                except Exception:
                    pass

                # post final log
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {kicked_display} kicked out of Impedance",
                        description=(
                            "Recruit was removed due to unwillingness to cooperate with the application protocol.\n\n"
                            f"Action approved by: {approver_text}"
                        ),
                        color=discord.Color.red()
                    )
                    await staff_ch.send(embed=embed)
                    print(f"📢 Recruit {kicked_display} kicked; approved by {approver_text}")

            elif is_no:
                pardoned_display = recruit_member.display_name if recruit_member else f"User ID {uid}"
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {pardoned_display} pardoned",
                        description=(
                            f"Despite not answering or refusing to cooperate, the recruit was pardoned.\n\n"
                            f"Approved by: {approver_text}"
                        ),
                        color=discord.Color.green()
                    )
                    await staff_ch.send(embed=embed)
                    print(f"📢 Recruit {pardoned_display} pardoned; approved by {approver_text}")

            # cleanup pending entry (keep review message visible for history)
            if uid in pending_recruits:
                del pending_recruits[uid]
                save_pending()
            return
    except Exception as e:
        print(f"⚠️ Error in on_raw_reaction_add: {e}")

# Background inactivity checker: posts admin review for idle recruits
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = now_ts()
            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last = entry.get("last_active", entry.get("started_at", now))
                # if idle >= 10 minutes
                if now - last >= 600:
                    # post admin review message
                    staff_ch = client.get_channel(CHANNELS["staff_review"])
                    # find the member's display name if in guilds
                    display_name = None
                    for g in client.guilds:
                        m = g.get_member(int(uid))
                        if m:
                            display_name = m.display_name
                            break
                    if display_name is None:
                        display_name = f"User ID {uid}"
                    if staff_ch:
                        embed = discord.Embed(
                            title=f"🪖 Recruit {display_name} for approval.",
                            description=(
                                "Has not answered or refused to answer the application questions within 10 minutes.\n\n"
                                "Should the recruit be rejected of application and tryout, and kicked out of the clan server?\n\n"
                                "React 👍 to **kick** and 👎 to **pardon**."
                            ),
                            color=discord.Color.dark_gold()
                        )
                        try:
                            review_msg = await staff_ch.send(embed=embed)
                            try:
                                await review_msg.add_reaction("👍")
                                await review_msg.add_reaction("👎")
                            except Exception:
                                pass
                            # mark under review
                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            entry["review_channel_id"] = staff_ch.id
                            save_pending()
                            print(f"📣 Posted admin review for recruit {display_name} (uid={uid})")
                        except Exception as e:
                            print(f"⚠️ Failed to post admin review for uid {uid}: {e}")
            await asyncio.sleep(60)
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker: {e}")
            await asyncio.sleep(60)

# Run bot
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

# Start bot thread so keep_alive Flask can be main process
threading.Thread(target=run_bot, daemon=True).start()

# Run keep-alive Flask app when executed directly
if __name__ == "__main__":
    # start self-pinger from keep_alive
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
