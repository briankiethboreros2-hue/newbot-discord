import os
import discord
from discord.ext import commands, tasks
import asyncio
import logging
from datetime import datetime, timedelta
import traceback
import sys
import time

# Import configuration and modules
from config import CHANNELS, ROLES, VOTING_ROLES, INTERVIEW_TIMEOUT
from recruitment import RecruitmentSystem
from online_announce import OnlineAnnounceSystem
from cleanup import CleanupSystem
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
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
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
        
        # Initialize state manager
        self.state = StateManager()
        
        # Initialize systems
        self.recruitment = None
        self.online_announce = None
        self.cleanup = None
        
        # Store guild for quick access
        self.main_guild = None
        
        # Join queue to handle rapid joins
        self.join_queue = asyncio.Queue()
        self.processing_joins = False

    async def setup_hook(self):
        """Setup hook - runs before on_ready"""
        logger.info("🔧 Running setup_hook...")
        
        # Start state auto-save
        self.state.start_auto_save()
        
        # Start join processor
        self.process_joins_task = asyncio.create_task(self.process_join_queue())
        
        # Add admin commands
        await self.add_admin_commands()

    async def add_admin_commands(self):
        """Add admin slash commands"""
        
        @self.tree.command(name="force_interview", description="Force start interview for a user")
        async def force_interview(interaction: discord.Interaction, member: discord.Member):
            """Admin command to force interview"""
            # Check if user has voting role
            if not any(role.id in VOTING_ROLES for role in interaction.user.roles):
                await interaction.response.send_message(
                    "❌ You need to be Cᥣᥲᥒ Mᥲstᥱr🌟, Queen❤️‍🔥, cute ✨, or OG-Impèrius🐦‍🔥 to use this command!",
                    ephemeral=True
                )
                return
            
            if self.recruitment:
                await interaction.response.send_message(f"📨 Starting interview for {member.mention}...", ephemeral=True)
                await self.recruitment.handle_new_member(member)
            else:
                await interaction.response.send_message("❌ Recruitment system not ready!", ephemeral=True)
        
        @self.tree.command(name="bot_status", description="Check bot status")
        async def bot_status(interaction: discord.Interaction):
            """Check bot status"""
            embed = discord.Embed(
                title="🤖 Bot Status",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="Uptime", value=self.get_uptime(), inline=False)
            embed.add_field(name="Active Interviews", value=str(len(self.state.active_interviews)), inline=True)
            embed.add_field(name="Guild Members", value=str(len(self.main_guild.members) if self.main_guild else "N/A"), inline=True)
            embed.add_field(name="Systems", value="✅ All systems operational" if all([
                self.recruitment, self.online_announce, self.cleanup
            ]) else "⚠️ Some systems offline", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.tree.command(name="cleanup_now", description="Run cleanup immediately")
        async def cleanup_now(interaction: discord.Interaction):
            """Run cleanup immediately"""
            if not any(role.id in VOTING_ROLES for role in interaction.user.roles):
                await interaction.response.send_message(
                    "❌ You need to be Cᥣᥲᥒ Mᥲstᥱr🌟, Queen❤️‍🔥, cute ✨, or OG-Impèrius🐦‍🔥 to use this command!",
                    ephemeral=True
                )
                return
            
            if self.cleanup:
                await interaction.response.send_message("🧹 Running cleanup tasks...", ephemeral=True)
                await self.cleanup.cleanup_task()
                await interaction.followup.send("✅ Cleanup completed!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Cleanup system not ready!", ephemeral=True)

    def get_uptime(self):
        """Calculate bot uptime"""
        if hasattr(self, 'start_time'):
            uptime = datetime.now() - self.start_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m {seconds}s"
        return "Unknown"

    async def on_ready(self):
        """Bot is ready - set up systems"""
        self.start_time = datetime.now()
        
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
            
            # Start state cleanup task
            self.cleanup_state_task.start()
            
            # Verify channels and roles exist
            await self.verify_resources()
            
            # Sync commands
            try:
                synced = await self.tree.sync()
                logger.info(f"✅ Synced {len(synced)} command(s)")
            except Exception as e:
                logger.error(f"❌ Error syncing commands: {e}")
            
            logger.info("✅ All systems initialized")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Impèrius Recruits"
            )
        )
        
        logger.info("✅ Bot is fully operational!")

    @tasks.loop(hours=1)
    async def cleanup_state_task(self):
        """Clean up stale state data hourly"""
        self.state.cleanup_stale_data()
    
    @cleanup_state_task.before_loop
    async def before_cleanup_state(self):
        await self.wait_until_ready()

    async def process_join_queue(self):
        """Process member joins from queue to avoid rate limits"""
        self.processing_joins = True
        logger.info("🚦 Join queue processor started")
        
        while True:
            try:
                member = await self.join_queue.get()
                
                # Process the join with delay
                await self.process_member_join(member)
                
                # Rate limit: 1 join every 2 seconds
                await asyncio.sleep(2)
                
                self.join_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in join queue processor: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def process_member_join(self, member):
        """Process a single member join"""
        try:
            logger.info(f"👤 Processing join for: {member.name} (ID: {member.id})")
            
            # Check for rapid rejoin
            user_id = member.id
            current_time = datetime.now()
            
            recent_join = self.state.get_recent_join(user_id)
            if recent_join:
                time_diff = (current_time - recent_join).total_seconds()
                if time_diff < 60:  # 1 minute cooldown
                    logger.info(f"⏸️ Skipping rapid rejoin for {member.name}")
                    return
            
            # Store join time
            self.state.add_recent_join(user_id, current_time)
            
            # INTERVIEW EVERYONE
            if self.recruitment:
                await self.recruitment.handle_new_member(member)
                
        except Exception as e:
            logger.error(f"❌ Error processing member join: {e}")
            traceback.print_exc()
    
    async def on_member_join(self, member):
        """Handle new member joining - Add to queue"""
        # Add to queue instead of processing immediately
        await self.join_queue.put(member)
        logger.info(f"📥 Added {member.name} to join queue (Queue size: {self.join_queue.qsize()})")
    
    async def on_member_remove(self, member):
        """Handle member leaving/kicked"""
        try:
            logger.info(f"👋 Member left: {member.name} (ID: {member.id})")
            
            # Clean up any active interviews for this user
            self.state.remove_active_interview(member.id)
            
            # Remove from recent joins
            self.state.remove_recent_join(member.id)
            
            # Notify admin channel
            channel = self.get_channel(CHANNELS["ADMIN"])
            if channel:
                embed = discord.Embed(
                    title="👋 Member Left",
                    description=f"**{member.name}** has left the server.",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=embed)
                
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
        
        # Send error to error channel if configured
        if CHANNELS["ERRORS"]:
            try:
                channel = self.get_channel(CHANNELS["ERRORS"])
                if channel:
                    embed = discord.Embed(
                        title="⚠️ Bot Error",
                        description=f"**Event:** {event}\n**Error:** {traceback.format_exc()[:1000]}",
                        color=discord.Color.red(),
                        timestamp=datetime.now()
                    )
                    await channel.send(embed=embed)
            except:
                pass

    async def verify_resources(self):
        """Verify that all channels and roles exist"""
        logger.info("🔍 Verifying channels and roles...")
        
        missing_channels = []
        missing_roles = []
        
        # Check channels
        for name, channel_id in CHANNELS.items():
            if channel_id:  # Skip optional channels
                channel = self.get_channel(channel_id)
                if channel:
                    logger.info(f"✅ Found {name}: {channel.name}")
                else:
                    logger.warning(f"⚠️ Channel not found: {name} (ID: {channel_id})")
                    missing_channels.append(name)
        
        # Check roles
        for name, role_id in ROLES.items():
            role = self.main_guild.get_role(role_id)
            if role:
                logger.info(f"✅ Found {name}: {role.name}")
            else:
                logger.warning(f"⚠️ Role not found: {name} (ID: {role_id})")
                missing_roles.append(name)
        
        # Log summary
        if missing_channels:
            logger.warning(f"Missing channels: {', '.join(missing_channels)}")
        if missing_roles:
            logger.warning(f"Missing roles: {', '.join(missing_roles)}")

    async def close(self):
        """Clean shutdown"""
        logger.info("🛑 Shutting down bot...")
        
        # Stop state auto-save
        self.state.stop_auto_save()
        
        # Save final state
        self.state.save_state()
        
        # Cancel join processor
        if hasattr(self, 'process_joins_task'):
            self.process_joins_task.cancel()
        
        await super().close()

def main():
    """Main function to run the bot"""
    logger.info("🚀 Starting Imperial Bot...")
    
    # Start keep_alive if available
    if keep_alive_available:
        logger.info("🌐 Starting keep_alive server...")
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
