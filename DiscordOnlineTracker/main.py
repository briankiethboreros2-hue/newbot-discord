# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Reaction-based approval (Option B) — bot does NOT react to its own review message.
# Keep keep_alive.py in the repo (ping_self).

import threading
import discord
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from keep_alive import app  # keep_alive.ping_self should exist

# -------------------------
# CONFIG
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

REMINDER_THRESHOLD = 50
STATE_FILE = "reminder_state.json"
PENDING_FILE = "pending_recruits.json"

RECRUIT_QUESTIONS = [
    "1️⃣ What is your purpose joining Impedance Discord server?",
    "2️⃣ Did a member of the clan invite you? If yes, who?",
    "3️⃣ Is the account you're using to apply in our clan your main account?",
    "4️⃣ Are you willing to change your in-game name to our clan format? (e.g., IM-Ryze)"
]

REMINDERS = [
    {"title": "🟢 Activity Reminder", "description": "Members must keep their status set only to “Online” while active.\nInactive members without notice may lose their role or be suspended."},
    {"title": "🧩 IGN Format", "description": "All members must use the official clan format: `IM-(Your IGN)`\nExample: IM-Ryze or IM-Reaper."},
    {"title": "🔊 Voice Channel Reminder", "description": "When online, you must join the **Public Call** channel.\nOpen mic is required — we value real-time communication.\nStay respectful and avoid mic spamming or toxic behavior."}
]

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
pending_recruits = {}  # str(uid) -> dict

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
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    if not recruit_ch:
        print("⚠️ Recruit channel not found.")
        return

    # announce and public notice
    try:
        await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to the server!")
    except Exception:
        pass

    notice_id = None
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
    print(f"📨 Started interview for recruit {member.display_name} (uid={uid})")

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
                    timeout=600  # 10 minutes
                )
            except asyncio.TimeoutError:
                pending_recruits[uid]["last_active"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"⌛ Recruit {member.display_name} timed out during interview.")
                return
            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["last_active"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # Completed
        try:
            await dm.send("✅ Thank you for your cooperation! Your answers will be reviewed by our admins. Please wait for further instructions.")
        except Exception:
            pass

        # delete public notice if present
        try:
            nid = pending_recruits.get(uid, {}).get("notify_msg")
            if nid:
                recruit_ch = client.get_channel(CHANNELS["recruit"])
                if recruit_ch:
                    try:
                        msg = await recruit_ch.fetch_message(nid)
                        await msg.delete()
                    except Exception:
                        pass
        except Exception:
            pass

        # send answers to admin channel for record
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

        # resolved & cleanup
        pending_recruits[uid]["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)
        if uid in pending_recruits:
            del pending_recruits[uid]
            save_json(PENDING_FILE, pending_recruits)
        print(f"✅ Completed interview for recruit {member.display_name} (uid={uid})")

    except Exception as e:
        # DM failed -> escalate to admin review
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        admin_ch = client.get_channel(CHANNELS["staff_review"])
        display_name = f"{member.display_name} (@{member.name})"
        if admin_ch:
            embed = discord.Embed(
                title=f"🪖 Recruit {display_name} for approval.",
                description=(
                    "Could not DM recruit or recruit blocked DMs.\n\n"
                    "Should the recruit be rejected and kicked out of the clan server?\n"
                    "React 👍 to kick, 👎 to pardon. (Only admins with special roles may decide.)"
                ),
                color=discord.Color.dark_gold()
            )
            try:
                review_msg = await admin_ch.send(embed=embed)
                # Do NOT add reactions programmatically to avoid bot reacting to itself.
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = review_msg.id
                save_json(PENDING_FILE, pending_recruits)
                print(f"📣 Posted admin review for DM-blocked recruit {display_name} (uid={uid})")
            except Exception as e2:
                print(f"⚠️ Failed to post admin review: {e2}")

        # notify recruit channel
        try:
            recruit_ch = client.get_channel(CHANNELS["recruit"])
            await recruit_ch.send(f"⚠️ {member.mention} did not respond to DMs. Admins have been notified.")
        except Exception:
            pass

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return
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
# REACTION HANDLER (first authorized admin reaction wins)
# -------------------------
@client.event
async def on_raw_reaction_add(payload):
    try:
        # ignore bot's own reactions
        if payload.user_id == client.user.id:
            return

        # only consider staff review channel
        if payload.channel_id != CHANNELS["staff_review"]:
            return

        # find matching pending entry
        for uid, entry in list(pending_recruits.items()):
            if not entry.get("under_review") or entry.get("resolved"):
                continue
            if entry.get("review_message_id") != payload.message_id:
                continue

            # get guild and reactor member
            guild = None
            if payload.guild_id:
                guild = client.get_guild(payload.guild_id)
            if guild is None:
                return

            reactor = guild.get_member(payload.user_id)
            if reactor is None:
                # try fetch
                try:
                    reactor_user = await client.fetch_user(payload.user_id)
                    # can't fetch member object without guild member
                    # so treat as unauthorized
                except Exception:
                    pass
                return

            # only allow special-role reactors
            if not is_authorized(reactor):
                print(f"🚫 Unauthorized reactor {reactor.display_name}; ignored.")
                return

            # determine decision from emoji
            emoji = None
            # payload.emoji.name for unicode vs custom
            try:
                emoji = payload.emoji.name if hasattr(payload.emoji, "name") else str(payload.emoji)
            except Exception:
                emoji = str(payload.emoji)
            is_kick = False
            is_pardon = False
            if emoji in ("👍", "+1", "thumbsup"):
                is_kick = True
            elif emoji in ("👎", "thumbsdown"):
                is_pardon = True
            else:
                # ignore other emojis
                return

            # only first valid reaction processed
            if entry.get("resolved"):
                return
            entry["resolved"] = True
            save_json(PENDING_FILE, pending_recruits)

            # determine recruit display
            recruit_display = f"ID {uid}"
            recruit_member = None
            try:
                # try to find in guild
                recruit_member = guild.get_member(int(uid))
                if recruit_member:
                    recruit_display = f"{recruit_member.display_name} (@{recruit_member.name})"
                else:
                    # fetch user fallback
                    try:
                        user_obj = await client.fetch_user(int(uid))
                        recruit_display = f"{user_obj.name} (@{user_obj.name})"
                    except Exception:
                        recruit_display = f"ID {uid}"
            except Exception:
                recruit_display = f"ID {uid}"

            approver_text = approver_label(reactor)
            staff_ch = client.get_channel(CHANNELS["staff_review"])

            if is_kick:
                kicked_display = recruit_display
                try:
                    if recruit_member:
                        await recruit_member.kick(reason="Rejected by admin vote")
                        # DM recruit if possible
                        try:
                            dm = await recruit_member.create_dm()
                            await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                        except Exception:
                            pass
                    if staff_ch:
                        embed = discord.Embed(
                            title=f"🪖 Recruit {kicked_display} kicked out of Impedance",
                            description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver_text}",
                            color=discord.Color.red()
                        )
                        await staff_ch.send(embed=embed)
                except Exception as e:
                    print(f"⚠️ Failed to kick recruit {uid}: {e}")

            elif is_pardon:
                pardoned_display = recruit_display
                if staff_ch:
                    embed = discord.Embed(
                        title=f"🪖 Recruit {pardoned_display} pardoned",
                        description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver_text}",
                        color=discord.Color.green()
                    )
                    await staff_ch.send(embed=embed)

            # cleanup pending and delete public notice if any
            try:
                notice_msg_id = entry.get("notify_msg")
                if notice_msg_id:
                    try:
                        recruit_ch = client.get_channel(CHANNELS["recruit"])
                        if recruit_ch:
                            msg = await recruit_ch.fetch_message(notice_msg_id)
                            await msg.delete()
                    except Exception:
                        pass
            except Exception:
                pass

            # remove pending record
            try:
                if uid in pending_recruits:
                    del pending_recruits[uid]
                    save_json(PENDING_FILE, pending_recruits)
            except Exception:
                pass

            # delete the review message so it's no longer active (optional)
            try:
                review_msg = await client.get_channel(payload.channel_id).fetch_message(payload.message_id)
                await review_msg.delete()
            except Exception:
                pass

            return

    except Exception as e:
        print(f"⚠️ Error in on_raw_reaction_add: {e}")

