# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Integrated main.py with DM interview, inactivity escalation, button poll for admins,
# one-admin resolution, and minimal fixes (no other logic changed).

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # keep_alive.py must provide ping_self()

# -------------------------
# CONFIG (easy to edit)
# -------------------------
CHANNELS = {
    "main": 1437768842871832597,         # Main announcements
    "recruit": 1437568595977834590,      # Recruit public notice channel
    "reminder": 1369091668724154419,     # Reminder message channel (tracked)
    "staff_review": 1437586858417852438  # Admin review channel
}

ROLES = {
    "queen": 1437578521374363769,
    "clan_master": 1389835747040694332,
    "impedance": 1437570031822176408,
    "og_impedance": 1437572916005834793
}

REMINDER_THRESHOLD = 50  # number of messages before posting next reminder
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

# Poll timeout (seconds). Poll resolves immediately on first authorized click.
POLL_TIMEOUT_SECONDS = 60 * 60  # 1 hour max (but will resolve early on first valid admin click)

# -------------------------
# SETUP
# -------------------------
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# state
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}  # keyed by str(user_id) -> dict metadata

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
# BUTTON-BASED POLL VIEW
# -------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid: str, timeout=POLL_TIMEOUT_SECONDS):
        super().__init__(timeout=timeout)
        self.recruit_uid = recruit_uid
        self.resolved = False

    async def resolve_decision(self, interaction: discord.Interaction, decision: str):
        # Only first authorized admin resolves
        if self.resolved:
            try:
                await interaction.response.send_message("This poll was already resolved.", ephemeral=True)
            except Exception:
                pass
            return

        reactor = interaction.user
        # check authorisation
        guild = interaction.guild
        if guild is None:
            try:
                await interaction.response.send_message("Guild context required.", ephemeral=True)
            except Exception:
                pass
            return

        member = guild.get_member(reactor.id)
        if not is_authorized(member):
            try:
                await interaction.response.send_message("You are not authorized to decide on recruits.", ephemeral=True)
            except Exception:
                pass
            return

        # mark resolved so later clicks ignored
        self.resolved = True

        uid = self.recruit_uid
        entry = pending_recruits.get(uid)
        staff_ch = client.get_channel(CHANNELS["staff_review"])

        # Try to get recruit member object
        recruit_member = None
        try:
            recruit_member = guild.get_member(int(uid))
        except Exception:
            recruit_member = None

        approver = approver_label(member)

        # Decision: kick
        if decision == "kick":
            kicked_display = recruit_member.display_name if recruit_member else f"ID {uid}"
            try:
                if recruit_member:
                    await recruit_member.kick(reason="Rejected by admin vote")
                    # DM recruit
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                    except Exception:
                        pass
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {kicked_display} kicked out of Impedance",
                        description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver}",
                        color=discord.Color.red()
                    )
                    await staff_ch.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to kick recruit {uid}: {e}")

        # Decision: pardon
        elif decision == "pardon":
            pardoned_display = recruit_member.display_name if recruit_member else f"ID {uid}"
            if staff_ch:
                embed = discord.Embed(
                    title=f"🪖 Recruit {pardoned_display} pardoned",
                    description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver}",
                    color=discord.Color.green()
                )
                await staff_ch.send(embed=embed)

        # clean up pending record & delete public notice if any
        try:
            if uid in pending_recruits:
                notice_id = pending_recruits[uid].get("notify_msg")
                if notice_id:
                    try:
                        recruit_ch = client.get_channel(CHANNELS["recruit"])
                        if recruit_ch:
                            m = await recruit_ch.fetch_message(notice_id)
                            await m.delete()
                    except Exception:
                        pass
                # remove record
                del pending_recruits[uid]
                save_json(PENDING_FILE, pending_recruits)
        except Exception:
            pass

        # disable buttons to avoid duplicate clicks
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # delete poll message per your preference (so it's not visible)
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # ephemeral confirmation to the reactor
        try:
            await interaction.response.send_message(f"Decision recorded: **{decision.upper()}** — approved by {approver}", ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger, custom_id="kick_recruit")
    async def kick_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.resolve_decision(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success, custom_id="pardon_recruit")
    async def pardon_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.resolve_decision(interaction, "pardon")

