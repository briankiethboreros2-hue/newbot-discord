import os
import discord
from discord.ext import commands, tasks
import asyncio
import logging
from datetime import datetime, timedelta
import traceback

# Import our modules
from recruitment import RecruitmentSystem
from online_announce import OnlineAnnounceSystem
from cleanup import CleanupSystem

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot intents (REQUIRED for member tracking)
intents = discord.Intents.default()
intents.members = True  # Needed for member join/leave events
intents.message_content = True  # Needed to read messages
intents.presences = True  # Needed for online status tracking
intents.guilds = True

class ImperialBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",  # You can change this if needed
            intents=intents,
            help_command=None
        )
        
        # Initialize systems
        self.recruitment = None
        self.online_announce = None
        self.cleanup = None
        
        # Configuration - Channel IDs from your requirements
        self.RECRUIT_CONFIRM_CHANNEL = 1437568595977834590  # Welcome channel
        self.ADMIN_CHANNEL = 1455138098437689387  # Admin notifications
        self.REVIEW_CHANNEL = 1454802873300025396  # Review channel
        self.TRYOUT_RESULT_CHANNEL = 1455205385463009310  # Tryout results
        self.ATTENDANCE_CHANNEL = 1437768842871832597  # Online announcements
        self.INACTIVE_ACCESS_CHANNEL = 1369091668724154419  # Inactive members can access
        
        # Role IDs
        self.IMPERIUS_ROLE = 1437570031822176408  # Impèrius🔥
        self.OG_ROLE = 1437572916005834793  # OG-Impèrius🐦‍🔥
        self.CLAN_MASTER_ROLE = 1389835747040694332  # Cᥣᥲᥒ Mᥲstᥱr🌟
        self.QUEEN_ROLE = 1437578521374363769  # Queen❤️‍🔥
        self.CUTE_ROLE = 1438420490455613540  # cute ✨
        self.INACTIVE_ROLE = 1454803208995340328  # Inactive role
        
        # Voice channel for inactive members
        self.INACTIVE_VOICE_CHANNEL = 1437575744824934531
        
        # Store guild for quick access
        self.main_guild = None

    async def on_ready(self):
        """Bot is ready - set up systems"""
        logger.info(f'✅ Bot is online as {self.user}')
        logger.info(f'📊 Connected to {len(self.guilds)} guild(s)')
        
        # Get the main guild (assuming bot is in one guild)
        if self.guilds:
            self.main_guild = self.guilds[0]
            logger.info(f'🏰 Main guild: {self.main_guild.name}')
            
            # Initialize systems with the guild
            self.recruitment = RecruitmentSystem(self, self.main_guild)
            self.online_announce = OnlineAnnounceSystem(self, self.main_guild)
            self.cleanup = CleanupSystem(self, self.main_guild)
            
            # Start cleanup task
            if hasattr(self.cleanup, 'start_cleanup_task'):
                self.cleanup.start_cleanup_task()
            
            logger.info("✅ All systems initialized")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Impèrius Recruits"
            )
        )
    
    async def on_member_join(self, member):
        """Handle new member joining"""
        try:
            if self.recruitment:
                await self.recruitment.handle_new_member(member)
        except Exception as e:
            logger.error(f"Error in on_member_join: {e}")
            traceback.print_exc()
    
    async def on_member_update(self, before, after):
        """Handle member status changes (online/offline)"""
        try:
            if self.online_announce:
                await self.online_announce.check_online_status(before, after)
        except Exception as e:
            logger.error(f"Error in on_member_update: {e}")
            traceback.print_exc()
    
    async def on_message(self, message):
        """Handle all messages (for DMs and interviews)"""
        # Let commands process first
        await self.process_commands(message)
        
        # Handle DM messages for interviews
        if isinstance(message.channel, discord.DMChannel) and message.author != self.user:
            try:
                if self.recruitment:
                    await self.recruitment.handle_dm_response(message)
            except Exception as e:
                logger.error(f"Error handling DM: {e}")
                traceback.print_exc()

    async def setup_hook(self):
        """Setup hook for tasks"""
        # Any pre-start setup can go here
        pass

# Keep alive for Render (you said you have this)
try:
    from keep_alive import keep_alive
    keep_alive_available = True
except ImportError:
    keep_alive_available = False
    logger.warning("keep_alive.py not found - running without keep_alive")

def main():
    """Main function to run the bot"""
    # Start keep_alive if available
    if keep_alive_available:
        keep_alive()
        logger.info("✅ keep_alive started")
    
    # Create bot instance
    bot = ImperialBot()
    
    # Get token from environment (Render sets this)
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        logger.error("Please set DISCORD_TOKEN in Render environment variables")
        return
    
    # Run the bot with error handling
    try:
        bot.run(token, reconnect=True)
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
