import json

with open('cleaned_specialchem_ingredients.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

total = len(data)
categorized = sum(1 for r in data if r.get('category_decided') in ['Active', 'Excipient'])
active = sum(1 for r in data if r.get('category_decided') == 'Active')
excipient = sum(1 for r in data if r.get('category_decided') == 'Excipient')

print(f"Total records: {total}")
print(f"Categorized: {categorized} ({categorized*100/total:.1f}%)")
print(f"Active: {active}")
print(f"Excipient: {excipient}")
print(f"Uncategorized: {total - categorized}")

# Check checkpoint
try:
    with open('categorization_checkpoint.json', 'r', encoding='utf-8') as f:
        checkpoint = json.load(f)
    print(f"\nCheckpoint found:")
    print(f"  Last processed index: {checkpoint.get('last_processed_index', 0)}")
    print(f"  Checkpoint says categorized: {checkpoint.get('categorized_count', 0)}")
except:
    print("\nNo checkpoint file found")

