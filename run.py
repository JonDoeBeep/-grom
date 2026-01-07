#!/usr/bin/env python3
"""
@grom Discord Bot - Entry Point

Run this file to start the bot:
    python run.py

Or run the module directly:
    python -m bot.main
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from bot.main import run_bot

if __name__ == "__main__":
    run_bot()
