import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging
# cleanup.py
import discord
import asyncio
# ... your other imports ...

# ======== ADD THIS CLASS DEFINITION ========
class InactiveMemberVoteView(discord.ui.View):
    def __init__(self, member_id, clan_name):
        super().__init__(timeout=86400)
        self.member_id = member_id
        self.clan_name = clan_name
        self.votes = {'kick': 0, 'keep': 0}
        self.voters = set()

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("Already voted!", ephemeral=True)
            return
        self.votes['kick'] += 1
        self.voters.add(interaction.user.id)
        await interaction.response.defer()

    @discord.ui.button(label="Keep", style=discord.ButtonStyle.success)
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("Already voted!", ephemeral=True)
            return
        self.votes['keep'] += 1
        self.voters.add(interaction.user.id)
        await interaction.response.defer()
# ======== END OF CLASS DEFINITION ========

# Your existing functions continue below...
async def check_inactive_members():
    # ... your existing code that uses InactiveMemberVoteView ...

logger = logging.getLogger(__name__)

def has_voting_role(member):
    """Check if member has any of the voting roles"""
    voting_roles = [
        1389835747040694332,  # Cᥣᥲᥒ Mᥲstᥱr🌟
        1437578521374363769,  # Queen❤️‍🔥
        1438420490455613540,  # cute ✨
        1437572916005834793,  # OG-Impèrius🐦‍🔥
    ]
    
    member_role_ids = [role.id for role in member.roles]
    return any(role_id in member_role_ids for role_id in voting_roles)

def make_timezone_naive(dt):
    """Convert offset-aware datetime to offset-naive"""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

class CleanupSystem:
    def __init__(self, bot, guild, state):
        self.bot = bot
        self.guild = guild
        self.state = state
        
    def start_cleanup_task(self):
        """Start the cleanup task"""
        self.cleanup_task.start()
    
    @tasks.loop(hours=24)  # Run every 24 hours
    async def cleanup_task(self):
        """Main cleanup task"""
        logger.info("Running cleanup task...")
        
        # Check for ghost users (no roles)
        await self.check_ghost_users()
        
        # Check for inactive members (every 7 days)
        if datetime.now().weekday() == 0:  # Run on Mondays (once a week)
            await self.check_inactive_members()
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Wait until bot is ready before starting cleanup"""
        await self.bot.wait_until_ready()
    
    async def check_ghost_users(self):
        """Check for users with no roles (ghosts)"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                logger.error("Admin channel not found!")
                return
            
            ghost_users = []
            now = datetime.now()
            
            for member in self.guild.members:
                # Skip bots
                if member.bot:
                    continue
                
                # Skip users who recently rejoined (within 24 hours)
                if member.joined_at:
                    # Make joined_at timezone naive
                    join_date = make_timezone_naive(member.joined_at)
                    hours_since_join = (now - join_date).total_seconds() / 3600
                    if hours_since_join < 24:
                        continue
                
                # Check if member has only @everyone role
                if len(member.roles) == 1:  # Only @everyone
                    # Calculate days in server
                    join_date = make_timezone_naive(member.joined_at)
                    if join_date:
                        days_in_server = (now - join_date).days
                        
                        # Only show if more than 1 day
                        if days_in_server >= 1:
                            ghost_users.append((member, days_in_server))
            
            if ghost_users:
                logger.info(f"Found {len(ghost_users)} ghost users")
                for member, days in ghost_users:
                    # Check if we've already reported this user recently
                    if self.state.is_user_checked(member.id):
                        continue
                    
                    embed = discord.Embed(
                        title="👻 Ghost User Detected",
                        description=f"**User:** {member.mention} ({member.name})\n"
                                  f"**Days in server:** {days} days\n"
                                  f"**Status:** No roles assigned",
                        color=discord.Color.dark_gray(),
                        timestamp=datetime.now()
                    )
                    
                    view = GhostUserVoteView(self.bot, member)
                    await channel.send(embed=embed, view=view)
                    
                    # Add to checked users
                    self.state.add_checked_user(member.id)
                    
                    # Wait a bit between messages to avoid rate limits
                    await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error checking ghost users: {e}")
    
    async def check_inactive_members(self):
        """Check for inactive Impèrius🔥 members"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                logger.error("Admin channel not found!")
                return
            
            imperius_role = self.guild.get_role(1437570031822176408)  # IMPERIUS_ROLE
            if not imperius_role:
                logger.error("Impèrius🔥 role not found!")
                return
            
            inactive_members = []
            now = datetime.now()
            
            for member in imperius_role.members:
                # Skip if member is bot
                if member.bot:
                    continue
                
                # Check last message in the guild
                last_message = await self.get_last_message(member)
                
                if last_message:
                    # Make message time naive
                    last_message_time = make_timezone_naive(last_message.created_at)
                    days_since_last_message = (now - last_message_time).days
                    
                    # If inactive for 7+ days
                    if days_since_last_message >= 7:
                        inactive_members.append((member, days_since_last_message))
                else:
                    # If no messages found, check join date
                    if member.joined_at:
                        join_date = make_timezone_naive(member.joined_at)
                        days_since_join = (now - join_date).days
                        if days_since_join >= 7:
                            inactive_members.append((member, days_since_join))
            
            if inactive_members:
                logger.info(f"Found {len(inactive_members)} inactive members")
                for member, days_inactive in inactive_members:
                    embed = discord.Embed(
                        title="😴 Inactive Member Detected",
                        description=f"**Member:** {member.mention} ({member.name})\n"
                                  f"**Role:** Impèrius🔥\n"
                                  f"**Days Inactive:** {days_inactive} days\n"
                                  f"**Candidate for demotion**",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    
                    view = InactiveMemberVoteView(self.bot, member)
                    await channel.send(embed=embed, view=view)
                    
                    await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error checking inactive members: {e}")
    
    async def get_last_message(self, member):
        """Get the last message sent by a member in the guild"""
        try:
            # Check recent messages in all text channels
            for channel in self.guild.text_channels:
                try:
                    # Check if bot has permission to read channel history
                    if not channel.permissions_for(self.guild.me).read_message_history:
                        continue
                    
                    # Get last 50 messages (fewer for performance)
                    async for message in channel.history(limit=50):
                        if message.author.id == member.id:
                            return message
                except discord.Forbidden:
                    continue
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting last message: {e}")
        
        return None

# The view classes remain the same as before...
# Keep all the GhostUserVoteView, InactiveMemberVoteView, ReviewDecisionView classes
# They don't need changes
