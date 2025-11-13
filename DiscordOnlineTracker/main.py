# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Fully fixed version — keeps everything intact with bug fixes.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # Flask keep-alive

# -------------------------
# === CONFIG ===
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,         # Main announcements
    "recruit": 1437568595977834590,      # Recruit channel
    "reminder": 1369091668724154419,     # Reminder message channel
    "staff_review": 1437586858417852438  # Admin review channel
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "impedance": 1437570031822176408,
    "og_impedance": 1437572916005834793
}

REMINDER_THRESHOLD = 50
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"

RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ Is the account you're using to apply in our clan your main account?",
    "4️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

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
# === SETUP ===
# -------------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)

state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}

# -------------------------
# === UTILITIES ===
# -------------------------
def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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

def approver_label(member: discord.Member):
    if not member:
        return "Unknown"
    role_ids = [r.id for r in member.roles]
    if ROLES["og_impedance"] in role_ids:
        return f"OG-{member.display_name}"
    if ROLES["clan_master"] in role_ids:
        return f"Clan Master {member.display_name}"
    if ROLES["queen"] in role_ids:
        return f"Queen {member.display_name}"
    return member.display_name

def is_authorized(member: discord.Member):
    if not member:
        return False
    role_ids = [r.id for r in member.roles]
    return any(ROLES[r] in role_ids for r in ("queen", "clan_master", "og_impedance"))

# -------------------------
# === EVENTS ===
# -------------------------
@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)
    client.loop.create_task(inactivity_checker())
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_member_join(member):
    """DM recruit with questions and announce in recruit channel."""
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        print("⚠️ Recruit channel not found.")
        return

    # Announce recruit joined
    try:
        join_embed = discord.Embed(
            title=f"🪖 Recruit candidate joined — candidate {member.display_name}",
            color=discord.Color.teal()
        )
        join_embed.set_thumbnail(url=member.display_avatar.url)
        await recruit_ch.send(embed=join_embed)
    except Exception as e:
        print(f"⚠️ Could not announce recruit join: {e}")

    # Notify recruit in channel and DM
    notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
    uid = str(member.id)
    pending_recruits[uid] = {
        "started_at": now_ts(),
        "last_active": now_ts(),
        "answers": [],
        "notify_msg": notice.id,
        "under_review": False,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer the following approval questions one by one:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author == member and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
                pending_recruits[uid]["answers"].append(reply.content.strip())
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
            except asyncio.TimeoutError:
                print(f"⌛ {member.display_name} did not answer in time.")
                await dm.send("You didn’t answer in time. Staff will review your application.")
                break

        # Finished answering
        if len(pending_recruits[uid]["answers"]) == len(RECRUIT_QUESTIONS):
            await dm.send("✅ Thank you! Your answers will be reviewed by the admins.")
            await notice.delete()

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
                for i, ans in enumerate(pending_recruits[uid]["answers"]):
                    formatted += f"**{labels[i]}**\n{ans}\n\n"
                embed = discord.Embed(
                    title=f"🪖 Recruit {member.display_name} for approval.",
                    description=f"{formatted}📅 **Date answered:** `{now_str}`",
                    color=discord.Color.blurple()
                )
                await admin_ch.send(embed=embed)

            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

    except Exception as e:
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        await recruit_ch.send(f"⚠️ {member.mention} did not respond to DMs. Admins have been notified.")

@client.event
async def on_raw_reaction_add(payload):
    """Handle admin reactions to approve/pardon recruits."""
    if payload.user_id == client.user.id:
        return  # ignore self reactions
    if payload.channel_id != CHANNELS["staff_review"]:
        return

    guild = client.get_guild(payload.guild_id)
    reactor = guild.get_member(payload.user_id)
    if not is_authorized(reactor):
        return

    emoji = str(payload.emoji)
    uid = None
    for rid, entry in pending_recruits.items():
        if entry.get("under_review") and entry.get("review_message_id") == payload.message_id:
            uid = rid
            break
    if not uid:
        return

    entry = pending_recruits[uid]
    recruit = guild.get_member(int(uid))
    approver = approver_label(reactor)
    staff_ch = client.get_channel(CHANNELS["staff_review"])

    if emoji.startswith("👍"):
        try:
            if recruit:
                await recruit.kick(reason="Rejected by admin vote")
                try:
                    dm = await recruit.create_dm()
                    await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                except Exception:
                    pass
            embed = discord.Embed(
                title=f"🪖 Recruit {recruit.display_name if recruit else uid} kicked out of Impedance",
                description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver}",
                color=discord.Color.red()
            )
            await staff_ch.send(embed=embed)
        except Exception as e:
            print(f"⚠️ Failed to kick recruit {uid}: {e}")

    elif emoji.startswith("👎"):
        embed = discord.Embed(
            title=f"🪖 Recruit {recruit.display_name if recruit else uid} pardoned",
            description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver}",
            color=discord.Color.green()
        )
        await staff_ch.send(embed=embed)

    del pending_recruits[uid]
    save_json(PENDING_FILE, pending_recruits)

