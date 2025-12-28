# modules/poll_manager.py - Poll-based voting system ...
import discord
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from utils.logger import logger
from utils.error_handler import with_error_handling
from config import Config

class PollManager:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.active_polls = {}
    
    async def initialize(self):
        """Initialize poll manager"""
        logger.info("Poll manager initialized")
    
    @with_error_handling
    async def create_poll(self, ctx, question: str, options: List[str], 
                         duration_hours: int = None, poll_type: str = "general") -> Optional[discord.Message]:
        """Create a general poll"""
        if duration_hours is None:
            duration_hours = Config.POLL_DURATION_HOURS
        
        if len(options) < 2 or len(options) > 5:
            await ctx.send("❌ Polls must have between 2 and 5 options.")
            return None
        
        # Create poll
        try:
            poll_message = await ctx.send(
                poll=discord.Poll(
                    question=question,
                    answers=[discord.PollAnswer(text=opt) for opt in options],
                    duration=timedelta(hours=duration_hours),
                    allow_multiselect=False
                )
            )
            
            # Store in database
            expires_at = (datetime.utcnow() + timedelta(hours=duration_hours)).isoformat()
            
            await self.db.conn.execute('''
                INSERT INTO polls (poll_id, message_id, channel_id, creator_id, 
                                  question, poll_type, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (poll_message.id, poll_message.id, ctx.channel.id, 
                  ctx.author.id, question, poll_type, expires_at))
            
            await self.db.conn.commit()
            
            # Add to active polls
            self.active_polls[poll_message.id] = {
                'message_id': poll_message.id,
                'channel_id': ctx.channel.id,
                'question': question,
                'expires_at': expires_at,
                'type': poll_type
            }
            
            # Add admin notice for responsibility
            if poll_type in ['cleanup', 'inactive', 'review']:
                await self._add_admin_notice(ctx, poll_message)
            
            logger.info(f"Poll created: {question} by {ctx.author}")
            return poll_message
            
        except discord.HTTPException as e:
            logger.error(f"Failed to create poll: {e}")
            await ctx.send("❌ Failed to create poll. Please check bot permissions.")
            return None
    
    @with_error_handling
    async def create_cleanup_poll(self, channel, member, poll_type: str = "ghost") -> Optional[discord.Message]:
        """Create a cleanup decision poll"""
        
        # Poll configuration based on type
        poll_configs = {
            "ghost": {
                "emoji": "👻",
                "question": f"Ghost User: {member.display_name}",
                "options": [
                    f"Kick {member.display_name}",
                    f"Promote to <@&{Config.IMPERIUS_ROLE_ID}>",
                    "Review (manual decision)"
                ],
                "color": 0xff5555
            },
            "inactive": {
                "emoji": "😴", 
                "question": f"Inactive User: {member.display_name}",
                "options": [
                    f"Demote to <@&{Config.INACTIVE_ROLE_ID}>",
                    "Keep current role",
                    "Review (manual decision)"
                ],
                "color": 0xffaa00
            },
            "returning": {
                "emoji": "🫡",
                "question": f"Returning User: {member.display_name}",
                "options": [
                    f"Promote to <@&{Config.IMPERIUS_ROLE_ID}>",
                    "Review (interview required)",
                    "Keep as inactive"
                ],
                "color": 0x55ff55
            },
            "review": {
                "emoji": "🔍",
                "question": f"Under Review: {member.display_name}",
                "options": [
                    f"Promote to <@&{Config.IMPERIUS_ROLE_ID}>",
                    "Kick from server",
                    "Extend review period"
                ],
                "color": 0x5555ff
            }
        }
        
        config = poll_configs.get(poll_type, poll_configs["ghost"])
        
        # Get user info for details
        user_info = await self.db.get_user_info(member.id)
        days_inactive = user_info['days_inactive'] if user_info else 0
        
        # Create embed with details
        embed = discord.Embed(
            title=f"{config['emoji']} {member.display_name}",
            description=f"**User:** {member.mention} ({member.id})\n"
                       f"**Status:** {poll_type.title()}\n"
                       f"**Inactive for:** {days_inactive} days\n"
                       f"**Account created:** {member.created_at.strftime('%Y-%m-%d')}",
            color=config['color']
        )
        
        if user_info and user_info['last_active']:
            embed.add_field(
                name="Last Active",
                value=user_info['last_active'][:10],
                inline=True
            )
        
        embed.add_field(
            name="Server Join Date",
            value=member.joined_at.strftime('%Y-%m-%d') if member.joined_at else "Unknown",
            inline=True
        )
        
        embed.set_footer(text="Vote ends in 24 hours • Single vote required")
        embed.timestamp = datetime.utcnow()
        
        # Send embed first
        await channel.send(embed=embed)
        
        # Create the poll
        poll = await self.create_poll(
            ctx=await self.bot.get_context(await channel.send("Creating poll...")),
            question=config['question'],
            options=config['options'],
            poll_type=poll_type
        )
        
        if poll:
            # Update database with target user
            await self.db.conn.execute('''
                UPDATE polls SET notes = ? WHERE poll_id = ?
            ''', (f"target_user:{member.id}", poll.id))
            await self.db.conn.commit()
            
            # Log the poll creation
            await self.db.log_cleanup_action(
                user_id=member.id,
                action_type=f"poll_created_{poll_type}",
                reason=f"Poll created for decision"
            )
        
        return poll
    
    @with_error_handling
    async def create_urgent_poll(self, ctx, question: str, options: List[str]) -> Optional[discord.Message]:
        """Create an urgent poll with shorter duration"""
        # Send TTS announcement
        await ctx.send(
            f"🚨 **URGENT VOTE REQUIRED** 🚨\n"
            f"{question}\n"
            f"All admins please vote immediately!",
            tts=True
        )
        
        # Create poll with short duration
        poll = await self.create_poll(
            ctx=ctx,
            question=f"🚨 URGENT: {question}",
            options=options,
            duration_hours=Config.URGENT_POLL_HOURS,
            poll_type="urgent"
        )
        
        # Ping online admins
        if poll:
            await self._ping_online_admins(ctx, question)
        
        return poll
    
    async def _ping_online_admins(self, ctx, question):
        """Ping online admins for urgent votes"""
        guild = ctx.guild
        admin_role_ids = Config.PROTECTED_ROLE_IDS
        
        online_admins = []
        for member in guild.members:
            if any(role.id in admin_role_ids for role in member.roles):
                if member.status != discord.Status.offline:
                    online_admins.append(member)
        
        # Send DM to online admins
        for admin in online_admins[:10]:  # Limit to 10 to avoid rate limits
            try:
                await admin.send(
                    f"🚨 **Urgent Vote Required**\n"
                    f"Server: {guild.name}\n"
                    f"Question: {question}\n"
                    f"Channel: {ctx.channel.mention}\n\n"
                    f"Please vote immediately!"
                )
            except:
                pass  # Can't DM this user
    
    async def _add_admin_notice(self, ctx, poll_message):
        """Add admin responsibility notice"""
        notice = await ctx.send(
            f"**📢 ADMIN NOTICE**\n"
            f"Poll: {poll_message.jump_url}\n\n"
            f"⚠️ **Important:**\n"
            f"• Only 1 vote per admin required\n"
            f"• By voting, you accept responsibility for the decision\n"
            f"• Decision will be implemented based on majority vote\n\n"
            f"Please cast your vote carefully."
        )
        
        # Pin the notice
        try:
            await notice.pin()
        except:
            pass  # Can't pin, no problem
    
    @with_error_handling
    async def process_poll_results(self, poll_id: int, results: Dict[str, int]) -> Optional[str]:
        """Process poll results and return winning option"""
        if not results:
            return None
        
        # Get the winning option (most votes)
        winning_option = max(results.items(), key=lambda x: x[1])
        
        # Update poll status in database
        await self.db.conn.execute('''
            UPDATE polls 
            SET status = 'closed', result = ?
            WHERE poll_id = ?
        ''', (winning_option[0], poll_id))
        
        await self.db.conn.commit()
        
        # Remove from active polls
        if poll_id in self.active_polls:
            del self.active_polls[poll_id]
        
        return winning_option[0]
    
    @with_error_handling
    async def archive_old_polls(self):
        """Archive polls older than 7 days"""
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        await self.db.conn.execute('''
            UPDATE polls 
            SET status = 'archived' 
            WHERE status = 'closed' 
            AND created_at < ?
        ''', (cutoff,))
        
        await self.db.conn.commit()
        
        logger.info("Old polls archived")
    
    def get_active_polls(self) -> Dict[int, Dict[str, Any]]:
        """Get all active polls"""
        return self.active_polls.copy()
