import json
import re
from collections import Counter, defaultdict

# Read the JSON file (JSONL format)
print("Loading JSON file...")
data = []
with open('output_specialChem_1765800534743.json', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                continue

print(f"Loaded {len(data)} items\n")

# URL pattern for detection
url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)

# Analyze structure in detail
print("="*80)
print("DETAILED FIELD ANALYSIS")
print("="*80)

# Analyze nested structures
def analyze_field(items, field_path="", max_depth=3, current_depth=0):
    """Recursively analyze field structures"""
    if current_depth >= max_depth:
        return
    
    if not field_path:
        # Top level - analyze all keys
        all_keys = set()
        for item in items:
            if isinstance(item, dict):
                all_keys.update(item.keys())
        
        for key in sorted(all_keys):
            values = [item.get(key) for item in items if isinstance(item, dict)]
            analyze_field(values, key, max_depth, current_depth + 1)
    else:
        # Analyze this specific field
        non_null = [v for v in items if v is not None and v != ""]
        null_count = len(items) - len(non_null)
        
        if null_count > 0:
            print(f"\n{field_path}:")
            print(f"  Missing/Empty: {null_count}/{len(items)} ({null_count*100/len(items):.1f}%)")
        
        if not non_null:
            return
        
        sample = non_null[0]
        sample_type = type(sample).__name__
        
        # Check for URLs in this field
        url_count = 0
        if isinstance(sample, str):
            if url_pattern.search(sample):
                url_count = sum(1 for v in non_null if isinstance(v, str) and url_pattern.search(v))
                print(f"  Contains URLs: {url_count}/{len(non_null)} ({url_count*100/len(non_null):.1f}%)")
        elif isinstance(sample, list):
            for v in non_null[:10]:  # Check first 10
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and url_pattern.search(item):
                            url_count += 1
                            break
                        elif isinstance(item, dict):
                            for val in item.values():
                                if isinstance(val, str) and url_pattern.search(val):
                                    url_count += 1
                                    break
        elif isinstance(sample, dict):
            for k, v in sample.items():
                if isinstance(v, str) and url_pattern.search(v):
                    url_count += 1
                analyze_field([item.get(field_path, {}).get(k) if isinstance(item.get(field_path), dict) else None 
                               for item in data if isinstance(item, dict)], 
                              f"{field_path}.{k}", max_depth, current_depth + 1)
        
        if isinstance(sample, (list, dict)) and current_depth < max_depth - 1:
            if isinstance(sample, list) and len(sample) > 0:
                analyze_field([v[0] if isinstance(v, list) and len(v) > 0 else None 
                               for v in non_null if isinstance(v, list)], 
                              f"{field_path}[0]", max_depth, current_depth + 1)

# Analyze key fields that matter for our schema
print("\n" + "="*80)
print("KEY FIELDS FOR INGREDIENT SCHEMA MAPPING")
print("="*80)

# Map to existing schema fields
schema_mapping = {
    "ingredient_name": "product_name",
    "original_inci_name": "inci_raw",
    "supplier": "supplier_name",
    "description": "description",
    "functionality_category_tree": "product_family",
    "chemical_class_category_tree": "chemical_family"  # might not exist
}

# Analyze INCI names
print("\n1. INCI NAMES ANALYSIS:")
inci_raw_present = sum(1 for item in data if item.get("inci_raw") and item.get("inci_raw").strip())
inci_list_present = sum(1 for item in data if item.get("inci") and len(item.get("inci", [])) > 0)
print(f"  - inci_raw present: {inci_raw_present}/{len(data)} ({inci_raw_present*100/len(data):.1f}%)")
print(f"  - inci list present: {inci_list_present}/{len(data)} ({inci_list_present*100/len(data):.1f}%)")

# Sample INCI formats
inci_samples = [item.get("inci_raw", "") for item in data[:10] if item.get("inci_raw")]
print(f"  - Sample INCI formats:")
for sample in inci_samples[:5]:
    print(f"    * {sample[:100]}")

# Analyze product_family (functional categories)
print("\n2. PRODUCT FAMILY (Functional Categories) ANALYSIS:")
pf_present = sum(1 for item in data if item.get("product_family") and len(item.get("product_family", [])) > 0)
print(f"  - product_family present: {pf_present}/{len(data)} ({pf_present*100/len(data):.1f}%)")

# Check structure
pf_samples = [item.get("product_family", []) for item in data[:10] if item.get("product_family")]
if pf_samples:
    print(f"  - Structure: List of dicts with 'name' and 'url' keys")
    print(f"  - Sample categories:")
    seen = set()
    for pf_list in pf_samples[:5]:
        for pf in pf_list:
            if isinstance(pf, dict) and pf.get("name"):
                if pf["name"] not in seen:
                    print(f"    * {pf['name']}")
                    seen.add(pf["name"])
                    if len(seen) >= 10:
                        break
        if len(seen) >= 10:
            break

