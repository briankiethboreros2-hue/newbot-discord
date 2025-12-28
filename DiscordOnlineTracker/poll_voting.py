"""
Poll Voting System for Discord Bot
Replaces reaction-based voting with Discord's native poll feature
"""

import discord
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os

class PollVoting:
    """Poll-based voting system"""
    
    def __init__(self, client):
        self.client = client
        self.active_polls: Dict[int, Dict] = {}  # message_id -> poll_data
        self.poll_results: Dict[int, Dict] = {}
        self.data_dir = "data"
        self.poll_file = os.path.join(self.data_dir, "active_polls.json")
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Load active polls on startup
        self.load_polls()
    
    def load_polls(self):
        """Load active polls from file"""
        try:
            if os.path.exists(self.poll_file):
                with open(self.poll_file, 'r') as f:
                    saved_polls = json.load(f)
                    
                    # Convert string dates to datetime
                    for msg_id, poll_data in saved_polls.items():
                        if 'created_at' in poll_data:
                            try:
                                poll_data['created_at'] = datetime.fromisoformat(poll_data['created_at'])
                            except:
                                poll_data['created_at'] = datetime.now()
                        
                        if 'expires_at' in poll_data:
                            try:
                                poll_data['expires_at'] = datetime.fromisoformat(poll_data['expires_at'])
                            except:
                                # Set default expiration if corrupted
                                poll_data['expires_at'] = datetime.now() + timedelta(hours=1)
                        
                        self.active_polls[int(msg_id)] = poll_data
                    
                    print(f"📊 Loaded {len(self.active_polls)} active polls")
                    
        except Exception as e:
            print(f"⚠️ Error loading polls: {e}")
    
    def save_polls(self):
        """Save active polls to file"""
        try:
            # Convert datetime to string for JSON
            polls_to_save = {}
            for msg_id, poll_data in self.active_polls.items():
                polls_to_save[str(msg_id)] = poll_data.copy()
                
                if 'created_at' in polls_to_save[str(msg_id)]:
                    polls_to_save[str(msg_id)]['created_at'] = polls_to_save[str(msg_id)]['created_at'].isoformat()
                
                if 'expires_at' in polls_to_save[str(msg_id)]:
                    polls_to_save[str(msg_id)]['expires_at'] = polls_to_save[str(msg_id)]['expires_at'].isoformat()
            
            with open(self.poll_file, 'w') as f:
                json.dump(polls_to_save, f, indent=2)
                
        except Exception as e:
            print(f"⚠️ Error saving polls: {e}")
    
    async def create_poll(self, channel: discord.TextChannel, 
                         question: str, 
                         options: List[str],
                         duration_minutes: int = 1440,  # 24 hours default
                         allowed_voters: List[int] = None) -> Optional[discord.Message]:
        """
        Create a poll with multiple options
        
        Args:
            channel: Channel to post poll in
            question: Poll question
            options: List of options (2-10)
            duration_minutes: How long the poll should last
            allowed_voters: List of role IDs allowed to vote (None = everyone)
            
        Returns:
            Poll message or None if failed
        """
        try:
            # Validate options
            if len(options) < 2 or len(options) > 10:
                raise ValueError("Poll must have between 2 and 10 options")
            
            if duration_minutes < 1 or duration_minutes > 10080:  # Max 7 days
                raise ValueError("Poll duration must be between 1 minute and 7 days")
            
            # Create poll message
            poll_text = f"**📊 POLL: {question}**\n\n"
            
            for i, option in enumerate(options):
                poll_text += f"**{i+1}️⃣** {option}\n"
            
            poll_text += f"\n⏰ Poll closes in {duration_minutes} minutes"
            
            if allowed_voters:
                poll_text += "\n👑 Voting restricted to specific roles"
            
            # Send message
            message = await channel.send(poll_text)
            
            # Add number reactions
            for i in range(len(options)):
                await message.add_reaction(f"{i+1}\u20e3")  # Keycap numbers 1-10
            
            # Store poll data
            self.active_polls[message.id] = {
                'question': question,
                'options': options,
                'channel_id': channel.id,
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(minutes=duration_minutes),
                'allowed_voters': allowed_voters or [],
                'votes': {i: [] for i in range(len(options))},
                'voters': set()  # Track who has voted
            }
            
            # Save to file
            self.save_polls()
            
            # Schedule poll closure
            asyncio.create_task(
                self._close_poll_after_delay(message.id, duration_minutes * 60)
            )
            
            return message
            
        except Exception as e:
            print(f"❌ Error creating poll: {e}")
            return None
    
    async def _close_poll_after_delay(self, message_id: int, delay_seconds: int):
        """Close poll after specified delay"""
        await asyncio.sleep(delay_seconds)
        await self.close_poll(message_id)
    
    async def close_poll(self, message_id: int):
        """Close a poll and announce results"""
        if message_id not in self.active_polls:
            return
        
        poll = self.active_polls[message_id]
        
        try:
            channel = self.client.get_channel(poll['channel_id'])
            if not channel:
                print(f"❌ Channel not found for poll {message_id}")
                return
            
            # Fetch message to get current reactions
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                print(f"❌ Poll message {message_id} not found")
                del self.active_polls[message_id]
                self.save_polls()
                return
            
            # Count votes from reactions
            total_votes = 0
            option_votes = {}
            
            for i, option in enumerate(poll['options']):
                vote_count = 0
                try:
                    reaction = discord.utils.get(message.reactions, emoji=f"{i+1}\u20e3")
                    if reaction:
                        # Count unique voters (excluding bots)
                        async for user in reaction.users():
                            if not user.bot:
                                vote_count += 1
                except:
                    pass
                
                option_votes[i] = vote_count
                total_votes += vote_count
            
            # Calculate results
            if total_votes == 0:
                results_text = "❌ No votes were cast in this poll."
            else:
                # Find winner(s)
                max_votes = max(option_votes.values())
                winning_options = [i for i, votes in option_votes.items() if votes == max_votes]
                
                results_text = f"**📊 POLL RESULTS: {poll['question']}**\n\n"
                
                for i, option in enumerate(poll['options']):
                    votes = option_votes.get(i, 0)
                    percentage = (votes / total_votes * 100) if total_votes > 0 else 0
                    
                    # Create progress bar
                    bar_length = 20
                    filled_length = int(bar_length * votes // max(1, max_votes))
                    bar = "█" * filled_length + "░" * (bar_length - filled_length)
                    
                    winner_indicator = " 🏆" if i in winning_options else ""
                    
                    results_text += f"**{i+1}️⃣ {option}**{winner_indicator}\n"
                    results_text += f"{bar} {votes} votes ({percentage:.1f}%)\n\n"
                
                if len(winning_options) == 1:
                    winner_text = poll['options'][winning_options[0]]
                    results_text += f"**Winner:** {winner_text}"
                else:
                    winners = [poll['options'][i] for i in winning_options]
                    results_text += f"**Tie between:** {', '.join(winners)}"
            
            # Send results
            embed = discord.Embed(
                title="Poll Results",
                description=results_text,
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.set_footer(text=f"Total votes: {total_votes}")
            
            await channel.send(embed=embed)
            
            # Store results
            self.poll_results[message_id] = {
                'question': poll['question'],
                'options': poll['options'],
                'votes': option_votes,
                'total_votes': total_votes,
                'winners': winning_options
            }
            
            # Clean up
            del self.active_polls[message_id]
            self.save_polls()
            
            print(f"✅ Closed poll {message_id} with {total_votes} votes")
            
        except Exception as e:
            print(f"❌ Error closing poll {message_id}: {e}")
    
    async def handle_reaction(self, payload: discord.RawReactionActionEvent):
        """Handle reactions on poll messages"""
        if payload.user_id == self.client.user.id:
            return
        
        if payload.message_id not in self.active_polls:
            return
        
        poll = self.active_polls[payload.message_id]
        
        # Check if poll has expired
        if datetime.now() > poll['expires_at']:
            await self.close_poll(payload.message_id)
            return
        
        # Check if voter is allowed
        if poll['allowed_voters']:
            guild = self.client.get_guild(payload.guild_id)
            if not guild:
                return
            
            member = guild.get_member(payload.user_id)
            if not member:
                return
            
            # Check if member has any of the allowed roles
            member_roles = [role.id for role in member.roles]
            if not any(role_id in member_roles for role_id in poll['allowed_voters']):
                # Remove reaction
                channel = self.client.get_channel(payload.channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(payload.message_id)
                        await message.remove_reaction(payload.emoji, member)
                    except:
                        pass
                return
        
        # Track voter
        poll['voters'].add(payload.user_id)
        
        # Parse which option was voted for
        try:
            # Extract number from emoji (e.g., "1⃣" -> 1)
            emoji_str = str(payload.emoji)
            if emoji_str.endswith('\u20e3'):  # Keycap
                option_num = int(emoji_str[0]) - 1
                if 0 <= option_num < len(poll['options']):
                    # Add vote
                    poll['votes'][option_num].append(payload.user_id)
        except:
            pass
        
        self.save_polls()
    
    async def cleanup_expired_polls(self):
        """Clean up expired polls"""
        current_time = datetime.now()
        expired_polls = []
        
        for message_id, poll_data in self.active_polls.items():
            if current_time > poll_data['expires_at']:
                expired_polls.append(message_id)
        
        for message_id in expired_polls:
            await self.close_poll(message_id)
