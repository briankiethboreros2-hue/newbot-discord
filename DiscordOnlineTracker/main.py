# Render Start Command: python3 main.py

import threading
from keep_alive import start_keep_alive
import discord
import os

intents = discord.Intents.default()
intents.members = True
intents.presences = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")


@client.event
async def on_presence_update(before, after):
    if before.status != after.status and str(
            after.status) in ["online", "idle", "dnd"]:
        channel = client.get_channel(1437768842871832597)

        if channel is None:
            print(
                f"⚠️ Channel not found. Please update the channel ID in main.py"
            )
            return

        if not isinstance(channel, discord.TextChannel):
            print(
                f"⚠️ Channel is not a text channel. Please use a text channel ID."
            )
            return

        member = after

        role_names = [role.name for role in member.roles]
        role_names_lower = [name.lower() for name in role_names]

        if "queen" in role_names_lower or "queen👑" in role_names_lower:
            title = f"👑 Queen {member.name} just came online!"
            color = discord.Color.gold()
        elif "cᥣᥲᥒ mᥲstᥱr🌟" in role_names_lower:
            title = f"🌟 Clan Master {member.name} just came online!"
            color = discord.Color.blue()
        elif "og-impedance🔫" in role_names_lower:
            title = f"🎉 OG 🎉 {member.name} just came online!"
            color = discord.Color.red()
        elif "impedance⭐" in role_names_lower:
            title = f"⭐ Impedance {member.name} just came online!"
            color = discord.Color.purple()
        else:
            title = f"🎉 {member.name} just came online! They're a member 🙂"
            color = discord.Color.green()

        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=after.display_avatar.url)

        await channel.send(embed=embed)
        print(f"📢 Sent announcement: {title}")


# start Flask + self-pinger in a separate thread so this file continues
threading.Thread(target=start_keep_alive, daemon=True).start()

token = os.getenv('DISCORD_TOKEN')
if not token:
    print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
    print("Please add your Discord bot token in Replit's Secrets tab.")
    print("Key: DISCORD_TOKEN")
    exit(1)

print("🤖 Starting Discord bot...")
client.run(token)
