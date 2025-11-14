# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"
# Fixed main.py — reaction-based admin decisions (first admin reaction wins).
# Only the reaction-approval flow was changed (no button view / no interactions).

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

# ----------------------------------
# SETUP
# ----------------------------------

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}  # keyed by stringified user id

# ----------------------------------
# UTILITIES (load/save/state)
# ----------------------------------

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

def now_ts():
    return int(time.time())

def readable_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_admin(member: discord.Member):
    """Return True if member has one of the special admin roles."""
    if not member:
        return False
    role_ids = [r.id for r in member.roles]
    return any(ROLES.get(k) and ROLES[k] in role_ids for k in ("queen", "clan_master", "og_impedance"))

def admin_label(member: discord.Member):
    """Return label for logging based on highest special role found."""
    if not member:
        return "Unknown"
    ids = [r.id for r in member.roles]
    if ROLES.get("queen") and ROLES["queen"] in ids:
        return f"Queen {member.display_name}"
    if ROLES.get("clan_master") and ROLES["clan_master"] in ids:
        return f"Clan Master {member.display_name}"
    if ROLES.get("og_impedance") and ROLES["og_impedance"] in ids:
        return f"OG-{member.display_name}"
    return member.display_name

# ----------------------------------
# EVENTS & CORE LOGIC
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
    """
    Send DM questionnaire to recruit, post public notice in recruit channel (deleted later),
    and send formatted answers to admin channel when complete.
    If DMs are blocked or interview times out, escalate to admin review (reaction-based).
    """
    recruit_ch = client.get_channel(CHANNELS["recruit"])
    staff_ch = client.get_channel(CHANNELS["staff_review"])

    # Friendly welcome (non-blocking)
    try:
        if recruit_ch:
            await recruit_ch.send(f"🎉 Everyone welcome {member.mention} to Impedance!")
    except Exception:
        pass

    # Public notice that DM sent (store ID to delete later)
    notice_id = None
    try:
        if recruit_ch:
            notice_msg = await recruit_ch.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")
            notice_id = notice_msg.id
    except Exception:
        notice_id = None

    uid = str(member.id)
    pending_recruits[uid] = {
        "started": now_ts(),
        "last": now_ts(),
        "answers": [],
        "announce": notice_id,
        "under_review": False,
        "review_message_id": None,
        "resolved": False
    }
    save_json(PENDING_FILE, pending_recruits)

    # DM interview
    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to Impedance! Please answer the approval questions:")
        for q in RECRUIT_QUESTIONS:
            await dm.send(q)
            try:
                reply = await client.wait_for(
                    "message",
                    check=lambda m: m.author.id == member.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600  # 10 minutes per question
                )
            except asyncio.TimeoutError:
                # mark last activity and let inactivity_checker escalate
                pending_recruits[uid]["last"] = now_ts()
                save_json(PENDING_FILE, pending_recruits)
                try:
                    await dm.send("⏳ You did not answer in time. Staff will be notified for review.")
                except Exception:
                    pass
                print(f"⌛ Recruit {member.display_name} timed out during interview.")
                return

            # record answer
            pending_recruits[uid]["answers"].append(reply.content.strip())
            pending_recruits[uid]["last"] = now_ts()
            save_json(PENDING_FILE, pending_recruits)

        # Completed questionnaire
        try:
            await dm.send("✅ Thank you! Your answers will be reviewed by the admins. Please wait for further instructions.")
        except Exception:
            pass

        # Delete public notice in recruit channel (if exists)
        try:
            if notice_id and recruit_ch:
                to_delete = await recruit_ch.fetch_message(notice_id)
                await to_delete.delete()
        except Exception:
            pass

        # Send formatted answers to admin review channel
        try:
            if staff_ch:
                labels = [
                    "Purpose of joining:",
                    "Invited by an Impedance member, and who:",
                    "At least Major rank:",
                    "Is this your main account:",
                    "Willing to CCN:"
                ]
                formatted = ""
                answers = pending_recruits[uid]["answers"]
                for i, ans in enumerate(answers):
                    label = labels[i] if i < len(labels) else f"Question {i+1}:"
                    formatted += f"**{label}**\n{ans}\n\n"
                now_str = readable_now()
                embed = discord.Embed(
                    title=f"🪖 Recruit {member.display_name} for approval.",
                    description=f"{formatted}📅 **Date answered:** `{now_str}`",
                    color=discord.Color.blurple()
                )
                await staff_ch.send(embed=embed)
        except Exception:
            pass

        # mark resolved and remove pending
        try:
            pending_recruits.pop(uid, None)
            save_json(PENDING_FILE, pending_recruits)
        except Exception:
            pass

    except Exception as e:
        # DM failed (blocked) -> immediate admin review via reactions
        print(f"⚠️ Could not DM {member.display_name}: {e}")
        try:
            if staff_ch:
                display = f"{member.display_name} (@{member.name})"
                embed = discord.Embed(
                    title=f"🪖 Recruit {display} for approval.",
                    description=(
                        "Could not DM recruit or recruit blocked DMs.\n\n"
                        "Should the recruit be rejected and kicked out of the clan server?\n"
                        "React 👍 to **kick**, 👎 to **pardon**. (Only admins with special roles may decide.)"
                    ),
                    color=discord.Color.dark_gold()
                )
                review_msg = await staff_ch.send(embed=embed)
                # add reactions for admins to use
                try:
                    await review_msg.add_reaction("👍")
                    await review_msg.add_reaction("👎")
                except Exception:
                    pass

                # mark pending under review
                pending_recruits[uid]["under_review"] = True
                pending_recruits[uid]["review_message_id"] = review_msg.id
                save_json(PENDING_FILE, pending_recruits)
        except Exception as e2:
            print(f"⚠️ Failed to post admin review on DM-fail: {e2}")

        # notify recruit channel (short notice)
        try:
            if recruit_ch:
                await recruit_ch.send(f"⚠️ {member.mention} did not respond to DMs. Admins have been notified.")
        except Exception:
            pass

