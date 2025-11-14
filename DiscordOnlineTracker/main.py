# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Final full main.py — Version 2 (button-based approval).
# Fix: interaction response sent BEFORE editing/deleting poll message to avoid Unknown Interaction.

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # keep_alive.py must define ping_self()

# -------------------------
# CONFIG (editable constants)
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,       # Main announcements
    "recruit": 1437568595977834590,    # Recruit notice channel
    "reminder": 1369091668724154419,   # Reminder channel (tracked)
    "staff_review": 1437586858417852438 # Admin review channel
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "impedance": 1437570031822176408,
    "og_impedance": 1437572916005834793
}

REMINDER_THRESHOLD = 50  # messages until next reminder
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"
POLL_DURATION_SECONDS = 60 * 60  # 1 hour, but resolves early on first admin click
INACTIVITY_SECONDS = 10 * 60     # 10 minutes to escalate

# Recruit DM questions (note we added the "Major rank" question as requested)
RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ We require at least Major 🎖 rank — are you at least Major First Class?",
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
        "description": "When online, you must join the **Public Call** channel. Open mic is required — be respectful and avoid mic spam."
    }
]

# -------------------------
# BOT SETUP
# -------------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# Persistent state
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}  # str(user_id) -> metadata dict

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
    if ROLES.get("og_impedance") and ROLES["og_impedance"] in role_ids:
        return f"OG-{member.display_name}"
    if ROLES.get("clan_master") and ROLES["clan_master"] in role_ids:
        return f"Clan Master {member.display_name}"
    if ROLES.get("queen") and ROLES["queen"] in role_ids:
        return f"Queen {member.display_name}"
    return member.display_name

def is_authorized(member: discord.Member):
    if not member:
        return False
    role_ids = [r.id for r in member.roles]
    return any(ROLES.get(k) and ROLES[k] in role_ids for k in ("queen", "clan_master", "og_impedance"))

# -------------------------
# ADMIN POLL VIEW (buttons)
# -------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid: str, timeout=POLL_DURATION_SECONDS):
        super().__init__(timeout=timeout)
        self.recruit_uid = recruit_uid
        self.resolved = False

    async def _finalize(self, interaction: discord.Interaction, decision: str):
        """Handle the decision. IMPORTANT: send interaction response FIRST to avoid Unknown Interaction."""
        # If already resolved, acknowledge and exit
        if self.resolved:
            try:
                await interaction.response.send_message("This poll was already resolved.", ephemeral=True)
            except Exception:
                pass
            return

        voter = interaction.user
        if not is_authorized(voter):
            try:
                await interaction.response.send_message("You are not authorized to decide on recruits.", ephemeral=True)
            except Exception:
                pass
            return

        self.resolved = True
        uid = self.recruit_uid
        entry = pending_recruits.get(uid, {})
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        # find recruit member across guilds
        recruit_member = None
        for g in client.guilds:
            m = g.get_member(int(uid))
            if m:
                recruit_member = m
                break

        approver_text = approver_label(voter)
        recruit_display = recruit_member.display_name if recruit_member else f"ID {uid}"

        # 1) Respond to interaction (ephemeral) FIRST — this avoids Unknown Interaction
        try:
            await interaction.response.send_message(f"Decision recorded: **{decision.upper()}** — approved by {approver_text}", ephemeral=True)
        except Exception:
            # if this fails, try defer+followup as fallback
            try:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(f"Decision recorded: **{decision.upper()}** — approved by {approver_text}", ephemeral=True)
            except Exception:
                pass

        # 2) Execute action & post public summary
        if decision == "kick":
            kicked_name = recruit_display
            if recruit_member:
                try:
                    await recruit_member.kick(reason="Rejected by admin vote")
                except Exception as e:
                    print(f"⚠️ Failed to kick {recruit_display}: {e}")
                # DM recruit about rejection
                try:
                    dm = await recruit_member.create_dm()
                    await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest.")
                except Exception:
                    pass

            # Post summary to staff channel
            if staff_ch:
                embed = discord.Embed(
                    title=f"🪖 Recruit {kicked_name} kicked out of Impedance",
                    description=(f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver_text}"),
                    color=discord.Color.red()
                )
                try:
                    await staff_ch.send(embed=embed)
                except Exception:
                    pass

        elif decision == "pardon":
            pardoned_name = recruit_display
            if staff_ch:
                embed = discord.Embed(
                    title=f"🪖 Recruit {pardoned_name} pardoned",
                    description=(f"Despite not answering, the recruit was pardoned.\n\nApproved by: {approver_text}"),
                    color=discord.Color.green()
                )
                try:
                    await staff_ch.send(embed=embed)
                except Exception:
                    pass

        # 3) Cleanup pending entry
        if uid in pending_recruits:
            # also try delete public notice in recruit channel if present
            try:
                notify_msg_id = pending_recruits[uid].get("notify_msg")
                if notify_msg_id:
                    rc = client.get_channel(CHANNELS["recruit"])
                    if rc:
                        try:
                            msg = await rc.fetch_message(notify_msg_id)
                            await msg.delete()
                        except Exception:
                            pass
            except Exception:
                pass

            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

        # 4) Disable buttons in the UI (edit message)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # 5) Delete the poll message after responding & editing (safe)
        try:
            await interaction.message.delete()
        except Exception:
            pass

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger, custom_id="kick_button")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success, custom_id="pardon_button")
    async def pardon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, "pardon")

