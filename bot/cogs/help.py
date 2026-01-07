"""
Help Cog - Help and utility commands.
"""

import discord
from discord.ext import commands

from bot.utils.logging import get_logger

logger = get_logger(__name__)


class HelpCog(commands.Cog, name="Help"):
    """Help and utility commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.hybrid_command(name="bothelp", description="Show bot help information")
    async def bothelp(self, ctx: commands.Context):
        """Show comprehensive help information about the bot."""
        embed = discord.Embed(
            title="Grom AI Bot Help",
            description="An AI chat bot with multiple personalities.",
            color=0x76b041
        )
        
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        embed.add_field(
            name="How to Interact",
            value=(
                "**Mention the bot**: Start your message with a mention\n"
                "**Reply to messages**: Reply to any bot message\n"
                "**Attachments**: Send images or PDFs when talking to the bot\n"
                "**Retry Responses**: React with a recycle emoji to retry"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Personality Commands",
            value=(
                "`/personality list` - Show all personalities\n"
                "`/personality info <name>` - Details about a personality\n"
                "`/personality set <name>` - Change personality for this channel\n"
                "`/create_personality <name> <description>` - Create new (mods only)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Utility Commands",
            value=(
                "`/bothelp` - Show this help message\n"
                "`/sync` - Sync slash commands (owner only)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Retry Feature",
            value="React to any bot message with a recycle emoji to regenerate that response.",
            inline=False
        )
        
        embed.set_footer(text="Use slash commands (/) for the best experience!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """Sync slash commands to Discord (owner only)."""
        await ctx.defer()
        
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} commands globally.")
            logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            await ctx.send(f"Failed to sync commands: {e}")
            logger.error(f"Failed to sync commands: {e}")


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(HelpCog(bot))
