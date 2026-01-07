# app/ai_ingredient_intelligence/config.py

"""App configuration loaded from .env"""

import os
from dotenv import load_dotenv

load_dotenv()

# Google Vision API Configuration
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")  # Optional - not required if using service account key

# Anthropic Claude API Configuration
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Presenton API Configuration
PRESENTON_API_KEY = os.getenv("PRESENTON_API_KEY")

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "skinbb")

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# File Upload Configuration
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB default
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp"]
ALLOWED_PDF_TYPES = ["application/pdf"]

#serper
SERPER_API_KEY = os.getenv("SERPER_API")
AWS_S3_BUCKET_PLATFORM_LOGOS = "platform_logos"