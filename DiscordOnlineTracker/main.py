# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app

# ----------------------------------
# CONFIGURATION (leave unchanged)
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
# BUTTON VIEW (Silent Defer)
# ----------------------------------

class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_id):
        super().__init__(timeout=3600)
        self.recruit_id = recruit_id
        self.resolved = False

    async def resolve(self, interaction, decision):
        if self.resolved:
            return

        # ALWAYS SILENT DEFER FIRST
        await interaction.response.defer()

        admin = interaction.user
        if not is_admin(admin):
            return  # silently ignore unauthorized presses

        self.resolved = True
        guild = interaction.guild
        staff_ch = client.get_channel(CHANNELS["staff_review"])

        recruit = guild.get_member(int(self.recruit_id))
        recruit_name = recruit.display_name if recruit else f"ID {self.recruit_id}"
        approver = admin_label(admin)

        # Disable buttons immediately
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

        # DELETE POLL MESSAGE
        try:
            await interaction.message.delete()
        except:
            pass

        # EXECUTE DECISION
        if decision == "kick":
            if recruit:
                try:
                    await recruit.kick()
                    try:
                        dm = await recruit.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected.")
                    except:
                        pass
                except:
                    pass

            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} kicked",
                description=f"Approved by **{approver}**",
                color=discord.Color.red()
            )
            await staff_ch.send(embed=embed)

        else:  # PARDON
            embed = discord.Embed(
                title=f"🪖 Recruit {recruit_name} pardoned",
                description=f"Approved by **{approver}**",
                color=discord.Color.green()
            )
            await staff_ch.send(embed=embed)

        if self.recruit_id in pending_recruits:
            del pending_recruits[self.recruit_id]
            save_json(PENDING_FILE, pending_recruits)

    # Buttons
    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger)
    async def kick_button(self, btn, interaction):
        await self.resolve(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success)
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
    client.loop.create_task(inactivity_checker())
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_member_join(member):
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])

    await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Impedance!")

    notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
    notice_id = notice.id

    uid = str(member.id)
    pending_recruits[uid] = {
        "started": now_ts(),
        "last": now_ts(),
        "answers": [],
        "announce": notice_id,
        "under_review": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM QUESTIONS
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

        await dm.send("✅ Thank you! Your answers will be reviewed by admins.")

        # Delete notice
        try:
            msg = await recruit_ch.fetch_message(notice_id)
            await msg.delete()
        except:
            pass

        # Post to admin review
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

    except Exception:
        # DM FAILED -> Immediate Poll
        view = AdminDecisionView(uid)
        embed = discord.Embed(
            title=f"🪖 Recruit {member.display_name} (@{member.name}) cannot be DMed",
            description="Should this recruit be kicked?\n(Admin vote required)",
            color=discord.Color.dark_gold()
        )
        msg = await staff_ch.send(embed=embed, view=view)
        pending_recruits[uid]["under_review"] = True
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
                title="Impedance Reminders",
                description=f"**{r['title']}**\n\n{r['description']}",
                color=discord.Color.orange()
            )
            await message.channel.send(embed=embed)
            state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
            state["message_counter"] = 0
            save_json(STATE_FILE, state)

@client.event
async def on_presence_update(before, after):
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            m = after
            ids = [r.id for r in m.roles]
            ch = client.get_channel(CHANNELS["main"])

            if ROLES["queen"] in ids:
                t, c = f"👑 Queen {m.display_name} just came online!", discord.Color.gold()
            elif ROLES["clan_master"] in ids:
                t, c = f"🌟 Clan Master {m.display_name} just came online!", discord.Color.blue()
            elif ROLES["og_impedance"] in ids:
                t, c = f"🎉 OG {m.display_name} online!", discord.Color.red()
            elif ROLES["impedance"] in ids:
                t, c = f"⭐ Member {m.display_name} just came online!", discord.Color.purple()
            else:
                return

            embed = discord.Embed(title=t, color=c)
            embed.set_thumbnail(url=after.display_avatar.url)
            await ch.send(embed=embed)
    except:
        pass

# ----------------------------------
# INACTIVITY CHECKER (10 min)
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

                # delete recruit’s notice
                try:
                    if data.get("announce"):
                        msg = await recruit_ch.fetch_message(data["announce"])
                        await msg.delete()
                except:
                    pass

                staff_ch = client.get_channel(CHANNELS["staff_review"])
                guild = staff_ch.guild
                member = guild.get_member(int(uid))
                name = member.display_name if member else f"ID {uid}"

                embed = discord.Embed(
                    title=f"🪖 Recruit {name} requires decision",
                    description="Recruit ignored approval questions.\nShould we kick them?",
                    color=discord.Color.dark_gold()
                )

                view = AdminDecisionView(uid)
                await staff_ch.send(embed=embed, view=view)

                pending_recruits[uid]["under_review"] = True
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
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except:
        pass
    app.run(host="0.0.0.0", port=8080)
