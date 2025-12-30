import os
import discord
from discord.ext import commands
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

# Create bot instance
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Global variables
state = None
recruitment = None
online_announce = None
cleanup_system = None
main_guild = None
bot_start_time = datetime.now()

@bot.event
async def on_ready():
    """Bot is ready - set up systems"""
    global state, recruitment, online_announce, cleanup_system, main_guild
    
    logger.info(f'✅ Bot is online as {bot.user} (ID: {bot.user.id})')
    logger.info(f'📊 Connected to {len(bot.guilds)} guild(s)')
    
    # Log all guilds
    for guild in bot.guilds:
        logger.info(f'🏰 Guild: {guild.name} (ID: {guild.id}) - Members: {guild.member_count}')
    
    # Get the main guild
    if bot.guilds:
        main_guild = bot.guilds[0]
        logger.info(f'🏰 Main guild: {main_guild.name} (ID: {main_guild.id})')
        
        try:
            # Initialize systems
            state = StateManager()
            recruitment = RecruitmentSystem(bot, main_guild, state)
            online_announce = OnlineAnnounce(bot, main_guild, state)
            cleanup_system = CleanupSystem(bot, main_guild, state)
            
            # Initialize check dates to prevent immediate flagging
            if hasattr(cleanup_system, 'initialize_check_dates'):
                await cleanup_system.initialize_check_dates()
            
            # Make cleanup system accessible to views
            InactiveMemberVoteView.cleanup_system = cleanup_system
            
            # Start tasks
            if hasattr(cleanup_system, 'start_cleanup_task'):
                cleanup_system.start_cleanup_task()
                logger.info("✅ Cleanup task started")
            
            if hasattr(online_announce, 'start_tracking'):
                online_announce.start_tracking()
                logger.info("✅ Online announcement tracking started")
            
            await verify_resources()
            logger.info("✅ All systems initialized")
            
        except Exception as e:
            logger.error(f"❌ Error initializing systems: {e}")
            traceback.print_exc()
    
    # Set bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Impèrius Recruits"
        ),
        status=discord.Status.online
    )
    
    logger.info("✅ Bot is fully operational!")

# ======== PUBLIC COMMANDS ========

@bot.command(name='test')
async def test_command(ctx):
    """Test if commands work"""
    await ctx.send("✅ Test command works! Commands are functional.")
    logger.info(f"Test command executed by {ctx.author.name}")

@bot.command(name='status')
async def status_command(ctx):
    """Check bot status"""
    global main_guild, recruitment, online_announce, cleanup_system, bot_start_time
    
    uptime = datetime.now() - bot_start_time
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds // 60) % 60
    
    embed = discord.Embed(
        title="🤖 Bot Status",
        color=discord.Color.blue()
    )
    embed.add_field(name="🏃 Uptime", value=f"{days}d {hours}h {minutes}m", inline=True)
    embed.add_field(name="🏰 Guild", value=main_guild.name if main_guild else "None", inline=True)
    embed.add_field(name="👤 Members", value=main_guild.member_count if main_guild else "0", inline=True)
    
    # System status
    systems = []
    if recruitment: systems.append("✅ Recruitment")
    if online_announce: systems.append("✅ Online Announce")
    if cleanup_system: systems.append("✅ Cleanup")
    
    embed.add_field(name="🔧 Systems", value="\n".join(systems) if systems else "❌ None", inline=False)
    
    await ctx.send(embed=embed)
    logger.info(f"Status command executed by {ctx.author.name}")

@bot.command(name='help')
async def help_command(ctx):
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
        ("`!forceresetcheck @user`", "Force reset check + grace period"),
        ("`!interview @user`", "Force start interview for member"),
        ("`!checkmember @user`", "Check member's detailed status"),
        ("`!checkinactive @user`", "Check if specific member is inactive"),
        ("`!cleanupstats`", "Show cleanup system statistics"),
        ("`!listgrace`", "List members in grace period")
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

# ======== ADMIN COMMANDS ========

