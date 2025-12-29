"""
ENHANCED CLEANUP SYSTEM WITH STABILITY FIXES
- Prevents Cloudflare bans with rate limiting
- Fixes member display issues
- Prevents spamming
- Adds proper timeout handling
- Includes Discord profiles
"""

import discord
import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import aiohttp

class CleanupSystem:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.user_activity = self.load_json('data/user_activity.json', {})
        self.demoted_users = self.load_json('data/demoted_users.json', {})
        self.demotion_posts = self.load_json('data/demotion_posts.json', {})
        self.last_cleanup_run = 0
        self.last_demotion_post = {}
        
        # Rate limiting protection
        self.api_calls = []
        self.max_api_calls = 30  # Conservative limit
        self.api_window = 5
        
        # Configuration
        self.demotion_threshold = 15  # 15+ days for demotion
        self.ghost_threshold = 7      # 7+ days without roles
        self.cleanup_cooldown = 21600  # 6 hours between runs
        
        # Track recent operations to prevent duplicates
        self.recent_operations = {}
        
        print("✅ Cleanup system initialized with stability fixes")
    
    # ==================== UTILITY METHODS ====================
    
    def load_json(self, path, default):
        """Safe JSON loading with corruption recovery"""
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Error loading {path}: {e}, using default")
        return default
    
    def save_json(self, path, data):
        """Safe JSON saving with atomic write"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Write to temp file first
            temp_path = f"{path}.tmp"
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Atomic replace
            os.replace(temp_path, path)
            return True
        except Exception as e:
            print(f"❌ Error saving {path}: {e}")
            return False
    
    async def rate_limit_check(self):
        """Enforce rate limiting to prevent Cloudflare bans"""
        current_time = time.time()
        
        # Remove calls older than window
        self.api_calls = [t for t in self.api_calls if current_time - t < self.api_window]
        
        # If approaching limit, wait
        if len(self.api_calls) >= self.max_api_calls:
            oldest_call = self.api_calls[0]
            wait_time = self.api_window - (current_time - oldest_call) + 0.1
            if wait_time > 0:
                print(f"⏱️ Cleanup system rate limit approaching, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.api_calls = []
        
        # Record this call
        self.api_calls.append(current_time)
    
    def cleanup_old_tracking(self):
        """Remove old tracking data to prevent memory bloat"""
        current_time = time.time()
        week_ago = current_time - (7 * 86400)
        
        # Clean user activity older than 30 days
        if hasattr(self, 'user_activity'):
            for user_id in list(self.user_activity.keys()):
                last_seen = self.user_activity[user_id].get('last_seen', 0)
                if last_seen < week_ago:
                    del self.user_activity[user_id]
        
        # Clean recent operations older than 1 hour
        for key in list(self.recent_operations.keys()):
            if current_time - self.recent_operations[key] > 3600:
                del self.recent_operations[key]
    
    # ==================== ACTIVITY TRACKING ====================
    
    async def track_user_activity(self, user_id, activity_type="message"):
        """Track user activity with rate limiting"""
        try:
            await self.rate_limit_check()
            
            uid = str(user_id)
            current_time = time.time()
            
            if uid not in self.user_activity:
                self.user_activity[uid] = {
                    'last_seen': current_time,
                    'last_message': current_time,
                    'last_presence': current_time,
                    'activities': []
                }
            
            self.user_activity[uid]['last_seen'] = current_time
            
            if activity_type == "message":
                self.user_activity[uid]['last_message'] = current_time
            elif activity_type == "presence_update":
                self.user_activity[uid]['last_presence'] = current_time
            
            # Track last 10 activities
            self.user_activity[uid]['activities'].append({
                'type': activity_type,
                'time': current_time
            })
            
            if len(self.user_activity[uid]['activities']) > 10:
                self.user_activity[uid]['activities'] = self.user_activity[uid]['activities'][-10:]
            
            # Save periodically (not every time)
            if int(current_time) % 300 == 0:  # Every 5 minutes
                self.save_all_data()
                
        except Exception as e:
            print(f"⚠️ Error tracking activity: {e}")
    
    def get_last_activity(self, user_id):
        """Get last activity timestamp for a user"""
        uid = str(user_id)
        if uid in self.user_activity:
            return self.user_activity[uid].get('last_seen')
        return None
    
    def calculate_days_inactive(self, last_activity_timestamp):
        """Calculate days inactive from timestamp"""
        if not last_activity_timestamp:
            return 999  # Default for unknown
        
        current_time = time.time()
        days_inactive = (current_time - last_activity_timestamp) / 86400
        return int(days_inactive)
    
    # ==================== DEMOTION SYSTEM ====================
    
    async def check_demotion_candidates(self, guild):
        """Check for demotion candidates (15+ days inactive)"""
        try:
            imperius_role = guild.get_role(self.config['roles'].get('imperius'))
            demoted_role = guild.get_role(self.config['roles'].get('demoted'))
            
            if not imperius_role or not demoted_role:
                print("❌ Required roles not found for demotion check")
                return []
            
            candidates = []
            
            for member in imperius_role.members:
                if member.bot:
                    continue
                
                # Check if already demoted
                if demoted_role in member.roles:
                    continue
                
                # Check for recent operation
                operation_key = f"demotion_check_{member.id}"
                if operation_key in self.recent_operations:
                    continue
                
                self.recent_operations[operation_key] = time.time()
                
                # Get activity
                last_active = self.get_last_activity(member.id)
                days_inactive = self.calculate_days_inactive(last_active)
                
                # Check threshold (15+ days)
                if days_inactive >= self.demotion_threshold:
                    candidates.append({
                        'member': member,
                        'days_inactive': days_inactive,
                        'last_active': last_active
                    })
                
                # Small delay to prevent rate limiting
                await asyncio.sleep(0.1)
            
            return candidates
            
        except Exception as e:
            print(f"❌ Error in demotion check: {e}")
            return []
    
    async def send_demotion_post(self, member_data):
        """Send demotion candidate post with proper formatting"""
        try:
            await self.rate_limit_check()
            
            member = member_data['member']
            days_inactive = member_data['days_inactive']
            last_active = member_data['last_active']
            
            # Check for duplicate recent post
            member_id = str(member.id)
            if member_id in self.last_demotion_post:
                last_post_time = self.last_demotion_post[member_id]
                if time.time() - last_post_time < 86400:  # 24 hours
                    print(f"⏭️ Skipping duplicate demotion post for {member.display_name}")
                    return None
            
            cleanup_channel = self.client.get_channel(self.config['channels'].get('cleanup'))
            if not cleanup_channel:
                print("❌ Cleanup channel not found")
                return None
            
            # Format last active
            if last_active:
                last_active_dt = datetime.fromtimestamp(last_active, tz=timezone.utc)
                last_active_str = last_active_dt.strftime("%Y-%m-%d %H:%M UTC")
            else:
                last_active_str = "Unknown"
            
            # Get member's top roles (excluding @everyone)
            member_roles = [role for role in member.roles if role.name != "@everyone"]
            top_role = member_roles[-1].name if member_roles else "No special roles"
            
            # Create embed
            embed = discord.Embed(
                title="🟡 Demotion Candidate",
                description=f"**{member.display_name}** is inactive for **{days_inactive} days**",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Member info with avatar
            embed.set_thumbnail(url=member.display_avatar.url)
            
            embed.add_field(
                name="👤 Member Information",
                value=f"**Name:** {member.display_name}\n"
                      f"**ID:** `{member.id}`\n"
                      f"**Server Join:** {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'}\n"
                      f"**Top Role:** {top_role}",
                inline=False
            )
            
            embed.add_field(
                name="📊 Activity Status",
                value=f"**Last Active:** {last_active_str}\n"
                      f"**Days Inactive:** {days_inactive}\n"
                      f"**Current Status:** {str(member.status).title()}",
                inline=False
            )
            
            embed.add_field(
                name="⚖️ Required Actions",
                value="React below to vote:\n"
                      "⬇️ - **Demote**: Keep in server with inactive role\n"
                      "👢 - **Kick**: Remove from server\n"
                      "✅ - **Spare**: Keep current role (needs 2+ admin votes)",
                inline=False
            )
            
            embed.set_footer(
                text=f"Member ID: {member.id} • Votes will be tallied for 48 hours"
            )
            
            # Send message
            message = await cleanup_channel.send(embed=embed)
            
            # Add reaction buttons
            await message.add_reaction("⬇️")   # Demote
            await message.add_reaction("👢")   # Kick
            await message.add_reaction("✅")   # Spare
            
            # Track this post
            self.last_demotion_post[member_id] = time.time()
            
            if member_id not in self.demotion_posts:
                self.demotion_posts[member_id] = []
            
            self.demotion_posts[member_id].append({
                'message_id': message.id,
                'channel_id': cleanup_channel.id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'member_name': member.display_name,
                'days_inactive': days_inactive
            })
            
            self.save_json('data/demotion_posts.json', self.demotion_posts)
            
            print(f"📝 Demotion post created for {member.display_name} ({days_inactive} days inactive)")
            return message
            
        except discord.HTTPException as e:
            if e.status == 429:
                print(f"🛑 Rate limited sending demotion post, waiting...")
                await asyncio.sleep(getattr(e, 'retry_after', 30))
                return await self.send_demotion_post(member_data)
            else:
                print(f"❌ HTTP error sending demotion post: {e}")
                return None
        except Exception as e:
            print(f"❌ Error sending demotion post: {e}")
            return None
    
    # ==================== GHOST CLEANUP SYSTEM ====================
    
    async def check_ghost_users(self, guild):
        """Check for ghost users (7+ days without roles & inactive)"""
        try:
            ghosts = []
            
            # Get all members without roles (except @everyone)
            for member in guild.members:
                if member.bot:
                    continue
                
                # Check if member has any roles besides @everyone
                has_roles = len([r for r in member.roles if r.name != "@everyone"]) > 0
                if has_roles:
                    continue
                
                # Check for recent operation
                operation_key = f"ghost_check_{member.id}"
                if operation_key in self.recent_operations:
                    continue
                
                self.recent_operations[operation_key] = time.time()
                
                # Get activity
                last_active = self.get_last_activity(member.id)
                days_inactive = self.calculate_days_inactive(last_active)
                
                # Check threshold (7+ days)
                if days_inactive >= self.ghost_threshold:
                    ghosts.append({
                        'member': member,
                        'days_inactive': days_inactive,
                        'last_active': last_active,
                        'join_date': member.joined_at
                    })
                
                # Small delay
                await asyncio.sleep(0.1)
            
            return ghosts
            
        except Exception as e:
            print(f"❌ Error in ghost check: {e}")
            return []
    
    async def send_ghost_report(self, ghost_data):
        """Send ghost user report"""
        try:
            await self.rate_limit_check()
            
            member = ghost_data['member']
            days_inactive = ghost_data['days_inactive']
            last_active = ghost_data['last_active']
            join_date = ghost_data['join_date']
            
            cleanup_channel = self.client.get_channel(self.config['channels'].get('cleanup'))
            if not cleanup_channel:
                print("❌ Cleanup channel not found")
                return None
            
            # Format dates
            if last_active:
                last_active_dt = datetime.fromtimestamp(last_active, tz=timezone.utc)
                last_active_str = last_active_dt.strftime("%Y-%m-%d %H:%M UTC")
            else:
                last_active_str = "Unknown"
            
            join_date_str = join_date.strftime("%Y-%m-%d") if join_date else "Unknown"
            
            # Create embed
            embed = discord.Embed(
                title="👻 Ghost User Detected",
                description=f"User with no roles inactive for **{days_inactive} days**",
                color=discord.Color.dark_gray(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Member info with avatar
            embed.set_thumbnail(url=member.display_avatar.url)
            
            embed.add_field(
                name="👤 User Information",
                value=f"**Name:** {member.display_name}\n"
                      f"**ID:** `{member.id}`\n"
                      f"**Discord:** {member.name}#{member.discriminator}\n"
                      f"**Server Join:** {join_date_str}",
                inline=False
            )
            
            embed.add_field(
                name="📊 Activity Status",
                value=f"**Last Active:** {last_active_str}\n"
                      f"**Days Inactive:** {days_inactive}\n"
                      f"**Current Status:** {str(member.status).title()}\n"
                      f"**Roles:** No roles assigned",
                inline=False
            )
            
            embed.add_field(
                name="⚠️ Recommended Action",
                value="This user has been inactive for 7+ days with no roles.\n"
                      "Consider removing them to keep the server clean.",
                inline=False
            )
            
            embed.set_footer(text=f"User ID: {member.id} • Detected on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
            
            # Send message
            message = await cleanup_channel.send(embed=embed)
            
            print(f"👻 Ghost report created for {member.display_name} ({days_inactive} days inactive)")
            return message
            
        except discord.HTTPException as e:
            if e.status == 429:
                print(f"🛑 Rate limited sending ghost report, waiting...")
                await asyncio.sleep(getattr(e, 'retry_after', 30))
                return await self.send_ghost_report(ghost_data)
            else:
                print(f"❌ HTTP error sending ghost report: {e}")
                return None
        except Exception as e:
            print(f"❌ Error sending ghost report: {e}")
            return None
    
    # ==================== MAIN CLEANUP METHODS ====================
    
    async def run_cleanup_check(self, guild):
        """Main cleanup check with anti-spam and rate limiting"""
        try:
            current_time = time.time()
            
            # Check cooldown (6 hours minimum between runs)
            if current_time - self.last_cleanup_run < self.cleanup_cooldown:
                print(f"⏭️ Cleanup check on cooldown. Next run in {int((self.cleanup_cooldown - (current_time - self.last_cleanup_run)) / 3600)} hours")
                return
            
            print(f"🧹 Starting cleanup check for {guild.name}...")
            
            # Run checks with delays between them
            demotion_candidates = await self.check_demotion_candidates(guild)
            await asyncio.sleep(2)  # Delay between checks
            
            ghost_users = await self.check_ghost_users(guild)
            
            # Process demotion candidates
            demotion_count = 0
            for candidate in demotion_candidates:
                # Check if we should stop due to rate limiting
                if len(self.api_calls) >= self.max_api_calls - 5:
                    print("⚠️ Approaching rate limit, pausing demotion posts")
                    await asyncio.sleep(5)
                
                message = await self.send_demotion_post(candidate)
                if message:
                    demotion_count += 1
                    await asyncio.sleep(3)  # Delay between posts
            
            # Process ghost users
            ghost_count = 0
            for ghost in ghost_users:
                if len(self.api_calls) >= self.max_api_calls - 5:
                    print("⚠️ Approaching rate limit, pausing ghost reports")
                    await asyncio.sleep(5)
                
                message = await self.send_ghost_report(ghost)
                if message:
                    ghost_count += 1
                    await asyncio.sleep(3)  # Delay between posts
            
            # Update last run time
            self.last_cleanup_run = current_time
            
            # Cleanup old tracking data
            self.cleanup_old_tracking()
            
            print(f"✅ Cleanup check completed:")
            print(f"   Demotion candidates: {demotion_count}")
            print(f"   Ghost users: {ghost_count}")
            print(f"   Next check in 6 hours")
            
        except Exception as e:
            print(f"❌ Error in main cleanup check: {e}")
            import traceback
            traceback.print_exc()
    
    async def handle_user_return(self, member):
        """Handle when a demoted user returns"""
        try:
            demoted_role = member.guild.get_role(self.config['roles'].get('demoted'))
            imperius_role = member.guild.get_role(self.config['roles'].get('imperius'))
            
            if demoted_role and demoted_role in member.roles:
                # Remove demoted role
                await member.remove_roles(demoted_role)
                
                # Add back imperius role
                if imperius_role:
                    await member.add_roles(imperius_role)
                
                # Send welcome back message
                welcome_ch = self.client.get_channel(self.config['channels'].get('welcome'))
                if welcome_ch:
                    embed = discord.Embed(
                        title="🎉 Welcome Back!",
                        description=f"{member.mention} has returned and been restored to **Imperius** role!",
                        color=discord.Color.green()
                    )
                    await welcome_ch.send(embed=embed)
                
                print(f"✅ Restored {member.display_name} to Imperius role")
                
        except Exception as e:
            print(f"❌ Error handling user return: {e}")
    
    # ==================== REACTION HANDLING ====================
    
    async def handle_demotion_reaction(self, payload):
        """Handle reactions on demotion posts"""
        try:
            # Only process in cleanup channel
            cleanup_ch_id = self.config['channels'].get('cleanup')
            if payload.channel_id != cleanup_ch_id:
                return
            
            # Get the message
            channel = self.client.get_channel(payload.channel_id)
            if not channel:
                return
            
            try:
                message = await channel.fetch_message(payload.message_id)
            except:
                return
            
            # Check if it's a demotion post (has specific reactions)
            if not any(str(r.emoji) in ["⬇️", "👢", "✅"] for r in message.reactions):
                return
            
            # Get reactor
            guild = self.client.get_guild(payload.guild_id)
            reactor = guild.get_member(payload.user_id)
            
            if not reactor or reactor.bot:
                return
            
            # Check if reactor is admin
            reactor_roles = [r.id for r in reactor.roles]
            admin_roles = self.config.get('admin_roles', [])
            
            if not any(role_id in admin_roles for role_id in reactor_roles):
                # Remove non-admin reaction
                await message.remove_reaction(payload.emoji, reactor)
                return
            
            # Parse member ID from embed footer
            if not message.embeds:
                return
            
            embed = message.embeds[0]
            footer = embed.footer.text
            
            # Extract member ID from footer
            import re
            match = re.search(r'Member ID: (\d+)', footer)
            if not match:
                return
            
            member_id = int(match.group(1))
            member = guild.get_member(member_id)
            
            if not member:
                print(f"❌ Member {member_id} not found in guild")
                return
            
            # Count votes
            reactions = message.reactions
            vote_counts = {}
            
            for reaction in reactions:
                emoji = str(reaction.emoji)
                if emoji in ["⬇️", "👢", "✅"]:
                    # Get users who reacted (excluding bots)
                    users = [user async for user in reaction.users() if not user.bot]
                    vote_counts[emoji] = len(users)
            
            print(f"📊 Vote counts for {member.display_name}: {vote_counts}")
            
            # Check if we have a decision (2+ votes for any action)
            for emoji, count in vote_counts.items():
                if count >= 2:
                    await self.process_demotion_decision(member, emoji, message)
                    break
            
        except Exception as e:
            print(f"❌ Error handling demotion reaction: {e}")
    
    async def process_demotion_decision(self, member, decision_emoji, message):
        """Process the final demotion decision"""
        try:
            guild = member.guild
            imperius_role = guild.get_role(self.config['roles'].get('imperius'))
            demoted_role = guild.get_role(self.config['roles'].get('demoted'))
            
            if decision_emoji == "⬇️":  # Demote
                if imperius_role in member.roles and demoted_role:
                    await member.remove_roles(imperius_role)
                    await member.add_roles(demoted_role)
                    
                    # Update embed
                    embed = message.embeds[0]
                    embed.color = discord.Color.blue()
                    embed.add_field(
                        name="✅ Decision Reached",
                        value=f"**DEMOTED** by admin vote\n"
                              f"{member.display_name} has been moved to Demoted role.",
                        inline=False
                    )
                    
                    await message.edit(embed=embed)
                    
                    # Send DM
                    try:
                        await member.send(
                            f"👋 Hello {member.display_name},\n\n"
                            f"Due to extended inactivity, you have been moved to the **Demoted** role in **{guild.name}**.\n"
                            f"You can regain your Imperius role by becoming active again!\n\n"
                            f"Last active: {embed.fields[1].value.split('**Last Active:** ')[1].split('\\n')[0]}"
                        )
                    except:
                        pass
                    
                    print(f"✅ Demoted {member.display_name}")
            
            elif decision_emoji == "👢":  # Kick
                # Check bot permissions
                bot_member = guild.get_member(self.client.user.id)
                if bot_member.guild_permissions.kick_members:
                    await member.kick(reason="Inactive for 15+ days (admin vote)")
                    
                    # Update embed
                    embed = message.embeds[0]
                    embed.color = discord.Color.red()
                    embed.add_field(
                        name="✅ Decision Reached",
                        value=f"**KICKED** by admin vote\n"
                              f"{member.display_name} has been removed from the server.",
                        inline=False
                    )
                    
                    await message.edit(embed=embed)
                    print(f"✅ Kicked {member.display_name}")
            
            elif decision_emoji == "✅":  # Spare
                # Update embed
                embed = message.embeds[0]
                embed.color = discord.Color.green()
                embed.add_field(
                    name="✅ Decision Reached",
                    value=f"**SPARED** by admin vote\n"
                          f"{member.display_name} will keep their current role.",
                    inline=False
                )
                
                await message.edit(embed=embed)
                print(f"✅ Spared {member.display_name}")
            
            # Clear reactions to prevent further voting
            await message.clear_reactions()
            
        except discord.Forbidden:
            print(f"❌ Bot lacks permissions to modify {member.display_name}")
        except Exception as e:
            print(f"❌ Error processing demotion decision: {e}")
    
    # ==================== DATA MANAGEMENT ====================
    
    def save_all_data(self):
        """Save all data files"""
        self.save_json('data/user_activity.json', self.user_activity)
        self.save_json('data/demoted_users.json', self.demoted_users)
        self.save_json('data/demotion_posts.json', self.demotion_posts)
        print("💾 Cleanup system data saved")
    
    async def cleanup_old_data(self):
        """Clean up old demotion posts data"""
        try:
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            
            for member_id in list(self.demotion_posts.keys()):
                # Remove posts older than 7 days
                self.demotion_posts[member_id] = [
                    post for post in self.demotion_posts[member_id]
                    if datetime.fromisoformat(post['timestamp'].replace('Z', '+00:00')) > week_ago
                ]
                
                # Remove empty entries
                if not self.demotion_posts[member_id]:
                    del self.demotion_posts[member_id]
            
            self.save_json('data/demotion_posts.json', self.demotion_posts)
            print("🧹 Cleaned up old demotion posts data")
            
        except Exception as e:
            print(f"❌ Error cleaning old data: {e}")
