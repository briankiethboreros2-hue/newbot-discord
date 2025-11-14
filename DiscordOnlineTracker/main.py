# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Fully rebuilt main.py with button-based admin polls and fixes.
# FIX comments mark important corrections requested.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # ensure keep_alive.ping_self exists

# -------------------------
# === CONFIG (leave as-is) ===
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,         # Main announcements
    "recruit": 1437568595977834590,      # Recruit public notice channel
    "reminder": 1369091668724154419,     # Reminder channel (tracked)
    "staff_review": 1437586858417852438  # Admin review channel
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "impedance": 1437570031822176408,
    "og_impedance": 1437572916005834793
}

REMINDER_THRESHOLD = 50  # messages
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

# Poll settings (1 hour max, but will resolve early on first valid admin vote)
POLL_DURATION_SECONDS = 60 * 60  # 1 hour

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
# UTILITIES
# -------------------------
def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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
    except:
        pass

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
    for k in ("queen", "clan_master", "og_impedance"):
        if ROLES[k] in role_ids:
            return True
    return False

# -------------------------
# === BUTTON POLL VIEW ===
# -------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid: str, created_at: int, timeout=POLL_DURATION_SECONDS):
        super().__init__(timeout=timeout)
        self.recruit_uid = recruit_uid
        self.created_at = created_at
        self.resolved = False

    async def resolve_decision(self, interaction: discord.Interaction, decision: str):
        if self.resolved:
            try:
                await interaction.response.send_message("This poll is already resolved.", ephemeral=True)
            except:
                pass
            return

        reactor = interaction.user
        if not is_authorized(reactor):
            await interaction.response.send_message("You are not authorized to vote.", ephemeral=True)
            return

        self.resolved = True
        uid = self.recruit_uid
        entry = pending_recruits.get(uid, {})
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        guild = interaction.guild

        recruit_member = guild.get_member(int(uid)) if guild else None
        approver_text = approver_label(reactor)

        if decision == "kick":
            kicked_name = recruit_member.display_name if recruit_member else f"ID {uid}"
            if recruit_member:
                try:
                    await recruit_member.kick(reason="Rejected by admin vote")
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("Your application was rejected. Thank you for your interest in Impedance.")
                    except:
                        pass
                except:
                    pass

            embed = discord.Embed(
                title=f"🪖 Recruit {kicked_name} kicked out of Impedance",
                description=f"Approved by: {approver_text}",
                color=discord.Color.red()
            )
            await staff_ch.send(embed=embed)

        if decision == "pardon":
            name = recruit_member.display_name if recruit_member else f"ID {uid}"
            embed = discord.Embed(
                title=f"🪖 Recruit {name} pardoned",
                description=f"Approved by: {approver_text}",
                color=discord.Color.green()
            )
            await staff_ch.send(embed=embed)

        # cleanup
        try:
            notice_id = entry.get("notify_msg")
            if notice_id:
                recruit_ch = client.get_channel(CHANNELS["recruit"])
                msg = await recruit_ch.fetch_message(notice_id)
                await msg.delete()
        except:
            pass

        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

        # disable buttons
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

        # delete poll
        try:
            await interaction.message.delete()
        except:
            pass

        await interaction.response.send_message(
            f"Decision recorded: **{decision.upper()}** — {approver_text}",
            ephemeral=True
        )

    # -------------------------
    # FIXED CALLBACKS (correct order!)
    # -------------------------
    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger)
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve_decision(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success)
    async def pardon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve_decision(interaction, "pardon")

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
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        return

    # Welcome
    try:
        await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")
    except:
        pass

    # Notice message (deleted later)
    try:
        msg = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check it.")
        notice_id = msg.id
    except:
        notice_id = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started_at": now_ts(),
        "last_active": now_ts(),
        "answers": [],
        "notify_msg": notice_id,
        "under_review": False,
        "review_message_id": None,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM interview
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer these questions one-by-one:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
            except:
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will review your application.")
                except:
                    pass
                return

            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        await dm.send("✅ Thank you! Your answers will be reviewed by admins.")

        # delete recruit notice
        try:
            notice_id = pending_recruits[uid]["notify_msg"]
            if notice_id:
                msg = await recruit_ch.fetch_message(notice_id)
                await msg.delete()
        except:
            pass

        # send formatted answers
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        formatted = ""
        labels = [
            "Purpose of joining:",
            "Invited by:",
            "Main Crossfire account:",
            "Willing to CCN:"
        ]

        for i, ans in enumerate(pending_recruits[uid]["answers"]):
            formatted += f"**{labels[i]}**\n{ans}\n\n"

        embed = discord.Embed(
            title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
            description=f"{formatted}",
            color=discord.Color.blurple()
        )
        await admin_ch.send(embed=embed)

        pending_recruits[uid]["resolved"] = True
        del pending_recruits[uid]
        save_json(PENDING_FILE, pending_recruits)

    except Exception:
        # DM failed — escalate immediately
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        display = f"{member.display_name} (@{member.name})"

        embed = discord.Embed(
            title=f"🪖 Recruit {display} for approval.",
            description="Recruit could not be DM'd. Decide their fate.",
            color=discord.Color.dark_gold()
        )

        view = AdminDecisionView(uid, now_ts())
        poll = await admin_ch.send(embed=embed, view=view)

        pending_recruits[uid]["under_review"] = True
        pending_recruits[uid]["review_message_id"] = poll.id
        save_json(PENDING_FILE, pending_recruits)

@client.event
async def on_message(message):
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
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            member = after
            role_ids = [r.id for r in member.roles]

            title, color = None, None
            if ROLES["queen"] in role_ids:
                title = f"👑 Queen {member.display_name} just came online!"
                color = discord.Color.gold()
            elif ROLES["clan_master"] in role_ids:
                title = f"🌟 Clan Master {member.display_name} just came online!"
                color = discord.Color.blue()
            elif ROLES["impedance"] in role_ids:
                title = f"⭐ Impedance {member.display_name} just came online!"
                color = discord.Color.purple()
            elif ROLES["og_impedance"] in role_ids:
                title = f"🎉 OG 🎉 {member.display_name} just came online!"
                color = discord.Color.red()

            if title:
                ch = client.get_channel(CHANNELS["main"])
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=after.display_avatar.url)
                await ch.send(embed=embed)

    except:
        pass

# -------------------------
# INACTIVITY CHECKER
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        now = now_ts()
        for uid, entry in list(pending_recruits.items()):
            if entry.get("resolved") or entry.get("under_review"):
                continue

            last = entry.get("last_active", entry.get("started_at"))
            if now - last >= 600:  # 10 minutes
                try:
                    recruit_ch = client.get_channel(CHANNELS["recruit"])
                    if entry.get("notify_msg"):
                        msg = await recruit_ch.fetch_message(entry["notify_msg"])
                        await msg.delete()
                except:
                    pass

                staff_ch = client.get_channel(CHANNELS["staff_review"])
                guild = staff_ch.guild
                member = guild.get_member(int(uid))
                display = f"{member.display_name} (@{member.name})" if member else f"ID {uid}"

                embed = discord.Embed(
                    title=f"🪖 Recruit {display} for approval.",
                    description="Recruit ignored the DM interview.\nDecide below:",
                    color=discord.Color.dark_gold()
                )

                view = AdminDecisionView(uid, now)
                poll = await staff_ch.send(embed=embed, view=view)

                entry["under_review"] = True
                entry["review_message_id"] = poll.id
                save_json(PENDING_FILE, pending_recruits)

        await asyncio.sleep(30)

# -------------------------
# RUN BOT
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
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except:
        pass

    app.run(host="0.0.0.0", port=8080)
