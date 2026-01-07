"""
Auto-Response Service.
Handles intelligent auto-responses in a designated channel.
"""

import json
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from bot.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AutoResponseSettings:
    """Configuration for auto-response behavior."""
    enabled: bool = True
    designated_channel_id: Optional[str] = None
    base_chance: float = 0.02  # 2%
    max_chance: float = 0.8    # 80% cap
    min_seconds_between: int = 30
    max_per_window: int = 3
    window_seconds: int = 300  # 5 minutes
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoResponseSettings":
        return cls(
            enabled=data.get("enabled", True),
            designated_channel_id=data.get("designated_channel_id"),
            base_chance=data.get("base_chance", 0.02),
            max_chance=data.get("max_chance", 0.8),
            min_seconds_between=data.get("min_seconds_between", 30),
            max_per_window=data.get("max_per_window", 3),
            window_seconds=data.get("window_seconds", 300),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutoResponseEngine:
    """
    Engine for determining when to auto-respond to messages.
    Uses probabilistic triggering with keyword multipliers and cooldowns.
    """
    
    def __init__(self, settings_file: str):
        self.settings_file = Path(settings_file)
        self.settings = self._load_settings()
        self.last_response_time: Optional[datetime] = None
        self.response_times: List[datetime] = []
    
    def _load_settings(self) -> AutoResponseSettings:
        """Load settings from file."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return AutoResponseSettings.from_dict(data)
        except Exception as e:
            logger.error(f"Error loading auto-response settings: {e}")
        
        return AutoResponseSettings()
    
    def save_settings(self):
        """Save current settings to file."""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings.to_dict(), f, indent=2)
            logger.info("Auto-response settings saved")
        except Exception as e:
            logger.error(f"Error saving auto-response settings: {e}")
    
    def set_designated_channel(self, channel_id: str):
        """Set the designated channel for auto-responses."""
        self.settings.designated_channel_id = str(channel_id)
        self.save_settings()
        logger.info(f"Designated auto-response channel set to: {channel_id}")
    
    def is_designated_channel(self, channel_id: str) -> bool:
        """Check if the given channel is the designated auto-response channel."""
        return str(channel_id) == self.settings.designated_channel_id
    
    def calculate_chance(
        self,
        message_content: str,
        keywords: Dict[str, float],
        context: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate the probability of responding to a message.
        
        Args:
            message_content: The message text
            keywords: Dict mapping keywords to multipliers
            context: Recent conversation history
            
        Returns:
            Probability between 0 and max_chance
        """
        chance = self.settings.base_chance
        content_lower = message_content.lower()
        
        # Keyword multipliers
        for keyword, multiplier in keywords.items():
            if keyword.lower() in content_lower:
                chance *= multiplier
                logger.debug(f"Keyword '{keyword}' matched, chance *= {multiplier}")
        
        # Message style factors
        if '?' in message_content:
            chance *= 2.0
            logger.debug("Question mark detected, chance *= 2.0")
        
        if '!' in message_content:
            chance *= 1.5
            logger.debug("Exclamation mark detected, chance *= 1.5")
        
        # Caps detection (if >30% caps)
        if len(message_content) > 0:
            caps_ratio = sum(1 for c in message_content if c.isupper()) / len(message_content)
            if caps_ratio > 0.3:
                chance *= 2.0
                logger.debug(f"High caps ratio ({caps_ratio:.2f}), chance *= 2.0")
        
        # Message length factors
        msg_len = len(message_content)
        if msg_len < 5:
            chance *= 0.3
            logger.debug("Very short message, chance *= 0.3")
        elif msg_len > 200:
            chance *= 0.5
            logger.debug("Very long message, chance *= 0.5")
        elif 10 <= msg_len <= 100:
            chance *= 1.5
            logger.debug("Message in sweet spot length, chance *= 1.5")
        
        # Conversation flow analysis
        if context:
            # Check for tech keywords in recent context
            tech_keywords = ['code', 'program', 'software', 'bug', 'error', 'help']
            recent_messages = [msg.get('message', '').lower() for msg in context[-5:]]
            tech_mentions = sum(
                1 for msg in recent_messages
                for kw in tech_keywords if kw in msg
            )
            if tech_mentions >= 2:
                chance *= 2.0
                logger.debug(f"Tech conversation detected ({tech_mentions} mentions), chance *= 2.0")
        
        # Apply cooldown penalties
        if not self._check_cooldowns_soft():
            chance *= 0.1
            logger.debug("Cooldown penalty applied, chance *= 0.1")
        
        # Cap at maximum
        final_chance = min(chance, self.settings.max_chance)
        logger.debug(f"Final auto-response chance: {final_chance:.4f} ({final_chance*100:.2f}%)")
        
        return final_chance
    
    def _check_cooldowns_soft(self) -> bool:
        """Check cooldowns without hard blocking (for chance reduction)."""
        now = datetime.now()
        
        # Min time between responses
        if self.last_response_time:
            elapsed = (now - self.last_response_time).total_seconds()
            if elapsed < self.settings.min_seconds_between:
                return False
        
        return True
    
    def check_cooldowns(self) -> bool:
        """Check if cooldowns allow responding."""
        now = datetime.now()
        
        # Min time between responses
        if self.last_response_time:
            elapsed = (now - self.last_response_time).total_seconds()
            if elapsed < self.settings.min_seconds_between:
                logger.debug(f"Cooldown: only {elapsed:.1f}s since last response")
                return False
        
        # Max per window
        window_start = now - timedelta(seconds=self.settings.window_seconds)
        recent = [t for t in self.response_times if t > window_start]
        if len(recent) >= self.settings.max_per_window:
            logger.debug(f"Cooldown: {len(recent)} responses in window (max: {self.settings.max_per_window})")
            return False
        
        return True
    
    def should_respond(
        self,
        channel_id: str,
        message_content: str,
        keywords: Dict[str, float],
        context: List[Dict[str, Any]]
    ) -> bool:
        """
        Determine if the bot should auto-respond to a message.
        
        Args:
            channel_id: The channel the message is in
            message_content: The message text
            keywords: Personality-specific keyword multipliers
            context: Recent conversation history
            
        Returns:
            True if should respond
        """
        if not self.settings.enabled:
            return False
        
        if not self.is_designated_channel(channel_id):
            return False
        
        if not self.check_cooldowns():
            return False
        
        chance = self.calculate_chance(message_content, keywords, context)
        roll = random.random()
        
        if roll < chance:
            logger.info(f"Auto-response triggered (roll: {roll:.4f} < chance: {chance:.4f})")
            return True
        
        logger.debug(f"Auto-response not triggered (roll: {roll:.4f} >= chance: {chance:.4f})")
        return False
    
    def record_response(self):
        """Record that a response was sent (for cooldown tracking)."""
        now = datetime.now()
        self.last_response_time = now
        self.response_times.append(now)
        
        # Prune old entries
        cutoff = now - timedelta(seconds=self.settings.window_seconds * 2)
        self.response_times = [t for t in self.response_times if t > cutoff]
        
        logger.debug(f"Recorded response. {len(self.response_times)} responses in tracking window.")


# Global engine instance (lazy loaded)
_engine: Optional[AutoResponseEngine] = None


def get_auto_response_engine() -> AutoResponseEngine:
    """Get the global auto-response engine instance."""
    global _engine
    if _engine is None:
        _engine = AutoResponseEngine("data/auto_response_settings.json")
    return _engine


def init_auto_response_engine(settings_file: str) -> AutoResponseEngine:
    """Initialize the auto-response engine with a custom settings file."""
    global _engine
    _engine = AutoResponseEngine(settings_file)
    return _engine
