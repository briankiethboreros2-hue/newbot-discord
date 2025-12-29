import discord
from discord.ext import commands
from datetime import datetime
from typing import Dict, List, Set

class PollingVote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}  # message_id: poll_data
        self.user_votes = {}  # user_id: set(message_ids)
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Track button interactions for voting"""
        if interaction.type != discord.InteractionType.component:
            return
        
        # Check if it's a voting button
        custom_id = interaction.data.get('custom_id', '')
        if not custom_id:
            return
        
        # Extract user_id from custom_id if present
        parts = custom_id.split('_')
        if len(parts) >= 3:
            try:
                target_user_id = int(parts[-1])
                action_type = '_'.join(parts[:-1])
                
                # Log the vote
                print(f"[VOTE] {interaction.user} voted {action_type} on user {target_user_id}")
                
            except ValueError:
                pass

def setup(bot):
    bot.add_cog(PollingVote(bot))
