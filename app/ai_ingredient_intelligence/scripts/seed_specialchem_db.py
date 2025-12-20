# scripts/seed_specialchem_db.py

"""
Seeds MongoDB with cleaned SpecialChem ingredient data
Similar to seed_db.py but optimized for SpecialChem data with all extra fields.

What this does:
1) Inserts/links:
   - INCI                    -> collection: ingre_inci
   - Suppliers               -> ingre_suppliers
   - Functional categories   -> ingre_functional_categories (with hierarchy)
   - Chemical classes        -> ingre_chemical_classes (with hierarchy)
   - Branded ingredients     -> ingre_branded_ingredients (links to all above)
2) Preserves all extra fields from SpecialChem:
   - product_category, product_type, product_family_raw, product_type_raw
   - characteristics, benefits, properties, compliance, applications
   - application_formats, documents, source
3) Creates helpful normalized fields for search/index
4) Creates indexes for faster lookups
5) HANDLES DUPLICATES: Replaces existing ingredients with same normalized name

Usage:
  python app/ai_ingredient_intelligence/scripts/seed_specialchem_db.py
"""

import json
import os
import sys
import time
import unicodedata
import re
from typing import List, Optional, Tuple, Dict, Any
from pymongo import MongoClient, ASCENDING
from bson.objectid import ObjectId
from tqdm import tqdm
from pathlib import Path

# Add project root to path to import config
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.config import MONGO_URI, DB_NAME

# -------------------
# Config
# -------------------
DATA_FILE = project_root / "cleaned_specialchem_ingredients.json"
CHECKPOINT_FILE = project_root / "seeding_checkpoint.json"

# Toggle behaviors
CREATE_INDEXES = True
BATCH_SIZE = 100  # Checkpoint every N records

# -------------------
# Connect
# -------------------
mongo_display = MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI
print(f"Connecting to MongoDB: {mongo_display}")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collections
branded_col = db["ingre_branded_ingredients"]
inci_col = db["ingre_inci"]
supplier_col = db["ingre_suppliers"]
func_cat_col = db["ingre_functional_categories"]
chem_class_col = db["ingre_chemical_classes"]
docs_col = db["ingre_documents"]
formulations_col = db["ingre_formulations"]

# -------------------
# Caches (avoid dups)
# -------------------
inci_cache = {}
supplier_cache = {}
func_cat_cache = {}
chem_class_cache = {}
branded_ingredient_cache = {}

