# main.py - CLEAN MODULAR VERSION
import discord
from discord.ext import commands
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import configuration
from config import Config

# Import utilities
from utils.logger import BotLogger, logger
from utils.error_handler import ErrorHandler

# Import modules
from modules.database_handler import DatabaseHandler
from modules.activity_tracker import ActivityTracker
from modules.poll_manager import PollManager
from modules.cleanup_manager import CleanupManager
from modules.role_manager import RoleManager
from modules.notification import Notification

class ModularBot(commands.Bot):
    def __init__(self):
        # Setup intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        # Initialize components
        self.logger = BotLogger().get_logger()
        self.error_handler = ErrorHandler(self)
        
        # Initialize database
        self.db = DatabaseHandler()
        
        # Initialize modules (will be fully initialized in setup_hook)
        self.activity_tracker = None
        self.poll_mgr = None
        self.role_mgr = None
        self.notifier = None
        self.cleanup_mgr = None
        
    async def setup_hook(self):
        """Initialize all modules when bot starts"""
        self.logger.info("Starting bot initialization...")
        
        try:
            # Initialize database first
            await self.db.initialize()
            self.logger.info("✅ Database initialized")
            
            # Initialize modules in proper order
            self.activity_tracker = ActivityTracker(self, self.db)
            self.poll_mgr = PollManager(self, self.db)
            self.role_mgr = RoleManager(self, self.db)
            self.notifier = Notification(self, self.db)
            self.cleanup_mgr = CleanupManager(self, self.db, self.poll_mgr, self.role_mgr)
            
            # Initialize modules
            await self.activity_tracker.initialize()
            await self.poll_mgr.initialize()
            await self.role_mgr.initialize()
            await self.cleanup_mgr.initialize()
            
            self.logger.info("✅ All modules initialized")
            
            # Sync commands if needed
            await self.tree.sync()
            
            self.logger.info("✅ Bot setup complete")
            
        except Exception as e:
            self.logger.error(f"❌ Setup failed: {e}")
            raise
    
    async def on_ready(self):
        """Bot is ready"""
        self.logger.info(f'✅ {self.user} is connected to Discord!')
        self.logger.info(f'✅ Guilds: {[g.name for g in self.guilds]}')
        
        # Send startup notification
        await self._send_startup_notification()
    
    async def _send_startup_notification(self):
        """Send startup notification to admin channel"""
        try:
            admin_channel = self.get_channel(Config.ADMIN_CHANNEL_ID)
            if admin_channel:
                embed = discord.Embed(
                    title="🤖 Bot Startup Complete",
                    description=f"{self.user.name} is now online and running.",
                    color=0x00ff00,
                    timestamp=discord.utils.utcnow()
                )
                
                embed.add_field(
                    name="Version", 
                    value="2.0.0 (Poll-Based Modular System)",
                    inline=True
                )
                
                embed.add_field(
                    name="Modules Loaded",
                    value="✅ Database\n✅ Activity Tracker\n✅ Poll Manager\n✅ Cleanup Manager\n✅ Role Manager\n✅ Notification",
                    inline=True
                )
                
                await admin_channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Failed to send startup notification: {e}")
    
    async def on_message(self, message):
        """Handle incoming messages"""
        if message.author.bot:
            return
        
        # Let activity tracker process the message
        if self.activity_tracker:
            await self.activity_tracker.track_message_activity(message.author)
        
        # Process commands
        await self.process_commands(message)
    
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates"""
        if member.bot:
            return
        
        # Let activity tracker process voice activity
        if self.activity_tracker:
            await self.activity_tracker.track_voice_activity(member, before, after)
    
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        error_message = await self.error_handler.handle_error(error, f"Command: {ctx.command}")
        if error_message:
            await ctx.send(error_message)
    
    async def close(self):
        """Clean shutdown"""
        self.logger.info("Shutting down bot...")
        
        # Gracefully shutdown modules
        if hasattr(self.activity_tracker, 'shutdown'):
            await self.activity_tracker.shutdown()
        
        # Close database
        if self.db:
            await self.db.close()
        
        self.logger.info("✅ Shutdown complete")
        await super().close()

# Create bot instance
bot = ModularBot()

# ==================== COMMANDS ====================

@bot.command(name='ping')
async def ping_command(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! {latency}ms')

@bot.command(name='cleanup_status')
@commands.has_permissions(administrator=True)
async def cleanup_status_command(ctx):
    """Check cleanup system status"""
    if not bot.cleanup_mgr:
        await ctx.send("❌ Cleanup manager not initialized")
        return
    
    embed = await bot.cleanup_mgr.get_status()
    await ctx.send(embed=embed)

@bot.command(name='force_check')
@commands.has_permissions(administrator=True)
async def force_check_command(ctx):
    """Force an inactivity check"""
    await ctx.send("🔄 Running manual cleanup check...")
    
    if bot.cleanup_mgr:
        await bot.cleanup_mgr.check_inactive_users()
        await ctx.send("✅ Cleanup check complete!")
    else:
        await ctx.send("❌ Cleanup manager not initialized")

@bot.command(name='user_info')
@commands.has_permissions(administrator=True)
async def user_info_command(ctx, member: discord.Member = None):
    """Get information about a user"""
    if not member:
        member = ctx.author
    
    if bot.role_mgr:
        embed = await bot.role_mgr.get_user_roles_info(member)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Role manager not initialized")

@bot.command(name='vote')
@commands.has_permissions(administrator=True)
async def vote_command(ctx, question, *options):
    """Create a poll vote"""
    if not bot.poll_mgr:
        await ctx.send("❌ Poll manager not initialized")
        return
    
    poll = await bot.poll_mgr.create_poll(ctx, question, list(options))
    if poll:
        await ctx.send(f"✅ Poll created: {poll.jump_url}")

@bot.command(name='urgent_vote')
@commands.has_permissions(administrator=True)
async def urgent_vote_command(ctx, question, *options):
    """Create an urgent poll"""
    if not bot.poll_mgr:
        await ctx.send("❌ Poll manager not initialized")
        return
    
    poll = await bot.poll_mgr.create_urgent_poll(ctx, question, list(options))
    if poll:
        await ctx.send(f"🚨 Urgent poll created: {poll.jump_url}")

@bot.command(name='dashboard')
@commands.has_permissions(administrator=True)
async def dashboard_command(ctx):
    """Show bot dashboard"""
    if not bot.notifier:
        await ctx.send("❌ Notification module not initialized")
        return
    
    embed = await bot.notifier.create_status_dashboard()
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(
        title="🤖 Bot Help & Commands",
        description="Available commands for administrators:",
        color=0x7289da
    )
    
    embed.add_field(
        name="📊 Status Commands",
        value="`!ping` - Check bot latency\n"
              "`!dashboard` - Show system dashboard\n"
              "`!cleanup_status` - Check cleanup system\n"
              "`!user_info [@user]` - Get user information",
        inline=False
    )
    
    embed.add_field(
        name="🗳️ Voting Commands",
        value="`!vote <question> <option1> <option2> ...` - Create poll\n"
              "`!urgent_vote <question> <options>` - Create urgent poll",
        inline=False
    )
    
    embed.add_field(
        name="🛠️ Management Commands",
        value="`!force_check` - Run manual cleanup check",
        inline=False
    )
    
    embed.set_footer(text="All commands require administrator permissions")
    
    await ctx.send(embed=embed)

# ==================== BOT STARTUP ====================

if __name__ == "__main__":
    # Check for token
    if not Config.BOT_TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN not found!")
        print("Local: Create .env file with DISCORD_BOT_TOKEN=your_token")
        print("Render: Add DISCORD_BOT_TOKEN as environment variable")
        sys.exit(1)
    
    # Run bot with error handling
    try:
        bot.run(Config.BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
