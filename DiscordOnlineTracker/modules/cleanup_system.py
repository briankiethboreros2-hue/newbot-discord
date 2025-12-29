import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
from typing import Dict, List, Optional
import aiohttp
from button_views import (
    GhostUserVoteView, 
    DemotionVoteView, 
    DemotedUserActionView,
    UnderReviewVoteView
)

class CleanupSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ghost_users = {}  # user_id: join_date
        self.demotion_candidates = {}  # user_id: last_active_date
        self.demoted_users = {}  # user_id: demotion_date
        self.under_review = {}  # user_id: review_start_date
        self.user_last_active = {}  # user_id: last_activity_datetime
        
        # Role IDs
        self.VERIFIED_ROLE_ID = 1437570031822176408
        self.INACTIVE_ROLE_ID = 1454803208995340328
        
        # Channel IDs
        self.ADMIN_CHANNEL_ID = 1455138098437689387
        self.CLEANUP_CHANNEL_ID = 1454802873300025396
        self.GREET_CHANNEL_ID = 1369091668724154419
        
        # Admin role IDs (can vote)
        self.ADMIN_ROLES = [
            1437572916005834793,
            1437578521374363769,
            1389835747040694332
        ]
        
        # Start background tasks
        self.cleanup_check.start()
        self.check_inactive_verified.start()
        self.check_active_demoted.start()
        
    def cog_unload(self):
        self.cleanup_check.cancel()
        self.check_inactive_verified.cancel()
        self.check_active_demoted.cancel()
    
    async def check_admin_permission(self, user: discord.Member) -> bool:
        """Check if user has admin voting permissions"""
        user_role_ids = [role.id for role in user.roles]
        return any(role_id in self.ADMIN_ROLES for role_id in user_role_ids)
    
    @tasks.loop(hours=1)
    async def cleanup_check(self):
        """Check for ghost users (no roles for 7+ days)"""
        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if not guild:
            return
        
        cleanup_channel = guild.get_channel(self.CLEANUP_CHANNEL_ID)
        admin_channel = guild.get_channel(self.ADMIN_CHANNEL_ID)
        
        if not cleanup_channel or not admin_channel:
            return
        
        current_time = datetime.utcnow()
        seven_days_ago = current_time - timedelta(days=7)
        
        for member in guild.members:
            # Check for ghost users (no roles except @everyone)
            if len(member.roles) <= 1:  # Only @everyone role
                join_date = member.joined_at
                
                if join_date and join_date < seven_days_ago:
                    user_id = member.id
                    
                    # Check if user is already being processed
                    if user_id not in self.ghost_users:
                        self.ghost_users[user_id] = join_date
                        
                        # Create embed for voting
                        embed = discord.Embed(
                            title="👻 Ghost User Detected",
                            description=f"**User:** {member.mention} ({member.display_name})\n"
                                      f"**User ID:** `{user_id}`\n"
                                      f"**Status:** Has no roles for 7+ days\n"
                                      f"**Joined:** {join_date.strftime('%Y-%m-%d %H:%M')}",
                            color=discord.Color.orange(),
                            timestamp=current_time
                        )
                        embed.set_footer(text=f"Member #{len(self.ghost_users) + 1}")
                        
                        # Send to cleanup channel for voting
                        view = GhostUserVoteView(self.bot, user_id, "ghost")
                        message = await cleanup_channel.send(embed=embed, view=view)
                        
                        # Also notify admin channel
                        admin_embed = discord.Embed(
                            title="⚠️ New Ghost User Alert",
                            description=f"A ghost user has been detected and added to cleanup queue.\n"
                                      f"**User:** {member.mention}\n"
                                      f"**Check:** <#{self.CLEANUP_CHANNEL_ID}>",
                            color=discord.Color.gold()
                        )
                        await admin_channel.send(embed=admin_embed)
    
    @tasks.loop(hours=2)
    async def check_inactive_verified(self):
        """Check verified members inactive for 15+ days"""
        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if not guild:
            return
        
        admin_channel = guild.get_channel(self.ADMIN_CHANNEL_ID)
        if not admin_channel:
            return
        
        verified_role = guild.get_role(self.VERIFIED_ROLE_ID)
        if not verified_role:
            return
        
        current_time = datetime.utcnow()
        fifteen_days_ago = current_time - timedelta(days=15)
        
        for member in verified_role.members:
            user_id = member.id
            
            # Skip if already being processed
            if user_id in self.demotion_candidates or user_id in self.under_review:
                continue
            
            # Check last activity (you might want to implement actual activity tracking)
            last_active = self.user_last_active.get(user_id, member.joined_at)
            
            if last_active and last_active < fifteen_days_ago:
                self.demotion_candidates[user_id] = last_active
                
                # Create demotion voting embed
                embed = discord.Embed(
                    title="⏰ Inactivity Alert - Verified Member",
                    description=f"**Member:** {member.mention} ({member.display_name})\n"
                              f"**User ID:** `{user_id}`\n"
                              f"**Status:** Inactive for 15+ days\n"
                              f"**Last Active:** {last_active.strftime('%Y-%m-%d %H:%M') if isinstance(last_active, datetime) else 'Unknown'}\n"
                              f"**Current Role:** <@&{self.VERIFIED_ROLE_ID}>",
                    color=discord.Color.purple(),
                    timestamp=current_time
                )
                
                # Send to admin channel for voting
                view = DemotionVoteView(self.bot, user_id, "inactive_verified")
                message = await admin_channel.send(embed=embed, view=view)
    
    @tasks.loop(hours=1)
    async def check_active_demoted(self):
        """Check if demoted users have become active"""
        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if not guild:
            return
        
        greet_channel = guild.get_channel(self.GREET_CHANNEL_ID)
        admin_channel = guild.get_channel(self.ADMIN_CHANNEL_ID)
        
        if not greet_channel or not admin_channel:
            return
        
        inactive_role = guild.get_role(self.INACTIVE_ROLE_ID)
        if not inactive_role:
            return
        
        for member in inactive_role.members:
            user_id = member.id
            
            # Check if user was recently active (within last hour)
            # You should implement actual activity tracking here
            # This is a placeholder - you need to track user activity properly
            if self.is_user_active(member):  # Implement this method based on your activity tracking
                if user_id in self.demoted_users and user_id not in self.under_review:
                    # User came back online
                    del self.demoted_users[user_id]
                    
                    # Send welcome message
                    welcome_embed = discord.Embed(
                        title="🎉 Welcome Back!",
                        description=f"**Welcome back {member.mention}!**\n\n"
                                  f"We've missed your presence in **Impèrius**! 🏰\n"
                                  f"It's great to see you active again!",
                        color=discord.Color.green(),
                        timestamp=datetime.utcnow()
                    )
                    welcome_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                    
                    await greet_channel.send(embed=welcome_embed)
                    
                    # Notify admins for review
                    review_embed = discord.Embed(
                        title="🔔 Previously Demoted User Active",
                        description=f"**User:** {member.mention} ({member.display_name})\n"
                                  f"**User ID:** `{user_id}`\n"
                                  f"**Status:** Became active after demotion\n"
                                  f"**Current Role:** <@&{self.INACTIVE_ROLE_ID}>\n\n"
                                  f"Please review their status and take appropriate action.",
                        color=discord.Color.blue()
                    )
                    
                    view = DemotedUserActionView(self.bot, user_id, "returned_active")
                    await admin_channel.send(embed=review_embed, view=view)
    
    def is_user_active(self, member: discord.Member) -> bool:
        """
        Check if user is active.
        You need to implement proper activity tracking.
        This could track: messages sent, voice activity, etc.
        """
        # Placeholder - implement your activity tracking logic here
        # Return True if user was active recently (e.g., last 1 hour)
        return False
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Track when users get roles updated"""
        # Track when users get promoted/demoted
        before_roles = {role.id for role in before.roles}
        after_roles = {role.id for role in after.roles}
        
        # Check if user got verified role
        if self.VERIFIED_ROLE_ID not in before_roles and self.VERIFIED_ROLE_ID in after_roles:
            user_id = after.id
            # Remove from any cleanup lists
            self.ghost_users.pop(user_id, None)
            self.demotion_candidates.pop(user_id, None)
            self.under_review.pop(user_id, None)
        
        # Check if user got demoted to inactive role
        if self.INACTIVE_ROLE_ID not in before_roles and self.INACTIVE_ROLE_ID in after_roles:
            user_id = after.id
            self.demoted_users[user_id] = datetime.utcnow()
            
            # Remove from other lists
            self.demotion_candidates.pop(user_id, None)
            self.under_review.pop(user_id, None)
            
            # Move to cleanup channel
            guild = after.guild
            cleanup_channel = guild.get_channel(self.CLEANUP_CHANNEL_ID)
            
            if cleanup_channel:
                embed = discord.Embed(
                    title="📥 User Demoted to Inactive",
                    description=f"**User:** {after.mention} ({after.display_name})\n"
                              f"**User ID:** `{user_id}`\n"
                              f"**Status:** Demoted due to inactivity\n"
                              f"**Demotion Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                
                view = DemotedUserActionView(self.bot, user_id, "demoted")
                await cleanup_channel.send(embed=embed, view=view)
    
    async def handle_vote_action(self, action: str, target_user_id: int, voter: discord.Member, message_id: int):
        """Handle vote actions from buttons"""
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if not guild:
            return
        
        target_user = guild.get_member(target_user_id)
        if not target_user:
            return
        
        admin_channel = guild.get_channel(self.ADMIN_CHANNEL_ID)
        cleanup_channel = guild.get_channel(self.CLEANUP_CHANNEL_ID)
        
        if action == "kick_ghost":
            # Kick ghost user
            try:
                await target_user.kick(reason=f"Ghost user cleanup - Voted by {voter.display_name}")
                
                # Send notification
                notification = (
                    f"👑 **{voter.display_name}** ordered user `{target_user_id}` to be kicked out of the server\n"
                    f"❌ **Reason:** Failed to pass and become part of **Impèrius** after 7+ days with no roles."
                )
                
                if cleanup_channel:
                    await cleanup_channel.send(notification)
                
                # Clean up records
                self.ghost_users.pop(target_user_id, None)
                
            except discord.Forbidden:
                if admin_channel:
                    await admin_channel.send(f"⚠️ Don't have permission to kick {target_user.mention}")
        
        elif action == "grant_role_ghost":
            # Grant verified role to ghost user
            verified_role = guild.get_role(self.VERIFIED_ROLE_ID)
            if verified_role:
                await target_user.add_roles(verified_role)
                
                notification = (
                    f"✨ **{voter.display_name}** has granted the **Impèrius** role to {target_user.mention}\n"
                    f"🎉 Welcome to the verified members!"
                )
                
                if cleanup_channel:
                    await cleanup_channel.send(notification)
                
                self.ghost_users.pop(target_user_id, None)
        
        elif action == "demote_verified":
            # Demote inactive verified user
            verified_role = guild.get_role(self.VERIFIED_ROLE_ID)
            inactive_role = guild.get_role(self.INACTIVE_ROLE_ID)
            
            if verified_role and inactive_role:
                await target_user.remove_roles(verified_role)
                await target_user.add_roles(inactive_role)
                
                notification = (
                    f"⬇️ **{voter.display_name}** has demoted {target_user.mention} to inactive status\n"
                    f"📉 **Reason:** Inactivity for 15+ days"
                )
                
                if admin_channel:
                    await admin_channel.send(notification)
                
                self.demotion_candidates.pop(target_user_id, None)
                self.demoted_users[target_user_id] = datetime.utcnow()
        
        elif action == "promote_demoted":
            # Promote demoted user back to verified
            verified_role = guild.get_role(self.VERIFIED_ROLE_ID)
            inactive_role = guild.get_role(self.INACTIVE_ROLE_ID)
            
            if verified_role and inactive_role:
                await target_user.remove_roles(inactive_role)
                await target_user.add_roles(verified_role)
                
                notification = (
                    f"⬆️ **{voter.display_name}** has promoted {target_user.mention} back to verified status!\n"
                    f"🎊 Welcome back to **Impèrius**!"
                )
                
                if cleanup_channel:
                    await cleanup_channel.send(notification)
                
                self.demoted_users.pop(target_user_id, None)
                self.under_review.pop(target_user_id, None)
        
        elif action == "kick_demoted":
            # Kick demoted user
            try:
                await target_user.kick(reason=f"Demoted user cleanup - Voted by {voter.display_name}")
                
                notification = (
                    f"👑 **{voter.display_name}** ordered user `{target_user_id}` to be kicked\n"
                    f"🗑️ **Reason:** Demoted user removal after review"
                )
                
                if cleanup_channel:
                    await cleanup_channel.send(notification)
                
                self.demoted_users.pop(target_user_id, None)
                self.under_review.pop(target_user_id, None)
                
            except discord.Forbidden:
                if admin_channel:
                    await admin_channel.send(f"⚠️ Don't have permission to kick {target_user.mention}")

def setup(bot):
    bot.add_cog(CleanupSystem(bot))
