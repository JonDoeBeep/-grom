"""
Main Discord Bot Module.
Entry point for the @grom Discord bot.
"""

import discord
from discord.ext import commands
from pathlib import Path

from bot.config import get_config, Config
from bot.services.ai_client import AIClient, download_image, download_pdf
from bot.services.personalities import init_personality_manager, get_personality_manager
from bot.services.auto_response import get_auto_response_engine, init_auto_response_engine
from bot.utils.logging import get_logger, set_debug_mode
from bot.utils.discord_helpers import convert_mentions_and_emojis, update_bot_nickname, strip_bot_mention

logger = get_logger(__name__)


class GromBot(commands.Bot):
    """
    The main bot class for @grom.
    """
    
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.members = True  # For member lookup in mentions
        
        super().__init__(
            command_prefix=config.command_prefix,
            intents=intents,
            help_command=None  # We use our own help command
        )
        
        self.config = config
        self.ai_client: AIClient = None
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        # Initialize AI client
        self.ai_client = AIClient(
            api_key=self.config.api_key,
            base_url=self.config.api_base_url,
            model=self.config.model
        )
        logger.info(f"AI client initialized with model: {self.config.model}")
        
        # Initialize personality manager
        base_dir = Path(__file__).parent.parent
        init_personality_manager(
            personalities_file=str(base_dir / "data" / "personalities.json"),
            contexts_dir=str(base_dir / "data" / "contexts")
        )
        logger.info("Personality manager initialized")
        
        # Initialize auto-response engine
        init_auto_response_engine(str(base_dir / "data" / "auto_response_settings.json"))
        logger.info("Auto-response engine initialized")
        
        # Load cogs
        await self.load_extension("bot.cogs.personality")
        await self.load_extension("bot.cogs.help")
        logger.info("Cogs loaded")
    
    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"{self.user} has connected to Discord!")
        logger.info(f"Bot is in {len(self.guilds)} guilds")
        
        # Set initial nickname for all guilds
        manager = get_personality_manager()
        for guild in self.guilds:
            # Get first text channel to determine personality
            first_channel = next((c for c in guild.text_channels), None)
            if first_channel:
                personality_index = manager.get_active_personality(str(first_channel.id))
                personality = manager.get_personality(personality_index)
                await update_bot_nickname(guild, personality.name)
        
        # Display available personalities
        logger.info("Available personalities:")
        for idx, name in manager.list_personalities():
            logger.info(f"  {idx}: {name}")
        
        # Sync commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_message(self, message: discord.Message):
        """Handle incoming messages."""
        if message.author == self.user:
            return
        
        # Log message to context
        manager = get_personality_manager()
        personality_index = manager.get_active_personality(str(message.channel.id))
        personality = manager.get_personality(personality_index)
        context_manager = manager.get_context_manager(personality)
        
        log_content = message.content
        if message.attachments:
            log_content += f" [user sent {len(message.attachments)} attachment(s)]"
        
        context_manager.add_message(
            str(message.channel.id),
            message.author.display_name,
            log_content,
            is_bot=False
        )
        
        # Check if bot should respond
        bot_mentioned = self.user in message.mentions
        is_reply_to_bot = (
            message.reference and
            message.reference.cached_message and
            message.reference.cached_message.author == self.user
        )
        
        # Process commands first
        ctx = await self.get_context(message)
        is_command = ctx.valid and ctx.command
        
        should_respond = False
        
        # Direct engagement (mention or reply)
        if (bot_mentioned or is_reply_to_bot) and not is_command:
            should_respond = True
        elif not is_command:
            # Check for auto-response
            engine = get_auto_response_engine()
            context_history = context_manager.get_raw_history(str(message.channel.id))
            
            if engine.should_respond(
                str(message.channel.id),
                message.content,
                personality.auto_response_keywords,
                context_history
            ):
                should_respond = True
                engine.record_response()
                logger.info(f"Auto-responding to message from {message.author.display_name}")
        
        if should_respond:
            await self.handle_ai_message(message)
        
        await self.process_commands(message)
    
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reactions on bot messages."""
        if user == self.user:
            return
        
        if reaction.message.author != self.user:
            return
        
        # Retry reaction
        if str(reaction.emoji) in ['recycle', 'arrows_counterclockwise']:
            await self.retry_message(reaction.message, user)
    
    async def handle_ai_message(self, message: discord.Message):
        """Generate and send an AI response to a message."""
        try:
            manager = get_personality_manager()
            personality_index = manager.get_active_personality(str(message.channel.id))
            personality = manager.get_personality(personality_index)
            context_manager = manager.get_context_manager(personality)
            
            async with message.channel.typing():
                # Prepare user message
                user_message = strip_bot_mention(message, message.content)
                
                # Handle attachments
                image_input = None
                pdf_text = None
                attachment_info = ""
                
                if message.attachments:
                    attachment = message.attachments[0]
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        image_input = await download_image(attachment.url)
                        attachment_info = f"\n[User attached an image: {attachment.filename}]"
                    elif attachment.filename.lower().endswith('.pdf'):
                        pdf_text = await download_pdf(attachment.url)
                        attachment_info = f"\n[User attached a PDF: {attachment.filename}]"
                
                # Build context
                conversation_history = context_manager.get_messages_for_api(str(message.channel.id), limit=10)
                
                # Handle reply context
                reply_info = ""
                if message.reference and message.reference.cached_message:
                    replied_to = message.reference.cached_message
                    reply_info = f'\nThis is a reply to {replied_to.author.display_name}: "{replied_to.content}"\n'
                
                # Build full user message
                full_user_message = f"{message.author.display_name}: {user_message}{attachment_info}{reply_info}"
                
                if pdf_text:
                    full_user_message += f"\n\nExtracted PDF Content:\n{pdf_text}"
                
                # Generate response
                response = await self.ai_client.generate_response(
                    system_prompt=personality.system_prompt,
                    user_message=full_user_message,
                    conversation_history=conversation_history,
                    image=image_input
                )
                
                # Convert mentions and emojis
                response = convert_mentions_and_emojis(response, message.guild)
                
                # Log bot response to context
                context_manager.add_message(
                    str(message.channel.id),
                    personality.name,
                    response,
                    is_bot=True,
                    personality=personality.name
                )
                
                # Send response
                if response:
                    if len(response) > 2000:
                        # Split long messages
                        for i in range(0, len(response), 2000):
                            await message.reply(response[i:i+2000])
                    else:
                        await message.reply(response)
                else:
                    await message.reply(f"{personality.name} has nothing to say...")
                    
        except Exception as e:
            logger.error(f"Error handling AI message: {e}")
            await message.reply("Sorry, an error occurred.")
    
    async def retry_message(self, target_message: discord.Message, user: discord.User):
        """Retry generating a response for a bot message."""
        try:
            manager = get_personality_manager()
            context_manager = manager.get_context_for_channel(str(target_message.channel.id))
            
            # Find the original user message
            original_message = None
            if target_message.reference and target_message.reference.cached_message:
                original_message = target_message.reference.cached_message
            else:
                # Look in history
                async for msg in target_message.channel.history(limit=5, before=target_message):
                    if msg.author != self.user:
                        original_message = msg
                        break
            
            if not original_message:
                logger.warning("Could not find original message to retry")
                return
            
            # Remove the old response from context
            context_manager.remove_last_bot_message(str(target_message.channel.id), target_message.content)
            
            # Delete the old message and regenerate
            await target_message.delete()
            await self.handle_ai_message(original_message)
            
            logger.info(f"Retried response for message from {original_message.author.display_name}")
            
        except Exception as e:
            logger.error(f"Error retrying message: {e}")
    
    async def close(self):
        """Cleanup when bot is shutting down."""
        if self.ai_client:
            await self.ai_client.close()
        await super().close()


def run_bot():
    """Run the bot with configuration from environment."""
    try:
        config = get_config()
        
        if config.debug_mode:
            set_debug_mode(True)
            logger.info("Debug mode enabled")
        
        errors = config.validate()
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            return
        
        bot = GromBot(config)
        bot.run(config.discord_token)
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
    except discord.LoginFailure:
        logger.error("Invalid Discord token!")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise


if __name__ == "__main__":
    run_bot()
