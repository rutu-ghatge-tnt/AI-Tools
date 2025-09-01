# app/ai_ingredient_intelligence/scripts/cleanup_old_fields.py
"""Script to cleanup old field names and keep only enhanced_description"""

import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm import tqdm

# Load .env variables
load_dotenv()

# ✅ Read env vars correctly with defaults
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME: str = os.getenv("DB_NAME", "skin_bb")

# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_branded_ingredients"]

async def cleanup_old_fields():
    """Remove old rephrased_description field and keep only enhanced_description"""
    
    print("🧹 Cleaning up old field names...")
    
    # Count documents with old field
    old_field_count = await collection.count_documents({"rephrased_description": {"$exists": True}})
    enhanced_count = await collection.count_documents({"enhanced_description": {"$exists": True}})
    
    print(f"📊 Found {old_field_count} documents with 'rephrased_description' field")
    print(f"📊 Found {enhanced_count} documents with 'enhanced_description' field")
    
    if old_field_count == 0:
        print("✅ No old fields to clean up!")
        return
    
    # Remove the old field from all documents
    result = await collection.update_many(
        {"rephrased_description": {"$exists": True}},
        {"$unset": {"rephrased_description": ""}}
    )
    
    print(f"✅ Removed 'rephrased_description' field from {result.modified_count} documents")
    
    # Verify cleanup
    remaining_old = await collection.count_documents({"rephrased_description": {"$exists": True}})
    print(f"🔍 Remaining documents with old field: {remaining_old}")
    
    if remaining_old == 0:
        print("🎉 Cleanup completed successfully!")
    else:
        print("⚠️ Some documents still have old fields")

if __name__ == "__main__":
    asyncio.run(cleanup_old_fields())
