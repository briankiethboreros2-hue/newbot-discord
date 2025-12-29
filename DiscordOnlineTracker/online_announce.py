import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OnlineAnnounce:
    def __init__(self, bot, guild, state):
        self.bot = bot
        self.guild = guild
        self.state = state
        self.online_members = set()  # Track currently announced members
        self.announce_channel_id = 1437768842871832597  # Attendance channel
        self.bot_startup_time = datetime.now()
        
        # Role configuration
        self.role_config = {
            1437570031822176408: {  # Impèrius🔥
                "name": "Impèrius🔥",
                "format": "{role} {member} is online!"
            },
            1437572916005834793: {  # OG-Impèrius🐦‍🔥
                "name": "OG-Impèrius🐦‍🔥", 
                "format": "{role} {member} is online!"
            },
            1389835747040694332: {  # Cᥣᥲᥒ Mᥲstᥱr🌟
                "name": "Cᥣᥲᥒ Mᥲstᥱr🌟",
                "format": "The Cᥣᥲᥒ Mᥲstᥱr🌟 {member} is online!"
            },
            1437578521374363769: {  # Queen❤️‍🔥
                "name": "Queen❤️‍🔥",
                "format": "The Queen❤️‍🔥 {member} is online!"
            },
            1438420490455613540: {  # cute ✨
                "name": "cute ✨",
                "format": "Most cute ✨ {member} went online!"
            }
        }
        
        self.tracked_role_ids = list(self.role_config.keys())
        self.initialized = False
    
    def start_tracking(self):
        """Start tracking online members"""
        logger.info("🟢 Starting online announcement tracking...")
        
        # Clear tracking
        self.online_members.clear()
        
        # Start tasks
        self.init_delayed.start()  # Wait 30 seconds before initial check
        self.presence_check.start()  # Regular presence check
    
    @tasks.loop(count=1)  # Run once after delay
    async def init_delayed(self):
        """Wait 30 seconds after bot startup before initializing"""
        await asyncio.sleep(30)  # Wait for Discord to send all presence data
        logger.info("✅ Delayed initialization complete")
        self.initialized = True
    
    @tasks.loop(seconds=45)  # Check every 45 seconds
    async def presence_check(self):
        """Main presence checking task"""
        if not self.initialized:
            return
            
        try:
            channel = self.guild.get_channel(self.announce_channel_id)
            if not channel:
                return
            
            # Check each member
            for member in self.guild.members:
                await self.check_member_status(member, channel)
                
        except Exception as e:
            logger.error(f"❌ Error in presence_check: {e}")
    
    async def check_member_status(self, member, channel):
        """Check and announce a single member's status"""
        try:
            # Skip bots
            if member.bot:
                return
            
            # Check if member has any tracked role
            has_tracked_role = False
            member_role = None
            
            for role_id in self.tracked_role_ids:
                role = discord.utils.get(member.roles, id=role_id)
                if role:
                    has_tracked_role = True
                    member_role = role
                    break
            
            if not has_tracked_role or not member_role:
                return
            
            # Get current status
            current_status = member.status
            member_id = member.id
            
            # Check if member is online (not offline)
            if current_status != discord.Status.offline:
                # Member is online - check if we need to announce
                if member_id not in self.online_members:
                    # This is a new online status
                    await self.announce_online(member, member_role, channel)
                    self.online_members.add(member_id)
                    logger.info(f"✅ Announced {member.display_name} as online")
            else:
                # Member is offline - remove from tracking
                if member_id in self.online_members:
                    self.online_members.remove(member_id)
                    logger.info(f"📴 {member.display_name} went offline")
                    
        except Exception as e:
            logger.error(f"❌ Error checking member {member.name}: {e}")
    
    async def announce_online(self, member, role, channel):
        """Announce a member coming online"""
        try:
            role_id = role.id
            role_config = self.role_config.get(role_id)
            
            if not role_config:
                return
            
            role_name = role_config["name"]
            format_str = role_config["format"]
            
            # Format the message
            message = format_str.format(role=role_name, member=member.display_name)
            
            # Create embed
            embed = discord.Embed(
                description=f"{message} {member.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # Add member avatar
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Add member info
            embed.add_field(name="Member", value=member.display_name, inline=True)
            embed.add_field(name="Role", value=role_name, inline=True)
            embed.add_field(name="Status", value=str(member.status).title(), inline=True)
            
            # Send announcement
            await channel.send(embed=embed)
            
            logger.info(f"📢 Announced {member.display_name} ({role_name}) online")
            
        except Exception as e:
            logger.error(f"❌ Error announcing {member.display_name}: {e}")
    
    # Event listener for presence updates
    async def on_presence_update(self, before, after):
        """Handle presence updates in real-time"""
        if not self.initialized:
            return
            
        try:
            # Skip if not in our guild
            if not after.guild or after.guild.id != self.guild.id:
                return
            
            # Skip bots
            if after.bot:
                return
            
            channel = self.guild.get_channel(self.announce_channel_id)
            if not channel:
                return
            
            # Check for status change
            if before.status != after.status:
                await self.check_member_status(after, channel)
                
        except Exception as e:
            logger.error(f"❌ Error in on_presence_update: {e}")
    
    @presence_check.before_loop
    async def before_presence_check(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()
    
    @init_delayed.before_loop
    async def before_init_delayed(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()
