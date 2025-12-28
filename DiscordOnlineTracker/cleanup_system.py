"""
Cleanup System Module for Discord Bot
Handles inactive user detection, demotion/promotion, and user tracking
"""

import discord
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Set, List, Optional
import time

class CleanupSystem:
    """Main cleanup system for managing inactive users"""
    
    def __init__(self, client, config: dict):
        """
        Initialize cleanup system
        
        Args:
            client: Discord client instance
            config: Configuration dictionary
        """
        self.client = client
        self.config = config
        
        # Load configuration
        self.channels = config.get('channels', {})
        self.roles = config.get('roles', {})
        self.admin_roles = config.get('admin_roles', [])
        
        # Files for persistence
        self.data_dir = "data"
        self.activity_file = os.path.join(self.data_dir, "user_activity.json")
        self.demoted_file = os.path.join(self.data_dir, "demoted_users.json")
        self.review_file = os.path.join(self.data_dir, "users_under_review.json")
        self.sent_embeds_file = os.path.join(self.data_dir, "sent_embeds.json")
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Data storage
        self.user_activity: Dict[str, Dict] = {}
        self.demoted_users: Set[str] = set()
        self.users_under_review: Dict[str, Dict] = {}
        self.sent_cleanup_embeds: Set[str] = set()
        self.sent_demotion_embeds: Set[str] = set()
        
        # Load data
        self.load_all_data()
        
        # Active polls tracking
        self.active_polls: Dict[str, Dict] = {}
        
        # Error tracking
        self.error_count = 0
        self.last_error_time = 0
        
        print(f"✅ Cleanup System initialized. Tracking {len(self.user_activity)} users.")
    
    # ========== DATA PERSISTENCE ==========
    
    def load_all_data(self):
        """Load all data from files"""
        try:
            self.user_activity = self._load_json(self.activity_file, {})
            
            # Convert string dates to datetime objects
            for user_id, data in self.user_activity.items():
                if 'last_active' in data and isinstance(data['last_active'], str):
                    try:
                        self.user_activity[user_id]['last_active'] = datetime.fromisoformat(data['last_active'])
                    except:
                        self.user_activity[user_id]['last_active'] = datetime.now() - timedelta(days=30)
            
            self.demoted_users = set(self._load_json(self.demoted_file, []))
            self.users_under_review = self._load_json(self.review_file, {})
            
            sent_data = self._load_json(self.sent_embeds_file, {})
            self.sent_cleanup_embeds = set(sent_data.get('cleanup', []))
            self.sent_demotion_embeds = set(sent_data.get('demotion', []))
            
        except Exception as e:
            print(f"⚠️ Error loading cleanup data: {e}")
            # Initialize empty data on error
            self.user_activity = {}
            self.demoted_users = set()
            self.users_under_review = {}
            self.sent_cleanup_embeds = set()
            self.sent_demotion_embeds = set()
    
    def save_all_data(self):
        """Save all data to files"""
        try:
            # Convert datetime to string for JSON
            activity_to_save = {}
            for user_id, data in self.user_activity.items():
                activity_to_save[user_id] = data.copy()
                if 'last_active' in activity_to_save[user_id] and isinstance(activity_to_save[user_id]['last_active'], datetime):
                    activity_to_save[user_id]['last_active'] = activity_to_save[user_id]['last_active'].isoformat()
            
            self._save_json(self.activity_file, activity_to_save)
            self._save_json(self.demoted_file, list(self.demoted_users))
            self._save_json(self.review_file, self.users_under_review)
            
            sent_data = {
                'cleanup': list(self.sent_cleanup_embeds),
                'demotion': list(self.sent_demotion_embeds)
            }
            self._save_json(self.sent_embeds_file, sent_data)
            
        except Exception as e:
            print(f"⚠️ Error saving cleanup data: {e}")
    
    def _load_json(self, filepath: str, default):
        """Load JSON file with error handling"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading {filepath}: {e}")
        return default
    
    def _save_json(self, filepath: str, data):
        """Save JSON file with error handling"""
        try:
            # Save to temp file first, then rename (atomic operation)
            temp_file = filepath + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Replace original file
            if os.path.exists(filepath):
                os.remove(filepath)
            os.rename(temp_file, filepath)
            
        except Exception as e:
            print(f"⚠️ Error saving {filepath}: {e}")
    
    # ========== USER ACTIVITY TRACKING ==========
    
    async def track_user_activity(self, user_id: int, activity_type: str = "general"):
        """
        Track user activity
        
        Args:
            user_id: Discord user ID
            activity_type: Type of activity (message, presence, voice, etc.)
        """
        try:
            uid = str(user_id)
            now = datetime.now()
            
            if uid not in self.user_activity:
                self.user_activity[uid] = {
                    'last_active': now,
                    'first_seen': now,
                    'total_activities': 0,
                    'activity_types': {},
                    'status_history': []
                }
            
            # Update last activity
            self.user_activity[uid]['last_active'] = now
            self.user_activity[uid]['total_activities'] = self.user_activity[uid].get('total_activities', 0) + 1
            
            # Track activity type
            activity_types = self.user_activity[uid].get('activity_types', {})
            activity_types[activity_type] = activity_types.get(activity_type, 0) + 1
            self.user_activity[uid]['activity_types'] = activity_types
            
            # Keep only recent status history (last 50 entries)
            status_entry = {
                'time': now.isoformat(),
                'type': activity_type
            }
            self.user_activity[uid].setdefault('status_history', []).append(status_entry)
            if len(self.user_activity[uid]['status_history']) > 50:
                self.user_activity[uid]['status_history'] = self.user_activity[uid]['status_history'][-50:]
            
            # Auto-save every 100 updates
            if self.user_activity[uid]['total_activities'] % 100 == 0:
                self.save_all_data()
                
        except Exception as e:
            self._handle_error("track_user_activity", e)
    
    def get_inactivity_days(self, user_id: int) -> int:
        """
        Get days since last activity
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Number of days inactive
        """
        try:
            uid = str(user_id)
            if uid not in self.user_activity:
                return 999  # Never tracked
            
            last_active = self.user_activity[uid].get('last_active')
            if not last_active:
                return 999
            
            if isinstance(last_active, str):
                try:
                    last_active = datetime.fromisoformat(last_active)
                except:
                    return 999
            
            days_inactive = (datetime.now() - last_active).days
            return max(0, days_inactive)  # Ensure non-negative
            
        except Exception as e:
            self._handle_error("get_inactivity_days", e)
            return 999
    
    def get_user_info(self, user_id: int) -> Dict:
        """Get comprehensive user info"""
        uid = str(user_id)
        if uid not in self.user_activity:
            return {'status': 'unknown', 'days_inactive': 999}
        
        days_inactive = self.get_inactivity_days(user_id)
        
        info = {
            'days_inactive': days_inactive,
            'total_activities': self.user_activity[uid].get('total_activities', 0),
            'last_active': self.user_activity[uid].get('last_active'),
            'is_demoted': uid in self.demoted_users,
            'under_review': uid in self.users_under_review
        }
        
        return info
    
    # ========== INACTIVE USER DETECTION ==========
    
    async def run_cleanup_check(self, guild: discord.Guild):
        """
        Run cleanup check for inactive users
        
        Args:
            guild: Discord guild to check
        """
        try:
            # Rate limiting check
            if not self._can_execute_cleanup():
                return
            
            print(f"🔍 Running cleanup check for {guild.name}...")
            
            # Get channels
            cleanup_channel = guild.get_channel(self.channels.get('cleanup'))
            admin_channel = guild.get_channel(self.channels.get('admin'))
            
            if not cleanup_channel or not admin_channel:
                print("⚠️ Cleanup or admin channel not found")
                return
            
            # Check all non-bot members
            checked_users = 0
            for member in guild.members:
                if member.bot:
                    continue
                
                checked_users += 1
                await self._check_member_inactivity(member, cleanup_channel, admin_channel)
                
                # Small delay to prevent rate limiting
                if checked_users % 50 == 0:
                    await asyncio.sleep(0.1)
            
            # Save data after check
            self.save_all_data()
            
            print(f"✅ Cleanup check completed. Checked {checked_users} users.")
            
        except Exception as e:
            self._handle_error("run_cleanup_check", e)
    
    async def _check_member_inactivity(self, member: discord.Member, 
                                      cleanup_channel: discord.TextChannel,
                                      admin_channel: discord.TextChannel):
        """Check individual member inactivity"""
        try:
            days_inactive = self.get_inactivity_days(member.id)
            
            # Check roles
            has_roles = len(member.roles) > 1  # More than just @everyone
            has_target_role = any(role.id == self.roles.get('imperius') for role in member.roles)
            is_demoted = str(member.id) in self.demoted_users
            
            # Ghost users (no roles) with 15+ days inactive
            if not has_roles and days_inactive >= 15:
                await self._handle_ghost_user(member, days_inactive, cleanup_channel)
            
            # Users with target role, 15+ days inactive, not already demoted
            elif has_target_role and days_inactive >= 15 and not is_demoted:
                await self._handle_demotion_candidate(member, days_inactive, admin_channel)
                
        except Exception as e:
            print(f"⚠️ Error checking member {member.id}: {e}")
    
    async def _handle_ghost_user(self, member: discord.Member, days_inactive: int, 
                                channel: discord.TextChannel):
        """Handle ghost user (no roles)"""
        embed_id = f"ghost_{member.id}"
        if embed_id in self.sent_cleanup_embeds:
            return
        
        try:
            # Import here to avoid circular imports
            from modules.button_views import GhostUserView
            
            # Get last active time
            last_active = self.user_activity.get(str(member.id), {}).get('last_active', 'Unknown')
            if isinstance(last_active, datetime):
                last_active_str = last_active.strftime('%Y-%m-%d %H:%M UTC')
            else:
                last_active_str = str(last_active)
            
            # Create formatted message
            border = "-" * 43
            message_content = (
                f"```\n{border}\n"
                f"| 👻 {str(member.id).ljust(36)} |\n"
                f"|   Last active: {last_active_str:<22} |\n"
                f"|   Days inactive: {days_inactive:<21} |\n"
                f"|                                          |\n"
                f"| [KICK BUTTON]                           |\n"
                f"{border}\n```"
            )
            
            view = GhostUserView(member, self)
            await channel.send(message_content, view=view)
            
            self.sent_cleanup_embeds.add(embed_id)
            self.save_all_data()
            
        except Exception as e:
            print(f"⚠️ Error handling ghost user {member.id}: {e}")
    
    async def _handle_demotion_candidate(self, member: discord.Member, days_inactive: int,
                                       channel: discord.TextChannel):
        """Handle demotion candidate"""
        embed_id = f"demote_{member.id}"
        if embed_id in self.sent_demotion_embeds:
            return
        
        try:
            from modules.button_views import DemotionReviewView
            
            # Get last active time
            last_active = self.user_activity.get(str(member.id), {}).get('last_active', 'Unknown')
            if isinstance(last_active, datetime):
                last_active_str = last_active.strftime('%Y-%m-%d %H:%M UTC')
            else:
                last_active_str = str(last_active)
            
            # Create formatted message
            border = "-" * 43
            message_content = (
                f"```\n{border}\n"
                f"| 🔻 {member.guild.name.ljust(36)} |\n"
                f"|   Last active: {last_active_str:<22} |\n"
                f"|   Days inactive: {days_inactive:<21} |\n"
                f"|                                          |\n"
                f"| [DEMOTE BUTTON]  [KICK BUTTON]         |\n"
                f"{border}\n```"
            )
            
            view = DemotionReviewView(member, self)
            await channel.send(message_content, view=view)
            
            self.sent_demotion_embeds.add(embed_id)
            self.save_all_data()
            
        except Exception as e:
            print(f"⚠️ Error handling demotion candidate {member.id}: {e}")
    
    # ========== USER MANAGEMENT ==========
    
    async def demote_user(self, member: discord.Member, admin: discord.Member) -> tuple[bool, str]:
        """Demote user to lower role"""
        try:
            target_role = member.guild.get_role(self.roles.get('imperius'))
            demote_role = member.guild.get_role(self.roles.get('demoted'))
            
            if not target_role or not demote_role:
                return False, "Required roles not found"
            
            # Check bot permissions
            bot_member = member.guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.manage_roles:
                return False, "Bot lacks manage_roles permission"
            
            # Role hierarchy check
            if target_role.position >= bot_member.top_role.position:
                return False, "Bot's role is not high enough to modify target role"
            
            # Perform demotion
            if target_role in member.roles:
                await member.remove_roles(target_role)
            
            if demote_role not in member.roles:
                await member.add_roles(demote_role)
            
            # Update tracking
            self.demoted_users.add(str(member.id))
            
            # Remove from sent embeds
            embed_id = f"demote_{member.id}"
            if embed_id in self.sent_demotion_embeds:
                self.sent_demotion_embeds.remove(embed_id)
            
            # Log action
            await self._log_admin_action("demote", member, admin)
            
            self.save_all_data()
            return True, f"✅ Demoted {member.display_name} to demoted role"
            
        except discord.Forbidden:
            return False, "❌ Bot lacks permissions"
        except discord.HTTPException as e:
            return False, f"❌ Discord API error: {e}"
        except Exception as e:
            self._handle_error("demote_user", e)
            return False, f"❌ Error: {str(e)[:100]}"
    
    async def promote_user(self, member: discord.Member, admin: discord.Member) -> tuple[bool, str]:
        """Promote user back to original role"""
        try:
            target_role = member.guild.get_role(self.roles.get('imperius'))
            demote_role = member.guild.get_role(self.roles.get('demoted'))
            
            if not target_role or not demote_role:
                return False, "Required roles not found"
            
            # Check bot permissions
            bot_member = member.guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.manage_roles:
                return False, "Bot lacks manage_roles permission"
            
            # Perform promotion
            if demote_role in member.roles:
                await member.remove_roles(demote_role)
            
            if target_role not in member.roles:
                await member.add_roles(target_role)
            
            # Update tracking
            if str(member.id) in self.demoted_users:
                self.demoted_users.remove(str(member.id))
            
            # Log action
            await self._log_admin_action("promote", member, admin)
            
            self.save_all_data()
            return True, f"✅ Promoted {member.display_name} back to imperius role"
            
        except discord.Forbidden:
            return False, "❌ Bot lacks permissions"
        except discord.HTTPException as e:
            return False, f"❌ Discord API error: {e}"
        except Exception as e:
            self._handle_error("promote_user", e)
            return False, f"❌ Error: {str(e)[:100]}"
    
    async def kick_user(self, member: discord.Member, admin: discord.Member) -> tuple[bool, str]:
        """Kick user from server"""
        try:
            # Check bot permissions
            bot_member = member.guild.get_member(self.client.user.id)
            if not bot_member.guild_permissions.kick_members:
                return False, "Bot lacks kick_members permission"
            
            # Hierarchy check
            if member.top_role.position >= bot_member.top_role.position:
                return False, "Cannot kick user with higher or equal role"
            
            # Perform kick
            await member.kick(reason=f"Inactivity cleanup - Action by {admin.display_name}")
            
            # Clean up tracking data
            uid = str(member.id)
            if uid in self.user_activity:
                del self.user_activity[uid]
            
            if uid in self.demoted_users:
                self.demoted_users.remove(uid)
            
            if uid in self.users_under_review:
                del self.users_under_review[uid]
            
            # Remove from sent embeds
            ghost_id = f"ghost_{member.id}"
            demote_id = f"demote_{member.id}"
            self.sent_cleanup_embeds.discard(ghost_id)
            self.sent_demotion_embeds.discard(demote_id)
            
            # Log action
            await self._log_admin_action("kick", member, admin)
            
            self.save_all_data()
            return True, f"✅ Kicked {member.display_name}"
            
        except discord.Forbidden:
            return False, "❌ Bot lacks permissions"
        except discord.HTTPException as e:
            return False, f"❌ Discord API error: {e}"
        except Exception as e:
            self._handle_error("kick_user", e)
            return False, f"❌ Error: {str(e)[:100]}"
    
    # ========== RETURNING USER HANDLING ==========
    
    async def handle_user_return(self, member: discord.Member):
        """Handle when a demoted user returns online"""
        try:
            # Check if user is demoted
            if str(member.id) not in self.demoted_users:
                return
            
            # Send welcome message
            welcome_channel = member.guild.get_channel(self.channels.get('welcome'))
            if welcome_channel:
                embed = discord.Embed(
                    title="Welcome Back!",
                    description=f"**{member.guild.name}**",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                days_inactive = self.get_inactivity_days(member.id)
                
                embed.add_field(
                    name="Message",
                    value="You were demoted due to inactivity\nI'll notify the admins about you",
                    inline=False
                )
                
                embed.add_field(
                    name="Days Inactive",
                    value=f"{days_inactive} days",
                    inline=False
                )
                
                embed.set_footer(text="Please wait for admin review")
                
                await welcome_channel.send(f"Welcome back! {member.mention}", embed=embed)
            
            # Notify admin channel
            await self._notify_admin_user_returned(member)
            
        except Exception as e:
            self._handle_error("handle_user_return", e)
    
    async def _notify_admin_user_returned(self, member: discord.Member):
        """Notify admins that a demoted user returned"""
        try:
            admin_channel = member.guild.get_channel(self.channels.get('admin'))
            if not admin_channel:
                return
            
            days_inactive = self.get_inactivity_days(member.id)
            
            from modules.button_views import ReturnReviewView
            
            # Create formatted message
            border = "-" * 48
            message_content = (
                f"```\n{border}\n"
                f"| 🟢 {member.guild.name} came back online!{' ' * 15}|\n"
                f"|                                              |\n"
                f"|   Days inactive: {days_inactive:<28} |\n"
                f"|                                              |\n"
                f"| [PROMOTE BUTTON] [REVIEW BUTTON]            |\n"
                f"{border}\n```"
            )
            
            view = ReturnReviewView(member, self)
            await admin_channel.send(message_content, view=view)
            
        except Exception as e:
            self._handle_error("_notify_admin_user_returned", e)
    
    async def put_user_under_review(self, member: discord.Member):
        """Put user under formal review"""
        try:
            admin_channel = member.guild.get_channel(self.channels.get('admin'))
            if not admin_channel:
                return
            
            days_inactive = self.get_inactivity_days(member.id)
            
            from modules.button_views import FinalReviewView
            
            # Create formatted message
            border = "-" * 48
            message_content = (
                f"```\n{border}\n"
                f"| 🟢 {member.guild.name} is under review{' ' * 18}|\n"
                f"|                                              |\n"
                f"|   Days inactive: {days_inactive:<28} |\n"
                f"|   Final decision: ⚖️{' ' * 28}|\n"
                f"|                                              |\n"
                f"| [PROMOTE BUTTON] [KICK BUTTON]              |\n"
                f"{border}\n```"
            )
            
            view = FinalReviewView(member, self)
            await admin_channel.send(message_content, view=view)
            
            # Track review
            self.users_under_review[str(member.id)] = {
                'started': datetime.now().isoformat(),
                'guild_id': member.guild.id,
                'days_inactive': days_inactive
            }
            
            self.save_all_data()
            
        except Exception as e:
            self._handle_error("put_user_under_review", e)
    
    # ========== ACTION LOGGING ==========
    
    async def _log_admin_action(self, action_type: str, member: discord.Member, 
                               admin: discord.Member):
        """Log admin action"""
        try:
            admin_channel = member.guild.get_channel(self.channels.get('admin'))
            if not admin_channel:
                return
            
            # Get role name based on action
            role_names = {
                "demote": "Demote Role",
                "promote": "Imperius Role",
                "kick": "No Role",
                "keep": "Imperius Role"
            }
            
            role_name = role_names.get(action_type, "Unknown Role")
            
            # Create formatted message
            border = "-" * 42
            message_content = (
                f"```\n{border}\n"
                f"| ⚖️ {role_name} {member.guild.name.ljust(25)} |\n"
                f"| Order the {action_type} of {str(member.id).ljust(16)} |\n"
                f"{border}\n```"
            )
            
            await admin_channel.send(message_content)
            
        except Exception as e:
            print(f"⚠️ Error logging action: {e}")
    
    # ========== UTILITY FUNCTIONS ==========
    
    def is_admin(self, member: discord.Member) -> bool:
        """Check if member is admin"""
        if not member:
            return False
        
        member_role_ids = [role.id for role in member.roles]
        return any(role_id in member_role_ids for role_id in self.admin_roles)
    
    def _can_execute_cleanup(self) -> bool:
        """Check if cleanup can be executed (rate limiting)"""
        current_time = time.time()
        
        # If too many errors recently, wait
        if self.error_count >= 5 and current_time - self.last_error_time < 300:  # 5 errors in 5 minutes
            return False
        
        return True
    
    def _handle_error(self, context: str, error: Exception):
        """Handle errors with rate limiting"""
        self.error_count += 1
        self.last_error_time = time.time()
        
        # Reset error count after 1 hour
        if time.time() - self.last_error_time > 3600:
            self.error_count = 0
        
        error_msg = f"⚠️ CleanupSystem error in {context}: {type(error).__name__}: {str(error)[:200]}"
        print(error_msg)
        
        # Log to file
        try:
            with open(os.path.join(self.data_dir, "cleanup_errors.log"), "a") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {context}: {error}\n")
        except:
            pass
    
    async def cleanup_old_data(self):
        """Clean up old tracking data"""
        try:
            cutoff_date = datetime.now() - timedelta(days=90)  # 90 days retention
            
            # Clean old user activity
            to_remove = []
            for user_id, data in self.user_activity.items():
                last_active = data.get('last_active')
                if isinstance(last_active, datetime) and last_active < cutoff_date:
                    to_remove.append(user_id)
            
            for user_id in to_remove:
                del self.user_activity[user_id]
            
            # Clean old sent embeds (older than 30 days)
            self.sent_cleanup_embeds = set()
            self.sent_demotion_embeds = set()
            
            # Clean old reviews (older than 7 days)
            to_remove = []
            for user_id, review_data in self.users_under_review.items():
                started = review_data.get('started')
                if started:
                    try:
                        review_date = datetime.fromisoformat(started)
                        if review_date < datetime.now() - timedelta(days=7):
                            to_remove.append(user_id)
                    except:
                        pass
            
            for user_id in to_remove:
                del self.users_under_review[user_id]
            
            self.save_all_data()
            print(f"🧹 Cleaned up {len(to_remove)} old entries")
            
        except Exception as e:
            self._handle_error("cleanup_old_data", e)
