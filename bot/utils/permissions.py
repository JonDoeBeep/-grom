"""
Permission utilities for bot commands.
"""

import discord
from discord.ext import commands
from functools import wraps


def is_mod():
    """
    Check decorator that requires the user to have moderator permissions.
    Moderator = has manage_messages permission or higher.
    """
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            # DMs - only allow bot owner
            return await ctx.bot.is_owner(ctx.author)
        
        # Check for manage_messages or administrator
        perms = ctx.author.guild_permissions
        return perms.manage_messages or perms.administrator
    
    return commands.check(predicate)


def is_admin():
    """
    Check decorator that requires the user to have administrator permissions.
    """
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return await ctx.bot.is_owner(ctx.author)
        return ctx.author.guild_permissions.administrator
    
    return commands.check(predicate)


async def check_mod_permissions(interaction: discord.Interaction) -> bool:
    """
    Check if user has mod permissions for app commands.
    Use in app_commands with @app_commands.check(check_mod_permissions)
    """
    if interaction.guild is None:
        return False
    
    perms = interaction.user.guild_permissions
    return perms.manage_messages or perms.administrator
