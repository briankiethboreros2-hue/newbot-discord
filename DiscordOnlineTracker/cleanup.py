import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# ======== INACTIVE MEMBER VOTE VIEW ========
class InactiveMemberVoteView(discord.ui.View):
    def __init__(self, member_id, member_name, days_inactive, cleanup_system):
        super().__init__(timeout=None)  # No timeout - stays forever
        self.member_id = member_id
        self.member_name = member_name
        self.days_inactive = days_inactive
        self.cleanup_system = cleanup_system
        self.vote_made = False
        
    @discord.ui.button(label="Demote", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def demote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "demote")
        
    @discord.ui.button(label="Keep Role", style=discord.ButtonStyle.success, emoji="✅")
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "keep")
        
    @discord.ui.button(label="Review", style=discord.ButtonStyle.secondary, emoji="📋")
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "review")
    
    async def handle_vote(self, interaction, vote_type):
        if self.vote_made:
            await interaction.response.send_message("Action already taken!", ephemeral=True)
            return
        
        self.vote_made = True
        
        # Remove original message
        try:
            await interaction.message.delete()
        except:
            pass
        
        admin_name = interaction.user.display_name
        
        if vote_type == "demote":
            await self.process_demote(interaction, admin_name)
        elif vote_type == "keep":
            await self.process_keep(interaction, admin_name)
        elif vote_type == "review":
            await self.process_review(interaction, admin_name)
        
        self.stop()
    
    async def process_demote(self, interaction, admin_name):
        """Demote member to inactive role"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                imperius_role = interaction.guild.get_role(1437570031822176408)  # Impèrius🔥
                inactive_role = interaction.guild.get_role(1454803208995340328)  # Inactive role
                
                if imperius_role and inactive_role:
                    await member.remove_roles(imperius_role)
                    await member.add_roles(inactive_role)
                    
                    # Restrict access to only specific channels
                    await self.restrict_channel_access(interaction.guild, member)
                    
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
                              f"**Vote:** Demote to Inactive or Keep Role?",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                # Create review voting view (Demote/Keep Role)
                view = InactiveReviewVoteView(member.id, member.display_name, self.days_inactive)
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
    def __init__(self, member_id, member_name, days_inactive):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.member_name = member_name
        self.days_inactive = days_inactive
        self.vote_made = False
        
    @discord.ui.button(label="Demote", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def demote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review_vote(interaction, "demote", "Demoted to Inactive")
        
    @discord.ui.button(label="Keep Role", style=discord.ButtonStyle.success, emoji="✅")
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review_vote(interaction, "keep", "Role Kept")
    
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
        
        admin_name = interaction.user.display_name
        
        if vote_type == "demote":
            await self.process_demote(interaction, admin_name)
        elif vote_type == "keep":
            await self.process_keep(interaction, admin_name)
        
        self.stop()
    
    async def process_demote(self, interaction, admin_name):
        """Demote to inactive role"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                imperius_role = interaction.guild.get_role(1437570031822176408)  # Impèrius🔥
                inactive_role = interaction.guild.get_role(1454803208995340328)  # Inactive
                
                if imperius_role and inactive_role:
                    await member.remove_roles(imperius_role)
                    await member.add_roles(inactive_role)
                    
                    # Restrict channel access
                    allowed_channels = [1369091668724154419, 1437575744824934531]
                    for channel in interaction.guild.text_channels:
                        if channel.id not in allowed_channels:
                            try:
                                await channel.set_permissions(member, view_channel=False)
                            except:
                                pass
                    
                    embed = discord.Embed(
                        title=f"⬇️ Member Demoted (Review)",
                        description=f"**Member:** {member.mention} ({member.display_name})\n"
                                  f"**Action:** Demoted to Inactive Role\n"
                                  f"**Reason:** {self.days_inactive} days inactive\n"
                                  f"**Decided By:** {admin_name}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    await interaction.channel.send(embed=embed)
                    
                    logger.info(f"Demoted {member.name} via review (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error demoting via review: {e}")
    
    async def process_keep(self, interaction, admin_name):
        """Keep the role"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                embed = discord.Embed(
                    title=f"✅ Role Kept (Review)",
                    description=f"**Member:** {member.mention} ({member.display_name})\n"
                              f"**Action:** Impèrius🔥 Role Kept\n"
                              f"**Reason:** Reviewed and approved\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
                
                logger.info(f"Kept {member.name}'s role via review (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error keeping role via review: {e}")

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
        
        try:
            await interaction.message.delete()
        except:
            pass
        
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
                await member.kick(reason=f"No roles after {self.days_in_server} days")
                
                embed = discord.Embed(
                    title=f"👢 Ghost User Kicked",
                    description=f"**User:** {member.display_name}\n"
                              f"**Days:** {self.days_in_server} days\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error kicking ghost user: {e}")
    
    async def process_ghost_chance(self, interaction, admin_name):
        """Give ghost user another chance"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                embed = discord.Embed(
                    title=f"🤝 Chance Given",
                    description=f"**User:** {member.mention}\n"
                              f"**Days:** {self.days_in_server} days\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error giving chance: {e}")

