# modules/role_manager.py - Role management system
import discord
from typing import Optional, List
from utils.logger import logger
from utils.error_handler import with_error_handling
from config import Config

class RoleManager:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    async def initialize(self):
        """Initialize role manager"""
        logger.info("Role manager initialized")
    
    @with_error_handling
    async def promote_to_imperius(self, member: discord.Member, reason: str = "") -> bool:
        """Promote a member to Imperius role"""
        guild = member.guild
        
        # Get roles
        imperius_role = guild.get_role(Config.IMPERIUS_ROLE_ID)
        inactive_role = guild.get_role(Config.INACTIVE_ROLE_ID)
        
        if not imperius_role:
            logger.error(f"Imperius role not found: {Config.IMPERIUS_ROLE_ID}")
            return False
        
        # Remove inactive role if present
        if inactive_role and inactive_role in member.roles:
            await self.safe_role_change(
                member=member,
                remove_role=inactive_role,
                add_role=imperius_role
            )
        else:
            # Just add Imperius role
            await self.safe_role_change(
                member=member,
                add_role=imperius_role
            )
        
        # Update database
        await self.db.update_user_status(
            user_id=member.id,
            status='active',
            notes=f"Promoted to Imperius: {reason}",
            role_id=Config.IMPERIUS_ROLE_ID
        )
        
        # Log action
        await self.db.log_cleanup_action(
            user_id=member.id,
            action_type="promoted",
            reason=reason,
            performed_by=self.bot.user.id
        )
        
        # Send welcome back message
        main_channel = guild.get_channel(Config.MAIN_CHANNEL_ID)
        if main_channel:
            await main_channel.send(
                f"🎉 Welcome back {member.mention}! "
                f"You have been promoted to <@&{Config.IMPERIUS_ROLE_ID}>."
            )
        
        logger.info(f"Promoted {member.name} to Imperius: {reason}")
        return True
    
    @with_error_handling
    async def demote_to_inactive(self, member: discord.Member, reason: str = "") -> bool:
        """Demote a member to inactive role"""
        guild = member.guild
        
        # Get roles
        imperius_role = guild.get_role(Config.IMPERIUS_ROLE_ID)
        inactive_role = guild.get_role(Config.INACTIVE_ROLE_ID)
        
        if not imperius_role or not inactive_role:
            logger.error(f"Roles not found: Imperius={Config.IMPERIUS_ROLE_ID}, Inactive={Config.INACTIVE_ROLE_ID}")
            return False
        
        # Check if user has protected admin roles
        has_protected_role = any(
            role.id in Config.PROTECTED_ROLE_IDS for role in member.roles
        )
        
        if has_protected_role:
            logger.warning(f"Cannot demote protected admin user: {member.name}")
            return False
        
        # Remove Imperius role, add inactive role
        await self.safe_role_change(
            member=member,
            remove_role=imperius_role,
            add_role=inactive_role
        )
        
        # Update channel permissions for inactive role
        await self._update_inactive_permissions(guild, inactive_role)
        
        # Update database
        await self.db.update_user_status(
            user_id=member.id,
            status='inactive',
            notes=f"Demoted to inactive: {reason}",
            role_id=Config.INACTIVE_ROLE_ID
        )
        
        # Log action
        await self.db.log_cleanup_action(
            user_id=member.id,
            action_type="demoted",
            reason=reason,
            performed_by=self.bot.user.id
        )
        
        # Send notification to cleanup channel
        cleanup_channel = guild.get_channel(Config.CLEANUP_CHANNEL_ID)
        if cleanup_channel:
            embed = discord.Embed(
                title="😔 User Demoted",
                description=f"{member.mention} has been demoted to <@&{Config.INACTIVE_ROLE_ID}>",
                color=0xff5555
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="User ID", value=member.id, inline=True)
            embed.timestamp = discord.utils.utcnow()
            
            await cleanup_channel.send(embed=embed)
        
        logger.info(f"Demoted {member.name} to inactive: {reason}")
        return True
    
    @with_error_handling
    async def safe_role_change(self, member: discord.Member, 
                              add_role: Optional[discord.Role] = None,
                              remove_role: Optional[discord.Role] = None) -> bool:
        """Safely change roles with error handling"""
        try:
            # Remove role if specified
            if remove_role and remove_role in member.roles:
                await member.remove_roles(remove_role, reason="Bot cleanup system")
            
            # Add role if specified
            if add_role and add_role not in member.roles:
                await member.add_roles(add_role, reason="Bot cleanup system")
            
            return True
            
        except discord.Forbidden:
            logger.error(f"Permission denied to modify roles for {member.name}")
            # Notify admins
            await self._notify_role_change_failed(member, add_role, remove_role)
            return False
            
        except discord.HTTPException as e:
            logger.error(f"HTTP error modifying roles for {member.name}: {e}")
            return False
    
    async def _update_inactive_permissions(self, guild: discord.Guild, inactive_role: discord.Role):
        """Update channel permissions for inactive role"""
        try:
            # Deny access to most channels
            for channel in guild.channels:
                # Skip allowed channels
                if channel.id in [Config.MAIN_CHANNEL_ID, Config.CALL_CHANNEL_ID]:
                    continue
                
                # Deny view permission for other channels
                if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    try:
                        # Get current permissions
                        current_perms = channel.permissions_for(inactive_role)
                        
                        # Only update if needed
                        if current_perms.view_channel:
                            await channel.set_permissions(
                                inactive_role,
                                view_channel=False,
                                send_messages=False,
                                connect=False,
                                speak=False,
                                reason="Inactive role permissions"
                            )
                    except:
                        continue  # Skip if can't modify
            
            # Ensure access to main and call channels
            main_channel = guild.get_channel(Config.MAIN_CHANNEL_ID)
            call_channel = guild.get_channel(Config.CALL_CHANNEL_ID)
            
            if main_channel:
                await main_channel.set_permissions(
                    inactive_role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    reason="Inactive role permissions"
                )
            
            if call_channel:
                await call_channel.set_permissions(
                    inactive_role,
                    view_channel=True,
                    connect=True,
                    speak=True,
                    reason="Inactive role permissions"
                )
                
        except Exception as e:
            logger.error(f"Error updating inactive permissions: {e}")
    
    async def _notify_role_change_failed(self, member: discord.Member, 
                                        add_role: Optional[discord.Role],
                                        remove_role: Optional[discord.Role]):
        """Notify admins when role change fails"""
        admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
        if not admin_channel:
            return
        
        action_desc = []
        if remove_role:
            action_desc.append(f"remove {remove_role.name}")
        if add_role:
            action_desc.append(f"add {add_role.name}")
        
        await admin_channel.send(
            f"🚨 **ROLE CHANGE FAILED**\n"
            f"**User:** {member.mention} ({member.id})\n"
            f"**Action:** {' and '.join(action_desc)}\n"
            f"**Reason:** Bot lacks permissions or role hierarchy issue\n\n"
            f"Please check:\n"
            f"1. Bot role is above target roles\n"
            f"2. Bot has 'Manage Roles' permission\n"
            f"3. Target user is not above bot in hierarchy"
        )
    
    @with_error_handling
    async def get_user_roles_info(self, member: discord.Member) -> discord.Embed:
        """Get information about user's roles"""
        embed = discord.Embed(
            title=f"👑 Role Information: {member.name}",
            color=member.color if member.color else 0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        
        # Add role list
        roles = [role for role in member.roles if role.name != "@everyone"]
        
        if roles:
            role_list = "\n".join([f"• {role.mention} ({role.id})" for role in roles])
            embed.add_field(name="Current Roles", value=role_list[:1024], inline=False)
        else:
            embed.add_field(name="Current Roles", value="No roles (ghost user)", inline=False)
        
        # Add protected status
        has_protected = any(role.id in Config.PROTECTED_ROLE_IDS for role in member.roles)
        embed.add_field(name="Protected Admin", value="✅ Yes" if has_protected else "❌ No", inline=True)
        
        # Add Imperius status
        has_imperius = any(role.id == Config.IMPERIUS_ROLE_ID for role in member.roles)
        embed.add_field(name="Imperius Role", value="✅ Yes" if has_imperius else "❌ No", inline=True)
        
        # Add Inactive status
        has_inactive = any(role.id == Config.INACTIVE_ROLE_ID for role in member.roles)
        embed.add_field(name="Inactive Role", value="✅ Yes" if has_inactive else "❌ No", inline=True)
        
        # Get user info from database
        user_info = await self.db.get_user_info(member.id)
        if user_info:
            embed.add_field(
                name="Database Status", 
                value=user_info['status'].title(), 
                inline=True
            )
            
            if user_info['days_inactive'] > 0:
                embed.add_field(
                    name="Days Inactive", 
                    value=str(user_info['days_inactive']), 
                    inline=True
                )
        
        embed.set_footer(text=f"User ID: {member.id}")
        
        return embed
