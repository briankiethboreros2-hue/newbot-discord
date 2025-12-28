import discord
from discord.ui import View, Button
import asyncio

class GhostUserView(View):
    def __init__(self, member, inactivity_data):
        super().__init__(timeout=86400)  # 24 hours
        self.member = member
        self.inactivity_data = inactivity_data
        self.voted_admins = set()
        
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        # Check if user has admin role
        admin_roles = [1389835747040694332, 1437578521374363769, 143757291600583479, 1438420490455613540]
        if not any(role.id in admin_roles for role in interaction.user.roles):
            await interaction.response.send_message("You don't have permission to vote.", ephemeral=True)
            return
            
        self.voted_admins.add(interaction.user.id)
        
        # Create action log
        embed = discord.Embed(
            title=":scales: Admin Action",
            color=discord.Color.blue()
        )
        embed.add_field(name="Action", value="Kick", inline=False)
        embed.add_field(name="User", value=f"<@{self.member.id}>", inline=False)
        embed.add_field(name="Admin", value=f"<@{interaction.user.id}>", inline=False)
        
        await interaction.channel.send(embed=embed)
        
        # Execute kick
        try:
            await self.member.kick(reason="Inactivity - Ghost User")
            await interaction.response.send_message(f"User {self.member.display_name} has been kicked.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error kicking user: {e}", ephemeral=True)

class DemotionReviewView(View):
    def __init__(self, member, inactivity_data, cleanup_system):
        super().__init__(timeout=86400)
        self.member = member
        self.inactivity_data = inactivity_data
        self.cleanup_system = cleanup_system
        self.votes = {"demote": set(), "keep": set()}
        
    @discord.ui.button(label="Demote", style=discord.ButtonStyle.primary, emoji="⬇️")
    async def demote_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "demote")
        
    @discord.ui.button(label="Keep Role", style=discord.ButtonStyle.success, emoji="✅")
    async def keep_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "keep")
    
    async def handle_vote(self, interaction, vote_type):
        # Check admin permissions
        admin_roles = [1389835747040694332, 1437578521374363769, 143757291600583479, 1438420490455613540]
        if not any(role.id in admin_roles for role in interaction.user.roles):
            await interaction.response.send_message("You don't have permission to vote.", ephemeral=True)
            return
            
        self.votes[vote_type].add(interaction.user.id)
        
        # Check if majority reached
        total_votes = len(self.votes["demote"]) + len(self.votes["keep"])
        if total_votes >= 2:  # At least 2 admins voted
            if len(self.votes["demote"]) > len(self.votes["keep"]):
                # Demote user
                success = await self.cleanup_system.demote_user(self.member, interaction.user)
                if success:
                    await interaction.response.send_message(f"User {self.member.display_name} has been demoted.", ephemeral=True)
                else:
                    await interaction.response.send_message("Failed to demote user.", ephemeral=True)
            else:
                await interaction.response.send_message(f"User {self.member.display_name} will keep their role.", ephemeral=True)
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message(f"Vote recorded. Current votes: Demote({len(self.votes['demote'])}), Keep({len(self.votes['keep'])})", ephemeral=True)

# Similar views for ReturnReviewView and FinalReviewView would be implemented
