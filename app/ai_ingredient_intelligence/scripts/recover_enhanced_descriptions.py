"""
Recover enhanced descriptions from backup files and merge into current file
This script helps recover enhanced descriptions that were lost due to file corruption
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List

# Files
CURRENT_FILE = "cleaned_specialchem_ingredients.json"
BACKUP_FILES = [
    "cleaned_specialchem_ingredients.json.backup_20251219_133151",
    "cleaned_specialchem_ingredients.json.pre_save_20251219_143343",
    "cleaned_specialchem_ingredients.json.backup_20251218_200344",
    "cleaned_specialchem_ingredients.json.pre_save_20251218_201156",
]

def load_json_safe(filepath: str) -> List[Dict[str, Any]]:
    """Load JSON file safely, handling corruption"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"   WARNING: {filepath} is corrupted: {e}")
        return []
    except Exception as e:
        print(f"   WARNING: Error loading {filepath}: {e}")
        return []

def create_ingredient_key(record: Dict[str, Any]) -> str:
    """Create unique key for ingredient matching"""
    name = record.get("ingredient_name", "").strip().lower()
    supplier = record.get("supplier", "").strip().lower()
    return f"{name}|||{supplier}"

def recover_enhanced_descriptions():
    """Recover enhanced descriptions from backup files"""
    
    print("=" * 80)
    print("Enhanced Descriptions Recovery Tool")
    print("=" * 80)
    
    # Load current file (might be corrupted or incomplete)
    print(f"\nLoading current file: {CURRENT_FILE}")
    current_data = []
    try:
        current_data = load_json_safe(CURRENT_FILE)
        if current_data:
            print(f"   Loaded {len(current_data)} records")
        else:
            print(f"   Current file is corrupted or empty")
    except:
        print(f"   Current file is corrupted or missing")
    
    # Create lookup for current data
    current_lookup = {}
    for record in current_data:
        key = create_ingredient_key(record)
        current_lookup[key] = record
    
    # Check backup files
    print(f"\nChecking backup files for enhanced descriptions...")
    recovered_count = 0
    backup_enhanced = {}
    
    for backup_file in BACKUP_FILES:
        if not os.path.exists(backup_file):
            print(f"   SKIP: {backup_file} - not found")
            continue
        
        print(f"\n   Checking: {backup_file}")
        backup_data = load_json_safe(backup_file)
        
        if not backup_data:
            continue
        
        print(f"      Loaded {len(backup_data)} records")
        
        # Find records with enhanced_description
        for record in backup_data:
            if record.get("enhanced_description") and record.get("category_decided") == "Active":
                key = create_ingredient_key(record)
                
                # Only keep if we don't already have it or if this one is better
                if key not in backup_enhanced:
                    backup_enhanced[key] = {
                        "enhanced_description": record.get("enhanced_description"),
                        "category_decided": record.get("category_decided"),
                        "source_file": backup_file
                    }
        
        enhanced_in_backup = len([r for r in backup_data if r.get("enhanced_description") and r.get("category_decided") == "Active"])
        print(f"      Found {enhanced_in_backup} Active ingredients with enhanced_description")
    
    print(f"\nRecovery Summary:")
    print(f"   Total enhanced descriptions found in backups: {len(backup_enhanced)}")
    
    # Merge into current data
    print(f"\nMerging enhanced descriptions into current data...")
    merged_count = 0
    new_count = 0
    
    for key, enhanced_data in backup_enhanced.items():
        if key in current_lookup:
            current_record = current_lookup[key]
            if not current_record.get("enhanced_description"):
                # Add enhanced description
                current_record["enhanced_description"] = enhanced_data["enhanced_description"]
                if enhanced_data.get("category_decided"):
                    current_record["category_decided"] = enhanced_data["category_decided"]
                merged_count += 1
        else:
            # Record not in current data - might need to add it
            new_count += 1
    
    print(f"   Merged {merged_count} enhanced descriptions into existing records")
    if new_count > 0:
        print(f"   WARNING: {new_count} enhanced records not found in current data (might be from different version)")
    
    # Count final stats
    actives = [r for r in current_data if r.get("category_decided") == "Active"]
    actives_with_desc = [r for r in actives if r.get("enhanced_description")]
    
    print(f"\nFinal Statistics:")
    print(f"   Total records: {len(current_data)}")
    print(f"   Active ingredients: {len(actives)}")
    print(f"   Active with enhanced_description: {len(actives_with_desc)} ({len(actives_with_desc)*100/len(actives):.1f}%)")
    print(f"   Still missing: {len(actives) - len(actives_with_desc)}")
    
    # Save recovered data
    output_file = CURRENT_FILE + ".recovered"
    print(f"\nSaving recovered data to: {output_file}")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print(f"   Saved {len(current_data)} records")
        print(f"\nNext steps:")
        print(f"   1. Review the recovered file: {output_file}")
        print(f"   2. If it looks good, replace the current file:")
        print(f"      copy {output_file} {CURRENT_FILE}")
        print(f"   3. Run the enhancement script again - it will only process missing records")
    except Exception as e:
        print(f"   ERROR saving: {e}")
    
    print("\n" + "=" * 80)
    print("Recovery complete!")
    print("=" * 80)

if __name__ == "__main__":
    recover_enhanced_descriptions()

