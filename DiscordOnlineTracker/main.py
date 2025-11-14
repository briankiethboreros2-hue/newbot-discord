# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Full file with ONLY Option A fix applied:
# ❗ Recruit is removed from pending_recruits ONLY after completing ALL answers.
# ❗ If recruit ignores/does not answer: entry is kept, inactivity checker works.

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
        "description": "Members must keep their status set only to “Online” while active."
    },
    {
        "title": "🧩 IGN Format",
        "description": "All members must use the official format: `IM-(Your IGN)`"
    },
    {
        "title": "🔊 Voice Channel Requirement",
        "description": "Join **Public Call** when online. Open mic is required."
    }
]

POLL_DURATION_SECONDS = 3600  # 1 hour max

# -------------------------
# INTENTS
# -------------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# STATE
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}  # uid -> dict


# -------------------------
# UTILS
# -------------------------
def now_ts(): return int(time.time())
def readable_now(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def approver_label(member):
    if not member:
        return "Unknown"
    r = [r.id for r in member.roles]
    if ROLES["og_impedance"] in r:
        return f"OG-{member.display_name}"
    if ROLES["clan_master"] in r:
        return f"Clan Master {member.display_name}"
    if ROLES["queen"] in r:
        return f"Queen {member.display_name}"
    return member.display_name

def is_authorized(member):
    if not member:
        return False
    r = [r.id for r in member.roles]
    return any(ROLES[k] in r for k in ("queen", "clan_master", "og_impedance"))


# -------------------------
# ADMIN DECISION POLL VIEW
# -------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid):
        super().__init__(timeout=POLL_DURATION_SECONDS)
        self.recruit_uid = recruit_uid
        self.resolved = False

    async def finalize(self, interaction, decision):
        if self.resolved:
            try:
                await interaction.response.send_message("Already resolved.", ephemeral=True)
            except:
                pass
            return

        voter = interaction.user
        if not is_authorized(voter):
            try:
                await interaction.response.send_message("You are not authorized.", ephemeral=True)
            except:
                pass
            return

        self.resolved = True
        uid = self.recruit_uid
        entry = pending_recruits.get(uid)
        guild = interaction.guild
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        recruit_member = guild.get_member(int(uid)) if guild else None

        approver = approver_label(voter)

        # --- KICK ---
        if decision == "kick":
            name = recruit_member.display_name if recruit_member else f"ID {uid}"
            if recruit_member:
                try:
                    await recruit_member.kick(reason="Rejected after inactivity")
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("Your application was rejected. Thank you for applying.")
                    except:
                        pass
                except:
                    pass

            embed = discord.Embed(
                title=f"🪖 Recruit {name} kicked.",
                description=f"Action approved by: **{approver}**",
                color=discord.Color.red()
            )
            if staff_ch:
                await staff_ch.send(embed=embed)

        # --- PARDON ---
        if decision == "pardon":
            name = recruit_member.display_name if recruit_member else f"ID {uid}"
            embed = discord.Embed(
                title=f"🪖 Recruit {name} pardoned.",
                description=f"Decision approved by: **{approver}**",
                color=discord.Color.green()
            )
            if staff_ch:
                await staff_ch.send(embed=embed)

        # CLEANUP ENTRY (Option A fix keeps it only until resolved)
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

        # Disable buttons + delete poll
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass
        try:
            await interaction.message.delete()
        except:
            pass

        try:
            await interaction.response.send_message(f"Decision recorded: {decision.upper()}", ephemeral=True)
        except:
            pass

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger)
    async def kick_button(self, button, interaction):
        await self.finalize(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success)
    async def pardon_button(self, button, interaction):
        await self.finalize(interaction, "pardon")


# -------------------------
# READY
# -------------------------
@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)
    client.loop.create_task(inactivity_checker())
    print(f"Logged in as {client.user}")


