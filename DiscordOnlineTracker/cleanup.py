import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CleanupSystem:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.checked_users = set()  # Track checked users to prevent duplicates
        
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
    
    async def check_ghost_users(self):
        """Check for users with no roles (ghosts)"""
        try:
            channel = self.bot.get_channel(self.bot.ADMIN_CHANNEL)
            if not channel:
                return
            
            ghost_users = []
            
            for member in self.guild.members:
                # Skip bots
                if member.bot:
                    continue
                
                # Check if member has only @everyone role
                if len(member.roles) == 1:  # Only @everyone
                    # Calculate days in server
                    join_date = member.joined_at
                    if join_date:
                        days_in_server = (datetime.now() - join_date).days
                        
                        # Only show if more than 1 day
                        if days_in_server >= 1:
                            ghost_users.append((member, days_in_server))
            
            if ghost_users:
                for member, days in ghost_users:
                    # Check if we've already reported this user recently
                    if member.id in self.checked_users:
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
                    self.checked_users.add(member.id)
                    
                    # Wait a bit between messages to avoid rate limits
                    await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error checking ghost users: {e}")
    
    async def check_inactive_members(self):
        """Check for inactive Impèrius🔥 members"""
        try:
            channel = self.bot.get_channel(self.bot.ADMIN_CHANNEL)
            if not channel:
                return
            
            imperius_role = self.guild.get_role(self.bot.IMPERIUS_ROLE)
            if not imperius_role:
                return
            
            inactive_members = []
            
            for member in imperius_role.members:
                # Skip if member is bot
                if member.bot:
                    continue
                
                # Check last message in the guild
                last_message = await self.get_last_message(member)
                
                if last_message:
                    days_since_last_message = (datetime.now() - last_message.created_at).days
                    
                    # If inactive for 7+ days
                    if days_since_last_message >= 7:
                        inactive_members.append((member, days_since_last_message))
                else:
                    # If no messages found, check join date
                    if member.joined_at:
                        days_since_join = (datetime.now() - member.joined_at).days
                        if days_since_join >= 7:
                            inactive_members.append((member, days_since_join))
            
            if inactive_members:
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
                    
                    await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error checking inactive members: {e}")
    
    async def get_last_message(self, member):
        """Get the last message sent by a member in the guild"""
        try:
            # Check recent messages in all text channels
            for channel in self.guild.text_channels:
                try:
                    # Get last 100 messages
                    async for message in channel.history(limit=100):
                        if message.author.id == member.id:
                            return message
                except discord.Forbidden:
                    continue
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting last message: {e}")
        
        return None

