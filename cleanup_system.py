import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio

class CleanupSystem:
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_channel_id = 1454802873300025396
        self.admin_channel_id = 1437586858417852438
        self.target_role_id = 1437570031822176408
        self.demote_role_id = 1454803208995340328
        self.admin_roles = [1389835747040694332, 1437578521374363769, 143757291600583479, 1438420490455613540]
        
        # Channels demoted users can access
        self.demoted_allowed_channels = [1369091668724154419, 1437575744824934531]
        
        self.ghost_users_review = {}
        self.demoted_users_review = {}
        self.users_under_review = {}
        
    async def check_inactive_users(self):
        """Check for inactive users and create review embeds"""
        try:
            for guild in self.bot.guilds:
                # Check ghost users (no roles)
                await self.check_ghost_users(guild)
                
                # Check users with target role
                await self.check_target_role_users(guild)
        except Exception as e:
            print(f"Error checking inactive users: {e}")
    
    async def check_ghost_users(self, guild):
        """Check users with no roles"""
        cleanup_channel = self.bot.get_channel(self.cleanup_channel_id)
        if not cleanup_channel:
            return
            
        for member in guild.members:
            if len(member.roles) == 1:  # Only @everyone role
                if member.bot:
                    continue
                    
                # Check last activity (you'll need to implement this based on your tracking)
                inactivity_data = await self.get_user_inactivity(member)
                if inactivity_data['days_inactive'] >= 15:
                    await self.create_ghost_user_embed(member, inactivity_data, cleanup_channel)
    
    async def check_target_role_users(self, guild):
        """Check users with target role for inactivity"""
        admin_channel = self.bot.get_channel(self.admin_channel_id)
        if not admin_channel:
            return
            
        target_role = guild.get_role(self.target_role_id)
        if not target_role:
            return
            
        for member in target_role.members:
            if member.bot:
                continue
                
            inactivity_data = await self.get_user_inactivity(member)
            if inactivity_data['days_inactive'] >= 15:
                await self.create_demotion_embed(member, inactivity_data, admin_channel)
    
    async def get_user_inactivity(self, member):
        """Get user inactivity data - you'll need to implement your tracking logic"""
        # This is a placeholder - implement based on your current tracking system
        last_active = datetime.utcnow() - timedelta(days=30)  # Example
        days_inactive = (datetime.utcnow() - last_active).days
        
        return {
            'last_active': last_active,
            'days_inactive': days_inactive
        }
    
    async def create_ghost_user_embed(self, member, inactivity_data, channel):
        """Create embed for ghost users"""
        embed = discord.Embed(
            title="Ghost User Detected",
            color=discord.Color.dark_gray()
        )
        
        embed.add_field(name="User", value=f"<@{member.id}>", inline=False)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=False)
        embed.add_field(name="Last Active", value=f"`{inactivity_data['last_active'].strftime('%Y-%m-%d %H:%M')} UTC`", inline=False)
        embed.add_field(name="Days Inactive", value=f"`{inactivity_data['days_inactive']}`", inline=False)
        
        view = GhostUserView(member, inactivity_data)
        await channel.send(embed=embed, view=view)
    
    async def create_demotion_embed(self, member, inactivity_data, channel):
        """Create embed for demotion review"""
        embed = discord.Embed(
            title=f"Demotion Review: {member.display_name}",
            color=discord.Color.orange()
        )
        
        embed.add_field(name="User", value=f"<@{member.id}>", inline=False)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=False)
        embed.add_field(name="Current Role", value=f"<@&{self.target_role_id}>", inline=False)
        embed.add_field(name="Last Active", value=f"`{inactivity_data['last_active'].strftime('%Y-%m-%d %H:%M')} UTC`", inline=False)
        embed.add_field(name="Days Inactive", value=f"`{inactivity_data['days_inactive']}`", inline=False)
        
        view = DemotionReviewView(member, inactivity_data, self)
        await channel.send(embed=embed, view=view)
    
    async def demote_user(self, member, admin):
        """Demote user to lower role"""
        try:
            target_role = member.guild.get_role(self.target_role_id)
            demote_role = member.guild.get_role(self.demote_role_id)
            
            if target_role in member.roles:
                await member.remove_roles(target_role)
            await member.add_roles(demote_role)
            
            # Send action log
            await self.log_action("Demotion", member, admin)
            
            return True
        except Exception as e:
            print(f"Error demoting user: {e}")
            return False
    
    async def promote_user(self, member, admin):
        """Promote user back to original role"""
        try:
            target_role = member.guild.get_role(self.target_role_id)
            demote_role = member.guild.get_role(self.demote_role_id)
            
            if demote_role in member.roles:
                await member.remove_roles(demote_role)
            await member.add_roles(target_role)
            
            # Send action log
            await self.log_action("Promotion", member, admin)
            
            return True
        except Exception as e:
            print(f"Error promoting user: {e}")
            return False
    
    async def log_action(self, action_type, member, admin):
        """Log admin actions"""
        log_channel = self.bot.get_channel(self.admin_channel_id)
        if not log_channel:
            return
            
        embed = discord.Embed(
            title=f":scales: {action_type} Action",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Action", value=f"`{action_type}`", inline=False)
        embed.add_field(name="User", value=f"<@{member.id}>", inline=False)
        embed.add_field(name="Admin", value=f"<@{admin.id}>", inline=False)
        embed.add_field(name="Timestamp", value=f"`{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`", inline=False)
        
        await log_channel.send(embed=embed)