# -------------------------
# INACTIVITY CHECKER
# -------------------------
async def inactivity_checker():
    await client.wait_until_ready()
    print("🔍 inactivity_checker running...")
    while not client.is_closed():
        try:
            now = now_ts()
            try:
                print(f"🔍 Checking pending recruits: count={len(pending_recruits)}")
            except Exception:
                pass

            for uid, entry in list(pending_recruits.items()):
                if entry.get("resolved") or entry.get("under_review"):
                    continue
                last = entry.get("last_active", entry.get("started_at", now))
                if now - last >= 600:  # 10 minutes
                    print(f"🔔 Escalating recruit uid={uid} (idle={now-last}s)")
                    # delete public recruit notice if exists
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
                                "React 👍 to kick, 👎 to pardon. (Only admins with special roles may decide.)"
                            ),
                            color=discord.Color.dark_gold()
                        )
                        try:
                            review_msg = await staff_ch.send(embed=embed)
                            # Do NOT add reactions programmatically
                            entry["under_review"] = True
                            entry["review_message_id"] = review_msg.id
                            save_json(PENDING_FILE, pending_recruits)
                            print(f"📣 Posted admin review for uid={uid}")
                        except Exception as e:
                            print(f"⚠️ Failed to post admin review for uid {uid}: {e}")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker: {e}")
            await asyncio.sleep(30)

# -------------------------
# RUN
# -------------------------
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN missing.")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    try:
        from keep_alive import ping_self
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