# -------------------------
# Load/save startup
# -------------------------
@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)
    client.loop.create_task(inactivity_checker())
    print(f"✅ Logged in as {client.user}")

# -------------------------
# on_member_join -> DM interview
# -------------------------
@client.event
async def on_member_join(member):
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        print("⚠️ Recruit channel not found.")
        return

    # Public welcome + DM notice (will be deleted later)
    try:
        await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")
    except Exception:
        pass

    notice_msg = None
    try:
        notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
        notice_msg = notice.id
    except Exception:
        notice_msg = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started_at": now_ts(),
        "last_active": now_ts(),
        "answers": [],
        "notify_msg": notice_msg,
        "under_review": False,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM interview flow
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer the following approval questions one by one:")

        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
            except asyncio.TimeoutError:
                # Did not answer in time; keep entry and let inactivity checker escalate
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"ℹ️ Member {member.display_name} timed out during interview.")
                return

            # Record answer
            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["step"] = pending_recruits[uid].get("step", 0) + 1
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # Completed all questions -> send confirmation DM, send answers to staff, then delete entry
        try:
            await dm.send("✅ Thank you for your cooperation! Your answers will be reviewed by our admins. Please wait for further instructions.")
        except Exception:
            pass

        # Delete the public notice in recruit channel
        try:
            nid = pending_recruits[uid].get("notify_msg")
            if nid:
                rc = client.get_channel(CHANNELS["recruit"])
                if rc:
                    try:
                        msg = await rc.fetch_message(nid)
                        await msg.delete()
                    except Exception:
                        pass
        except Exception:
            pass

        # Send formatted answers to admin review
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        if admin_ch:
            now_str = readable_now()
            labels = [
                "Purpose of joining:",
                "Invited by an Impedance member, and who:",
                "At least Major or up rank:",
                "Main Crossfire account:",
                "Willing to CCN:"
            ]
            formatted = ""
            answers = pending_recruits[uid]["answers"]
            for i, a in enumerate(answers):
                label = labels[i] if i < len(labels) else f"Question {i+1}:"
                formatted += f"**{label}**\n{a}\n\n"

            embed = discord.Embed(
                title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
                description=f"{formatted}📅 **Date answered:** `{now_str}`",
                color=discord.Color.blurple()
            )
            try:
                await admin_ch.send(embed=embed)
            except Exception:
                pass

        # mark resolved and remove pending entry (Option A: deletion only when complete)
        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        # now remove the processed entry
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)
        print(f"✅ Completed interview for {member.display_name}")

    except Exception as e:
        # DM failed (blocked) or other error: escalate immediately to staff review poll
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        # Try to create admin poll immediately
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        display_name = f"{member.display_name} (@{member.name})"
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {display_name} for approval.",
                description=(
                    "Could not DM recruit or recruit blocked DMs. Recruit did not respond.\n\n"
                    "Should the recruit be rejected and kicked out of the clan server?\n"
                    "One authorized admin vote will decide."
                ),
                color=discord.Color.dark_gold()
            )
            try:
                view = AdminDecisionView(uid)
                poll_msg = await admin_ch.send(embed=embed, view=view)
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["poll_msg"] = poll_msg.id
                save_json(PENDING_FILE, pending_recruits)
            except Exception as e2:
                print(f"⚠️ Failed to post admin poll: {e2}")

        # Notify recruit channel
        try:
            rc = client.get_channel(CHANNELS["recruit"])
            if rc:
                await rc.send(f"⚠️ {member.mention} did not respond to DMs. Admins have been notified.")
        except Exception:
            pass

