# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Clean full file – ONLY modification is adding Question #3 + label.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app

# -------------------------
# === CONFIG (unchanged) ===
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,
    "recruit": 1437568595977834590,
    "reminder": 1369091668724154419,
    "staff_review": 1437586858417852438
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

# -------------------------
# RECRUIT QUESTIONS (updated)
# -------------------------
RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ We require at least Major🎖 rank, are you at least Major First Class?",   # NEW
    "4️⃣ Is the account you're using to apply in our clan your main account?",
    "5️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

# -------------------------
# Reminder entries unchanged
# -------------------------
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

POLL_DURATION_SECONDS = 3600

# -------------------------
# SETUP
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
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_authorized(member):
    if not member:
        return False
    r = [role.id for role in member.roles]
    return (
        ROLES["queen"] in r or
        ROLES["clan_master"] in r or
        ROLES["og_impedance"] in r
    )

def approver_label(member):
    r = [role.id for role in member.roles]
    if ROLES["og_impedance"] in r:
        return f"OG-{member.display_name}"
    if ROLES["clan_master"] in r:
        return f"Clan Master {member.display_name}"
    if ROLES["queen"] in r:
        return f"Queen {member.display_name}"
    return member.display_name

# -----------------------------------------------------
# UI VIEW FOR POLL — FIXED (correct use of Interaction)
# -----------------------------------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid):
        super().__init__(timeout=POLL_DURATION_SECONDS)
        self.recruit_uid = recruit_uid
        self.resolved = False

    async def resolve_decision(self, interaction: discord.Interaction, decision: str):
        if self.resolved:
            await interaction.response.send_message("This poll is already resolved.", ephemeral=True)
            return

        reactor = interaction.user
        if not is_authorized(reactor):
            await interaction.response.send_message("You are not authorized for this action.", ephemeral=True)
            return

        self.resolved = True
        uid = self.recruit_uid
        entry = pending_recruits.get(uid, {})
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        guild = staff_ch.guild

        # get recruit member
        recruit_member = guild.get_member(int(uid))
        recruit_name = recruit_member.display_name if recruit_member else f"ID {uid}"
        approver = approver_label(reactor)

        # Kick logic
        if decision == "kick":
            if recruit_member:
                try:
                    await recruit_member.kick(reason="Rejected by admin decision")
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("Your application was rejected. Thank you for your interest in joining Impedance.")
                    except:
                        pass
                except:
                    pass

            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} kicked out of Impedance",
                description=f"Action approved by: **{approver}**",
                color=discord.Color.red()
            )
            await staff_ch.send(embed=embed)

        # Pardon logic
        else:
            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} pardoned",
                description=f"Approved by: **{approver}**",
                color=discord.Color.green()
            )
            await staff_ch.send(embed=embed)

        # cleanup
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

        # disable buttons
        for c in self.children:
            c.disabled = True
        await interaction.message.edit(view=self)

        # ephemeral confirmation
        await interaction.response.send_message(f"Decision recorded: **{decision}**", ephemeral=True)

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger)
    async def kick_button(self, button, interaction):
        await self.resolve_decision(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success)
    async def pardon_button(self, button, interaction):
        await self.resolve_decision(interaction, "pardon")

# -------------------------
# EVENTS
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
    await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")

    notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
    notice_id = notice.id

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

    # DM questions
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome! Please answer these questions one by one.")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                msg = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
            except asyncio.TimeoutError:
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                await dm.send("⏳ You did not answer in time. Staff will review your application.")
                return

            pending_recruits[uid]["answers"].append(msg.content)
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        await dm.send("✅ Thank you! Your answers have been submitted for review.")

        # delete recruit notice
        try:
            msg = await recruit_ch.fetch_message(notice_id)
            await msg.delete()
        except:
            pass

        # send formatted answers
        admin = client.get_channel(CHANNELS["staff_review"])
        now_str = readable_now()
        labels = [
            "Purpose of joining:",
            "Invited by an Impedance member, and who:",
            "Atleast Major or up rank:",          # NEW LABEL
            "Main Crossfire account:",
            "Willing to CCN:"
        ]

        formatted = ""
        for i, ans in enumerate(pending_recruits[uid]["answers"]):
            formatted += f"**{labels[i]}**\n{ans}\n\n"

        embed = discord.Embed(
            title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
            description=f"{formatted}📅 **Date answered:** `{now_str}`",
            color=discord.Color.blurple()
        )
        await admin.send(embed=embed)

        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        del pending_recruits[uid]
        save_json(PENDING_FILE, pending_recruits)

    except Exception:
        # DM failed → escalate
        admin = client.get_channel(CHANNELS["staff_review"])
        embed = discord.Embed(
            title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
            description="Recruit did not respond to DMs.\nPlease vote below.",
            color=discord.Color.gold()
        )
        view = AdminDecisionView(uid)
        poll = await admin.send(embed=embed, view=view)
        view.message = poll

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
            r = REMINDERS[state["current_reminder"]]
            embed = discord.Embed(
                title="Reminders Impedance!",
                description=f"**{r['title']}**\n\n{r['description']}",
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
            r = [role.id for role in member.roles]
            title = None
            color = None

            if ROLES["queen"] in r:
                title = f"👑 Queen {member.display_name} just came online!"
                color = discord.Color.gold()
            elif ROLES["clan_master"] in r:
                title = f"🌟 Clan Master {member.display_name} just came online!"
                color = discord.Color.blue()
            elif ROLES["impedance"] in r:
                title = f"⭐ Impedance {member.display_name} just came online!"
                color = discord.Color.purple()
            elif ROLES["og_impedance"] in r:
                title = f"🎉 OG 🎉 {member.display_name} just came online!"
                color = discord.Color.red()

            if title:
                ch = client.get_channel(CHANNELS["main"])
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=after.display_avatar.url)
                await ch.send(embed=embed)
    except:
        pass

# -----------------------------------------------------
# INACTIVITY CHECKER
# -----------------------------------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        now = now_ts()
        for uid, entry in list(pending_recruits.items()):
            if entry.get("resolved") or entry.get("under_review"):
                continue

            last = entry.get("last_active", entry["started_at"])

            if now - last >= 600:
                admin = client.get_channel(CHANNELS["staff_review"])

                guild = admin.guild
                recruit_member = guild.get_member(int(uid))
                display_name = f"{recruit_member.display_name} (@{recruit_member.name})" if recruit_member else f"ID {uid}"

                embed = discord.Embed(
                    title=f"🪖 Recruit {display_name} for approval.",
                    description="Recruit has not answered within 10 minutes.\nPlease vote below.",
                    color=discord.Color.gold()
                )
                view = AdminDecisionView(uid)
                poll = await admin.send(embed=embed, view=view)
                view.message = poll

                entry["under_review"] = True
                entry["review_message_id"] = poll.id
                save_json(PENDING_FILE, pending_recruits)

        await asyncio.sleep(30)

# -------------------------
# RUN BOT
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
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
