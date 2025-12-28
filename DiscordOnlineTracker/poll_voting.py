"""
Poll Voting System for Discord Bot
Optional - Use if you want polls instead of buttons
"""

import discord
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os

class PollVoting:
    """Poll-based voting system (optional feature)"""
    
    def __init__(self, client):
        self.client = client
        self.active_polls: Dict[int, Dict] = {}
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        
    async def create_poll(self, channel, question, options, duration_minutes=60, allowed_voters=None):
        """Create a simple poll - optional feature"""
        try:
            if len(options) < 2 or len(options) > 10:
                return None
            
            poll_text = f"**📊 POLL: {question}**\n\n"
            for i, option in enumerate(options):
                poll_text += f"{i+1}. {option}\n"
            
            poll_text += f"\n⏰ Poll closes in {duration_minutes} minutes"
            
            if allowed_voters:
                poll_text += f"\n👑 Voting restricted to admins"
            
            message = await channel.send(poll_text)
            
            # Add number reactions
            for i in range(len(options)):
                await message.add_reaction(f"{i+1}\N{COMBINING ENCLOSING KEYCAP}")
            
            # Schedule auto-close
            asyncio.create_task(
                self._close_poll_after_delay(message.id, channel, duration_minutes * 60)
            )
            
            return message
            
        except Exception as e:
            print(f"❌ Poll creation error: {e}")
            return None
    
    async def _close_poll_after_delay(self, message_id, channel, delay_seconds):
        """Close poll after delay"""
        await asyncio.sleep(delay_seconds)
        
        try:
            message = await channel.fetch_message(message_id)
            
            # Count votes
            results = {}
            for reaction in message.reactions:
                if hasattr(reaction.emoji, 'name') and reaction.emoji.name[0].isdigit():
                    option_num = int(reaction.emoji.name[0])
                    results[option_num] = reaction.count - 1  # Subtract bot's reaction
            
            # Create results embed
            if results:
                embed = discord.Embed(
                    title="📊 Poll Results",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                for option_num, votes in sorted(results.items()):
                    embed.add_field(
                        name=f"Option {option_num}",
                        value=f"{votes} votes",
                        inline=True
                    )
                
                await channel.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Poll closing error: {e}")
