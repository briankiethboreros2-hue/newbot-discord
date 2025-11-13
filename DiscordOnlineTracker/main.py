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

# state
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}  # str(uid) -> dict

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
# === BUTTON VIEW (POLL) ===
# -------------------------
class AdminDecisionView(discord.ui.View):
    def __init__(self, recruit_uid: str, created_at: int, timeout=POLL_DURATION_SECONDS):
        super().__init__(timeout=timeout)
        self.recruit_uid = recruit_uid
        self.created_at = created_at
        self.resolved = False

    async def _resolve(self, interaction: discord.Interaction, decision: str):
        # Only first authorized admin to click triggers resolution
        if self.resolved:
            # already handled
            try:
                await interaction.response.send_message("This poll was already resolved.", ephemeral=True)
            except Exception:
                pass
            return

        reactor = interaction.user
        if not is_authorized(reactor):
            # not a valid admin voter
            try:
                await interaction.response.send_message("You are not authorized to decide on recruits.", ephemeral=True)
            except Exception:
                pass
            return

        # Mark resolved
        self.resolved = True
        uid = self.recruit_uid
        entry = pending_recruits.get(uid)
        staff_ch = client.get_channel(CHANNELS["staff_review"])
        guild = interaction.guild

        # fetch member if possible
        recruit_member = None
        try:
            recruit_member = guild.get_member(int(uid))
        except Exception:
            recruit_member = None

        approver_text = approver_label(reactor)

        if decision == "kick":
            # Attempt to kick
            kicked_name = recruit_member.display_name if recruit_member else f"ID {uid}"
            try:
                if recruit_member:
                    await recruit_member.kick(reason="Rejected by admin vote")
                    # DM them
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                    except Exception:
                        pass
                # Post summary embed
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {kicked_name} kicked out of Impedance",
                        description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver_text}",
                        color=discord.Color.red()
                    )
                    await staff_ch.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to kick recruit {uid}: {e}")

        elif decision == "pardon":
            pardoned_name = recruit_member.display_name if recruit_member else f"ID {uid}"
            if staff_ch:
                embed = discord.Embed(
                    title=f"🪖 Recruit {pardoned_name} pardoned",
                    description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver_text}",
                    color=discord.Color.green()
                )
                await staff_ch.send(embed=embed)

        # Cleanup pending
        if uid in pending_recruits:
            try:
                # delete any public recruit notice in recruit channel
                notice_msg_id = pending_recruits[uid].get("notify_msg")
                if notice_msg_id:
                    try:
                        recruit_ch = client.get_channel(CHANNELS["recruit"])
                        msg = await recruit_ch.fetch_message(notice_msg_id)
                        await msg.delete()
                    except Exception:
                        pass
            except Exception:
                pass
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

        # disable buttons to avoid duplicates
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # delete the poll message (requested)
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Acknowledge the admin who clicked (ephemeral)
        try:
            await interaction.response.send_message(f"Decision recorded: **{decision.upper()}** — approved by {approver_text}", ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger, custom_id="kick_button")
    async def kick_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # FIX: first-authorized-admin click resolves immediately
        await self._resolve(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success, custom_id="pardon_button")
    async def pardon_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # FIX: first-authorized-admin click resolves immediately
        await self._resolve(interaction, "pardon")

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
    """Announce join, send DM questionnaire, create pending entry."""
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        print("⚠️ Recruit channel not found.")
        return

    # Announce new recruit (friendly)
    try:
        await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")
    except Exception:
        pass

    # Notify recruit in channel (will be deleted later)
    try:
        notice = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
        notice_id = notice.id
    except Exception:
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
                # did not answer in time for this question; leave entry and let inactivity checker escalate
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"⌛ Recruit {member.display_name} timed out during interview.")
                return
            # record
            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # Completed all questions
        try:
            await dm.send("✅ Thank you for your cooperation! Your answers will be reviewed by our admins. Please wait for further instructions.")
        except Exception:
            pass

        # FIX: delete the public recruit notice now that answers are complete
        if pending_recruits.get(uid, {}).get("notify_msg"):
            try:
                recruit_ch = client.get_channel(CHANNELS["recruit"])
                msg = await recruit_ch.fetch_message(pending_recruits[uid]["notify_msg"])
                await msg.delete()
            except Exception:
                pass

        # Send formatted answers to admin review channel (for record)
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
                title=f"🪖 Recruit {member.display_name} (@{member.name}) for approval.",
                description=f"{formatted}📅 **Date answered:** `{now_str}`",
                color=discord.Color.blurple()
            )
            await admin_ch.send(embed=embed)

        # mark resolved and remove pending
        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)

    except Exception as e:
        # DM failed or blocked — escalate immediately to admin poll
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        display_name = f"{member.display_name} (@{member.name})"
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {display_name} for approval.",
                description=(
                    "Could not DM recruit or recruit blocked DMs.\n\n"
                    "Should the recruit be rejected and kicked out of the clan server?\n"
                    "Please vote below (authorized admins only)."
                ),
                color=discord.Color.dark_gold()
            )
            view = AdminDecisionView(recruit_uid=uid, created_at=now_ts())
            try:
                poll_msg = await admin_ch.send(embed=embed, view=view)
                view.message = poll_msg
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = poll_msg.id
                save_json(PENDING_FILE, pending_recruits)
            except Exception as e2:
                print(f"⚠️ Failed to post admin poll: {e2}")

        # notify recruit channel
        try:
            recruit_ch = client.get_channel(CHANNELS["recruit"])
            await recruit_ch.send(f"⚠️ {member.mention} did not respond to DMs. Admins have been notified.")
        except Exception:
            pass

@client.event
async def on_message(message):
    # ignore bot itself
    if message.author.id == client.user.id:
        return
    # Reminder channel logic
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
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=after.display_avatar.url)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Error in presence handler: {e}")

# -------------------------
# === INACTIVITY CHECKER ===
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = now_ts()
            for uid, entry in list(pending_recruits.items()):
                # skip resolved or already under review
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last = entry.get("last_active", entry.get("started_at", now))
                # if idle >= 10 minutes -> create poll
                if now - last >= 600:
                    # FIX: ensure recruit notice is deleted when escalation happens
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
                    # get display name if possible
                    display_name = None
                    guild = None
                    if staff_ch:
                        guild = staff_ch.guild
                        try:
                            member = guild.get_member(int(uid))
                            if member:
                                display_name = f"{member.display_name} (@{member.name})"
                        except Exception:
                            display_name = None
                    if display_name is None:
                        display_name = f"ID {uid}"

                    if staff_ch:
                        embed = discord.Embed(
                            title=f"🪖 Recruit {display_name} for approval.",
                            description=(
                                "Recruit has not answered or refused to answer within 10 minutes.\n\n"
                                "Should the recruit be rejected and kicked out of the clan?\n"
                                "Please vote below (authorized admins only)."
                            ),
                            color=discord.Color.dark_gold()
                        )
                        view = AdminDecisionView(recruit_uid=uid, created_at=now)
                        try:
                            poll_msg = await staff_ch.send(embed=embed, view=view)
                            view.message = poll_msg
                            entry["under_review"] = True
                            entry["review_message_id"] = poll_msg.id
                            save_json(PENDING_FILE, pending_recruits)
                        except Exception as e:
                            print(f"⚠️ Failed to post admin poll for uid {uid}: {e}")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker: {e}")
            await asyncio.sleep(30)

# -------------------------
# === RUN BOT ===
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN missing.")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

# run bot thread so Flask is main process for Render
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    # start self-pinger from keep_alive (if provided)
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
