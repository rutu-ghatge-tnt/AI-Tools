"""
Quick script to check enhancement status in cleaned data or checkpoint
"""
import json
import os
import sys

def check_file(filename):
    """Check enhancement status in a JSON file"""
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return
    
    print(f"\n📊 Checking: {filename}")
    print("=" * 60)
    
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    enhanced = sum(1 for r in data if r.get("enhanced_description"))
    has_category = sum(1 for r in data if r.get("category_decided"))
    has_inci_filled = sum(1 for r in data if len(r.get("inci_names", [])) > 0)
    has_compliance = sum(1 for r in data if r.get("extra_data", {}).get("compliance"))
    has_applications = sum(1 for r in data if r.get("extra_data", {}).get("applications"))
    has_properties = sum(1 for r in data if r.get("extra_data", {}).get("properties"))
    
    print(f"📁 Total records: {total}")
    print(f"✅ Enhanced descriptions: {enhanced} ({enhanced*100/total:.1f}%)")
    print(f"✅ Category decided: {has_category} ({has_category*100/total:.1f}%)")
    print(f"✅ Has INCI names: {has_inci_filled} ({has_inci_filled*100/total:.1f}%)")
    print(f"✅ Has compliance: {has_compliance} ({has_compliance*100/total:.1f}%)")
    print(f"✅ Has applications: {has_applications} ({has_applications*100/total:.1f}%)")
    print(f"✅ Has properties: {has_properties} ({has_properties*100/total:.1f}%)")
    
    # Show sample enhanced records
    print(f"\n📝 Sample Enhanced Records:")
    count = 0
    for record in data:
        if record.get("enhanced_description") and count < 5:
            name = record.get("ingredient_name", "Unknown")
            category = record.get("category_decided", "N/A")
            desc = record.get("enhanced_description", "")[:100]
            print(f"\n   {count + 1}. {name}")
            print(f"      Category: {category}")
            print(f"      Description: {desc}...")
            count += 1
    
    if enhanced == 0:
        print(f"\n⚠️  WARNING: No enhanced descriptions found!")
        print(f"   This could mean:")
        print(f"   - Enhancement hasn't started yet")
        print(f"   - OpenAI API key is missing")
        print(f"   - Enhancement failed for all records")

if __name__ == "__main__":
    # Check output file
    if os.path.exists("cleaned_specialchem_ingredients.json"):
        check_file("cleaned_specialchem_ingredients.json")
    
    # Check checkpoint file
    if os.path.exists("cleaning_checkpoint.json"):
        print("\n" + "=" * 60)
        print("📋 CHECKPOINT FILE STATUS")
        print("=" * 60)
        with open("cleaning_checkpoint.json", 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)
        
        total = checkpoint.get("total_records", 0)
        processed = checkpoint.get("last_processed_index", 0)
        cleaned = len(checkpoint.get("cleaned_data", []))
        enhanced = checkpoint.get("enhanced_count", 0)
        enhancement_start = checkpoint.get("enhancement_start_index", 0)
        
        print(f"📊 Progress: {processed}/{total} records processed ({processed*100/total:.1f}%)")
        print(f"✅ Cleaned: {cleaned} records")
        print(f"🤖 Enhanced: {enhanced} descriptions")
        print(f"⏭️  Enhancement starting from: {enhancement_start}")
        
        if cleaned > 0:
            print(f"\n💡 Enhancement status: {'In progress' if enhancement_start < cleaned else 'Not started yet'}")
            if enhanced > 0:
                print(f"   ✅ Enhancement is working! {enhanced} descriptions enhanced so far")
            else:
                print(f"   ⏳ Enhancement hasn't started or is at the beginning")

