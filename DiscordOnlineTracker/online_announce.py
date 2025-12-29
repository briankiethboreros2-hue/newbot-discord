import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OnlineAnnounce:
    def __init__(self, bot):
        self.bot = bot
        self.online_members = set()  # Track currently announced members
        self.announce_channel_id = 1437768842871832597  # Attendance channel
        self.role_names = {
            1437570031822176408: "Impèrius🔥",
            1437572916005834793: "OG-Impèrius🐦‍🔥",
            1389835747040694332: "Cᥣᥲᥒ Mᥲstᥱr🌟",
            1437578521374363769: "Queen❤️‍🔥",
            1438420490455613540: "cute ✨"
        }
        self.special_titles = {
            1389835747040694332: "The Cᥣᥲᥒ Mᥲstᥱr🌟",
            1437578521374363769: "The Queen❤️‍🔥",
            1438420490455613540: "Most cute ✨"
        }
        
    def start_tracking(self):
        """Start tracking online members"""
        self.check_online_members.start()
    
    @tasks.loop(seconds=30)  # Check every 30 seconds
    async def check_online_members(self):
        """Check for members who came online"""
        try:
            guild = self.bot.guilds[0] if self.bot.guilds else None
            if not guild:
                return
            
            channel = guild.get_channel(self.announce_channel_id)
            if not channel:
                return
            
            for member in guild.members:
                # Skip bots and offline members
                if member.bot or member.status == discord.Status.offline:
                    if member.id in self.online_members:
                        self.online_members.remove(member.id)
                    continue
                
                # Skip if already announced as online
                if member.id in self.online_members:
                    continue
                
                # Check if member has any of our tracked roles
                has_tracked_role = False
                member_role = None
                
                for role_id in self.role_names.keys():
                    role = discord.utils.get(member.roles, id=role_id)
                    if role:
                        has_tracked_role = True
                        member_role = role
                        break
                
                if has_tracked_role and member_role:
                    # Check if member was offline before (not in our tracking)
                    # This prevents announcing on bot startup
                    if member.id not in self.online_members:
                        await self.announce_online(member, member_role, channel)
                        self.online_members.add(member.id)
                
        except Exception as e:
            logger.error(f"Error in online check: {e}")
    
    async def announce_online(self, member, role, channel):
        """Announce member coming online"""
        try:
            role_id = role.id
            role_name = self.role_names.get(role_id, role.name)
            
            # Get appropriate title
            if role_id in self.special_titles:
                title = self.special_titles[role_id]
                message = f"{title} **{member.display_name}** is online! {member.mention}"
            else:
                message = f"{role_name} **{member.display_name}** is online! {member.mention}"
            
            # Add avatar and profile link
            embed = discord.Embed(
                description=message,
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")
            
            await channel.send(embed=embed)
            logger.info(f"Announced {member.display_name} ({role_name}) online")
            
        except Exception as e:
            logger.error(f"Error announcing online: {e}")
    
    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Listen for presence changes"""
        try:
            # Skip bots and DMs
            if before.bot or not before.guild:
                return
            
            # Check if member came online (from offline to any online status)
            if (before.status == discord.Status.offline and 
                after.status != discord.Status.offline):
                
                guild = after.guild
                channel = guild.get_channel(self.announce_channel_id)
                
                if not channel:
                    return
                
                # Check if member has tracked role
                has_tracked_role = False
                member_role = None
                
                for role_id in self.role_names.keys():
                    role = discord.utils.get(after.roles, id=role_id)
                    if role:
                        has_tracked_role = True
                        member_role = role
                        break
                
                if has_tracked_role and member_role:
                    if after.id not in self.online_members:
                        await self.announce_online(after, member_role, channel)
                        self.online_members.add(after.id)
            
            # If member went offline, remove from tracking
            elif (before.status != discord.Status.offline and 
                  after.status == discord.Status.offline):
                
                if after.id in self.online_members:
                    self.online_members.remove(after.id)
                    
        except Exception as e:
            logger.error(f"Error in presence update: {e}")

async def setup(bot):
    """Setup function for cog"""
    online_announce = OnlineAnnounce(bot)
    bot.add_cog(online_announce)
    online_announce.start_tracking()
    logger.info("Online Announcement system started")