@client.event
async def on_message(message):
    """Handle reminders every 50 messages."""
    if message.author.id == client.user.id:
        return
    if message.channel.id == CHANNELS["reminder"]:
        state["message_counter"] += 1
        save_json(STATE_FILE, state)
        if state["message_counter"] >= REMINDER_THRESHOLD:
            reminder = REMINDERS[state["current_reminder"]]
            embed = discord.Embed(
                title="Reminders Impedance!",
                description=f"**{reminder['title']}**\n\n{reminder['description']}",
                color=discord.Color.orange()
            )
            await message.channel.send(embed=embed)
            state["message_counter"] = 0
            state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
            save_json(STATE_FILE, state)

@client.event
async def on_presence_update(before, after):
    """Announce special members coming online."""
    if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
        member = after
        role_ids = [r.id for r in member.roles]
        if ROLES["queen"] in role_ids:
            title, color = f"👑 Queen {member.display_name} just came online!", discord.Color.gold()
        elif ROLES["clan_master"] in role_ids:
            title, color = f"🌟 Clan Master {member.display_name} just came online!", discord.Color.blue()
        elif ROLES["impedance"] in role_ids:
            title, color = f"⭐ Impedance {member.display_name} just came online!", discord.Color.purple()
        elif ROLES["og_impedance"] in role_ids:
            title, color = f"🎉 OG 🎉 {member.display_name} just came online!", discord.Color.red()
        else:
            return
        ch = client.get_channel(CHANNELS["main"])
        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=after.display_avatar.url)
        await ch.send(embed=embed)

# -------------------------
# === INACTIVITY CHECKER ===
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        now = now_ts()
        for uid, entry in list(pending_recruits.items()):
            if entry.get("under_review") or entry.get("resolved"):
                continue
            if now - entry.get("last_active", now) >= 600:
                recruit_ch = client.get_channel(CHANNELS["recruit"])
                try:
                    msg_id = entry.get("notify_msg")
                    if msg_id:
                        msg = await recruit_ch.fetch_message(msg_id)
                        await msg.delete()
                except Exception:
                    pass

                staff_ch = client.get_channel(CHANNELS["staff_review"])
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit for approval (ID {uid})",
                        description=(
                            "Recruit has not answered or refused to answer within 10 minutes.\n\n"
                            "Should the recruit be rejected and kicked out of the clan?\nReact 👍 to kick, 👎 to pardon."
                        ),
                        color=discord.Color.dark_gold()
                    )
                    msg = await staff_ch.send(embed=embed)
                    await msg.add_reaction("👍")
                    await msg.add_reaction("👎")
                    entry["under_review"] = True
                    entry["review_message_id"] = msg.id
                    save_json(PENDING_FILE, pending_recruits)
        await asyncio.sleep(60)

# -------------------------
# === RUN BOT ===
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN missing.")
        return
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    from keep_alive import ping_self
    threading.Thread(target=ping_self, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
