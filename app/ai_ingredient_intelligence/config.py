# app/config.py

"""App configuration loaded from .env"""

import os
from pathlib import Path
from dotenv import load_dotenv
from app.config import MONGO_URI, DB_NAME

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv(MONGO_URI)
DB_NAME = os.getenv(DB_NAME)