class GhostUserVoteView(discord.ui.View):
    """View for ghost user voting"""
    def __init__(self, bot, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.voted_admins = set()
    
    @discord.ui.button(label="🦶 Kick", style=discord.ButtonStyle.red, custom_id="ghost_kick")
    async def ghost_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes to kick ghost user"""
        await self.handle_vote(interaction, "kick")
    
    @discord.ui.button(label="🎯 Give Chance", style=discord.ButtonStyle.green, custom_id="ghost_chance")
    async def ghost_chance(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes to give chance"""
        await self.handle_vote(interaction, "chance")
    
    async def handle_vote(self, interaction, action):
        """Handle ghost user vote"""
        if interaction.user.id in self.voted_admins:
            await interaction.response.send_message("You've already voted!", ephemeral=True)
            return
        
        self.voted_admins.add(interaction.user.id)
        
        admin_name = interaction.user.display_name
        
        # Send action to admin channel
        channel = self.bot.get_channel(self.bot.ADMIN_CHANNEL)
        if channel:
            if action == "kick":
                try:
                    # Try to kick the user
                    await self.member.kick(reason="Ghost user - no roles after 24h")
                    message = f"👑 **{admin_name}** kicked ghost user {self.member.mention}"
                except Exception as e:
                    message = f"👑 **{admin_name}** voted to kick ghost user {self.member.mention} (Failed: {e})"
            else:
                message = f"👑 **{admin_name}** gave a chance to ghost user {self.member.mention}"
            
            await channel.send(message)
        
        await interaction.response.send_message(f"Vote recorded: {action}", ephemeral=True)

class InactiveMemberVoteView(discord.ui.View):
    """View for inactive member voting"""
    def __init__(self, bot, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.voted_admins = set()
    
    @discord.ui.button(label="⬇️ Demote", style=discord.ButtonStyle.red, custom_id="inactive_demote")
    async def inactive_demote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes to demote"""
        await self.handle_vote(interaction, "demote")
    
    @discord.ui.button(label="✅ Pardon", style=discord.ButtonStyle.green, custom_id="inactive_pardon")
    async def inactive_pardon(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes to pardon"""
        await self.handle_vote(interaction, "pardon")
    
    @discord.ui.button(label="🔍 Review", style=discord.ButtonStyle.blurple, custom_id="inactive_review")
    async def inactive_review(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes for review"""
        await self.handle_vote(interaction, "review")
    
    async def handle_vote(self, interaction, action):
        """Handle inactive member vote"""
        if interaction.user.id in self.voted_admins:
            await interaction.response.send_message("You've already voted!", ephemeral=True)
            return
        
        self.voted_admins.add(interaction.user.id)
        
        admin_name = interaction.user.display_name
        
        channel = self.bot.get_channel(self.bot.ADMIN_CHANNEL)
        if channel:
            if action == "demote":
                await self.demote_member()
                message = f"👑 **{admin_name}** demoted inactive member {self.member.mention}"
            elif action == "pardon":
                message = f"👑 **{admin_name}** pardoned inactive member {self.member.mention}"
            else:  # review
                message = f"👑 **{admin_name}** requested review for inactive member {self.member.mention}"
                await self.send_to_review_channel(admin_name)
            
            await channel.send(message)
        
        await interaction.response.send_message(f"Vote recorded: {action}", ephemeral=True)
    
    async def demote_member(self):
        """Demote member to inactive role"""
        try:
            # Get roles
            imperius_role = self.member.guild.get_role(self.bot.IMPERIUS_ROLE)
            inactive_role = self.member.guild.get_role(self.bot.INACTIVE_ROLE)
            
            if imperius_role and inactive_role:
                # Remove Impèrius🔥 role
                await self.member.remove_roles(imperius_role)
                # Add inactive role
                await self.member.add_roles(inactive_role)
                
                # Send DM notification
                try:
                    embed = discord.Embed(
                        title="Role Update - Impèrius",
                        description="You have been moved to the inactive roster due to inactivity.\n\n"
                                  "As an inactive member, you can only access:\n"
                                  f"• <#{self.bot.INACTIVE_ACCESS_CHANNEL}>\n"
                                  f"• <#{self.bot.INACTIVE_VOICE_CHANNEL}>\n\n"
                                  "Contact an admin if you wish to return to active status.",
                        color=discord.Color.orange()
                    )
                    await self.member.send(embed=embed)
                except:
                    pass  # Can't DM, that's okay
                
        except Exception as e:
            logger.error(f"Error demoting member: {e}")
    
    async def send_to_review_channel(self, admin_name):
        """Send to review channel for final decision"""
        try:
            channel = self.bot.get_channel(self.bot.REVIEW_CHANNEL)
            if not channel:
                return
            
            embed = discord.Embed(
                title="🔍 Inactive Member Review",
                description=f"**Member:** {self.member.mention} ({self.member.name})\n"
                          f"**Requested by:** {admin_name}\n\n"
                          "Should this member be promoted back or kicked?",
                color=discord.Color.purple(),
                timestamp=datetime.now()
            )
            
            view = ReviewDecisionView(self.bot, self.member)
            await channel.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error sending to review channel: {e}")

class ReviewDecisionView(discord.ui.View):
    """View for review channel decision"""
    def __init__(self, bot, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.voted_admins = set()
    
    @discord.ui.button(label="⬆️ Promote", style=discord.ButtonStyle.green, custom_id="review_promote")
    async def review_promote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes to promote back"""
        await self.handle_decision(interaction, "promote")
    
    @discord.ui.button(label="🦶 Kick", style=discord.ButtonStyle.red, custom_id="review_kick")
    async def review_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Admin votes to kick"""
        await self.handle_decision(interaction, "kick")
    
    async def handle_decision(self, interaction, decision):
        """Handle review decision"""
        if interaction.user.id in self.voted_admins:
            await interaction.response.send_message("You've already voted!", ephemeral=True)
            return
        
        self.voted_admins.add(interaction.user.id)
        
        admin_name = interaction.user.display_name
        
        if decision == "promote":
            await self.promote_member()
            message = f"👑 **{admin_name}** promoted {self.member.mention} back to Impèrius🔥"
        else:
            try:
                await self.member.kick(reason="Inactive member - voted to kick in review")
                message = f"👑 **{admin_name}** kicked inactive member {self.member.mention}"
            except Exception as e:
                message = f"👑 **{admin_name}** voted to kick inactive member {self.member.mention} (Failed: {e})"
        
        # Send to admin channel
        channel = self.bot.get_channel(self.bot.ADMIN_CHANNEL)
        if channel:
            await channel.send(message)
        
        await interaction.response.send_message(f"Vote recorded: {decision}", ephemeral=True)
    
    async def promote_member(self):
        """Promote member back to Impèrius🔥"""
        try:
            imperius_role = self.member.guild.get_role(self.bot.IMPERIUS_ROLE)
            inactive_role = self.member.guild.get_role(self.bot.INACTIVE_ROLE)
            
            if imperius_role and inactive_role:
                # Remove inactive role
                await self.member.remove_roles(inactive_role)
                # Add Impèrius🔥 role
                await self.member.add_roles(imperius_role)
                
                # Send DM notification
                try:
                    embed = discord.Embed(
                        title="Welcome Back - Impèrius",
                        description="You have been promoted back to active status!\n\n"
                                  "Your Impèrius🔥 role has been restored.",
                        color=discord.Color.green()
                    )
                    await self.member.send(embed=embed)
                except:
                    pass  # Can't DM, that's okay
                
        except Exception as e:
            logger.error(f"Error promoting member: {e}")
