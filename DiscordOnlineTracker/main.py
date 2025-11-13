# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Final integrated bot file — includes recruit DM interview, admin review, reminders, and presence tracking.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # must provide ping_self()

# -------------------------
# === CONFIG (easy edit) ===
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,         # Main announcements
    "recruit": 1437568595977834590,      # Recruit channel
    "reminder": 1369091668724154419,     # Reminder message channel
    "staff_review": 1437586858417852438  # Admin review channel
}

ROLES = {
    "queen": 1437578521374363769,        # Queen👑
    "clan_master": 1389835747040694332,  # Cᥣᥲᥒ  Mᥲstᥱr🌟
    "impedance": 1437570031822176408,    # Impedance⭐
    "og_impedance": 1437572916005834793  # OG-Impedance🔫
}

REMINDER_THRESHOLD = 50  # send a reminder every 50 messages

# Persistent files
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"

# Recruit DM questions
RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ Is the account you're using to apply in our clan your main account?",
    "4️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

# Reminder messages
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
# === END CONFIG ===
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
# === Utility Functions ===
# -------------------------
def load_json(file, default):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"⚠️ Error loading {file}: {e}")
        return default

def save_json(file, data):
    try:
        with open(file, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"⚠️ Error saving {file}: {e}")

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_authorized(member):
    if not member:
        return False
    role_ids = [r.id for r in member.roles]
    return any(ROLES[k] in role_ids for k in ["queen", "clan_master", "og_impedance"])

def approver_label(member):
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

# -------------------------
# === Events ===
# -------------------------
@client.event
async def on_ready():
    global state, pending_recruits
    print(f"✅ Logged in as {client.user}")
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)
    client.loop.create_task(inactivity_checker())
    print("🕓 Bot ready and running.")

@client.event
async def on_member_join(member):
    """Announce new recruit and start DM interview."""
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        print("⚠️ Recruit channel not found.")
        return

    # 🎉 Announce new recruit joining
    try:
        await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")
    except Exception:
        pass

    # Notify recruit to check DMs
    notify_msg = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
    notify_msg_id = notify_msg.id

    uid = str(member.id)
    pending_recruits[uid] = {
        "step": 0,
        "answers": [],
        "started_at": now_ts(),
        "last_active": now_ts(),
        "notify_message_id": notify_msg_id,
        "under_review": False,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM interview
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer the following approval questions one by one:")

        for q_idx, q in enumerate(RECRUIT_QUESTIONS):
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
            except asyncio.TimeoutError:
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                return

            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["step"] = q_idx + 1
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        await dm.send(
            "✅ Thank you for your cooperation! We’re looking forward to welcoming you to Impedance.\n"
            "Your answers will be reviewed by the admins. Please wait for further instructions."
        )

        # ✅ Delete the “check your DMs” message now
        try:
            msg = await recruit_ch.fetch_message(notify_msg_id)
            await msg.delete()
        except Exception:
            pass

        # Send answers to admin review
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

        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        del pending_recruits[uid]
        save_json(PENDING_FILE, pending_recruits)

    except Exception as e:
        print(f"⚠️ DM failed for {member.display_name}: {e}")
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {member.display_name} for approval.",
                description=(
                    "Could not DM recruit or recruit blocked DMs.\n\n"
                    "Should the recruit be rejected and kicked out of the clan server?\n"
                    "React 👍 to **kick**, 👎 to **pardon**."
                ),
                color=discord.Color.dark_gold()
            )
            review_msg = await admin_ch.send(embed=embed)
            await review_msg.add_reaction("👍")
            await review_msg.add_reaction("👎")
            pending_recruits[uid]["under_review"] = True
            pending_recruits[uid]["review_message_id"] = review_msg.id
            save_json(PENDING_FILE, pending_recruits)

# -------------------------
# === Reminders & Reactions ===
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
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

# === Presence announcement ===
@client.event
async def on_presence_update(before, after):
    if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
        member = after
        role_ids = [r.id for r in member.roles]
        title, color = None, None
        if ROLES["queen"] in role_ids:
            title, color = f"👑 Queen {member.display_name} just came online!", discord.Color.gold()
        elif ROLES["clan_master"] in role_ids:
            title, color = f"🌟 Clan Master {member.display_name} just came online!", discord.Color.blue()
        elif ROLES["impedance"] in role_ids:
            title, color = f"⭐ Impedance {member.display_name} just came online!", discord.Color.purple()
        elif ROLES["og_impedance"] in role_ids:
            title, color = f"🎉 OG 🎉 {member.display_name} just came online!", discord.Color.red()
        if title:
            ch = client.get_channel(CHANNELS["main"])
            embed = discord.Embed(title=title, color=color)
            embed.set_thumbnail(url=after.display_avatar.url)
            await ch.send(embed=embed)

# === Inactivity checker ===
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        now = now_ts()
        for uid, entry in list(pending_recruits.items()):
            if entry.get("resolved") or entry.get("under_review"):
                continue
            last = entry.get("last_active", entry.get("started_at", now))
            if now - last >= 600:
                staff_ch = client.get_channel(CHANNELS["staff_review"])
                display_name = "Unknown"
                for g in client.guilds:
                    m = g.get_member(int(uid))
                    if m:
                        display_name = m.display_name
                        break
                embed = discord.Embed(
                    title=f"🪖 Recruit {display_name} for approval.",
                    description=(
                        "Has not answered or refused to answer within 10 minutes.\n\n"
                        "Should the recruit be rejected and kicked out of the clan?\n"
                        "React 👍 to **kick** or 👎 to **pardon**."
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
# === Run Bot ===
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
