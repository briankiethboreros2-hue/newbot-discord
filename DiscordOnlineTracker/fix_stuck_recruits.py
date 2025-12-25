# fix_stuck_recruits.py
# One-time script to clean up stuck recruits from before the fix
import json
import discord
import asyncio
import os
import time

TOKEN = os.getenv("DISCORD_TOKEN")  # Same token as your main bot
CHANNEL_ID = 1437586858417852438  # Your staff_review channel ID

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Cleanup bot logged in as {client.user}")
    print("🔄 Starting stuck recruit cleanup...")
    
    try:
        # Load existing pending recruits
        with open("pending_recruits.json", "r") as f:
            pending_recruits = json.load(f)
        print(f"📊 Loaded {len(pending_recruits)} total pending recruits")
    except Exception as e:
        print(f"❌ Could not load pending_recruits.json: {e}")
        await client.close()
        return
    
    staff_ch = client.get_channel(CHANNEL_ID)
    if not staff_ch:
        print("❌ Could not find staff review channel")
        await client.close()
        return
    
    current_time = time.time()
    stuck_count = 0
    total_count = len(pending_recruits)
    
    print(f"🔍 Scanning {total_count} pending recruits...")
    
    for uid, entry in list(pending_recruits.items()):
        # Skip if already resolved or under review
        if entry.get("resolved", False):
            continue
            
        if entry.get("under_review", False):
            continue
        
        # Check if this is a stuck entry (older than 5 minutes)
        entry_time = entry.get("last", entry.get("started", 0))
        if current_time - entry_time > 300:  # 5 minutes or older
            stuck_count += 1
            
            # Get member info if possible
            guild = staff_ch.guild
            display_name = f"ID {uid}"
            member_mention = f"<@{uid}>"
            
            if guild:
                try:
                    m = guild.get_member(int(uid))
                    if m:
                        display_name = f"{m.display_name} (@{m.name})"
                        member_mention = m.mention
                except Exception:
                    pass
            
            print(f"🪖 Found stuck recruit: {display_name}")
            
            # Create admin review embed
            embed = discord.Embed(
                title=f"🪖 [CLEANUP] Recruit {display_name}",
                description=(
                    "**Stuck recruit found from before fix**\n\n"
                    "This recruit joined but verification stalled.\n\n"
                    "**Options:**\n"
                    "• 👍 = Kick recruit\n"
                    "• 👎 = Keep recruit (manual verification needed)\n\n"
                    f"**User:** {member_mention}"
                ),
                color=0x800080
            )
            embed.add_field(name="User ID", value=f"`{uid}`", inline=True)
            embed.add_field(name="Stuck since", value=f"<t:{int(entry_time)}:R>", inline=True)
            
            if entry.get("answers"):
                answers_count = len(entry["answers"])
                embed.add_field(name="Progress", value=f"Answered {answers_count}/5 questions", inline=False)
            
            try:
                # Send to admin channel
                review_msg = await staff_ch.send(embed=embed)
                await review_msg.add_reaction("👍")
                await review_msg.add_reaction("👎")
                
                # Mark as under review
                entry["under_review"] = True
                entry["review_message_id"] = review_msg.id
                entry["cleanup_timestamp"] = current_time
                
                print(f"✅ Created review for {display_name}")
                
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"⚠️ Failed to create review for {uid}: {e}")
    
    # Save updated data
    try:
        with open("pending_recruits.json", "w") as f:
            json.dump(pending_recruits, f, indent=2)
        print(f"💾 Saved updated data")
    except Exception as e:
        print(f"⚠️ Could not save data: {e}")
    
    # Send summary
    summary_embed = discord.Embed(
        title="🧹 Cleanup Complete",
        description=f"Scanned {total_count} pending recruits\nFound and marked {stuck_count} stuck recruit(s) for review",
        color=0x00ff00
    )
    await staff_ch.send(embed=summary_embed)
    
    print(f"✅ Cleanup complete! Found {stuck_count} stuck recruit(s)")
    print("🛑 Bot will exit in 5 seconds...")
    await asyncio.sleep(5)
    await client.close()

@client.event
async def on_disconnect():
    print("🔌 Cleanup bot disconnected")

client.run(TOKEN)
