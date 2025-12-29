import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# ======== INACTIVE MEMBER VOTE VIEW ========
class InactiveMemberVoteView(discord.ui.View):
    def __init__(self, member_id, member_name, days_inactive, cleanup_system):
        super().__init__(timeout=None)  # No timeout
        self.member_id = member_id
        self.member_name = member_name
        self.days_inactive = days_inactive
        self.cleanup_system = cleanup_system
        self.vote_made = False  # Track if vote already made
        
    @discord.ui.button(label="Demote", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def demote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "demote", "Demoted to Inactive")
        
    @discord.ui.button(label="Keep Role", style=discord.ButtonStyle.success, emoji="✅")
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "keep", "Role Kept")
        
    @discord.ui.button(label="Review", style=discord.ButtonStyle.secondary, emoji="📋")
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "review", "Sent to Review")
    
    async def handle_vote(self, interaction, vote_type, action_text):
        # Prevent multiple votes on same button
        if self.vote_made:
            await interaction.response.send_message("Action already taken!", ephemeral=True)
            return
        
        self.vote_made = True
        
        # Remove original message immediately
        try:
            await interaction.message.delete()
        except:
            pass
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        # Store who voted
        admin_name = interaction.user.display_name
        
        # Process the vote
        if vote_type == "demote":
            await self.process_demote(interaction, admin_name)
        elif vote_type == "keep":
            await self.process_keep(interaction, admin_name)
        elif vote_type == "review":
            await self.process_review(interaction, admin_name)
        
        # Stop the view
        self.stop()
    
    async def process_demote(self, interaction, admin_name):
        """Demote member to inactive role"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                imperius_role = interaction.guild.get_role(1437570031822176408)  # Impèrius🔥
                inactive_role = interaction.guild.get_role(1454803208995340328)  # Inactive role
                
                if imperius_role and inactive_role:
                    # Remove Impèrius role, add inactive role
                    await member.remove_roles(imperius_role)
                    await member.add_roles(inactive_role)
                    
                    # Restrict access to only specific channels
                    await self.restrict_channel_access(interaction.guild, member)
                    
                    # Post result
                    embed = discord.Embed(
                        title=f"⬇️ Member Demoted",
                        description=f"**Member:** {member.mention} ({member.display_name})\n"
                                  f"**Action:** Demoted to Inactive Role\n"
                                  f"**Reason:** {self.days_inactive} days inactive\n"
                                  f"**Decided By:** {admin_name}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    await interaction.channel.send(embed=embed)
                    
                    logger.info(f"Demoted {member.name} to inactive (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error demoting member: {e}")
            await interaction.channel.send(f"❌ Error demoting member: {e}")
    
    async def process_keep(self, interaction, admin_name):
        """Keep member's role"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                embed = discord.Embed(
                    title=f"✅ Role Kept",
                    description=f"**Member:** {member.mention} ({member.display_name})\n"
                              f"**Action:** Role Kept\n"
                              f"**Reason:** Pardoned by admin\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
                
                logger.info(f"Kept {member.name}'s role (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error keeping role: {e}")
    
    async def process_review(self, interaction, admin_name):
        """Send to review channel"""
        try:
            review_channel = interaction.guild.get_channel(1454802873300025396)  # Review channel
            member = interaction.guild.get_member(self.member_id)
            
            if member and review_channel:
                embed = discord.Embed(
                    title=f"📋 Inactive Member Review",
                    description=f"**Member:** {member.mention} ({member.display_name})\n"
                              f"**Current Role:** Impèrius🔥\n"
                              f"**Days Inactive:** {self.days_inactive} days\n"
                              f"**Sent for Review By:** {admin_name}\n\n"
                              f"**Vote:** Promote back or Kick?",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                # Create review voting view
                view = InactiveReviewVoteView(member.id, member.display_name)
                await review_channel.send(embed=embed, view=view)
                
                # Confirm in admin channel
                await interaction.channel.send(
                    f"📋 **Sent to Review Channel**\n"
                    f"Member: {member.mention}\n"
                    f"Sent by: {admin_name}\n"
                    f"Review: <#{review_channel.id}>"
                )
                
                logger.info(f"Sent {member.name} to review (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error sending to review: {e}")
            await interaction.channel.send(f"❌ Error sending to review: {e}")
    
    async def restrict_channel_access(self, guild, member):
        """Restrict inactive member to only specific channels"""
        try:
            # Allow access to these channels only
            allowed_channels = [
                1369091668724154419,  # specific channel
                1437575744824934531   # call channel
            ]
            
            # Get all text channels
            for channel in guild.text_channels:
                if channel.id not in allowed_channels:
                    try:
                        # Deny view permission
                        await channel.set_permissions(member, view_channel=False)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error restricting channel access: {e}")

# ======== INACTIVE REVIEW VOTE VIEW ========
class InactiveReviewVoteView(discord.ui.View):
    def __init__(self, member_id, member_name):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.member_name = member_name
        self.vote_made = False
        
    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️")
    async def promote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review_vote(interaction, "promote", "Promoted Back")
        
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review_vote(interaction, "kick", "Kicked")
    
    async def handle_review_vote(self, interaction, vote_type, action_text):
        if self.vote_made:
            await interaction.response.send_message("Action already taken!", ephemeral=True)
            return
        
        self.vote_made = True
        
        # Remove original message
        try:
            await interaction.message.delete()
        except:
            pass
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        admin_name = interaction.user.display_name
        
        if vote_type == "promote":
            await self.process_promote(interaction, admin_name)
        elif vote_type == "kick":
            await self.process_kick(interaction, admin_name)
        
        self.stop()
    
    async def process_promote(self, interaction, admin_name):
        """Promote back to Impèrius🔥"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                imperius_role = interaction.guild.get_role(1437570031822176408)  # Impèrius🔥
                inactive_role = interaction.guild.get_role(1454803208995340328)  # Inactive
                
                if imperius_role and inactive_role:
                    # Remove inactive, add Impèrius
                    await member.remove_roles(inactive_role)
                    await member.add_roles(imperius_role)
                    
                    # Restore channel access
                    await self.restore_channel_access(interaction.guild, member)
                    
                    embed = discord.Embed(
                        title=f"⬆️ Member Promoted Back",
                        description=f"**Member:** {member.mention} ({member.display_name})\n"
                                  f"**Action:** Promoted back to Impèrius🔥\n"
                                  f"**Decided By:** {admin_name}",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    await interaction.channel.send(embed=embed)
                    
                    logger.info(f"Promoted {member.name} back (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error promoting back: {e}")
    
    async def process_kick(self, interaction, admin_name):
        """Kick the member"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                # Send DM before kicking
                try:
                    await member.send(f"You have been kicked from Impèrius due to inactivity. You can rejoin if you wish to be active again.")
                except:
                    pass
                
                # Kick member
                await member.kick(reason=f"Inactive - Voted by {admin_name}")
                
                embed = discord.Embed(
                    title=f"👢 Member Kicked",
                    description=f"**Member:** {member.display_name}\n"
                              f"**Action:** Kicked from server\n"
                              f"**Reason:** Inactivity\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
                
                logger.info(f"Kicked {member.name} (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error kicking member: {e}")
    
    async def restore_channel_access(self, guild, member):
        """Restore normal channel access"""
        try:
            # Reset channel permissions to default
            for channel in guild.text_channels:
                try:
                    await channel.set_permissions(member, overwrite=None)
                except:
                    pass
        except Exception as e:
            logger.error(f"Error restoring channel access: {e}")

# ======== GHOST USER VOTE VIEW ========
class GhostUserVoteView(discord.ui.View):
    def __init__(self, member_id, member_name, days_in_server, cleanup_system):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.member_name = member_name
        self.days_in_server = days_in_server
        self.cleanup_system = cleanup_system
        self.vote_made = False
        
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_ghost_vote(interaction, "kick")
        
    @discord.ui.button(label="Give Chance", style=discord.ButtonStyle.success, emoji="🤝")
    async def chance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_ghost_vote(interaction, "chance")
    
    async def handle_ghost_vote(self, interaction, vote_type):
        if self.vote_made:
            await interaction.response.send_message("Action already taken!", ephemeral=True)
            return
        
        self.vote_made = True
        
        # Remove original message
        try:
            await interaction.message.delete()
        except:
            pass
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        admin_name = interaction.user.display_name
        
        if vote_type == "kick":
            await self.process_ghost_kick(interaction, admin_name)
        elif vote_type == "chance":
            await self.process_ghost_chance(interaction, admin_name)
        
        self.stop()
    
    async def process_ghost_kick(self, interaction, admin_name):
        """Kick ghost user"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                await member.kick(reason=f"Ghost user - No roles after {self.days_in_server} days (Voted by {admin_name})")
                
                embed = discord.Embed(
                    title=f"👢 Ghost User Kicked",
                    description=f"**User:** {member.display_name}\n"
                              f"**Days in server:** {self.days_in_server} days\n"
                              f"**Reason:** No roles assigned\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
                
                logger.info(f"Kicked ghost user {member.name} (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error kicking ghost user: {e}")
            await interaction.channel.send(f"❌ Error kicking user: {e}")
    
    async def process_ghost_chance(self, interaction, admin_name):
        """Give ghost user another chance"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                embed = discord.Embed(
                    title=f"🤝 Chance Given",
                    description=f"**User:** {member.mention} ({member.display_name})\n"
                              f"**Days in server:** {self.days_in_server} days\n"
                              f"**Action:** Given another chance\n"
                              f"**Decided By:** {admin_name}\n\n"
                              f"*Will be checked again in 24 hours*",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
                
                logger.info(f"Gave chance to ghost user {member.name} (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error giving chance: {e}")

# ======== CLEANUP SYSTEM ========
class CleanupSystem:
    def __init__(self, bot, guild, state):
        self.bot = bot
        self.guild = guild
        self.state = state
        self.reported_users = set()  # Track already reported users
        self.reported_inactives = set()  # Track already reported inactive members
        
    def start_cleanup_task(self):
        """Start the cleanup task"""
        self.cleanup_task.start()
    
    @tasks.loop(hours=24)  # Run every 24 hours
    async def cleanup_task(self):
        """Main cleanup task"""
        logger.info("Running cleanup task...")
        
        # Reset tracking sets daily
        self.reported_users.clear()
        
        # Check for ghost users
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
                
                # Skip if already reported today
                if member.id in self.reported_users:
                    continue
                
                # Skip users who recently rejoined (within 24 hours)
                if member.joined_at:
                    join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
                    hours_since_join = (now - join_date).total_seconds() / 3600
                    if hours_since_join < 24:
                        continue
                
                # Check if member has only @everyone role
                if len(member.roles) == 1:  # Only @everyone
                    # Calculate days in server
                    join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
                    if join_date:
                        days_in_server = (now - join_date).days
                        
                        # Only show if more than 1 day
                        if days_in_server >= 1:
                            ghost_users.append((member, days_in_server))
                            self.reported_users.add(member.id)  # Mark as reported
            
            # Post ghost users ONE AT A TIME with delay
            if ghost_users:
                logger.info(f"Found {len(ghost_users)} ghost users")
                for member, days in ghost_users[:5]:  # Limit to 5 per day to avoid spam
                    embed = discord.Embed(
                        title="👻 Ghost User Detected",
                        description=f"**User:** {member.mention} ({member.name})\n"
                                  f"**Days in server:** {days} days\n"
                                  f"**Status:** No roles assigned",
                        color=discord.Color.dark_gray(),
                        timestamp=datetime.now()
                    )
                    
                    view = GhostUserVoteView(member.id, member.name, days, self)
                    await channel.send(embed=embed, view=view)
                    
                    # Wait 5 seconds between posts to avoid spam
                    await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error checking ghost users: {e}")
    
    async def check_inactive_members(self):
        """Check for inactive Impèrius🔥 members (runs weekly)"""
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
                
                # Skip if already reported
                if member.id in self.reported_inactives:
                    continue
                
                # Check last message in the guild
                last_message = await self.get_last_message(member)
                
                if last_message:
                    last_message_time = last_message.created_at.replace(tzinfo=None) if last_message.created_at.tzinfo else last_message.created_at
                    days_since_last_message = (now - last_message_time).days
                    
                    # If inactive for 7+ days
                    if days_since_last_message >= 7:
                        inactive_members.append((member, days_since_last_message))
                        self.reported_inactives.add(member.id)
                else:
                    # If no messages found, check join date
                    if member.joined_at:
                        join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
                        days_since_join = (now - join_date).days
                        if days_since_join >= 7:
                            inactive_members.append((member, days_since_join))
                            self.reported_inactives.add(member.id)
            
            # Post inactive members ONE AT A TIME with delay
            if inactive_members:
                logger.info(f"Found {len(inactive_members)} inactive members")
                for member, days_inactive in inactive_members[:10]:  # Limit to 10 per week
                    embed = discord.Embed(
                        title=f"😴 Inactive Member - {member.display_name}",
                        description=f"**Member:** {member.mention}\n"
                                  f"**Role:** Impèrius🔥\n"
                                  f"**Days Inactive:** {days_inactive} days\n"
                                  f"**Candidate for demotion**",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    
                    view = InactiveMemberVoteView(member.id, member.display_name, days_inactive, self)
                    await channel.send(embed=embed, view=view)
                    
                    # Wait 10 seconds between posts to avoid spam
                    await asyncio.sleep(10)
            
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
                    
                    # Get last 100 messages
                    async for message in channel.history(limit=100):
                        if message.author.id == member.id and not message.author.bot:
                            return message
                except discord.Forbidden:
                    continue
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting last message: {e}")
        
        return None
