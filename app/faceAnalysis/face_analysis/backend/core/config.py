"""
Configuration settings for the Face Analysis application
"""

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

# Get the project root directory (where main.py is located)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys - Use the same key as main app
    ANTHROPIC_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")  # Use CLAUDE_API_KEY from main app
    GOOGLE_APPLICATION_CREDENTIALS: str = "vision_key.json"  # Optional fallback
    
    # MongoDB Configuration
    MONGODB_URL: str = "mongodb://localhost:27017/"
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # Data Configuration - Use absolute paths
    DATA_DIR: str = str(PROJECT_ROOT / "backend" / "data")
    UPLOAD_DIR: str = str(PROJECT_ROOT / "backend" / "uploads")
    RESULTS_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "results")
    RECOMMENDATIONS_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "recommendations")
    
    # CSV Data File
    CSV_DATA_FILE: str = str(PROJECT_ROOT / "skincare_products.csv")
    
    # Analysis Parameters
    SKIN_ANALYSIS_PARAMETERS: List[str] = [
        "acne",
        "dark_spot", 
        "dark_circle",
        "wrinkle",
        "uneven_skintone",
        "pores",
        "pigmentation",
        "dullness",
        "overall_skin_health"
    ]
    
    # Ethnicity Options
    ETHNICITY_OPTIONS: List[str] = [
        "Caucasian",
        "African American", 
        "Asian",
        "Indian",
        "Hispanic/Latino",
        "Middle Eastern",
        "Mixed",
        "Other"
    ]
    
    # Gender Options
    GENDER_OPTIONS: List[str] = [
        "Male",
        "Female",
        "Non-binary",
        "Prefer not to say"
    ]
    
    # Skin Type Options
    SKIN_TYPE_OPTIONS: List[str] = [
        "normal",
        "dry",
        "oily",
        "combination",
        "sensitive"
    ]
    
    # Budget Ranges
    BUDGET_RANGES: List[dict] = [
        {"label": "Budget ($0-25)", "min": 0, "max": 25},
        {"label": "Mid-range ($25-75)", "min": 25, "max": 75},
        {"label": "Premium ($75-150)", "min": 75, "max": 150},
        {"label": "Luxury ($150+)", "min": 150, "max": 1000}
    ]
    
    # Model Configuration
    CLAUDE_MODEL: str = "claude-3-opus-20240229"
    CLAUDE_MAX_TOKENS: int = 2000
    CLAUDE_TEMPERATURE: float = 0.3
    
    # Image Processing
    MAX_IMAGE_SIZE: int = 1024
    SUPPORTED_FORMATS: List[str] = ["jpg", "jpeg", "png", "bmp"]
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # Camera Configuration
    CAMERA_INDEX: int = 0
    CAPTURE_ANGLES: List[str] = ["front", "left", "right"]
    
    class Config:
        env_file = str(PROJECT_ROOT.parent.parent / ".env")  # Load from project root
        case_sensitive = True
        extra = "ignore"  # Allow extra environment variables

# Global settings instance
settings = Settings()

# Debug: Print API key status
if settings.ANTHROPIC_API_KEY:
    print(f"Face Analysis API key loaded successfully (length: {len(settings.ANTHROPIC_API_KEY)})")
else:
    print("Face Analysis API key not found - analysis will not be available")

