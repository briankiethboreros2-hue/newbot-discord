import discord
from discord.ui import Button, View
from datetime import datetime, timedelta
from typing import Optional

class GhostUserVoteView(View):
    def __init__(self, bot, user_id: int, vote_type: str, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.vote_type = vote_type
        self.voters = set()  # Track who has voted
        self.vote_result = {"kick": 0, "grant": 0, "review": 0}
        
        # Create buttons
        self.add_item(Button(style=discord.ButtonStyle.red, label="🚫 Kick", custom_id=f"ghost_kick_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.green, label="✨ Grant Role", custom_id=f"ghost_grant_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id=f"ghost_review_{user_id}"))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to vote"""
        # Check admin roles
        cleanup_cog = self.bot.get_cog("CleanupSystem")
        if cleanup_cog:
            return await cleanup_cog.check_admin_permission(interaction.user)
        return False
    
    async def on_timeout(self):
        """Handle timeout - disable buttons"""
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True
        
        # Update message if possible
        if hasattr(self, 'message'):
            try:
                await self.message.edit(view=self)
            except:
                pass
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Button):
        """Handle errors"""
        await interaction.response.send_message(f"❌ An error occurred: {str(error)}", ephemeral=True)
    
    async def handle_vote(self, interaction: discord.Interaction, action: str):
        """Handle voting logic"""
        user_id = interaction.user.id
        
        if user_id in self.voters:
            await interaction.response.send_message("⚠️ You have already voted on this user!", ephemeral=True)
            return
        
        # Add to voters
        self.voters.add(user_id)
        
        # Update vote count
        if action == "kick":
            self.vote_result["kick"] += 1
        elif action == "grant":
            self.vote_result["grant"] += 1
        elif action == "review":
            self.vote_result["review"] += 1
        
        # Check if we have a decision (1 vote needed as per requirements)
        if len(self.voters) >= 1:
            # Determine action based on votes
            if self.vote_result["kick"] > 0:
                final_action = "kick"
            elif self.vote_result["grant"] > 0:
                final_action = "grant"
            elif self.vote_result["review"] > 0:
                final_action = "review"
            else:
                final_action = None
            
            if final_action:
                # Call cleanup system to handle the action
                cleanup_cog = self.bot.get_cog("CleanupSystem")
                if cleanup_cog:
                    await cleanup_cog.handle_vote_action(
                        f"{final_action}_{self.vote_type}",
                        self.user_id,
                        interaction.user,
                        interaction.message.id
                    )
                
                # Disable buttons after decision
                for item in self.children:
                    if isinstance(item, Button):
                        item.disabled = True
                
                # Update embed with result
                embed = interaction.message.embeds[0] if interaction.message.embeds else None
                if embed:
                    embed.add_field(
                        name="✅ Decision Made",
                        value=f"**Action:** {final_action.upper()}\n"
                              f"**By:** {interaction.user.mention}\n"
                              f"**Time:** {datetime.utcnow().strftime('%H:%M:%S')}",
                        inline=False
                    )
                    embed.color = discord.Color.green()
                
                await interaction.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"✅ Vote registered! Action `{final_action}` will be executed.", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Vote registered!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Vote registered! Waiting for more votes...", ephemeral=True)
    
    @discord.ui.button(style=discord.ButtonStyle.red, label="🚫 Kick", custom_id="ghost_kick")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "kick")
    
    @discord.ui.button(style=discord.ButtonStyle.green, label="✨ Grant Role", custom_id="ghost_grant")
    async def grant_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "grant")
    
    @discord.ui.button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id="ghost_review")
    async def review_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "review")

class DemotionVoteView(View):
    def __init__(self, bot, user_id: int, vote_type: str, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.vote_type = vote_type
        self.voters = set()
        self.vote_result = {"demote": 0, "review": 0}
        
        self.add_item(Button(style=discord.ButtonStyle.red, label="📉 Demote", custom_id=f"inactive_demote_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id=f"inactive_review_{user_id}"))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cleanup_cog = self.bot.get_cog("CleanupSystem")
        if cleanup_cog:
            return await cleanup_cog.check_admin_permission(interaction.user)
        return False
    
    async def handle_vote(self, interaction: discord.Interaction, action: str):
        user_id = interaction.user.id
        
        if user_id in self.voters:
            await interaction.response.send_message("⚠️ You have already voted!", ephemeral=True)
            return
        
        self.voters.add(user_id)
        
        if action == "demote":
            self.vote_result["demote"] += 1
        elif action == "review":
            self.vote_result["review"] += 1
        
        if len(self.voters) >= 1:
            final_action = "demote" if self.vote_result["demote"] > 0 else "review"
            
            cleanup_cog = self.bot.get_cog("CleanupSystem")
            if cleanup_cog:
                if final_action == "demote":
                    await cleanup_cog.handle_vote_action(
                        f"demote_{self.vote_type}",
                        self.user_id,
                        interaction.user,
                        interaction.message.id
                    )
                elif final_action == "review":
                    # Mark as under review
                    if self.user_id not in cleanup_cog.under_review:
                        cleanup_cog.under_review[self.user_id] = datetime.utcnow()
                    
                    # Create under review voting
                    view = UnderReviewVoteView(self.bot, self.user_id, "under_review")
                    
                    embed = interaction.message.embeds[0]
                    embed.title = "📋 Under Review - Verified Member"
                    embed.description += f"\n\n**Status:** Under Review\n**Review Started:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
                    embed.color = discord.Color.blue()
                    
                    await interaction.message.edit(embed=embed, view=view)
            
            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True
            
            await interaction.response.send_message(f"✅ Vote registered! Action `{final_action}` executed.", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Vote registered!", ephemeral=True)
    
    @discord.ui.button(style=discord.ButtonStyle.red, label="📉 Demote", custom_id="inactive_demote")
    async def demote_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "demote")
    
    @discord.ui.button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id="inactive_review")
    async def review_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "review")

class DemotedUserActionView(View):
    def __init__(self, bot, user_id: int, vote_type: str, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.vote_type = vote_type
        self.voters = set()
        
        self.add_item(Button(style=discord.ButtonStyle.green, label="⬆️ Promote", custom_id=f"demoted_promote_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.red, label="🚫 Kick", custom_id=f"demoted_kick_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id=f"demoted_review_{user_id}"))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cleanup_cog = self.bot.get_cog("CleanupSystem")
        if cleanup_cog:
            return await cleanup_cog.check_admin_permission(interaction.user)
        return False
    
    async def handle_vote(self, interaction: discord.Interaction, action: str):
        user_id = interaction.user.id
        
        if user_id in self.voters:
            await interaction.response.send_message("⚠️ Already voted!", ephemeral=True)
            return
        
        self.voters.add(user_id)
        
        if len(self.voters) >= 1:
            cleanup_cog = self.bot.get_cog("CleanupSystem")
            if cleanup_cog:
                if action == "promote":
                    await cleanup_cog.handle_vote_action(
                        "promote_demoted",
                        self.user_id,
                        interaction.user,
                        interaction.message.id
                    )
                elif action == "kick":
                    await cleanup_cog.handle_vote_action(
                        "kick_demoted",
                        self.user_id,
                        interaction.user,
                        interaction.message.id
                    )
                elif action == "review":
                    # Mark as under review
                    if self.user_id not in cleanup_cog.under_review:
                        cleanup_cog.under_review[self.user_id] = datetime.utcnow()
                    
                    embed = interaction.message.embeds[0]
                    embed.title = f"📋 Under Review - Demoted User"
                    embed.description += f"\n\n**Status:** Under Review\n**By:** {interaction.user.mention}"
                    embed.color = discord.Color.blue()
                    
                    await interaction.message.edit(embed=embed)
            
            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True
            
            await interaction.response.send_message(f"✅ Action `{action}` executed!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Vote registered!", ephemeral=True)
    
    @discord.ui.button(style=discord.ButtonStyle.green, label="⬆️ Promote", custom_id="demoted_promote")
    async def promote_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "promote")
    
    @discord.ui.button(style=discord.ButtonStyle.red, label="🚫 Kick", custom_id="demoted_kick")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "kick")
    
    @discord.ui.button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id="demoted_review")
    async def review_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "review")

class UnderReviewVoteView(View):
    def __init__(self, bot, user_id: int, vote_type: str, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.vote_type = vote_type
        self.voters = set()
        
        self.add_item(Button(style=discord.ButtonStyle.green, label="✅ Pardon", custom_id=f"review_pardon_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.red, label="📉 Demote", custom_id=f"review_demote_{user_id}"))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cleanup_cog = self.bot.get_cog("CleanupSystem")
        if cleanup_cog:
            return await cleanup_cog.check_admin_permission(interaction.user)
        return False
    
    async def handle_vote(self, interaction: discord.Interaction, action: str):
        user_id = interaction.user.id
        
        if user_id in self.voters:
            await interaction.response.send_message("⚠️ Already voted!", ephemeral=True)
            return
        
        self.voters.add(user_id)
        
        if len(self.voters) >= 1:
            cleanup_cog = self.bot.get_cog("CleanupSystem")
            if cleanup_cog:
                if action == "pardon":
                    # Keep the verified role
                    guild = self.bot.get_guild(self.bot.config.guild_id)
                    if guild:
                        target_user = guild.get_member(self.user_id)
                        if target_user:
                            # Remove from under review
                            cleanup_cog.under_review.pop(self.user_id, None)
                            cleanup_cog.demotion_candidates.pop(self.user_id, None)
                            
                            embed = interaction.message.embeds[0]
                            embed.title = "✅ Pardoned - Keeps Role"
                            embed.description += f"\n\n**Decision:** Pardoned\n**By:** {interaction.user.mention}\nUser keeps their verified role."
                            embed.color = discord.Color.green()
                            
                            await interaction.message.edit(embed=embed, view=None)
                
                elif action == "demote":
                    await cleanup_cog.handle_vote_action(
                        "demote_verified",
                        self.user_id,
                        interaction.user,
                        interaction.message.id
                    )
            
            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True
            
            await interaction.response.send_message(f"✅ Action `{action}` executed!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Vote registered!", ephemeral=True)
    
    @discord.ui.button(style=discord.ButtonStyle.green, label="✅ Pardon", custom_id="review_pardon")
    async def pardon_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "pardon")
    
    @discord.ui.button(style=discord.ButtonStyle.red, label="📉 Demote", custom_id="review_demote")
    async def demote_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "demote")