# -------------------------
# MEMBER JOIN → DM INTERVIEW
# -------------------------
@client.event
async def on_member_join(member):

    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if recruit_ch:
        await recruit_ch.send(f"🎉 Welcome {member.mention}!")
        notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM!")
        notice_id = notice.id
    else:
        notice_id = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started_at": now_ts(),
        "last_active": now_ts(),
        "answers": [],
        "notify_msg": notice_id,
        "under_review": False,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM FLOW
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance**! Please answer the questions:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
            except asyncio.TimeoutError:
                # Recruit failed to answer → Keep entry (Option A)
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                await dm.send("⏳ You did not answer in time. Admins will review your application.")
                return

            pending_recruits[uid]["answers"].append(reply.content)
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # COMPLETED SUCCESSFULLY → NOW delete entry (Option A)
        await dm.send("✅ Thank you! Your answers will be reviewed.")

        # Delete public notice now
        try:
            if notice_id:
                msg = await recruit_ch.fetch_message(notice_id)
                await msg.delete()
        except:
            pass

        # Build formatted admin message
        labels = [
            "Purpose of joining:",
            "Invited by whom:",
            "At least Major or up rank:",
            "Main Crossfire account:",
            "Willing to CCN:"
        ]
        formatted = ""
        for i, ans in enumerate(pending_recruits[uid]["answers"]):
            formatted += f"**{labels[i]}**\n{ans}\n\n"

        admin_ch = client.get_channel(CHANNELS["staff_review"])
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
                description=f"{formatted}\n📅 {readable_now()}",
                color=discord.Color.blurple()
            )
            await admin_ch.send(embed=embed)

        # NOW SAFE TO DELETE ENTRY
        del pending_recruits[uid]
        save_json(PENDING_FILE, pending_recruits)

    except Exception as e:
        print(f"DM error: {e}")
        # escalate immediately if DM failed
        await escalate_to_poll(uid, member)
# -------------------------
# ESCALATION FUNCTION (DM failed or timeout)
# -------------------------
async def escalate_to_poll(uid, member):
    """Creates a poll in admin review channel if recruit ignores/blocks DM."""
    staff_ch = client.get_channel(CHANNELS["staff_review"])
    recruit_ch = client.get_channel(CHANNELS["recruit"])

    display = f"{member.display_name} (@{member.name})"

    # delete recruit notice if exists
    entry = pending_recruits.get(uid)
    if entry and entry.get("notify_msg"):
        try:
            msg = await recruit_ch.fetch_message(entry["notify_msg"])
            await msg.delete()
        except:
            pass

    if staff_ch:
        embed = discord.Embed(
            title=f"🪖 Recruit {display} for approval.",
            description=(
                "Recruit did not answer or blocked DMs.\n\n"
                "Should the recruit be **kicked** or **pardoned**?\n"
                "Only authorized admins may vote."
            ),
            color=discord.Color.dark_gold()
        )

        view = AdminDecisionView(uid)
        poll_msg = await staff_ch.send(embed=embed, view=view)

        # store poll ID
        pending_recruits[uid]["under_review"] = True
        pending_recruits[uid]["poll_msg"] = poll_msg.id
        save_json(PENDING_FILE, pending_recruits)

    # notify recruit channel
    try:
        await recruit_ch.send(f"⚠️ {member.mention} did not respond. Admins will review the application.")
    except:
        pass


# -------------------------
# ON MESSAGE (reminder logic)
# -------------------------
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
            try:
                await message.channel.send(embed=embed)
            except:
                pass

            # rotate reminders
            state["message_counter"] = 0
            state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
            save_json(STATE_FILE, state)


# -------------------------
# PRESENCE ANNOUNCEMENTS
# -------------------------
@client.event
async def on_presence_update(before, after):
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            member = after
            r = [r.id for r in member.roles]

            ch = client.get_channel(CHANNELS["main"])
            if not ch:
                return

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
                title = f"🎉 OG {member.display_name} just came online!"
                color = discord.Color.red()

            if title:
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await ch.send(embed=embed)
                except:
                    pass
    except Exception as e:
        print(f"Presence error: {e}")


# -------------------------
# INACTIVITY CHECKER (every 30s)
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    print("🔍 inactivity_checker running…")

    while not client.is_closed():
        try:
            now = now_ts()

            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue

                last = entry.get("last_active", entry["started_at"])
                if now - last >= 600:  # 10min
                    # fetch guild + member
                    member = None
                    for g in client.guilds:
                        m = g.get_member(int(uid))
                        if m:
                            member = m
                            break

                    if not member:
                        # user left the server
                        pending_recruits[uid]["resolved"] = True
                        save_json(PENDING_FILE, pending_recruits)
                        continue

                    print(f"⏳ Recruit {member.display_name} inactive → escalating.")
                    await escalate_to_poll(uid, member)

            await asyncio.sleep(30)

        except Exception as e:
            print("inactivity_checker error:", e)
            await asyncio.sleep(30)


# -------------------------
# RUN BOT
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN missing!")
        return

    print("🤖 Starting bot...")
    time.sleep(3)
    client.run(token)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except:
        pass

    app.run(host="0.0.0.0", port=8080)
