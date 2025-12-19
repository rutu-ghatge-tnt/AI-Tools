import json
import glob
import os

print("=" * 80)
print("Checking All Backup Files for Categories")
print("=" * 80)

backup_files = sorted(glob.glob('cleaned_specialchem_ingredients.json.backup_*'), reverse=True)

for backup_file in backup_files:
    print(f"\n{backup_file}:")
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total = len(data)
        active = sum(1 for r in data if r.get("category_decided") == "Active")
        excipient = sum(1 for r in data if r.get("category_decided") == "Excipient")
        null = sum(1 for r in data if r.get("category_decided") is None)
        other = total - active - excipient - null
        
        print(f"  Total records: {total}")
        print(f"  Active: {active} ({active*100/total:.1f}%)")
        print(f"  Excipient: {excipient} ({excipient*100/total:.1f}%)")
        print(f"  Null/None: {null} ({null*100/total:.1f}%)")
        print(f"  Other: {other}")
        
        if active + excipient > total * 0.8:  # If >80% categorized
            print(f"  *** FULLY CATEGORIZED ***")
            print(f"  This is the file to use!")
            
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "=" * 80)

