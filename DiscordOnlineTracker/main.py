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
except ImportError as e:
    keep_alive_available = False
    print(f"⚠️ keep_alive.py not found: {e}")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Bot intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True
intents.guilds = True

class ImperialBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        # Initialize systems
        self.recruitment = None
        self.online_announce = None
        self.cleanup = None
        
        # Store guild for quick access
        self.main_guild = None
        
        # Store member join times to prevent duplicate processing
        self.recent_joins = {}

    async def setup_hook(self):
        """Setup hook - runs before on_ready"""
        logger.info("🔧 Running setup_hook...")
        # Persistent views will be added in on_ready after systems are initialized

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
            
            # Start join cleanup task
            self.cleanup_recent_joins.start()
            
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

    @tasks.loop(minutes=5)
    async def cleanup_recent_joins(self):
        """Clean up recent joins dictionary to prevent memory leak"""
        now = datetime.now()
        to_remove = []
        
        for user_id, join_time in list(self.recent_joins.items()):
            if (now - join_time).total_seconds() > 300:  # 5 minutes
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del self.recent_joins[user_id]
    
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
            # Prevent duplicate processing for returnees
            user_id = member.id
            current_time = datetime.now()
            
            if user_id in self.recent_joins:
                # User joined recently, check if it's been at least 1 minute
                last_join = self.recent_joins[user_id]
                time_diff = (current_time - last_join).total_seconds()
                
                if time_diff < 60:  # 1 minute cooldown
                    logger.info(f"⏸️ Skipping duplicate join for {member.name} (rejoined too quickly)")
                    return
            
            # Store join time
            self.recent_joins[user_id] = current_time
            
            logger.info(f"👤 New member joined: {member.name} (ID: {member.id})")
            
            # Check if member already has a role (returnee)
            has_role = len(member.roles) > 1  # More than just @everyone
            
            if has_role:
                logger.info(f"↩️ Returnee detected: {member.name} already has roles")
                # Don't interview returnees
                return
            
            if self.recruitment:
                await self.recruitment.handle_new_member(member)
        except Exception as e:
            logger.error(f"❌ Error in on_member_join: {e}")
            traceback.print_exc()
    
    async def on_member_remove(self, member):
        """Handle member leaving/kicked"""
        try:
            logger.info(f"👋 Member left: {member.name} (ID: {member.id})")
            
            # Clean up any active interviews for this user
            if self.recruitment and member.id in self.recruitment.active_interviews:
                del self.recruitment.active_interviews[member.id]
                logger.info(f"🧹 Cleared interview data for {member.name}")
            
            # Clean up interview timeouts
            if self.recruitment and member.id in self.recruitment.interview_timeouts:
                del self.recruitment.interview_timeouts[member.id]
                
        except Exception as e:
            logger.error(f"❌ Error in on_member_remove: {e}")
    
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
                import time
                time.sleep(10)
            else:
                logger.error(f"❌ Max retries ({max_retries}) reached. Giving up.")
                break

if __name__ == "__main__":
    main()
