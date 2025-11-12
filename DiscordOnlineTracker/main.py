# Render Start Command: python3 "bot code/DiscordOnlineTracker/main.py"

import threading
import discord
import os
from keep_alive import app  # import the Flask app instead of start_keep_alive

intents = discord.Intents.default()
intents.members = True
intents.presences = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_presence_update(before, after):
    if before.status != after.status and str(after.status) in ["online", "idle", "dnd"]:
        channel = client.get_channel(1437768842871832597)
        if not channel or not isinstance(channel, discord.TextChannel):
            print("⚠️ Channel not found or not a text channel.")
            return

        member = after
        roles_lower = [r.name.lower() for r in member.roles]

        if "queen" in roles_lower or "queen👑" in roles_lower:
            title, color = f"👑 Queen {member.name} just came online!", discord.Color.gold()
        elif "cᥣᥲᥒ mᥲstᥱr🌟" in roles_lower:
            title, color = f"🌟 Clan Master {member.name} just came online!", discord.Color.blue()
        elif "og-impedance🔫" in roles_lower:
            title, color = f"🎉 OG 🎉 {member.name} just came online!", discord.Color.red()
        elif "impedance⭐" in roles_lower:
            title, color = f"⭐ Impedance {member.name} just came online!", discord.Color.purple()
        else:
            title, color = f"🎉 {member.name} just came online! They're a member 🙂", discord.Color.green()

        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=after.display_avatar.url)
        await channel.send(embed=embed)
        print(f"📢 Sent announcement: {title}")

# --- run bot in a background thread so Flask can stay foreground ---
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not found in environment variables!")
        return
    print("🤖 Starting Discord bot…")
    client.run(token)

threading.Thread(target=run_bot, daemon=True).start()

# --- start Flask as the main process Render monitors ---
if __name__ == "__main__":
    from keep_alive import ping_self
    threading.Thread(target=ping_self, daemon=True).start()
    print("🌐 Starting Flask keep-alive server…")
    app.run(host="0.0.0.0", port=8080)
