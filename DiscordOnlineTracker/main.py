# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app, ping_self   # ✅ FIXED IMPORT

# ----------------------------------
# CONFIGURATION (unchanged)
# ----------------------------------

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
    "4️⃣ Is the account you're using to apply in our clan your main account?",
    "5️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

REMINDERS = [
    {
        "title": "🟢 Activity Reminder",
        "description": "Members must keep their status set only to “Online” while active."
    },
    {
        "title": "🧩 IGN Format",
        "description": "All members must use the official clan format: IM-(Your IGN)."
    },
    {
        "title": "🔊 Voice Channel Reminder",
        "description": "Members online must join the Public Call channel."
    }
]

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}

def load_json(path, default):
    try:
        with open(path, "r") as f: return json.load(f)
    except: return default

def save_json(path, data):
    try:
        with open(path, "w") as f: json.dump(data, f)
    except: pass

def now_ts(): return int(time.time())
def readable_now(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_admin(member):
    if not member: return False
    ids = [r.id for r in member.roles]
    return (
        ROLES["queen"] in ids or
        ROLES["clan_master"] in ids or
        ROLES["og_impedance"] in ids
    )

def admin_label(member):
    if ROLES["queen"] in [r.id for r in member.roles]:
        return f"Queen {member.display_name}"
    if ROLES["clan_master"] in [r.id for r in member.roles]:
        return f"Clan Master {member.display_name}"
    if ROLES["og_impedance"] in [r.id for r in member.roles]:
        return f"OG-{member.display_name}"
    return member.display_name

# ----------------------------------
# PERSISTENT BUTTON VIEW
# ----------------------------------

class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_id=None):
        super().__init__(timeout=None)   # persistent
        self.recruit_id = recruit_id
        self.resolved = False

    async def _get_uid(self, msg_id):
        for uid, info in pending_recruits.items():
            if info.get("review_message_id") == msg_id:
                return uid
        return self.recruit_id

    async def resolve(self, interaction, decision):

        try:
            await interaction.response.defer()
        except:
            pass

        msg_id = interaction.message.id
        uid = await self._get_uid(msg_id)
        if not uid:
            return

        actor = interaction.user
        if not is_admin(actor):
            return

        self.resolved = True

        guild = interaction.guild
        recruit = guild.get_member(int(uid)) if guild else None
        recruit_name = recruit.display_name if recruit else f"ID {uid}"
        approver = admin_label(actor)

        # Disable buttons
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

        # Delete poll message
        try:
            await interaction.message.delete()
        except:
            pass

        staff_ch = client.get_channel(CHANNELS["staff_review"])

        if decision == "kick":
            try:
                if recruit:
                    await recruit.kick(reason="Rejected by admin decision")
                    try:
                        dm = await recruit.create_dm()
                        await dm.send("Your application was rejected. Thank you for applying.")
                    except:
                        pass
            except:
                pass

            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} kicked out of Impedance",
                description=f"Approved by: {approver}",
                color=discord.Color.red()
            )
            await staff_ch.send(embed=embed)

        else:  # pardon
            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} pardoned",
                description=f"Approved by: {approver}",
                color=discord.Color.green()
            )
            await staff_ch.send(embed=embed)

        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger, custom_id="approve_kick")
    async def kick_button(self, btn, interaction):
        await self.resolve(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success, custom_id="grant_pardon")
    async def pardon_button(self, btn, interaction):
        await self.resolve(interaction, "pardon")

# ----------------------------------
# BOT EVENTS
# ----------------------------------

@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)

    # Register persistent buttons
    client.add_view(AdminDecisionView())

    client.loop.create_task(inactivity_checker())
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_member_join(member):
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])

    await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Impedance!")

    notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
    uid = str(member.id)

    pending_recruits[uid] = {
        "started": now_ts(),
        "last": now_ts(),
        "answers": [],
        "announce": notice.id,
        "under_review": False,
        "review_message_id": None
    }
    save_json(PENDING_FILE, pending_recruits)

    # Try to DM questions
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to Impedance! Please answer the approval questions:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            msg = await client.wait_for(
                "message",
                timeout=600,
                check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel)
            )
            pending_recruits[uid]["answers"].append(msg.content)
            pending_recruits[uid]["last"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        await dm.send("✅ Thank you! Your answers will be reviewed.")

        try:
            msg = await recruit_ch.fetch_message(notice.id)
            await msg.delete()
        except:
            pass

        # Post results to admin review
        labels = [
            "Purpose of joining:",
            "Invited by:",
            "At least Major rank:",
            "Main account:",
            "Willing to CCN:"
        ]

        formatted = ""
        for i, ans in enumerate(pending_recruits[uid]["answers"]):
            formatted += f"**{labels[i]}**\n{ans}\n\n"

        embed = discord.Embed(
            title=f"📝 Recruit {member.display_name} (@{member.name}) for approval",
            description=formatted,
            color=discord.Color.blurple()
        )
        await staff_ch.send(embed=embed)

        del pending_recruits[uid]
        save_json(PENDING_FILE, pending_recruits)

    except:
        # DM failed → create poll
        embed = discord.Embed(
            title=f"🪖 Recruit {member.display_name} (@{member.name}) cannot be DMed",
            description="Should this recruit be kicked?\n(Admin vote required)",
            color=discord.Color.dark_gold()
        )
        view = AdminDecisionView(recruit_id=uid)
        msg = await staff_ch.send(embed=embed, view=view)
        pending_recruits[uid]["under_review"] = True
        pending_recruits[uid]["review_message_id"] = msg.id
        save_json(PENDING_FILE, pending_recruits)

# ----------------------------------
# REMINDERS
# ----------------------------------

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
                title="Impedance Reminders",
                description=f"**{r['title']}**\n\n{r['description']}",
                color=discord.Color.orange()
            )
            await message.channel.send(embed=embed)
            state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
            state["message_counter"] = 0
            save_json(STATE_FILE, state)

# ----------------------------------
# PRESENCE ANNOUNCEMENTS
# ----------------------------------

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
            await ch.send(embed=embed)
    except:
        pass

# ----------------------------------
# INACTIVITY CHECKER
# ----------------------------------

async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        now = now_ts()
        for uid, data in list(pending_recruits.items()):
            if data.get("under_review"):
                continue

            last = data.get("last", data["started"])
            if now - last >= 600:
                recruit_ch = client.get_channel(CHANNELS["recruit"])
                staff_ch = client.get_channel(CHANNELS["staff_review"])

                try:
                    msg = await recruit_ch.fetch_message(data["announce"])
                    await msg.delete()
                except:
                    pass

                guild = staff_ch.guild
                member = guild.get_member(int(uid))
                name = member.display_name if member else f"ID {uid}"

                embed = discord.Embed(
                    title=f"🪖 Recruit {name} requires decision",
                    description="Recruit ignored approval questions.\nShould we kick them?",
                    color=discord.Color.dark_gold()
                )

                view = AdminDecisionView(recruit_id=uid)
                poll_msg = await staff_ch.send(embed=embed, view=view)
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = poll_msg.id
                save_json(PENDING_FILE, pending_recruits)

        await asyncio.sleep(20)

# ----------------------------------
# RUN BOT
# ----------------------------------

def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    # start self-pinger (fixed)
    threading.Thread(target=ping_self, daemon=True).start()

    # run Flask server
    app.run(host="0.0.0.0", port=8080)
