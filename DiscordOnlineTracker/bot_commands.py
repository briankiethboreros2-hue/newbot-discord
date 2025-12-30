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
        bot = ctx.bot
        uptime = datetime.now() - bot.bot_start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds // 60) % 60
        
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="🏃 Uptime", value=f"{days}d {hours}h {minutes}m", inline=True)
        embed.add_field(name="🏰 Guild", value=bot.main_guild.name if hasattr(bot, 'main_guild') and bot.main_guild else "None", inline=True)
        embed.add_field(name="👤 Members", value=bot.main_guild.member_count if hasattr(bot, 'main_guild') and bot.main_guild else "0", inline=True)
        
        # System status
        systems = []
        if hasattr(bot, 'recruitment') and bot.recruitment: systems.append("✅ Recruitment")
        if hasattr(bot, 'online_announce') and bot.online_announce: systems.append("✅ Online Announce")
        if hasattr(bot, 'cleanup_system') and bot.cleanup_system: systems.append("✅ Cleanup")
        
        embed.add_field(name="🔧 Systems", value="\n".join(systems) if systems else "❌ None", inline=False)
        
        await ctx.send(embed=embed)
    
    @bot.command(name='cleanup')
    @commands.has_permissions(administrator=True)
    async def manual_cleanup(ctx):
        """Manually trigger cleanup system"""
        bot = ctx.bot
        await ctx.send("🚀 Running manual cleanup...")
        
        if hasattr(bot, 'cleanup_system') and bot.cleanup_system:
            try:
                # Run ghost user check
                await ctx.send("👻 Checking ghost users...")
                await bot.cleanup_system.check_ghost_users()
                
                # Run inactive member check
                await ctx.send("😴 Checking inactive members...")
                await bot.cleanup_system.check_inactive_members_15day_cycle()
                
                await ctx.send("✅ Cleanup completed!")
            except Exception as e:
                await ctx.send(f"❌ Error during cleanup: {e}")
        else:
            await ctx.send("❌ Cleanup system not initialized")
    
    @bot.command(name='resetcheck')
    @commands.has_permissions(administrator=True)
    async def reset_member_check(ctx, member: discord.Member = None):
        """Reset a member's inactivity check date"""
        bot = ctx.bot
        if not member:
            await ctx.send("❌ Please mention a member: `!resetcheck @username`")
            return
        
        if not hasattr(bot, 'cleanup_system') or not bot.cleanup_system:
            await ctx.send("❌ Cleanup system not initialized")
            return
        
        if hasattr(bot.cleanup_system, 'member_last_check'):
            bot.cleanup_system.member_last_check[member.id] = datetime.now()
            await ctx.send(f"✅ Reset check date for {member.mention} to today")
        else:
            await ctx.send("❌ Check tracking not available")
    
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