@bot.command(name='cleanup')
@commands.has_permissions(administrator=True)
async def manual_cleanup(ctx):
    """Manually trigger cleanup system"""
    global cleanup_system
    
    await ctx.send("🚀 Running manual cleanup...")
    
    if cleanup_system:
        try:
            # Run ghost user check
            await ctx.send("👻 Checking ghost users...")
            await cleanup_system.check_ghost_users()
            
            # Run inactive member check
            await ctx.send("😴 Checking inactive members...")
            await cleanup_system.check_inactive_members_15day_cycle()
            
            await ctx.send("✅ Cleanup completed!")
        except Exception as e:
            await ctx.send(f"❌ Error during cleanup: {e}")
            logger.error(f"Manual cleanup error: {e}")
    else:
        await ctx.send("❌ Cleanup system not initialized")
    
    logger.info(f"Cleanup command executed by {ctx.author.name}")

@bot.command(name='resetcheck')
@commands.has_permissions(administrator=True)
async def reset_member_check(ctx, member: discord.Member = None):
    """Reset a member's inactivity check date"""
    global cleanup_system
    
    if not member:
        await ctx.send("❌ Please mention a member: `!resetcheck @username`")
        return
    
    if not cleanup_system:
        await ctx.send("❌ Cleanup system not initialized")
        return
    
    if hasattr(cleanup_system, 'member_last_check'):
        cleanup_system.member_last_check[member.id] = datetime.now()
        await ctx.send(f"✅ Reset check date for {member.mention} to today")
        logger.info(f"Admin reset check for {member.name} by {ctx.author.name}")
    else:
        await ctx.send("❌ Check tracking not available")

@bot.command(name='forceresetcheck')
@commands.has_permissions(administrator=True)
async def force_reset_member_check(ctx, member: discord.Member = None):
    """Force reset a member's check date and add grace period"""
    global cleanup_system
    
    if not member:
        await ctx.send("❌ Please mention a member: `!forceresetcheck @username`")
        return
    
    if not cleanup_system:
        await ctx.send("❌ Cleanup system not initialized")
        return
    
    # Record pardon (resets check date and adds grace period)
    if hasattr(cleanup_system, 'record_admin_pardon'):
        success = await cleanup_system.record_admin_pardon(member.id)
        
        if success:
            grace_until = cleanup_system.member_grace_period.get(member.id, datetime.now() + timedelta(days=7))
            await ctx.send(
                f"✅ Force reset check for {member.mention}\n"
                f"📅 Last check reset to today\n"
                f"🛡️ Grace period added until {grace_until.strftime('%Y-%m-%d')}"
            )
        else:
            await ctx.send(f"❌ Failed to reset check for {member.mention}")
    else:
        await ctx.send("❌ Cleanup system doesn't support force reset")