# -------------------
# Helpers
# -------------------
def normalize_text(s: str) -> str:
    """Remove accents, lowercase, collapse spaces for search normalization."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()

def get_or_create_inci(name: Optional[str]) -> Optional[ObjectId]:
    """Create/find an INCI by name; also stores a normalized variant for fast search."""
    if not name:
        return None
    norm = normalize_text(name)
    if norm in inci_cache:
        return inci_cache[norm]
    doc = inci_col.find_one({"inciName_normalized": norm}, {"_id": 1})
    if doc:
        _id = doc["_id"]
    else:
        _id = inci_col.insert_one({"inciName": name, "inciName_normalized": norm}).inserted_id
    inci_cache[norm] = _id
    return _id

def get_or_create_supplier(name: Optional[str]) -> Optional[ObjectId]:
    """Create/find a supplier by exact name (no normalization for display accuracy)."""
    if not name:
        return None
    if name in supplier_cache:
        return supplier_cache[name]
    doc = supplier_col.find_one({"supplierName": name}, {"_id": 1})
    if doc:
        _id = doc["_id"]
    else:
        _id = supplier_col.insert_one({"supplierName": name}).inserted_id
    supplier_cache[name] = _id
    return _id

def get_or_create_category(
    tree: List[str],
    col,
    cache: dict,
    name_field: str,
    norm_field: str
) -> Optional[ObjectId]:
    """Create/find a nested category structure."""
    if not tree:
        return None
    
    parent_id = None
    for level, name in enumerate(tree, start=1):
        if not name or not name.strip():
            continue
        key = (name.strip(), parent_id)
        if key in cache:
            _id = cache[key]
        else:
            doc = col.find_one({name_field: name.strip(), "parent_id": parent_id}, {"_id": 1})
            if doc:
                _id = doc["_id"]
            else:
                _id = col.insert_one({
                    name_field: name.strip(),
                    norm_field: normalize_text(name.strip()),
                    "level": level,
                    "parent_id": parent_id
                }).inserted_id
            cache[key] = _id
        parent_id = _id
    return parent_id

def remove_duplicate_ingredient(ingredient_name: str) -> bool:
    """Remove existing ingredient with same normalized name if it exists. Returns True if removed."""
    if not ingredient_name:
        return False
    
    norm_name = normalize_text(ingredient_name)
    
    # Check cache first
    existing_id = branded_ingredient_cache.get(norm_name)
    
    # Also check database
    if not existing_id:
        doc = branded_col.find_one(
            {"ingredient_name_normalized": norm_name},
            {"_id": 1}
        )
        if doc:
            existing_id = doc["_id"]
    
    # Remove if exists (REPLACE old with new)
    if existing_id:
        branded_col.delete_one({"_id": existing_id})
        if norm_name in branded_ingredient_cache:
            del branded_ingredient_cache[norm_name]
        return True
    
    return False

def create_indexes():
    """Create helpful indexes once. Safe to run repeatedly."""
    print("Creating indexes...")
    
    try:
        inci_col.create_index([("inciName_normalized", ASCENDING)], name="idx_inci_norm", background=True)
        func_cat_col.create_index([("functionalName_normalized", ASCENDING)], name="idx_func_norm", background=True)
        chem_class_col.create_index([("chemicalClassName_normalized", ASCENDING)], name="idx_chem_norm", background=True)
        branded_col.create_index([("ingredient_name_normalized", ASCENDING)], name="idx_branded_name_norm", background=True)
        branded_col.create_index([("inci_ids", ASCENDING)], name="idx_branded_inci_ids", background=True)
        branded_col.create_index([("supplier_id", ASCENDING)], name="idx_branded_supplier", background=True)
        branded_col.create_index([("functional_category_ids", ASCENDING)], name="idx_branded_func", background=True)
        branded_col.create_index([("chemical_class_ids", ASCENDING)], name="idx_branded_chem", background=True)
        print("Indexes created successfully")
    except Exception as e:
        print(f"Warning: Some indexes might already exist: {e}")

def load_seed_checkpoint() -> Dict[str, Any]:
    """Load seeding checkpoint if exists"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_seed_checkpoint(checkpoint_data: Dict[str, Any]):
    """Save seeding checkpoint"""
    try:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save checkpoint: {e}")

def estimate_time_remaining(start_time: float, processed: int, total: int) -> str:
    """Estimate time remaining based on current progress"""
    if processed == 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    remaining = (total - processed) / rate if rate > 0 else 0
    
    if remaining < 60:
        return f"{int(remaining)}s"
    elif remaining < 3600:
        return f"{int(remaining // 60)}m {int(remaining % 60)}s"
    else:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return f"{hours}h {minutes}m"

