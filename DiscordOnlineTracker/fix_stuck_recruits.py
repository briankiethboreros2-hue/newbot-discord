# fix_stuck_recruits.py - IMPORTABLE VERSION
import json
import discord
import asyncio
import os
import time

async def cleanup_stuck_recruits():
    """Run stuck recruit cleanup - returns count of cleaned recruits"""
    print("🔄 Starting stuck recruit cleanup...")
    
    try:
        # Load existing pending recruits
        with open("pending_recruits.json", "r") as f:
            pending_recruits = json.load(f)
        print(f"📊 Loaded {len(pending_recruits)} total pending recruits")
    except Exception as e:
        print(f"❌ Could not load pending_recruits.json: {e}")
        return 0
    
    # We need a client to access Discord
    # This will be passed from main bot
    return pending_recruits  # Return data for main bot to process

def should_cleanup_user(entry, current_time):
    """Check if a user entry needs cleanup"""
    if entry.get("resolved", False) or entry.get("under_review", False):
        return False
    
    entry_time = entry.get("last", entry.get("started", 0))
    return current_time - entry_time > 300  # 5 minutes or older

async def create_admin_review(client, uid, entry, staff_channel_id):
    """Create admin review message for a stuck recruit"""
    staff_ch = client.get_channel(staff_channel_id)
    if not staff_ch:
        return None
    
    current_time = time.time()
    entry_time = entry.get("last", entry.get("started", 0))
    
    # Get member info
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
    
    # Create embed
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
        review_msg = await staff_ch.send(embed=embed)
        await review_msg.add_reaction("👍")
        await review_msg.add_reaction("👎")
        
        return review_msg.id  # Return message ID
        
    except Exception as e:
        print(f"⚠️ Failed to create review for {uid}: {e}")
        return None

# Remove the auto-run code at the bottom
# client.run(TOKEN)  <-- DELETE THIS LINE
