"""
Restore cleaned_specialchem_ingredients.json from backup
"""

import json
import shutil
import os
from pathlib import Path

BACKUP_FILE = "cleaned_specialchem_ingredients.json.backup_20251218_200344"  # This one has 17,142 Actives
CURRENT_FILE = "cleaned_specialchem_ingredients.json"

def restore_from_backup():
    """Restore from backup file"""
    
    print("=" * 80)
    print("RESTORING FROM BACKUP")
    print("=" * 80)
    
    if not os.path.exists(BACKUP_FILE):
        print(f"ERROR: Backup file not found: {BACKUP_FILE}")
        return False
    
    print(f"\n1. Verifying backup file...")
    try:
        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        print(f"   Backup has {len(backup_data)} records")
        
        # Count what we have
        actives = [r for r in backup_data if r.get("category_decided") == "Active"]
        with_desc = [r for r in actives if r.get("enhanced_description")]
        print(f"   Active ingredients: {len(actives)}")
        print(f"   Active with enhanced_description: {len(with_desc)}")
        
    except Exception as e:
        print(f"   ERROR: Backup file is corrupted: {e}")
        return False
    
    # Backup current file first
    if os.path.exists(CURRENT_FILE):
        backup_current = CURRENT_FILE + ".before_restore"
        print(f"\n2. Backing up current file to: {backup_current}")
        try:
            shutil.copy2(CURRENT_FILE, backup_current)
            print(f"   Current file backed up")
        except Exception as e:
            print(f"   WARNING: Could not backup current file: {e}")
    
    # Restore from backup
    print(f"\n3. Restoring from backup...")
    try:
        shutil.copy2(BACKUP_FILE, CURRENT_FILE)
        print(f"   Restored {len(backup_data)} records")
        
        # Verify restore
        with open(CURRENT_FILE, 'r', encoding='utf-8') as f:
            restored_data = json.load(f)
        
        if len(restored_data) == len(backup_data):
            print(f"   VERIFIED: Restore successful!")
            return True
        else:
            print(f"   WARNING: Record count mismatch!")
            return False
            
    except Exception as e:
        print(f"   ERROR: Restore failed: {e}")
        return False

if __name__ == "__main__":
    success = restore_from_backup()
    if success:
        print("\n" + "=" * 80)
        print("RESTORE COMPLETE!")
        print("=" * 80)
        print("\nNext: Run the enhancement script - it will only process missing records")
    else:
        print("\n" + "=" * 80)
        print("RESTORE FAILED!")
        print("=" * 80)

