"""
Restore category_decided from backup file to current cleaned file
"""

import json
import os
from collections import defaultdict

# Files
BACKUP_FILE = "cleaned_specialchem_ingredients.json.backup_20251218_200344"  # Fully categorized backup
CURRENT_FILE = "cleaned_specialchem_ingredients.json"
OUTPUT_FILE = "cleaned_specialchem_ingredients.json"

print("=" * 80)
print("Restoring Categories from Backup")
print("=" * 80)

# Load backup (has categories)
print(f"\nLoading backup file: {BACKUP_FILE}")
with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
    backup_data = json.load(f)
print(f"Loaded {len(backup_data)} records from backup")

# Create lookup by ingredient_name + supplier (unique identifier)
backup_lookup = {}
for record in backup_data:
    key = (record.get("ingredient_name", ""), record.get("supplier", ""))
    if key not in backup_lookup:
        backup_lookup[key] = record.get("category_decided")

print(f"Created lookup for {len(backup_lookup)} unique ingredients")

# Load current file (no categories)
print(f"\nLoading current file: {CURRENT_FILE}")
with open(CURRENT_FILE, 'r', encoding='utf-8') as f:
    current_data = json.load(f)
print(f"Loaded {len(current_data)} records from current file")

# Restore categories
print(f"\nRestoring categories...")
restored_count = 0
for record in current_data:
    key = (record.get("ingredient_name", ""), record.get("supplier", ""))
    if key in backup_lookup:
        category = backup_lookup[key]
        if category and record.get("category_decided") is None:
            record["category_decided"] = category
            restored_count += 1

print(f"Restored categories for {restored_count} records")

# Count categories
active_count = sum(1 for r in current_data if r.get("category_decided") == "Active")
excipient_count = sum(1 for r in current_data if r.get("category_decided") == "Excipient")
uncategorized_count = sum(1 for r in current_data if r.get("category_decided") not in ["Active", "Excipient"])

print(f"\nCategory Summary:")
print(f"   Active: {active_count}")
print(f"   Excipient: {excipient_count}")
print(f"   Uncategorized: {uncategorized_count}")

# Save
print(f"\nSaving to {OUTPUT_FILE}...")
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(current_data, f, indent=2, ensure_ascii=False)
print(f"Saved {len(current_data)} records with restored categories")

print("\n" + "=" * 80)
print("Categories restored successfully!")
print("=" * 80)
print(f"\nNow you can run clean_specialchem_data.py again to enhance Active ingredients")