@bot.command(name='interview')
@commands.has_permissions(administrator=True)
async def force_interview(ctx, member: discord.Member = None):
    """Force start an interview for a member"""
    global recruitment
    
    if not member:
        await ctx.send("❌ Please mention a member: `!interview @username`")
        return
    
    if not recruitment:
        await ctx.send("❌ Recruitment system not initialized")
        return
    
    await ctx.send(f"📝 Starting interview for {member.mention}...")
    try:
        await recruitment.start_dm_interview(member)
        await ctx.send(f"✅ Interview started! Check DMs with {member.name}")
    except discord.Forbidden:
        await ctx.send(f"❌ Cannot DM {member.mention}. They may have DMs disabled.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
    
    logger.info(f"Interview command executed by {ctx.author.name} for {member.name}")

@bot.command(name='checkmember')
@commands.has_permissions(administrator=True)
async def check_member_status(ctx, member: discord.Member = None):
    """Check a member's status"""
    global cleanup_system
    
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
    if cleanup_system and hasattr(cleanup_system, 'member_last_check'):
        last_check = cleanup_system.member_last_check.get(member.id)
        if last_check:
            days_ago = (datetime.now() - last_check).days
            embed.add_field(name="📅 Last Check", value=f"{last_check.strftime('%Y-%m-%d')} ({days_ago} days ago)", inline=True)
        else:
            embed.add_field(name="📅 Last Check", value="Never checked", inline=True)
    
    # Check grace period
    if cleanup_system and hasattr(cleanup_system, 'member_grace_period'):
        if member.id in cleanup_system.member_grace_period:
            grace_until = cleanup_system.member_grace_period[member.id]
            days_left = (grace_until - datetime.now()).days + 1
            embed.add_field(name="🛡️ Grace Period", value=f"Until: {grace_until.strftime('%Y-%m-%d')} ({days_left} days left)", inline=True)
    
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

@bot.command(name='checkinactive')
@commands.has_permissions(administrator=True)
async def check_specific_member(ctx, member: discord.Member = None):
    """Manually check if a specific member is inactive"""
    global cleanup_system, main_guild
    
    if not member:
        await ctx.send("❌ Please mention a member: `!checkinactive @username`")
        return
    
    if not cleanup_system:
        await ctx.send("❌ Cleanup system not initialized")
        return
    
    imperius_role = main_guild.get_role(1437570031822176408)
    if not imperius_role or imperius_role not in member.roles:
        await ctx.send(f"❌ {member.mention} is not in Impèrius🔥 role")
        return
    
    # Check grace period
    if hasattr(cleanup_system, 'member_grace_period') and member.id in cleanup_system.member_grace_period:
        grace_until = cleanup_system.member_grace_period[member.id]
        if datetime.now() < grace_until:
            days_left = (grace_until - datetime.now()).days + 1
            await ctx.send(f"🛡️ {member.mention} is in grace period for {days_left} more days (until {grace_until.strftime('%Y-%m-%d')})")
            return
    
    # Check attendance
    attendance_channel = main_guild.get_channel(1437768842871832597)
    if not attendance_channel:
        await ctx.send("❌ Attendance channel not found")
        return
    
    # Check last 15 days
    check_since = datetime.now() - timedelta(days=15)
    
    if hasattr(cleanup_system, 'was_member_active_since'):
        was_active = await cleanup_system.was_member_active_since(member, attendance_channel, check_since)
        
        if was_active:
            await ctx.send(f"✅ {member.mention} has been active in the last 15 days")
        else:
            # Check last check date
            last_check = cleanup_system.member_last_check.get(member.id) if hasattr(cleanup_system, 'member_last_check') else None
            if last_check:
                days_ago = (datetime.now() - last_check).days
                await ctx.send(f"⚠️ {member.mention} appears INACTIVE for 15+ days\n📅 Last checked: {last_check.strftime('%Y-%m-%d')} ({days_ago} days ago)")
            else:
                await ctx.send(f"⚠️ {member.mention} appears INACTIVE for 15+ days\n📅 Never checked before")
    else:
        await ctx.send("❌ Cleanup system doesn't support activity checking")

@bot.command(name='cleanupstats')
@commands.has_permissions(administrator=True)
async def cleanup_stats(ctx):
    """Show cleanup system statistics"""
    global cleanup_system
    
    if not cleanup_system:
        await ctx.send("❌ Cleanup system not initialized")
        return
    
    # Try to get statistics from cleanup system
    if hasattr(cleanup_system, 'get_statistics'):
        stats = await cleanup_system.get_statistics()
    else:
        # Fallback basic stats
        stats = {
            "members_tracked": len(cleanup_system.member_last_check) if hasattr(cleanup_system, 'member_last_check') else 0,
            "last_ghost_check": cleanup_system.last_ghost_check if hasattr(cleanup_system, 'last_ghost_check') else datetime.now(),
            "last_inactive_check": cleanup_system.last_inactive_check if hasattr(cleanup_system, 'last_inactive_check') else datetime.now(),
        }
        
        # Count grace period members
        if hasattr(cleanup_system, 'member_grace_period'):
            stats["in_grace_period"] = len(cleanup_system.member_grace_period)
    
    embed = discord.Embed(
        title="📊 Cleanup System Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    # Basic stats
    embed.add_field(
        name="👥 Members Tracked",
        value=f"{stats.get('members_tracked', 0)} Impèrius members",
        inline=True
    )
    
    embed.add_field(
        name="🛡️ In Grace Period",
        value=f"{stats.get('in_grace_period', 0)} members",
        inline=True
    )
    
    embed.add_field(
        name="👻 Last Ghost Check",
        value=stats.get('last_ghost_check', datetime.now()).strftime("%Y-%m-%d %H:%M"),
        inline=True
    )
    
    embed.add_field(
        name="😴 Last Inactive Check",
        value=stats.get('last_inactive_check', datetime.now()).strftime("%Y-%m-%d %H:%M"),
        inline=True
    )
    
    # Next check info
    if 'next_inactive_check' in stats:
        next_check = stats['next_inactive_check']
        days_until = stats.get('days_until_next', 0)
        
        embed.add_field(
            name="🔄 Next Inactive Check",
            value=f"{next_check.strftime('%Y-%m-%d')}\n({days_until} days from now)",
            inline=True
        )
    
    # Grace period info
    if stats.get('in_grace_period', 0) > 0:
        embed.add_field(
            name="🛡️ Grace Period Note",
            value="Members in grace period won't be checked for inactivity",
            inline=False
        )
    
    embed.set_footer(text="Grace period: 7 days after promotion/pardon")
    
    await ctx.send(embed=embed)
    logger.info(f"Cleanupstats command executed by {ctx.author.name}")

@bot.command(name='listgrace')
@commands.has_permissions(administrator=True)
async def list_grace_period_members(ctx):
    """List all members currently in grace period"""
    global cleanup_system, main_guild
    
    if not cleanup_system:
        await ctx.send("❌ Cleanup system not initialized")
        return
    
    if not hasattr(cleanup_system, 'member_grace_period'):
        await ctx.send("❌ Grace period system not available")
        return
    
    grace_members = cleanup_system.member_grace_period
    
    if not grace_members:
        await ctx.send("🛡️ No members currently in grace period")
        return
    
    now = datetime.now()
    embed = discord.Embed(
        title="🛡️ Members in Grace Period",
        description="These members won't be checked for inactivity",
        color=discord.Color.green(),
        timestamp=now
    )
    
    sorted_members = sorted(grace_members.items(), key=lambda x: x[1])  # Sort by grace end date
    
    for member_id, grace_until in sorted_members:
        member = main_guild.get_member(member_id)
        if member:
            days_left = max(0, (grace_until - now).days) + 1
            embed.add_field(
                name=member.display_name,
                value=f"Until: {grace_until.strftime('%Y-%m-%d')}\n({days_left} days left)",
                inline=True
            )
    
    embed.set_footer(text=f"Total: {len(grace_members)} members")
    
    await ctx.send(embed=embed)
    logger.info(f"Listgrace command executed by {ctx.author.name}")

# ======== EVENT HANDLERS ========

@bot.event
async def on_member_join(member):
    """Handle new member joining - WITH CLEAN ON DEMAND"""
    global main_guild, state, recruitment
    
    if not main_guild or member.guild.id != main_guild.id:
        return
        
    try:
        logger.info(f"👤 New member joined: {member.name} (ID: {member.id})")
        
        # Clean old entries FIRST (before checking)
        if hasattr(state, 'cleanup_recent_joins_on_demand'):
            cleaned = state.cleanup_recent_joins_on_demand()
            if cleaned > 0:
                logger.debug(f"🧹 Cleaned {cleaned} old recent joins before checking {member.name}")
        
        # Check for rapid rejoin
        user_id = member.id
        current_time = datetime.now()
        
        recent_join = state.get_recent_join(user_id) if hasattr(state, 'get_recent_join') else None
        if recent_join:
            time_diff = (current_time - recent_join).total_seconds()
            if time_diff < 60:  # 1 minute cooldown
                logger.info(f"⏸️ Skipping rapid rejoin for {member.name} (joined {time_diff:.0f}s ago)")
                return
        
        # Store join time
        if hasattr(state, 'add_recent_join'):
            state.add_recent_join(user_id, current_time)
        
        # Interview everyone including returnees
        if recruitment and hasattr(recruitment, 'handle_new_member'):
            await recruitment.handle_new_member(member)
            
    except Exception as e:
        logger.error(f"❌ Error in on_member_join: {e}")
        traceback.print_exc()

@bot.event
async def on_member_remove(member):
    """Handle member leaving/kicked"""
    global recruitment, cleanup_system
    
    try:
        logger.info(f"👋 Member left: {member.name} (ID: {member.id})")
        
        # Clean up any active interviews for this user
        if recruitment and hasattr(recruitment, 'cleanup_member_data'):
            recruitment.cleanup_member_data(member.id)
            
        # Remove from cleanup system tracking if exists
        if cleanup_system and hasattr(cleanup_system, 'member_last_check'):
            if member.id in cleanup_system.member_last_check:
                del cleanup_system.member_last_check[member.id]
                logger.info(f"Removed {member.name} from cleanup tracking")
        
        # Remove from grace period if exists
        if cleanup_system and hasattr(cleanup_system, 'member_grace_period'):
            if member.id in cleanup_system.member_grace_period:
                del cleanup_system.member_grace_period[member.id]
                logger.info(f"Removed {member.name} from grace period tracking")
            
    except Exception as e:
        logger.error(f"❌ Error in on_member_remove: {e}")

@bot.event
async def on_presence_update(before, after):
    """Handle presence status changes (online/offline/idle/dnd)"""
    global main_guild, online_announce
    
    try:
        # Skip if not in our main guild
        if not after.guild or after.guild.id != main_guild.id:
            return
        
        # Skip bots
        if after.bot:
            return
        
        # Log the presence change for debugging
        if before.status != after.status:
            logger.info(f"🔄 Presence update: {after.name} - {before.status} → {after.status}")
        
        # Pass to online announcement system if it exists
        if online_announce:
            if hasattr(online_announce, 'on_presence_update'):
                await online_announce.on_presence_update(before, after)
                
    except Exception as e:
        logger.error(f"❌ Error in on_presence_update: {e}")
        traceback.print_exc()

@bot.event
async def on_message(message):
    """Handle all messages (for DMs and interviews)"""
    global recruitment
    
    # Don't respond to ourselves
    if message.author == bot.user:
        return
        
    # Handle DM messages for interviews
    if isinstance(message.channel, discord.DMChannel):
        try:
            logger.info(f"💬 DM from {message.author.name}: {message.content[:50]}...")
            if recruitment and hasattr(recruitment, 'handle_dm_response'):
                await recruitment.handle_dm_response(message)
        except Exception as e:
            logger.error(f"❌ Error handling DM: {e}")
            traceback.print_exc()
    
    # Process commands for non-DM messages
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        # Ignore CommandNotFound errors silently
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}")
    else:
        logger.error(f"❌ Error in command {ctx.command}: {error}")
        traceback.print_exc()

# ======== HELPER FUNCTIONS ========

async def verify_resources():
    """Verify that all channels and roles exist"""
    global main_guild
    
    if not main_guild:
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
        channel = main_guild.get_channel(channel_id)
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
        role = main_guild.get_role(role_id)
        if role:
            logger.info(f"✅ Found {name}: {role.name} (Members: {len(role.members)})")
        else:
            logger.warning(f"⚠️ Role not found: {name} (ID: {role_id})")

# ======== MAIN FUNCTION ========

def run_bot():
    """Run the bot"""
    # Import your existing keep_alive
    try:
        from keep_alive import start_keep_alive
        logger.info("🌐 Starting keep_alive server...")
        import threading
        keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("✅ keep_alive server started in background")
    except ImportError as e:
        logger.warning(f"⚠️ keep_alive.py not found: {e}")
    
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
    logger.info("🚀 Starting Imperial Bot...")
    run_bot()