# Analyze chemical_family
print("\n3. CHEMICAL FAMILY ANALYSIS:")
chem_family_present = sum(1 for item in data if item.get("chemical_family") and len(item.get("chemical_family", [])) > 0)
print(f"  - chemical_family present: {chem_family_present}/{len(data)} ({chem_family_present*100/len(data):.1f}%)")

# Analyze characteristics
print("\n4. CHARACTERISTICS ANALYSIS:")
char_present = sum(1 for item in data if item.get("characteristics") and isinstance(item.get("characteristics"), dict) and len(item.get("characteristics", {})) > 0)
print(f"  - characteristics present: {char_present}/{len(data)} ({char_present*100/len(data):.1f}%)")

# Sample characteristics keys
char_keys = set()
for item in data[:100]:
    if isinstance(item.get("characteristics"), dict):
        char_keys.update(item.get("characteristics", {}).keys())
print(f"  - Common characteristic keys: {sorted(list(char_keys))[:15]}")

# Analyze properties
print("\n5. PROPERTIES ANALYSIS:")
props_present = sum(1 for item in data if item.get("properties") and len(item.get("properties", [])) > 0)
print(f"  - properties present: {props_present}/{len(data)} ({props_present*100/len(data):.1f}%)")

# Analyze documents
print("\n6. DOCUMENTS ANALYSIS:")
docs_present = sum(1 for item in data if item.get("documents") and len(item.get("documents", [])) > 0)
print(f"  - documents present: {docs_present}/{len(data)} ({docs_present*100/len(data):.1f}%)")

# URL Analysis
print("\n" + "="*80)
print("URL DETECTION ANALYSIS")
print("="*80)

url_fields = defaultdict(int)
url_field_samples = defaultdict(list)

for item in data:
    for key, value in item.items():
        if value is None:
            continue
        
        # Check strings
        if isinstance(value, str) and url_pattern.search(value):
            url_fields[key] += 1
            if len(url_field_samples[key]) < 3:
                url_field_samples[key].append(value[:150])
        
        # Check lists
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str) and url_pattern.search(v):
                    url_fields[f"{key} (list items)"] += 1
                    if len(url_field_samples[f"{key} (list items)"]) < 3:
                        url_field_samples[f"{key} (list items)"].append(v[:150])
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, str) and url_pattern.search(v2):
                            url_fields[f"{key}.{k2}"] += 1
                            if len(url_field_samples[f"{key}.{k2}"]) < 3:
                                url_field_samples[f"{key}.{k2}"].append(v2[:150])
        
        # Check dicts
        elif isinstance(value, dict):
            for k2, v2 in value.items():
                if isinstance(v2, str) and url_pattern.search(v2):
                    url_fields[f"{key}.{k2}"] += 1
                    if len(url_field_samples[f"{key}.{k2}"]) < 3:
                        url_field_samples[f"{key}.{k2}"].append(v2[:150])

print("\nFields containing URLs:")
for field, count in sorted(url_fields.items(), key=lambda x: x[1], reverse=True):
    pct = count * 100 / len(data)
    print(f"  - {field}: {count}/{len(data)} ({pct:.1f}%)")
    if field in url_field_samples and url_field_samples[field]:
        print(f"    Sample: {url_field_samples[field][0][:100]}...")

# Summary
print("\n" + "="*80)
print("DATA CLEANING REQUIREMENTS SUMMARY")
print("="*80)
print("""
1. REMOVE URLs from:
   - product_url (entire field)
   - product_family[].url
   - product_type[].url
   - inci[].url
   - documents[].document_url
   - chemical_family[].url (if exists)

2. HANDLE MISSING VALUES:
   - images: 100% empty (can remove or keep as empty array)
   - documents: 98.1% empty (keep structure)
   - compliance: 70.2% empty (keep structure)
   - applications: 44.3% empty (keep structure)
   - properties: 33.1% empty (keep structure)
   - inci: 16.2% empty (critical - need handling)
   - inci_raw: 16.1% empty (critical - need handling)

3. MAP TO EXISTING SCHEMA:
   - ingredient_name <- product_name
   - original_inci_name <- inci_raw (parse pipe-separated)
   - supplier <- supplier_name
   - description <- description
   - functionality_category_tree <- product_family (extract names, remove URLs)
   - chemical_class_category_tree <- chemical_family (if exists, extract names)

4. PRESERVE EXTRA DATA:
   - characteristics (dict)
   - benefits (list)
   - properties (list of dicts)
   - compliance (list)
   - applications (list)
   - application_formats (list)
   - availability_status (str)
   - product_category (str)
   - product_type (list, extract names)
   - scraped_at (str)
   - source (str)
""")

