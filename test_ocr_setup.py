#!/usr/bin/env python3
"""
Test script to verify OCR and Claude API setup
"""

import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_setup():
    """Test the OCR and Claude API setup"""
    
    print("🔍 Testing SkinBB AI Tools Setup...")
    print("=" * 50)
    
    # Check environment variables
    print("\n📋 Environment Variables:")
    print(f"GOOGLE_APPLICATION_CREDENTIALS: {'✅ Set' if os.getenv('GOOGLE_APPLICATION_CREDENTIALS') else '❌ Missing'}")
    print(f"GOOGLE_CLOUD_PROJECT: {'✅ Set (Optional)' if os.getenv('GOOGLE_CLOUD_PROJECT') else '⚠️  Not Set (Optional)'}")
    print(f"CLAUDE_API_KEY: {'✅ Set' if os.getenv('CLAUDE_API_KEY') else '❌ Missing'}")
    print(f"MONGO_URI: {'✅ Set' if os.getenv('MONGO_URI') else '❌ Missing'}")
    
    # Check if credentials file exists
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_path:
        if os.path.exists(creds_path):
            print(f"Google Credentials File: ✅ Found at {creds_path}")
        else:
            print(f"Google Credentials File: ❌ Not found at {creds_path}")
    else:
        print("Google Credentials File: ❌ Path not specified")
    
    # Test imports
    print("\n📦 Testing Dependencies:")
    try:
        import fastapi
        print("FastAPI: ✅ Imported")
    except ImportError as e:
        print(f"FastAPI: ❌ Import failed - {e}")
    
    try:
        import google.cloud.vision
        print("Google Cloud Vision: ✅ Imported")
    except ImportError as e:
        print(f"Google Cloud Vision: ❌ Import failed - {e}")
    
    try:
        import anthropic
        print("Anthropic: ✅ Imported")
    except ImportError as e:
        print(f"Anthropic: ❌ Import failed - {e}")
    
    try:
        import fitz
        print("PyMuPDF: ✅ Imported")
    except ImportError as e:
        print(f"PyMuPDF: ❌ Import failed - {e}")
    
    try:
        from PIL import Image
        print("Pillow: ✅ Imported")
    except ImportError as e:
        print(f"Pillow: ❌ Import failed - {e}")
    
    try:
        import pymongo
        print("PyMongo: ✅ Imported")
    except ImportError as e:
        print(f"PyMongo: ❌ Import failed - {e}")
    
    # Test OCR processor import
    print("\n🔧 Testing OCR Processor:")
    try:
        from app.ai_ingredient_intelligence.logic.ocr_processor import OCRProcessor
        print("OCR Processor: ✅ Imported")
        
        # Test initialization
        try:
            processor = OCRProcessor()
            print("OCR Processor: ✅ Initialized")
        except Exception as e:
            print(f"OCR Processor: ❌ Initialization failed - {e}")
            
    except ImportError as e:
        print(f"OCR Processor: ❌ Import failed - {e}")
    
    # Test API import
    print("\n🌐 Testing API:")
    try:
        from app.ai_ingredient_intelligence.api.analyze_inci import router
        print("API Router: ✅ Imported")
    except ImportError as e:
        print(f"API Router: ❌ Import failed - {e}")
    
    print("\n" + "=" * 50)
    
    # Summary
    print("\n📊 Setup Summary:")
    missing_vars = []
    if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        missing_vars.append("GOOGLE_APPLICATION_CREDENTIALS")
    if not os.getenv('CLAUDE_API_KEY'):
        missing_vars.append("CLAUDE_API_KEY")
    if not os.getenv('MONGO_URI'):
        missing_vars.append("MONGO_URI")
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file")
    else:
        print("✅ All required environment variables are set")
        print("⚠️  GOOGLE_CLOUD_PROJECT is optional when using service account key file")
    
    print("\n🚀 Ready to run the application!")

if __name__ == "__main__":
    asyncio.run(test_setup())
