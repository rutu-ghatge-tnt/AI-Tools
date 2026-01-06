"""
Product Comparison API Endpoint
================================

API endpoint for comparing multiple cosmetic products.
Extracted from analyze_inci.py for better modularity.
"""

import time
import os
import json
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
from app.ai_ingredient_intelligence.db.collections import compare_history_col
from app.ai_ingredient_intelligence.models.schemas import (
    CompareProductsResponse,
    ProductComparisonItem
)

router = APIRouter(tags=["Product Comparison"])


@router.post("/compare-products", response_model=CompareProductsResponse)
async def compare_products(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Compare multiple products based on URLs or INCI strings.
    
    Request body:
    {
        "products": [
            {"input": "https://example.com/product1", "input_type": "url"},
            {"input": "Water, Glycerin, ...", "input_type": "inci"},
            ...
        ]
    }
    
    The endpoint will:
    1. If URL: Scrape the URL to extract product data
    2. If INCI: Use the INCI string directly
    3. Send all products to Claude for structured comparison
    4. Return comparison data with INCI, benefits, claims, price, and attributes
    
    Response:
    {
        "products": [ProductComparisonItem, ...],
        "processing_time": float
    }
    """
    start = time.time()
    scraper = None
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = payload.get("name", "").strip() if payload.get("name") else ""  # Required: custom name for history
    tag = payload.get("tag")  # Optional: tag for history
    notes = payload.get("notes")  # Optional: notes for history
    provided_history_id = payload.get("history_id")  # Optional: reuse existing history item
    history_id = None
    
    # Validate name is provided if auto-save is enabled (user_id is present)
    if user_id_value and not provided_history_id and not name:
        raise HTTPException(status_code=400, detail="name is required for auto-save")
    
    # Validate history_id if provided
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await compare_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_item:
                    history_id = provided_history_id
                    print(f"[AUTO-SAVE] Using existing history_id: {history_id}")
                else:
                    print(f"[AUTO-SAVE] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, creating new one")
            else:
                print(f"[AUTO-SAVE] Warning: Invalid history_id format: {provided_history_id}, creating new one")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Error validating history_id: {e}, creating new one")
    
    try:
        # Parse products from payload
        if "products" not in payload or not payload["products"]:
            raise HTTPException(status_code=400, detail="Missing required field: 'products' array")
        
        products_list = payload["products"]
        if not isinstance(products_list, list):
            raise HTTPException(status_code=400, detail="products must be an array")
        if len(products_list) < 2:
            raise HTTPException(status_code=400, detail="At least 2 products are required for comparison")
        
        # Validate all products
        for i, product in enumerate(products_list):
            if "input" not in product or "input_type" not in product:
                raise HTTPException(status_code=400, detail=f"Product {i+1} is missing 'input' or 'input_type' field")
            product["input_type"] = product["input_type"].lower()
            if product["input_type"] not in ["url", "inci"]:
                raise HTTPException(status_code=400, detail=f"Product {i+1} input_type must be 'url' or 'inci'")
        
        # Initialize scraper if any product is a URL
        needs_scraper = any(p["input_type"] == "url" for p in products_list)
        if needs_scraper:
            scraper = URLScraper()
        
        # Helper function to process a single product
        async def process_single_product(idx: int, product: dict, scraper_instance: Optional[URLScraper] = None) -> dict:
            """Process a single product (URL or INCI) - can run in parallel"""
            product_input = product["input"]
            product_type = product["input_type"]
            product_num = idx + 1
            
            print(f"Processing product {product_num} (type: {product_type})...")
            
            # Use provided scraper or create a new one for this product
            product_scraper = scraper_instance if scraper_instance else URLScraper()
            
            product_data = {
                "url_context": None,
                "text": "",
                "inci": [],
                "product_name": None
            }
            
            if product_type == "url":
                if not product_input.startswith(("http://", "https://")):
                    raise HTTPException(status_code=400, detail=f"Product {product_num} must be a valid URL when input_type is 'url'")
                product_data["url_context"] = product_input  # Store URL for Claude
                extraction_result = await product_scraper.extract_ingredients_from_url(product_input)
                product_data["text"] = extraction_result.get("extracted_text", "")
                product_data["inci"] = extraction_result.get("ingredients", [])
                product_data["product_name"] = extraction_result.get("product_name")
                # Try to detect product name from text if not already extracted
                if not product_data["product_name"] and product_data["text"]:
                    try:
                        product_data["product_name"] = await product_scraper.detect_product_name(product_data["text"], product_input)
                    except:
                        pass
            else:
                # INCI input - validate it's a list
                if not isinstance(product_input, list):
                    raise HTTPException(status_code=400, detail=f"Product {product_num} input must be an array of strings when input_type is 'inci'")
                
                if not product_input:
                    raise HTTPException(status_code=400, detail=f"Product {product_num} INCI list cannot be empty")
                
                # Parse INCI list (handles list of strings, each may contain separators)
                product_data["text"] = ", ".join(product_input)  # Join for display
                product_data["inci"] = parse_inci_string(product_input)
                
                # Use Claude to clean and validate INCI list if we have a scraper
                if product_scraper and product_data["inci"]:
                    try:
                        # Join for Claude text extraction
                        inci_text = ", ".join(product_input)
                        cleaned_inci = await product_scraper.extract_ingredients_from_text(inci_text)
                        if cleaned_inci:
                            product_data["inci"] = cleaned_inci
                    except:
                        pass  # Fall back to parsed list
                product_data["product_name"] = None
            
            # Clean up scraper if we created a new one
            if product_scraper != scraper_instance and product_scraper:
                try:
                    await product_scraper.close()
                except:
                    pass
            
            return product_data
        
        # Process all products in parallel for better performance
        print(f"Processing {len(products_list)} products in parallel...")
        # Create tasks for parallel processing
        tasks = [
            process_single_product(idx, product, scraper if needs_scraper else None)
            for idx, product in enumerate(products_list)
        ]
        # Wait for all products to be processed
        processed_products = await asyncio.gather(*tasks)
        
        # If scraper wasn't initialized but we need Claude for comparison
        if not scraper:
            scraper = URLScraper()
        
        # Prepare data for Claude comparison
        claude_client = scraper._get_claude_client() if scraper else None
        if not claude_client:
            claude_key = os.getenv("CLAUDE_API_KEY")
            if not claude_key:
                raise HTTPException(status_code=500, detail="CLAUDE_API_KEY environment variable is not set")
            from anthropic import Anthropic
            claude_client = Anthropic(api_key=claude_key)
        
        # Create comparison prompt for Claude
        model_name = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"
        
        # Prepare full text for better extraction (use more context to capture price, ratings, etc.)
        for idx, product_data in enumerate(processed_products):
            product_data["text_full"] = product_data["text"][:10000] if len(product_data["text"]) > 10000 else product_data["text"]
            print(f"Product {idx+1} extracted text length: {len(product_data['text'])} chars")
            print(f"Product {idx+1} text preview (first 500 chars): {product_data['text'][:500]}")
            if product_data["url_context"]:
                print(f"Product {idx+1} URL: {product_data['url_context']}")
        
        # Build product data sections for prompt
        product_sections = []
        for idx, product_data in enumerate(processed_products):
            product_num = idx + 1
            url_info = f"\n- Source URL: {product_data['url_context']}" if product_data["url_context"] else "\n- Source: INCI text input (no URL)"
            product_sections.append(f"""Product {product_num} Data:
- Product Name (if known): {product_data['product_name'] or 'Not specified'}{url_info}
- INCI Ingredients: {', '.join(product_data['inci']) if product_data['inci'] else 'Not available'}
- Full Extracted Text:
{product_data['text_full']}""")
        
        products_section = "\n\n".join(product_sections)
        
        # Build JSON structure for response
        products_json_structure = ",\n".join([f'''  "product{i+1}": {{
    "product_name": "extract the full product name from text, or null if not found",
    "brand_name": "extract the brand/manufacturer name from text, or null if not found",
    "inci": ["list", "of", "all", "ingredients"],
    "benefits": ["list", "of", "all", "benefits", "mentioned"],
    "claims": ["list", "of", "all", "claims", "mentioned"],
    "price": "extract price in format like '₹999' or '$29.99' or 'INR 1,299', or null if not found",
    "cruelty_free": true/false/null,
    "sulphate_free": true/false/null,
    "paraben_free": true/false/null,
    "vegan": true/false/null,
    "organic": true/false/null,
    "fragrance_free": true/false/null,
    "non_comedogenic": true/false/null,
    "hypoallergenic": true/false/null
  }}''' for i in range(len(processed_products))])
        
        comparison_prompt = f"""You are an expert cosmetic product analyst. Compare {len(processed_products)} cosmetic products and provide a structured comparison.

IMPORTANT: If a URL is provided, use it as context to verify and extract information. The URL may contain additional product details like price, ratings, and specifications that might not be fully captured in the scraped text.

{products_section}

Please analyze all {len(processed_products)} products CAREFULLY and extract ALL available information from the extracted text. Return a JSON object with the following structure:
{{
{products_json_structure}
}}

CRITICAL INSTRUCTIONS:
1. PRODUCT NAME: Look for product titles, headings, or product names in the extracted text. Extract the complete product name (e.g., "Vitamin C Brightening Serum" not just "Serum"). If URL is provided, the product name might be in the URL path or page title.
2. BRAND NAME: Look for brand names, manufacturer names, or company names. This is usually mentioned before the product name or in the beginning of the text. Common patterns: "Bobbi Brown", "The Ordinary", "CeraVe", etc.
3. PRICE: This is CRITICAL - Search EXTENSIVELY for price information in the extracted text. Look for:
   - Formats: ₹999, $29.99, INR 1,299, Rs. 599, ₹7,500, etc.
   - Keywords: "Price:", "₹", "$", "INR", "Rs.", "MRP", "Cost"
   - Price sections, pricing tables, or highlighted price displays
   - If URL is provided (especially e-commerce sites like Nykaa, Amazon, Flipkart), price is almost always visible on the page
   - Extract the exact price with currency symbol as shown
4. RATINGS: If available, extract ratings information (e.g., "4.5/5", "4.5 stars", "4322 ratings")
5. INCI: Use the provided INCI list if available, otherwise extract from text. Ensure all ingredients are included. Look for ingredient lists, "Ingredients:" sections, or INCI declarations.
6. BENEFITS: Extract all mentioned benefits (e.g., "brightens skin", "reduces wrinkles", "hydrates", "boosts glow")
7. CLAIMS: Extract all marketing claims (e.g., "100% plant-based", "dermatologically tested", "suitable for sensitive skin", "primer & moisturizer")
8. BOOLEAN ATTRIBUTES: This is CRITICAL - Determine these attributes carefully:
   - SULPHATE_FREE: 
     * Set to FALSE if ingredients contain: Sodium Lauryl Sulfate, Sodium Laureth Sulfate, Ammonium Lauryl Sulfate, SLES, SLS, or any "sulfate"/"sulphate"
     * Set to TRUE if text explicitly states "sulphate-free", "sulfate-free", or "sulphate free"
     * Set to NULL only if you cannot determine from ingredients or text
   - PARABEN_FREE:
     * Set to FALSE if ingredients contain: Methylparaben, Ethylparaben, Propylparaben, Butylparaben, Isobutylparaben, Benzylparaben, or any "paraben"
     * Set to TRUE if text explicitly states "paraben-free" or "paraben free"
     * Set to NULL only if you cannot determine from ingredients or text
   - FRAGRANCE_FREE:
     * Set to FALSE if ingredients contain: Parfum, Fragrance, Aroma, Perfume
     * Set to TRUE if text explicitly states "fragrance-free", "fragrance free", or "unscented"
     * Set to NULL only if you cannot determine from ingredients or text
   - OTHER ATTRIBUTES (cruelty_free, vegan, organic, non_comedogenic, hypoallergenic):
     * Determine from explicit claims in text (e.g., "cruelty-free", "vegan", "organic")
     * Look for certifications, labels, or product descriptions
     * Set to NULL only if truly not available
   - IMPORTANT: Always check the INCI ingredients list provided above - if it contains the ingredient, set the corresponding attribute to FALSE
   - IMPORTANT: If the text explicitly claims "X-free", set it to TRUE even if you don't see the ingredient
9. URL CONTEXT: If a URL is provided, use it to understand the source (e.g., nykaa.com, amazon.in, flipkart.com) and extract information accordingly. E-commerce sites typically have price, ratings, and detailed product information prominently displayed.
10. Use null ONLY if information is truly not available after thorough search
11. Return ONLY valid JSON, no additional text or explanations

Return the JSON comparison:"""

        print("Sending comparison request to Claude...")
        # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
        max_tokens = 4096 if "claude-3-opus-20240229" in model_name else 8192
        
        # Run synchronous Claude API call in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: claude_client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=0.1,
                messages=[{"role": "user", "content": comparison_prompt}]
            )
        )
        
        # Extract response content
        claude_response = response.content[0].text.strip()
        
        # Parse JSON response
        try:
            # Clean the response to extract JSON
            if '{' in claude_response and '}' in claude_response:
                json_start = claude_response.find('{')
                json_end = claude_response.rfind('}') + 1
                json_str = claude_response[json_start:json_end]
                comparison_data = json.loads(json_str)
            else:
                raise Exception("No JSON found in Claude response")
        except json.JSONDecodeError as e:
            print(f"Failed to parse Claude response: {e}")
            print(f"Response: {claude_response[:500]}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse comparison response from AI: {str(e)}"
            )
        
        # Extract product data from Claude response
        all_products_data = []
        for idx in range(len(processed_products)):
            product_key = f"product{idx+1}"
            if product_key in comparison_data:
                all_products_data.append(comparison_data[product_key])
            else:
                # Fallback: create empty product data
                all_products_data.append({})
        
        # Helper function to determine boolean attributes from INCI list
        def determine_attributes_from_inci(inci_list: List[str], text: str = "") -> Dict[str, Optional[bool]]:
            """Determine boolean attributes from INCI ingredients and text"""
            attributes = {}
            inci_lower = [ing.lower() for ing in inci_list]
            text_lower = text.lower()
            all_text = " ".join(inci_lower) + " " + text_lower
            
            # Sulphate free detection
            sulphate_keywords = [
                "sodium lauryl sulfate", "sodium laureth sulfate", "ammonium lauryl sulfate",
                "ammonium laureth sulfate", "sodium lauryl sulfoacetate", "sles", "sls",
                "sulfate", "sulphate"
            ]
            has_sulphate = any(keyword in all_text for keyword in sulphate_keywords)
            # Check for explicit "sulphate-free" or "sulfate-free" claims
            has_sulphate_free_claim = "sulphate-free" in all_text or "sulfate-free" in all_text or "sulphate free" in all_text or "sulfate free" in all_text
            if has_sulphate_free_claim:
                attributes["sulphate_free"] = True
            elif has_sulphate:
                attributes["sulphate_free"] = False
            else:
                attributes["sulphate_free"] = None
            
            # Paraben free detection
            paraben_keywords = [
                "methylparaben", "ethylparaben", "propylparaben", "butylparaben",
                "isobutylparaben", "benzylparaben", "paraben"
            ]
            has_paraben = any(keyword in all_text for keyword in paraben_keywords)
            # Check for explicit "paraben-free" claims
            has_paraben_free_claim = "paraben-free" in all_text or "paraben free" in all_text
            if has_paraben_free_claim:
                attributes["paraben_free"] = True
            elif has_paraben:
                attributes["paraben_free"] = False
            else:
                attributes["paraben_free"] = None
            
            # Fragrance free detection
            fragrance_keywords = ["parfum", "fragrance", "aroma", "perfume"]
            has_fragrance = any(keyword in all_text for keyword in fragrance_keywords)
            has_fragrance_free_claim = "fragrance-free" in all_text or "fragrance free" in all_text or "unscented" in all_text
            if has_fragrance_free_claim:
                attributes["fragrance_free"] = True
            elif has_fragrance:
                attributes["fragrance_free"] = False
            else:
                attributes["fragrance_free"] = None
            
            return attributes
        
        # Build response with extracted text for all products
        final_products_data = []
        all_attrs = []
        
        for idx, product_data in enumerate(processed_products):
            claude_product_data = all_products_data[idx] if idx < len(all_products_data) else {}
            
            # Merge with actual INCI if we extracted it (prefer our extraction if available)
            final_inci = claude_product_data.get("inci", []) if claude_product_data.get("inci") else product_data["inci"]
            claude_product_data["inci"] = final_inci
            
            # Add extracted text
            claude_product_data["extracted_text"] = product_data["text"]
            
            # Add selected_method (input_type) and url from original request
            original_product = products_list[idx]
            claude_product_data["selected_method"] = original_product.get("input_type", "inci")
            claude_product_data["url"] = product_data.get("url_context") if original_product.get("input_type") == "url" else None
            
            # Fallback: Determine boolean attributes from INCI if Claude didn't extract them
            attrs = determine_attributes_from_inci(final_inci, product_data["text"])
            all_attrs.append(attrs)
            
            # Update attributes only if they're null in Claude's response
            for attr in ["sulphate_free", "paraben_free", "fragrance_free"]:
                if claude_product_data.get(attr) is None and attrs.get(attr) is not None:
                    claude_product_data[attr] = attrs[attr]
                    print(f"Fallback: Set product{idx+1}.{attr} = {attrs[attr]} from INCI analysis")
            
            final_products_data.append(claude_product_data)
        
        # SECOND PASS: Fill missing fields using deep analysis
        print("\n=== SECOND PASS: Filling Missing Fields ===")
        
        def identify_missing_fields(product_data: Dict, product_num: int) -> List[str]:
            """Identify which fields are null or empty"""
            missing = []
            required_fields = {
                "product_name": product_data.get("product_name"),
                "brand_name": product_data.get("brand_name"),
                "price": product_data.get("price"),
                "benefits": product_data.get("benefits", []),
                "claims": product_data.get("claims", []),
                "cruelty_free": product_data.get("cruelty_free"),
                "sulphate_free": product_data.get("sulphate_free"),
                "paraben_free": product_data.get("paraben_free"),
                "vegan": product_data.get("vegan"),
                "organic": product_data.get("organic"),
                "fragrance_free": product_data.get("fragrance_free"),
                "non_comedogenic": product_data.get("non_comedogenic"),
                "hypoallergenic": product_data.get("hypoallergenic"),
            }
            
            for field, value in required_fields.items():
                if value is None or (isinstance(value, list) and len(value) == 0):
                    missing.append(field)
            
            if missing:
                print(f"Product {product_num} missing fields: {', '.join(missing)}")
            return missing
        
        # Helper function to fill missing fields for a single product
        async def fill_missing_fields_for_product(idx: int, product_data: Dict, current_product: Dict, claude_client_instance, model_name: str) -> Dict:
            """Fill missing fields for a single product - can run in parallel"""
            product_num = idx + 1
            missing_fields = identify_missing_fields(product_data, product_num)
            
            if not missing_fields:
                return product_data
            
            print(f"Attempting to fill {len(missing_fields)} missing fields for Product {product_num}...")
            fill_prompt = f"""You are an expert cosmetic product researcher. Use your knowledge base, web search capabilities, and deep analysis to find missing information about this product.

Product Information:
- Product Name: {product_data.get('product_name') or 'Unknown'}
- Brand Name: {product_data.get('brand_name') or 'Unknown'}
- INCI Ingredients: {', '.join(product_data.get('inci', [])) if product_data.get('inci') else 'Not available'}
- Current Extracted Text: {current_product['text'][:5000] if current_product['text'] else 'Not available'}
- Source URL: {current_product['url_context'] or 'Not provided'}
- Current Benefits: {', '.join(product_data.get('benefits', [])) or 'None'}
- Current Claims: {', '.join(product_data.get('claims', [])) or 'None'}

MISSING FIELDS TO FILL:
{', '.join(missing_fields)}

INSTRUCTIONS:
1. Use your knowledge base and reasoning to find information about this specific product
2. If a URL is provided, use it to understand the product context
3. For PRODUCT_NAME: If currently null, try to infer from brand name, INCI list, or URL
4. For BRAND_NAME: If currently null, try to extract from product name, URL, or text
5. For PRICE: Search for current market price. If not findable, use "Price not available" (not null)
6. For BENEFITS: If empty, infer from INCI ingredients (e.g., hyaluronic acid = hydration, vitamin C = brightening)
7. For CLAIMS: If empty, infer common claims based on ingredients and product type
8. For BOOLEAN ATTRIBUTES (cruelty_free, vegan, organic, etc.):
   - Use ingredient analysis: Check INCI list for indicators
   - Use brand knowledge: Many brands have known policies (e.g., The Ordinary = cruelty-free)
   - Use product type inference: Organic products often indicate organic status
   - If truly cannot determine, use reasonable defaults based on product category
   - NEVER return null - always provide true or false based on best available information

Return ONLY a JSON object with the missing fields filled. Use this exact structure:
{{
  "product_name": "value or keep existing if not missing",
  "brand_name": "value or keep existing if not missing",
  "price": "value or 'Price not available' if not findable",
  "benefits": ["list", "of", "benefits"],
  "claims": ["list", "of", "claims"],
  "cruelty_free": true/false,
  "sulphate_free": true/false,
  "paraben_free": true/false,
  "vegan": true/false,
  "organic": true/false,
  "fragrance_free": true/false,
  "non_comedogenic": true/false,
  "hypoallergenic": true/false
}}

IMPORTANT: Only include fields that were in the MISSING FIELDS list above. For fields not in the missing list, you can omit them or use the existing values.
CRITICAL: NEVER use null. Always provide a value (even if it's "Unknown" for text fields or false for booleans when uncertain).
"""
            
            try:
                # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
                max_tokens = 4096 if "claude-3-opus-20240229" in model_name else 8192
                
                # Run synchronous Claude API call in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                fill_response = await loop.run_in_executor(
                    None,
                    lambda: claude_client_instance.messages.create(
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=0.2,
                        messages=[{"role": "user", "content": fill_prompt}]
                    )
                )
                
                fill_content = fill_response.content[0].text.strip()
                if '{' in fill_content and '}' in fill_content:
                    json_start = fill_content.find('{')
                    json_end = fill_content.rfind('}') + 1
                    json_str = fill_content[json_start:json_end]
                    fill_data = json.loads(json_str)
                    
                    # Merge filled fields into product_data
                    for field in missing_fields:
                        if field in fill_data and fill_data[field] is not None:
                            # Handle list fields
                            if field in ["benefits", "claims"]:
                                if isinstance(fill_data[field], list) and len(fill_data[field]) > 0:
                                    product_data[field] = fill_data[field]
                                    print(f"✓ Filled product{product_num}.{field} with {len(fill_data[field])} items")
                            # Handle boolean fields - never allow null
                            elif field in ["cruelty_free", "sulphate_free", "paraben_free", "vegan", "organic", "fragrance_free", "non_comedogenic", "hypoallergenic"]:
                                if fill_data[field] is not None:
                                    product_data[field] = fill_data[field]
                                    print(f"✓ Filled product{product_num}.{field} = {fill_data[field]}")
                            # Handle string fields
                            else:
                                if fill_data[field] and fill_data[field] != "null":
                                    product_data[field] = fill_data[field]
                                    print(f"✓ Filled product{product_num}.{field} = {fill_data[field]}")
            except Exception as e:
                print(f"Warning: Failed to fill missing fields for Product {product_num}: {e}")
            
            return product_data
        
        # Fill missing fields for all products in parallel
        print(f"Filling missing fields for {len(final_products_data)} products in parallel...")
        fill_tasks = [
            fill_missing_fields_for_product(idx, product_data, processed_products[idx], claude_client, model_name)
            for idx, product_data in enumerate(final_products_data)
        ]
        # Wait for all fill operations to complete
        final_products_data = await asyncio.gather(*fill_tasks)
        
        # Final pass: Ensure no null values remain
        print("\n=== FINAL PASS: Ensuring No Null Values ===")
        
        def ensure_no_nulls(product_data: Dict, product_num: int, attrs_dict: Dict):
            """Final check to ensure no null values remain"""
            # Ensure string fields have values
            if not product_data.get("product_name"):
                product_data["product_name"] = "Product name not available"
            if not product_data.get("brand_name"):
                product_data["brand_name"] = "Brand name not available"
            if not product_data.get("price"):
                product_data["price"] = "Price not available"
            
            # Ensure list fields have values
            if not product_data.get("benefits") or len(product_data.get("benefits", [])) == 0:
                product_data["benefits"] = ["Benefits information not available"]
            if not product_data.get("claims") or len(product_data.get("claims", [])) == 0:
                product_data["claims"] = ["Claims information not available"]
            
            # Ensure boolean fields have values (never null)
            boolean_fields = ["cruelty_free", "sulphate_free", "paraben_free", "vegan", "organic", "fragrance_free", "non_comedogenic", "hypoallergenic"]
            for field in boolean_fields:
                if product_data.get(field) is None:
                    # Use INCI analysis as final fallback
                    if field in attrs_dict and attrs_dict[field] is not None:
                        product_data[field] = attrs_dict[field]
                    else:
                        product_data[field] = False  # Default to False if truly unknown
                    print(f"✓ Final fallback: Set product{product_num}.{field} = {product_data[field]}")
        
        # Final pass: Ensure no null values remain for all products
        for idx, product_data in enumerate(final_products_data):
            ensure_no_nulls(product_data, idx + 1, all_attrs[idx])
        
        # Calculate processing time
        processing_time = time.time() - start
        
        # 🔹 Auto-save: Create or update history before processing completes
        if user_id_value and not history_id:
            try:
                # Build products array for history
                products_array = []
                for product in products_list:
                    products_array.append({
                        "input": product.get("input", ""),
                        "input_type": product.get("input_type", "inci")
                    })
                
                # Check if there's an existing history item with same products
                existing_history = await compare_history_col.find_one({
                    "user_id": user_id_value,
                    "products": products_array
                })
                
                if existing_history:
                    history_id = str(existing_history["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same products, reusing history_id: {history_id}")
                    
                    # Reset status to in_progress
                    await compare_history_col.update_one(
                        {"_id": ObjectId(history_id)},
                        {"$set": {
                            "status": "in_progress",
                            "name": name,
                            "tag": tag,
                            "notes": notes or ""
                        }}
                    )
                    print(f"[AUTO-SAVE] Reset existing history item {history_id} status to 'in_progress'")
                else:
                    # Create new history document with "in_progress" status
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
                        "tag": tag,
                        "notes": notes or "",
                        "products": products_array,
                        "status": "in_progress",
                        "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                    }
                    
                    result = await compare_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                # Continue without history_id
        
        # Convert to ProductComparisonItem objects
        product_items = [ProductComparisonItem(**product_data) for product_data in final_products_data]
        
        # Build response with history_id included
        response_data = {
            "products": product_items,
            "processing_time": processing_time,
            "id": history_id if history_id else None
        }
        
        response = CompareProductsResponse(**response_data)
        
        # 🔹 Auto-save: Update history with "completed" status and comparison_result
        if history_id and user_id_value:
            try:
                # Convert response to dict for storage
                comparison_result_dict = response.dict(exclude_none=True) if hasattr(response, "dict") else response.model_dump(exclude_none=True)
                
                update_doc = {
                    "status": "completed",
                    "comparison_result": comparison_result_dict,
                    "processing_time": processing_time
                }
                
                await compare_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with completed status")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error comparing products: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compare products: {str(e)}"
        )
    finally:
        # Clean up scraper
        if scraper:
            try:
                await scraper.close()
            except:
                pass

