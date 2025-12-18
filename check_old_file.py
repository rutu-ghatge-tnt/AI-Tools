import json
import os

old_file = 'output_specialChem_1765800534743.json'
if os.path.exists(old_file):
    with open(old_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    categorized = sum(1 for r in data if r.get('category_decided') in ['Active', 'Excipient'])
    active = sum(1 for r in data if r.get('category_decided') == 'Active')
    excipient = sum(1 for r in data if r.get('category_decided') == 'Excipient')
    
    print(f"OLD FILE ({old_file}):")
    print(f"Total records: {total}")
    print(f"Categorized: {categorized} ({categorized*100/total:.1f}%)")
    print(f"Active: {active}")
    print(f"Excipient: {excipient}")
else:
    print("Old file not found")

