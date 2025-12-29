import os
import discord
from discord.ext import commands, tasks
import asyncio
import logging
from datetime import datetime, timedelta
import traceback
import sys
import time

# Import our modules
from recruitment import RecruitmentSystem
from online_announce import OnlineAnnounce
from cleanup import CleanupSystem, InactiveMemberVoteView
from state_manager import StateManager

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
        
        self.state = StateManager()
        self.recruitment = None
        self.online_announce = None
        self.cleanup_system = None
        self.main_guild = None
        self.bot_start_time = datetime.now()

    async def setup_hook(self):
        """Setup hook - runs before on_ready"""
        logger.info("🔧 Running setup_hook...")
        
        if hasattr(self.state, 'start_auto_save'):
            self.state.start_auto_save()
        
        if hasattr(self, 'cleanup_state_task'):
            self.cleanup_state_task.start()

    async def on_ready(self):
        """Bot is ready - set up systems"""
        logger.info(f'✅ Bot is online as {self.user} (ID: {self.user.id})')
        logger.info(f'📊 Connected to {len(self.guilds)} guild(s)')
        
        # Log all guilds
        for guild in self.guilds:
            logger.info(f'🏰 Guild: {guild.name} (ID: {guild.id}) - Members: {guild.member_count}')
        
        # Get the main guild
        if self.guilds:
            self.main_guild = self.guilds[0]
            logger.info(f'🏰 Main guild: {self.main_guild.name} (ID: {self.main_guild.id})')
            
            try:
                # Initialize systems
                self.recruitment = RecruitmentSystem(self, self.main_guild, self.state)
                self.online_announce = OnlineAnnounce(self, self.main_guild, self.state)
                self.cleanup_system = CleanupSystem(self, self.main_guild, self.state)
                
                # Initialize check dates to prevent immediate flagging
                if hasattr(self.cleanup_system, 'initialize_check_dates'):
                    await self.cleanup_system.initialize_check_dates()
                
                # Make cleanup system accessible to views
                InactiveMemberVoteView.cleanup_system = self.cleanup_system
                
                # Start tasks
                if hasattr(self.cleanup_system, 'start_cleanup_task'):
                    self.cleanup_system.start_cleanup_task()
                    logger.info("✅ Cleanup task started")
                
                if hasattr(self.online_announce, 'start_tracking'):
                    self.online_announce.start_tracking()
                    logger.info("✅ Online announcement tracking started")
                
                await self.verify_resources()
                logger.info("✅ All systems initialized")
                
            except Exception as e:
                logger.error(f"❌ Error initializing systems: {e}")
                traceback.print_exc()
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Impèrius Recruits"
            ),
            status=discord.Status.online
        )
        
        logger.info("✅ Bot is fully operational!")

    @tasks.loop(hours=1)
    async def cleanup_state_task(self):
        """Clean up stale state data hourly"""
        if hasattr(self.state, 'cleanup_stale_data'):
            self.state.cleanup_stale_data()
    
    @cleanup_state_task.before_loop
    async def before_cleanup_state(self):
        await self.wait_until_ready()

    async def verify_resources(self):
        """Verify that all channels and roles exist"""
        if not self.main_guild:
            return
            
        logger.info("🔍 Verifying channels and roles...")
        
        channels_to_check = [
            ("RECRUIT_CONFIRM_CHANNEL", 1437568595977834590),
            ("ADMIN_CHANNEL", 1455138098437689387),
            ("REVIEW_CHANNEL", 1454802873300025396),
            ("TRYOUT_RESULT_CHANNEL", 1455205385463009310),
            ("ATTENDANCE_CHANNEL", 1437768842871832597),
            ("INACTIVE_ACCESS_CHANNEL", 1369091668724154419)
        ]
        
        for name, channel_id in channels_to_check:
            channel = self.main_guild.get_channel(channel_id)
            if channel:
                logger.info(f"✅ Found {name}: {channel.name}")
            else:
                logger.warning(f"⚠️ Channel not found: {name} (ID: {channel_id})")
        
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
                logger.info(f"✅ Found {name}: {role.name} (Members: {len(role.members)})")
            else:
                logger.warning(f"⚠️ Role not found: {name} (ID: {role_id})")

    async def on_member_join(self, member):
        """Handle new member joining"""
        if not self.main_guild or member.guild.id != self.main_guild.id:
            return
            
        try:
            logger.info(f"👤 New member joined: {member.name} (ID: {member.id})")
            
            # Prevent rapid rejoins
            user_id = member.id
            current_time = datetime.now()
            
            recent_join = self.state.get_recent_join(user_id) if hasattr(self.state, 'get_recent_join') else None
            if recent_join:
                time_diff = (current_time - recent_join).total_seconds()
                if time_diff < 60:  # 1 minute cooldown
                    logger.info(f"⏸️ Skipping rapid rejoin for {member.name}")
                    return
            
            # Store join time
            if hasattr(self.state, 'add_recent_join'):
                self.state.add_recent_join(user_id, current_time)
            
            # Interview everyone including returnees
            if self.recruitment and hasattr(self.recruitment, 'handle_new_member'):
                await self.recruitment.handle_new_member(member)
                
        except Exception as e:
            logger.error(f"❌ Error in on_member_join: {e}")
            traceback.print_exc()
    
    async def on_member_remove(self, member):
        """Handle member leaving/kicked"""
        try:
            logger.info(f"👋 Member left: {member.name} (ID: {member.id})")
            
            # Clean up any active interviews for this user
            if self.recruitment and hasattr(self.recruitment, 'cleanup_member_data'):
                self.recruitment.cleanup_member_data(member.id)
                
            # Remove from cleanup system tracking if exists
            if self.cleanup_system and hasattr(self.cleanup_system, 'member_last_check'):
                if member.id in self.cleanup_system.member_last_check:
                    del self.cleanup_system.member_last_check[member.id]
                    logger.info(f"Removed {member.name} from cleanup tracking")
                
        except Exception as e:
            logger.error(f"❌ Error in on_member_remove: {e}")
    
    async def on_presence_update(self, before, after):
        """Handle presence status changes (online/offline/idle/dnd)"""
        try:
            # Skip if not in our main guild
            if not after.guild or after.guild.id != self.main_guild.id:
                return
            
            # Skip bots
            if after.bot:
                return
            
            # Log the presence change for debugging
            if before.status != after.status:
                logger.info(f"🔄 Presence update: {after.name} - {before.status} → {after.status}")
            
            # Pass to online announcement system if it exists
            if self.online_announce:
                if hasattr(self.online_announce, 'on_presence_update'):
                    await self.online_announce.on_presence_update(before, after)
                    
        except Exception as e:
            logger.error(f"❌ Error in on_presence_update: {e}")
            traceback.print_exc()
    
    async def on_message(self, message):
        """Handle all messages (for DMs and interviews)"""
        if message.author == self.user:
            return
            
        if isinstance(message.channel, discord.DMChannel):
            try:
                logger.info(f"💬 DM from {message.author.name}: {message.content[:50]}...")
                if self.recruitment and hasattr(self.recruitment, 'handle_dm_response'):
                    await self.recruitment.handle_dm_response(message)
            except Exception as e:
                logger.error(f"❌ Error handling DM: {e}")
                traceback.print_exc()
        
        await self.process_commands(message)

    async def on_error(self, event, *args, **kwargs):
        """Handle errors in events"""
        logger.error(f"❌ Error in event {event}:")
        traceback.print_exc()

def main():
    """Main function to run the bot"""
    logger.info("🚀 Starting Imperial Bot...")
    
    if keep_alive_available:
        logger.info("🌐 Starting keep_alive server...")
        import threading
        keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("✅ keep_alive server started in background")
    
    bot = ImperialBot()
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        logger.error("❌ DISCORD_TOKEN not found!")
        try:
            with open('token.txt', 'r') as f:
                token = f.read().strip()
                logger.info("✅ Found token in token.txt")
        except:
            logger.error("❌ Also no token.txt file found")
            return
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"🔗 Connecting to Discord... (Attempt {retry_count + 1}/{max_retries})")
            bot.run(token, reconnect=True)
        except discord.LoginFailure:
            logger.error("❌ Invalid token.")
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
                logger.error(f"❌ Max retries ({max_retries}) reached.")
                break

if __name__ == "__main__":
    main()
