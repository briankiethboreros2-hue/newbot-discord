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
        self.voters = set()
        self.vote_result = {"kick": 0, "grant": 0, "review": 0}

        # Buttons preserved with correct custom_id format
        self.add_item(Button(style=discord.ButtonStyle.red, label="🚫 Kick", custom_id=f"ghost_kick_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.green, label="✨ Grant Role", custom_id=f"ghost_grant_{user_id}"))
        self.add_item(Button(style=discord.ButtonStyle.grey, label="📝 Review", custom_id=f"ghost_review_{user_id}"))

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

        if action == "kick":
            self.vote_result["kick"] += 1
        elif action == "grant":
            self.vote_result["grant"] += 1
        elif action == "review":
            self.vote_result["review"] += 1

        if len(self.voters) >= 1:
            if self.vote_result["kick"] > 0:
                final_action = "kick"
            elif self.vote_result["grant"] > 0:
                final_action = "grant"
            elif self.vote_result["review"] > 0:
                final_action = "review"
            else:
                final_action = None

            cleanup_cog = self.bot.get_cog("CleanupSystem")
            if cleanup_cog and final_action:
                await cleanup_cog.handle_vote_action(
                    f"{final_action}_{self.vote_type}",
                    self.user_id,
                    interaction.user,
                    interaction.message.id
                )

            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True

            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed and final_action:
                embed.add_field(
                    name="✅ Decision Made",
                    value=f"**Action:** {final_action.upper()}\n"
                          f"**By:** {interaction.user.mention}\n"
                          f"**Time:** {datetime.utcnow().strftime('%H:%M:%S')}",
                    inline=False
                )
                embed.color = discord.Color.green()

            await interaction.message.edit(embed=embed, view=self)
            await interaction.response.send_message(f"✅ Vote registered! Action `{final_action}` executed.", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Vote registered!", ephemeral=True)

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
            await interaction.response.send_message("⚠️ Already voted!", ephemeral=True)
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
                    if self.user_id not in cleanup_cog.under_review:
                        cleanup_cog.under_review[self.user_id] = datetime.utcnow()

            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True

            await interaction.response.send_message(f"✅ Action `{final_action}` executed.", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Vote registered!", ephemeral=True)

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
        cleanup_cog = self.bot.get_cog("CleanupSystem")

        if cleanup_cog:
            if action == "pardon":
                cleanup_cog.under_review.pop(self.user_id, None)
                embed = interaction.message.embeds[0]
                embed.title = "✅ Pardoned - Keeps Role"
                embed.description += f"\n\n**Decision:** Pardoned\n**By:** {interaction.user.mention}"
                embed.color = discord.Color.green()
                await interaction.message.edit(embed=embed, view=None)

            elif action == "demote":
                await cleanup_cog.handle_vote_action(
                    f"demote_{self.vote_type}",
                    self.user_id,
                    interaction.user,
                    interaction.message.id
                )

        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True

        await interaction.response.send_message(f"✅ Action `{action}` executed!", ephemeral=True)
