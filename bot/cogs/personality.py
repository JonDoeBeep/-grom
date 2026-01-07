"""
Personality Cog - Commands for managing bot personalities.
"""

import json
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Dict

from bot.services.personalities import get_personality_manager
from bot.services.auto_response import get_auto_response_engine
from bot.utils.permissions import is_mod, check_mod_permissions
from bot.utils.discord_helpers import update_bot_nickname
from bot.utils.logging import get_logger

logger = get_logger(__name__)


class PersonalityCog(commands.Cog, name="Personality"):
    """Commands for managing bot personalities."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def personality_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for personality names."""
        manager = get_personality_manager()
        personalities = manager.list_personalities()
        
        choices = []
        current_lower = current.lower()
        
        for idx, name in personalities:
            if current_lower in name.lower() or not current:
                choices.append(app_commands.Choice(name=name, value=name))
                if len(choices) >= 25:  # Discord limit
                    break
        
        return choices
    
    @commands.hybrid_command(name="personality", description="Manage bot personalities")
    @app_commands.describe(
        action="Action to perform: list, info, or set",
        personality="Name of the personality (for info/set)"
    )
    @app_commands.autocomplete(personality=personality_autocomplete)
    async def personality(
        self,
        ctx: commands.Context,
        action: str = "list",
        personality: Optional[str] = None
    ):
        """
        Manage bot personalities.
        
        Actions:
        - list: Show all available personalities
        - info <name>: Show details about a personality
        - set <name>: Set the personality for this channel
        """
        manager = get_personality_manager()
        action = action.lower()
        
        if action == "list":
            embed = discord.Embed(
                title="Available Personalities",
                color=0x76b041
            )
            
            active_index = manager.get_active_personality(str(ctx.channel.id))
            
            for idx, name in manager.list_personalities():
                status = " (active)" if idx == active_index else ""
                embed.add_field(
                    name=f"{idx + 1}. {name}{status}",
                    value=f"Use `/personality set {name}` to activate",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        
        elif action == "info":
            if not personality:
                await ctx.send("Please specify a personality name: `/personality info <name>`")
                return
            
            result = manager.get_personality_by_name(personality)
            if not result:
                await ctx.send(f"Personality '{personality}' not found. Use `/personality list` to see available options.")
                return
            
            idx, p = result
            embed = discord.Embed(
                title=f"Personality: {p.name}",
                color=0x76b041
            )
            
            # Truncate system prompt for display
            prompt_preview = p.system_prompt[:500] + "..." if len(p.system_prompt) > 500 else p.system_prompt
            embed.add_field(name="System Prompt", value=f"```{prompt_preview}```", inline=False)
            embed.add_field(name="Context File", value=p.context_file, inline=True)
            
            await ctx.send(embed=embed)
        
        elif action == "set":
            # Check mod permissions for setting personality
            if ctx.guild:
                perms = ctx.author.guild_permissions
                if not (perms.manage_messages or perms.administrator):
                    await ctx.send("You need moderator permissions to change the personality.", ephemeral=True)
                    return
            
            if not personality:
                await ctx.send("Please specify a personality name: `/personality set <name>`", ephemeral=True)
                return
            
            result = manager.get_personality_by_name(personality)
            if not result:
                await ctx.send(f"Personality '{personality}' not found. Use `/personality list` to see available options.", ephemeral=True)
                return
            
            idx, p = result
            manager.set_active_personality(str(ctx.channel.id), idx)
            
            # Update bot nickname
            if ctx.guild:
                await update_bot_nickname(ctx.guild, p.name)
            
            embed = discord.Embed(
                title="Personality Changed",
                description=f"Now using **{p.name}** in this channel.",
                color=0x76b041
            )
            await ctx.send(embed=embed)
            logger.info(f"Personality changed to '{p.name}' in channel {ctx.channel.id}")
        
        else:
            await ctx.send(f"Unknown action '{action}'. Use: list, info, or set")
    
    async def _generate_keywords(self, name: str, description: str) -> Dict[str, float]:
        """Use AI to generate auto-response keywords for a personality."""
        prompt = f"""Generate keyword triggers for a Discord bot personality.

Personality: {name}
Description: {description}

Return a JSON object mapping keywords to multiplier values (1.0-20.0).
Higher values = more likely to trigger auto-response.
Include:
- The personality's name (highest, ~20.0)
- Topic-specific terms relevant to the personality (5.0-10.0)
- General interest terms (2.0-5.0)

Example format:
{{"rust": 8.0, "programming": 3.0, "glorpo": 20.0}}

Return ONLY the JSON object, no other text or markdown."""

        try:
            response = await self.bot.ai_client.generate_response(
                system_prompt="You generate JSON configuration for bots. Return only valid JSON.",
                user_message=prompt
            )
            
            # Clean up response - remove markdown code blocks if present
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]  # Remove first line
            if response.endswith("```"):
                response = response.rsplit("\n", 1)[0]  # Remove last line
            response = response.strip()
            
            keywords = json.loads(response)
            
            # Ensure personality name is included
            if name.lower() not in [k.lower() for k in keywords.keys()]:
                keywords[name.lower()] = 20.0
            
            logger.info(f"Generated {len(keywords)} keywords for personality '{name}'")
            return keywords
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI-generated keywords: {e}")
            # Fallback to basic keywords
            return {name.lower(): 20.0}
        except Exception as e:
            logger.error(f"Error generating keywords: {e}")
            return {name.lower(): 20.0}
    
    @commands.hybrid_command(name="create_personality", description="Create a custom personality (Mods only)")
    @app_commands.describe(
        name="Name for the new personality",
        description="Description of how the personality should behave"
    )
    @is_mod()
    async def create_personality(
        self,
        ctx: commands.Context,
        name: str,
        *,
        description: str
    ):
        """
        Create a custom personality. Requires moderator permissions.
        
        The description will be used to generate a system prompt and auto-response keywords.
        """
        manager = get_personality_manager()
        
        # Check if name already exists
        if manager.get_personality_by_name(name):
            await ctx.send(f"A personality named '{name}' already exists.")
            return
        
        await ctx.defer()  # This might take a moment
        
        # Generate keywords using AI
        keywords = await self._generate_keywords(name, description)
        
        # Create the system prompt
        system_prompt = f"""You are named {name} and are currently chatting in a Discord server.

{description}

Communicate responses naturally, staying true to this character description.
Do not include name: or message: in your response.
You can use information about the chat participants in your replies."""
        
        personality = manager.add_personality(name, system_prompt, keywords)
        
        embed = discord.Embed(
            title="Personality Created",
            description=f"Created new personality: **{name}**",
            color=0x76b041
        )
        embed.add_field(
            name="Activate it with:",
            value=f"`/personality set {name}`",
            inline=False
        )
        
        # Show generated keywords
        keyword_preview = ", ".join(f"{k} ({v}x)" for k, v in list(keywords.items())[:5])
        if len(keywords) > 5:
            keyword_preview += f" ... and {len(keywords) - 5} more"
        embed.add_field(
            name="Auto-response keywords:",
            value=keyword_preview,
            inline=False
        )
        
        await ctx.send(embed=embed)
        logger.info(f"New personality '{name}' created by {ctx.author.display_name} with {len(keywords)} keywords")
    
    @create_personality.error
    async def create_personality_error(self, ctx: commands.Context, error):
        """Handle errors for create_personality command."""
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You need moderator permissions to create personalities.")
        else:
            logger.error(f"Error in create_personality: {error}")
            await ctx.send("An error occurred while creating the personality.")
    
    # ============ Auto-Response Commands ============
    
    @commands.hybrid_group(name="autoresponse", description="Manage auto-responses")
    @is_mod()
    async def autoresponse(self, ctx: commands.Context):
        """Auto-response management commands. Requires moderator permissions."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/autoresponse status`, `/autoresponse setchannel`, `/autoresponse enable`, or `/autoresponse disable`")
    
    @autoresponse.command(name="setchannel", description="Set this channel for auto-responses")
    async def setchannel(self, ctx: commands.Context):
        """Designate the current channel for auto-responses."""
        engine = get_auto_response_engine()
        engine.set_designated_channel(str(ctx.channel.id))
        
        embed = discord.Embed(
            title="Auto-Response Channel Set",
            description=f"Auto-responses will now occur in {ctx.channel.mention}",
            color=0x76b041
        )
        await ctx.send(embed=embed)
        logger.info(f"Auto-response channel set to {ctx.channel.id} by {ctx.author.display_name}")
    
    @autoresponse.command(name="disable", description="Disable auto-responses")
    async def disable(self, ctx: commands.Context):
        """Disable auto-responses entirely."""
        engine = get_auto_response_engine()
        engine.settings.enabled = False
        engine.save_settings()
        
        embed = discord.Embed(
            title="Auto-Responses Disabled",
            description="The bot will no longer auto-respond to messages.",
            color=0xff6b6b
        )
        await ctx.send(embed=embed)
        logger.info(f"Auto-responses disabled by {ctx.author.display_name}")
    
    @autoresponse.command(name="enable", description="Enable auto-responses")
    async def enable(self, ctx: commands.Context):
        """Enable auto-responses."""
        engine = get_auto_response_engine()
        engine.settings.enabled = True
        engine.save_settings()
        
        embed = discord.Embed(
            title="Auto-Responses Enabled",
            description="The bot will now auto-respond in the designated channel.",
            color=0x76b041
        )
        await ctx.send(embed=embed)
        logger.info(f"Auto-responses enabled by {ctx.author.display_name}")
    
    @autoresponse.command(name="status", description="Show auto-response status")
    async def status(self, ctx: commands.Context):
        """Show current auto-response configuration."""
        engine = get_auto_response_engine()
        s = engine.settings
        
        channel_mention = f"<#{s.designated_channel_id}>" if s.designated_channel_id else "Not set"
        status_emoji = "Enabled" if s.enabled else "Disabled"
        status_color = 0x76b041 if s.enabled else 0xff6b6b
        
        embed = discord.Embed(
            title="Auto-Response Status",
            color=status_color
        )
        embed.add_field(name="Status", value=status_emoji, inline=True)
        embed.add_field(name="Channel", value=channel_mention, inline=True)
        embed.add_field(name="Base Chance", value=f"{s.base_chance*100:.1f}%", inline=True)
        embed.add_field(name="Min Cooldown", value=f"{s.min_seconds_between}s", inline=True)
        embed.add_field(name="Max/Window", value=f"{s.max_per_window} per {s.window_seconds//60}min", inline=True)
        
        await ctx.send(embed=embed)
    
    @autoresponse.error
    async def autoresponse_error(self, ctx: commands.Context, error):
        """Handle errors for autoresponse commands."""
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You need moderator permissions to manage auto-responses.")
        else:
            logger.error(f"Error in autoresponse: {error}")
            await ctx.send("An error occurred.")


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(PersonalityCog(bot))