def seed_main():
    """Main seeding function"""
    start_time = time.time()
    
    # Load checkpoint
    checkpoint = load_seed_checkpoint()
    processed_ingredients = set(checkpoint.get("processed_ingredients", []))
    start_index = checkpoint.get("last_processed_index", 0)
    inserted_count = checkpoint.get("inserted_count", 0)
    replaced_count = checkpoint.get("replaced_count", 0)
    error_count = checkpoint.get("error_count", 0)
    
    # Check if data file exists
    if not os.path.exists(DATA_FILE):
        print(f"Error: Data file not found: {DATA_FILE}")
        print(f"   Please run clean_specialchem_data.py first to generate the cleaned data file.")
        return
    
    # Load data
    print(f"Loading data from {DATA_FILE}...")
    file_size_mb = os.path.getsize(DATA_FILE) / (1024 * 1024)
    print(f"   File size: {file_size_mb:.2f} MB")
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading data file: {e}")
        return
    
    total_records = len(data)
    
    if start_index > 0:
        print(f"\nResuming seeding from checkpoint: {start_index}/{total_records} records already processed")
        print(f"   Continuing from record {start_index + 1}...")
        print(f"   Already inserted: {inserted_count}")
        print(f"   Already replaced: {replaced_count}")
    else:
        print(f"\nStarting fresh seeding (no checkpoint found)")
        print(f"   Total records to process: {total_records}")
    
    # Estimate total time
    estimated_time_per_record = 0.03
    estimated_total_time = total_records * estimated_time_per_record
    print(f"\nTime Estimate:")
    print(f"   Estimated time per record: ~{estimated_time_per_record:.3f}s")
    print(f"   Estimated total time: ~{estimated_total_time/60:.1f} minutes ({estimated_total_time/3600:.2f} hours)")
    print(f"   (Actual time may vary based on database performance)")
    
    # Process records
    print(f"\nStarting seeding process...\n")
    
    for idx, item in enumerate(tqdm(data[start_index:], desc="Seeding data", initial=start_index, total=total_records, unit="records")):
        current_index = start_index + idx
        
        try:
            ingredient_name = item.get("ingredient_name", "").strip()
            
            if not ingredient_name:
                error_count += 1
                continue
            
            # Remove duplicate if exists (REPLACE old with new)
            was_duplicate = remove_duplicate_ingredient(ingredient_name)
            if was_duplicate:
                replaced_count += 1
            
            # INCI references
            inci_ids = []
            for n in item.get("inci_names", []):
                if n and n.strip():
                    oid = get_or_create_inci(n.strip())
                    if oid:
                        inci_ids.append(oid)
            
            # Supplier
            supplier_id = get_or_create_supplier(item.get("supplier"))
            
            # Functional categories
            func_ids: List[ObjectId] = []
            for tree in item.get("functionality_category_tree", []):
                if tree and isinstance(tree, list):
                    fid = get_or_create_category(
                        tree=tree,
                        col=func_cat_col,
                        cache=func_cat_cache,
                        name_field="functionalName",
                        norm_field="functionalName_normalized",
                    )
                    if fid:
                        func_ids.append(fid)
            
            # Chemical classes
            chem_ids: List[ObjectId] = []
            for tree in item.get("chemical_class_category_tree", []):
                if tree and isinstance(tree, list):
                    cid = get_or_create_category(
                        tree=tree,
                        col=chem_class_col,
                        cache=chem_class_cache,
                        name_field="chemicalClassName",
                        norm_field="chemicalClassName_normalized",
                    )
                    if cid:
                        chem_ids.append(cid)
            
            # Build branded ingredient document with ALL extra fields
            branded_doc = {
                "ingredient_name": ingredient_name,
                "ingredient_name_normalized": normalize_text(ingredient_name),
                "original_inci_name": item.get("original_inci_name", ""),
                "inci_ids": inci_ids,
                "functional_category_ids": func_ids,
                "chemical_class_ids": chem_ids,
                "supplier_id": supplier_id,
                "description": item.get("description", "") or "",
                "documents_id": [],
            }
            
            # Add enhanced description if available
            if item.get("enhanced_description"):
                branded_doc["enhanced_description"] = item.get("enhanced_description")
            
            # Add category_decided if available
            if item.get("category_decided"):
                branded_doc["category_decided"] = item.get("category_decided")
            
            # Add ALL extra_data fields from SpecialChem (preserve everything including source)
            if item.get("extra_data"):
                extra_data = item.get("extra_data")
                branded_doc["extra_data"] = {
                    "product_category": extra_data.get("product_category", ""),
                    "product_type": extra_data.get("product_type", []),
                    "product_family_raw": extra_data.get("product_family_raw", ""),
                    "product_type_raw": extra_data.get("product_type_raw", ""),
                    "characteristics": extra_data.get("characteristics", {}),
                    "benefits": extra_data.get("benefits", []),
                    "properties": extra_data.get("properties", []),
                    "compliance": extra_data.get("compliance", []),
                    "applications": extra_data.get("applications", []),
                    "application_formats": extra_data.get("application_formats", []),
                    "documents": extra_data.get("documents", []),
                    "source": extra_data.get("source", "specialchem")  # CRITICAL: Preserve source for filtering
                }
            
            # Insert and cache
            result = branded_col.insert_one(branded_doc)
            norm_name = normalize_text(ingredient_name)
            branded_ingredient_cache[norm_name] = result.inserted_id
            processed_ingredients.add(norm_name)
            inserted_count += 1
            
            # Save checkpoint every BATCH_SIZE records
            if (current_index + 1) % BATCH_SIZE == 0:
                elapsed = time.time() - start_time
                rate = (current_index + 1) / elapsed if elapsed > 0 else 0
                remaining_time = estimate_time_remaining(start_time, current_index + 1, total_records)
                
                save_seed_checkpoint({
                    "last_processed_index": current_index + 1,
                    "processed_ingredients": list(processed_ingredients),
                    "inserted_count": inserted_count,
                    "replaced_count": replaced_count,
                    "error_count": error_count
                })
                
                tqdm.write(f"Checkpoint saved @ {current_index + 1}/{total_records} | "
                          f"Rate: {rate:.1f} rec/s | "
                          f"ETA: {remaining_time} | "
                          f"Inserted: {inserted_count} | "
                          f"Replaced: {replaced_count}")
        
        except Exception as e:
            error_count += 1
            tqdm.write(f"Error processing record {current_index + 1}: {e}")
            continue
    
    # Final summary
    total_time = time.time() - start_time
    print(f"\n" + "="*80)
    print(f"Seeding Summary:")
    print(f"="*80)
    print(f"   Inserted: {inserted_count} ingredients")
    print(f"   Replaced duplicates: {replaced_count} ingredients")
    print(f"   Errors: {error_count} records")
    print(f"   Total processed: {total_records} ingredients")
    print(f"   Total time: {total_time/60:.2f} minutes ({total_time:.2f} seconds)")
    print(f"   Average rate: {total_records/total_time:.2f} records/second")
    print(f"="*80)
    
    # Remove checkpoint file on successful completion
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print(f"Removed checkpoint file (seeding complete)")
    
    # Verify counts in database
    print(f"\nVerifying database...")
    db_inserted = branded_col.count_documents({})
    db_inci = inci_col.count_documents({})
    db_suppliers = supplier_col.count_documents({})
    db_func_cats = func_cat_col.count_documents({})
    db_chem_classes = chem_class_col.count_documents({})
    
    print(f"   Branded ingredients in DB: {db_inserted}")
    print(f"   INCI names in DB: {db_inci}")
    print(f"   Suppliers in DB: {db_suppliers}")
    print(f"   Functional categories in DB: {db_func_cats}")
    print(f"   Chemical classes in DB: {db_chem_classes}")

# -------------------
# Main
# -------------------
if __name__ == "__main__":
    print("="*80)
    print("SpecialChem MongoDB Seeding Script")
    print("="*80)
    print(f"Data file: {DATA_FILE}")
    print(f"Checkpoint file: {CHECKPOINT_FILE}")
    print(f"Database: {DB_NAME}")
    print(f"MongoDB URI: {MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI}")
    print("="*80)
    
    if CREATE_INDEXES:
        create_indexes()
        print()
    
    seed_main()
    print("\nSeeding of core collections completed.")
    print("All done!")

