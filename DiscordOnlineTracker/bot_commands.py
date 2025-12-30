import discord
from discord.ext import commands
from datetime import datetime

def setup(bot):
    """Setup function to add commands to bot"""
    
    @bot.command(name='test')
    async def test_command(ctx):
        """Test if commands work"""
        await ctx.send("✅ Test command works! Bot is responding.")
    
    @bot.command(name='status')
    async def status_command(ctx):
        """Check bot status"""
        bot_instance = ctx.bot
        uptime = datetime.now() - bot_instance.bot_start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds // 60) % 60
        
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="🏃 Uptime", value=f"{days}d {hours}h {minutes}m", inline=True)
        embed.add_field(name="🏰 Guild", value=bot_instance.main_guild.name if hasattr(bot_instance, 'main_guild') and bot_instance.main_guild else "None", inline=True)
        embed.add_field(name="👤 Members", value=bot_instance.main_guild.member_count if hasattr(bot_instance, 'main_guild') and bot_instance.main_guild else "0", inline=True)
        
        # System status
        systems = []
        if hasattr(bot_instance, 'recruitment') and bot_instance.recruitment: 
            systems.append("✅ Recruitment")
        if hasattr(bot_instance, 'online_announce') and bot_instance.online_announce: 
            systems.append("✅ Online Announce")
        if hasattr(bot_instance, 'cleanup_system') and bot_instance.cleanup_system: 
            systems.append("✅ Cleanup")
        
        embed.add_field(name="🔧 Systems", value="\n".join(systems) if systems else "❌ None", inline=False)
        
        await ctx.send(embed=embed)
    
    @bot.command(name='cleanup')
    @commands.has_permissions(administrator=True)
    async def manual_cleanup(ctx):
        """Manually trigger cleanup system"""
        bot_instance = ctx.bot
        await ctx.send("🚀 Running manual cleanup...")
        
        if hasattr(bot_instance, 'cleanup_system') and bot_instance.cleanup_system:
            try:
                # Run ghost user check
                await ctx.send("👻 Checking ghost users...")
                await bot_instance.cleanup_system.check_ghost_users()
                
                # Run inactive member check
                await ctx.send("😴 Checking inactive members...")
                await bot_instance.cleanup_system.check_inactive_members_15day_cycle()
                
                await ctx.send("✅ Cleanup completed!")
            except Exception as e:
                await ctx.send(f"❌ Error during cleanup: {e}")
        else:
            await ctx.send("❌ Cleanup system not initialized")
    
    @bot.command(name='resetcheck')
    @commands.has_permissions(administrator=True)
    async def reset_member_check(ctx, member: discord.Member = None):
        """Reset a member's inactivity check date"""
        bot_instance = ctx.bot
        if not member:
            await ctx.send("❌ Please mention a member: `!resetcheck @username`")
            return
        
        if not hasattr(bot_instance, 'cleanup_system') or not bot_instance.cleanup_system:
            await ctx.send("❌ Cleanup system not initialized")
            return
        
        if hasattr(bot_instance.cleanup_system, 'member_last_check'):
            bot_instance.cleanup_system.member_last_check[member.id] = datetime.now()
            await ctx.send(f"✅ Reset check date for {member.mention} to today")
        else:
            await ctx.send("❌ Check tracking not available")
    
    @bot.command(name='interview')
    @commands.has_permissions(administrator=True)
    async def force_interview(ctx, member: discord.Member = None):
        """Force start an interview for a member"""
        bot_instance = ctx.bot
        if not member:
            await ctx.send("❌ Please mention a member: `!interview @username`")
            return
        
        if not hasattr(bot_instance, 'recruitment') or not bot_instance.recruitment:
            await ctx.send("❌ Recruitment system not initialized")
            return
        
        await ctx.send(f"📝 Starting interview for {member.mention}...")
        try:
            await bot_instance.recruitment.start_dm_interview(member)
            await ctx.send(f"✅ Interview started! Check DMs with {member.name}")
        except discord.Forbidden:
            await ctx.send(f"❌ Cannot DM {member.mention}. They may have DMs disabled.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    
    @bot.command(name='checkmember')
    @commands.has_permissions(administrator=True)
    async def check_member_status(ctx, member: discord.Member = None):
        """Check a member's status"""
        bot_instance = ctx.bot
        if not member:
            await ctx.send("❌ Please mention a member: `!checkmember @username`")
            return
        
        embed = discord.Embed(
            title=f"📊 Member Status: {member.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Avatar
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        
        # Basic info
        embed.add_field(name="📛 Name", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="🆔 ID", value=member.id, inline=True)
        embed.add_field(name="🤖 Bot", value="✅ Yes" if member.bot else "❌ No", inline=True)
        
        # Roles
        role_names = [role.name for role in member.roles if role.name != "@everyone"]
        embed.add_field(name="👑 Roles", value=", ".join(role_names) if role_names else "No roles", inline=False)
        
        # Check if in cleanup tracking
        if (hasattr(bot_instance, 'cleanup_system') and bot_instance.cleanup_system and 
            hasattr(bot_instance.cleanup_system, 'member_last_check')):
            last_check = bot_instance.cleanup_system.member_last_check.get(member.id)
            if last_check:
                days_ago = (datetime.now() - last_check).days
                embed.add_field(name="📅 Last Check", value=f"{last_check.strftime('%Y-%m-%d')} ({days_ago} days ago)", inline=True)
            else:
                embed.add_field(name="📅 Last Check", value="Never checked", inline=True)
        
        # Dates
        if member.joined_at:
            join_date = member.joined_at.replace(tzinfo=None) if member.joined_at.tzinfo else member.joined_at
            days_in_server = (datetime.now() - join_date).days
            embed.add_field(name="📅 Joined", value=f"{join_date.strftime('%Y-%m-%d')} ({days_in_server} days ago)", inline=True)
        
        if member.created_at:
            create_date = member.created_at.replace(tzinfo=None) if member.created_at.tzinfo else member.created_at
            account_age = (datetime.now() - create_date).days
            embed.add_field(name="📅 Account Age", value=f"{account_age} days", inline=True)
        
        # Status
        embed.add_field(name="📱 Status", value=str(member.status).title(), inline=True)
        
        await ctx.send(embed=embed)
    
    @bot.command(name='help')
    async def help_command(ctx):
        """Show available commands"""
        embed = discord.Embed(
            title="🤖 Impèrius Bot Commands",
            description="Prefix: `!`",
            color=discord.Color.green()
        )
        
        # Admin commands
        admin_cmds = [
            ("`!cleanup`", "Run manual cleanup (ghost + inactive check)"),
            ("`!resetcheck @user`", "Reset member's inactivity check date"),
            ("`!interview @user`", "Force start interview for member"),
            ("`!checkmember @user`", "Check member's detailed status")
        ]
        
        # Public commands
        public_cmds = [
            ("`!status`", "Check bot status"),
            ("`!help`", "Show this help message"),
            ("`!test`", "Test if commands work")
        ]
        
        embed.add_field(
            name="👑 Admin Commands",
            value="\n".join([f"**{cmd}** - {desc}" for cmd, desc in admin_cmds]),
            inline=False
        )
        
        embed.add_field(
            name="👥 Public Commands",
            value="\n".join([f"**{cmd}** - {desc}" for cmd, desc in public_cmds]),
            inline=False
        )
        
        embed.set_footer(text="Bot automatically handles interviews, online tracking, and cleanup")
        
        await ctx.send(embed=embed)
    
    print("✅ Commands have been registered with the bot")
