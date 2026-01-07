"""
Discord-specific helper utilities.
Handles mention/emoji conversion and other Discord-specific transformations.
"""

import discord
import json
import re
from pathlib import Path
from typing import Optional, Set

from bot.utils.logging import get_logger

logger = get_logger(__name__)


# Cache for bad words list
_bad_words_cache: Optional[Set[str]] = None


def _load_bad_words() -> Set[str]:
    """Load bad words from config file."""
    global _bad_words_cache
    if _bad_words_cache is not None:
        return _bad_words_cache
    
    try:
        config_path = Path("data/filter_config.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _bad_words_cache = set(word.lower() for word in data.get("bad_words", []))
                return _bad_words_cache
    except Exception as e:
        logger.error(f"Error loading bad words config: {e}")
    
    _bad_words_cache = set()
    return _bad_words_cache


def filter_response(text: str, guild: Optional[discord.Guild]) -> str:
    """
    Filter bot responses to remove dangerous mentions and bad words.
    
    Removes:
    - @everyone and @here mentions
    - Role mentions (<@&ID>)
    - User mentions (replaced with display name, no ping)
    - Bad words (exact word boundary matching)
    
    Args:
        text: The response text to filter
        guild: The Discord guild for looking up member display names
        
    Returns:
        Filtered text safe for sending
    """
    if not text:
        return text
    
    # Remove @everyone and @here
    text = text.replace("@everyone", "@\u200beveryone")
    text = text.replace("@here", "@\u200bhere")
    
    # Remove role mentions (<@&ID>) - replace with @deleted-role
    text = re.sub(r'<@&\d+>', '@deleted-role', text)
    
    # Replace user mentions with display names (no ping)
    def replace_user_mention(match):
        user_id = match.group(1)
        if guild:
            member = guild.get_member(int(user_id))
            if member:
                return f"@{member.display_name}"
        return "@unknown-user"
    
    # Match <@ID> and <@!ID> patterns
    text = re.sub(r'<@!?(\d+)>', replace_user_mention, text)
    
    # Filter bad words using exact word boundary matching
    bad_words = _load_bad_words()
    if bad_words:
        def replace_bad_word(match):
            return '*' * len(match.group(0))
        
        # Build pattern for word boundary matching
        # Sort by length (longest first) to match longer phrases first
        sorted_words = sorted(bad_words, key=len, reverse=True)
        pattern = r'\b(' + '|'.join(re.escape(word) for word in sorted_words) + r')\b'
        text = re.sub(pattern, replace_bad_word, text, flags=re.IGNORECASE)
    
    return text


def convert_mentions_and_emojis(message_text: str, guild: Optional[discord.Guild]) -> str:
    """
    Convert @(username) to actual Discord mentions and :(emoji): to actual emojis.
    
    Args:
        message_text: The text to process
        guild: The Discord guild for looking up members/emojis
        
    Returns:
        Processed text with converted mentions and emojis
    """
    if not message_text:
        return message_text
    
    def replace_mention(match):
        username = match.group(1)
        if guild:
            member = discord.utils.find(
                lambda m: m.display_name.lower() == username.lower() or m.name.lower() == username.lower(),
                guild.members
            )
            if member:
                return member.mention
        return f"@{username}"
    
    def replace_emoji(match):
        emoji_name = match.group(1)
        if guild:
            emoji = discord.utils.get(guild.emojis, name=emoji_name)
            if emoji:
                return str(emoji)
        return f":{emoji_name}:"
    
    # Convert @(username) patterns
    message_text = re.sub(r'@\(([^)]+)\)', replace_mention, message_text)
    
    # Convert :(emoji_name): patterns (but not standard Unicode emoji shortcodes)
    message_text = re.sub(r':([a-zA-Z0-9_]+):', replace_emoji, message_text)
    
    return message_text


async def update_bot_nickname(guild: discord.Guild, personality_name: str):
    """
    Update the bot's nickname to match the current personality.
    
    Args:
        guild: The Discord guild to update nickname in
        personality_name: The new nickname to set
    """
    try:
        if guild and guild.me:
            current_nick = guild.me.display_name
            if current_nick.lower() != personality_name.lower():
                await guild.me.edit(nick=personality_name)
                logger.info(f"Updated nickname to '{personality_name}' in guild '{guild.name}'")
        else:
            logger.warning("Could not update nickname - guild or member not found")
    except discord.Forbidden:
        logger.warning(f"No permission to change nickname in '{guild.name}'")
    except discord.HTTPException as e:
        logger.error(f"Failed to update nickname: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating nickname: {e}")


def strip_bot_mention(message: discord.Message, content: str) -> str:
    """
    Remove bot mentions from message content.
    
    Args:
        message: The Discord message
        content: The content to strip mentions from
        
    Returns:
        Content with bot mentions removed
    """
    if message.guild and message.guild.me:
        bot_id = message.guild.me.id
        content = content.replace(f'<@{bot_id}>', '').replace(f'<@!{bot_id}>', '')
    return content.strip()
