# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
import time
import json
from datetime import datetime, timezone
from keep_alive import app  # import the Flask app instead of start_keep_alive

# --- Intents ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.messages = True
intents.message_content = True  # Required for DMs and message tracking

client = discord.Client(intents=intents)

# --- Channel IDs ---
MAIN_CHANNEL_ID = 1437768842871832597        # Main announcements
RECRUIT_CHANNEL_ID = 1437568595977834590     # Recruit channel
REMINDER_CHANNEL_ID = 1369091668724154419    # Rules reminder channel
ADMIN_REVIEW_CHANNEL_ID = 1437586858417852438  # Admin review channel

# --- Role IDs ---
ROLE_ID_QUEEN = 1437578521374363769
ROLE_ID_CLAN_MASTER = 1389835747040694332
ROLE_ID_IMPEDANCE = 1437570031822176408
ROLE_ID_OG_IMPEDANCE = 1437572916005834793

# --- Reminder rotation system ---
reminders = [
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

STATE_FILE = "reminder_state.json"
state = {"message_counter": 0, "current_reminder": 0}
pending_recruits = {}

# --- Utility functions ---
def load_state():
    global state
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        print(f"🔁 Loaded state: {state}")
    except FileNotFoundError:
        print("ℹ️ No previous state found — starting fresh.")

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        print(f"💾 Saved state: {state}")
    except Exception as e:
        print(f"⚠️ Failed to save state: {e}")


@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    load_state()
    print("🕓 Ready and tracking messages for reminders.")


@client.event
async def on_member_join(member):
    """DM recruit with questions and notify in recruit channel."""
    recruit_channel = client.get_channel(RECRUIT_CHANNEL_ID)
    if not recruit_channel:
        print("⚠️ Recruit channel not found.")
        return

    # Notify recruit publicly
    notify_msg = await recruit_channel.send(f"🪖 {member.mention}, I have sent you a DM. Please check your DMs.")

    questions = [
        "1️⃣ What is your purpose joining Impedance discord server?",
        "2️⃣ Did a member of the clan invite you? If yes, who?",
        "3️⃣ Is the account you're using to apply in our clan your main account?",
        "4️⃣ Are you willing to change your in-game name to the clan format? (e.g., IM-Ryze)"
    ]

    try:
        dm = await member.create_dm()
        await dm.send("🪖 Welcome to **Impedance!** Please answer the following approval questions one by one:")

        answers = []
        for q in questions:
            await dm.send(q)
            msg = await client.wait_for(
                "message",
                check=lambda m: m.author == member and isinstance(m.channel, discord.DMChannel),
                timeout=600
            )
            answers.append(msg.content)

        # Confirmation message to recruit
        await dm.send("✅ Thank you for your cooperation! Your answers will be reviewed by our admins.")

        # Remove the public notification message
        await notify_msg.delete()

        # Send to admin review channel
        admin_channel = client.get_channel(ADMIN_REVIEW_CHANNEL_ID)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Use labels for formatted answers
        labels = [
            "Purpose of joining:",
            "Invited by an Impedance member, and who:",
            "Main Crossfire account:",
            "Willing to CCN:"
        ]

        formatted = ""
        for i, answer in enumerate(answers):
            label = labels[i] if i < len(labels) else f"Question {i+1}:"
            formatted += f"**{label}**\n{answer}\n\n"

        embed = discord.Embed(
            title=f"🪖 Recruit {member.display_name} for approval.",
            description=f"{formatted}📅 **Date answered:** `{now_str}`",
            color=discord.Color.blurple()
        )
        await admin_channel.send(embed=embed)
        print(f"📩 Sent recruit answers for {member.name}")

    except Exception as e:
        print(f"⚠️ Could not DM {member.name}: {e}")
        pending_recruits[member.id] = time.time()

        # Notify admin if they fail to respond
        await recruit_channel.send(
            f"⚠️ {member.mention} did not respond to DM within 10 minutes or blocked DMs."
        )


@client.event
async def on_message(message):
    """Send rotating reminders every 50 messages in the reminder channel."""
    if message.author == client.user:
        return

    if message.channel.id == REMINDER_CHANNEL_ID:
        state["message_counter"] += 1
        save_state()

        if state["message_counter"] >= 50:
            reminder = reminders[state["current_reminder"]]
            embed = discord.Embed(
                title="Reminders Impedance!",
                description=f"**{reminder['title']}**\n\n{reminder['description']}",
                color=discord.Color.orange()
            )
            await message.channel.send(embed=embed)
            print(f"📢 Sent reminder: {reminder['title']}")
            state["message_counter"] = 0
            state["current_reminder"] = (state["current_reminder"] + 1) % len(reminders)
            save_state()


@client.event
async def on_presence_update(before, after):
    """Announce when members with specific roles come online."""
    if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
        member = after
        role_ids = [r.id for r in member.roles]

        if ROLE_ID_QUEEN in role_ids:
            title, color = f"👑 Queen {member.name} just came online!", discord.Color.gold()
        elif ROLE_ID_CLAN_MASTER in role_ids:
            title, color = f"🌟 Clan Master {member.name} just came online!", discord.Color.blue()
        elif ROLE_ID_IMPEDANCE in role_ids:
            title, color = f"⭐ Impedance {member.name} just came online!", discord.Color.purple()
        elif ROLE_ID_OG_IMPEDANCE and ROLE_ID_OG_IMPEDANCE in role_ids:
            title, color = f"🎉 OG 🎉 {member.name} just came online!", discord.Color.red()
        else:
            return

        channel = client.get_channel(MAIN_CHANNEL_ID)
        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=after.display_avatar.url)
        await channel.send(embed=embed)
        print(f"📢 Announced online: {title}")


# --- Run bot in background thread ---
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

# --- Keep-alive server ---
if __name__ == "__main__":
    from keep_alive import ping_self
    threading.Thread(target=ping_self, daemon=True).start()
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
