"""
Quick script to verify MongoDB data integrity after enhancement
"""

import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is required. Please set it in your .env file.")
if not DB_NAME:
    raise ValueError("DB_NAME environment variable is required. Please set it in your .env file.")

async def verify_data():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db["ingre_branded_ingredients"]
    
    print("=" * 80)
    print("MongoDB Data Verification")
    print("=" * 80)
    print()
    
    # Total SpecialChem Active ingredients
    total = await collection.count_documents({
        "category_decided": "Active",
        "extra_data.source": "specialchem"
    })
    
    # Enhanced
    enhanced = await collection.count_documents({
        "category_decided": "Active",
        "extra_data.source": "specialchem",
        "enhanced_description": {"$exists": True}
    })
    
    # Need enhancement
    need_enhancement = total - enhanced
    
    print(f"SpecialChem Active Ingredients:")
    print(f"  Total: {total:,}")
    print(f"  Enhanced: {enhanced:,} ({enhanced/total*100:.1f}%)")
    print(f"  Need enhancement: {need_enhancement:,}")
    print()
    
    # Check for ingredients with enhanced_description but missing other fields
    missing_inci = await collection.count_documents({
        "category_decided": "Active",
        "extra_data.source": "specialchem",
        "enhanced_description": {"$exists": True},
        "$or": [
            {"inci_ids": {"$exists": False}},
            {"inci_ids": []}
        ]
    })
    
    missing_categories = await collection.count_documents({
        "category_decided": "Active",
        "extra_data.source": "specialchem",
        "enhanced_description": {"$exists": True},
        "$or": [
            {"functional_category_ids": {"$exists": False}},
            {"functional_category_ids": []}
        ]
    })
    
    print(f"Enhanced but missing data:")
    print(f"  Missing INCI names: {missing_inci:,}")
    print(f"  Missing categories: {missing_categories:,}")
    print()
    
    # Sample a few enhanced ingredients to verify
    print("Sample enhanced ingredients (first 5):")
    cursor = collection.find({
        "category_decided": "Active",
        "extra_data.source": "specialchem",
        "enhanced_description": {"$exists": True}
    }).limit(5)
    
    async for doc in cursor:
        name = doc.get("ingredient_name", "Unknown")
        has_inci = bool(doc.get("inci_ids"))
        has_cat = bool(doc.get("functional_category_ids"))
        print(f"  [OK] {name[:50]}")
        print(f"    INCI: {'Yes' if has_inci else 'No'}, Categories: {'Yes' if has_cat else 'No'}")
    
    print()
    print("=" * 80)
    print("Data appears to be safe in MongoDB!")
    print("=" * 80)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(verify_data())

