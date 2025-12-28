# modules/cleanup_manager.py - Cleanup & inactivity management system
import discord
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from utils.logger import logger
from utils.error_handler import with_error_handling
from config import Config

class CleanupManager:
    def __init__(self, bot, db, poll_mgr=None, role_mgr=None):
        self.bot = bot
        self.db = db
        self.poll_mgr = poll_mgr
        self.role_mgr = role_mgr
        self._is_checking = False
        
    async def initialize(self):
        """Initialize cleanup manager"""
        logger.info("Cleanup manager initialized")
        
        # Import managers if not provided
        if not self.poll_mgr:
            from modules.poll_manager import PollManager
            self.poll_mgr = PollManager(self.bot, self.db)
            await self.poll_mgr.initialize()
        
        if not self.role_mgr:
            from modules.role_manager import RoleManager
            self.role_mgr = RoleManager(self.bot, self.db)
            await self.role_mgr.initialize()
    
    @with_error_handling
    async def check_inactive_users(self):
        """Main cleanup check for inactive users"""
        if self._is_checking:
            logger.warning("Cleanup check already in progress")
            return
        
        self._is_checking = True
        
        try:
            guild = self.bot.guilds[0] if self.bot.guilds else None
            if not guild:
                logger.error("Bot not in any guild")
                return
            
            logger.info(f"Starting cleanup check for guild: {guild.name}")
            
            # 1. Check for ghost users (no roles)
            await self._check_ghost_users(guild)
            
            # 2. Check for inactive Imperius members
            await self._check_inactive_imperius_users(guild)
            
            # 3. Check for users to warn (12 days)
            await self._check_warning_users(guild)
            
            logger.info("Cleanup check completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup check: {e}")
        finally:
            self._is_checking = False
    
    async def _check_ghost_users(self, guild: discord.Guild):
        """Check for users with no roles (ghost users)"""
        cleanup_channel = guild.get_channel(Config.CLEANUP_CHANNEL_ID)
        if not cleanup_channel:
            logger.error(f"Cleanup channel not found: {Config.CLEANUP_CHANNEL_ID}")
            return
        
        ghost_users = await self.db.get_ghost_users(guild)
        
        for ghost_data in ghost_users:
            member = ghost_data['member']
            
            # Skip bots and protected users
            if member.bot:
                continue
            
            # Check if already has a pending poll
            has_pending = await self._has_pending_poll(member.id, "ghost")
            if has_pending:
                continue
            
            # Create poll for this ghost user
            poll = await self.poll_mgr.create_cleanup_poll(
                channel=cleanup_channel,
                member=member,
                poll_type="ghost"
            )
            
            if poll:
                logger.info(f"Created ghost poll for {member.name}")
                
                # Ping admins for ghost users (urgent)
                await cleanup_channel.send(
                    f"👻 **Ghost user detected!** {member.mention}\n"
                    f"Please vote on the above poll."
                )
    
    async def _check_inactive_imperius_users(self, guild: discord.Guild):
        """Check for inactive Imperius members (15+ days)"""
        cleanup_channel = guild.get_channel(Config.CLEANUP_CHANNEL_ID)
        if not cleanup_channel:
            return
        
        # Get inactive users from database
        inactive_users = await self.db.calculate_inactivity()
        
        for user_data in inactive_users:
            user_id = user_data['user_id']
            member = guild.get_member(user_id)
            
            if not member:
                # User left the server
                await self.db.update_user_status(
                    user_id=user_id,
                    status='left_server',
                    notes="User left server while inactive"
                )
                continue
            
            # Check if user has protected admin roles
            has_protected_role = any(
                role.id in Config.PROTECTED_ROLE_IDS for role in member.roles
            )
            
            if has_protected_role:
                # Admin users are protected from auto-demotion
                logger.info(f"Protected admin user skipped: {member.name}")
                continue
            
            # Check if user has Imperius role
            has_imperius_role = any(
                role.id == Config.IMPERIUS_ROLE_ID for role in member.roles
            )
            
            if not has_imperius_role:
                # User doesn't have Imperius role, skip
                continue
            
            # Check if already has a pending poll
            has_pending = await self._has_pending_poll(member.id, "inactive")
            if has_pending:
                continue
            
            # Create poll for demotion
            poll = await self.poll_mgr.create_cleanup_poll(
                channel=cleanup_channel,
                member=member,
                poll_type="inactive"
            )
            
            if poll:
                logger.info(f"Created inactive poll for {member.name}")
                
                # Update user status to pending_demotion
                await self.db.update_user_status(
                    user_id=user_id,
                    status='pending_demotion',
                    notes=f"Inactive for {user_data['days_inactive']} days, poll created"
                )
    
    async def _check_warning_users(self, guild: discord.Guild):
        """Check for users to warn (12 days inactive)"""
        # Get users at 12 days inactive
        cursor = await self.db.conn.execute('''
            SELECT user_id, username, days_inactive 
            FROM user_activity 
            WHERE days_inactive = ? 
            AND status = 'active'
            AND current_role_id = ?
        ''', (Config.INACTIVITY_WARNING_DAYS, Config.IMPERIUS_ROLE_ID))
        
        warning_users = await cursor.fetchall()
        
        for user_row in warning_users:
            user_id, username, days_inactive = user_row
            member = guild.get_member(user_id)
            
            if member:
                # Check if already warned
                cursor = await self.db.conn.execute('''
                    SELECT last_warning FROM user_activity WHERE user_id = ?
                ''', (user_id,))
                
                last_warning = await cursor.fetchone()
                
                # Warn only once per inactivity period
                if not last_warning or not last_warning[0]:
                    await self._send_inactivity_warning(member, days_inactive)
                    
                    # Update last warning time
                    await self.db.conn.execute('''
                        UPDATE user_activity 
                        SET last_warning = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    ''', (user_id,))
                    
                    await self.db.conn.commit()
    
    async def _send_inactivity_warning(self, member: discord.Member, days_inactive: int):
        """Send inactivity warning to user"""
        try:
            # Try to DM the user
            await member.send(
                f"⚠️ **Inactivity Warning**\n"
                f"You have been inactive for {days_inactive} days.\n"
                f"If you remain inactive for {Config.INACTIVITY_DEMOTION_DAYS - days_inactive} more days, "
                f"you will be demoted to the Inactive role.\n\n"
                f"Please be active in the server to maintain your current role."
            )
            logger.info(f"Sent inactivity warning to {member.name}")
        except:
            # Can't DM, log it
            logger.warning(f"Could not DM inactivity warning to {member.name}")
    
    async def _has_pending_poll(self, user_id: int, poll_type: str) -> bool:
        """Check if user already has a pending poll"""
        cursor = await self.db.conn.execute('''
            SELECT COUNT(*) FROM polls 
            WHERE notes LIKE ? 
            AND status = 'open'
        ''', (f"%target_user:{user_id}%",))
        
        count = await cursor.fetchone()
        return count[0] > 0 if count else False
    
    @with_error_handling
    async def process_poll_result(self, poll_id: int, winning_option: str, results: Dict[str, int]):
        """Process the result of a cleanup poll"""
        # Get poll details
        cursor = await self.db.conn.execute('''
            SELECT poll_id, notes, poll_type FROM polls WHERE poll_id = ?
        ''', (poll_id,))
        
        poll_data = await cursor.fetchone()
        if not poll_data:
            logger.error(f"Poll not found: {poll_id}")
            return
        
        poll_id, notes, poll_type = poll_data
        
        # Extract target user from notes
        target_user_id = None
        if notes and notes.startswith("target_user:"):
            try:
                target_user_id = int(notes.split(":")[1])
            except:
                pass
        
        if not target_user_id:
            logger.error(f"No target user for poll {poll_id}")
            return
        
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return
        
        member = guild.get_member(target_user_id)
        if not member:
            logger.error(f"Member not found: {target_user_id}")
            return
        
        # Process based on poll type and winning option
        if poll_type == "ghost":
            await self._process_ghost_poll_result(member, winning_option)
        elif poll_type == "inactive":
            await self._process_inactive_poll_result(member, winning_option)
        elif poll_type == "returning":
            await self._process_returning_poll_result(member, winning_option)
        elif poll_type == "review":
            await self._process_review_poll_result(member, winning_option)
        
        # Log the vote result
        await self.db.log_vote(
            target_user_id=member.id,
            target_username=member.name,
            voter_id=self.bot.user.id,  # System vote
            voter_username=self.bot.user.name,
            action=f"poll_result_{poll_type}",
            poll_id=poll_id,
            result=winning_option
        )
    
    async def _process_ghost_poll_result(self, member: discord.Member, winning_option: str):
        """Process ghost user poll result"""
        if "Kick" in winning_option:
            await self._kick_member(member, "Ghost user - voted to kick")
        elif "Promote" in winning_option:
            await self._promote_to_imperius(member, "Ghost user - voted to promote")
        elif "Review" in winning_option:
            await self._mark_for_review(member, "Ghost user - needs review")
    
    async def _process_inactive_poll_result(self, member: discord.Member, winning_option: str):
        """Process inactive user poll result"""
        if "Demote" in winning_option:
            await self._demote_to_inactive(member, "Inactive - voted to demote")
        elif "Review" in winning_option:
            await self._mark_for_review(member, "Inactive user - needs review")
        # "Keep current role" requires no action
    
    async def _process_returning_poll_result(self, member: discord.Member, winning_option: str):
        """Process returning user poll result"""
        if "Promote" in winning_option:
            await self._promote_to_imperius(member, "Returning user - voted to promote")
        elif "Review" in winning_option:
            await self._mark_for_review(member, "Returning user - needs interview")
        # "Keep as inactive" requires no action
    
    async def _process_review_poll_result(self, member: discord.Member, winning_option: str):
        """Process review poll result"""
        if "Promote" in winning_option:
            await self._promote_to_imperius(member, "Review complete - voted to promote")
        elif "Kick" in winning_option:
            await self._kick_member(member, "Review complete - voted to kick")
        # "Extend review period" requires no action
    
    async def _kick_member(self, member: discord.Member, reason: str):
        """Kick a member from the server"""
        try:
            await member.kick(reason=reason)
            logger.info(f"Kicked {member.name}: {reason}")
            
            # Update database
            await self.db.update_user_status(
                user_id=member.id,
                status='kicked',
                notes=reason
            )
            
            # Log cleanup action
            await self.db.log_cleanup_action(
                user_id=member.id,
                action_type="kicked",
                reason=reason,
                performed_by=self.bot.user.id
            )
            
        except Exception as e:
            logger.error(f"Failed to kick {member.name}: {e}")
    
    async def _promote_to_imperius(self, member: discord.Member, reason: str):
        """Promote member to Imperius role"""
        await self.role_mgr.promote_to_imperius(member, reason)
    
    async def _demote_to_inactive(self, member: discord.Member, reason: str):
        """Demote member to inactive role"""
        await self.role_mgr.demote_to_inactive(member, reason)
    
    async def _mark_for_review(self, member: discord.Member, reason: str):
        """Mark member for review"""
        # Create review poll in admin channel
        admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
        if admin_channel:
            poll = await self.poll_mgr.create_cleanup_poll(
                channel=admin_channel,
                member=member,
                poll_type="review"
            )
            
            if poll:
                # Update database
                await self.db.update_user_status(
                    user_id=member.id,
                    status='under_review',
                    notes=reason
                )
    
    async def get_status(self) -> discord.Embed:
        """Get cleanup system status"""
        # Get counts from database
        cursor = await self.db.conn.execute('''
            SELECT status, COUNT(*) FROM user_activity GROUP BY status
        ''')
        
        status_counts = await cursor.fetchall()
        
        # Get pending polls
        cursor = await self.db.conn.execute('''
            SELECT poll_type, COUNT(*) FROM polls 
            WHERE status = 'open' GROUP BY poll_type
        ''')
        
        poll_counts = await cursor.fetchall()
        
        # Create status embed
        embed = discord.Embed(
            title="🧹 Cleanup System Status",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        # Add user status counts
        status_text = ""
        for status, count in status_counts:
            status_text += f"**{status.title()}:** {count}\n"
        
        if status_text:
            embed.add_field(name="User Statuses", value=status_text, inline=False)
        
        # Add poll counts
        poll_text = ""
        for poll_type, count in poll_counts:
            poll_text += f"**{poll_type.title()} polls:** {count}\n"
        
        if poll_text:
            embed.add_field(name="Pending Polls", value=poll_text, inline=False)
        
        # Add system info
        embed.add_field(
            name="Settings",
            value=f"**Warning:** {Config.INACTIVITY_WARNING_DAYS} days\n"
                  f"**Demotion:** {Config.INACTIVITY_DEMOTION_DAYS} days\n"
                  f"**Check time:** {Config.CHECK_TIME_HOUR}:00",
            inline=False
        )
        
        embed.set_footer(text="Last updated")
        
        return embed