@client.event
async def on_message(message):
    """Reminder counter and rotation logic. Unchanged except threshold can be configured."""
    if message.author.id == client.user.id:
        return

    if message.channel.id == CHANNELS["reminder"]:
        state["message_counter"] = state.get("message_counter", 0) + 1
        save_json(STATE_FILE, state)

        if state["message_counter"] >= REMINDER_THRESHOLD:
            r = REMINDERS[state.get("current_reminder", 0)]
            embed = discord.Embed(
                title="Impedance Reminders",
                description=f"**{r['title']}**\n\n{r['description']}",
                color=discord.Color.orange()
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass

            state["current_reminder"] = (state.get("current_reminder", 0) + 1) % len(REMINDERS)
            state["message_counter"] = 0
            save_json(STATE_FILE, state)

@client.event
async def on_presence_update(before, after):
    """Announce presence for members with special roles (online/idle/dnd)."""
    try:
        if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
            m = after
            ids = [r.id for r in m.roles]
            ch = client.get_channel(CHANNELS["main"])

            title = None
            color = None
            if ROLES["queen"] in ids:
                title, color = f"👑 Queen {m.display_name} just came online!", discord.Color.gold()
            elif ROLES["clan_master"] in ids:
                title, color = f"🌟 Clan Master {m.display_name} just came online!", discord.Color.blue()
            elif ROLES.get("og_impedance") and ROLES["og_impedance"] in ids:
                title, color = f"🎉 OG 🎉 {m.display_name} just came online!", discord.Color.red()
            elif ROLES["impedance"] in ids:
                title, color = f"⭐ Impedance {m.display_name} just came online!", discord.Color.purple()

            if title and ch:
                embed = discord.Embed(title=title, color=color)
                embed.set_thumbnail(url=after.display_avatar.url)
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
    except Exception:
        pass

# --------------------------
# Reaction handling (first admin reaction wins)
# --------------------------

@client.event
async def on_raw_reaction_add(payload):
    """
    When an admin reacts to a pending review message with 👍 or 👎, the first authorized admin's reaction triggers the action.
    Only considers messages that have a matching pending_recruits[uid]["review_message_id"].
    """
    try:
        # ignore bot's own reactions
        if payload.user_id == client.user.id:
            return

        # We only care about reactions in staff_review channel
        if payload.channel_id != CHANNELS["staff_review"]:
            return

        # get the emoji string (works for unicode)
        emoji_str = str(payload.emoji)

        # Determine decision
        decision = None
        if "👍" in emoji_str:
            decision = "kick"
        elif "👎" in emoji_str:
            decision = "pardon"
        else:
            return  # ignore other reactions

        # Find which pending recruit this message belongs to
        target_uid = None
        for uid, entry in pending_recruits.items():
            if entry.get("under_review") and entry.get("review_message_id") == payload.message_id:
                target_uid = uid
                break

        if not target_uid:
            # no matching pending review found
            return

        entry = pending_recruits.get(target_uid)
        if not entry or entry.get("resolved"):
            return

        # Get guild and reactor member
        guild = client.get_guild(payload.guild_id) if payload.guild_id else None
        reactor = guild.get_member(payload.user_id) if guild else None

        # check authorized
        if not is_admin(reactor):
            # unauthorized — ignore
            return

        # FIRST admin reaction wins: resolve immediately
        # mark resolved to avoid race
        entry["resolved"] = True
        save_json(PENDING_FILE, pending_recruits)

        # perform action (kick/pardon)
        recruit_member = None
        if guild:
            try:
                recruit_member = guild.get_member(int(target_uid))
            except Exception:
                recruit_member = None

        approver_text = admin_label(reactor)

        staff_ch = client.get_channel(CHANNELS["staff_review"])

        if decision == "kick":
            # attempt to kick the recruit
            kicked_name = recruit_member.display_name if recruit_member else f"ID {target_uid}"
            try:
                if recruit_member:
                    await recruit_member.kick(reason="Rejected by admin decision")
                    # DM them
                    try:
                        dm = await recruit_member.create_dm()
                        await dm.send("We are sorry to inform you that your application was rejected. Thank you for your interest in joining Impedance.")
                    except Exception:
                        pass
            except Exception as e:
                print(f"⚠️ Failed to kick recruit {target_uid}: {e}")

            # log final message
            try:
                embed = discord.Embed(
                    title=f"🪖 Recruit {kicked_name} kicked out of Impedance",
                    description=f"Recruit was removed due to refusal or inactivity.\n\nApproved by: {approver_text}",
                    color=discord.Color.red()
                )
                if staff_ch:
                    await staff_ch.send(embed=embed)
            except Exception:
                pass

        else:  # pardon
            pardoned_name = recruit_member.display_name if recruit_member else f"ID {target_uid}"
            try:
                embed = discord.Embed(
                    title=f"🪖 Recruit {pardoned_name} pardoned",
                    description=f"Recruit was pardoned and will remain in the server.\n\nApproved by: {approver_text}",
                    color=discord.Color.green()
                )
                if staff_ch:
                    await staff_ch.send(embed=embed)
            except Exception:
                pass

        # try to delete the review message to clean up
        try:
            review_msg_id = entry.get("review_message_id")
            if review_msg_id and staff_ch:
                try:
                    msg = await staff_ch.fetch_message(review_msg_id)
                    await msg.delete()
                except Exception:
                    pass
        except Exception:
            pass

        # cleanup pending entry
        try:
            if target_uid in pending_recruits:
                del pending_recruits[target_uid]
                save_json(PENDING_FILE, pending_recruits)
        except Exception:
            pass

    except Exception as e:
        print(f"⚠️ Error in on_raw_reaction_add: {e}")

# --------------------------
# Inactivity checker (10 minutes)
# --------------------------

async def inactivity_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            now = now_ts()
            for uid, entry in list(pending_recruits.items()):
                if entry.get("under_review") or entry.get("resolved"):
                    continue

                last = entry.get("last", entry.get("started", now))
                # if idle >= 10 minutes
                if now - last >= 600:
                    # delete public notice in recruit channel if it exists
                    try:
                        recruit_ch = client.get_channel(CHANNELS["recruit"])
                        if recruit_ch and entry.get("announce"):
                            try:
                                msg = await recruit_ch.fetch_message(entry["announce"])
                                await msg.delete()
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # create admin review message in staff channel and add reactions
                    try:
                        staff_ch = client.get_channel(CHANNELS["staff_review"])
                        if not staff_ch:
                            continue

                        # attempt to get member display name
                        display_name = None
                        guild = staff_ch.guild
                        if guild:
                            member = guild.get_member(int(uid))
                            if member:
                                display_name = f"{member.display_name} (@{member.name})"
                        if display_name is None:
                            display_name = f"ID {uid}"

                        embed = discord.Embed(
                            title=f"🪖 Recruit {display_name} requires decision",
                            description=(
                                "Recruit ignored approval questions.\nShould we kick them?\n\n"
                                "React 👍 to **kick**, 👎 to **pardon**. (Only admins with special roles may decide.)"
                            ),
                            color=discord.Color.dark_gold()
                        )
                        review_msg = await staff_ch.send(embed=embed)
                        try:
                            await review_msg.add_reaction("👍")
                            await review_msg.add_reaction("👎")
                        except Exception:
                            pass

                        # mark under review and store message id
                        entry["under_review"] = True
                        entry["review_message_id"] = review_msg.id
                        save_json(PENDING_FILE, pending_recruits)
                    except Exception as e:
                        print(f"⚠️ Failed to post admin review for uid {uid}: {e}")

            await asyncio.sleep(20)
        except Exception as e:
            print(f"⚠️ Error in inactivity_checker: {e}")
            await asyncio.sleep(20)

# --------------------------
# Run bot
# --------------------------

def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    # start self-pinger (from keep_alive) to keep Render awake
    try:
        threading.Thread(target=ping_self, daemon=True).start()
    except Exception:
        pass
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
