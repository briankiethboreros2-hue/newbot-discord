# modules/activity_tracker.py - User activity tracking system
from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio
from utils.logger import logger
from utils.error_handler import with_error_handling
from config import Config

class ActivityTracker:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self._last_cleanup_run = None
        self._activity_cache = {}
    
    async def initialize(self):
        """Initialize activity tracker"""
        logger.info("Activity tracker initialized")
        
        # Start background tasks
        self.cleanup_task = self.bot.loop.create_task(
            self._run_periodic_cleanup()
        )
    
    async def shutdown(self):
        """Shutdown activity tracker"""
        if hasattr(self, 'cleanup_task'):
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
    
    @with_error_handling
    async def track_message_activity(self, member) -> bool:
        """Track when a user sends a message"""
        if member.bot:
            return False
        
        # Check if user is inactive and returned
        user_info = await self.db.get_user_info(member.id)
        
        if user_info and user_info['status'] == 'inactive':
            # User has returned from inactivity!
            await self._handle_user_return(member, user_info)
        
        # Update activity in database
        await self.db.update_user_activity(
            user_id=member.id,
            username=member.name,
            activity_type="message"
        )
        
        # Update cache
        self._activity_cache[member.id] = datetime.utcnow()
        
        return True
    
    @with_error_handling
    async def track_voice_activity(self, member, before, after) -> bool:
        """Track when a user joins/leaves voice"""
        if member.bot:
            return False
        
        # Only track when joining voice (not leaving)
        if before.channel is None and after.channel is not None:
            user_info = await self.db.get_user_info(member.id)
            
            if user_info and user_info['status'] == 'inactive':
                # User has returned from inactivity!
                await self._handle_user_return(member, user_info)
            
            # Update activity in database
            await self.db.update_user_activity(
                user_id=member.id,
                username=member.name,
                activity_type="voice"
            )
            
            # Update cache
            self._activity_cache[member.id] = datetime.utcnow()
        
        return True
    
    async def _handle_user_return(self, member, user_info):
        """Handle when an inactive user returns"""
        logger.info(f"Inactive user returned: {member.name} ({member.id})")
        
        # Check if user has protected admin roles
        has_protected_role = any(
            role.id in Config.PROTECTED_ROLE_IDS for role in member.roles
        )
        
        if has_protected_role:
            # Admin users get auto-promoted back
            await self._auto_promote_returning_admin(member)
        else:
            # Regular users go to admin channel for review
            await self._notify_admins_returning_user(member, user_info)
    
    async def _auto_promote_returning_admin(self, member):
        """Automatically promote returning admin users"""
        from modules.role_manager import RoleManager
        from modules.notification import Notification
        
        role_mgr = RoleManager(self.bot, self.db)
        notifier = Notification(self.bot, self.db)
        
        # Get roles
        imperius_role = self.bot.get_guild(member.guild.id).get_role(Config.IMPERIUS_ROLE_ID)
        inactive_role = self.bot.get_guild(member.guild.id).get_role(Config.INACTIVE_ROLE_ID)
        
        if imperius_role and inactive_role:
            # Remove inactive role, add Imperius role
            await role_mgr.safe_role_change(
                member=member,
                remove_role=inactive_role,
                add_role=imperius_role
            )
            
            # Update database
            await self.db.update_user_status(
                user_id=member.id,
                status='active',
                notes="Auto-promoted (admin user returned)",
                role_id=Config.IMPERIUS_ROLE_ID
            )
            
            # Notify
            await notifier.send_admin_notification(
                title="🔄 Admin Auto-Promoted",
                description=f"{member.mention} (admin) has returned and was auto-promoted.",
                color=0x00ff00
            )
    
    async def _notify_admins_returning_user(self, member, user_info):
        """Notify admins about returning inactive user"""
        from modules.poll_manager import PollManager
        from modules.notification import Notification
        
        poll_mgr = PollManager(self.bot, self.db)
        notifier = Notification(self.bot, self.db)
        
        # Get admin channel
        admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
        if not admin_channel:
            logger.error("Admin channel not found")
            return
        
        # Create poll for admin decision
        poll = await poll_mgr.create_returning_user_poll(
            channel=admin_channel,
            member=member,
            days_inactive=user_info['days_inactive'] if user_info else 0
        )
        
        # Send notification
        await notifier.send_returning_user_notification(member, user_info)
    
    async def _run_periodic_cleanup(self):
        """Run periodic inactivity checks"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                now = datetime.now()
                
                # Run at configured time (default 2:00 AM)
                if now.hour == Config.CHECK_TIME_HOUR and (
                    self._last_cleanup_run is None or 
                    self._last_cleanup_run.day != now.day
                ):
                    logger.info("Running daily inactivity check...")
                    await self._check_inactive_users()
                    self._last_cleanup_run = now
                    logger.info("Daily inactivity check completed")
                
                # Wait 1 hour before checking again
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _check_inactive_users(self):
        """Check for inactive users and trigger cleanup"""
        from modules.cleanup_manager import CleanupManager
        
        cleanup_mgr = CleanupManager(self.bot, self.db)
        await cleanup_mgr.check_inactive_users()
    
    def get_last_activity(self, user_id: int) -> Optional[datetime]:
        """Get last activity from cache"""
        return self._activity_cache.get(user_id)
    
    async def force_activity_check(self):
        """Force an immediate activity check"""
        logger.info("Manual activity check triggered")
        await self._check_inactive_users()
        return "Activity check completed"
