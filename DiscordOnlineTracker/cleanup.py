import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def has_voting_role(member):
    """Check if member has any of the voting roles"""
    voting_roles = [
        1389835747040694332,  # Cᥣᥲᥒ Mᥲstᥱr🌟
        1437578521374363769,  # Queen❤️‍🔥
        1438420490455613540,  # cute ✨
        1437572916005834793,  # OG-Impèrius🐦‍🔥
    ]
    
    member_role_ids = [role.id for role in member.roles]
    return any(role_id in member_role_ids for role_id in voting_roles)

class CleanupSystem:
    def __init__(self, bot, guild, state):
        self.bot = bot
        self.guild = guild
        self.state = state
        
    def start_cleanup_task(self):
        """Start the cleanup task"""
        self.cleanup_task.start()
    
    @tasks.loop(hours=24)  # Run every 24 hours
    async def cleanup_task(self):
        """Main cleanup task"""
        logger.info("Running cleanup task...")
        
        # Check for ghost users (no roles)
        await self.check_ghost_users()
        
        # Check for inactive members (every 7 days)
        if datetime.now().weekday() == 0:  # Run on Mondays (once a week)
            await self.check_inactive_members()
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Wait until bot is ready before starting cleanup"""
        await self.bot.wait_until_ready()
    
    async def check_ghost_users(self):
        """Check for users with no roles (ghosts)"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                logger.error("Admin channel not found!")
                return
            
            ghost_users = []
            
            for member in self.guild.members:
                # Skip bots
                if member.bot:
                    continue
                
                # Skip users who recently rejoined (within 24 hours)
                if member.joined_at:
                    hours_since_join = (datetime.now() - member.joined_at).total_seconds() / 3600
                    if hours_since_join < 24:
                        continue
                
                # Check if member has only @everyone role
                if len(member.roles) == 1:  # Only @everyone
                    # Calculate days in server
                    join_date = member.joined_at
                    if join_date:
                        days_in_server = (datetime.now() - join_date).days
                        
                        # Only show if more than 1 day
                        if days_in_server >= 1:
                            ghost_users.append((member, days_in_server))
            
            if ghost_users:
                logger.info(f"Found {len(ghost_users)} ghost users")
                for member, days in ghost_users:
                    # Check if we've already reported this user recently
                    if self.state.is_user_checked(member.id):
                        continue
                    
                    embed = discord.Embed(
                        title="👻 Ghost User Detected",
                        description=f"**User:** {member.mention} ({member.name})\n"
                                  f"**Days in server:** {days} days\n"
                                  f"**Status:** No roles assigned",
                        color=discord.Color.dark_gray(),
                        timestamp=datetime.now()
                    )
                    
                    view = GhostUserVoteView(self.bot, member)
                    await channel.send(embed=embed, view=view)
                    
                    # Add to checked users
                    self.state.add_checked_user(member.id)
                    
                    # Wait a bit between messages to avoid rate
