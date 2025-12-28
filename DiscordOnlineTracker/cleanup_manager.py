import discord
import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Set
import os

class CleanupManager:
    def __init__(self, client):
        self.client = client
        
        # Channel IDs
        self.cleanup_channel_id = 1454802873300025396
        self.admin_channel_id = 1437586858417852438
        self.welcome_channel_id = 1369091668724154419
        self.call_channel_id = 1437575744824934531
        
        # Role IDs
        self.target_role_id = 1437570031822176408  # Imperius role
        self.demote_role_id = 1454803208995340328  # Demoted role
        self.admin_role_ids = [1389835747040694332, 1437578521374363769, 
                             143757291600583479, 1438420490455613540]
        
        # Files
        self.activity_file = "user_activity.json"
        self.demoted_file = "demoted_users.json"
        self.review_file = "users_under_review.json"
        
        # Tracking
        self.user_activity = self.load_activity()
        self.demoted_users = self.load_demoted()
        self.users_under_review = self.load_reviews()
        self.sent_embeds = set()
        
        # Buttons tracking
        self.active_views = {}
        
    # ========== DATA MANAGEMENT ==========
    
    def load_activity(self) -> Dict[str, Dict]:
        try:
            if os.path.exists(self.activity_file):
                with open(self.activity_file, 'r') as f:
                    data = json.load(f)
                    # Convert string dates back to datetime
                    for user_id, info in data.items():
                        if 'last_active' in info:
                            try:
                                data[user_id]['last_active'] = datetime.fromisoformat(info['last_active'])
                            except:
                                data[user_id]['last_active'] = datetime.now() - timedelta(days=30)
                    return data
        except Exception as e:
            print(f"Error loading activity: {e}")
        return {}
    
    def save_activity(self):
        try:
            # Convert datetime to string
            save_data = {}
            for user_id, info in self.user_activity.items():
                save_data[user_id] = info.copy()
                if 'last_active' in save_data[user_id] and isinstance(save_data[user_id]['last_active'], datetime):
                    save_data[user_id]['last_active'] = save_data[user_id]['last_active'].isoformat()
            
            with open(self.activity_file, 'w') as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            print(f"Error saving activity: {e}")
    
    def load_demoted(self) -> Set[str]:
        try:
            if os.path.exists(self.demoted_file):
                with open(self.demoted_file, 'r') as f:
                    return set(json.load(f))
        except:
            pass
        return set()
    
    def save_demoted(self):
        try:
            with open(self.demoted_file, 'w') as f:
                json.dump(list(self.demoted_users), f)
        except Exception as e:
            print(f"Error saving demoted users: {e}")
    
    def load_reviews(self) -> Dict[str, Dict]:
        try:
            if os.path.exists(self.review_file):
                with open(self.review_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def save_reviews(self):
        try:
            with open(self.review_file, 'w') as f:
                json.dump(self.users_under_review, f, indent=2)
        except Exception as e:
            print(f"Error saving reviews: {e}")
    
    # ========== ACTIVITY TRACKING ==========
    
    async def track_activity(self, user_id: int):
        """Track user activity"""
        try:
            uid = str(user_id)
            now = datetime.now()
            
            if uid not in self.user_activity:
                self.user_activity[uid] = {
                    'last_active': now,
                    'first_seen': now,
                    'activity_count': 0
                }
            
            self.user_activity[uid]['last_active'] = now
            self.user_activity[uid]['activity_count'] = self.user_activity[uid].get('activity_count', 0) + 1
            self.user_activity[uid]['last_update'] = now
            
            # Save every 10 updates or every hour
            if self.user_activity[uid]['activity_count'] % 10 == 0:
                self.save_activity()
                
        except Exception as e:
            print(f"Error tracking activity: {e}")
    
    def get_inactivity_days(self, user_id: int) -> int:
        """Get days since last activity"""
        uid = str(user_id)
        if uid not in self.user_activity:
            return 999
        
        last_active = self.user_activity[uid].get('last_active')
        if not last_active:
            return 999
        
        if isinstance(last_active, str):
            try:
                last_active = datetime.fromisoformat(last_active)
            except:
                return 999
        
        days_inactive = (datetime.now() - last_active).days
        return days_inactive
    
    # ========== CLEANUP CHECKS ==========
    
    async def run_cleanup_check(self):
        """Main cleanup check function"""
        try:
            guild = self.get_guild()
            if not guild:
                return
            
            await self.check_ghost_users(guild)
            await self.check_demotion_candidates(guild)
            
            # Save data
            self.save_activity()
            
        except Exception as e:
            print(f"Error in cleanup check: {e}")
    
    async def check_ghost_users(self, guild):
        """Check for users with no roles (ghosts)"""
        cleanup_channel = self.client.get_channel(self.cleanup_channel_id)
        if not cleanup_channel:
            return
        
        for member in guild.members:
            if member.bot:
                continue
            
            # Check if member only has @everyone role
            if len(member.roles) <= 1:
                days_inactive = self.get_inactivity_days(member.id)
                
                if days_inactive >= 15:
                    await self.post_ghost_embed(member, days_inactive, cleanup_channel)
    
    async def check_demotion_candidates(self, guild):
        """Check for inactive users with target role"""
        admin_channel = self.client.get_channel(self.admin_channel_id)
        if not admin_channel:
            return
        
        target_role = guild.get_role(self.target_role_id)
        if not target_role:
            return
        
        for member in target_role.members:
            if member.bot:
                continue
            
            days_inactive = self.get_inactivity_days(member.id)
            
            if days_inactive >= 15 and str(member.id) not in self.demoted_users:
                await self.post_demotion_embed(member, days_inactive, admin_channel)
    
    # ========== EMBED POSTING ==========
    
    async def post_ghost_embed(self, member, days_inactive, channel):
        """Post ghost user embed"""
        embed_id = f"ghost_{member.id}"
        if embed_id in self.sent_embeds:
            return
        
        try:
            # Get last active time
            last_active = self.user_activity.get(str(member.id), {}).get('last_active', 'Unknown')
            if isinstance(last_active, datetime):
                last_active_str = last_active.strftime('%Y-%m-%d %H:%M')
            else:
                last_active_str = str(last_active)
            
            # Create embed
            embed = discord.Embed(
                title=f"👻 Ghost User Detected",
                color=discord.Color.dark_gray(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="User ID",
                value=f"`{member.id}`",
                inline=False
            )
            
            embed.add_field(
                name="Last Active",
                value=f"`{last_active_str}`",
                inline=False
            )
            
            embed.add_field(
                name="Days Inactive",
                value=f"`{days_inactive}`",
                inline=False
            )
            
            embed.set_footer(text="Administrator action required")
            
            # Create view with buttons
            from button_views import GhostUserView
            view = GhostUserView(member, self)
            
            # Post with border formatting
            await channel.send("```" + "-" * 42 + "```")
            message = await channel.send(embed=embed, view=view)
            await channel.send("```" + "-" * 42 + "```")
            
            # Track
            self.sent_embeds.add(embed_id)
            self.active_views[message.id] = view
            
        except Exception as e:
            print(f"Error posting ghost embed: {e}")
    
    async def post_demotion_embed(self, member, days_inactive, channel):
        """Post demotion review embed"""
        embed_id = f"demote_{member.id}"
        if embed_id in self.sent_embeds:
            return
        
        try:
            # Get last active time
            last_active = self.user_activity.get(str(member.id), {}).get('last_active', 'Unknown')
            if isinstance(last_active, datetime):
                last_active_str = last_active.strftime('%Y-%m-%d %H:%M')
            else:
                last_active_str = str(last_active)
            
            # Create embed
            embed = discord.Embed(
                title=f"🔻 Demotion Review - {member.guild.name}",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="User ID",
                value=f"`{member.id}`",
                inline=False
            )
            
            embed.add_field(
                name="Last Active",
                value=f"`{last_active_str}`",
                inline=False
            )
            
            embed.add_field(
                name="Days Inactive",
                value=f"`{days_inactive}`",
                inline=False
            )
            
            embed.set_footer(text="Vote restricted to administrators")
            
            # Create view with buttons
            from button_views import DemotionReviewView
            view = DemotionReviewView(member, self)
            
            # Post with border formatting
            await channel.send("```" + "-" * 42 + "```")
            message = await channel.send(embed=embed, view=view)
            await channel.send("```" + "-" * 42 + "```")
            
            # Track
            self.sent_embeds.add(embed_id)
            self.active_views[message.id] = view
            
        except Exception as e:
            print(f"Error posting demotion embed: {e}")
    
    # ========== USER MANAGEMENT ==========
    
    async def demote_user(self, member, admin):
        """Demote user to lower role"""
        try:
            guild = member.guild
            target_role = guild.get_role(self.target_role_id)
            demote_role = guild.get_role(self.demote_role_id)
            
            if not target_role or not demote_role:
                return False, "Roles not found"
            
            # Remove target role and add demote role
            if target_role in member.roles:
                await member.remove_roles(target_role)
            
            if demote_role not in member.roles:
                await member.add_roles(demote_role)
            
            # Update tracking
            self.demoted_users.add(str(member.id))
            self.save_demoted()
            
            # Log action
            await self.log_action("demote", member, admin, member.guild.name)
            
            # Remove from sent embeds
            embed_id = f"demote_{member.id}"
            if embed_id in self.sent_embeds:
                self.sent_embeds.remove(embed_id)
            
            return True, f"Demoted {member.display_name} successfully"
            
        except Exception as e:
            return False, f"Error demoting user: {str(e)}"
    
    async def promote_user(self, member, admin):
        """Promote user back to original role"""
        try:
            guild = member.guild
            target_role = guild.get_role(self.target_role_id)
            demote_role = guild.get_role(self.demote_role_id)
            
            if not target_role or not demote_role:
                return False, "Roles not found"
            
            # Remove demote role and add target role
            if demote_role in member.roles:
                await member.remove_roles(demote_role)
            
            if target_role not in member.roles:
                await member.add_roles(target_role)
            
            # Update tracking
            if str(member.id) in self.demoted_users:
                self.demoted_users.remove(str(member.id))
                self.save_demoted()
            
            # Log action
            await self.log_action("promote", member, admin, member.guild.name)
            
            return True, f"Promoted {member.display_name} successfully"
            
        except Exception as e:
            return False, f"Error promoting user: {str(e)}"
    
    async def kick_user(self, member, admin):
        """Kick user from server"""
        try:
            await member.kick(reason=f"Inactivity cleanup - Action by {admin.display_name}")
            
            # Log action
            await self.log_action("kick", member, admin, member.guild.name)
            
            # Clean up tracking
            uid = str(member.id)
            if uid in self.user_activity:
                del self.user_activity[uid]
                self.save_activity()
            
            if uid in self.demoted_users:
                self.demoted_users.remove(uid)
                self.save_demoted()
            
            return True, f"Kicked {member.display_name} successfully"
            
        except Exception as e:
            return False, f"Error kicking user: {str(e)}"
    
    # ========== RETURNING USER HANDLING ==========
    
    async def handle_user_return(self, member):
        """Handle when a demoted user returns online"""
        try:
            # Check if user is demoted
            if str(member.id) not in self.demoted_users:
                return
            
            # Send welcome message
            welcome_channel = self.client.get_channel(self.welcome_channel_id)
            if welcome_channel:
                embed = discord.Embed(
                    title="Welcome Back!",
                    description=f"**{member.guild.name}**",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Message",
                    value="You were demoted due to inactivity\nI'll notify the admins about you",
                    inline=False
                )
                
                await welcome_channel.send(f"Welcome back! {member.mention}", embed=embed)
            
            # Notify admin channel
            await self.notify_admin_user_returned(member)
            
        except Exception as e:
            print(f"Error handling user return: {e}")
    
    async def notify_admin_user_returned(self, member):
        """Notify admins that a demoted user returned"""
        admin_channel = self.client.get_channel(self.admin_channel_id)
        if not admin_channel:
            return
        
        try:
            days_inactive = self.get_inactivity_days(member.id)
            
            embed = discord.Embed(
                title=f"🟢 {member.guild.name} came back online!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="User",
                value=f"<@{member.id}>",
                inline=False
            )
            
            embed.add_field(
                name="Days Inactive",
                value=f"`{days_inactive}`",
                inline=False
            )
            
            embed.set_footer(text="Review required")
            
            from button_views import ReturnReviewView
            view = ReturnReviewView(member, self)
            
            await admin_channel.send("```" + "-" * 48 + "```")
            message = await admin_channel.send(embed=embed, view=view)
            await admin_channel.send("```" + "-" * 48 + "```")
            
            self.active_views[message.id] = view
            
        except Exception as e:
            print(f"Error notifying admin: {e}")
    
    async def put_user_under_review(self, member):
        """Put user under formal review"""
        admin_channel = self.client.get_channel(self.admin_channel_id)
        if not admin_channel:
            return
        
        try:
            days_inactive = self.get_inactivity_days(member.id)
            
            embed = discord.Embed(
                title=f"🟢 {member.guild.name} is under review",
                color=discord.Color.yellow(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="User",
                value=f"<@{member.id}>",
                inline=False
            )
            
            embed.add_field(
                name="Days Inactive",
                value=f"`{days_inactive}`",
                inline=False
            )
            
            embed.add_field(
                name="Final Decision",
                value="⚖️",
                inline=False
            )
            
            from button_views import FinalReviewView
            view = FinalReviewView(member, self)
            
            await admin_channel.send("```" + "-" * 48 + "```")
            message = await admin_channel.send(embed=embed, view=view)
            await admin_channel.send("```" + "-" * 48 + "```")
            
            self.users_under_review[str(member.id)] = {
                'started': datetime.now().isoformat(),
                'reviewer': None
            }
            self.save_reviews()
            
            self.active_views[message.id] = view
            
        except Exception as e:
            print(f"Error putting user under review: {e}")
    
    # ========== ACTION LOGGING ==========
    
    async def log_action(self, action_type, member, admin, server_name):
        """Log admin action"""
        admin_channel = self.client.get_channel(self.admin_channel_id)
        if not admin_channel:
            return
        
        try:
            # Get role name based on action
            if action_type == "demote":
                role_name = "Demote Role"
            elif action_type == "promote":
                role_name = "Imperius Role"
            elif action_type == "kick":
                role_name = "No Role"
            else:
                role_name = "Unknown Role"
            
            embed = discord.Embed(
                title=f"⚖️ {role_name} {server_name}",
                description=f"Order the {action_type} of <@{member.id}>",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.set_footer(text=f"Action by {admin.display_name}")
            
            await admin_channel.send("```" + "-" * 42 + "```")
            await admin_channel.send(embed=embed)
            await admin_channel.send("```" + "-" * 42 + "```")
            
        except Exception as e:
            print(f"Error logging action: {e}")
    
    # ========== UTILITY ==========
    
    def get_guild(self):
        """Get main guild"""
        if self.client.guilds:
            return self.client.guilds[0]
        return None
    
    def is_admin(self, member):
        """Check if member is admin"""
        if not member:
            return False
        
        member_role_ids = [role.id for role in member.roles]
        return any(role_id in member_role_ids for role_id in self.admin_role_ids)
    
    def cleanup_old_views(self):
        """Clean up old views"""
        current_time = time.time()
        to_remove = []
        
        for message_id, view in self.active_views.items():
            if view.is_finished():
                to_remove.append(message_id)
        
        for message_id in to_remove:
            del self.active_views[message_id]
