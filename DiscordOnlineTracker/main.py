# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# FULL main.py — ONLY the button interaction fix applied.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app

# -------------------------
# === CONFIG ===
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

RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ We require at least **Major 🎖 rank**. Are you at least **Major First Class**?",
    "4️⃣ Is the account you're using to apply in our clan your main account?",
    "5️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
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

POLL_DURATION_SECONDS = 3600  # 1 hour

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
# === HELPERS ===
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
    return (
        ROLES["queen"] in role_ids
        or ROLES["clan_master"] in role_ids
        or ROLES["og_impedance"] in role_ids
    )


# -------------------------
# === POLL BUTTONS (FIXED) ===
# -------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid: str, timeout=POLL_DURATION_SECONDS):
        super().__init__(timeout=timeout)
        self.recruit_uid = recruit_uid
        self.resolved = False

    async def resolve_decision(self, interaction: discord.Interaction, decision: str):
        if self.resolved:
            # SAFE fix
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("This poll was already resolved.", ephemeral=True)
            return

        reactor = interaction.user  
        if not is_authorized(reactor):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("You are not authorized.", ephemeral=True)
            return

        self.resolved = True

        uid = self.recruit_uid
        entry = pending_recruits.get(uid, {})
        staff_ch = client.get_channel(CHANNELS["staff_review"])

        guild = interaction.guild
        recruit_member = guild.get_member(int(uid)) if guild else None

        approver = approver_label(reactor)
        recruit_name = recruit_member.display_name if recruit_member else f"ID {uid}"

        # ========== KICK ==========
        if decision == "kick":
            if recruit_member:
                try:
                    await recruit_member.kick(reason="Rejected by admin")
                except:
                    pass

                try:
                    dm = await recruit_member.create_dm()
                    await dm.send("Your application was rejected by the admins.")
                except:
                    pass

            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} kicked out",
                description=f"Approved by: {approver}",
                color=discord.Color.red()
            )
            await staff_ch.send(embed=embed)

        # ========== PARDON ==========
        if decision == "pardon":
            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} pardoned",
                description=f"Approved by: {approver}",
                color=discord.Color.green()
            )
            await staff_ch.send(embed=embed)

        # Cleanup
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

        # Disable buttons
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

        # SAFE FIX – prevent Unknown Interaction
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            f"Decision recorded: **{decision.upper()}** — by {approver}",
            ephemeral=True
        )

    # BUTTON: Kick
    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger, custom_id="btn_kick")
    async def kick_button(self, button, interaction):
        await self.resolve_decision(interaction, "kick")

    # BUTTON: Pardon
    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success, custom_id="btn_pardon")
    async def pardon_button(self, button, interaction):
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

    notice = await recruit_ch.send(
        f"🪖 {member.mention}, I have sent you a DM. Please check your inbox."
    )

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

    # DM questions
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer the following questions:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    timeout=600,
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel)
                )
            except:
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                await dm.send("⏳ You did not answer in time. Admins will review your application.")
                return

            pending_recruits[uid]["answers"].append(reply.content)
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # delete notice
        try:
            msg = await recruit_ch.fetch_message(pending_recruits[uid]["notify_msg"])
            await msg.delete()
        except:
            pass

        # send answers to staff
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        now_str = readable_now()

        labels = [
            "Purpose of joining:",
            "Invited by an Impedance member, and who:",
            "At least Major rank:",
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
        await staff_ch.send(embed=embed)

        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        del pending_recruits[uid]
        save_json(PENDING_FILE, pending_recruits)

    except Exception as e:
        print("DM failed:", e)


# -------------------------
# === INACTIVITY CHECKER ===
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()

    while True:
        now = now_ts()

        for uid, entry in list(pending_recruits.items()):
            if entry.get("resolved") or entry.get("under_review"):
                continue

            last = entry.get("last_active", entry["started_at"])

            if now - last >= 600:
                staff_ch = client.get_channel(CHANNELS["staff_review"])
                guild = staff_ch.guild
                member = guild.get_member(int(uid))
                display_name = member.display_name if member else f"ID {uid}"

                embed = discord.Embed(
                    title=f"🪖 Recruit {display_name} for approval.",
                    description="Recruit ignored the DM interview.\n\nAdmins — choose what action should be taken:",
                    color=discord.Color.orange()
                )

                view = AdminDecisionView(uid)
                poll_msg = await staff_ch.send(embed=embed, view=view)

                pending_recruits[uid]["under_review"] = True
                save_json(PENDING_FILE, pending_recruits)

        await asyncio.sleep(30)


# -------------------------
# === RUN BOT ===
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    time.sleep(5)
    client.run(token)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    from keep_alive import ping_self
    threading.Thread(target=ping_self, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
