import discord
from discord.ui import View, Button
from datetime import datetime

class UserReviewSystem:
    def __init__(self, bot):
        self.bot = bot
        self.users_under_review = {}
        
    async def handle_user_return(self, member):
        """Handle when a demoted user returns"""
        demote_role_id = 1454803208995340328
        
        # Check if user has demoted role
        if any(role.id == demote_role_id for role in member.roles):
            # Send welcome message
            welcome_channel = self.bot.get_channel(1369091668724154419)
            if welcome_channel:
                await welcome_channel.send(
                    f"Welcome back! {member.mention}\n"
                    f"You were demoted due to inactivity\n"
                    f"I'll notify the admins about you"
                )
            
            # Notify admin channel
            await self.notify_admin_user_returned(member)
    
    async def notify_admin_user_returned(self, member):
        """Notify admins that a demoted user returned"""
        admin_channel = self.bot.get_channel(1437586858417852438)
        if not admin_channel:
            return
            
        # Get inactivity data
        inactivity_data = await self.get_user_inactivity(member)
        
        embed = discord.Embed(
            title=f":green_circle: {member.display_name} came back online!",
            color=discord.Color.green()
        )
        
        embed.add_field(name="User", value=f"<@{member.id}>", inline=False)
        embed.add_field(name="Days Inactive", value=f"`{inactivity_data['days_inactive']}`", inline=False)
        
        view = ReturnReviewView(member, inactivity_data)
        await admin_channel.send(embed=embed, view=view)
    
    async def put_user_under_review(self, member):
        """Put user under formal review"""
        admin_channel = self.bot.get_channel(1437586858417852438)
        if not admin_channel:
            return
            
        inactivity_data = await self.get_user_inactivity(member)
        
        embed = discord.Embed(
            title=f":green_circle: {member.display_name} is under review",
            color=discord.Color.yellow()
        )
        
        embed.add_field(name="User", value=f"<@{member.id}>", inline=False)
        embed.add_field(name="Days Inactive", value=f"`{inactivity_data['days_inactive']}`", inline=False)
        embed.add_field(name="Final Decision", value=":scales:", inline=False)
        
        view = FinalReviewView(member, inactivity_data)
        await admin_channel.send(embed=embed, view=view)
