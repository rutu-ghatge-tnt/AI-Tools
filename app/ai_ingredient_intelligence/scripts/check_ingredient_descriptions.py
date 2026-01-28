# app/ai_ingredient_intelligence/scripts/check_ingredient_descriptions.py
"""Script to check MongoDB for ingredients with enhanced_description vs description"""

import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env variables
load_dotenv()

# Read env vars
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME: str = os.getenv("DB_NAME", "skin_bb")

# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_branded_ingredients"]

async def check_ingredient_descriptions():
    """Check MongoDB for ingredients with enhanced_description vs description"""
    
    print("🔍 Checking ingredient descriptions in MongoDB...")
    print(f"Database: {DB_NAME}")
    print(f"Collection: ingre_branded_ingredients")
    print()
    
    # Count total ingredients
    total = await collection.count_documents({})
    print(f"📊 Total ingredients: {total}")
    
    # Count with enhanced_description
    with_enhanced = await collection.count_documents({"enhanced_description": {"$exists": True, "$ne": None, "$ne": ""}})
    print(f"✅ Ingredients with enhanced_description: {with_enhanced}")
    
    # Count with description (but not enhanced_description)
    with_description_only = await collection.count_documents({
        "description": {"$exists": True, "$ne": None, "$ne": ""},
        "$or": [
            {"enhanced_description": {"$exists": False}},
            {"enhanced_description": None},
            {"enhanced_description": ""}
        ]
    })
    print(f"📝 Ingredients with description only (no enhanced_description): {with_description_only}")
    
    # Count with neither
    with_neither = await collection.count_documents({
        "$and": [
            {
                "$or": [
                    {"description": {"$exists": False}},
                    {"description": None},
                    {"description": ""}
                ]
            },
            {
                "$or": [
                    {"enhanced_description": {"$exists": False}},
                    {"enhanced_description": None},
                    {"enhanced_description": ""}
                ]
            }
        ]
    })
    print(f"❌ Ingredients with neither description nor enhanced_description: {with_neither}")
    
    # Count with both
    with_both = await collection.count_documents({
        "description": {"$exists": True, "$ne": None, "$ne": ""},
        "enhanced_description": {"$exists": True, "$ne": None, "$ne": ""}
    })
    print(f"🔄 Ingredients with both description and enhanced_description: {with_both}")
    
    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Total: {total}")
    print(f"  With enhanced_description: {with_enhanced} ({with_enhanced/total*100:.1f}%)")
    print(f"  With description only: {with_description_only} ({with_description_only/total*100:.1f}%)")
    print(f"  With both: {with_both}")
    print(f"  With neither: {with_neither} ({with_neither/total*100:.1f}%)")
    print("=" * 60)
    
    # Show some examples
    print()
    print("📋 Sample ingredients with description only (no enhanced_description):")
    cursor = collection.find({
        "description": {"$exists": True, "$ne": None, "$ne": ""},
        "$or": [
            {"enhanced_description": {"$exists": False}},
            {"enhanced_description": None},
            {"enhanced_description": ""}
        ]
    }, {
        "ingredient_name": 1,
        "description": 1,
        "enhanced_description": 1
    }).limit(5)
    
    count = 0
    async for doc in cursor:
        count += 1
        desc = doc.get("description", "")[:100] + "..." if len(doc.get("description", "")) > 100 else doc.get("description", "")
        print(f"  {count}. {doc.get('ingredient_name', 'N/A')}")
        print(f"     Description: {desc}")
        print()
    
    if count == 0:
        print("  (None found)")
    
    print()
    print("📋 Sample ingredients with neither description nor enhanced_description:")
    cursor = collection.find({
        "$and": [
            {
                "$or": [
                    {"description": {"$exists": False}},
                    {"description": None},
                    {"description": ""}
                ]
            },
            {
                "$or": [
                    {"enhanced_description": {"$exists": False}},
                    {"enhanced_description": None},
                    {"enhanced_description": ""}
                ]
            }
        ]
    }, {
        "ingredient_name": 1,
        "description": 1,
        "enhanced_description": 1
    }).limit(5)
    
    count = 0
    async for doc in cursor:
        count += 1
        print(f"  {count}. {doc.get('ingredient_name', 'N/A')}")
    
    if count == 0:
        print("  (None found)")

if __name__ == "__main__":
    asyncio.run(check_ingredient_descriptions())

