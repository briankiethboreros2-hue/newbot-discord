import os
import discord
from discord.ext import commands
import logging
from datetime import datetime
import traceback
import sys
import time
import aiohttp
import asyncio
from quart import Quart, request

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
        # Create custom connector to bypass Cloudflare
        connector = aiohttp.TCPConnector(
            limit=None,
            ttl_dns_cache=300,
            family=4,  # Use IPv4 only (more reliable)
            ssl=False
        )
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            connector=connector,
            # Use older HTTP version
            http_version=9
        )
        
        self.state = StateManager()
        self.recruitment = None
        self.online_announce = None
        self.cleanup_system = None
        self.main_guild = None
        self.bot_start_time = datetime.now()
        self.retry_count = 0
        self.max_retries = 10
        
        # Register all commands
        self.setup_commands()

    def setup_commands(self):
        """Setup all commands"""
        # Create command objects from the decorated methods
        self.add_command(commands.Command(name='test', callback=self.test_command))
        self.add_command(commands.Command(name='status', callback=self.status_command))
        self.add_command(commands.Command(name='cleanup', callback=self.manual_cleanup))
        self.add_command(commands.Command(name='resetcheck', callback=self.reset_member_check))
        self.add_command(commands.Command(name='interview', callback=self.force_interview))
        self.add_command(commands.Command(name='checkmember', callback=self.check_member_status))
        self.add_command(commands.Command(name='help', callback=self.help_command))
        
        # Add permission checks
        self.manual_cleanup.requires = commands.has_permissions(administrator=True)
        self.reset_member_check.requires = commands.has_permissions(administrator=True)
        self.force_interview.requires = commands.has_permissions(administrator=True)
        self.check_member_status.requires = commands.has_permissions(administrator=True)

    async def setup_hook(self):
        """Setup hook - runs before on_ready"""
        logger.info("🔧 Running setup_hook...")
        
        # Enable gateway intents for better reconnection
        self._connection.gateway.encoding = 'json'
        self._connection.gateway.zlib = False
        
        if hasattr(self.state, 'start_auto_save'):
            self.state.start_auto_save()

    async def on_connect(self):
        """Called when bot connects to Discord"""
        logger.info(f"🔗 Connected to Discord Gateway")
        self.retry_count = 0  # Reset retry count on successful connection

    async def on_disconnect(self):
        """Called when bot disconnects"""
        logger.warning(f"🔌 Bot disconnected. Attempting to reconnect...")
        self.retry_count += 1
        
        if self.retry_count <= self.max_retries:
            wait_time = min(30 * self.retry_count, 300)  # Exponential backoff up to 5 min
            logger.info(f"⏳ Reconnecting in {wait_time} seconds... (Attempt {self.retry_count}/{self.max_retries})")
            await asyncio.sleep(wait_time)
        else:
            logger.error(f"❌ Max reconnection attempts reached. Please restart manually.")

    async def on_resumed(self):
        """Called when bot resumes connection"""
        logger.info(f"✅ Connection resumed")

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

    # ======== COMMAND METHODS ========
    
    async def test_command(self, ctx):
        """Test if commands work"""
        await ctx.send("✅ Test command works! Commands are functional.")
        logger.info(f"Test command executed by {ctx.author.name}")
    
    async def status_command(self, ctx):
        """Check bot status"""
        uptime = datetime.now() - self.bot_start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds // 60) % 60
        
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="🏃 Uptime", value=f"{days}d {hours}h {minutes}m", inline=True)
        embed.add_field(name="🏰 Guild", value=self.main_guild.name if self.main_guild else "None", inline=True)
        embed.add_field(name="👤 Members", value=self.main_guild.member_count if self.main_guild else "0", inline=True)
        
        # System status
        systems = []
        if self.recruitment: systems.append("✅ Recruitment")
        if self.online_announce: systems.append("✅ Online Announce")
        if self.cleanup_system: systems.append("✅ Cleanup")
        
        embed.add_field(name="🔧 Systems", value="\n".join(systems) if systems else "❌ None", inline=False)
        
        await ctx.send(embed=embed)
        logger.info(f"Status command executed by {ctx.author.name}")
    
    async def manual_cleanup(self, ctx):
        """Manually trigger cleanup system"""
        await ctx.send("🚀 Running manual cleanup...")
        
        if self.cleanup_system:
            try:
                # Run ghost user check
                await ctx.send("👻 Checking ghost users...")
                await self.cleanup_system.check_ghost_users()
                
                # Run inactive member check
                await ctx.send("😴 Checking inactive members...")
                await self.cleanup_system.check_inactive_members_15day_cycle()
                
                await ctx.send("✅ Cleanup completed!")
            except Exception as e:
                await ctx.send(f"❌ Error during cleanup: {e}")
                logger.error(f"Manual cleanup error: {e}")
        else:
            await ctx.send("❌ Cleanup system not initialized")
        
        logger.info(f"Cleanup command executed by {ctx.author.name}")
    
    async def reset_member_check(self, ctx, member: discord.Member = None):
        """Reset a member's inactivity check date"""
        if not member:
            await ctx.send("❌ Please mention a member: `!resetcheck @username`")
            return
        
        if not self.cleanup_system:
            await ctx.send("❌ Cleanup system not initialized")
            return
        
        if hasattr(self.cleanup_system, 'member_last_check'):
            self.cleanup_system.member_last_check[member.id] = datetime.now()
            await ctx.send(f"✅ Reset check date for {member.mention} to today")
            logger.info(f"Admin reset check for {member.name} by {ctx.author.name}")
        else:
            await ctx.send("❌ Check tracking not available")
    
    async def force_interview(self, ctx, member: discord.Member = None):
        """Force start an interview for a member"""
        if not member:
            await ctx.send("❌ Please mention a member: `!interview @username`")
            return
        
        if not self.recruitment:
            await ctx.send("❌ Recruitment system not initialized")
            return
        
        await ctx.send(f"📝 Starting interview for {member.mention}...")
        try:
            await self.recruitment.start_dm_interview(member)
            await ctx.send(f"✅ Interview started! Check DMs with {member.name}")
        except discord.Forbidden:
            await ctx.send(f"❌ Cannot DM {member.mention}. They may have DMs disabled.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
        
        logger.info(f"Interview command executed by {ctx.author.name} for {member.name}")
    
    async def check_member_status(self, ctx, member: discord.Member = None):
        """Check a member's status"""
        if not member:
            await ctx.send("❌ Please mention a member: `!checkmember @username`")
            return
        
        embed = discord.Embed(
            title=f"📊 Member Status: {member.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Avatar
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        
        # Basic info
        embed.add_field(name="📛 Name", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="🆔 ID", value=member.id, inline=True)
        embed.add_field(name="🤖 Bot", value="✅ Yes" if member.bot else "❌ No", inline=True)
        
        # Roles
        role_names = [role.name for role in member.roles if role.name != "@everyone"]
        embed.add_field(name="👑 Roles", value=", ".join(role_names) if role_names else "No roles", inline=False)
        
        # Check if in cleanup tracking
        if self.cleanup_system and hasattr(self.cleanup_system, 'member_last_check'):
            last_check = self.cleanup_system.member_last_check.get(member.id)
            if last_check:
                days_ago = (datetime.now() - last_check).days
                embed.add_field(name="📅 Last Check", value=f"{last_check.strftime('%Y-%m-%d')} ({days_ago} days ago)", inline=True)
            else:
                embed.add_field(name="📅 Last Check", value="Never checked", inline=True)
        
        # Dates
        if member.joined_at:
            join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
            days_in_server = (datetime.now() - join_date).days
            embed.add_field(name="📅 Joined", value=f"{join_date.strftime('%Y-%m-%d')} ({days_in_server} days ago)", inline=True)
        
        if member.created_at:
            create_date = member.created_at.replace(tzinfo=None) if member.created_at.tzinfo else member.created_at
            account_age = (datetime.now() - create_date).days
            embed.add_field(name="📅 Account Age", value=f"{account_age} days", inline=True)
        
        # Status
        embed.add_field(name="📱 Status", value=str(member.status).title(), inline=True)
        
        await ctx.send(embed=embed)
        logger.info(f"Checkmember command executed by {ctx.author.name} for {member.name}")
    
    async def help_command(self, ctx):
        """Show available commands"""
        embed = discord.Embed(
            title="🤖 Impèrius Bot Commands",
            description="Prefix: `!`",
            color=discord.Color.green()
        )
        
        # Admin commands
        admin_cmds = [
            ("`!cleanup`", "Run manual cleanup (ghost + inactive check)"),
            ("`!resetcheck @user`", "Reset member's inactivity check date"),
            ("`!interview @user`", "Force start interview for member"),
            ("`!checkmember @user`", "Check member's detailed status")
        ]
        
        # Public commands
        public_cmds = [
            ("`!status`", "Check bot status"),
            ("`!help`", "Show this help message"),
            ("`!test`", "Test if commands work")
        ]
        
        embed.add_field(
            name="👑 Admin Commands",
            value="\n".join([f"**{cmd}** - {desc}" for cmd, desc in admin_cmds]),
            inline=False
        )
        
        embed.add_field(
            name="👥 Public Commands",
            value="\n".join([f"**{cmd}** - {desc}" for cmd, desc in public_cmds]),
            inline=False
        )
        
        embed.set_footer(text="Bot automatically handles interviews, online tracking, and cleanup")
        
        await ctx.send(embed=embed)
        logger.info(f"Help command executed by {ctx.author.name}")

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
        """Handle new member joining - WITH CLEAN ON DEMAND"""
        if not self.main_guild or member.guild.id != self.main_guild.id:
            return
            
        try:
            logger.info(f"👤 New member joined: {member.name} (ID: {member.id})")
            
            # Clean old entries FIRST (before checking)
            if hasattr(self.state, 'cleanup_recent_joins_on_demand'):
                cleaned = self.state.cleanup_recent_joins_on_demand()
                if cleaned > 0:
                    logger.debug(f"🧹 Cleaned {cleaned} old recent joins before checking {member.name}")
            
            # Check for rapid rejoin
            user_id = member.id
            current_time = datetime.now()
            
            recent_join = self.state.get_recent_join(user_id) if hasattr(self.state, 'get_recent_join') else None
            if recent_join:
                time_diff = (current_time - recent_join).total_seconds()
                if time_diff < 60:  # 1 minute cooldown
                    logger.info(f"⏸️ Skipping rapid rejoin for {member.name} (joined {time_diff:.0f}s ago)")
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
        # Don't respond to ourselves
        if message.author == self.user:
            return
            
        # Handle DM messages for interviews
        if isinstance(message.channel, discord.DMChannel):
            try:
                logger.info(f"💬 DM from {message.author.name}: {message.content[:50]}...")
                if self.recruitment and hasattr(self.recruitment, 'handle_dm_response'):
                    await self.recruitment.handle_dm_response(message)
            except Exception as e:
                logger.error(f"❌ Error handling DM: {e}")
                traceback.print_exc()
        
        # Process commands for non-DM messages
        await self.process_commands(message)

    async def on_error(self, event, *args, **kwargs):
        """Handle errors in events"""
        logger.error(f"❌ Error in event {event}:")
        traceback.print_exc()

# Create Quart app for web server
app = Quart(__name__)

@app.route('/')
async def index():
    return {
        "status": "online",
        "bot": "Imperial Bot",
        "time": datetime.now().isoformat()
    }

@app.route('/health')
async def health():
    return {"status": "healthy"}, 200

def run_web_server():
    """Run Quart web server"""
    app.run(host='0.0.0.0', port=8080)

async def run_bot_with_retry():
    """Run bot with retry logic"""
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        # Try to get token from file
        try:
            with open('token.txt', 'r') as f:
                token = f.read().strip()
                logger.info("✅ Found token in token.txt")
        except:
            logger.error("❌ No token found in environment or token.txt")
            return
    
    bot_instance = ImperialBot()
    
    while True:
        try:
            logger.info("🔗 Attempting to connect to Discord...")
            await bot_instance.start(token)
            
        except discord.LoginFailure:
            logger.error("❌ Invalid token. Please check your token.")
            break
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            traceback.print_exc()
            
            # Exponential backoff
            wait_time = min(300, 30 * (bot_instance.retry_count + 1))  # Max 5 minutes
            logger.info(f"🔄 Restarting in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            
            bot_instance.retry_count += 1
            if bot_instance.retry_count > bot_instance.max_retries:
                logger.error("❌ Max retries reached. Please check your configuration.")
                break

def main():
    """Main function to run the bot"""
    logger.info("🚀 Starting Imperial Bot with Cloudflare bypass...")
    
    # Start web server in background thread
    import threading
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("🌐 Web server started on port 8080")
    
    # Run bot with asyncio
    try:
        asyncio.run(run_bot_with_retry())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
