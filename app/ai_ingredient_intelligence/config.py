# app/config.py

"""App configuration loaded from .env"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb")
DB_NAME = os.getenv("DB_NAME", "skin_bb")
MODEL_PATH = os.getenv("MODEL_PATH", "app/ml/model.pkl")