# -------------------------
# EVENTS
# -------------------------
@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)
    # start inactivity checker
    try:
        client.loop.create_task(inactivity_checker())
        print("🟢 inactivity_checker task started.")
    except Exception as e:
        print(f"⚠️ Failed to start inactivity_checker: {e}")
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_member_join(member):
    """DM recruit with questions and notify in recruit channel."""
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        print("⚠️ Recruit channel not found.")
        return

    # Public welcome message (optional)
    try:
        await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")
    except Exception:
        pass

    # Public notice that bot sent DM (we will delete this later)
    notice_msg_id = None
    try:
        notice_msg = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
        notice_msg_id = notice_msg.id
    except Exception:
        notice_msg_id = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started_at": now_ts(),
        "last_active": now_ts(),
        "answers": [],
        "notify_msg": notice_msg_id,
        "under_review": False,
        "review_message_id": None,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)
    print(f"📩 Started DM interview for recruit {member.display_name} (uid={uid})")

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
                    timeout=600  # 10 minutes per question
                )
            except asyncio.TimeoutError:
                # IMPORTANT FIX: DO NOT reset last_active here.
                # Keep original last_active so inactivity_checker can detect elapsed time since started_at.
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"⌛ Recruit {member.display_name} timed out during interview (uid={uid}).")
                # exit DM flow; inactivity_checker will escalate after threshold
                return

            # record answer
            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # Completed all questions successfully
        try:
            await dm.send("✅ Thank you for your cooperation! Your answers will be reviewed by our admins. Please wait for further instructions.")
        except Exception:
            pass

        # Delete the public recruit notice (if present)
        try:
            nid = pending_recruits.get(uid, {}).get("notify_msg")
            if nid:
                try:
                    msg = await recruit_ch.fetch_message(nid)
                    await msg.delete()
                except Exception:
                    pass
        except Exception:
            pass

        # Post answers to admin review channel for record (not requiring action)
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
            answers = pending_recruits[uid].get("answers", [])
            for i, ans in enumerate(answers):
                label = labels[i] if i < len(labels) else f"Question {i+1}:"
                formatted += f"**{label}**\n{ans}\n\n"
            embed = discord.Embed(
                title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
                description=f"{formatted}📅 **Date answered:** `{now_str}`",
                color=discord.Color.blurple()
            )
            try:
                await admin_ch.send(embed=embed)
            except Exception:
                pass

        # mark resolved and cleanup pending
        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)
        print(f"✅ Completed interview for recruit {member.display_name} (uid={uid})")

    except Exception as e:
        # DM failed (blocked or other error) -> escalate immediately using poll
        print(f"⚠️ Could not DM {member.display_name} (uid={uid}): {e}")
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        display_name = f"{member.display_name} (@{member.name})"
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {display_name} for approval.",
                description=(
                    "Could not DM recruit or recruit blocked DMs.\n\n"
                    "Should the recruit be rejected and kicked out of the clan server?\n"
                    "One authorized admin vote decides: Kick or Pardon."
                ),
                color=discord.Color.dark_gold()
            )
            try:
                view = AdminDecisionView(recruit_uid=uid)
                poll_msg = await admin_ch.send(embed=embed, view=view)
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = poll_msg.id
                save_json(PENDING_FILE, pending_recruits)
                print(f"📣 Posted admin poll for DM-blocked recruit {display_name} (uid={uid})")
            except Exception as e2:
                print(f"⚠️ Failed to post admin poll for DM-blocked recruit: {e2}")

        # also notify recruit channel briefly
        try:
            await recruit_ch.send(f"⚠️ {member.mention} did not respond to DM or blocked DMs. Admins have been notified.")
        except Exception:
            pass

@client.event
async def on_message(message):
    # ignore bot's own messages
    if message.author.id == client.user.id:
        return

    # Reminder system: only count messages in the reminder channel
    try:
        if message.channel.id == CHANNELS["reminder"]:
            state["message_counter"] = state.get("message_counter", 0) + 1
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
                except Exception:
                    pass
                state["message_counter"] = 0
                state["current_reminder"] = (state["current_reminder"] + 1) % len(REMINDERS)
                save_json(STATE_FILE, state)
    except Exception as e:
        print(f"⚠️ Error in on_message: {e}")

@client.event
async def on_presence_update(before, after):
    try:
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
            elif ROLES.get("og_impedance") and ROLES["og_impedance"] in role_ids:
                title, color = f"🎉 OG 🎉 {member.display_name} just came online!", discord.Color.red()
            if title:
                ch = client.get_channel(CHANNELS["main"])
                if ch:
                    embed = discord.Embed(title=title, color=color)
                    embed.set_thumbnail(url=after.display_avatar.url)
                    try:
                        await ch.send(embed=embed)
                    except Exception:
                        pass
    except Exception as e:
        print(f"⚠️ Error in presence handler: {e}")

# -------------------------
# INACTIVITY / ESCALATION CHECKER
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    print("🔍 inactivity_checker running...")
    while not client.is_closed():
        try:
            now = now_ts()
            # debug log
            try:
                print(f"🔍 Checking pending recruits: {len(pending_recruits)}")
            except Exception:
                pass

            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last = entry.get("last_active", entry.get("started_at", now))
                # escalate if idle >= 10 minutes
                if now - last >= 600:
                    print(f"🔔 Escalating recruit uid={uid} (idle={now-last}s)")
                    # delete public recruit notice if any
                    try:
                        recruit_ch = client.get_channel(CHANNELS["recruit"])
                        if recruit_ch and entry.get("notify_msg"):
                            try:
                                msg = await recruit_ch.fetch_message(entry["notify_msg"])
                                await msg.delete()
                            except Exception:
                                pass
                    except Exception:
                        pass

                    staff_ch = client.get_channel(CHANNELS["staff_review"])
                    # determine display name
                    display_name = None
                    if staff_ch:
                        guild = staff_ch.guild
                        try:
                            member = guild.get_member(int(uid))
                            if member:
                                display_name = f"{member.display_name} (@{member.name})"
                        except Exception:
                            display_name = None
                    if display_name is None:
                        try:
                            u = await client.fetch_user(int(uid))
                            display_name = f"{u.name} (@{u.name})"
                        except Exception:
                            display_name = f"ID {uid}"

                    if staff_ch:
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
                            view = AdminDecisionView(recruit_uid=uid)
                            poll_msg = await staff_ch.send(embed=embed, view=view)
                            # mark under review and save
                            entry["under_review"] = True
                            entry["review_message_id"] = poll_msg.id
                            save_json(PENDING_FILE, pending_recruits)
                            print(f"📣 Posted admin poll for idle recruit {display_name} (uid={uid})")
                        except Exception as e:
                            print(f"⚠️ Failed to post admin poll for uid {uid}: {e}")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker: {e}")
            await asyncio.sleep(30)

# -------------------------
# RUN BOT
# -------------------------
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

# Run keep-alive when executed directly
if __name__ == "__main__":
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
