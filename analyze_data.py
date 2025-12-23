import json
import sys
from collections import Counter

# Read the JSON file (JSONL format - one JSON object per line)
print("Loading JSON file...")
data = []
with open('output_specialChem_1765800534743.json', 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        line = line.strip()
        if line:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: Error parsing line {line_num}: {e}")
                continue

print(f"\n{'='*60}")
print("DATA STRUCTURE OVERVIEW")
print(f"{'='*60}")

print(f"Type: List (JSONL format)")
print(f"Total items: {len(data)}")

if len(data) > 0:
    sample = data[0]
    print(f"\nFirst item type: {type(sample)}")
    if isinstance(sample, dict):
        print(f"First item keys ({len(sample)} keys):")
        for key in list(sample.keys()):
            value = sample[key]
            value_type = type(value).__name__
            if isinstance(value, str):
                value_preview = value[:100] + "..." if len(value) > 100 else value
            elif isinstance(value, list):
                value_preview = f"List with {len(value)} items"
                if len(value) > 0:
                    value_preview += f" (first: {type(value[0]).__name__})"
            elif isinstance(value, dict):
                value_preview = f"Dict with {len(value)} keys"
            else:
                value_preview = str(value)[:100]
            print(f"  - {key}: {value_type} = {value_preview}")

# Analyze all items for missing values and URL patterns
print(f"\n{'='*60}")
print("DATA QUALITY ANALYSIS")
print(f"{'='*60}")

items = data
print(f"Analyzing {len(items)} items...")

# Collect all keys across all items
all_keys = set()
key_counts = Counter()
missing_values = {}
url_fields = []
url_patterns = ['http://', 'https://', 'www.', '.com', '.org', '.net', '.edu']

for item in items:
    if isinstance(item, dict):
        for key, value in item.items():
            all_keys.add(key)
            key_counts[key] += 1
            
            # Check for missing/null values
            if value is None or value == "" or (isinstance(value, list) and len(value) == 0) or (isinstance(value, dict) and len(value) == 0):
                if key not in missing_values:
                    missing_values[key] = 0
                missing_values[key] += 1
            
            # Check for URLs
            if isinstance(value, str):
                if any(pattern in value.lower() for pattern in url_patterns):
                    if key not in url_fields:
                        url_fields.append(key)
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, str) and any(pattern in v.lower() for pattern in url_patterns):
                        if key not in url_fields:
                            url_fields.append(key)
            elif isinstance(value, dict):
                for v in value.values():
                    if isinstance(v, str) and any(pattern in v.lower() for pattern in url_patterns):
                        if key not in url_fields:
                            url_fields.append(key)

print(f"\nTotal unique keys: {len(all_keys)}")
print(f"\nKey frequency (top 20):")
for key, count in key_counts.most_common(20):
    print(f"  - {key}: {count}/{len(items)} ({count*100/len(items):.1f}%)")

print(f"\nMissing/Empty values (top 20):")
for key, count in sorted(missing_values.items(), key=lambda x: x[1], reverse=True)[:20]:
    pct = count * 100 / len(items)
    print(f"  - {key}: {count}/{len(items)} ({pct:.1f}%)")

print(f"\nFields containing URLs: {url_fields}")

# Show a complete sample item
print(f"\n{'='*60}")
print("COMPLETE SAMPLE ITEM")
print(f"{'='*60}")
if items:
    sample = items[0]
    print(json.dumps(sample, indent=2, ensure_ascii=False)[:3000])  # First 3000 chars