# -------------------------
# On_message -> reminders
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Track only the designated reminder channel
    if message.channel.id == CHANNELS["reminder"]:
        state["message_counter"] = state.get("message_counter", 0) + 1
        save_json(STATE_FILE, state)
        if state["message_counter"] >= REMINDER_THRESHOLD:
            rem = REMINDERS[state.get("current_reminder", 0)]
            embed = discord.Embed(
                title="Reminders Impedance!",
                description=f"**{rem['title']}**\n\n{rem['description']}",
                color=discord.Color.orange()
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
            state["message_counter"] = 0
            state["current_reminder"] = (state.get("current_reminder", 0) + 1) % len(REMINDERS)
            save_json(STATE_FILE, state)

# -------------------------
# Presence announcements
# -------------------------
@client.event
async def on_presence_update(before, after):
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            member = after
            role_ids = [r.id for r in member.roles]
            title = None
            color = None
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
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Error in presence handler: {e}")

# -------------------------
# Escalate to admin poll helper
# -------------------------
async def escalate_to_poll(uid: str, member: discord.Member):
    """Create a staff poll message for a recruit who ignored/blocked DMs."""
    staff_ch = client.get_channel(CHANNELS["staff_review"])
    recruit_ch = client.get_channel(CHANNELS["recruit"])

    display_name = f"{member.display_name} (@{member.name})"

    # delete recruit channel notice if exists
    try:
        entry = pending_recruits.get(uid, {})
        if entry and entry.get("notify_msg"):
            rc = recruit_ch
            if rc:
                try:
                    msg = await rc.fetch_message(entry["notify_msg"])
                    await msg.delete()
                except Exception:
                    pass
    except Exception:
        pass

    if not staff_ch:
        return

    embed = discord.Embed(
        title=f"🪖 Recruit {display_name} for approval.",
        description=(
            "Recruit has not answered or refused to answer within 10 minutes.\n\n"
            "Should the recruit be rejected and kicked out of the clan?\n"
            "One authorized admin vote decides: Kick or Pardon."
        ),
        color=discord.Color.dark_gold()
    )

    try:
        view = AdminDecisionView(uid)
        poll_msg = await staff_ch.send(embed=embed, view=view)
        pending_recruits[uid]["under_review"] = True
        pending_recruits[uid]["poll_msg"] = poll_msg.id
        save_json(PENDING_FILE, pending_recruits)
    except Exception as e:
        print(f"⚠️ Failed to post admin poll: {e}")

    # small notify in recruit channel (non-deleting)
    try:
        if recruit_ch:
            await recruit_ch.send(f"⚠️ {member.mention} did not respond to DM within {INACTIVITY_SECONDS//60} minutes. Admins have been notified.")
    except Exception:
        pass

# -------------------------
# Inactivity checker background task
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
                last = entry.get("last_active", entry.get("started_at", now))
                if now - last >= INACTIVITY_SECONDS:
                    # find member object if possible
                    member = None
                    for g in client.guilds:
                        m = g.get_member(int(uid))
                        if m:
                            member = m
                            break
                    if not member:
                        # recruit left or not in any guild
                        # mark resolved to avoid infinite loop
                        pending_recruits[uid]["resolved"] = True
                        save_json(PENDING_FILE, pending_recruits)
                        continue

                    # escalate (this will create poll)
                    await escalate_to_poll(uid, member)
            await asyncio.sleep(30)
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker: {e}")
            await asyncio.sleep(30)

# -------------------------
# Run bot
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

# Start bot thread so Flask can be main for Render
threading.Thread(target=run_bot, daemon=True).start()

# Keep-alive when run directly
if __name__ == "__main__":
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
