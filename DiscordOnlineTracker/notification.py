# modules/notification.py - Notification and embed system
import discord
from datetime import datetime
from typing import Optional, Dict, Any
from utils.logger import logger
from utils.error_handler import with_error_handling
from config import Config

class Notification:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    @with_error_handling
    async def send_admin_notification(self, title: str, description: str, 
                                     color: int = 0x00ff00, 
                                     ping_admins: bool = False) -> Optional[discord.Message]:
        """Send notification to admin channel"""
        admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
        if not admin_channel:
            logger.error(f"Admin channel not found: {Config.ADMIN_CHANNEL_ID}")
            return None
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow()
        )
        
        message_content = ""
        if ping_admins:
            # Ping admin roles
            message_content = " ".join([f"<@&{role_id}>" for role_id in Config.PROTECTED_ROLE_IDS])
        
        try:
            message = await admin_channel.send(content=message_content, embed=embed)
            return message
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")
            return None
    
    @with_error_handling
    async def send_cleanup_notification(self, member: discord.Member, 
                                        notification_type: str, 
                                        extra_info: Dict[str, Any] = None) -> Optional[discord.Message]:
        """Send notification to cleanup channel"""
        cleanup_channel = self.bot.get_channel(Config.CLEANUP_CHANNEL_ID)
        if not cleanup_channel:
            return None
        
        notification_configs = {
            "ghost_detected": {
                "title": "👻 Ghost User Detected",
                "description": f"{member.mention} has no roles.",
                "color": 0xff5555,
                "ping": True
            },
            "inactive_demoted": {
                "title": "😴 User Demoted to Inactive",
                "description": f"{member.mention} has been demoted for inactivity.",
                "color": 0xffaa00,
                "ping": False
            },
            "user_returned": {
                "title": "🫡 User Returned from Inactivity",
                "description": f"{member.mention} has returned and needs review.",
                "color": 0x55ff55,
                "ping": True
            },
            "user_promoted": {
                "title": "🎉 User Promoted",
                "description": f"{member.mention} has been promoted to <@&{Config.IMPERIUS_ROLE_ID}>.",
                "color": 0x00ff00,
                "ping": False
            },
            "user_kicked": {
                "title": "👢 User Kicked",
                "description": f"{member.mention} has been kicked from the server.",
                "color": 0xff0000,
                "ping": False
            }
        }
        
        config = notification_configs.get(notification_type, notification_configs["ghost_detected"])
        
        embed = discord.Embed(
            title=config["title"],
            description=config["description"],
            color=config["color"],
            timestamp=datetime.utcnow()
        )
        
        # Add extra info if provided
        if extra_info:
            for key, value in extra_info.items():
                if value:  # Only add non-empty values
                    embed.add_field(name=key.title(), value=str(value), inline=True)
        
        # Add user info
        user_info = await self.db.get_user_info(member.id)
        if user_info:
            embed.add_field(name="Status", value=user_info['status'].title(), inline=True)
            if user_info['days_inactive'] > 0:
                embed.add_field(name="Days Inactive", value=str(user_info['days_inactive']), inline=True)
        
        embed.set_footer(text=f"User ID: {member.id}")
        
        message_content = ""
        if config["ping"]:
            message_content = " ".join([f"<@&{role_id}>" for role_id in Config.PROTECTED_ROLE_IDS])
        
        try:
            message = await cleanup_channel.send(content=message_content, embed=embed)
            return message
        except Exception as e:
            logger.error(f"Failed to send cleanup notification: {e}")
            return None
    
    @with_error_handling
    async def send_returning_user_notification(self, member: discord.Member, user_info: Dict[str, Any]):
        """Send notification for returning inactive user"""
        admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
        if not admin_channel:
            return
        
        embed = discord.Embed(
            title="🫡 Returning Inactive User",
            description=f"{member.mention} has returned after being inactive.",
            color=0x55ff55,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="User", value=f"{member.mention}\n{member.name}", inline=True)
        embed.add_field(name="User ID", value=str(member.id), inline=True)
        
        if user_info:
            embed.add_field(name="Previously Inactive For", 
                           value=f"{user_info.get('days_inactive', 0)} days", 
                           inline=False)
            
            if user_info.get('demotion_date'):
                embed.add_field(name="Demoted On", 
                               value=user_info['demotion_date'][:10], 
                               inline=True)
        
        embed.add_field(
            name="Required Action",
            value="Please vote on whether to promote this user back to Imperius role or keep as inactive.",
            inline=False
        )
        
        embed.set_footer(text="Auto-generated by cleanup system")
        
        await admin_channel.send(
            content=" ".join([f"<@&{role_id}>" for role_id in Config.PROTECTED_ROLE_IDS]),
            embed=embed
        )
    
    @with_error_handling
    async def send_welcome_back_message(self, member: discord.Member):
        """Send welcome back message to main channel"""
        main_channel = self.bot.get_channel(Config.MAIN_CHANNEL_ID)
        if not main_channel:
            return
        
        embed = discord.Embed(
            title="👋 Welcome Back!",
            description=f"Welcome back {member.mention}! We're glad to see you again.",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Notice",
            value="Your activity has been noted. Please continue to participate in the community!",
            inline=False
        )
        
        await main_channel.send(embed=embed)
    
    @with_error_handling  
    async def create_status_dashboard(self) -> discord.Embed:
        """Create a status dashboard embed"""
        # Get stats from database
        cursor = await self.db.conn.execute('''
            SELECT 
                COUNT(*) as total_users,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_users,
                SUM(CASE WHEN status = 'inactive' THEN 1 ELSE 0 END) as inactive_users,
                SUM(CASE WHEN status = 'under_review' THEN 1 ELSE 0 END) as review_users,
                SUM(CASE WHEN status = 'kicked' THEN 1 ELSE 0 END) as kicked_users
            FROM user_activity
        ''')
        
        stats = await cursor.fetchone()
        
        # Get pending polls
        cursor = await self.db.conn.execute('''
            SELECT poll_type, COUNT(*) FROM polls 
            WHERE status = 'open' GROUP BY poll_type
        ''')
        
        poll_counts = await cursor.fetchall()
        
        # Create dashboard embed
        embed = discord.Embed(
            title="📊 Bot Status Dashboard",
            color=0x7289da,
            timestamp=datetime.utcnow()
        )
        
        # Add user statistics
        if stats:
            total, active, inactive, review, kicked = stats
            embed.add_field(
                name="👥 User Statistics",
                value=f"**Total Tracked:** {total}\n"
                      f"**Active:** {active}\n"
                      f"**Inactive:** {inactive}\n"
                      f"**Under Review:** {review}\n"
                      f"**Kicked:** {kicked}",
                inline=False
            )
        
        # Add poll statistics
        if poll_counts:
            poll_text = ""
            for poll_type, count in poll_counts:
                poll_text += f"**{poll_type.title()}:** {count}\n"
            
            embed.add_field(name="📋 Pending Polls", value=poll_text, inline=False)
        
        # Add system info
        embed.add_field(
            name="⚙️ System Settings",
            value=f"**Inactivity Warning:** {Config.INACTIVITY_WARNING_DAYS} days\n"
                  f"**Auto-demotion:** {Config.INACTIVITY_DEMOTION_DAYS} days\n"
                  f"**Daily Check:** {Config.CHECK_TIME_HOUR}:00\n"
                  f"**Poll Duration:** {Config.POLL_DURATION_HOURS} hours",
            inline=False
        )
        
        embed.set_footer(text="Bot System Dashboard")
        
        return embed
