import os
import discord
from discord.ext import commands, tasks
import asyncio
import logging
from datetime import datetime, timedelta
import traceback
import sys

# Import our modules
from recruitment import RecruitmentSystem
from online_announce import OnlineAnnounceSystem
from cleanup import CleanupSystem

# Import your existing keep_alive
try:
    from keep_alive import start_keep_alive
    keep_alive_available = True
    logger.info("✅ keep_alive.py found and imported")
except ImportError as e:
    keep_alive_available = False
    logger.warning(f"⚠️ keep_alive.py not found: {e}")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
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
        
        # Store guild for quick access
        self.main_guild = None

    async def setup_hook(self):
        """Setup hook - runs before on_ready"""
        logger.info("🔧 Running setup_hook...")
        # Add persistent views here if needed
        self.add_view(TryoutVoteView(self))
        self.add_view(TryoutDecisionView(self))
        self.add_view(GhostUserVoteView(self))
        self.add_view(InactiveMemberVoteView(self))
        self.add_view(ReviewDecisionView(self))

    async def on_ready(self):
        """Bot is ready - set up systems"""
        logger.info(f'✅ Bot is online as {self.user} (ID: {self.user.id})')
        logger.info(f'📊 Connected to {len(self.guilds)} guild(s)')
        
        # Log all guilds
        for guild in self.guilds:
            logger.info(f'🏰 Guild: {guild.name} (ID: {guild.id})')
            
        # Get the main guild (assuming bot is in one guild)
        if self.guilds:
            self.main_guild = self.guilds[0]
            logger.info(f'🏰 Main guild: {self.main_guild.name} (ID: {self.main_guild.id})')
            
            # Initialize systems with the guild
            self.recruitment = RecruitmentSystem(self, self.main_guild)
            self.online_announce = OnlineAnnounceSystem(self, self.main_guild)
            self.cleanup = CleanupSystem(self, self.main_guild)
            
            # Start cleanup task
            if hasattr(self.cleanup, 'start_cleanup_task'):
                self.cleanup.start_cleanup_task()
                logger.info("✅ Cleanup task started")
            
            # Verify channels and roles exist
            await self.verify_resources()
            
            logger.info("✅ All systems initialized")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Impèrius Recruits"
            )
        )
        
        logger.info("✅ Bot is fully operational!")
    
    async def verify_resources(self):
        """Verify that all channels and roles exist"""
        logger.info("🔍 Verifying channels and roles...")
        
        # Channel verification
        channels_to_check = [
            ("RECRUIT_CONFIRM_CHANNEL", 1437568595977834590),
            ("ADMIN_CHANNEL", 1455138098437689387),
            ("REVIEW_CHANNEL", 1454802873300025396),
            ("TRYOUT_RESULT_CHANNEL", 1455205385463009310),
            ("ATTENDANCE_CHANNEL", 1437768842871832597),
            ("INACTIVE_ACCESS_CHANNEL", 1369091668724154419)
        ]
        
        for name, channel_id in channels_to_check:
            channel = self.get_channel(channel_id)
            if channel:
                logger.info(f"✅ Found {name}: {channel.name}")
            else:
                logger.warning(f"⚠️ Channel not found: {name} (ID: {channel_id})")
        
        # Role verification
        roles_to_check = [
            ("IMPERIUS_ROLE", 1437570031822176408),
            ("OG_ROLE", 1437572916005834793),
            ("CLAN_MASTER_ROLE", 1389835747040694332),
            ("QUEEN_ROLE", 1437578521374363769),
            ("CUTE_ROLE", 1438420490455613540),
            ("INACTIVE_ROLE", 1454803208995340328)
        ]
        
        for name, role_id in roles_to_check:
            role = self.main_guild.get_role(role_id)
            if role:
                logger.info(f"✅ Found {name}: {role.name}")
            else:
                logger.warning(f"⚠️ Role not found: {name} (ID: {role_id})")
    
    async def on_member_join(self, member):
        """Handle new member joining"""
        try:
            logger.info(f"👤 New member joined: {member.name} (ID: {member.id})")
            if self.recruitment:
                await self.recruitment.handle_new_member(member)
        except Exception as e:
            logger.error(f"❌ Error in on_member_join: {e}")
            traceback.print_exc()
    
    async def on_member_update(self, before, after):
        """Handle member status changes (online/offline)"""
        try:
            if self.online_announce:
                await self.online_announce.check_online_status(before, after)
        except Exception as e:
            logger.error(f"❌ Error in on_member_update: {e}")
            traceback.print_exc()
    
    async def on_message(self, message):
        """Handle all messages (for DMs and interviews)"""
        # Don't respond to ourselves
        if message.author == self.user:
            return
            
        # Handle DM messages for interviews
        if isinstance(message.channel, discord.DMChannel):
            try:
                logger.info(f"💬 DM from {message.author.name}: {message.content[:50]}...")
                if self.recruitment:
                    await self.recruitment.handle_dm_response(message)
            except Exception as e:
                logger.error(f"❌ Error handling DM: {e}")
                traceback.print_exc()
        
        # Let commands process
        await self.process_commands(message)

    async def on_error(self, event, *args, **kwargs):
        """Handle errors in events"""
        logger.error(f"❌ Error in event {event}:")
        traceback.print_exc()

# Import views for persistent views
from recruitment import TryoutVoteView, TryoutDecisionView
from cleanup import GhostUserVoteView, InactiveMemberVoteView, ReviewDecisionView

def main():
    """Main function to run the bot"""
    logger.info("🚀 Starting Imperial Bot...")
    
    # Start keep_alive if available
    if keep_alive_available:
        logger.info("🌐 Starting keep_alive server...")
        # Start in a thread so it doesn't block
        import threading
        keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("✅ keep_alive server started in background")
    
    # Create bot instance
    bot = ImperialBot()
    
    # Get token from environment (Render sets this)
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        logger.error("Please set DISCORD_TOKEN in Render environment variables")
        # Try to get from file as fallback (for local testing)
        try:
            with open('token.txt', 'r') as f:
                token = f.read().strip()
                logger.info("✅ Found token in token.txt")
        except:
            logger.error("❌ Also no token.txt file found")
            return
    
    # Run the bot with error handling
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"🔗 Connecting to Discord... (Attempt {retry_count + 1}/{max_retries})")
            bot.run(token, reconnect=True)
        except discord.LoginFailure:
            logger.error("❌ Invalid token. Please check your DISCORD_TOKEN.")
            break
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            traceback.print_exc()
            retry_count += 1
            if retry_count < max_retries:
                logger.info(f"🔄 Restarting in 10 seconds...")
                time.sleep(10)
            else:
                logger.error(f"❌ Max retries ({max_retries}) reached. Giving up.")
                break

if __name__ == "__main__":
    main()
