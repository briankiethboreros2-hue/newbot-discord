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
        self.tracked_members = set()  # Track members we've seen online
    
    async def check_online_status(self, before, after):
        """Check if member came online"""
        # Skip if not in our guild
        if after.guild.id != self.guild.id:
            return
        
        # Skip bot users
        if after.bot:
            return
        
        # Get member's current roles
        member_roles = [role.id for role in after.roles]
        
        # Check if member has any of the tracked roles
        tracked_roles = [
            1437570031822176408,  # Impèrius🔥
            1437572916005834793,  # OG-Impèrius🐦‍🔥
            1389835747040694332,  # Cᥣᥲᥒ Mᥲstᥱr🌟
            1437578521374363769,  # Queen❤️‍🔥
            1438420490455613540   # cute ✨
        ]
        
        # Check if member has any tracked role
        has_tracked_role = any(role_id in member_roles for role_id in tracked_roles)
        
        # Only announce if member has a tracked role
        if not has_tracked_role:
            return
        
        # Check if status changed from offline to online (not idle/dnd)
        # Only announce when explicitly coming online from offline
        if (before.status == discord.Status.offline and 
            after.status == discord.Status.online):
            await self.announce_online(after)
        
        # Also announce when changing from dnd/idle to online
        elif ((before.status == discord.Status.dnd or before.status == discord.Status.idle) and 
              after.status == discord.Status.online):
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
            channel = self.bot.get_channel(1437768842871832597)  # ATTENDANCE_CHANNEL
            if not channel:
                logger.error(f"Attendance channel not found!")
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
                logger.info(f"Announced {member.name} as online")
                
        except Exception as e:
            logger.error(f"Error announcing online status: {e}")
    
    async def get_announcement_text(self, member):
        """Get the appropriate announcement text based on roles"""
        member_name = member.display_name
        
        # Check roles in order of importance
        if 1438420490455613540 in [role.id for role in member.roles]:  # cute ✨
            return f"Most cute ✨ **{member_name}** went online! 💫"
        
        elif 1437578521374363769 in [role.id for role in member.roles]:  # Queen❤️‍🔥
            return f"The Queen❤️‍🔥 **{member_name}** is online! 👑"
        
        elif 1389835747040694332 in [role.id for role in member.roles]:  # Cᥣᥲᥒ Mᥲstᥱr🌟
            return f"The Cᥣᥲᥒ Mᥲstᥱr🌟 **{member_name}** is online! ⭐"
        
        elif 1437572916005834793 in [role.id for role in member.roles]:  # OG-Impèrius🐦‍🔥
            return f"OG-Impèrius🐦‍🔥 **{member_name}** is online! 🔥"
        
        elif 1437570031822176408 in [role.id for role in member.roles]:  # Impèrius🔥
            return f"Impèrius🔥 **{member_name}** is online! 🛡️"
        
        # Check if member has any other role (not a recruit)
        elif len(member.roles) > 1:  # More than just @everyone
            return f"Member **{member_name}** is online! 👋"
        
        return None  # Don't announce recruits without roles
