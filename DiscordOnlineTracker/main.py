# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app, ping_self

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

# -------------------------
# Simple JSON helpers
# -------------------------
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

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

# -------------------------
# Admin utilities
# -------------------------
def is_admin(member: discord.Member):
    if not member:
        return False
    ids = [r.id for r in member.roles]
    return (
        ROLES["queen"] in ids
        or ROLES["clan_master"] in ids
        or ROLES["og_impedance"] in ids
    )

def admin_label(member: discord.Member):
    if not member:
        return "Unknown"
    ids = [r.id for r in member.roles]
    if ROLES["queen"] in ids:
        return f"Queen {member.display_name}"
    if ROLES["clan_master"] in ids:
        return f"Clan Master {member.display_name}"
    if ROLES["og_impedance"] in ids:
        return f"OG-{member.display_name}"
    return member.display_name

# -------------------------
# Persistent Button View
# -------------------------
class AdminDecisionView(discord.ui.View):
    """
    Persistent view with two buttons:
    - custom_id="approve_kick"
    - custom_id="grant_pardon"
    The view is registered on_ready with client.add_view(AdminDecisionView()).
    Each created poll message should be associated with a pending_recruits[uid]["review_message_id"] = msg.id
    and pending_recruits[uid]["under_review"] = True
    """

    def __init__(self, recruit_id=None):
        super().__init__(timeout=None)  # persistent
        self.recruit_id = recruit_id
        self._resolved = False

    async def _find_uid_for_message(self, message_id):
        for uid, entry in pending_recruits.items():
            if entry.get("review_message_id") == message_id:
                return uid
        return self.recruit_id

    async def _handle_decision(self, interaction: discord.Interaction, decision: str):
        # Defer silently (ephemeral) so user sees a private confirmation
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            # fallback: continue even if defer fails
            pass

        # Determine uid (from view or by mapping message id -> uid)
        msg = getattr(interaction, "message", None)
        msg_id = getattr(msg, "id", None) if msg else None
        uid = None
        if msg_id:
            uid = await self._find_uid_for_message(msg_id)
        if not uid:
            uid = self.recruit_id
        if not uid:
            # cannot map uid; inform actor privately (ephemeral)
            try:
                await interaction.followup.send("Could not map recruit for this poll.", ephemeral=True)
            except:
                pass
            return

        # check actor privileges
        actor = interaction.user
        if not is_admin(actor):
            try:
                await interaction.followup.send("You are not authorized to perform this action.", ephemeral=True)
            except:
                pass
            return

        # ensure only first valid admin proceeds
        if self._resolved:
            try:
                await interaction.followup.send("This poll was already resolved.", ephemeral=True)
            except:
                pass
            return
        self._resolved = True

        # fetch guild & member
        guild = interaction.guild
        recruit_member = None
        if guild:
            try:
                recruit_member = guild.get_member(int(uid))
            except Exception:
                recruit_member = None
        else:
            # fallback: search across guilds for member
            for g in client.guilds:
                m = g.get_member(int(uid))
                if m:
                    guild = g
                    recruit_member = m
                    break

        approver = admin_label(actor)
        recruit_name = recruit_member.display_name if recruit_member else f"ID {uid}"

        # disable the buttons to avoid duplicates (best-effort)
        for child in self.children:
            child.disabled = True
        try:
            if msg:
                await msg.edit(view=self)
        except:
            pass

        # delete poll message (user requested A: delete poll)
        try:
            if msg:
                await msg.delete()
        except:
            pass

        staff_ch = client.get_channel(CHANNELS["staff_review"])

        if decision == "kick":
            # attempt to kick
            try:
                if recruit_member:
                    await recruit_member.kick(reason="Rejected by admin decision")
                    # DM recruit about rejection (best-effort)
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                    except:
                        pass
            except Exception:
                pass

            # post final log
            if staff_ch:
                try:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {recruit_name} kicked out of Impedance",
                        description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver}",
                        color=discord.Color.red()
                    )
                    await staff_ch.send(embed=embed)
                except:
                    pass

            # ephemeral confirmation to actor
            try:
                await interaction.followup.send(
                    f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver}",
                    ephemeral=True
                )
            except:
                pass

        else:  # pardon
            if staff_ch:
                try:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {recruit_name} pardoned",
                        description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver}",
                        color=discord.Color.green()
                    )
                    await staff_ch.send(embed=embed)
                except:
                    pass

            try:
                await interaction.followup.send(
                    f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver}",
                    ephemeral=True
                )
            except:
                pass

        # cleanup pending entry
        try:
            if uid in pending_recruits:
                del pending_recruits[uid]
                save_json(PENDING_FILE, pending_recruits)
        except:
            pass

    @discord.ui.button(label="Kick recruit", style=discord.ButtonStyle.danger, custom_id="approve_kick")
    async def kick_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self._handle_decision(interaction, "kick")

    @discord.ui.button(label="Pardon recruit", style=discord.ButtonStyle.success, custom_id="grant_pardon")
    async def pardon_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self._handle_decision(interaction, "pardon")

