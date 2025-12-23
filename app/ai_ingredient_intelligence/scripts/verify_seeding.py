"""
Quick verification script to check seeding results
Shows breakdown of ingredients by source and category
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is required. Please set it in your .env file.")
if not DB_NAME:
    raise ValueError("DB_NAME environment variable is required. Please set it in your .env file.")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_branded_ingredients"]

print("=" * 80)
print("Seeding Verification Report")
print("=" * 80)
print()

# Total count
total = collection.count_documents({})
print(f"Total ingredients in database: {total:,}")
print()

# SpecialChem ingredients
specialchem_total = collection.count_documents({"extra_data.source": "specialchem"})
specialchem_active = collection.count_documents({
    "extra_data.source": "specialchem",
    "category_decided": "Active"
})
specialchem_enhanced = collection.count_documents({
    "extra_data.source": "specialchem",
    "category_decided": "Active",
    "enhanced_description": {"$exists": True}
})
specialchem_needs_enhancement = collection.count_documents({
    "extra_data.source": "specialchem",
    "category_decided": "Active",
    "enhanced_description": {"$exists": False}
})

print(f"SpecialChem Ingredients:")
print(f"   Total SpecialChem: {specialchem_total:,}")
print(f"   Active: {specialchem_active:,}")
print(f"   Already enhanced: {specialchem_enhanced:,}")
print(f"   Need enhancement: {specialchem_needs_enhancement:,}")
print()

# Non-SpecialChem (original data)
non_specialchem = collection.count_documents({
    "$or": [
        {"extra_data.source": {"$exists": False}},
        {"extra_data.source": {"$ne": "specialchem"}}
    ]
})
print(f"Non-SpecialChem (Original) Ingredients: {non_specialchem:,}")
print()

# Category breakdown for SpecialChem
print(f"SpecialChem by Category:")
categories = ["Active", "Excipient", "Additive", "Other"]
for cat in categories:
    count = collection.count_documents({
        "extra_data.source": "specialchem",
        "category_decided": cat
    })
    if count > 0:
        print(f"   {cat}: {count:,}")

print()
print("=" * 80)
print("Summary:")
print(f"   Total: {total:,}")
print(f"   SpecialChem: {specialchem_total:,} ({specialchem_total/total*100:.1f}%)")
print(f"   Original (non-SpecialChem): {non_specialchem:,} ({non_specialchem/total*100:.1f}%)")
print(f"   SpecialChem Active needing enhancement: {specialchem_needs_enhancement:,}")
print("=" * 80)

