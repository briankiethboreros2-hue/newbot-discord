import discord
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OnlineAnnounceSystem:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.last_online = {}  # Store last online announcements to prevent spam
    
    async def check_online_status(self, before, after):
        """Check if member came online"""
        # Skip if not in our guild
        if after.guild.id != self.guild.id:
            return
        
        # Skip bot users
        if after.bot:
            return
        
        # Check if status changed to online (from offline)
        if before.status == discord.Status.offline and after.status != discord.Status.offline:
            await self.announce_online(after)
    
    async def announce_online(self, member):
        """Announce member going online"""
        try:
            # Prevent spam (only announce once every 30 minutes per user)
            user_id = member.id
            current_time = datetime.now()
            
            if user_id in self.last_online:
                last_time = self.last_online[user_id]
                time_diff = (current_time - last_time).total_seconds()
                if time_diff < 1800:  # 30 minutes
                    return
            
            self.last_online[user_id] = current_time
            
            # Get attendance channel
            channel = self.bot.get_channel(self.bot.ATTENDANCE_CHANNEL)
            if not channel:
                logger.error(f"Attendance channel not found: {self.bot.ATTENDANCE_CHANNEL}")
                return
            
            # Get member's highest role for announcement
            announcement = await self.get_announcement_text(member)
            
            if announcement:
                # Create embed
                embed = discord.Embed(
                    description=announcement,
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                # Add member avatar
                embed.set_thumbnail(url=member.display_avatar.url)
                
                # Add footer with time
                embed.set_footer(text="Online Status")
                
                await channel.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error announcing online status: {e}")
    
    async def get_announcement_text(self, member):
        """Get the appropriate announcement text based on roles"""
        member_name = member.display_name
        
        # Check roles in order of importance
        if self.bot.CUTE_ROLE in [role.id for role in member.roles]:
            return f"Most cute ✨ **{member_name}** went online! 💫"
        
        elif self.bot.QUEEN_ROLE in [role.id for role in member.roles]:
            return f"The Queen❤️‍🔥 **{member_name}** is online! 👑"
        
        elif self.bot.CLAN_MASTER_ROLE in [role.id for role in member.roles]:
            return f"The Cᥣᥲᥒ Mᥲstᥱr🌟 **{member_name}** is online! ⭐"
        
        elif self.bot.OG_ROLE in [role.id for role in member.roles]:
            return f"OG-Impèrius🐦‍🔥 **{member_name}** is online! 🔥"
        
        elif self.bot.IMPERIUS_ROLE in [role.id for role in member.roles]:
            return f"Impèrius🔥 **{member_name}** is online! 🛡️"
        
        # Check if member has any role (not a recruit)
        elif len(member.roles) > 1:  # More than just @everyone
            return f"Member **{member_name}** is online! 👋"
        
        return None  # Don't announce recruits without roles
