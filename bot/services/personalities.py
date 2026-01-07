"""
Personality Management Service.
Handles loading, switching, and creating personalities.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from bot.services.context import ContextManager
from bot.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Personality:
    """Represents a bot personality."""
    name: str
    system_prompt: str
    context_file: str
    auto_response_keywords: Dict[str, float] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Personality":
        return cls(
            name=data.get("name", "Unknown"),
            system_prompt=data.get("system_prompt", ""),
            context_file=data.get("context_file", "default_context.json"),
            auto_response_keywords=data.get("auto_response_keywords", {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "context_file": self.context_file,
            "auto_response_keywords": self.auto_response_keywords
        }


class PersonalityManager:
    """
    Manages bot personalities and their contexts.
    """
    
    def __init__(self, personalities_file: str, contexts_dir: str = "data/contexts"):
        """
        Initialize the personality manager.
        
        Args:
            personalities_file: Path to personalities.json
            contexts_dir: Directory for context files
        """
        self.personalities_file = Path(personalities_file)
        self.contexts_dir = Path(contexts_dir)
        self.personalities: List[Personality] = []
        self.default_personality_index: int = 0
        self.active_personalities: Dict[str, int] = {}  # channel_id -> personality_index
        self.context_managers: Dict[str, ContextManager] = {}  # context_file -> manager
        
        self._load_personalities()
        self._load_settings()
    
    def _load_personalities(self):
        """Load personalities from the JSON file."""
        try:
            if not self.personalities_file.exists():
                logger.warning(f"Personalities file not found: {self.personalities_file}")
                self._create_default_personality()
                return
            
            with open(self.personalities_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.default_personality_index = data.get("default_personality", 0)
            
            for p_data in data.get("personalities", []):
                self.personalities.append(Personality.from_dict(p_data))
            
            logger.info(f"Loaded {len(self.personalities)} personalities")
            
        except Exception as e:
            logger.error(f"Error loading personalities: {e}")
            self._create_default_personality()
    
    def _create_default_personality(self):
        """Create a default personality if none exist."""
        self.personalities = [
            Personality(
                name="Assistant",
                system_prompt="You are a helpful Discord bot assistant.",
                context_file="assistant_context.json"
            )
        ]
    
    def _load_settings(self):
        """Load channel personality settings."""
        settings_file = self.personalities_file.parent / "personality_settings.json"
        try:
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    self.active_personalities = json.load(f)
        except Exception as e:
            logger.error(f"Error loading personality settings: {e}")
    
    def save_settings(self):
        """Save channel personality settings."""
        settings_file = self.personalities_file.parent / "personality_settings.json"
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.active_personalities, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving personality settings: {e}")
    
    def get_personality(self, index: int = 0) -> Personality:
        """Get a personality by index."""
        if 0 <= index < len(self.personalities):
            return self.personalities[index]
        return self.personalities[0] if self.personalities else Personality("Bot", "", "bot_context.json")
    
    def get_personality_by_name(self, name: str) -> Optional[Tuple[int, Personality]]:
        """Get a personality by name (case-insensitive)."""
        name_lower = name.lower()
        for i, p in enumerate(self.personalities):
            if p.name.lower() == name_lower:
                return (i, p)
        return None
    
    def get_active_personality(self, channel_id: str) -> int:
        """Get the active personality index for a channel."""
        return self.active_personalities.get(str(channel_id), self.default_personality_index)
    
    def set_active_personality(self, channel_id: str, personality_index: int):
        """Set the active personality for a channel."""
        if 0 <= personality_index < len(self.personalities):
            self.active_personalities[str(channel_id)] = personality_index
            self.save_settings()
        else:
            raise ValueError(f"Invalid personality index: {personality_index}")
    
    def get_context_manager(self, personality: Personality) -> ContextManager:
        """Get or create a context manager for a personality."""
        context_file = personality.context_file
        
        if context_file not in self.context_managers:
            # Put context files in the contexts directory
            context_path = self.contexts_dir / context_file
            self.context_managers[context_file] = ContextManager(str(context_path))
        
        return self.context_managers[context_file]
    
    def get_context_for_channel(self, channel_id: str) -> ContextManager:
        """Get the context manager for a channel's active personality."""
        personality_index = self.get_active_personality(channel_id)
        personality = self.get_personality(personality_index)
        return self.get_context_manager(personality)
    
    def list_personalities(self) -> List[Tuple[int, str]]:
        """List all personalities as (index, name) tuples."""
        return [(i, p.name) for i, p in enumerate(self.personalities)]
    
    def add_personality(
        self,
        name: str,
        system_prompt: str,
        auto_response_keywords: Optional[Dict[str, float]] = None
    ) -> Personality:
        """
        Add a new personality.
        
        Args:
            name: The personality name
            system_prompt: The system prompt
            auto_response_keywords: Keywords for auto-response triggering
            
        Returns:
            The created personality
        """
        # Create context filename from name
        context_file = f"{name.lower().replace(' ', '_')}_context.json"
        
        # Default keywords include the personality name
        if auto_response_keywords is None:
            auto_response_keywords = {name.lower(): 20.0}
        
        personality = Personality(
            name=name,
            system_prompt=system_prompt,
            context_file=context_file,
            auto_response_keywords=auto_response_keywords
        )
        
        self.personalities.append(personality)
        self._save_personalities()
        
        logger.info(f"Added new personality: {name}")
        return personality
    
    def _save_personalities(self):
        """Save personalities to the JSON file."""
        try:
            data = {
                "default_personality": self.default_personality_index,
                "personalities": [p.to_dict() for p in self.personalities]
            }
            
            with open(self.personalities_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving personalities: {e}")


# Global manager instance (lazy loaded)
_manager: Optional[PersonalityManager] = None


def get_personality_manager() -> PersonalityManager:
    """Get the global personality manager instance."""
    global _manager
    if _manager is None:
        # Default paths - can be overridden
        _manager = PersonalityManager(
            personalities_file="data/personalities.json",
            contexts_dir="data/contexts"
        )
    return _manager


def init_personality_manager(personalities_file: str, contexts_dir: str) -> PersonalityManager:
    """Initialize the personality manager with custom paths."""
    global _manager
    _manager = PersonalityManager(personalities_file, contexts_dir)
    return _manager
