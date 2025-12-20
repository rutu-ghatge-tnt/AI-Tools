"""Check all backup files to find the one with correct Active ingredient count"""

import json
import os
from pathlib import Path

backup_files = [
    "cleaned_specialchem_ingredients.json.backup_20251219_133151",
    "cleaned_specialchem_ingredients.json.backup_20251218_200344",
    "cleaned_specialchem_ingredients.json.pre_save_20251219_143343",
    "cleaned_specialchem_ingredients.json.pre_save_20251218_201156",
    "cleaned_specialchem_ingredients.json.before_restore",
]

print("=" * 80)
print("Checking All Backup Files for Active Ingredient Count")
print("=" * 80)

results = []

for backup_file in backup_files:
    if not os.path.exists(backup_file):
        continue
    
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total = len(data)
        actives = [r for r in data if r.get("category_decided") == "Active"]
        active_count = len(actives)
        with_desc = [r for r in actives if r.get("enhanced_description")]
        
        file_size = os.path.getsize(backup_file) / (1024 * 1024)  # MB
        
        results.append({
            "file": backup_file,
            "total": total,
            "actives": active_count,
            "with_desc": len(with_desc),
            "size_mb": file_size
        })
        
        print(f"\n{backup_file}:")
        print(f"  Total records: {total}")
        print(f"  Active ingredients: {active_count}")
        print(f"  Active with enhanced_description: {len(with_desc)}")
        print(f"  File size: {file_size:.2f} MB")
        
    except Exception as e:
        print(f"\n{backup_file}: ERROR - {e}")

print("\n" + "=" * 80)
print("SUMMARY - Files sorted by Active count:")
print("=" * 80)

results.sort(key=lambda x: x["actives"], reverse=True)

for r in results:
    print(f"{r['actives']:5d} Actives | {r['total']:5d} total | {r['size_mb']:6.2f} MB | {r['file']}")

# Find the one with ~17,000 actives
target = [r for r in results if 16000 <= r["actives"] <= 18000]
if target:
    print("\n" + "=" * 80)
    print("FOUND FILE WITH ~17,000 ACTIVES:")
    print("=" * 80)
    for r in target:
        print(f"  {r['file']} - {r['actives']} Actives")

