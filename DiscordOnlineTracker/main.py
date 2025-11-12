# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
import time
from discord.ext import tasks
from keep_alive import app  # import the Flask app instead of start_keep_alive

# --- Intents ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)

# --- Channel IDs ---
MAIN_CHANNEL_ID = 1437768842871832597       # Main announcements
RECRUIT_CHANNEL_ID = 1437568595977834590    # Recruit candidates
REMINDER_CHANNEL_ID = 1369091668724154419   # Reminders channel

# --- Role IDs ---
ROLE_ID_QUEEN = 1437578521374363769         # 👑 Queen
ROLE_ID_CLAN_MASTER = 1389835747040694332   # 🌟 Clan Master
ROLE_ID_IMPEDANCE = 1437570031822176408     # ⭐ Impedance
ROLE_ID_OG_IMPEDANCE = 1437572916005834793  # 🎉 OG Impedance (optional)


@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    reminder_loop.start()
    print("🕒 Reminder loop started — posting every 3 minutes.")


@client.event
async def on_member_join(member):
    """Announce when a new member joins the server."""
    recruit_channel = client.get_channel(RECRUIT_CHANNEL_ID)
    if not recruit_channel or not isinstance(recruit_channel, discord.TextChannel):
        print("⚠️ Recruit channel not found or not a text channel.")
        return

    title = f"🪖 Recruit candidate joined — candidate {member.name}"
    embed = discord.Embed(title=title, color=discord.Color.teal())
    embed.set_thumbnail(url=member.display_avatar.url)
    await recruit_channel.send(embed=embed)
    print(f"📢 Announced new recruit candidate: {member.name}")


@client.event
async def on_presence_update(before, after):
    """Announce when members with specific roles come online."""
    if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
        member = after
        role_ids = [r.id for r in member.roles]

        print(f"🧩 Detected role IDs for {member.name}: {role_ids}")

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

        # Send announcement
        channel = client.get_channel(MAIN_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            print("⚠️ Main channel not found or not a text channel.")
            return

        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=after.display_avatar.url)
        await channel.send(embed=embed)
        print(f"📢 Sent special role announcement: {title}")


# --- Reminder messages ---
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

current_reminder = 0


@tasks.loop(minutes=3)
async def reminder_loop():
    """Sends one reminder every 3 minutes, rotating through the list."""
    global current_reminder
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    if not channel:
        print("⚠️ Reminder channel not found.")
        return

    reminder = reminders[current_reminder]
    embed = discord.Embed(
        title="Reminders Impedance!",
        description=f"**{reminder['title']}**\n\n{reminder['description']}",
        color=discord.Color.orange()
    )
    await channel.send(embed=embed)
    print(f"📢 Sent reminder: {reminder['title']}")

    current_reminder = (current_reminder + 1) % len(reminders)


# --- Run bot in a background thread so Flask can stay in foreground ---
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    time.sleep(5)
    client.run(token)


threading.Thread(target=run_bot, daemon=True).start()

# --- Start Flask as the main process Render monitors ---
if __name__ == "__main__":
    from keep_alive import ping_self
    threading.Thread(target=ping_self, daemon=True).start()
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
