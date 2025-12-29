import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger(__name__)

# ======== INACTIVE MEMBER VOTE VIEW ========
class InactiveMemberVoteView(discord.ui.View):
    def __init__(self, member_id, member_name, days_inactive, cleanup_system=None):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.member_name = member_name
        self.days_inactive = days_inactive
        self.vote_made = False
        self.cleanup_system = cleanup_system
        
    @discord.ui.button(label="Demote", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def demote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "demote")
        
    @discord.ui.button(label="Keep Role", style=discord.ButtonStyle.success, emoji="✅")
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "keep")
    
    async def handle_vote(self, interaction, vote_type):
        if self.vote_made:
            await interaction.response.send_message("Already decided!", ephemeral=True)
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
        """Demote member to inactive role and post to review channel"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                imperius_role = interaction.guild.get_role(1437570031822176408)  # Impèrius🔥
                inactive_role = interaction.guild.get_role(1454803208995340328)  # Inactive role
                
                if imperius_role and inactive_role:
                    # Remove Impèrius, add Inactive
                    await member.remove_roles(imperius_role)
                    await member.add_roles(inactive_role)
                    
                    # Post to review channel for promotion/kick voting
                    review_channel = interaction.guild.get_channel(1454802873300025396)
                    if review_channel:
                        embed = discord.Embed(
                            title=f"📋 Demoted Member Review",
                            description=f"**Member:** {member.mention} ({member.display_name})\n"
                                      f"**Previous Role:** Impèrius🔥\n"
                                      f"**Current Role:** Inactive\n"
                                      f"**Days Inactive:** {self.days_inactive} days\n"
                                      f"**Demoted By:** {admin_name}\n\n"
                                      f"**Vote:** Promote back or Kick?",
                            color=discord.Color.blue(),
                            timestamp=datetime.now()
                        )
                        
                        view = DemotedReviewVoteView(member.id, member.display_name)
                        await review_channel.send(embed=embed, view=view)
                    
                    # Confirm in admin channel
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
                    
                    # Send DM to member
                    try:
                        await member.send(
                            f"📋 **You have been demoted to Inactive role**\n\n"
                            f"**Reason:** {self.days_inactive} days inactive\n"
                            f"**Action by:** {admin_name}\n\n"
                            f"You can now only access specific channels.\n"
                            f"Contact admins if you want to be promoted back."
                        )
                    except:
                        pass  # Can't DM user
                        
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
                              f"**Action:** Impèrius🔥 Role Kept\n"
                              f"**Reason:** Pardoned by admin\n"
                              f"**Decided By:** {admin_name}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.channel.send(embed=embed)
                
                # Record the pardon in cleanup system
                if self.cleanup_system:
                    await self.cleanup_system.record_admin_pardon(member.id)
                elif hasattr(interaction.client, 'cleanup_system'):
                    await interaction.client.cleanup_system.record_admin_pardon(member.id)
                
                logger.info(f"Kept {member.name}'s role (voted by {admin_name})")
        except Exception as e:
            logger.error(f"Error keeping role: {e}")

# ======== DEMOTED REVIEW VOTE VIEW ========
class DemotedReviewVoteView(discord.ui.View):
    def __init__(self, member_id, member_name):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.member_name = member_name
        self.vote_made = False
        
    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️")
    async def promote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review_vote(interaction, "promote")
        
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_review_vote(interaction, "kick")
    
    async def handle_review_vote(self, interaction, vote_type):
        if self.vote_made:
            await interaction.response.send_message("Already decided!", ephemeral=True)
            return
        
        self.vote_made = True
        
        # Remove original message
        try:
            await interaction.message.delete()
        except:
            pass
        
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
                    
                    # Restore channel permissions
                    for channel in interaction.guild.text_channels:
                        try:
                            await channel.set_permissions(member, overwrite=None)
                        except:
                            pass
                    
                    # Post in tryout result channel
                    result_channel = interaction.guild.get_channel(1455205385463009310)
                    if result_channel:
                        await result_channel.send(f"🎉 {member.mention} has been promoted back to Impèrius🔥!")
                    
                    embed = discord.Embed(
                        title="✅ Member Promoted Back",
                        description=f"**Member:** {member.mention} ({member.display_name})\n"
                                  f"**Action:** Promoted back to Impèrius🔥\n"
                                  f"**Decided By:** {admin_name}",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    await interaction.channel.send(embed=embed)
                    
                    # Send DM to member
                    try:
                        await member.send(f"🎉 **You have been promoted back to Impèrius🔥!** Welcome back!")
                    except:
                        pass
                    
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
                    await member.send("You have been kicked from Impèrius due to inactivity.")
                except:
                    pass
                
                # Kick member
                await member.kick(reason=f"Inactive - Voted by {admin_name}")
                
                embed = discord.Embed(
                    title="👢 Member Kicked",
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

# ======== GHOST USER VOTE VIEW ========
class GhostUserVoteView(discord.ui.View):
    def __init__(self, member_id, member_name, days_in_server):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.member_name = member_name
        self.days_in_server = days_in_server
        self.vote_made = False
        
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_ghost_vote(interaction, "kick")
        
    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️")
    async def promote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_ghost_vote(interaction, "promote")
        
    @discord.ui.button(label="Re-tryout", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def retry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_ghost_vote(interaction, "retryout")
    
    async def handle_ghost_vote(self, interaction, vote_type):
        if self.vote_made:
            await interaction.response.send_message("Already decided!", ephemeral=True)
            return
        
        self.vote_made = True
        
        # Remove original message
        try:
            await interaction.message.delete()
        except:
            pass
        
        admin_name = interaction.user.display_name
        
        if vote_type == "kick":
            await self.process_ghost_kick(interaction, admin_name)
        elif vote_type == "promote":
            await self.process_ghost_promote(interaction, admin_name)
        elif vote_type == "retryout":
            await self.process_ghost_retryout(interaction, admin_name)
        
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
    
    async def process_ghost_promote(self, interaction, admin_name):
        """Promote ghost user directly to Impèrius🔥"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if member:
                imperius_role = interaction.guild.get_role(1437570031822176408)
                
                if imperius_role:
                    await member.add_roles(imperius_role)
                    
                    # Post in tryout result channel
                    result_channel = interaction.guild.get_channel(1455205385463009310)
                    if result_channel:
                        await result_channel.send(f"🎉 {member.mention} was promoted directly to Impèrius🔥!")
                    
                    embed = discord.Embed(
                        title=f"⬆️ Ghost User Promoted",
                        description=f"**User:** {member.mention}\n"
                                  f"**Action:** Directly promoted to Impèrius🔥\n"
                                  f"**Decided By:** {admin_name}",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    await interaction.channel.send(embed=embed)
                    
                    # Send welcome DM
                    try:
                        await member.send(f"🎉 **Welcome to Impèrius🔥!** You've been directly promoted by {admin_name}.")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error promoting ghost user: {e}")
    
    async def process_ghost_retryout(self, interaction, admin_name):
        """Send ghost user to re-tryout interview"""
        try:
            member = interaction.guild.get_member(self.member_id)
            if not member:
                return
            
            embed = discord.Embed(
                title=f"🔄 Ghost User Sent to Tryout",
                description=f"**User:** {member.mention}\n"
                          f"**Action:** Sent to tryout system\n"
                          f"**Decided By:** {admin_name}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            await interaction.channel.send(embed=embed)
            
            # Post in recruit channel
            recruit_channel = interaction.guild.get_channel(1437568595977834590)
            if recruit_channel:
                await recruit_channel.send(f"🔄 {member.mention} has been sent for re-tryout by {admin_name}")
                await recruit_channel.send("Please check your DMs")
            
            # Send DM interview
            try:
                interview_embed = discord.Embed(
                    title="🔄 Re-tryout Interview",
                    description=f"Hello {member.name},\n\n"
                              f"An admin has requested you to complete a re-tryout interview.\n"
                              f"Please answer the following questions within 5 minutes:",
                    color=discord.Color.blue()
                )
                
                questions = [
                    "1️⃣ Do you agree to participate in clan tryouts? (yes/no)",
                    "2️⃣ What will be your future in-game name? (e.g., IM-Ryze)",
                    "3️⃣ Are you open to communication about your gameplay? (yes/no)",
                    "4️⃣ Will you prioritize playing with clan members? (yes/no)",
                    "5️⃣ Are you working or a student?"
                ]
                
                interview_embed.add_field(
                    name="Questions",
                    value="\n".join(questions),
                    inline=False
                )
                
                interview_embed.set_footer(text="Reply to this DM with your answers.")
                
                await member.send(embed=interview_embed)
                
                logger.info(f"Sent re-tryout interview to {member.name}")
                
            except discord.Forbidden:
                await interaction.channel.send(f"❌ Cannot DM {member.mention}. They may have DMs disabled.")
                
        except Exception as e:
            logger.error(f"Error sending ghost user to tryout: {e}")

# ======== CLEANUP SYSTEM ========
class CleanupSystem:
    def __init__(self, bot, guild, state):
        self.bot = bot
        self.guild = guild
        self.state = state
        self.last_ghost_check = datetime.now() - timedelta(days=1)
        self.last_inactive_check = datetime.now() - timedelta(days=1)
        self.attendance_channel_id = 1437768842871832597
        self.admin_channel_id = 1455138098437689387
        self.review_channel_id = 1454802873300025396
        
        # Track when each member was last checked
        self.member_last_check = {}  # {member_id: last_check_date}
    
    def start_cleanup_task(self):
        """Start the cleanup task"""
        self.cleanup_task.start()
    
    @tasks.loop(hours=24)  # Check every 24 hours
    async def cleanup_task(self):
        """Main cleanup task - runs daily"""
        logger.info("🚀 Running cleanup task...")
        
        # Check for ghost users (every day)
        await self.check_ghost_users()
        
        # Check for inactive Impèrius members (every 15 days per member)
        await self.check_inactive_members_15day_cycle()
        
        logger.info("✅ Cleanup task completed")
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()
    
    async def check_inactive_members_15day_cycle(self):
        """Check for inactive Impèrius🔥 members - only checks each member every 15 days"""
        try:
            admin_channel = self.guild.get_channel(self.admin_channel_id)
            attendance_channel = self.guild.get_channel(self.attendance_channel_id)
            
            if not admin_channel or not attendance_channel:
                logger.error("❌ Required channels not found!")
                return
            
            now = datetime.now()
            imperius_role = self.guild.get_role(1437570031822176408)
            
            if not imperius_role:
                logger.error("❌ Impèrius🔥 role not found!")
                return
            
            logger.info(f"😴 Starting 15-day cycle check for {len(imperius_role.members)} Impèrius members...")
            
            members_checked = 0
            members_skipped = 0
            members_flagged = 0
            
            # Check each Impèrius member
            for member in imperius_role.members:
                if member.bot:
                    continue
                
                member_id = member.id
                last_check_date = self.member_last_check.get(member_id)
                
                # Only check if 15+ days since last check OR never checked before
                should_check = False
                
                if last_check_date is None:
                    # Never checked before - check now
                    should_check = True
                else:
                    # Calculate days since last check
                    days_since_last_check = (now - last_check_date).days
                    if days_since_last_check >= 15:
                        should_check = True
                    else:
                        # Skip - not time to check yet
                        members_skipped += 1
                        logger.debug(f"Skipping {member.name} - checked {days_since_last_check} days ago")
                        continue
                
                if should_check:
                    members_checked += 1
                    
                    # Determine if member was active since last check date
                    was_active = False
                    
                    if last_check_date:
                        # Check attendance channel for activity since last check
                        was_active = await self.was_member_active_since(member, attendance_channel, last_check_date)
                    else:
                        # First time checking - check last 15 days
                        fifteen_days_ago = now - timedelta(days=15)
                        was_active = await self.was_member_active_since(member, attendance_channel, fifteen_days_ago)
                    
                    if not was_active:
                        # Member inactive since last check - flag for demotion
                        days_inactive = 15  # Default
                        if last_check_date:
                            days_inactive = (now - last_check_date).days
                        
                        # Check if already posted today
                        already_posted = await self.is_user_already_posted_today(admin_channel, member.id, "inactive")
                        if not already_posted:
                            embed = discord.Embed(
                                title=f"😴 Inactive Impèrius Member",
                                description=f"**Member:** {member.mention} ({member.display_name})\n"
                                          f"**Role:** Impèrius🔥\n"
                                          f"**Days Inactive:** {days_inactive} days\n"
                                          f"**Last Checked:** {last_check_date.strftime('%Y-%m-%d') if last_check_date else 'First check'}\n\n"
                                          f"**Candidate for demotion to Inactive role**",
                                color=discord.Color.orange(),
                                timestamp=now
                            )
                            
                            view = InactiveMemberVoteView(member.id, member.display_name, days_inactive, self)
                            await admin_channel.send(embed=embed, view=view)
                            
                            members_flagged += 1
                            logger.info(f"Flagged inactive member: {member.name} ({days_inactive} days since last check)")
                            await asyncio.sleep(2)
                    
                    # Update last check date to TODAY (whether active or not)
                    self.member_last_check[member_id] = now
                    logger.debug(f"Updated last check for {member.name}: {now.strftime('%Y-%m-%d')}")
            
            logger.info(f"✅ 15-day cycle check completed: {members_checked} checked, {members_skipped} skipped, {members_flagged} flagged")
            
        except Exception as e:
            logger.error(f"❌ Error checking inactive members (15-day cycle): {e}")
    
    async def was_member_active_since(self, member, attendance_channel, since_date):
        """Check if member was active in attendance channel since given date"""
        try:
            async for message in attendance_channel.history(limit=100, after=since_date):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.description and str(member.id) in embed.description:
                            return True
            return False
        except Exception as e:
            logger.error(f"Error checking member activity: {e}")
            return False
    
    async def record_admin_pardon(self, member_id):
        """Call this when admin pardons a member (from InactiveMemberVoteView.process_keep)"""
        self.member_last_check[member_id] = datetime.now()
        logger.info(f"Admin pardon recorded for member {member_id}, last check reset to today")
    
    async def check_ghost_users(self):
        """Check for users with no roles (ghosts) - posts to REVIEW channel"""
        try:
            review_channel = self.guild.get_channel(self.review_channel_id)
            if not review_channel:
                logger.error(f"❌ Review channel not found: {self.review_channel_id}")
                return
            
            now = datetime.now()
            
            # Only check once per day
            if (now - self.last_ghost_check).days < 1:
                return
            
            logger.info("👻 Checking for ghost users...")
            ghost_count = 0
            
            for member in self.guild.members:
                if member.bot:
                    continue
                
                # Skip users who recently joined (< 24 hours)
                if member.joined_at:
                    join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
                    hours_since_join = (now - join_date).total_seconds() / 3600
                    if hours_since_join < 24:
                        continue
                
                # Check if member has only @everyone role
                if len(member.roles) == 1:  # Only @everyone
                    days_in_server = (now - join_date).days
                    
                    if days_in_server >= 1:
                        # Check if already posted today
                        already_posted = await self.is_user_already_posted_today(review_channel, member.id, "ghost")
                        if not already_posted:
                            embed = discord.Embed(
                                title="👻 Ghost User Detected",
                                description=f"**User:** {member.mention} ({member.name})\n"
                                          f"**Days in server:** {days_in_server} days\n"
                                          f"**Status:** No roles assigned",
                                color=discord.Color.dark_gray(),
                                timestamp=now
                            )
                            
                            view = GhostUserVoteView(member.id, member.name, days_in_server)
                            await review_channel.send(embed=embed, view=view)
                            
                            ghost_count += 1
                            logger.info(f"Posted ghost user: {member.name}")
                            await asyncio.sleep(2)  # Rate limiting
            
            self.last_ghost_check = now
            logger.info(f"✅ Ghost user check completed: {ghost_count} found")
            
        except Exception as e:
            logger.error(f"❌ Error checking ghost users: {e}")
    
    async def get_last_activity_date(self, member, attendance_channel):
        """Get the last date a member was announced online"""
        try:
            last_date = None
            
            async for message in attendance_channel.history(limit=200):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.description and str(member.id) in embed.description:
                            if message.created_at:
                                msg_time = message.created_at.replace(tzinfo=None) if message.created_at.tzinfo else message.created_at
                                if not last_date or msg_time > last_date:
                                    last_date = msg_time
                            break
                if last_date:
                    break
            
            return last_date
            
        except Exception as e:
            logger.error(f"Error getting last activity: {e}")
            return None
    
    async def is_user_already_posted_today(self, channel, user_id, post_type):
        """Check if user was already posted about today"""
        try:
            today = datetime.now().date()
            
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and message.created_at.date() == today:
                    if message.embeds:
                        for embed in message.embeds:
                            if embed.description and str(user_id) in embed.description:
                                # Check post type by title
                                title = embed.title or ""
                                if post_type == "inactive" and ("Inactive" in title or "😴" in title):
                                    return True
                                elif post_type == "ghost" and ("Ghost" in title or "👻" in title):
                                    return True
        except:
            pass
        return False
