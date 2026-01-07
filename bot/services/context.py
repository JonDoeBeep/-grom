"""
Context Management Service.
Handles conversation history storage and retrieval.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from bot.utils.logging import get_logger

logger = get_logger(__name__)


class ContextManager:
    """
    Manages conversation context for channels.
    Stores messages per channel and persists to JSON.
    """
    
    def __init__(self, context_file: str, max_history: int = 300):
        """
        Initialize the context manager.
        
        Args:
            context_file: Path to the JSON file for persistence
            max_history: Maximum number of messages to keep per channel (default 300)
        """
        self.context_file = Path(context_file)
        self.max_history = max_history
        self.context_data: Dict[str, List[Dict[str, Any]]] = {}
        self.load()
    
    def load(self):
        """Load conversation context from the JSON file."""
        try:
            if self.context_file.exists():
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, dict):
                        self.context_data = loaded_data
                    else:
                        logger.warning(f"Context file {self.context_file} was not a valid dict, resetting")
                        self.context_data = {}
            else:
                self.context_data = {}
                logger.info(f"Context file {self.context_file} not found, starting fresh")
        except json.JSONDecodeError as e:
            logger.error(f"Error loading context from {self.context_file}: {e}")
            self.context_data = {}
        except Exception as e:
            logger.error(f"Error loading context from {self.context_file}: {e}")
            self.context_data = {}
    
    def save(self):
        """Save the current conversation context to the JSON file."""
        try:
            # Ensure parent directory exists
            self.context_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump(self.context_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving context to {self.context_file}: {e}")
    
    def add_message(
        self,
        channel_id: str,
        user: str,
        message: str,
        is_bot: bool = False,
        **kwargs
    ):
        """
        Add a message to the conversation context.
        
        Args:
            channel_id: The Discord channel ID
            user: The username/display name
            message: The message content
            is_bot: Whether this is a bot message
            **kwargs: Additional metadata to store
        """
        channel_id = str(channel_id)
        
        if channel_id not in self.context_data:
            self.context_data[channel_id] = []
        
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "user": user,
            "message": message,
            "is_bot": is_bot,
            **kwargs
        }
        self.context_data[channel_id].append(message_entry)
        
        # Trim to max history
        if len(self.context_data[channel_id]) > self.max_history:
            self.context_data[channel_id] = self.context_data[channel_id][-self.max_history:]
        
        self.save()
    
    def get_history(self, channel_id: str, limit: int = 10) -> str:
        """
        Get recent conversation history as a formatted string.
        
        Args:
            channel_id: The Discord channel ID
            limit: Maximum number of messages to return
            
        Returns:
            Formatted conversation history string
        """
        channel_id = str(channel_id)
        if channel_id not in self.context_data:
            return ""
        
        recent_messages = self.context_data[channel_id][-limit:]
        context_lines = []
        
        for msg in recent_messages:
            if msg.get("is_bot"):
                speaker = msg.get("personality", "Bot")
            else:
                speaker = msg.get("user", "Unknown User")
            
            message_text = msg.get("message", "")
            context_lines.append(f"{speaker.title()}: {message_text}")
        
        return "\n".join(context_lines)
    
    def get_messages_for_api(self, channel_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Get conversation history formatted for the OpenAI API.
        
        Args:
            channel_id: The Discord channel ID
            limit: Maximum number of messages to return
            
        Returns:
            List of message dicts with 'role' and 'content'
        """
        channel_id = str(channel_id)
        if channel_id not in self.context_data:
            return []
        
        recent_messages = self.context_data[channel_id][-limit:]
        api_messages = []
        
        for msg in recent_messages:
            role = "assistant" if msg.get("is_bot") else "user"
            content = msg.get("message", "")
            
            # Add username prefix for user messages
            if not msg.get("is_bot"):
                user = msg.get("user", "User")
                content = f"{user}: {content}"
            
            api_messages.append({"role": role, "content": content})
        
        return api_messages
    
    def get_raw_history(self, channel_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get raw message history for a channel.
        
        Args:
            channel_id: The Discord channel ID
            limit: Maximum number of messages to return
            
        Returns:
            List of raw message dictionaries
        """
        channel_id = str(channel_id)
        return self.context_data.get(channel_id, [])[-limit:]
    
    def remove_last_bot_message(self, channel_id: str, content: str) -> bool:
        """
        Remove a specific bot message from history (for retry functionality).
        
        Args:
            channel_id: The Discord channel ID
            content: The content of the message to remove
            
        Returns:
            True if message was found and removed
        """
        channel_id = str(channel_id)
        if channel_id not in self.context_data:
            return False
        
        channel_history = self.context_data[channel_id]
        for i in range(len(channel_history) - 1, -1, -1):
            msg = channel_history[i]
            if msg.get("is_bot") and msg.get("message") == content:
                channel_history.pop(i)
                self.save()
                return True
        
        return False
    
    def clear_channel(self, channel_id: str):
        """Clear all history for a channel."""
        channel_id = str(channel_id)
        if channel_id in self.context_data:
            del self.context_data[channel_id]
            self.save()