# ======== CLEANUP SYSTEM ========
class CleanupSystem:
    def __init__(self, bot, guild, state):
        self.bot = bot
        self.guild = guild
        self.state = state
        self.last_check = {}  # Track when users were last checked
        self.attendance_channel_id = 1437768842871832597  # Attendance channel
        
    def start_cleanup_task(self):
        """Start the cleanup task"""
        self.cleanup_task.start()
    
    @tasks.loop(hours=24)  # Check every 24 hours
    async def cleanup_task(self):
        """Main cleanup task"""
        logger.info("Running cleanup task...")
        
        # Check for ghost users (every day)
        await self.check_ghost_users()
        
        # Check for inactive members (every 7 days)
        if datetime.now().weekday() == 0:  # Run on Mondays (once a week)
            await self.check_inactive_members()
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()
    
    async def check_ghost_users(self):
        """Check for users with no roles"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                return
            
            now = datetime.now()
            
            for member in self.guild.members:
                if member.bot:
                    continue
                
                # Skip if checked in last 24 hours
                last_check = self.last_check.get(member.id)
                if last_check and (now - last_check).days < 1:
                    continue
                
                if member.joined_at:
                    join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
                    hours_since_join = (now - join_date).total_seconds() / 3600
                    if hours_since_join < 24:
                        continue
                
                # Check if only @everyone role
                if len(member.roles) == 1:
                    days_in_server = (now - join_date).days
                    if days_in_server >= 1:
                        # Check if already posted (search in channel)
                        already_posted = await self.is_already_posted(channel, member.id, "ghost")
                        if not already_posted:
                            embed = discord.Embed(
                                title="👻 Ghost User Detected",
                                description=f"**User:** {member.mention}\n"
                                          f"**Days:** {days_in_server} days",
                                color=discord.Color.dark_gray(),
                                timestamp=now
                            )
                            
                            view = GhostUserVoteView(member.id, member.name, days_in_server, self)
                            await channel.send(embed=embed, view=view)
                            
                            # Mark as checked
                            self.last_check[member.id] = now
                            
                            # Wait to avoid rate limits
                            await asyncio.sleep(2)
                            
        except Exception as e:
            logger.error(f"Error checking ghost users: {e}")
    
    async def check_inactive_members(self):
        """Check for inactive Impèrius🔥 members based on attendance channel"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                return
            
            imperius_role = self.guild.get_role(1437570031822176408)
            if not imperius_role:
                return
            
            now = datetime.now()
            attendance_channel = self.guild.get_channel(self.attendance_channel_id)
            
            if not attendance_channel:
                logger.error("Attendance channel not found for tracking!")
                return
            
            logger.info(f"Checking inactivity via attendance channel: {attendance_channel.name}")
            
            for member in imperius_role.members:
                if member.bot:
                    continue
                
                # Skip if checked in last 7 days
                last_check = self.last_check.get(member.id)
                if last_check and (now - last_check).days < 7:
                    continue
                
                # Get last time member was announced online in attendance channel
                last_announced = await self.get_last_attendance_announcement(member, attendance_channel)
                
                if last_announced:
                    days_inactive = (now - last_announced).days
                    
                    # Member is inactive if not announced online for 7+ days
                    if days_inactive >= 7:
                        # Check if already posted
                        already_posted = await self.is_already_posted(channel, member.id, "inactive")
                        if not already_posted:
                            embed = discord.Embed(
                                title=f"😴 Inactive Member - {member.display_name}",
                                description=f"**Member:** {member.mention}\n"
                                          f"**Role:** Impèrius🔥\n"
                                          f"**Days Inactive:** {days_inactive} days\n"
                                          f"**Last Online:** {last_announced.strftime('%Y-%m-%d %H:%M')}\n"
                                          f"**Candidate for demotion**",
                                color=discord.Color.orange(),
                                timestamp=now
                            )
                            
                            view = InactiveMemberVoteView(member.id, member.display_name, days_inactive, self)
                            await channel.send(embed=embed, view=view)
                            
                            self.last_check[member.id] = now
                            await asyncio.sleep(2)
                else:
                    # If never announced in attendance channel, check join date
                    if member.joined_at:
                        join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
                        days_since_join = (now - join_date).days
                        
                        if days_since_join >= 7:
                            # Member has been in server for 7+ days but never shown online
                            already_posted = await self.is_already_posted(channel, member.id, "inactive")
                            if not already_posted:
                                embed = discord.Embed(
                                    title=f"😴 Inactive Member - {member.display_name}",
                                    description=f"**Member:** {member.mention}\n"
                                              f"**Role:** Impèrius🔥\n"
                                              f"**Days Since Join:** {days_since_join} days\n"
                                              f"**Status:** Never appeared online\n"
                                              f"**Candidate for demotion**",
                                    color=discord.Color.orange(),
                                    timestamp=now
                                )
                                
                                view = InactiveMemberVoteView(member.id, member.display_name, days_since_join, self)
                                await channel.send(embed=embed, view=view)
                                
                                self.last_check[member.id] = now
                                await asyncio.sleep(2)
                            
        except Exception as e:
            logger.error(f"Error checking inactive members: {e}")
    
    async def get_last_attendance_announcement(self, member, attendance_channel):
        """Get the last time member was announced online in attendance channel"""
        try:
            last_announcement = None
            
            async for message in attendance_channel.history(limit=200):  # Check last 200 messages
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.description and str(member.id) in embed.description:
                            # Found announcement for this member
                            if message.created_at:
                                msg_time = message.created_at.replace(tzinfo=None) if message.created_at.tzinfo else message.created_at
                                if not last_announcement or msg_time > last_announcement:
                                    last_announcement = msg_time
            
            return last_announcement
            
        except Exception as e:
            logger.error(f"Error getting attendance announcement: {e}")
            return None
    
    async def is_already_posted(self, channel, user_id, post_type):
        """Check if user was already posted about"""
        try:
            # Check last 50 messages in the channel
            async for message in channel.history(limit=50):
                if message.embeds and message.author == self.bot.user:
                    for embed in message.embeds:
                        if embed.description and str(user_id) in embed.description:
                            # Check if this is a similar post (not a result post)
                            if post_type == "inactive" and ("Inactive Member" in embed.title or "😴" in embed.title):
                                return True
                            elif post_type == "ghost" and ("Ghost User" in embed.title or "👻" in embed.title):
                                return True
        except:
            pass
        return False
