import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging

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

class RecruitmentSystem:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        
        # Store active interviews: user_id -> {data}
        self.active_interviews = {}
        self.interview_timeouts = {}
        
        # Store admin review messages: user_id -> message_id
        self.admin_review_messages = {}
        self.tryout_vote_messages = {}
        
        # Track completed interviews to prevent re-interviewing returnees
        self.completed_interviews = set()
        self.failed_interviews = set()
        
        # Interview questions
        self.RECRUIT_QUESTIONS = [
            "1️⃣ Since you agreed to our terms and have read the rules, that also states we conduct clan tryouts. Do you agree to participate? (yes or no)",
            "2️⃣ We require CCN 1 week after the day you joined or got accepted, failed to comply with the requirements might face with penalty, What will be your future in-game name? (e.g., IM-Ryze)",
            "3️⃣ Our clan encourage members to improve, our members, OGs and Admins are always vocal when it comes to play making and correction of members. We are open so you can express yourself and also suggest, Are you open to communication about your personal gameplay and others suggestions? (yes or no)",
            "4️⃣ We value team chemistry, communication and overall team improvements so we prioritize playing with clan members than playing with others. so are you? (yes or no)",
            "5️⃣ We understand that sometimes there will be busy days and other priorities, we do have members who are working and also studying, are you working or a student?"
        ]
        
        # Start cleanup task for timed out interviews
        self.cleanup_interviews.start()
    
    @tasks.loop(minutes=1)
    async def cleanup_interviews(self):
        """Clean up interviews that have timed out"""
        now = datetime.now()
        to_remove = []
        
        for user_id, interview_data in list(self.active_interviews.items()):
            if 'start_time' in interview_data:
                time_diff = now - interview_data['start_time']
                if time_diff.total_seconds() > 300:  # 5 minutes
                    to_remove.append(user_id)
                    # Notify admins about timeout
                    await self.notify_interview_timeout(user_id, interview_data)
        
        for user_id in to_remove:
            if user_id in self.active_interviews:
                del self.active_interviews[user_id]
            if user_id in self.interview_timeouts:
                del self.interview_timeouts[user_id]
            self.failed_interviews.add(user_id)
    
    @cleanup_interviews.before_loop
    async def before_cleanup_interviews(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()
    
    async def handle_new_member(self, member):
        """Handle new member joining"""
        try:
            # Check if member is a returnee (already completed or failed interview)
            if member.id in self.completed_interviews:
                logger.info(f"⏭️ Skipping interview for returnee {member.name} (already completed)")
                return
                
            if member.id in self.failed_interviews:
                logger.info(f"⏭️ Skipping interview for returnee {member.name} (previously failed)")
                # Clear from failed list so they can try again
                self.failed_interviews.discard(member.id)
            
            # Check if member already has a role (shouldn't happen but safety check)
            if len(member.roles) > 1:
                logger.info(f"⏭️ Skipping interview for {member.name} (already has roles)")
                return
            
            # Get the recruit confirmation channel
            channel = self.bot.get_channel(1437568595977834590)  # RECRUIT_CONFIRM_CHANNEL
            if not channel:
                logger.error("Recruit confirmation channel not found!")
                return
            
            # Send welcome message
            welcome_msg = await channel.send(f":sparkles: Welcome to Impèrius!! {member.mention}")
            
            # Send DM instruction
            dm_instruction = await channel.send(f"Please check your DMs {member.mention}")
            
            # Store message IDs for later deletion
            self.interview_timeouts[member.id] = {
                'welcome_msg': welcome_msg.id,
                'dm_instruction': dm_instruction.id,
                'channel_id': channel.id,
                'member_name': member.name
            }
            
            # Start DM interview
            await self.start_dm_interview(member)
            
        except Exception as e:
            logger.error(f"Error handling new member: {e}")
    
    async def start_dm_interview(self, member):
        """Start DM interview with new member"""
        try:
            # Create DM channel
            dm_channel = await member.create_dm()
            
            # Send initial message
            embed = discord.Embed(
                title="Impèrius Recruitment Interview 🏰",
                description=f"Hello {member.name}, This is a mandatory interview for clarification for joining Impèrius\n"
                          f"**You have 5 minutes to answer these questions**\n\n"
                          f"Type `cancel` at any time to stop the interview.",
                color=discord.Color.blue()
            )
            await dm_channel.send(embed=embed)
            
            await asyncio.sleep(1)
            
            # Store interview data
            self.active_interviews[member.id] = {
                'answers': [],
                'current_question': 0,
                'start_time': datetime.now(),
                'member': member,
                'dm_channel': dm_channel,
                'member_name': member.name
            }
            
            # Ask first question
            await self.ask_next_question(member.id)
            
        except discord.Forbidden:
            logger.warning(f"Could not send DM to {member.name} - they might have DMs disabled")
            # Notify in channel that DMs are blocked
            await self.notify_dm_blocked(member)
        except Exception as e:
            logger.error(f"Error starting DM interview: {e}")
    
    async def ask_next_question(self, user_id):
        """Ask the next question in the interview"""
        if user_id not in self.active_interviews:
            return
        
        interview = self.active_interviews[user_id]
        question_index = interview['current_question']
        
        if question_index >= len(self.RECRUIT_QUESTIONS):
            await self.complete_interview(user_id)
            return
        
        question = self.RECRUIT_QUESTIONS[question_index]
        
        embed = discord.Embed(
            title=f"Question {question_index + 1}/{len(self.RECRUIT_QUESTIONS)}",
            description=question,
            color=discord.Color.gold()
        )
        
        try:
            await interview['dm_channel'].send(embed=embed)
        except Exception as e:
            logger.error(f"Error sending question: {e}")
    
    async def handle_dm_response(self, message):
        """Handle DM responses from users"""
        user_id = message.author.id
        
        if user_id not in self.active_interviews:
            return
        
        # Check if user wants to cancel
        if message.content.lower() == 'cancel':
            await message.channel.send("❌ Interview cancelled.")
            if user_id in self.active_interviews:
                del self.active_interviews[user_id]
            await self.cleanup_channel_messages(user_id)
            self.failed_interviews.add(user_id)
            return
        
        interview = self.active_interviews[user_id]
        question_index = interview['current_question']
        
        # Store answer
        interview['answers'].append(message.content)
        interview['current_question'] += 1
        
        # Check if all questions answered
        if interview['current_question'] >= len(self.RECRUIT_QUESTIONS):
            await self.complete_interview(user_id)
        else:
            await self.ask_next_question(user_id)
    
    async def complete_interview(self, user_id):
        """Complete the interview and notify admins"""
        if user_id not in self.active_interviews:
            return
        
        interview = self.active_interviews[user_id]
        member = interview['member']
        
        # Delete "Please check your DMs" message
        await self.cleanup_channel_messages(user_id)
        
        # Send completion message to user
        try:
            embed = discord.Embed(
                title="✅ Interview Complete!",
                description="Thank you for completing the interview!\n"
                          "Our admins will review your answers shortly.",
                color=discord.Color.green()
            )
            await interview['dm_channel'].send(embed=embed)
        except:
            pass
        
        # Mark as completed
        self.completed_interviews.add(user_id)
        
        # Send to admin channel for review
        await self.send_to_admin_review(member, interview['answers'])
        
        # Remove from active interviews
        del self.active_interviews[user_id]
    
    async def send_to_admin_review(self, member, answers):
        """Send interview results to admin channel"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                logger.error("Admin channel not found!")
                return
            
            embed = discord.Embed(
                title=f":military_helmet: Recruit {member.name} ({member.id})",
                description=f"**Willing to tryout:**\n{answers[0] if len(answers) > 0 else 'No answer'}\n\n"
                          f"**Clan format CCN:**\n{answers[1] if len(answers) > 1 else 'No answer'}\n\n"
                          f"**Open to discussion of personal gameplay and training:**\n{answers[2] if len(answers) > 2 else 'No answer'}\n\n"
                          f"**Working or student:**\n{answers[4] if len(answers) > 4 else 'No answer'}\n\n"
                          f"**Should we put the recruit to try out?**",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            view = TryoutVoteView(self.bot, member, answers)
            message = await channel.send(embed=embed, view=view)
            
            # Store message for reference
            self.admin_review_messages[member.id] = message.id
            
        except Exception as e:
            logger.error(f"Error sending to admin review: {e}")
    
    async def notify_interview_timeout(self, user_id, interview_data):
        """Notify admins when interview times out"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                return
            
            member = interview_data.get('member')
            if not member:
                return
            
            embed = discord.Embed(
                title="⏰ Interview Timed Out",
                description=f"Recruit {member.mention} ({member.name}) failed to complete the interview within 5 minutes.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            
            await channel.send(embed=embed)
            
            # Clean up channel messages
            await self.cleanup_channel_messages(user_id)
            
        except Exception as e:
            logger.error(f"Error notifying timeout: {e}")
    
    async def notify_dm_blocked(self, member):
        """Notify when user has DMs blocked"""
        try:
            channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
            if not channel:
                return
            
            embed = discord.Embed(
                title="📨 DMs Blocked",
                description=f"Recruit {member.mention} ({member.name}) has DMs disabled.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            
            await channel.send(embed=embed)
            
            # Clean up channel messages
            await self.cleanup_channel_messages(member.id)
            
        except Exception as e:
            logger.error(f"Error notifying DM blocked: {e}")
    
    async def cleanup_channel_messages(self, user_id):
        """Clean up messages in recruit channel"""
        if user_id not in self.interview_timeouts:
            return
        
        try:
            data = self.interview_timeouts[user_id]
            channel = self.bot.get_channel(data['channel_id'])
            if not channel:
                return
            
            # Try to delete the "Please check your DMs" message
            try:
                message = await channel.fetch_message(data['dm_instruction'])
                await message.delete()
                logger.info(f"🗑️ Deleted DM instruction for {data.get('member_name', 'unknown')}")
            except discord.NotFound:
                logger.warning(f"DM instruction message not found for user {user_id}")
            except discord.Forbidden:
                logger.error(f"No permission to delete message for user {user_id}")
            except Exception as e:
                logger.error(f"Error deleting message: {e}")
            
            # Clean up data
            if user_id in self.interview_timeouts:
                del self.interview_timeouts[user_id]
            
        except Exception as e:
            logger.error(f"Error cleaning up messages: {e}")

class TryoutVoteView(discord.ui.View):
    """View for admin tryout voting"""
    def __init__(self, bot, member=None, answers=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.answers = answers
        self.voted_admins = set()
    
    @discord.ui.button(label="✅ Tryout", style=discord.ButtonStyle.green, custom_id="persistent:tryout_yes")
    async def tryout_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "tryout")
    
    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.red, custom_id="persistent:tryout_no")
    async def tryout_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, "reject")
    
    async def handle_vote(self, interaction, vote_type):
        """Handle admin vote"""
        # Check if user has voting role
        if not has_voting_role(interaction.user):
            await interaction.response.send_message(
                "❌ You need to be Cᥣᥲᥒ Mᥲstᥱr🌟, Queen❤️‍🔥, cute ✨, or OG-Impèrius🐦‍🔥 to vote!",
                ephemeral=True
            )
            return
        
        # Check if admin has already voted
        if interaction.user.id in self.voted_admins:
            await interaction.response.send_message("⚠️ You've already voted!", ephemeral=True)
            return
        
        self.voted_admins.add(interaction.user.id)
        
        # Get admin's display name
        admin_name = interaction.user.display_name
        
        # Send notification in admin channel
        channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
        if channel:
            if vote_type == "tryout":
                message = f"👑 **{admin_name}** ordered the tryout for :military_helmet: {self.member.mention}"
                
                # Send to review channel for tryout decision
                await self.send_to_review_channel()
            else:
                message = f"👑 **{admin_name}** rejected :military_helmet: {self.member.mention}"
            
            await channel.send(message)
        
        await interaction.response.send_message(f"✅ Vote recorded: {vote_type}", ephemeral=True)
    
    async def send_to_review_channel(self):
        """Send to review channel for tryout decision"""
        try:
            channel = self.bot.get_channel(1454802873300025396)  # REVIEW_CHANNEL
            if not channel:
                logger.error("Review channel not found!")
                return
            
            embed = discord.Embed(
                title=f":military_helmet: Recruit {self.member.name} Tryout Decision :scales:",
                description=f"**CCN:** {self.answers[1] if len(self.answers) > 1 else 'Not provided'}\n\n"
                          f"Vote whether the recruit passes or fails the tryout:",
                color=discord.Color.purple(),
                timestamp=datetime.now()
            )
            
            view = TryoutDecisionView(self.bot, self.member, self.answers)
            await channel.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error sending to review channel: {e}")

class TryoutDecisionView(discord.ui.View):
    """View for tryout pass/fail decision"""
    def __init__(self, bot, member=None, answers=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.answers = answers
        self.voted_admins = set()
    
    @discord.ui.button(label="✅ Pass", style=discord.ButtonStyle.green, custom_id="persistent:tryout_pass")
    async def tryout_pass(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_decision(interaction, "passed")
    
    @discord.ui.button(label="❌ Fail", style=discord.ButtonStyle.red, custom_id="persistent:tryout_fail")
    async def tryout_fail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_decision(interaction, "failed")
    
    async def handle_decision(self, interaction, decision):
        """Handle tryout decision"""
        # Check if user has voting role
        if not has_voting_role(interaction.user):
            await interaction.response.send_message(
                "❌ You need to be Cᥣᥲᥒ Mᥲstᥱr🌟, Queen❤️‍🔥, cute ✨, or OG-Impèrius🐦‍🔥 to vote!",
                ephemeral=True
            )
            return
        
        if interaction.user.id in self.voted_admins:
            await interaction.response.send_message("⚠️ You've already voted!", ephemeral=True)
            return
        
        self.voted_admins.add(interaction.user.id)
        
        admin_name = interaction.user.display_name
        
        # Send decision to admin channel
        admin_channel = self.bot.get_channel(1455138098437689387)  # ADMIN_CHANNEL
        if admin_channel:
            await admin_channel.send(f"👑 **{admin_name}** {decision} recruit :military_helmet: {self.member.mention}")
        
        if decision == "passed":
            # Give role and announce in tryout result channel
            await self.handle_passed_recruit(admin_name)
        
        await interaction.response.send_message(f"✅ Vote recorded: {decision}", ephemeral=True)
    
    async def handle_passed_recruit(self, admin_name):
        """Handle passed recruit"""
        try:
            # Give Impèrius🔥 role
            role = self.member.guild.get_role(1437570031822176408)  # IMPERIUS_ROLE
            if role and role not in self.member.roles:
                await self.member.add_roles(role)
                logger.info(f"🎉 Gave Impèrius🔥 role to {self.member.name}")
            elif role in self.member.roles:
                logger.info(f"ℹ️ {self.member.name} already has Impèrius🔥 role")
            
            # Announce in tryout result channel
            channel = self.bot.get_channel(1455205385463009310)  # TRYOUT_RESULT_CHANNEL
            if channel:
                embed = discord.Embed(
                    title="🎉 New Member Joins Impèrius!",
                    description=f":military_helmet: **{self.member.name}** passed! and joining our ranks!\n"
                              f"Now an Impèrius🔥 member!\n\n"
                              f"Approved by: **{admin_name}**",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.set_thumbnail(url=self.member.display_avatar.url)
                await channel.send(embed=embed)
            
        except discord.Forbidden:
            logger.error(f"❌ No permission to add role to {self.member.name}")
        except Exception as e:
            logger.error(f"Error handling passed recruit: {e}")
