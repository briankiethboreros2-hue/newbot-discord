import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta

class PollVoting:
    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}
        
    async def create_poll(self, ctx, question, options, duration_minutes=5):
        """Create a poll with options"""
        try:
            poll = await ctx.send(f"**{question}**\n\n" + "\n".join([f"{i+1}. {option}" for i, option in enumerate(options)]))
            
            # Store poll info
            self.active_polls[poll.id] = {
                'question': question,
                'options': options,
                'votes': {i: [] for i in range(len(options))},
                'expires': datetime.utcnow() + timedelta(minutes=duration_minutes),
                'channel_id': ctx.channel.id,
                'author_id': ctx.author.id
            }
            
            return poll
        except Exception as e:
            print(f"Error creating poll: {e}")
            return None
    
    async def tally_poll_results(self, poll_id):
        """Tally poll results"""
        if poll_id not in self.active_polls:
            return None
            
        poll = self.active_polls[poll_id]
        votes = poll['votes']
        
        # Find winning option
        max_votes = 0
        winning_option = None
        
        for option_idx, voters in votes.items():
            if len(voters) > max_votes:
                max_votes = len(voters)
                winning_option = option_idx
        
        return {
            'winning_option': winning_option,
            'winning_option_text': poll['options'][winning_option] if winning_option is not None else None,
            'total_votes': sum(len(v) for v in votes.values()),
            'votes_by_option': {poll['options'][i]: len(v) for i, v in votes.items()}
        }
    
    async def check_expired_polls(self):
        """Check and clean up expired polls"""
        current_time = datetime.utcnow()
        expired_polls = []
        
        for poll_id, poll_data in self.active_polls.items():
            if current_time > poll_data['expires']:
                expired_polls.append(poll_id)
                
        for poll_id in expired_polls:
            await self.announce_poll_result(poll_id)
            del self.active_polls[poll_id]
    
    async def announce_poll_result(self, poll_id):
        """Announce poll results"""
        try:
            poll_data = self.active_polls.get(poll_id)
            if not poll_data:
                return
                
            results = await self.tally_poll_results(poll_id)
            if not results:
                return
                
            channel = self.bot.get_channel(poll_data['channel_id'])
            if channel:
                embed = discord.Embed(
                    title="Poll Results",
                    description=f"**{poll_data['question']}**",
                    color=discord.Color.green()
                )
                
                for option, votes in results['votes_by_option'].items():
                    embed.add_field(name=option, value=f"Votes: {votes}", inline=False)
                
                embed.add_field(name="Winner", value=results['winning_option_text'], inline=False)
                embed.add_field(name="Total Votes", value=results['total_votes'], inline=False)
                
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Error announcing poll results: {e}")
