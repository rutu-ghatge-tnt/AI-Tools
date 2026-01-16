# app/config.py

from pathlib import Path
import os
from dotenv import load_dotenv

# Get the absolute path to the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from .env file in project root
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"⚠️ .env file not found at: {env_path}")

# Claude API settings
from typing import Optional

CLAUDE_API_KEY: Optional[str] = os.getenv("CLAUDE_API_KEY")
# Use CLAUDE_MODEL if set, otherwise fall back to MODEL_NAME, otherwise use default
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"

# Get the absolute path to the directory where this config.py file resides
APP_DIR = Path(__file__).parent.resolve()

# Define Chroma DB path relative to the app folder location
CHROMA_DB_PATH: str = str("chroma_db")

# Optional: Validate critical env variables early
if not CLAUDE_API_KEY:
    print("Warning: CLAUDE_API_KEY is not set in the .env file. Chatbot functionality will be limited.")
else:
    print(f"Claude API key loaded successfully (model: {CLAUDE_MODEL})")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME = os.getenv("DB_NAME", "skin_bb")
