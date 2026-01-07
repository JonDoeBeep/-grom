"""
Configuration management for the bot.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class Config:
    """Bot configuration loaded from environment variables."""
    
    # Discord
    discord_token: str
    
    # AI API (OpenAI-compatible, works with NanoGPT, OpenAI, Ollama, etc.)
    api_key: str
    api_base_url: str
    model: str
    
    # Bot settings
    debug_mode: bool
    command_prefix: str
    
    @classmethod
    def from_env(cls, env_path: Optional[str] = None) -> "Config":
        """Load configuration from environment variables."""
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()
        
        discord_token = os.getenv("DISCORD_TOKEN")
        if not discord_token:
            raise ValueError("DISCORD_TOKEN environment variable is required")
        
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        return cls(
            discord_token=discord_token,
            api_key=api_key,
            api_base_url=os.getenv("OPENAI_BASE_URL", "https://api.nano-gpt.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true",
            command_prefix=os.getenv("COMMAND_PREFIX", "/"),
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if not self.discord_token:
            errors.append("DISCORD_TOKEN is required")
        if not self.api_key:
            errors.append("OPENAI_API_KEY is required")
        return errors


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config():
    """Reload configuration from environment."""
    global _config
    _config = Config.from_env()
    return _config
