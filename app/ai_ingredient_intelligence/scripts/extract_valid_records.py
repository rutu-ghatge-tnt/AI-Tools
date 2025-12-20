"""
Extract valid records from corrupted JSON file
This tries to recover as many records as possible from a corrupted file
"""

import json
import re
from typing import List, Dict, Any

CORRUPTED_FILE = "cleaned_specialchem_ingredients.json"
OUTPUT_FILE = "cleaned_specialchem_ingredients.json.recovered"

def extract_valid_records():
    """Extract valid records from corrupted JSON"""
    
    print("=" * 80)
    print("Extracting Valid Records from Corrupted File")
    print("=" * 80)
    
    print(f"\nReading corrupted file: {CORRUPTED_FILE}")
    with open(CORRUPTED_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    print(f"File size: {len(content)} characters")
    
    # Try to find where the corruption starts
    # Look for the last complete record
    print("\nSearching for valid records...")
    
    # Try parsing incrementally
    valid_records = []
    corruption_point = None
    
    # Method 1: Try to find complete records using regex
    # Look for complete JSON objects
    record_pattern = r'\{\s*"ingredient_name"[^}]*"extra_data"[^}]*\}'
    matches = re.finditer(record_pattern, content, re.DOTALL)
    
    found_records = []
    for match in matches:
        try:
            record = json.loads(match.group())
            if record.get("ingredient_name"):
                found_records.append(record)
        except:
            continue
    
    print(f"Found {len(found_records)} potentially valid records via regex")
    
    # Method 2: Try incremental parsing
    print("\nTrying incremental parsing...")
    for i in range(len(content), 0, -1000):  # Check every 1000 chars from end
        try:
            test_content = content[:i] + "]"
            test_data = json.loads(test_content)
            if isinstance(test_data, list) and len(test_data) > 0:
                valid_records = test_data
                corruption_point = i
                print(f"SUCCESS! Found {len(valid_records)} valid records")
                print(f"Corruption starts around character {i}")
                break
        except:
            continue
    
    if not valid_records and found_records:
        print("Using regex-extracted records...")
        valid_records = found_records
    
    if not valid_records:
        print("ERROR: Could not extract any valid records")
        return
    
    # Count enhanced descriptions
    actives = [r for r in valid_records if r.get("category_decided") == "Active"]
    actives_with_desc = [r for r in actives if r.get("enhanced_description")]
    
    print(f"\nRecovery Summary:")
    print(f"   Total valid records: {len(valid_records)}")
    print(f"   Active ingredients: {len(actives)}")
    print(f"   Active with enhanced_description: {len(actives_with_desc)} ({len(actives_with_desc)*100/len(actives):.1f}%)")
    
    # Save recovered data
    print(f"\nSaving recovered data to: {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(valid_records, f, indent=2, ensure_ascii=False)
        print(f"   Saved {len(valid_records)} records")
        print(f"\nNext steps:")
        print(f"   1. Review: {OUTPUT_FILE}")
        print(f"   2. If good, replace: copy {OUTPUT_FILE} {CORRUPTED_FILE}")
        print(f"   3. Run enhancement script - it will only process missing records")
    except Exception as e:
        print(f"   ERROR saving: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    extract_valid_records()

