#!/usr/bin/env python3
"""
Convert Formulynx Market Research Excel Workbook to Enhanced Taxonomy Format
This script reads the Excel workbook and converts it to structured taxonomy data
"""

import pandas as pd
import json
from pathlib import Path
from typing import Dict, List, Any

def convert_excel_to_taxonomy(file_path: str) -> Dict[str, Any]:
    """Convert Excel workbook to enhanced taxonomy format"""
    
    excel_file = pd.ExcelFile(file_path)
    sheet_names = excel_file.sheet_names
    
    taxonomy_data = {}
    
    print("Converting Excel workbook to taxonomy format...")
    
    # Convert Skin Concerns
    if "Skin Concerns" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Skin Concerns")
        skin_concerns = {}
        
        for _, row in df.iterrows():
            concern_id = str(row['ID']).strip().lower()
            
            # Parse related concerns (comma-separated)
            related_concerns = []
            if pd.notna(row.get('Related Concerns')):
                related_concerns = [c.strip() for c in str(row['Related Concerns']).split(',') if c.strip()]
            
            # Parse addressed by benefits (comma-separated)
            addressed_by_benefits = []
            if pd.notna(row.get('Addressed By Benefits')):
                addressed_by_benefits = [b.strip() for b in str(row['Addressed By Benefits']).split(',') if b.strip()]
            
            # Parse location variants
            location_variants = []
            if pd.notna(row.get('Location Variants')):
                location_variants = [l.strip() for l in str(row['Location Variants']).split(',') if l.strip()]
            
            # Parse search terms
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            skin_concerns[concern_id] = {
                "id": concern_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "is_parent": str(row['Is Parent']).strip().lower() == "yes" if pd.notna(row.get('Is Parent')) else False,
                "related_concerns": related_concerns,
                "addressed_by_benefits": addressed_by_benefits,
                "location_variants": location_variants,
                "search_terms": search_terms,
                "india_priority": str(row['India Priority']).strip().lower() if pd.notna(row.get('India Priority')) else None
            }
        
        taxonomy_data["skin_concerns"] = skin_concerns
        print(f"✓ Converted {len(skin_concerns)} skin concerns")
    
    # Convert Skin Benefits
    if "Skin Benefits" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Skin Benefits")
        skin_benefits = {}
        
        for _, row in df.iterrows():
            benefit_id = str(row['ID']).strip().lower()
            
            # Parse related benefits
            related_benefits = []
            if pd.notna(row.get('Related Benefits')):
                related_benefits = [b.strip() for b in str(row['Related Benefits']).split(',') if b.strip()]
            
            # Parse addresses concerns
            addresses_concerns = []
            if pd.notna(row.get('Addresses Concerns')):
                addresses_concerns = [c.strip() for c in str(row['Addresses Concerns']).split(',') if c.strip()]
            
            # Parse key ingredients
            key_ingredients = []
            if pd.notna(row.get('Key Ingredients')):
                key_ingredients = [i.strip() for i in str(row['Key Ingredients']).split(',') if i.strip()]
            
            # Parse search terms
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            skin_benefits[benefit_id] = {
                "id": benefit_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "is_parent": str(row['Is Parent']).strip().lower() == "yes" if pd.notna(row.get('Is Parent')) else False,
                "related_benefits": related_benefits,
                "addresses_concerns": addresses_concerns,
                "key_ingredients": key_ingredients,
                "search_terms": search_terms,
                "india_priority": str(row['India Priority']).strip().lower() if pd.notna(row.get('India Priority')) else None
            }
        
        taxonomy_data["skin_benefits"] = skin_benefits
        print(f"✓ Converted {len(skin_benefits)} skin benefits")
    
    # Convert Hair Concerns
    if "Hair Concerns" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Hair Concerns")
        hair_concerns = {}
        
        for _, row in df.iterrows():
            concern_id = str(row['ID']).strip().lower()
            
            related_concerns = []
            if pd.notna(row.get('Related Concerns')):
                related_concerns = [c.strip() for c in str(row['Related Concerns']).split(',') if c.strip()]
            
            addressed_by_benefits = []
            if pd.notna(row.get('Addressed By Benefits')):
                addressed_by_benefits = [b.strip() for b in str(row['Addressed By Benefits']).split(',') if b.strip()]
            
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            hair_concerns[concern_id] = {
                "id": concern_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "is_parent": str(row['Is Parent']).strip().lower() == "yes" if pd.notna(row.get('Is Parent')) else False,
                "related_concerns": related_concerns,
                "addressed_by_benefits": addressed_by_benefits,
                "search_terms": search_terms,
                "india_priority": str(row['India Priority']).strip().lower() if pd.notna(row.get('India Priority')) else None
            }
        
        taxonomy_data["hair_concerns"] = hair_concerns
        print(f"✓ Converted {len(hair_concerns)} hair concerns")
    
    # Convert Hair Benefits
    if "Hair Benefits" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Hair Benefits")
        hair_benefits = {}
        
        for _, row in df.iterrows():
            benefit_id = str(row['ID']).strip().lower()
            
            related_benefits = []
            if pd.notna(row.get('Related Benefits')):
                related_benefits = [b.strip() for b in str(row['Related Benefits']).split(',') if b.strip()]
            
            addresses_concerns = []
            if pd.notna(row.get('Addresses Concerns')):
                addresses_concerns = [c.strip() for c in str(row['Addresses Concerns']).split(',') if c.strip()]
            
            key_ingredients = []
            if pd.notna(row.get('Key Ingredients')):
                key_ingredients = [i.strip() for i in str(row['Key Ingredients']).split(',') if i.strip()]
            
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            hair_benefits[benefit_id] = {
                "id": benefit_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "is_parent": str(row['Is Parent']).strip().lower() == "yes" if pd.notna(row.get('Is Parent')) else False,
                "related_benefits": related_benefits,
                "addresses_concerns": addresses_concerns,
                "key_ingredients": key_ingredients,
                "search_terms": search_terms,
                "india_priority": str(row['India Priority']).strip().lower() if pd.notna(row.get('India Priority')) else None
            }
        
        taxonomy_data["hair_benefits"] = hair_benefits
        print(f"✓ Converted {len(hair_benefits)} hair benefits")
    
    # Convert Skin Product Types
    if "Skin Product Types" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Skin Product Types")
        skin_product_types = {}
        
        for _, row in df.iterrows():
            product_id = str(row['ID']).strip().lower()
            
            related_types = []
            if pd.notna(row.get('Related Types')):
                related_types = [t.strip() for t in str(row['Related Types']).split(',') if t.strip()]
            
            alternative_formats = []
            if pd.notna(row.get('Alternative Formats')):
                alternative_formats = [f.strip() for f in str(row['Alternative Formats']).split(',') if f.strip()]
            
            sub_types = []
            if pd.notna(row.get('Sub Types')):
                sub_types = [s.strip() for s in str(row['Sub Types']).split(',') if s.strip()]
            
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            skin_product_types[product_id] = {
                "id": product_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "related_types": related_types,
                "alternative_formats": alternative_formats,
                "sub_types": sub_types,
                "search_terms": search_terms
            }
        
        taxonomy_data["skin_product_types"] = skin_product_types
        print(f"✓ Converted {len(skin_product_types)} skin product types")
    
    # Convert Hair Product Types
    if "Hair Product Types" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Hair Product Types")
        hair_product_types = {}
        
        for _, row in df.iterrows():
            product_id = str(row['ID']).strip().lower()
            
            related_types = []
            if pd.notna(row.get('Related Types')):
                related_types = [t.strip() for t in str(row['Related Types']).split(',') if t.strip()]
            
            alternative_formats = []
            if pd.notna(row.get('Alternative Formats')):
                alternative_formats = [f.strip() for f in str(row['Alternative Formats']).split(',') if f.strip()]
            
            sub_types = []
            if pd.notna(row.get('Sub Types')):
                sub_types = [s.strip() for s in str(row['Sub Types']).split(',') if s.strip()]
            
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            hair_product_types[product_id] = {
                "id": product_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "related_types": related_types,
                "alternative_formats": alternative_formats,
                "sub_types": sub_types,
                "search_terms": search_terms
            }
        
        taxonomy_data["hair_product_types"] = hair_product_types
        print(f"✓ Converted {len(hair_product_types)} hair product types")
    
    # Convert Skin Ingredients
    if "Skin Ingredients" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Skin Ingredients")
        skin_ingredients = {}
        
        for _, row in df.iterrows():
            ingredient_id = str(row['ID']).strip().lower()
            
            related_ingredients = []
            if pd.notna(row.get('Related Ingredients')):
                related_ingredients = [i.strip() for i in str(row['Related Ingredients']).split(',') if i.strip()]
            
            benefits = []
            if pd.notna(row.get('Benefits')):
                benefits = [b.strip() for b in str(row['Benefits']).split(',') if b.strip()]
            
            concerns = []
            if pd.notna(row.get('Concerns')):
                concerns = [c.strip() for c in str(row['Concerns']).split(',') if c.strip()]
            
            inci_names = []
            if pd.notna(row.get('INCI Names')):
                inci_names = [i.strip() for i in str(row['INCI Names']).split(',') if i.strip()]
            
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            skin_ingredients[ingredient_id] = {
                "id": ingredient_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "parent": str(row['Parent']).strip().lower() if pd.notna(row.get('Parent')) else None,
                "related_ingredients": related_ingredients,
                "benefits": benefits,
                "concerns": concerns,
                "inci_names": inci_names,
                "search_terms": search_terms,
                "notes": str(row['Notes']).strip() if pd.notna(row.get('Notes')) else None
            }
        
        taxonomy_data["skin_ingredients"] = skin_ingredients
        print(f"✓ Converted {len(skin_ingredients)} skin ingredients")
    
    # Convert Hair Ingredients
    if "Hair Ingredients" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Hair Ingredients")
        hair_ingredients = {}
        
        for _, row in df.iterrows():
            ingredient_id = str(row['ID']).strip().lower()
            
            related_ingredients = []
            if pd.notna(row.get('Related Ingredients')):
                related_ingredients = [i.strip() for i in str(row['Related Ingredients']).split(',') if i.strip()]
            
            benefits = []
            if pd.notna(row.get('Benefits')):
                benefits = [b.strip() for b in str(row['Benefits']).split(',') if b.strip()]
            
            concerns = []
            if pd.notna(row.get('Concerns')):
                concerns = [c.strip() for c in str(row['Concerns']).split(',') if c.strip()]
            
            inci_names = []
            if pd.notna(row.get('INCI Names')):
                inci_names = [i.strip() for i in str(row['INCI Names']).split(',') if i.strip()]
            
            search_terms = []
            if pd.notna(row.get('Search Terms')):
                search_terms = [s.strip() for s in str(row['Search Terms']).split(',') if s.strip()]
            
            hair_ingredients[ingredient_id] = {
                "id": ingredient_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "category": str(row['Category']).strip().lower() if pd.notna(row.get('Category')) else "",
                "related_ingredients": related_ingredients,
                "benefits": benefits,
                "concerns": concerns,
                "inci_names": inci_names,
                "search_terms": search_terms,
                "india_priority": str(row['India Priority']).strip().lower() if pd.notna(row.get('India Priority')) else None,
                "notes": str(row['Notes']).strip() if pd.notna(row.get('Notes')) else None
            }
        
        taxonomy_data["hair_ingredients"] = hair_ingredients
        print(f"✓ Converted {len(hair_ingredients)} hair ingredients")
    
    # Convert Price Tiers
    if "Price Tiers" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Price Tiers")
        price_tiers = {}
        
        for _, row in df.iterrows():
            tier_id = str(row['ID']).strip().lower()
            
            min_price = None
            if pd.notna(row.get('Min Price (₹)')):
                try:
                    min_price = int(row['Min Price (₹)'])
                except (ValueError, TypeError):
                    min_price = None
            
            max_price = None
            if pd.notna(row.get('Max Price (₹)')):
                try:
                    max_price = int(row['Max Price (₹)'])
                except (ValueError, TypeError):
                    max_price = None
            
            price_tiers[tier_id] = {
                "id": tier_id,
                "label": str(row['Label']).strip(),
                "icon": str(row['Icon']).strip() if pd.notna(row.get('Icon')) else "",
                "color": str(row['Color']).strip() if pd.notna(row.get('Color')) else "",
                "min_price": min_price,
                "max_price": max_price,
                "display": str(row['Display']).strip() if pd.notna(row.get('Display')) else "",
                "typical_channels": str(row['Typical Channels']).strip() if pd.notna(row.get('Typical Channels')) else "",
                "typical_brands": str(row['Typical Brands']).strip() if pd.notna(row.get('Typical Brands')) else "",
                "research_notes": str(row['Research Notes']).strip() if pd.notna(row.get('Research Notes')) else ""
            }
        
        taxonomy_data["price_tiers"] = price_tiers
        print(f"✓ Converted {len(price_tiers)} price tiers")
    
    # Convert Market Positioning
    if "Market Positioning" in sheet_names:
        df = pd.read_excel(file_path, sheet_name="Market Positioning")
        market_positioning = {}
        
        for _, row in df.iterrows():
            positioning_id = str(row['ID']).strip().lower()
            
            market_positioning[positioning_id] = {
                "id": positioning_id,
                "label": str(row['Label']).strip(),
                "description": str(row['Description']).strip() if pd.notna(row.get('Description')) else "",
                "common_claims": str(row['Common Claims']).strip() if pd.notna(row.get('Common Claims')) else "",
                "target_consumer": str(row['Target Consumer']).strip() if pd.notna(row.get('Target Consumer')) else "",
                "example_brands": str(row['Example Brands']).strip() if pd.notna(row.get('Example Brands')) else ""
            }
        
        taxonomy_data["market_positioning"] = market_positioning
        print(f"✓ Converted {len(market_positioning)} market positioning types")
    
    return taxonomy_data

if __name__ == "__main__":
    excel_file = Path("formulynx_market_research_taxonomy (2).xlsx")
    
    if not excel_file.exists():
        print(f"Error: Excel file not found at {excel_file}")
        exit(1)
    
    # Convert Excel to taxonomy format
    taxonomy_data = convert_excel_to_taxonomy(str(excel_file))
    
    # Save to JSON file
    output_file = "enhanced_formulynx_taxonomy.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(taxonomy_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Conversion complete!")
    print(f"📄 Enhanced taxonomy saved to: {output_file}")
    print(f"📊 Summary:")
    for category, data in taxonomy_data.items():
        print(f"  - {category}: {len(data)} items")