# -------------------------
# BOT EVENTS
# -------------------------
@client.event
async def on_ready():
    global state, pending_recruits
    state = load_json(STATE_FILE, state)
    pending_recruits = load_json(PENDING_FILE, pending_recruits)

    # register a blank persistent view so Discord routes interactions after restarts
    try:
        client.add_view(AdminDecisionView())  # persistent registration (no recruit_id)
    except Exception:
        pass

    # start background inactivity checker (keeps watching pending entries)
    client.loop.create_task(inactivity_checker())
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_member_join(member):
    """
    NEW BEHAVIOR (Option 3): do NOT DM the recruit.
    Immediately post an admin poll in staff_review channel for decision.
    Also post a public recruit notice in recruit channel (deleted later when resolved).
    """
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])

    # welcome public message (optional)
    try:
        if recruit_ch:
            await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Impedance!")
    except:
        pass

    # public notice that a DM would have been sent (to be deleted when resolved)
    notice_id = None
    try:
        if recruit_ch:
            notice = await recruit_ch.send(f"🪖 {member.mention}, staff will review your application shortly.")
            notice_id = notice.id
    except:
        notice_id = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started": now_ts(),
        "last": now_ts(),
        "answers": [],           # empty because we skip DM flow
        "announce": notice_id,
        "under_review": True,    # immediate poll posted
        "review_message_id": None
    }
    save_json(PENDING_FILE, pending_recruits)

    # Immediately post admin poll (persistent view) in staff_review
    try:
        if staff_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {member.display_name} (@{member.name}) requires decision",
                description="Recruit joined and will be reviewed. Should this recruit be kicked?\n(Admins with special roles may decide.)",
                color=discord.Color.dark_gold()
            )
            view = AdminDecisionView(recruit_id=uid)
            msg = await staff_ch.send(embed=embed, view=view)
            # store message id so the view can map message -> recruit later
            pending_recruits[uid]["review_message_id"] = msg.id
            save_json(PENDING_FILE, pending_recruits)
    except Exception as e:
        print("⚠️ Failed to post admin poll on member_join:", e)

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    if message.channel.id == CHANNELS["reminder"]:
        state["message_counter"] = state.get("message_counter", 0) + 1
        save_json(STATE_FILE, state)

        if state["message_counter"] >= REMINDER_THRESHOLD:
            r = REMINDERS[state["current_reminder"]]
            embed = discord.Embed(
                title="Impedance Reminders",
                description=f"**{r['title']}**\n\n{r['description']}",
                color=discord.Color.orange()
            )
            try:
                await message.channel.send(embed=embed)
            except:
                pass
            state["current_reminder"] = (state.get("current_reminder", 0) + 1) % len(REMINDERS)
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
            try:
                await ch.send(embed=embed)
            except:
                pass
    except:
        pass

# ----------------------------------
# INACTIVITY CHECKER (still useful if any entries exist)
# posts admin poll if pending entry hasn't been resolved after 10 minutes
# ----------------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        now = now_ts()
        for uid, data in list(pending_recruits.items()):
            # skip already under review
            if data.get("under_review"):
                continue

            last = data.get("last", data.get("started", now))
            if now - last >= 600:
                recruit_ch = client.get_channel(CHANNELS["recruit"])
                # delete recruit notice if present
                try:
                    if data.get("announce") and recruit_ch:
                        msg = await recruit_ch.fetch_message(data["announce"])
                        try:
                            await msg.delete()
                        except:
                            pass
                except:
                    pass

                staff_ch = client.get_channel(CHANNELS["staff_review"])
                guild = staff_ch.guild if staff_ch else None
                member = None
                try:
                    if guild:
                        member = guild.get_member(int(uid))
                except:
                    member = None
                name = member.display_name if member else f"ID {uid}"

                try:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {name} requires decision",
                        description="Recruit ignored approval questions.\nShould we kick them?",
                        color=discord.Color.dark_gold()
                    )
                    view = AdminDecisionView(recruit_id=uid)
                    msg = await staff_ch.send(embed=embed, view=view)
                    pending_recruits[uid]["under_review"] = True
                    pending_recruits[uid]["review_message_id"] = msg.id
                    save_json(PENDING_FILE, pending_recruits)
                except Exception as e:
                    print("⚠️ Failed to post admin poll in inactivity_checker:", e)

        await asyncio.sleep(20)

# ----------------------------------
# RUN BOT
# ----------------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN not found in environment variables!")
        return
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    # start self-pinger (keeps Render awake)
    try:
        threading.Thread(target=ping_self, daemon=True).start()
    except:
        pass
    app.run(host="0.0.0.0", port=8080)
