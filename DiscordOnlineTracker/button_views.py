"""
Button Views for Discord Bot
Handles all button interactions for the cleanup system
"""

import discord
from discord.ui import View, Button
import asyncio
from datetime import datetime

class BaseAdminView(View):
    """Base view for admin actions with rate limiting"""
    
    def __init__(self, member: discord.Member, cleanup_system, timeout=86400):  # 24 hours
        super().__init__(timeout=timeout)
        self.member = member
        self.cleanup_system = cleanup_system
        self.voted_admins = set()
        self.vote_lock = asyncio.Lock()  # Prevent race conditions
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can interact"""
        # Check if view is already expired
        if self.is_finished():
            await interaction.response.send_message(
                "❌ This action has expired. Please run cleanup check again.",
                ephemeral=True
            )
            return False
        
        # Check admin permissions
        if not self.cleanup_system.is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to vote on this action.",
                ephemeral=True
            )
            return False
        
        return True

class GhostUserView(BaseAdminView):
    """View for handling ghost users"""
    
    def __init__(self, member: discord.Member, cleanup_system):
        super().__init__(member, cleanup_system, timeout=86400)
        self.votes_needed = 1  # Only 1 admin needed for ghost users
    
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢", custom_id="ghost_kick")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await interaction.response.defer(thinking=True)
            
            # Check if already voted
            if interaction.user.id in self.voted_admins:
                await interaction.followup.send(
                    "✅ You have already voted on this action.",
                    ephemeral=True
                )
                return
            
            self.voted_admins.add(interaction.user.id)
            
            # Execute kick
            success, message = await self.cleanup_system.kick_user(
                self.member, 
                interaction.user
            )
            
            if success:
                # Disable all buttons
                for child in self.children:
                    child.disabled = True
                await interaction.message.edit(view=self)
                
                await interaction.followup.send(
                    f"✅ {message}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {message}",
                    ephemeral=True
                )

class DemotionReviewView(BaseAdminView):
    """View for demotion review voting"""
    
    def __init__(self, member: discord.Member, cleanup_system):
        super().__init__(member, cleanup_system, timeout=86400)
        self.demote_votes = set()
        self.keep_votes = set()
        self.votes_needed = 2  # Need 2 admins to agree
    
    @discord.ui.button(label="Demote", style=discord.ButtonStyle.primary, emoji="⬇️", custom_id="demote_vote")
    async def demote_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await self._handle_vote(interaction, "demote")
        
    @discord.ui.button(label="Keep Role", style=discord.ButtonStyle.success, emoji="✅", custom_id="keep_vote")
    async def keep_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await self._handle_vote(interaction, "keep")
    
    async def _handle_vote(self, interaction: discord.Interaction, vote_type: str):
        await interaction.response.defer(thinking=True)
        
        voter_id = interaction.user.id
        
        # Remove from other vote category if already voted
        if voter_id in self.demote_votes:
            self.demote_votes.remove(voter_id)
        if voter_id in self.keep_votes:
            self.keep_votes.remove(voter_id)
        
        # Add to new vote category
        if vote_type == "demote":
            self.demote_votes.add(voter_id)
        else:
            self.keep_votes.add(voter_id)
        
        total_votes = len(self.demote_votes) + len(self.keep_votes)
        
        # Send vote confirmation
        await interaction.followup.send(
            f"📊 Vote recorded!\n"
            f"Demote: {len(self.demote_votes)}\n"
            f"Keep: {len(self.keep_votes)}\n"
            f"Need {self.votes_needed - total_votes} more vote(s).",
            ephemeral=True
        )
        
        # Check if we have enough votes
        if total_votes >= self.votes_needed:
            if len(self.demote_votes) > len(self.keep_votes):
                # Demote user
                success, message = await self.cleanup_system.demote_user(
                    self.member, 
                    interaction.user
                )
                
                if success:
                    # Disable all buttons
                    for child in self.children:
                        child.disabled = True
                    await interaction.message.edit(view=self)
            else:
                # Keep role
                await self.cleanup_system._log_admin_action(
                    "keep", 
                    self.member, 
                    interaction.user
                )
                
                # Disable all buttons
                for child in self.children:
                    child.disabled = True
                await interaction.message.edit(view=self)

class ReturnReviewView(BaseAdminView):
    """View for returning user review"""
    
    def __init__(self, member: discord.Member, cleanup_system):
        super().__init__(member, cleanup_system, timeout=86400)  # 24 hours
        
        # Add user info to view
        self.days_inactive = cleanup_system.get_inactivity_days(member.id)
        self.server_name = member.guild.name
    
    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️", custom_id="promote_user")
    async def promote_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await interaction.response.defer(thinking=True)
            
            # Log who is taking action
            print(f"👑 {interaction.user.display_name} promoting {self.member.display_name}")
            
            success, message = await self.cleanup_system.promote_user(
                self.member, 
                interaction.user
            )
            
            if success:
                # Update activity tracking (user is now active)
                await self.cleanup_system.track_user_activity(self.member.id, "promoted_back")
                
                # Disable all buttons
                for child in self.children:
                    child.disabled = True
                await interaction.message.edit(view=self)
            
            await interaction.followup.send(
                f"{'✅' if success else '❌'} {message}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Review", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="review_user")
    async def review_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await interaction.response.defer(thinking=True)
            
            print(f"🔍 {interaction.user.display_name} putting {self.member.display_name} under review")
            
            # Put user under review
            await self.cleanup_system.put_user_under_review(self.member)
            
            # Disable buttons
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
            
            await interaction.followup.send(
                f"✅ User {self.member.display_name} has been put under review.",
                ephemeral=True
            )
    
    async def _handle_review(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        
        # Put user under review
        await self.cleanup_system.put_user_under_review(self.member)
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.followup.send(
            f"✅ User {self.member.display_name} has been put under review.",
            ephemeral=True
        )

class FinalReviewView(BaseAdminView):
    """View for final review voting"""
    
    def __init__(self, member: discord.Member, cleanup_system):
        super().__init__(member, cleanup_system, timeout=86400)
        self.promote_votes = set()
        self.kick_votes = set()
        self.votes_needed = 2
    
    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️", custom_id="final_promote")
    async def promote_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await self._handle_vote(interaction, "promote")
    
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢", custom_id="final_kick")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        async with self.vote_lock:
            await self._handle_vote(interaction, "kick")
    
    async def _handle_vote(self, interaction: discord.Interaction, vote_type: str):
        await interaction.response.defer(thinking=True)
        
        voter_id = interaction.user.id
        
        # Remove from other vote category if already voted
        if voter_id in self.promote_votes:
            self.promote_votes.remove(voter_id)
        if voter_id in self.kick_votes:
            self.kick_votes.remove(voter_id)
        
        # Add to new vote category
        if vote_type == "promote":
            self.promote_votes.add(voter_id)
        else:
            self.kick_votes.add(voter_id)
        
        total_votes = len(self.promote_votes) + len(self.kick_votes)
        
        # Send vote confirmation
        await interaction.followup.send(
            f"📊 Vote recorded!\n"
            f"Promote: {len(self.promote_votes)}\n"
            f"Kick: {len(self.kick_votes)}\n"
            f"Need {self.votes_needed - total_votes} more vote(s).",
            ephemeral=True
        )
        
        # Check if we have enough votes
        if total_votes >= self.votes_needed:
            if len(self.promote_votes) > len(self.kick_votes):
                # Promote user
                success, message = await self.cleanup_system.promote_user(
                    self.member, 
                    interaction.user
                )
                
                if success:
                    # Disable all buttons
                    for child in self.children:
                        child.disabled = True
                    await interaction.message.edit(view=self)
            else:
                # Kick user
                success, message = await self.cleanup_system.kick_user(
                    self.member,
                    interaction.user
                )
                
                if success:
                    # Disable all buttons
                    for child in self.children:
                        child.disabled = True
                    await interaction.message.edit(view=self)
