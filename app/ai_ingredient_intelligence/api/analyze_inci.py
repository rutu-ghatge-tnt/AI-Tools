# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException, Form, Request, Header
from fastapi.responses import Response
import time
import os
import json
import re
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.logic.bis_rag import (
    get_bis_cautions_for_ingredients,
    initialize_bis_vectorstore,
    get_bis_retriever,
    check_bis_rag_health,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
from app.ai_ingredient_intelligence.logic.cas_api import get_synonyms_batch, get_synonyms_for_ingredient

# Claude AI setup for intelligent matching
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

claude_api_key = os.getenv("CLAUDE_API_KEY")
claude_model = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"

if ANTHROPIC_AVAILABLE and claude_api_key:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        claude_client = None
else:
    claude_client = None
from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
from app.ai_ingredient_intelligence.models.schemas import (
    AnalyzeInciRequest,
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup,   # ⬅️ new schema for grouping
    ExtractIngredientsResponse,  # ⬅️ new schema for URL extraction
    CompareProductsRequest,  # ⬅️ new schema for comparison
    CompareProductsResponse,  # ⬅️ new schema for comparison
    ProductComparisonItem,  # ⬅️ new schema for comparison
    DecodeHistoryItem,  # ⬅️ new schema for decode history
    SaveDecodeHistoryRequest,  # ⬅️ new schema for saving history
    GetDecodeHistoryResponse,  # ⬅️ new schema for getting history
    CompareHistoryItem,  # ⬅️ new schema for compare history
    SaveCompareHistoryRequest,  # ⬅️ new schema for saving compare history
    GetCompareHistoryResponse,  # ⬅️ new schema for getting compare history
    MarketResearchRequest,  # ⬅️ new schema for market research
    MarketResearchResponse,  # ⬅️ new schema for market research response
    MarketResearchProduct,  # ⬅️ new schema for market research product
    MarketResearchHistoryItem,  # ⬅️ new schema for market research history
    SaveMarketResearchHistoryRequest,  # ⬅️ new schema for saving market research history
    GetMarketResearchHistoryResponse,  # ⬅️ new schema for getting market research history
)
from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import distributor_col, decode_history_col, compare_history_col, market_research_history_col, branded_ingredients_col, inci_col
from datetime import datetime, timezone, timedelta
from bson import ObjectId


# ============================================================================
# HELPER FUNCTIONS FOR CATEGORY COMPUTATION
# ============================================================================

async def compute_item_category(matched_inci: List[str], inci_categories: Dict[str, str]) -> Optional[str]:
    """
    Compute category for an item (handles both single and combination INCI)
    
    Logic:
    - If ANY INCI in the combination is "Active" → whole combination is "Active"
    - If ALL are "Excipient" (and no Active found) → combination is "Excipient"
    - If no categories found → None
    
    Args:
        matched_inci: List of INCI names (can be single or multiple for combinations)
        inci_categories: Dict mapping normalized INCI name to category ("Active" or "Excipient")
    
    Returns:
        "Active", "Excipient", or None
    """
    if not matched_inci:
        return None
    
    has_active = False
    has_excipient = False
    
    for inci in matched_inci:
        normalized = inci.strip().lower()
        category = inci_categories.get(normalized)
        
        if category:
            if category.upper() == "ACTIVE":
                has_active = True
            elif category.upper() == "EXCIPIENT":
                has_excipient = True
    
    # If ANY is active, whole combination is active
    if has_active:
        return "Active"
    elif has_excipient:
        # Only excipient if all are excipients (no active found)
        return "Excipient"
    
    return None


async def fetch_and_compute_categories(items: List[AnalyzeInciItem]) -> Tuple[Dict[str, str], List[AnalyzeInciItem]]:
    """
    Fetch categories for all INCI names and compute item-level categories
    
    Args:
        items: List of AnalyzeInciItem objects
    
    Returns:
        Tuple of:
        - inci_categories: Dict mapping normalized INCI name to category
        - items_processed: Items processed (category_decided for branded, category computed only for general INCI)
    """
    # Collect all unique INCI names from all items
    all_inci_names = set()
    for item in items:
        for inci in item.matched_inci:
            all_inci_names.add(inci.strip().lower())
    
    # Fetch categories from database
    inci_categories = {}
    if all_inci_names:
        normalized_names = list(all_inci_names)
        cursor = inci_col.find(
            {"inciName_normalized": {"$in": normalized_names}},
            {"inciName_normalized": 1, "category": 1}
        )
        results = await cursor.to_list(length=None)
        
        for doc in results:
            normalized = doc.get("inciName_normalized", "").strip().lower()
            category = doc.get("category")
            if normalized and category:
                inci_categories[normalized] = category
    
    # Process items: Compute category for bifurcation (actives/excipients tabs)
    # For general INCI: Get from MongoDB first, compute if not found
    # For combinations: Always compute based on individual INCI categories
    items_processed = []
    for item in items:
        # The matcher already sets description to enhanced_description if available
        display_description = item.description  # Already uses enhanced_description from matcher
        
        # Compute category for bifurcation (actives/excipients tabs)
        item_category = None
        
        if len(item.matched_inci) > 1:
            # COMBINATION: Always compute category based on individual INCI categories
            # Logic: If ANY INCI is Active → combination is Active
            item_category = await compute_item_category(item.matched_inci, inci_categories)
        elif item.tag == "G":
            # GENERAL INCI (single): Get from MongoDB first, compute if not found
            if len(item.matched_inci) == 1:
                inci_name = item.matched_inci[0].strip().lower()
                # Try to get from MongoDB first
                item_category = inci_categories.get(inci_name)
                # If not found in MongoDB, compute it (though it should be there)
                if not item_category:
                    item_category = await compute_item_category(item.matched_inci, inci_categories)
        elif item.tag == "B":
            # BRANDED (single): Use category_decided from MongoDB, but also compute for bifurcation
            # For single branded INCI, use category_decided if available, otherwise compute
            if item.category_decided:
                item_category = item.category_decided
            elif len(item.matched_inci) == 1:
                inci_name = item.matched_inci[0].strip().lower()
                item_category = inci_categories.get(inci_name)
                if not item_category:
                    item_category = await compute_item_category(item.matched_inci, inci_categories)
        
        # Create new item with only necessary fields
        item_dict = {
            "ingredient_name": item.ingredient_name,
            "ingredient_id": item.ingredient_id,
            "supplier_name": item.supplier_name,
            "description": display_description,  # Uses enhanced_description for branded ingredients
            "category_decided": item.category_decided,  # Keep category_decided from MongoDB for branded
            "category": item_category,  # Category for bifurcation (actives/excipients tabs)
            "functionality_category_tree": item.functionality_category_tree,
            "chemical_class_category_tree": item.chemical_class_category_tree,
            "match_score": item.match_score,
            "matched_inci": item.matched_inci,
            "tag": item.tag,
            "match_method": item.match_method
        }
        
        items_processed.append(AnalyzeInciItem(**item_dict))
    
    return inci_categories, items_processed

router = APIRouter(tags=["INCI Analysis"])


@router.get("/server-health")
async def server_health():
    """
    Comprehensive server health check endpoint.
    Tests: Chrome availability, Claude API, environment variables.
    """
    health_status = {
        "status": "healthy",
        "checks": {},
        "errors": []
    }
    
    # Check Chrome/Chromium
    import subprocess
    chrome_available = False
    chrome_version = None
    try:
        result = subprocess.run(
            ["google-chrome", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            chrome_available = True
            chrome_version = result.stdout.strip()
    except:
        try:
            result = subprocess.run(
                ["chromium-browser", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                chrome_available = True
                chrome_version = result.stdout.strip()
        except:
            pass
    
    health_status["checks"]["chrome"] = {
        "available": chrome_available,
        "version": chrome_version
    }
    if not chrome_available:
        health_status["errors"].append("Chrome/Chromium not found. Install with: sudo apt-get install -y google-chrome-stable")
    
    # Check environment variables
    claude_key = os.getenv("CLAUDE_API_KEY")
    headless_mode = os.getenv("HEADLESS_MODE", "true")
    
    health_status["checks"]["environment"] = {
        "CLAUDE_API_KEY": "set" if claude_key else "missing",
        "HEADLESS_MODE": headless_mode,
        "MODEL_NAME": os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"
    }
    if not claude_key:
        health_status["errors"].append("CLAUDE_API_KEY not set in environment")
        health_status["status"] = "unhealthy"
    
    # Check if Selenium can initialize (quick test)
    selenium_ok = False
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        selenium_ok = True
    except Exception as e:
        health_status["errors"].append(f"Selenium import failed: {str(e)}")
        health_status["status"] = "unhealthy"
    
    health_status["checks"]["selenium"] = {
        "imported": selenium_ok
    }
    
    # Overall status
    if health_status["errors"]:
        health_status["status"] = "unhealthy"
    
    return health_status

@router.get("/bis-rag/health")
async def bis_rag_health():
    """
    Health check endpoint for BIS RAG functionality.
    Uses the comprehensive health check function from bis_rag module.
    """
    from pathlib import Path
    import os
    
    # Get comprehensive health check
    health = check_bis_rag_health()
    
    # Format response with additional details
    health_status = {
        "status": health.get("status", "unknown"),
        "checks": {
            "pdf_files": {
                "status": "ok" if health.get("pdf_files_found", 0) > 0 else "warning",
                "count": health.get("pdf_files_found", 0),
                "path": str(BIS_DATA_PATH),
                "files": [f.name for f in list(BIS_DATA_PATH.glob("*.pdf"))[:5]] if BIS_DATA_PATH.exists() else []
            },
            "vectorstore_directory": {
                "status": "ok" if health.get("vectorstore_path_exists", False) else "warning",
                "exists": health.get("vectorstore_path_exists", False),
                "path": str(BIS_CHROMA_DB_PATH)
            },
            "vectorstore_initialization": {
                "status": "ok" if health.get("vectorstore_initialized", False) else "error",
                "initialized": health.get("vectorstore_initialized", False)
            },
            "retriever_creation": {
                "status": "ok" if health.get("retriever_created", False) else "error",
                "created": health.get("retriever_created", False),
                "test_query_results": health.get("retriever_test_query", 0)
            }
        },
        "errors": health.get("errors", []),
        "warnings": []
    }
    
    # Add warnings based on status
    if health.get("pdf_files_found", 0) == 0:
        health_status["warnings"].append("No PDF files found in data directory")
    if not health.get("vectorstore_path_exists", False):
        health_status["warnings"].append("Vectorstore directory does not exist or is empty")
    if health.get("status") != "healthy":
        health_status["warnings"].append(f"BIS RAG status: {health.get('status')}")
    
    # Set overall status based on errors
    if health_status["errors"]:
        health_status["status"] = "unhealthy"
    elif health_status["warnings"] and health_status["status"] == "healthy":
        health_status["status"] = "degraded"
        retriever = None
    
    # Check 5: Test retrieval (if retriever is available)
    if retriever is not None:
        try:
            # Test with a common ingredient
            test_query = "salicylic acid"
            test_docs = retriever.invoke(test_query)
            health_status["checks"]["test_retrieval"] = {
                "status": "ok",
                "query": test_query,
                "documents_retrieved": len(test_docs),
                "sample_doc_length": len(test_docs[0].page_content) if test_docs else 0
            }
        except Exception as e:
            health_status["checks"]["test_retrieval"] = {
                "status": "error",
                "error": str(e)
            }
            health_status["errors"].append(f"Test retrieval failed: {e}")
    else:
        health_status["checks"]["test_retrieval"] = {
            "status": "skipped",
            "reason": "Retriever not available"
        }
    
    # Check 6: Test full BIS cautions function
    try:
        test_ingredients = ["Salicylic Acid"]
        test_cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        health_status["checks"]["bis_cautions_function"] = {
            "status": "ok",
            "test_ingredients": test_ingredients,
            "ingredients_with_cautions": len(test_cautions),
            "total_cautions": sum(len(c) for c in test_cautions.values())
        }
    except Exception as e:
        health_status["checks"]["bis_cautions_function"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["errors"].append(f"BIS cautions function test failed: {e}")
    
    # Overall status
    if health_status["errors"]:
        health_status["status"] = "unhealthy"
    elif health_status["warnings"]:
        health_status["status"] = "degraded"
    
    return health_status

@router.get("/test-selenium")
async def test_selenium():
    """Test endpoint to check if Selenium is working"""
    import asyncio
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        def test():
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            print("Installing ChromeDriver...")
            service = Service(ChromeDriverManager().install())
            print("Starting Chrome...")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("Loading page...")
            driver.get("https://www.google.com")
            title = driver.title
            print(f"Page loaded: {title}")
            driver.quit()
            return title
        
        loop = asyncio.get_event_loop()
        title = await loop.run_in_executor(None, test)
        
        return {"status": "success", "message": f"Selenium is working! Page title: {title}"}
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Selenium test error: {error_trace}")
        return {
            "status": "error", 
            "message": str(e), 
            "type": type(e).__name__,
            "traceback": error_trace
        }


@router.post("/analyze-inci-form", response_model=AnalyzeInciResponse)
async def analyze_inci_form(
    inci_names: List[str] = Form(..., description="Raw INCI names from product label")
):
    """
    DEPRECATED: Use /api/analyze-inci instead (supports both JSON and form data).
    This endpoint is kept for backward compatibility only.
    """
    # Convert form data to JSON payload format and call the main endpoint
    return await analyze_inci({"inci_names": inci_names})


# URL-based ingredient extraction endpoint (ONLY extracts, doesn't analyze)
@router.post("/extract-ingredients-from-url", response_model=ExtractIngredientsResponse)
async def extract_ingredients_from_url(payload: dict):
    """
    Extract ingredients from a product URL.
    
    This endpoint ONLY extracts ingredients - it does NOT analyze them.
    After extraction, use the extracted ingredients list with /api/analyze-inci endpoint.
    
    Request body:
    {
        "url": "https://example.com/product/..."
    }
    
    Returns:
    {
        "ingredients": ["Water", "Glycerin", ...],
        "extracted_text": "Full scraped text...",
        "platform": "amazon",
        "url": "https://...",
        "processing_time": 5.123
    }
    """
    start = time.time()
    scraper = None
    
    try:
        # Validate payload
        if "url" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: url")
        
        url = payload["url"]
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(status_code=400, detail="url must be a non-empty string")
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
        
        # Initialize URL scraper
        scraper = URLScraper()
        
        # Extract ingredients from URL
        print(f"Scraping URL: {url}")
        extraction_result = await scraper.extract_ingredients_from_url(url)
        
        ingredients = extraction_result["ingredients"]
        extracted_text = extraction_result["extracted_text"]
        platform = extraction_result.get("platform", "unknown")
        is_estimated = extraction_result.get("is_estimated", False)
        source = extraction_result.get("source", "url_extraction")
        product_name = extraction_result.get("product_name")
        
        if not ingredients:
            # Check if it was an access denied issue
            if "access denied" in extracted_text.lower() or "forbidden" in extracted_text.lower() or "403" in extracted_text.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Access denied by the website. Some e-commerce sites (like Nykaa) block automated requests. Please try: 1) Copy the ingredient list manually and paste it in INCI List mode, or 2) Try a different product URL from Amazon or Flipkart."
                )
            raise HTTPException(
                status_code=404, 
                detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
            )
        
        # Generate appropriate message based on source
        message = None
        if is_estimated and source == "ai_search":
            message = f"Unable to extract ingredients directly from the URL. These are estimated ingredients found via AI search based on the product: {product_name or 'detected product'}. Please verify these ingredients match the actual product formulation."
        
        print(f"Extracted {len(ingredients)} ingredients from {platform} (estimated: {is_estimated})")
        
        # Clean up scraper
        await scraper.close()
        
        return ExtractIngredientsResponse(
            ingredients=ingredients,
            extracted_text=extracted_text,
            platform=platform,
            url=url,
            processing_time=round(time.time() - start, 3),
            is_estimated=is_estimated,
            source=source,
            product_name=product_name,
            message=message
        )
        
    except HTTPException:
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        
        # Print full traceback to server console
        print(f"\n{'='*60}")
        print(f"ERROR in extract_ingredients_from_url: {error_type}")
        print(f"Message: {error_msg}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        
        # Try to close scraper on error
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        
        # Provide more helpful error messages
        if "chrome" in error_msg.lower() or "webdriver" in error_msg.lower() or "driver" in error_msg.lower():
            raise HTTPException(
                status_code=500, 
                detail=f"Browser automation error: {error_msg}. Please ensure Chrome browser is installed. If Chrome is installed, ChromeDriver will be downloaded automatically on first use."
            )
        elif "claude" in error_msg.lower() or "anthropic" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=f"AI service error: {error_msg}. Please check CLAUDE_API_KEY environment variable."
            )
        elif "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=f"Request timeout: {error_msg}. The website may be slow or blocking requests. Please try again."
            )
        else:
            # Return full error for debugging
            raise HTTPException(
                status_code=500, 
                detail=f"{error_type}: {error_msg}"
            )


# Simple JSON endpoint for frontend compatibility
@router.post("/analyze-inci", response_model=AnalyzeInciResponse)
async def analyze_inci(payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Analyze INCI ingredients with automatic history saving.
    
    Auto-saving behavior:
    - If user_id and name are provided, automatically saves to decode history
    - Saves with "in_progress" status before analysis
    - Updates with "completed" status and analysis_result after analysis
    - Saving errors don't fail the analysis (graceful degradation)
    
    Request body:
    {
        "inci_names": ["ingredient1", "ingredient2", ...] or "ingredient1, ingredient2",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "expected_benefits": "Expected benefits" (optional)
    }
    
    Headers:
    - X-User-Id: User ID (optional, can also be in payload)
    """
    start = time.time()
    history_id = None
    
    # Extract optional fields for auto-saving
    user_id_value = user_id or payload.get("user_id")
    name = payload.get("name", "").strip()
    tag = payload.get("tag")
    notes = payload.get("notes", "")
    expected_benefits = payload.get("expected_benefits")
    input_data = payload.get("input_data")  # Optional: explicit input data, otherwise will use parsed ingredients
    
    # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided
    # Auto-save always happens if user_id is provided (name is optional, will use default if not provided)
    if user_id_value:
        try:
            # Parse INCI names first to get input_data
            if "inci_names" not in payload:
                raise HTTPException(status_code=400, detail="Missing required field: inci_names")
            
            inci_input = payload["inci_names"]
            ingredients_preview = parse_inci_string(inci_input)
            input_data_value = input_data or (", ".join(ingredients_preview) if ingredients_preview else str(inci_input))
            
            # Use provided name or generate default name from ingredients
            display_name = name if name else (ingredients_preview[0] + "..." if ingredients_preview else "Untitled Analysis")
            if not display_name or len(display_name) > 100:
                display_name = ingredients_preview[0] + "..." if ingredients_preview and len(ingredients_preview) > 0 else "Untitled Analysis"
            
            # Save initial state
            history_doc = {
                "user_id": user_id_value,
                "name": display_name,
                "tag": tag,
                "input_type": "inci",
                "input_data": input_data_value,
                "status": "in_progress",
                "notes": notes,
                "expected_benefits": expected_benefits,
                "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
            }
            result = await decode_history_col.insert_one(history_doc)
            history_id = str(result.inserted_id)
            print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
            # Continue with analysis even if saving fails
    
    try:
        # Validate payload format: { inci_names: ["ingredient1", "ingredient2", ...] or "ingredient1, ingredient2" }
        if "inci_names" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: inci_names")
        
        # Parse INCI names - handles both string and list, with all separators
        inci_input = payload["inci_names"]
        ingredients = parse_inci_string(inci_input)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No valid ingredients found after parsing. Please check your input format.")
        
        extracted_text = ", ".join(ingredients)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients provided")
        
        # 🔹 Get synonyms from CAS API for better matching
        print("Retrieving synonyms from CAS API...")
        synonyms_map = await get_synonyms_batch(ingredients)
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        
        # Match ingredients using new flow
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
        # 🔹 Get BIS cautions for all ingredients (runs in parallel with matching)
        print("Retrieving BIS cautions...")
        bis_cautions = await get_bis_cautions_for_ingredients(ingredients)
        if bis_cautions:
            print(f"[OK] Retrieved BIS cautions for {len(bis_cautions)} ingredients: {list(bis_cautions.keys())}")
        else:
            print("[WARNING] No BIS cautions retrieved - this may indicate an issue with the BIS retriever")
        
    except HTTPException:
        # Update history status to "failed" if we have history_id
        if history_id and user_id_value:
            try:
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": {"status": "failed"}}
                )
            except:
                pass
        raise
    except Exception as e:
        # Update history status to "failed" if we have history_id
        if history_id and user_id_value:
            try:
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": {"status": "failed"}}
                )
            except:
                pass
        print(f"Error in analyze_inci_json: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Fetch categories for INCI-based bifurcation (only for general INCI, not branded)
    print("Fetching ingredient categories for INCI-based bifurcation...")
    inci_categories, items_processed = await fetch_and_compute_categories(items)
    print(f"Found categories for {len(inci_categories)} INCI names")

    # 🔹 Group ALL detected ingredients (branded + general) by matched_inci
    detected_dict = defaultdict(list)
    for item in items_processed:
        key = tuple(sorted(item.matched_inci))
        detected_dict[key].append(item)

    detected: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in detected_dict.items()
    ]
    # Sort by number of INCI: more INCI first, then lower, single at last
    detected.sort(key=lambda x: len(x.inci_list), reverse=True)

    # Filter out water-related BIS cautions
    filtered_bis_cautions = None
    if bis_cautions:
        filtered_bis_cautions = {}
        water_related_keywords = ['water', 'aqua']
        for ingredient, cautions in bis_cautions.items():
            ingredient_lower = ingredient.lower()
            is_water_related = any(water_term in ingredient_lower for water_term in water_related_keywords)
            if not is_water_related:
                filtered_bis_cautions[ingredient] = cautions

    # Build response (deprecated fields are not included - they will be excluded by exclude_none=True in schema)
    response = AnalyzeInciResponse(
        detected=detected,  # All detected ingredients (branded + general) grouped by INCI
        unable_to_decode=unable_to_decode,
        processing_time=round(time.time() - start, 3),
        bis_cautions=filtered_bis_cautions if filtered_bis_cautions else None,
        categories=inci_categories if inci_categories else None,  # INCI categories for bifurcation
    )
    
    # 🔹 Auto-save: Update history with "completed" status and analysis_result
    if history_id and user_id_value:
        try:
            # Convert response to dict for storage
            analysis_result_dict = response.dict()
            
            update_doc = {
                "status": "completed",
                "analysis_result": analysis_result_dict
            }
            
            await decode_history_col.update_one(
                {"_id": ObjectId(history_id), "user_id": user_id_value},
                {"$set": update_doc}
            )
            print(f"[AUTO-SAVE] Updated history {history_id} with completed status")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
            # Don't fail the response if saving fails
    
    return response


# URL-based ingredient analysis endpoint
@router.post("/analyze-url", response_model=AnalyzeInciResponse)
async def analyze_url(payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Extract ingredients from a product URL and analyze them with automatic history saving.
    
    Auto-saving behavior:
    - If user_id and name are provided, automatically saves to decode history
    - Saves with "in_progress" status before analysis
    - Updates with "completed" status and analysis_result after analysis
    - Saving errors don't fail the analysis (graceful degradation)
    
    Request body:
    {
        "url": "https://example.com/product/...",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "expected_benefits": "Expected benefits" (optional)
    }
    
    Headers:
    - X-User-Id: User ID (optional, can also be in payload)
    
    The endpoint will:
    1. Scrape the URL to extract text content
    2. Use AI to extract ingredient list from the text
    3. Analyze the extracted ingredients
    4. Return the analysis results with extracted text
    """
    start = time.time()
    scraper = None
    history_id = None
    
    # Extract optional fields for auto-saving
    user_id_value = user_id or payload.get("user_id")
    name = payload.get("name", "").strip()
    tag = payload.get("tag")
    notes = payload.get("notes", "")
    expected_benefits = payload.get("expected_benefits")
    
    try:
        # Validate payload
        if "url" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: url")
        
        url = payload["url"]
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(status_code=400, detail="url must be a non-empty string")
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided
        # Auto-save always happens if user_id is provided (name is optional, will use default if not provided)
        if user_id_value:
            try:
                # Use provided name or generate default name from URL
                display_name = name if name else (url.split('/')[-1] if url else "Untitled Analysis")
                if not display_name or len(display_name) > 100:
                    display_name = "Untitled Analysis"
                
                history_doc = {
                    "user_id": user_id_value,
                    "name": display_name,
                    "tag": tag,
                    "input_type": "url",
                    "input_data": url,
                    "status": "in_progress",
                    "notes": notes,
                    "expected_benefits": expected_benefits,
                    "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
                }
                result = await decode_history_col.insert_one(history_doc)
                history_id = str(result.inserted_id)
                print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                # Continue with analysis even if saving fails
        
        # Initialize URL scraper
        scraper = URLScraper()
        
        # Extract ingredients from URL
        print(f"Scraping URL: {url}")
        extraction_result = await scraper.extract_ingredients_from_url(url)
        
        ingredients = extraction_result["ingredients"]
        extracted_text = extraction_result["extracted_text"]
        platform = extraction_result.get("platform", "unknown")
        
        if not ingredients:
            raise HTTPException(
                status_code=404, 
                detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
            )
        
        print(f"Extracted {len(ingredients)} ingredients from {platform}")
        
        # 🔹 Get synonyms from CAS API for better matching
        print("Retrieving synonyms from CAS API...")
        synonyms_map = await get_synonyms_batch(ingredients)
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        
        # Match ingredients using new flow
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
        # Get BIS cautions for all ingredients
        print("Retrieving BIS cautions...")
        bis_cautions = await get_bis_cautions_for_ingredients(ingredients)
        
        # Clean up scraper
        await scraper.close()
        
    except HTTPException:
        # Update history status to "failed" if we have history_id
        if history_id and user_id_value:
            try:
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": {"status": "failed"}}
                )
            except:
                pass
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise
    except Exception as e:
        # Update history status to "failed" if we have history_id
        if history_id and user_id_value:
            try:
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": {"status": "failed"}}
                )
            except:
                pass
        print(f"Error in analyze_url: {e}")
        # Try to close browser on error
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Fetch categories for INCI-based bifurcation (only for general INCI, not branded)
    print("Fetching ingredient categories for INCI-based bifurcation...")
    inci_categories, items_processed = await fetch_and_compute_categories(items)
    print(f"Found categories for {len(inci_categories)} INCI names")

    # 🔹 Group ALL detected ingredients (branded + general) by matched_inci
    detected_dict = defaultdict(list)
    for item in items_processed:
        key = tuple(sorted(item.matched_inci))
        detected_dict[key].append(item)

    detected: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in detected_dict.items()
    ]
    # Sort by number of INCI: more INCI first, then lower, single at last
    detected.sort(key=lambda x: len(x.inci_list), reverse=True)

    # Filter out water-related BIS cautions
    filtered_bis_cautions = None
    if bis_cautions:
        filtered_bis_cautions = {}
        water_related_keywords = ['water', 'aqua']
        for ingredient, cautions in bis_cautions.items():
            ingredient_lower = ingredient.lower()
            is_water_related = any(water_term in ingredient_lower for water_term in water_related_keywords)
            if not is_water_related:
                filtered_bis_cautions[ingredient] = cautions

    # Build response (deprecated fields are not included - they will be excluded by exclude_none=True in schema)
    response = AnalyzeInciResponse(
        detected=detected,  # All detected ingredients (branded + general) grouped by INCI
        unable_to_decode=unable_to_decode,
        processing_time=round(time.time() - start, 3),
        bis_cautions=filtered_bis_cautions if filtered_bis_cautions else None,
        categories=inci_categories if inci_categories else None,  # INCI categories for bifurcation
    )
    
    # 🔹 Auto-save: Update history with "completed" status and analysis_result
    if history_id and user_id_value:
        try:
            # Convert response to dict for storage
            analysis_result_dict = response.dict()
            
            update_doc = {
                "status": "completed",
                "analysis_result": analysis_result_dict
            }
            
            await decode_history_col.update_one(
                {"_id": ObjectId(history_id), "user_id": user_id_value},
                {"$set": update_doc}
            )
            print(f"[AUTO-SAVE] Updated history {history_id} with completed status")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
            # Don't fail the response if saving fails
    
    return response


@router.get("/suppliers")
async def get_suppliers():
    """
    Get all suppliers from ingre_suppliers collection
    Returns list of supplier names
    """
    try:
        suppliers_collection = db["ingre_suppliers"]
        cursor = suppliers_collection.find({}, {"supplierName": 1, "_id": 0})
        suppliers = await cursor.to_list(length=None)
        
        # Extract supplier names and sort alphabetically
        supplier_names = sorted([s.get("supplierName", "") for s in suppliers if s.get("supplierName")])
        
        return {"suppliers": supplier_names}
    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch suppliers: {str(e)}")


@router.post("/ingredients/categories")
async def get_ingredient_categories(payload: dict):
    """
    Get categories (Active/Excipient) for INCI ingredients from ingre_inci collection
    Accepts: { "inci_names": ["INCI1", "INCI2", ...] }
    Returns: { "categories": { "INCI1": "Active", "INCI2": "Excipient", ... } }
    """
    try:
        if "inci_names" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: inci_names")
        
        inci_names = payload["inci_names"]
        if not isinstance(inci_names, list):
            raise HTTPException(status_code=400, detail="inci_names must be a list")
        
        if not inci_names:
            return {"categories": {}}
        
        # Normalize INCI names for matching (lowercase, trim)
        normalized_names = [name.strip().lower() for name in inci_names]
        
        # Query ingre_inci collection for matching INCI names
        # Match on inciName_normalized field
        query = {
            "inciName_normalized": {"$in": normalized_names}
        }
        
        cursor = inci_col.find(query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
        results = await cursor.to_list(length=None)
        
        # Build mapping: normalized_name -> category
        category_map = {}
        for doc in results:
            normalized = doc.get("inciName_normalized", "").strip().lower()
            category = doc.get("category")
            if normalized and category:
                category_map[normalized] = category
        
        # Map back to original INCI names (case-insensitive)
        result_categories = {}
        for original_name in inci_names:
            normalized = original_name.strip().lower()
            if normalized in category_map:
                result_categories[original_name] = category_map[normalized]
        
        return {"categories": result_categories}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching ingredient categories: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch categories: {str(e)}")


@router.get("/suppliers/paginated")
async def get_suppliers_paginated(skip: int = 0, limit: int = 50, search: Optional[str] = None):
    """
    Get suppliers with pagination and search
    """
    try:
        suppliers_collection = db["ingre_suppliers"]
        
        # Build query
        query = {}
        if search:
            query["supplierName"] = {"$regex": search, "$options": "i"}
        
        # Get total count
        total = await suppliers_collection.count_documents(query)
        
        # Get paginated results
        cursor = suppliers_collection.find(query, {"supplierName": 1, "_id": 0}).skip(skip).limit(limit)
        suppliers = await cursor.to_list(length=None)
        
        # Extract supplier names
        supplier_names = [s.get("supplierName", "") for s in suppliers if s.get("supplierName")]
        
        return {
            "suppliers": supplier_names,
            "total": total,
            "skip": skip,
            "limit": limit,
            "hasMore": (skip + limit) < total
        }
    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch suppliers: {str(e)}")


@router.post("/distributor/register")
async def register_distributor(payload: dict):
    """
    Register a new distributor and save to distributor collection
    
    Request body:
    {
        "firmName": "ABC Distributors",
        "category": "Pvt Ltd",
        "registeredAddress": "123 Main St, City",
        "contactPerson": {
            "name": "John Doe",
            "number": "+91-1234567890",
            "email": "contact@abc.com",
            "zone": "India"
        },
        "ingredientName": "Hyaluronic Acid",
        "principlesSuppliers": ["Supplier 1", "Supplier 2"],
        "yourInfo": {
            "name": "John Doe",
            "email": "john@abc.com",
            "designation": "Director",
            "contactNo": "+91-9876543210"
        },
        "acceptTerms": true
    }
    """
    try:
        # Validate required fields
        required_fields = ["firmName", "category", "registeredAddress", "contactPersons", 
                         "ingredientName", "principlesSuppliers", "yourInfo", "acceptTerms"]
        for field in required_fields:
            if field not in payload:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        if not payload.get("acceptTerms"):
            raise HTTPException(status_code=400, detail="Terms and conditions must be accepted")
        
        # Validate contact persons
        contact_persons = payload.get("contactPersons", [])
        if not isinstance(contact_persons, list) or len(contact_persons) == 0:
            raise HTTPException(status_code=400, detail="At least one contact person is required")
        
        for idx, contact_person in enumerate(contact_persons):
            if not isinstance(contact_person, dict):
                raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: Must be an object")
            
            contact_fields = ["name", "number", "email", "zones"]
            for field in contact_fields:
                if field not in contact_person:
                    raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: Missing required field: {field}")
                
                # Validate zones field specifically
                if field == "zones":
                    if not isinstance(contact_person["zones"], list) or len(contact_person["zones"]) == 0:
                        raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: At least one zone is required")
                # Validate other fields are not empty
                elif not contact_person[field] or (isinstance(contact_person[field], str) and not contact_person[field].strip()):
                    raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: {field} cannot be empty")
        
        # Validate principles suppliers
        principles_suppliers = payload.get("principlesSuppliers", [])
        if not isinstance(principles_suppliers, list) or len(principles_suppliers) == 0:
            raise HTTPException(status_code=400, detail="At least one supplier must be selected in Principles You Represent")
        
        # Validate your info
        your_info = payload.get("yourInfo", {})
        if not isinstance(your_info, dict):
            raise HTTPException(status_code=400, detail="yourInfo must be an object")
        
        your_info_fields = ["name", "email", "designation", "contactNo"]
        for field in your_info_fields:
            if field not in your_info or not your_info[field]:
                raise HTTPException(status_code=400, detail=f"Your Info: Missing required field: {field}")
        
        # Prepare distributor document
        from datetime import datetime
        
        # Lookup ingredient IDs from branded ingredients collection by name
        ingredient_name = payload["ingredientName"]
        ingredient_id_provided = payload.get("ingredientId")  # Optional ingredient ID from frontend
        ingredient_ids = []
        
        # Clean ingredient name (remove trailing commas, extra spaces)
        ingredient_name_clean = ingredient_name.strip().rstrip(',').strip()
        
        print(f"🔍 Looking up ingredient IDs for: '{ingredient_name_clean}'")
        
        # CRITICAL: If ingredientId is provided from frontend, use it directly (most reliable)
        if ingredient_id_provided:
            try:
                ing_id_obj = ObjectId(ingredient_id_provided)
                # Verify the ID exists in the collection
                verify_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                if verify_doc:
                    ingredient_ids.append(str(ing_id_obj))
                    print(f"✅✅✅ Using provided ingredient ID: {ingredient_id_provided}")
                    print(f"   Verified: Ingredient '{verify_doc.get('ingredient_name', 'N/A')}' exists with this ID")
                else:
                    print(f"❌ WARNING: Provided ingredient ID {ingredient_id_provided} not found! Will lookup by name instead.")
                    ingredient_id_provided = None  # Fall back to name lookup
            except Exception as e:
                print(f"❌ WARNING: Invalid ingredient ID format {ingredient_id_provided}: {e}. Will lookup by name instead.")
                ingredient_id_provided = None  # Fall back to name lookup
        
        # If no valid ID provided, lookup by name
        if not ingredient_ids:
            print(f"🔍 No ingredient ID provided, looking up by name: '{ingredient_name_clean}'")
            
            # Strategy 1: Try exact match on ingredient_name field (case-insensitive)
            print(f"🔍 Strategy 1: Exact match search for '{ingredient_name_clean}'")
            count_found = 0
            async for branded_ingredient in branded_ingredients_col.find(
                {"ingredient_name": {"$regex": f"^{ingredient_name_clean}$", "$options": "i"}}
            ):
                count_found += 1
                ing_id_obj = branded_ingredient["_id"]
                ing_id_str = str(ing_id_obj)
                
                # CRITICAL: Verify the ID exists by querying it directly
                verify_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                if verify_doc:
                    if ing_id_str not in ingredient_ids:
                        ingredient_ids.append(ing_id_str)
                        print(f"✅ Found ingredient ID (exact match): {ing_id_str}")
                        print(f"   Ingredient Name: '{branded_ingredient.get('ingredient_name', 'N/A')}'")
                        print(f"   ObjectId Type: {type(ing_id_obj)}")
                        print(f"   String ID: {ing_id_str}")
                        print(f"   ✅ VERIFIED: Can query back with ObjectId({ing_id_str})")
                        
                        # Double verification: Try querying with string
                        try:
                            verify_doc2 = await branded_ingredients_col.find_one({"_id": ObjectId(ing_id_str)})
                            if verify_doc2:
                                print(f"   ✅ DOUBLE VERIFIED: Can also query with ObjectId(string)")
                            else:
                                print(f"   ❌ WARNING: Cannot query with ObjectId(string)")
                        except Exception as e:
                            print(f"   ❌ ERROR converting to ObjectId: {e}")
                else:
                    print(f"❌ CRITICAL: ID {ing_id_str} verification FAILED - document not found!")
            
            if count_found == 0:
                print(f"   No exact matches found")
            
            # Strategy 2: If no exact match, try normalized match (remove special chars, normalize spaces)
            if len(ingredient_ids) == 0:
                import re
                normalized_search = re.sub(r'[^\w\s]', '', ingredient_name_clean).strip()
                normalized_search = re.sub(r'\s+', ' ', normalized_search)
                print(f"🔍 Trying normalized match: '{normalized_search}'")
                
                async for branded_ingredient in branded_ingredients_col.find(
                    {"ingredient_name": {"$regex": f"^{re.escape(normalized_search)}$", "$options": "i"}}
                ):
                    ing_id = str(branded_ingredient["_id"])
                    if ing_id not in ingredient_ids:
                        ingredient_ids.append(ing_id)
                        print(f"✅ Found ingredient ID (normalized): {ing_id} for '{branded_ingredient.get('ingredient_name', 'N/A')}'")
            
            # Strategy 3: Try partial match (contains) on ingredient_name
            if len(ingredient_ids) == 0:
                print(f"🔍 Trying partial match (contains)...")
                async for branded_ingredient in branded_ingredients_col.find(
                    {"ingredient_name": {"$regex": re.escape(ingredient_name_clean), "$options": "i"}}
                ):
                    ing_id = str(branded_ingredient["_id"])
                    if ing_id not in ingredient_ids:
                        ingredient_ids.append(ing_id)
                        print(f"✅ Found ingredient ID (partial): {ing_id} for '{branded_ingredient.get('ingredient_name', 'N/A')}'")
            
            # Strategy 4: Try matching against INCI names in the ingredient's inci_ids
            if len(ingredient_ids) == 0:
                print(f"🔍 Trying INCI name match...")
                # First, get the INCI document that matches the name
                inci_doc = await inci_col.find_one(
                    {"inciName": {"$regex": f"^{ingredient_name_clean}$", "$options": "i"}}
                )
                if inci_doc:
                    inci_id = inci_doc["_id"]
                    # Now find branded ingredients that have this INCI in their inci_ids
                    async for branded_ingredient in branded_ingredients_col.find(
                        {"inci_ids": inci_id}
                    ):
                        ing_id = str(branded_ingredient["_id"])
                        if ing_id not in ingredient_ids:
                            ingredient_ids.append(ing_id)
                            print(f"✅ Found ingredient ID (via INCI): {ing_id} for '{branded_ingredient.get('ingredient_name', 'N/A')}'")
        
        # Final verification: Check all found IDs actually exist in the collection
        # This is CRITICAL - we must verify each ID can be queried
        verified_ids = []
        print(f"\n🔍 FINAL VERIFICATION: Testing {len(ingredient_ids)} ID(s)...")
        for ing_id_str in ingredient_ids:
            try:
                print(f"\n   Testing ID: {ing_id_str}")
                print(f"   ID Type: {type(ing_id_str)}")
                
                # Convert to ObjectId
                ing_id_obj = ObjectId(ing_id_str)
                print(f"   Converted to ObjectId: {ing_id_obj}")
                print(f"   ObjectId Type: {type(ing_id_obj)}")
                
                # Query 1: Direct ObjectId query
                verify_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                if verify_doc:
                    print(f"   ✅ Query 1 PASSED: Found with ObjectId")
                    print(f"      Ingredient: '{verify_doc.get('ingredient_name', 'N/A')}'")
                    
                    # Query 2: String to ObjectId conversion
                    verify_doc2 = await branded_ingredients_col.find_one({"_id": ObjectId(ing_id_str)})
                    if verify_doc2:
                        print(f"   ✅ Query 2 PASSED: Found with ObjectId(string)")
                        verified_ids.append(ing_id_str)
                        print(f"   ✅✅✅ ID {ing_id_str} is VALID and VERIFIED")
                    else:
                        print(f"   ❌ Query 2 FAILED: Cannot find with ObjectId(string)")
                else:
                    print(f"   ❌ Query 1 FAILED: ID {ing_id_str} does NOT exist!")
                    print(f"   🔍 Debug: Checking if ID exists in any form...")
                    
                    # Try to find by string match in _id field (shouldn't work but let's check)
                    all_docs = await branded_ingredients_col.find({}).limit(5).to_list(length=5)
                    print(f"   Sample _id types from collection:")
                    for doc in all_docs:
                        print(f"      - {doc.get('ingredient_name', 'N/A')}: _id={doc['_id']} (type: {type(doc['_id'])}, str: {str(doc['_id'])})")
                    
            except Exception as e:
                print(f"   ❌ ERROR: Invalid ID format {ing_id_str}: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n📊 Verification Summary:")
        print(f"   Original IDs: {len(ingredient_ids)}")
        print(f"   Verified IDs: {len(verified_ids)}")
        print(f"   Verified ID List: {verified_ids}")
        
        ingredient_ids = verified_ids  # Use only verified IDs
        
        if len(ingredient_ids) == 0:
            print(f"❌ ERROR: No valid ingredient IDs found for '{ingredient_name_clean}'. Please check if the ingredient exists in the database.")
            print(f"   Searched in: ingredient_name field and INCI names")
            # Let's also show what ingredients exist with similar names for debugging
            print(f"   Debug: Searching for similar ingredient names...")
            async for similar in branded_ingredients_col.find(
                {"ingredient_name": {"$regex": ingredient_name_clean[:5] if len(ingredient_name_clean) > 5 else ingredient_name_clean, "$options": "i"}}
            ).limit(5):
                print(f"   Similar: '{similar.get('ingredient_name', 'N/A')}' (ID: {similar['_id']})")
        else:
            print(f"✅ Successfully found and verified {len(ingredient_ids)} ingredient ID(s): {ingredient_ids}")
        
        # Validate and prepare contact persons data
        contact_persons_data = []
        for idx, cp in enumerate(contact_persons):
            contact_person_data = {
                "name": cp.get("name", "").strip(),
                "number": cp.get("number", "").strip(),
                "email": cp.get("email", "").strip(),
                "zones": cp.get("zones", []) if isinstance(cp.get("zones"), list) else []
            }
            # Ensure zones is a list of strings
            if contact_person_data["zones"]:
                contact_person_data["zones"] = [str(zone).strip() for zone in contact_person_data["zones"] if zone]
            contact_persons_data.append(contact_person_data)
            print(f"📝 Contact Person {idx + 1}: {contact_person_data['name']} - {contact_person_data['email']} - Zones: {contact_person_data['zones']}")
        
        # Store only ingredientIds (list) - names will be fetched from IDs when needed
        # Do NOT store ingredientName - it will be fetched from IDs when querying
        # IMPORTANT: Store IDs as strings (MongoDB will handle conversion when needed)
        distributor_doc = {
            "firmName": payload["firmName"],
            "category": payload["category"],
            "registeredAddress": payload["registeredAddress"],
            "contactPersons": contact_persons_data,  # Use validated and cleaned contact persons
            "ingredientIds": ingredient_ids,  # Store ONLY list of ingredient IDs (as strings) - names fetched from IDs
            "principlesSuppliers": payload["principlesSuppliers"],
            "yourInfo": payload["yourInfo"],
            "acceptTerms": payload["acceptTerms"],
            "status": "under review",  # under review, approved, rejected
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        print(f"💾 Saving distributor document:")
        print(f"   - Firm: {payload['firmName']}")
        print(f"   - Ingredient Name: {ingredient_name_clean}")
        print(f"   - Ingredient IDs: {ingredient_ids}")
        print(f"   - Contact Persons: {len(contact_persons_data)}")
        
        # CRITICAL: Final verification before saving - test EXACTLY how we'll query them later
        final_verified_ids = []
        if ingredient_ids:
            print(f"\n🔍 CRITICAL FINAL VERIFICATION: Testing {len(ingredient_ids)} ID(s) can be queried...")
            for ing_id_str in ingredient_ids:
                print(f"\n   Testing ID: '{ing_id_str}'")
                print(f"   ID length: {len(ing_id_str)}")
                print(f"   ID format check: {ing_id_str.isalnum() if isinstance(ing_id_str, str) else 'not string'}")
                
                try:
                    # Test 1: Convert to ObjectId
                    ing_id_obj = ObjectId(ing_id_str)
                    print(f"   ✅ Can convert to ObjectId: {ing_id_obj}")
                    
                    # Test 2: Query with ObjectId (this is how we'll use it)
                    test_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                    if test_doc:
                        print(f"   ✅✅✅ ID {ing_id_str} EXISTS in collection!")
                        print(f"      Ingredient Name: '{test_doc.get('ingredient_name', 'N/A')}'")
                        print(f"      Document _id: {test_doc['_id']}")
                        print(f"      Document _id type: {type(test_doc['_id'])}")
                        print(f"      Document _id as string: {str(test_doc['_id'])}")
                        
                        # Test 3: Verify the string matches
                        if str(test_doc['_id']) == ing_id_str:
                            print(f"   ✅ String ID matches document _id")
                            final_verified_ids.append(ing_id_str)
                        else:
                            print(f"   ⚠️ WARNING: String mismatch! Document has: {str(test_doc['_id'])}, we have: {ing_id_str}")
                            # Use the actual document ID instead
                            final_verified_ids.append(str(test_doc['_id']))
                            print(f"   ✅ Using actual document ID: {str(test_doc['_id'])}")
                    else:
                        print(f"   ❌❌❌ CRITICAL: ID {ing_id_str} CANNOT be found in collection!")
                        print(f"   🔍 Debug: Checking collection stats...")
                        total_count = await branded_ingredients_col.count_documents({})
                        print(f"   Total documents in collection: {total_count}")
                        
                        # Try to find ANY document to see ID format
                        sample_doc = await branded_ingredients_col.find_one({})
                        if sample_doc:
                            print(f"   Sample document _id: {sample_doc['_id']} (type: {type(sample_doc['_id'])}, str: {str(sample_doc['_id'])})")
                        
                except Exception as e:
                    print(f"   ❌❌❌ CRITICAL ERROR with ID {ing_id_str}: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"\n📊 Final Verification Summary:")
            print(f"   Original IDs: {ingredient_ids}")
            print(f"   Verified IDs: {final_verified_ids}")
            print(f"   Verified Count: {len(final_verified_ids)}")
            
            # Update the doc with ONLY verified IDs
            ingredient_ids = final_verified_ids
            distributor_doc["ingredientIds"] = ingredient_ids
            
            if len(ingredient_ids) == 0:
                print(f"\n⚠️⚠️⚠️ WARNING: No valid ingredient IDs to save! Distributor will be saved with empty ingredientIds array.")
        
        # Insert into distributor collection
        result = await distributor_col.insert_one(distributor_doc)
        
        if result.inserted_id:
            return {
                "success": True,
                "message": "Distributor registration submitted successfully",
                "distributorId": str(result.inserted_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save distributor registration")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error registering distributor: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to register distributor: {str(e)}")


@router.get("/distributor/verify-ingredient-id/{ingredient_id}")
async def verify_ingredient_id(ingredient_id: str):
    """
    Debug endpoint to verify if an ingredient ID exists in the branded ingredients collection
    """
    try:
        print(f"🔍 Verifying ingredient ID: {ingredient_id}")
        
        # Try to find the ingredient
        try:
            ing_id_obj = ObjectId(ingredient_id)
        except Exception as e:
            return {
                "valid_format": False,
                "error": f"Invalid ObjectId format: {e}",
                "ingredient_id": ingredient_id
            }
        
        # Query the collection
        ingredient_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
        
        if ingredient_doc:
            return {
                "valid_format": True,
                "exists": True,
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_doc.get("ingredient_name", "N/A"),
                "document_id": str(ingredient_doc["_id"]),
                "document_id_type": str(type(ingredient_doc["_id"])),
                "match": str(ingredient_doc["_id"]) == ingredient_id
            }
        else:
            # Show sample documents to help debug
            sample_docs = await branded_ingredients_col.find({}).limit(3).to_list(length=3)
            sample_info = []
            for doc in sample_docs:
                sample_info.append({
                    "ingredient_name": doc.get("ingredient_name", "N/A"),
                    "_id": str(doc["_id"]),
                    "_id_type": str(type(doc["_id"]))
                })
            
            return {
                "valid_format": True,
                "exists": False,
                "ingredient_id": ingredient_id,
                "error": "Ingredient ID not found in branded_ingredients collection",
                "sample_documents": sample_info,
                "total_documents": await branded_ingredients_col.count_documents({})
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "ingredient_id": ingredient_id
        }


@router.get("/distributor/by-ingredient/{ingredient_name}")
async def get_distributor_by_ingredient(ingredient_name: str, ingredient_id: Optional[str] = None):
    """
    Get all distributor information for a specific ingredient
    
    Searches by ingredientIds array (primary) and ingredient name (backward compatibility).
    Returns list of all distributors for the ingredient, otherwise returns empty list
    
    Query params:
    - ingredient_name: Name of the ingredient (required, from path)
    - ingredient_id: ID of the ingredient (optional, from query string)
    """
    try:
        # Build query to search by ingredientIds array (primary) and name (backward compatibility)
        query_conditions = []
        ingredient_ids_to_search = []
        
        # If ingredient_id is provided, use it
        if ingredient_id:
            try:
                # Validate that ingredient_id is a valid ObjectId format
                ObjectId(ingredient_id)
                ingredient_ids_to_search.append(ingredient_id)
            except:
                # If ingredient_id is not a valid ObjectId, ignore it
                pass
        else:
            # If ingredient_id not provided, lookup IDs from ingredient name
            async for branded_ingredient in branded_ingredients_col.find(
                {"ingredient_name": {"$regex": f"^{ingredient_name}$", "$options": "i"}}
            ):
                ingredient_ids_to_search.append(str(branded_ingredient["_id"]))
        
        # Primary: Search by ingredientIds array using $in operator
        # Convert string IDs to ObjectIds for proper MongoDB querying
        if ingredient_ids_to_search:
            ingredient_ids_as_objectids = []
            for ing_id_str in ingredient_ids_to_search:
                try:
                    ingredient_ids_as_objectids.append(ObjectId(ing_id_str))
                except:
                    print(f"⚠️ Invalid ObjectId format: {ing_id_str}")
            
            if ingredient_ids_as_objectids:
                # Also search with string IDs (in case they're stored as strings)
                query_conditions.append({
                    "$or": [
                        {"ingredientIds": {"$in": ingredient_ids_as_objectids}},  # ObjectId format
                        {"ingredientIds": {"$in": ingredient_ids_to_search}}  # String format
                    ]
                })
        
        # Backward compatibility: Also search by ingredient name (case-insensitive)
        # This handles old records that may only have ingredientName
        query_conditions.append({"ingredientName": {"$regex": f"^{ingredient_name}$", "$options": "i"}})
        
        # Use $or to search by either ingredientIds or name
        query = {"$or": query_conditions} if len(query_conditions) > 1 else query_conditions[0]
        
        # Find all distributors matching the query
        distributors = await distributor_col.find(query).sort("createdAt", -1).to_list(length=None)
        
        # Convert ObjectId to string and fetch ingredientName from IDs for response
        for distributor in distributors:
            distributor["_id"] = str(distributor["_id"])
            
            # Always fetch ingredientName from ingredientIds (primary source)
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                ingredient_names = []
                for ing_id in distributor["ingredientIds"]:
                    try:
                        # Try as ObjectId first, then as string
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                            except:
                                print(f"⚠️ Invalid ObjectId format in distributor: {ing_id}")
                                continue
                        else:
                            ing_id_obj = ing_id
                        
                        ing_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                        if ing_doc:
                            ingredient_names.append(ing_doc.get("ingredient_name", ""))
                            print(f"✅ Found ingredient name for ID {ing_id}: {ing_doc.get('ingredient_name', 'N/A')}")
                        else:
                            print(f"❌ ERROR: Ingredient ID {ing_id} not found in branded_ingredients collection!")
                    except Exception as e:
                        print(f"⚠️ Error looking up ingredient ID {ing_id}: {e}")
                        pass
                # Use first name found, or join if multiple
                if ingredient_names:
                    distributor["ingredientName"] = ingredient_names[0] if len(ingredient_names) == 1 else ", ".join(ingredient_names)
                else:
                    # If IDs don't resolve, fallback to stored name or query parameter
                    distributor["ingredientName"] = distributor.get("ingredientName", ingredient_name)
            else:
                # Backward compatibility: if no ingredientIds, use stored ingredientName or query parameter
                if "ingredientName" not in distributor:
                    distributor["ingredientName"] = ingredient_name
        
        return distributors if distributors else []
            
    except Exception as e:
        print(f"Error fetching distributors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch distributors: {str(e)}")


@router.post("/distributor/by-ingredients")
async def get_distributors_by_ingredients(payload: dict):
    """
    Get distributor information for multiple ingredients in a single batch call
    
    Request body:
    {
        "ingredients": [
            {"name": "Ingredient1", "id": "optional_id1"},
            {"name": "Ingredient2", "id": "optional_id2"},
            ...
        ]
    }
    
    Returns:
    {
        "Ingredient1": [distributor1, distributor2, ...],
        "Ingredient2": [distributor3, ...],
        ...
    }
    """
    try:
        if "ingredients" not in payload or not isinstance(payload["ingredients"], list):
            raise HTTPException(status_code=400, detail="Request must contain 'ingredients' array")
        
        ingredients = payload["ingredients"]
        if not ingredients:
            return {}
        
        # Collect all ingredient IDs and names
        all_ingredient_ids = []
        all_ingredient_names = []
        ingredient_id_map = {}  # Maps ingredient_name -> list of IDs
        ingredient_name_to_key = {}  # Maps normalized name to original key
        
        for ing in ingredients:
            if not isinstance(ing, dict) or "name" not in ing:
                continue
            
            ingredient_name = ing["name"]
            ingredient_id = ing.get("id")
            
            # Normalize name for lookup
            normalized_name = ingredient_name.strip().lower()
            ingredient_name_to_key[normalized_name] = ingredient_name
            
            # If ID provided, use it
            if ingredient_id:
                try:
                    ObjectId(ingredient_id)  # Validate format
                    all_ingredient_ids.append(ingredient_id)
                    if ingredient_name not in ingredient_id_map:
                        ingredient_id_map[ingredient_name] = []
                    ingredient_id_map[ingredient_name].append(ingredient_id)
                except:
                    pass
            
            all_ingredient_names.append(ingredient_name)
        
        # If no IDs provided, lookup IDs from names
        if not all_ingredient_ids:
            for ing in ingredients:
                if not isinstance(ing, dict) or "name" not in ing:
                    continue
                ingredient_name = ing["name"]
                async for branded_ingredient in branded_ingredients_col.find(
                    {"ingredient_name": {"$regex": f"^{ingredient_name}$", "$options": "i"}}
                ):
                    ing_id_str = str(branded_ingredient["_id"])
                    all_ingredient_ids.append(ing_id_str)
                    if ingredient_name not in ingredient_id_map:
                        ingredient_id_map[ingredient_name] = []
                    ingredient_id_map[ingredient_name].append(ing_id_str)
        
        # Build query conditions
        query_conditions = []
        
        # Primary: Search by ingredientIds array using $in operator
        if all_ingredient_ids:
            ingredient_ids_as_objectids = []
            for ing_id_str in all_ingredient_ids:
                try:
                    ingredient_ids_as_objectids.append(ObjectId(ing_id_str))
                except:
                    pass
            
            if ingredient_ids_as_objectids:
                query_conditions.append({
                    "$or": [
                        {"ingredientIds": {"$in": ingredient_ids_as_objectids}},  # ObjectId format
                        {"ingredientIds": {"$in": all_ingredient_ids}}  # String format
                    ]
                })
        
        # Backward compatibility: Also search by ingredient names (case-insensitive)
        if all_ingredient_names:
            name_regex_conditions = [
                {"ingredientName": {"$regex": f"^{name}$", "$options": "i"}}
                for name in all_ingredient_names
            ]
            if name_regex_conditions:
                query_conditions.append({"$or": name_regex_conditions})
        
        # Build final query
        if not query_conditions:
            return {}
        
        query = {"$or": query_conditions} if len(query_conditions) > 1 else query_conditions[0]
        
        # Single database query for all distributors
        all_distributors = await distributor_col.find(query).sort("createdAt", -1).to_list(length=None)
        
        # Process distributors: convert ObjectId to string and fetch ingredient names
        processed_distributors = []
        for distributor in all_distributors:
            distributor["_id"] = str(distributor["_id"])
            
            # Fetch ingredientName from ingredientIds
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                ingredient_names = []
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                            except:
                                continue
                        else:
                            ing_id_obj = ing_id
                        
                        ing_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                        if ing_doc:
                            ingredient_names.append(ing_doc.get("ingredient_name", ""))
                    except Exception as e:
                        pass
                
                if ingredient_names:
                    distributor["ingredientName"] = ingredient_names[0] if len(ingredient_names) == 1 else ", ".join(ingredient_names)
                else:
                    distributor["ingredientName"] = distributor.get("ingredientName", "")
            else:
                distributor["ingredientName"] = distributor.get("ingredientName", "")
            
            processed_distributors.append(distributor)
        
        # Group distributors by ingredient name
        result_map = {}
        
        # Initialize result map with empty arrays for all requested ingredients
        for ing in ingredients:
            if isinstance(ing, dict) and "name" in ing:
                result_map[ing["name"]] = []
        
        # Group distributors by matching ingredient
        for distributor in processed_distributors:
            distributor_ingredient_name = distributor.get("ingredientName", "")
            
            # Try to match distributor to requested ingredients
            matched = False
            for ing in ingredients:
                if not isinstance(ing, dict) or "name" not in ing:
                    continue
                
                ingredient_name = ing["name"]
                normalized_name = ingredient_name.strip().lower()
                distributor_normalized = distributor_ingredient_name.strip().lower()
                
                # Check if distributor matches this ingredient
                # Match by exact name or if distributor's ingredientIds contains this ingredient's ID
                if (normalized_name == distributor_normalized or 
                    (ingredient_name in ingredient_id_map and 
                     distributor.get("ingredientIds") and
                     any(str(ing_id) in [str(x) for x in distributor.get("ingredientIds", [])] 
                         for ing_id in ingredient_id_map[ingredient_name]))):
                    if ingredient_name not in result_map:
                        result_map[ingredient_name] = []
                    result_map[ingredient_name].append(distributor)
                    matched = True
                    break
            
            # If no match found but distributor has ingredientName, try fuzzy match
            if not matched and distributor_ingredient_name:
                for ing in ingredients:
                    if not isinstance(ing, dict) or "name" not in ing:
                        continue
                    ingredient_name = ing["name"]
                    if ingredient_name.strip().lower() == distributor_ingredient_name.strip().lower():
                        if ingredient_name not in result_map:
                            result_map[ingredient_name] = []
                        result_map[ingredient_name].append(distributor)
                        break
        
        return result_map
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching distributors in batch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch distributors: {str(e)}")


@router.post("/compare-products", response_model=CompareProductsResponse)
async def compare_products(payload: dict):
    """
    Compare two products based on URLs or INCI strings.
    
    Request body:
    {
        "input1": "https://example.com/product1" or "Water, Glycerin, ...",
        "input2": "https://example.com/product2" or "Water, Hyaluronic Acid, ...",
        "input1_type": "url" or "inci",
        "input2_type": "url" or "inci"
    }
    
    The endpoint will:
    1. If URL: Scrape the URL to extract product data
    2. If INCI: Use the INCI string directly
    3. Send both to Claude for structured comparison
    4. Return comparison data with INCI, benefits, claims, price, and attributes
    """
    start = time.time()
    scraper = None
    
    try:
        # Validate payload
        if "input1" not in payload or "input2" not in payload:
            raise HTTPException(status_code=400, detail="Missing required fields: input1 and input2")
        
        if "input1_type" not in payload or "input2_type" not in payload:
            raise HTTPException(status_code=400, detail="Missing required fields: input1_type and input2_type")
        
        input1 = payload["input1"]
        input2 = payload["input2"]
        input1_type = payload["input1_type"].lower()
        input2_type = payload["input2_type"].lower()
        
        if input1_type not in ["url", "inci"] or input2_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input1_type and input2_type must be 'url' or 'inci'")
        
        # Initialize scraper if needed
        if input1_type == "url" or input2_type == "url":
            scraper = URLScraper()
        
        # Use the shared INCI parser utility
        from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
        
        # Store URLs for Claude context
        url1_context = None
        url2_context = None
        
        # Process input1
        print(f"Processing input1 (type: {input1_type})...")
        if input1_type == "url":
            if not input1.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="input1 must be a valid URL when input1_type is 'url'")
            url1_context = input1  # Store URL for Claude
            extraction_result1 = await scraper.extract_ingredients_from_url(input1)
            text1 = extraction_result1.get("extracted_text", "")
            inci1 = extraction_result1.get("ingredients", [])
            product_name1 = extraction_result1.get("product_name")
            # Try to detect product name from text if not already extracted
            if not product_name1 and text1:
                try:
                    product_name1 = await scraper.detect_product_name(text1, input1)
                except:
                    pass
        else:
            # INCI input - parse directly first, then use Claude to clean if needed
            text1 = input1
            inci1 = parse_inci_string(input1)
            # Use Claude to clean and validate INCI list if we have a scraper
            if scraper and inci1:
                try:
                    cleaned_inci = await scraper.extract_ingredients_from_text(input1)
                    if cleaned_inci:
                        inci1 = cleaned_inci
                except:
                    pass  # Fall back to parsed list
            product_name1 = None
        
        # Process input2
        print(f"Processing input2 (type: {input2_type})...")
        if input2_type == "url":
            if not input2.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="input2 must be a valid URL when input2_type is 'url'")
            url2_context = input2  # Store URL for Claude
            extraction_result2 = await scraper.extract_ingredients_from_url(input2)
            text2 = extraction_result2.get("extracted_text", "")
            inci2 = extraction_result2.get("ingredients", [])
            product_name2 = extraction_result2.get("product_name")
            # Try to detect product name from text if not already extracted
            if not product_name2 and text2:
                try:
                    product_name2 = await scraper.detect_product_name(text2, input2)
                except:
                    pass
        else:
            # INCI input - parse directly first, then use Claude to clean if needed
            text2 = input2
            inci2 = parse_inci_string(input2)
            # Use Claude to clean and validate INCI list if we have a scraper
            if scraper and inci2:
                try:
                    cleaned_inci = await scraper.extract_ingredients_from_text(input2)
                    if cleaned_inci:
                        inci2 = cleaned_inci
                except:
                    pass  # Fall back to parsed list
            product_name2 = None
        
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
        from app.config import CLAUDE_MODEL
        model_name = CLAUDE_MODEL if CLAUDE_MODEL else (os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929")
        
        # Prepare full text for better extraction (use more context to capture price, ratings, etc.)
        # Use more characters to ensure we capture price, ratings, and other product details
        # Increase limit to capture all available information
        text1_full = text1[:10000] if len(text1) > 10000 else text1
        text2_full = text2[:10000] if len(text2) > 10000 else text2
        
        # Debug: Print what we're extracting
        print(f"Input1 extracted text length: {len(text1)} chars")
        print(f"Input1 text preview (first 500 chars): {text1[:500]}")
        if url1_context:
            print(f"Input1 URL: {url1_context}")
        
        print(f"Input2 extracted text length: {len(text2)} chars")
        print(f"Input2 text preview (first 500 chars): {text2[:500]}")
        if url2_context:
            print(f"Input2 URL: {url2_context}")
        
        # Build URL context strings
        url1_info = f"\n- Source URL: {url1_context}" if url1_context else "\n- Source: INCI text input (no URL)"
        url2_info = f"\n- Source URL: {url2_context}" if url2_context else "\n- Source: INCI text input (no URL)"
        
        comparison_prompt = f"""You are an expert cosmetic product analyst. Compare two cosmetic products and provide a structured comparison.

IMPORTANT: If a URL is provided, use it as context to verify and extract information. The URL may contain additional product details like price, ratings, and specifications that might not be fully captured in the scraped text.

Product 1 Data:
- Product Name (if known): {product_name1 or 'Not specified'}{url1_info}
- INCI Ingredients: {', '.join(inci1) if inci1 else 'Not available'}
- Full Extracted Text:
{text1_full}

Product 2 Data:
- Product Name (if known): {product_name2 or 'Not specified'}{url2_info}
- INCI Ingredients: {', '.join(inci2) if inci2 else 'Not available'}
- Full Extracted Text:
{text2_full}

Please analyze both products CAREFULLY and extract ALL available information from the extracted text. Return a JSON object with the following structure:
{{
  "product1": {{
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
  }},
  "product2": {{
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
  }}
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
        response = claude_client.messages.create(
            model=model_name,
            max_tokens=8192,
            temperature=0.1,
            messages=[
                {
                    "role": "user",
                    "content": comparison_prompt
                }
            ]
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
        
        # Build response with extracted text
        product1_data = comparison_data.get("product1", {})
        product2_data = comparison_data.get("product2", {})
        
        # Merge with actual INCI if we extracted it (prefer our extraction if available)
        final_inci1 = product1_data.get("inci", []) if product1_data.get("inci") else inci1
        final_inci2 = product2_data.get("inci", []) if product2_data.get("inci") else inci2
        
        product1_data["inci"] = final_inci1
        product2_data["inci"] = final_inci2
        
        # Add extracted text
        product1_data["extracted_text"] = text1
        product2_data["extracted_text"] = text2
        
        # Fallback: Determine boolean attributes from INCI if Claude didn't extract them
        # Only override if Claude returned null
        attrs1 = determine_attributes_from_inci(final_inci1, text1)
        attrs2 = determine_attributes_from_inci(final_inci2, text2)
        
        # Update attributes only if they're null in Claude's response
        for attr in ["sulphate_free", "paraben_free", "fragrance_free"]:
            if product1_data.get(attr) is None and attrs1.get(attr) is not None:
                product1_data[attr] = attrs1[attr]
                print(f"Fallback: Set product1.{attr} = {attrs1[attr]} from INCI analysis")
            if product2_data.get(attr) is None and attrs2.get(attr) is not None:
                product2_data[attr] = attrs2[attr]
                print(f"Fallback: Set product2.{attr} = {attrs2[attr]} from INCI analysis")
        
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
        
        # Check for missing fields in both products
        missing_fields1 = identify_missing_fields(product1_data, 1)
        missing_fields2 = identify_missing_fields(product2_data, 2)
        
        # Fill missing fields for product 1
        if missing_fields1:
            print(f"Attempting to fill {len(missing_fields1)} missing fields for Product 1...")
            fill_prompt1 = f"""You are an expert cosmetic product researcher. Use your knowledge base, web search capabilities, and deep analysis to find missing information about this product.

Product Information:
- Product Name: {product1_data.get('product_name') or 'Unknown'}
- Brand Name: {product1_data.get('brand_name') or 'Unknown'}
- INCI Ingredients: {', '.join(final_inci1) if final_inci1 else 'Not available'}
- Current Extracted Text: {text1[:5000] if text1 else 'Not available'}
- Source URL: {url1_context or 'Not provided'}
- Current Benefits: {', '.join(product1_data.get('benefits', [])) or 'None'}
- Current Claims: {', '.join(product1_data.get('claims', [])) or 'None'}

MISSING FIELDS TO FILL:
{', '.join(missing_fields1)}

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
                fill_response1 = claude_client.messages.create(
                    model=model_name,
                    max_tokens=8192,
                    temperature=0.2,
                    messages=[
                        {
                            "role": "user",
                            "content": fill_prompt1
                        }
                    ]
                )
                
                fill_content1 = fill_response1.content[0].text.strip()
                if '{' in fill_content1 and '}' in fill_content1:
                    json_start = fill_content1.find('{')
                    json_end = fill_content1.rfind('}') + 1
                    json_str = fill_content1[json_start:json_end]
                    fill_data1 = json.loads(json_str)
                    
                    # Merge filled fields into product1_data
                    for field in missing_fields1:
                        if field in fill_data1 and fill_data1[field] is not None:
                            # Handle list fields
                            if field in ["benefits", "claims"]:
                                if isinstance(fill_data1[field], list) and len(fill_data1[field]) > 0:
                                    product1_data[field] = fill_data1[field]
                                    print(f"✓ Filled product1.{field} with {len(fill_data1[field])} items")
                            # Handle boolean fields - never allow null
                            elif field in ["cruelty_free", "sulphate_free", "paraben_free", "vegan", "organic", "fragrance_free", "non_comedogenic", "hypoallergenic"]:
                                if fill_data1[field] is not None:
                                    product1_data[field] = fill_data1[field]
                                    print(f"✓ Filled product1.{field} = {fill_data1[field]}")
                            # Handle string fields
                            else:
                                if fill_data1[field] and fill_data1[field] != "null":
                                    product1_data[field] = fill_data1[field]
                                    print(f"✓ Filled product1.{field} = {fill_data1[field]}")
            except Exception as e:
                print(f"Warning: Failed to fill missing fields for Product 1: {e}")
        
        # Fill missing fields for product 2
        if missing_fields2:
            print(f"Attempting to fill {len(missing_fields2)} missing fields for Product 2...")
            fill_prompt2 = f"""You are an expert cosmetic product researcher. Use your knowledge base, web search capabilities, and deep analysis to find missing information about this product.

Product Information:
- Product Name: {product2_data.get('product_name') or 'Unknown'}
- Brand Name: {product2_data.get('brand_name') or 'Unknown'}
- INCI Ingredients: {', '.join(final_inci2) if final_inci2 else 'Not available'}
- Current Extracted Text: {text2[:5000] if text2 else 'Not available'}
- Source URL: {url2_context or 'Not provided'}
- Current Benefits: {', '.join(product2_data.get('benefits', [])) or 'None'}
- Current Claims: {', '.join(product2_data.get('claims', [])) or 'None'}

MISSING FIELDS TO FILL:
{', '.join(missing_fields2)}

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
                fill_response2 = claude_client.messages.create(
                    model=model_name,
                    max_tokens=8192,
                    temperature=0.2,
                    messages=[
                        {
                            "role": "user",
                            "content": fill_prompt2
                        }
                    ]
                )
                
                fill_content2 = fill_response2.content[0].text.strip()
                if '{' in fill_content2 and '}' in fill_content2:
                    json_start = fill_content2.find('{')
                    json_end = fill_content2.rfind('}') + 1
                    json_str = fill_content2[json_start:json_end]
                    fill_data2 = json.loads(json_str)
                    
                    # Merge filled fields into product2_data
                    for field in missing_fields2:
                        if field in fill_data2 and fill_data2[field] is not None:
                            # Handle list fields
                            if field in ["benefits", "claims"]:
                                if isinstance(fill_data2[field], list) and len(fill_data2[field]) > 0:
                                    product2_data[field] = fill_data2[field]
                                    print(f"✓ Filled product2.{field} with {len(fill_data2[field])} items")
                            # Handle boolean fields - never allow null
                            elif field in ["cruelty_free", "sulphate_free", "paraben_free", "vegan", "organic", "fragrance_free", "non_comedogenic", "hypoallergenic"]:
                                if fill_data2[field] is not None:
                                    product2_data[field] = fill_data2[field]
                                    print(f"✓ Filled product2.{field} = {fill_data2[field]}")
                            # Handle string fields
                            else:
                                if fill_data2[field] and fill_data2[field] != "null":
                                    product2_data[field] = fill_data2[field]
                                    print(f"✓ Filled product2.{field} = {fill_data2[field]}")
            except Exception as e:
                print(f"Warning: Failed to fill missing fields for Product 2: {e}")
        
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
        
        ensure_no_nulls(product1_data, 1, attrs1)
        ensure_no_nulls(product2_data, 2, attrs2)
        
        # Calculate processing time (fix: use the start variable from the beginning)
        processing_time = time.time() - start
        
        return CompareProductsResponse(
            product1=ProductComparisonItem(**product1_data),
            product2=ProductComparisonItem(**product2_data),
            processing_time=processing_time
        )
        
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


@router.post("/save-decode-history")
async def save_decode_history(payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Save decode history with name and tag (user-specific)
    
    HISTORY FUNCTIONALITY:
    - All decode operations are automatically saved to user's history
    - History is user-specific and isolated by user_id
    - Supports status tracking: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Name and tags can be edited later using PATCH /decode-history/{history_id}
    - Input data (INCI or URL) cannot be changed after creation
    - History items can be searched by name or tag
    - History persists across sessions and page refreshes
    
    Request body:
    {
        "name": "Product Name",
        "tag": "optional-tag",
        "input_type": "inci" or "url",
        "input_data": "ingredient list or URL",
        "analysis_result": {...} (optional if status is "in_progress"),
        "status": "in_progress" | "completed" | "failed" (default: "completed")
    }
    
    Headers:
    - X-User-Id: User ID (optional, can also be in payload)
    """
    try:
        # Validate payload
        if "name" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: name")
        if "input_type" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: input_type")
        if "input_data" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: input_data")
        
        name = payload["name"]
        tag = payload.get("tag")
        input_type = payload["input_type"]
        input_data = payload["input_data"]
        status = payload.get("status", "completed")  # Default to "completed" for backward compatibility
        analysis_result = payload.get("analysis_result")  # Optional if status is "in_progress"
        report_data = payload.get("report_data")  # Optional report data
        notes = payload.get("notes", "")  # Optional notes
        expected_benefits = payload.get("expected_benefits")  # Optional expected benefits
        
        # Validate status
        if status not in ["in_progress", "completed", "failed"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'in_progress', 'completed', or 'failed'")
        
        # If status is completed, analysis_result is required
        if status == "completed" and analysis_result is None:
            raise HTTPException(status_code=400, detail="analysis_result is required when status is 'completed'")
        
        # Get user_id from header or payload
        user_id_value = user_id or payload.get("user_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header or user_id in payload")
        
        # Create history document
        history_doc = {
            "user_id": user_id_value,
            "name": name,
            "tag": tag,
            "input_type": input_type,
            "input_data": input_data,
            "status": status,
            "report_data": report_data,  # Store report if available
            "notes": notes,  # Store notes
            "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
        }
        
        # Only include analysis_result if provided
        if analysis_result is not None:
            history_doc["analysis_result"] = analysis_result
        
        # Include expected_benefits if provided
        if expected_benefits is not None:
            history_doc["expected_benefits"] = expected_benefits
        
        # Insert into MongoDB
        result = await decode_history_col.insert_one(history_doc)
        history_doc["_id"] = str(result.inserted_id)
        
        return {
            "success": True,
            "id": str(result.inserted_id),
            "message": "History saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error saving decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save decode history: {str(e)}"
        )


@router.get("/decode-history")
async def get_decode_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Get decode history with optional unified search by name or tag (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Returns all decode history items for the authenticated user
    - Status field indicates: "pending" (analysis in progress), "analyzed" (completed), or "failed"
    - Frontend can use status to determine if analysis is complete or still pending
    - If page refreshes before analysis completes, status="pending" indicates input is preserved
    - Items with status="pending" will have analysis_result=None
    - Supports pagination with limit and skip parameters
    - Search works across both name and tag fields
    
    Query parameters:
    - search: Search term for name or tag (optional, searches both)
    - limit: Number of results (default: 50)
    - skip: Number of results to skip (default: 0)
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        # Validate user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        # Build query - ALWAYS filter by user_id
        query = {"user_id": user_id}
        
        # Unified search: search both name and tag
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"tag": {"$regex": search, "$options": "i"}}
            ]
        
        # Get total count
        total = await decode_history_col.count_documents(query)
        
        # Fetch items
        cursor = decode_history_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string and ensure all fields are included
        for item in items:
            item["id"] = str(item["_id"])
            del item["_id"]
            # Ensure report_data is included (might be None if not set)
            if "report_data" not in item:
                item["report_data"] = None
            # Map status for frontend: "in_progress" -> "pending", "completed" -> "analyzed"
            if "status" in item:
                status_mapping = {
                    "in_progress": "pending",
                    "completed": "analyzed",
                    "failed": "failed"
                }
                item["status"] = status_mapping.get(item["status"], item["status"])
            else:
                # Default to "analyzed" for backward compatibility (old records without status)
                item["status"] = "analyzed"
            # Ensure analysis_result is None if status is pending or failed
            if item.get("status") in ["pending", "failed"] and "analysis_result" not in item:
                item["analysis_result"] = None
        
        # Debug: print first item to verify report_data is included
        if items:
            first_item = items[0]
            print(f"DEBUG: First history item - ID: {first_item.get('id')}, Has report_data: {first_item.get('report_data') is not None}, Report length: {len(first_item.get('report_data', '')) if first_item.get('report_data') else 0}")
        
        return GetDecodeHistoryResponse(
            items=[DecodeHistoryItem(**item) for item in items],
            total=total
        )
        
    except Exception as e:
        print(f"Error fetching decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch decode history: {str(e)}"
        )


@router.options("/decode-history/{history_id}")
async def options_decode_history(history_id: str):
    """Handle OPTIONS preflight request for CORS"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )

@router.patch("/decode-history/{history_id}")
async def update_decode_history(history_id: str, payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Update a decode history item - allows editing name and tags only
    
    HISTORY FUNCTIONALITY:
    - Name and tags can be edited at any time, even after analysis is complete
    - Input data (INCI or URL) cannot be changed after creation to maintain data integrity
    - Other fields like report_data, notes, status, and analysis_result can also be updated
    - This endpoint is useful for organizing and categorizing history items
    
    Editable fields:
    - name: Update the name of the decode history item
    - tag: Update or add a categorization tag
    - notes: Update user notes
    - report_data: Update report HTML (if available)
    - status: Update status (in_progress, completed, failed)
    - analysis_result: Update analysis result
    - expected_benefits: Update expected benefits
    
    Non-editable fields:
    - input_data: Cannot be changed (creates new history item instead)
    - input_type: Cannot be changed
    - user_id: Cannot be changed
    - created_at: Cannot be changed
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        # Validate user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Prevent editing input_data and input_type
        if "input_data" in payload or "input_type" in payload:
            raise HTTPException(
                status_code=400, 
                detail="input_data and input_type cannot be edited. Create a new history item instead."
            )
        
        # Build update document
        update_doc = {}
        if "name" in payload:
            update_doc["name"] = payload["name"]
        if "tag" in payload:
            update_doc["tag"] = payload["tag"]
        if "report_data" in payload:
            update_doc["report_data"] = payload["report_data"]
        if "notes" in payload:
            update_doc["notes"] = payload["notes"]
        if "status" in payload:
            status = payload["status"]
            if status not in ["in_progress", "completed", "failed"]:
                raise HTTPException(status_code=400, detail="Invalid status. Must be 'in_progress', 'completed', or 'failed'")
            update_doc["status"] = status
        if "analysis_result" in payload:
            update_doc["analysis_result"] = payload["analysis_result"]
        if "expected_benefits" in payload:
            update_doc["expected_benefits"] = payload["expected_benefits"]
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Only update if it belongs to the user
        result = await decode_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to update it")
        
        return {
            "success": True,
            "message": "History updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update decode history: {str(e)}"
        )


@router.delete("/decode-history/{history_id}")
async def delete_decode_history(history_id: str, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Delete a decode history item by ID (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Permanently deletes a decode history item from user's history
    - Only the owner (matching user_id) can delete their own history items
    - Deletion is permanent and cannot be undone
    - Useful for cleaning up old or unwanted history items
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        # Validate user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Only delete if it belongs to the user
        result = await decode_history_col.delete_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to delete it")
        
        return {
            "success": True,
            "message": "History item deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete decode history: {str(e)}"
        )


# ========== COMPARE HISTORY ENDPOINTS ==========

@router.post("/save-compare-history")
async def save_compare_history(payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Save compare history with name and tag (user-specific)
    
    HISTORY FUNCTIONALITY:
    - All product comparison operations are automatically saved to user's history
    - History is user-specific and isolated by user_id
    - Supports status tracking: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Name and tags can be used for organization and categorization
    - History items can be searched by name or tag
    - History persists across sessions and page refreshes
    
    Request body:
    {
        "name": "Comparison Name",
        "tag": "optional-tag",
        "input1": "URL or INCI",
        "input2": "URL or INCI",
        "input1_type": "url" or "inci",
        "input2_type": "url" or "inci",
        "comparison_result": {...} (optional if status is "in_progress"),
        "status": "in_progress" | "completed" | "failed" (default: "completed")
    }
    
    Headers:
    - X-User-Id: User ID (optional, can also be in payload)
    """
    try:
        # Validate payload
        if "name" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: name")
        if "input1" not in payload or "input2" not in payload:
            raise HTTPException(status_code=400, detail="Missing required fields: input1 and input2")
        if "input1_type" not in payload or "input2_type" not in payload:
            raise HTTPException(status_code=400, detail="Missing required fields: input1_type and input2_type")
        
        name = payload["name"]
        tag = payload.get("tag")
        input1 = payload["input1"]
        input2 = payload["input2"]
        input1_type = payload["input1_type"]
        input2_type = payload["input2_type"]
        status = payload.get("status", "completed")  # Default to "completed" for backward compatibility
        comparison_result = payload.get("comparison_result")  # Optional if status is "in_progress"
        notes = payload.get("notes", "")  # Optional notes
        
        # Validate status
        if status not in ["in_progress", "completed", "failed"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'in_progress', 'completed', or 'failed'")
        
        # If status is completed, comparison_result is required
        if status == "completed" and comparison_result is None:
            raise HTTPException(status_code=400, detail="comparison_result is required when status is 'completed'")
        
        # Get user_id from header or payload
        user_id_value = user_id or payload.get("user_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header or user_id in payload")
        
        # Create history document
        history_doc = {
            "user_id": user_id_value,
            "name": name,
            "tag": tag,
            "input1": input1,
            "input2": input2,
            "input1_type": input1_type,
            "input2_type": input2_type,
            "status": status,
            "notes": notes,  # Store notes
            "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
        }
        
        # Only include comparison_result if provided
        if comparison_result is not None:
            history_doc["comparison_result"] = comparison_result
        
        # Insert into MongoDB
        result = await compare_history_col.insert_one(history_doc)
        history_doc["_id"] = str(result.inserted_id)
        
        return {
            "success": True,
            "id": str(result.inserted_id),
            "message": "Compare history saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error saving compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save compare history: {str(e)}"
        )


@router.get("/compare-history")
async def get_compare_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Get compare history with optional unified search by name or tag (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Returns all comparison history items for the authenticated user
    - Status field indicates: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Frontend can use status to determine if comparison is complete or still pending
    - If page refreshes before comparison completes, status="in_progress" indicates inputs are preserved
    - Items with status="in_progress" will have comparison_result=None
    - Supports pagination with limit and skip parameters
    - Search works across both name and tag fields
    
    Query parameters:
    - search: Search term for name or tag (optional, searches both)
    - limit: Number of results (default: 50)
    - skip: Number of results to skip (default: 0)
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        # Validate user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        # Build query - ALWAYS filter by user_id
        query = {"user_id": user_id}
        
        # Unified search: search both name and tag
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"tag": {"$regex": search, "$options": "i"}}
            ]
        
        # Get total count
        total = await compare_history_col.count_documents(query)
        
        # Fetch items
        cursor = compare_history_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string and ensure all fields are included
        for item in items:
            item["id"] = str(item["_id"])
            del item["_id"]
            # Map status for frontend: "in_progress" -> "pending", "completed" -> "analyzed"
            if "status" in item:
                status_mapping = {
                    "in_progress": "pending",
                    "completed": "analyzed",
                    "failed": "failed"
                }
                item["status"] = status_mapping.get(item["status"], item["status"])
            else:
                # Default to "analyzed" for backward compatibility (old records without status)
                item["status"] = "analyzed"
            # Ensure comparison_result is None if status is pending or failed
            if item.get("status") in ["pending", "failed"] and "comparison_result" not in item:
                item["comparison_result"] = None
        
        return GetCompareHistoryResponse(
            items=[CompareHistoryItem(**item) for item in items],
            total=total
        )
        
    except Exception as e:
        print(f"Error fetching compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch compare history: {str(e)}"
        )


@router.patch("/compare-history/{history_id}")
async def update_compare_history(history_id: str, payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Update a compare history item (e.g., add notes)
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        # Validate user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Build update document
        update_doc = {}
        if "notes" in payload:
            update_doc["notes"] = payload["notes"]
        if "status" in payload:
            status = payload["status"]
            if status not in ["in_progress", "completed", "failed"]:
                raise HTTPException(status_code=400, detail="Invalid status. Must be 'in_progress', 'completed', or 'failed'")
            update_doc["status"] = status
        if "comparison_result" in payload:
            update_doc["comparison_result"] = payload["comparison_result"]
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Only update if it belongs to the user
        result = await compare_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to update it")
        
        return {
            "success": True,
            "message": "History updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update compare history: {str(e)}"
        )


@router.delete("/compare-history/{history_id}")
async def delete_compare_history(history_id: str, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Delete a compare history item by ID (user-specific)
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        # Validate user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Only delete if it belongs to the user
        result = await compare_history_col.delete_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to delete it")
        
        return {
            "success": True,
            "message": "Compare history item deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete compare history: {str(e)}"
        )


# ============================================================================
# AI-POWERED INGREDIENT IDENTIFICATION FOR MARKET RESEARCH
# ============================================================================

async def analyze_formulation_and_suggest_matching_with_ai(
    original_ingredients: List[str],
    normalized_ingredients: List[str],
    category_map: Dict[str, str]
) -> Dict[str, any]:
    """
    Use Claude AI to analyze formulation and suggest what ingredients/products to match
    for market research when no active ingredients are found in the database.
    
    Returns dict with:
    - analysis: AI's analysis message
    - product_type: Type of product (cleanser, lotion, etc.)
    - ingredients_to_match: List of normalized ingredient names to use for matching
    """
    if not claude_client:
        return {
            "analysis": None,
            "product_type": None,
            "ingredients_to_match": [],
            "reasoning": None
        }
    
    print(f"    [AI Function] Analyzing formulation with {len(original_ingredients)} ingredients...")
    
    # Build context about what we found
    categorized_ingredients = []
    uncategorized_ingredients = []
    
    for norm_ing in normalized_ingredients:
        category = category_map.get(norm_ing)
        original = next((ing for ing in original_ingredients if ing.strip().lower() == norm_ing), norm_ing)
        if category:
            categorized_ingredients.append(f"- {original} → {category}")
        else:
            uncategorized_ingredients.append(f"- {original}")
    
    system_prompt = """You are an expert cosmetic chemist analyzing formulations for market research matching.

Your task is to:
1. Analyze the formulation to determine if it has active ingredients
2. Identify the product type (cleanser, lotion, serum, etc.)
3. If no actives found, provide a clear analysis message
4. Suggest which ingredients should be used for matching similar products

ANALYSIS APPROACH:
- First, check if there are any therapeutic/active ingredients (moisturizers like urea/glycerin, sunscreens, acne actives, soothing agents, etc.)
- If NO actives found, provide a message like: "This formulation contains no defined active ingredient (e.g., no moisturizer like urea/glycerin, no sunscreen, no acne actives, no soothing agents, etc.). Based on ingredients, it resembles a [product_type]."
- Identify the product type: cleanser, lotion base, cream base, shampoo, conditioner, etc.
- Based on the product type, suggest which ingredients to use for matching (even if they're excipients, they can help find similar base formulations)

MATCHING STRATEGY:
- If actives exist: Use those for matching
- If no actives: Use key functional ingredients that define the product type (e.g., for cleansers: surfactants; for lotions: emollients, humectants)

OUTPUT FORMAT:
Return a JSON object with this structure:
{
  "analysis": "Your analysis message (e.g., 'This formulation contains no defined active ingredient...')",
  "product_type": "cleanser" | "lotion" | "cream" | "serum" | "shampoo" | "conditioner" | "other",
  "ingredients_to_match": ["normalized_ingredient1", "normalized_ingredient2", ...],
  "reasoning": "Brief explanation of matching strategy"
}

The "ingredients_to_match" array should contain NORMALIZED (lowercase, trimmed) ingredient names from the input list that should be used for matching products."""

    user_prompt = f"""Analyze this formulation and determine the matching strategy for market research.

ORIGINAL INGREDIENT LIST:
{chr(10).join(original_ingredients[:50])}

CATEGORIZED INGREDIENTS (from database):
{chr(10).join(categorized_ingredients[:20]) if categorized_ingredients else "None found in database"}

UNCATEGORIZED INGREDIENTS (not in database):
{chr(10).join(uncategorized_ingredients[:30]) if uncategorized_ingredients else "None"}

TASK:
1. Check if this formulation has any active/therapeutic ingredients
2. If NO actives: Provide analysis message explaining why (e.g., "This formulation contains no defined active ingredient...")
3. Identify the product type based on ingredient profile
4. Suggest which ingredients to use for matching (actives if present, or key functional ingredients if no actives)
5. Return normalized ingredient names for matching

Return your analysis as JSON with the structure specified in the system prompt."""

    try:
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=8192,
            temperature=0.2,  # Lower temperature for more consistent classification
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return {
                "analysis": None,
                "product_type": None,
                "ingredients_to_match": [],
                "reasoning": None
            }
        
        content = response.content[0].text.strip()
        
        # Try to extract JSON from the response
        # Handle cases where response might have markdown code blocks
        json_match = re.search(r'\{[^{}]*"ingredients_to_match"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        analysis = result.get("analysis", "")
        product_type = result.get("product_type", "")
        ingredients_to_match = result.get("ingredients_to_match", [])
        reasoning = result.get("reasoning", "")
        
        print(f"    AI Analysis: {analysis}")
        if product_type:
            print(f"    Product Type: {product_type}")
        print(f"    AI Reasoning: {reasoning}")
        
        # Normalize the AI-identified ingredients to match our format
        normalized_actives = []
        for ai_ing in ingredients_to_match:
            normalized = re.sub(r"\s+", " ", str(ai_ing).strip()).strip().lower()
            if normalized and normalized in normalized_ingredients:
                normalized_actives.append(normalized)
        
        return {
            "analysis": analysis,
            "product_type": product_type,
            "ingredients_to_match": normalized_actives,
            "reasoning": reasoning
        }
        
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Error parsing AI response as JSON: {e}")
        print(f"    Response was: {content[:200]}")
        # Return empty dict instead of empty list to maintain structure
        return {
            "analysis": None,
            "product_type": None,
            "ingredients_to_match": [],
            "reasoning": None
        }
    except Exception as e:
        print(f"    ⚠️  Error calling Claude AI: {e}")
        import traceback
        traceback.print_exc()
        # Return empty dict instead of empty list to maintain structure
        return {
            "analysis": None,
            "product_type": None,
            "ingredients_to_match": [],
            "reasoning": None
        }


async def enhance_product_ranking_with_ai(
    products: List[Dict],
    input_actives: List[str],
    original_ingredients: List[str]
) -> List[Dict]:
    """
    Use AI to intelligently re-rank products based on ingredient analysis.
    Considers ingredient importance, concentration, and product similarity.
    """
    if not claude_client or len(products) == 0:
        return products
    
    # Limit to top 20 products for AI analysis (to avoid too many API calls)
    products_to_analyze = products[:20]
    
    # Build product summary for AI
    product_summaries = []
    for i, product in enumerate(products_to_analyze):
        product_summaries.append({
            "index": i,
            "name": product.get("productName", "Unknown"),
            "brand": product.get("brand", ""),
            "matched_actives": product.get("active_ingredients", [])[:5],  # Top 5
            "match_percentage": product.get("match_percentage", 0),
            "total_ingredients": product.get("total_ingredients", 0)
        })
    
    system_prompt = """You are an expert cosmetic product analyst specializing in market research and product matching.

Your task is to analyze and rank products based on their similarity to a target product's active ingredients.

RANKING CRITERIA (in order of importance):
1. **Active Ingredient Match Quality**: Products with more matching active ingredients rank higher
2. **Ingredient Importance**: Key actives (e.g., Retinol, Niacinamide, Salicylic Acid) are more important than less common ones
3. **Match Completeness**: Products that match ALL or most target actives rank higher than partial matches
4. **Product Relevance**: Products with similar active profiles are more relevant

OUTPUT FORMAT:
Return a JSON object with this structure:
{
  "ranked_indices": [3, 1, 5, 2, ...],  // Product indices in order of relevance (0-based)
  "reasoning": "Brief explanation of ranking logic"
}

The ranked_indices array should contain the product indices (from the input) in order from most relevant to least relevant."""

    user_prompt = f"""Analyze and rank the following products based on their similarity to the target product's active ingredients.

TARGET PRODUCT ACTIVE INGREDIENTS:
{chr(10).join(f"- {ing}" for ing in input_actives[:10])}

PRODUCTS TO RANK:
{json.dumps(product_summaries, indent=2)}

TASK:
1. Analyze each product's matched active ingredients
2. Compare them to the target product's active ingredients
3. Rank products from most similar/relevant to least similar
4. Consider both the number of matches and the importance of matched ingredients

Return your ranking as JSON with the structure specified in the system prompt."""

    try:
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=8192,
            temperature=0.2,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return products
        
        content = response.content[0].text.strip()
        
        # Extract JSON
        json_match = re.search(r'\{[^{}]*"ranked_indices"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        ranked_indices = result.get("ranked_indices", [])
        reasoning = result.get("reasoning", "")
        
        print(f"    AI Ranking Reasoning: {reasoning}")
        
        # Re-order products based on AI ranking
        if ranked_indices and len(ranked_indices) == len(products_to_analyze):
            # Create mapping from index to product
            reordered = []
            used_indices = set()
            for idx in ranked_indices:
                if 0 <= idx < len(products_to_analyze) and idx not in used_indices:
                    reordered.append(products_to_analyze[idx])
                    used_indices.add(idx)
            
            # Add any products not in the AI ranking (shouldn't happen, but safety check)
            for i, product in enumerate(products_to_analyze):
                if i not in used_indices:
                    reordered.append(product)
            
            # Combine with products not analyzed
            return reordered + products[len(products_to_analyze):]
        
        return products
        
    except Exception as e:
        print(f"    ⚠️  Error in AI ranking: {e}")
        return products


# ============================================================================
# MARKET RESEARCH HISTORY ENDPOINTS
# ============================================================================

@router.post("/save-market-research-history")
async def save_market_research_history(payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Save market research history (user-specific)
    
    Request body:
    {
        "name": "Product Name",
        "tag": "optional-tag",
        "input_type": "inci" or "url",
        "input_data": "ingredient list or URL",
        "research_result": {...} (optional),
        "ai_analysis": "AI analysis message",
        "ai_product_type": "Product type",
        "ai_reasoning": "AI reasoning",
        "notes": "User notes"
    }
    
    Headers:
    - X-User-Id: User ID (optional, can also be in payload)
    """
    try:
        if "name" not in payload:
            raise HTTPException(status_code=400, detail="name is required")
        if "input_type" not in payload:
            raise HTTPException(status_code=400, detail="input_type is required")
        if "input_data" not in payload:
            raise HTTPException(status_code=400, detail="input_data is required")
        
        user_id_value = user_id or payload.get("user_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="user_id is required (provide in header or payload)")
        
        name = payload.get("name", "").strip()
        tag = payload.get("tag", "").strip() or None
        input_type = payload.get("input_type", "").lower()
        input_data = payload.get("input_data", "").strip()
        research_result = payload.get("research_result")
        ai_analysis = payload.get("ai_analysis")
        ai_product_type = payload.get("ai_product_type")
        ai_reasoning = payload.get("ai_reasoning")
        notes = payload.get("notes", "").strip() or None
        
        if input_type not in ["inci", "url"]:
            raise HTTPException(status_code=400, detail="input_type must be 'inci' or 'url'")
        
        history_doc = {
            "user_id": user_id_value,
            "name": name,
            "tag": tag,
            "input_type": input_type,
            "input_data": input_data,
            "research_result": research_result,
            "ai_analysis": ai_analysis,
            "ai_product_type": ai_product_type,
            "ai_reasoning": ai_reasoning,
            "notes": notes,
            "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
        }
        
        result = await market_research_history_col.insert_one(history_doc)
        
        return {
            "success": True,
            "id": str(result.inserted_id),
            "message": "Market research history saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error saving market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save market research history: {str(e)}"
        )


@router.get("/market-research-history", response_model=GetMarketResearchHistoryResponse)
async def get_market_research_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Get market research history (user-specific)
    
    Query parameters:
    - search: Search term for name or tag (optional)
    - limit: Number of results (default: 50)
    - skip: Number of results to skip (default: 0)
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        query = {"user_id": user_id}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"tag": {"$regex": search, "$options": "i"}}
            ]
        
        total = await market_research_history_col.count_documents(query)
        cursor = market_research_history_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        for item in items:
            item["id"] = str(item["_id"])
            del item["_id"]
        
        return GetMarketResearchHistoryResponse(
            items=[MarketResearchHistoryItem(**item) for item in items],
            total=total
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market research history: {str(e)}"
        )


@router.patch("/market-research-history/{history_id}")
async def update_market_research_history(history_id: str, payload: dict, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Update market research history item (user-specific)
    Allows editing name, tag, and notes
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        update_data = {}
        if "name" in payload:
            update_data["name"] = payload["name"].strip()
        if "tag" in payload:
            update_data["tag"] = payload["tag"].strip() or None
        if "notes" in payload:
            update_data["notes"] = payload["notes"].strip() or None
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = await market_research_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to update it")
        
        return {
            "success": True,
            "message": "Market research history updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update market research history: {str(e)}"
        )


@router.delete("/market-research-history/{history_id}")
async def delete_market_research_history(history_id: str, user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Delete market research history item (user-specific)
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required. Please provide X-User-Id header")
        
        result = await market_research_history_col.delete_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to delete it")
        
        return {
            "success": True,
            "message": "Market research history deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete market research history: {str(e)}"
        )


# Market Research endpoint - matches ingredients with externalProducts collection
@router.post("/market-research", response_model=MarketResearchResponse)
async def market_research(payload: dict):
    """
    Market Research: Match products from URL or INCI list with externalProducts collection.
    
    IMPORTANT: Only matches ACTIVE ingredients. Shows all products that have at least one active ingredient match.
    
    Request body:
    {
        "url": "https://example.com/product/..." (required if input_type is "url"),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci"),
        "input_type": "url" or "inci"
    }
    
    Returns:
    {
        "products": [list of matched products with images and full details, sorted by active match percentage],
        "extracted_ingredients": [list of ingredients extracted from input],
        "total_matched": number of matched products (with at least one active ingredient match),
        "processing_time": time taken,
        "input_type": "url" or "inci"
    }
    
    Note: Products are included if they match at least one active ingredient from the input.
    Excipients and unknown ingredients are ignored for matching purposes.
    """
    start = time.time()
    scraper = None
    
    try:
        # Validate payload
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'")
        
        ingredients = []
        extracted_text = ""
        
        if input_type == "url":
            url = payload.get("url", "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="url is required when input_type is 'url'")
            
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
            
            # Initialize URL scraper and extract ingredients
            scraper = URLScraper()
            print(f"Scraping URL for market research: {url}")
            extraction_result = await scraper.extract_ingredients_from_url(url)
            
            # Get ingredients - could be list or string, ensure it's a list
            ingredients_raw = extraction_result.get("ingredients", [])
            extracted_text = extraction_result.get("extracted_text", "")
            
            # If ingredients is a string, parse it
            if isinstance(ingredients_raw, str):
                ingredients = parse_inci_string(ingredients_raw)
            elif isinstance(ingredients_raw, list):
                ingredients = ingredients_raw
            else:
                ingredients = []
            
            print(f"Extracted ingredients from URL: {ingredients}")
            
            if not ingredients:
                raise HTTPException(
                    status_code=404,
                    detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
                )
        elif input_type == "inci":
            # INCI input
            inci = payload.get("inci", "").strip()
            if not inci:
                raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'")
            
            # Parse INCI string
            ingredients = parse_inci_string(inci)
            extracted_text = inci
            
            if not ingredients:
                raise HTTPException(
                    status_code=400,
                    detail="No valid ingredients found after parsing. Please check your input format."
                )
        
        # Query externalproducts collection (lowercase - as shown in MongoDB Compass)
        external_products_col = db["externalproducts"]
        collection_name = "externalproducts"
        print(f"✅ Using collection: {collection_name}")
        
        # For ingredient-based matching (url, inci)
        print(f"Extracted {len(ingredients)} ingredients for market research")
        print(f"Ingredients list: {ingredients}")
        
        # Normalize ingredients for matching - use same normalization as database
        # Database uses: re.sub(r"\s+", " ", s).strip().lower()
        import re
        normalized_input_ingredients = []
        for ing in ingredients:
            if ing and ing.strip():
                # Use same normalization as database: normalize spaces, strip, lowercase
                normalized = re.sub(r"\s+", " ", ing.strip()).strip().lower()
                if normalized:
                    normalized_input_ingredients.append(normalized)
        
        # Remove duplicates while preserving order
        seen = set()
        normalized_input_ingredients = [x for x in normalized_input_ingredients if not (x in seen or seen.add(x))]
        
        print(f"Normalized {len(ingredients)} input ingredients to {len(normalized_input_ingredients)} unique normalized ingredients")
        
        print(f"Normalized ingredients for matching ({len(normalized_input_ingredients)}): {normalized_input_ingredients[:10]}{'...' if len(normalized_input_ingredients) > 10 else ''}")
        
        # Initialize AI analysis variables (will be populated if AI is used)
        ai_analysis_message = None
        ai_product_type = None
        ai_reasoning = None
        
        # Categorize input ingredients into actives and excipients
        print(f"\n{'='*60}")
        print("STEP 1.5: Categorizing input ingredients...")
        print(f"{'='*60}")
        input_actives = []  # List of normalized active ingredient names
        input_excipients = []  # List of normalized excipient ingredient names
        input_unknown = []  # Ingredients without category
        
        if normalized_input_ingredients:
            try:
                # Query INCI collection for categories (exact match only)
                inci_query = {
                    "inciName_normalized": {"$in": normalized_input_ingredients}
                }
                print(f"  Querying INCI collection with {len(normalized_input_ingredients)} normalized ingredients...")
                print(f"  Sample normalized ingredients being queried: {normalized_input_ingredients[:5]}")
                inci_cursor = inci_col.find(inci_query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                inci_results = await inci_cursor.to_list(length=None)
                print(f"  Found {len(inci_results)} INCI records in database")
                
                # Build mapping of normalized name -> category
                input_category_map = {}
                for inci_doc in inci_results:
                    normalized = inci_doc.get("inciName_normalized", "").strip().lower()
                    category = inci_doc.get("category", "")
                    inci_name = inci_doc.get("inciName", "")
                    if normalized and category:
                        input_category_map[normalized] = category
                        if len(input_category_map) <= 5:  # Log first 5 matches
                            print(f"    Matched: '{normalized}' -> category: '{category}' (INCI: {inci_name})")
                
                print(f"  Built category map with {len(input_category_map)} entries")
                if len(input_category_map) == 0 and len(normalized_input_ingredients) > 0:
                    print(f"  ⚠️  WARNING: No matches found in database!")
                    print(f"  This means the normalized names don't match what's in the database.")
                    print(f"  Sample query values: {normalized_input_ingredients[:3]}")
                    # Try to find a sample from database to compare
                    sample_doc = await inci_col.find_one({}, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                    if sample_doc:
                        print(f"  Sample DB doc: inciName='{sample_doc.get('inciName')}', inciName_normalized='{sample_doc.get('inciName_normalized')}'")
                
                # Categorize input ingredients
                for normalized_ing in normalized_input_ingredients:
                    category = input_category_map.get(normalized_ing)
                    if category == "Active":
                        input_actives.append(normalized_ing)
                    elif category == "Excipient":
                        input_excipients.append(normalized_ing)
                    else:
                        input_unknown.append(normalized_ing)
                
                print(f"  Input actives: {len(input_actives)}")
                print(f"  Input excipients: {len(input_excipients)}")
                print(f"  Input unknown (no category): {len(input_unknown)}")
                if input_actives:
                    print(f"  Sample actives: {input_actives[:5]}")
                else:
                    print(f"  ⚠️  WARNING: No active ingredients found!")
                    print(f"  This could mean:")
                    print(f"    1. Ingredients are not categorized in the database")
                    print(f"    2. Normalized names don't match")
                    print(f"    3. All ingredients are excipients")
                    print(f"  Sample normalized ingredients: {normalized_input_ingredients[:5]}")
                    print(f"  Sample category map entries: {list(input_category_map.items())[:5] if input_category_map else 'None'}")
                if input_excipients:
                    print(f"  Sample excipients: {input_excipients[:5]}")
            except Exception as e:
                print(f"  Warning: Error categorizing input ingredients: {e}")
                import traceback
                traceback.print_exc()
                # If categorization fails, treat all as unknown (will match all)
                input_unknown = normalized_input_ingredients.copy()
                print(f"  Fallback: Treating all {len(input_unknown)} ingredients as unknown")
        
        # If no actives found, use AI to analyze formulation and suggest what to match
        if len(input_actives) == 0:
            print(f"\n⚠️  No active ingredients found in database lookup!")
            print(f"  Using AI to analyze formulation and suggest matching strategy...")
            print(f"  Total input ingredients: {len(normalized_input_ingredients)}")
            
            # Use Claude AI to analyze formulation and suggest what to match
            if claude_client and normalized_input_ingredients:
                print(f"  🤖 Calling Claude AI to analyze formulation...")
                try:
                    ai_analysis = await analyze_formulation_and_suggest_matching_with_ai(
                        ingredients,
                        normalized_input_ingredients,
                        input_category_map
                    )
                    
                    # Store AI analysis for response (always store, even if no ingredients to match)
                    if ai_analysis:
                        # Get values, convert empty strings to None
                        analysis_val = ai_analysis.get("analysis")
                        ai_analysis_message = analysis_val if analysis_val and analysis_val.strip() else None
                        
                        product_type_val = ai_analysis.get("product_type")
                        ai_product_type = product_type_val if product_type_val and product_type_val.strip() else None
                        
                        reasoning_val = ai_analysis.get("reasoning")
                        ai_reasoning = reasoning_val if reasoning_val and reasoning_val.strip() else None
                        
                        print(f"  📊 AI Analysis stored: {ai_analysis_message}")
                        print(f"  🏷️  Product Type stored: {ai_product_type}")
                        print(f"  💭 AI Reasoning stored: {ai_reasoning}")
                    
                    if ai_analysis and ai_analysis.get("ingredients_to_match"):
                        ai_identified_actives = ai_analysis.get("ingredients_to_match", [])
                        print(f"  ✓ AI suggested {len(ai_identified_actives)} ingredients to match: {ai_identified_actives[:5]}")
                        
                        # Add AI-identified actives to input_actives
                        input_actives.extend(ai_identified_actives)
                        print(f"  ✓ Total active ingredients after AI: {len(input_actives)}")
                    else:
                        print(f"  ⚠️  AI could not suggest ingredients to match. Will skip product matching.")
                        if ai_analysis_message:
                            print(f"  AI Message: {ai_analysis_message}")
                except Exception as e:
                    print(f"  ❌ Error using AI to analyze formulation: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                if not claude_client:
                    print(f"  ⚠️  Claude client not available. Cannot use AI matching.")
                    if not claude_api_key:
                        print(f"     Reason: CLAUDE_API_KEY environment variable not set")
                    elif not ANTHROPIC_AVAILABLE:
                        print(f"     Reason: anthropic package not installed")
                if not normalized_input_ingredients:
                    print(f"  ⚠️  No normalized ingredients available for AI analysis.")
                print(f"  Will skip product matching since no actives to match against.")
        
        # CRITICAL: Always fetch ALL products with ingredients - don't rely on regex query
        # The regex query might not work well with arrays, so we'll do matching in Python
        print(f"\n{'='*60}")
        print("STEP 1: Fetching products from database...")
        print(f"{'='*60}")
        all_products = []
        try:
            # First, check how many products exist
            print("Counting documents in collection...")
            total_count = await external_products_col.count_documents({})
            print(f"  Total documents: {total_count}")
            
            # Check for ingredients field in different ways
            has_ingredients_count_1 = await external_products_col.count_documents({
                "ingredients": {"$exists": True}
            })
            has_ingredients_count_2 = await external_products_col.count_documents({
                "ingredients": {"$exists": True, "$ne": None}
            })
            has_ingredients_count_3 = await external_products_col.count_documents({
                "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
            })
            
            print(f"  Products with ingredients field: {has_ingredients_count_1}")
            print(f"  Products with ingredients (not null): {has_ingredients_count_2}")
            print(f"  Products with ingredients (not null/empty): {has_ingredients_count_3}")
            
            # Try to get a sample product to see the structure
            sample_product = await external_products_col.find_one({})
            if sample_product:
                print(f"\n  Sample product structure:")
                print(f"    Keys: {list(sample_product.keys())[:10]}")
                if "ingredients" in sample_product:
                    sample_ing = sample_product["ingredients"]
                    print(f"    Ingredients type: {type(sample_ing).__name__}")
                    if isinstance(sample_ing, list):
                        print(f"    Ingredients array length: {len(sample_ing)}")
                        print(f"    First 3 ingredients: {sample_ing[:3]}")
                    elif isinstance(sample_ing, str):
                        print(f"    Ingredients string length: {len(sample_ing)}")
                        print(f"    First 200 chars: {sample_ing[:200]}")
            
            # Fetch ALL products that have ingredients (no limit - we need to check everything)
            print(f"\nFetching all products with ingredients...")
            all_products = await external_products_col.find({
                "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
            }).to_list(length=None)  # NO LIMIT - check all products
            
            print(f"✅ Fetched {len(all_products)} products to check")
            
            if len(all_products) == 0:
                print(f"\n⚠️ WARNING: No products found in {collection_name} collection!")
                print("   Possible reasons:")
                print("   1. The collection is empty")
                print("   2. Products don't have 'ingredients' field")
                print("   3. All ingredients fields are null or empty")
                print("   4. Collection name is incorrect")
                
                # Try fetching ANY products to see if collection has data
                any_products = await external_products_col.find({}).limit(5).to_list(length=None)
                if any_products:
                    print(f"   Found {len(any_products)} products in collection, but none have ingredients field")
                    print(f"   Sample product keys: {list(any_products[0].keys())[:10] if any_products else 'N/A'}")
                
                return MarketResearchResponse(
                    products=[],
                    extracted_ingredients=ingredients,
                    total_matched=0,
                    processing_time=round(time.time() - start, 2),
                    input_type=input_type,
                    ai_analysis=ai_analysis_message,
                    ai_product_type=ai_product_type,
                    ai_reasoning=ai_reasoning
                )
        except Exception as e:
            print(f"\n❌ ERROR fetching products: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch products from database: {str(e)}"
            )
        
        # Debug: Check a few sample products to see ingredient format
        if all_products and len(all_products) > 0:
            print(f"\n{'='*60}")
            print("DEBUG: Sample Product Analysis")
            print(f"{'='*60}")
            for i, sample_product in enumerate(all_products[:3]):  # Check first 3 products
                sample_ingredients = sample_product.get("ingredients", "")
                product_name = sample_product.get("name") or sample_product.get("productName") or "Unknown"
                print(f"\nSample Product {i+1}: {product_name[:50]}")
                print(f"  Ingredients type: {type(sample_ingredients).__name__}")
                if isinstance(sample_ingredients, str):
                    print(f"  Ingredients (first 300 chars): {sample_ingredients[:300]}")
                    # Try to parse it
                    parsed = parse_inci_string(sample_ingredients[:300])
                    print(f"  Parsed count: {len(parsed)} ingredients")
                    if parsed:
                        print(f"  First 3 parsed: {parsed[:3]}")
                elif isinstance(sample_ingredients, list):
                    print(f"  Ingredients array length: {len(sample_ingredients)}")
                    if sample_ingredients:
                        print(f"  First 5: {sample_ingredients[:5]}")
            print(f"{'='*60}\n")
        
        # Match products based on ingredient overlap
        matched_products = []
        print(f"\n{'='*60}")
        print(f"Starting ingredient matching:")
        print(f"  Input ingredients ({len(normalized_input_ingredients)}): {normalized_input_ingredients[:10]}{'...' if len(normalized_input_ingredients) > 10 else ''}")
        print(f"  Products to check: {len(all_products)}")
        print(f"{'='*60}\n")
        
        if len(all_products) == 0:
            print("⚠️ WARNING: No products found in database to check!")
            print("This might indicate:")
            print("  1. The externalProducts collection is empty")
            print("  2. No products have an 'ingredients' field")
            print("  3. Database connection issue")
            return MarketResearchResponse(
                products=[],
                extracted_ingredients=ingredients,
                total_matched=0,
                processing_time=round(time.time() - start, 2),
                input_type=input_type
            )
        
        print(f"🔍 Starting to check {len(all_products)} products for matches...")
        print(f"  Active ingredients to match against: {len(input_actives)}")
        if input_actives:
            print(f"  Active ingredients list: {input_actives[:10]}{'...' if len(input_actives) > 10 else ''}")
        else:
            print(f"  ⚠️  NO ACTIVE INGREDIENTS FOUND - will skip all products!")
        matches_found = 0
        
        for idx, product in enumerate(all_products):
            if (idx + 1) % 500 == 0:
                print(f"  Processed {idx + 1}/{len(all_products)} products... ({matches_found} matches so far)")
            
            product_ingredients_raw = product.get("ingredients", "")
            if not product_ingredients_raw:
                continue
            
            # Parse ingredients - handle both string and array formats
            product_ingredients = []
            
            if isinstance(product_ingredients_raw, list):
                # If it's already a list, use it directly (cleaned format)
                product_ingredients = [str(ing).strip() for ing in product_ingredients_raw if ing and str(ing).strip()]
            elif isinstance(product_ingredients_raw, str):
                # Extract ingredients from the string
                ingredients_text = product_ingredients_raw.strip()
                
                # Skip if empty
                if not ingredients_text:
                    continue
                
                # Try to find the actual ingredient list (after "Full Ingredients List:" or "Ingredients:")
                if "Full Ingredients List:" in ingredients_text:
                    ingredients_text = ingredients_text.split("Full Ingredients List:")[-1].strip()
                elif "Ingredients:" in ingredients_text:
                    ingredients_text = ingredients_text.split("Ingredients:")[-1].strip()
                
                # Clean up escaped backslashes (\\\\ becomes \)
                ingredients_text = ingredients_text.replace("\\\\", "\\")
                # Replace backslashes with commas for parsing (Water\\Aqua\\Eau -> Water, Aqua, Eau)
                ingredients_text = ingredients_text.replace("\\", ", ")
                
                # Parse the ingredients string using the same parser
                product_ingredients = parse_inci_string(ingredients_text)
            else:
                continue
            
            if not product_ingredients:
                continue
            
            # Normalize product ingredients (remove trailing punctuation for better matching)
            normalized_product_ingredients = []
            original_ingredient_map = {}  # Map normalized -> original for matching
            for ing in product_ingredients:
                if isinstance(ing, str):
                    # Clean: strip, remove trailing punctuation, lowercase
                    cleaned = ing.strip().rstrip('.,;!?').strip()
                    if cleaned:
                        normalized = cleaned.lower()
                        normalized_product_ingredients.append(normalized)
                        original_ingredient_map[normalized] = ing.strip()  # Keep original for display
                elif isinstance(ing, dict) and "name" in ing:
                    cleaned = str(ing["name"]).strip().rstrip('.,;!?').strip()
                    if cleaned:
                        normalized = cleaned.lower()
                        normalized_product_ingredients.append(normalized)
                        original_ingredient_map[normalized] = str(ing["name"]).strip()
            
            # MARKET RESEARCH: Only match active ingredients
            # Skip this product if no active ingredients in input
            if len(input_actives) == 0:
                # No active ingredients to match, skip this product
                continue
            
            # Find matching ingredients - ONLY match active ingredients
            matched_ingredients = []
            matched_active_indices = set()  # Track which active ingredients were matched
            import re
            
            # Create a mapping from normalized active ingredient to its index in normalized_input_ingredients
            active_to_index_map = {}
            for idx, input_ing in enumerate(normalized_input_ingredients):
                if input_ing in input_actives:
                    active_to_index_map[input_ing] = idx
            
            # Only match active ingredients
            for active_ing in input_actives:
                input_clean = active_ing.strip()
                if not input_clean:
                    continue
                
                # Try to match this active ingredient with any product ingredient
                matched_this_active = False
                
                for prod_ing in normalized_product_ingredients:
                    prod_clean = prod_ing.strip()
                    if not prod_clean:
                        continue
                    
                    is_match = False
                    
                    # Multiple matching strategies (in order of preference):
                    # 1. Exact match
                    if input_clean == prod_clean:
                        is_match = True
                    # 2. Word boundary match - check if input is a complete word in product (most reliable)
                    elif len(input_clean) > 3:
                        # Use word boundaries for better matching
                        word_boundary_pattern = r'\b' + re.escape(input_clean) + r'\b'
                        if re.search(word_boundary_pattern, prod_clean, re.IGNORECASE):
                            is_match = True
                    # 3. Contains match (handles cases like "Niacinamide" matching "Niacinamide (Vitamin B3)")
                    # But only if the input is substantial (at least 4 chars) to avoid false matches
                    elif len(input_clean) >= 4:
                        if input_clean in prod_clean or prod_clean in input_clean:
                            is_match = True
                    # 4. For short ingredients (3 chars or less), only exact match
                    # This prevents false matches on very short strings
                    
                    if is_match:
                        # Get original ingredient name from map
                        original_ing = original_ingredient_map.get(prod_ing)
                        if original_ing and original_ing not in matched_ingredients:
                            matched_ingredients.append(original_ing)
                            # Track the index of this active ingredient
                            if active_ing in active_to_index_map:
                                matched_active_indices.add(active_to_index_map[active_ing])
                            matched_this_active = True
                            if len(matched_products) < 10:  # Log for first 10 matches for debugging
                                print(f"  ✓ Matched active: '{active_ing}' -> '{original_ing}' (product: {product.get('name', 'Unknown')[:30]})")
                        break  # Found a match for this active ingredient, move to next
                
                # Debug: log if we couldn't match this active
                if not matched_this_active and idx < 3:  # Log for first 3 products
                    print(f"  ✗ Could not match active '{active_ing}' in product {product.get('name', 'Unknown')[:30]}")
                    if len(normalized_product_ingredients) > 0:
                        print(f"    Product has {len(normalized_product_ingredients)} ingredients, sample: {normalized_product_ingredients[:3]}")
            
            # Calculate match percentage based ONLY on active ingredients
            matched_actives = []
            for matched_idx in matched_active_indices:
                if matched_idx < len(normalized_input_ingredients):
                    matched_ing_normalized = normalized_input_ingredients[matched_idx]
                    if matched_ing_normalized in input_actives:
                        matched_actives.append(matched_ing_normalized)
            
            # Match percentage is based only on active ingredients
            active_match_count = len(matched_actives)
            total_active_ingredients = len(input_actives)
            active_match_percentage = (active_match_count / total_active_ingredients * 100) if total_active_ingredients > 0 else 0
            
            # For compatibility, also calculate overall match (but we won't use it for filtering)
            match_count = active_match_count
            total_input_ingredients = len(input_actives)  # Only count actives
            match_percentage = active_match_percentage  # Same as active match percentage
            
            # MARKET RESEARCH: Include any product that has at least one active ingredient match
            # No percentage threshold - show all products with active ingredient matches
            should_include = active_match_count > 0
            
            if len(matched_products) < 5:  # Debug for first 5
                print(f"  Product match (active only): {active_match_percentage:.1f}% | Actives: {len(matched_actives)}/{len(input_actives)} | Include: {should_include}")
            
            # Include products that have at least one active ingredient match
            if should_include:
                matches_found += 1
                
                # Get product image - prioritize s3Image/s3Images, fallback to image/images
                image = None
                images = []
                
                # Try S3 images first (preferred)
                if "s3Image" in product and product["s3Image"]:
                    image = product["s3Image"]
                    if isinstance(image, str):
                        images = [image]
                
                if "s3Images" in product and product["s3Images"]:
                    if isinstance(product["s3Images"], list) and len(product["s3Images"]) > 0:
                        images = product["s3Images"]
                        if not image and images:
                            image = images[0]
                
                # Fallback to regular images if S3 not available
                if not image and "image" in product and product["image"]:
                    image = product["image"]
                    if isinstance(image, str) and image not in images:
                        images.insert(0, image)
                
                if "images" in product and product["images"]:
                    if isinstance(product["images"], list):
                        for img in product["images"]:
                            if img and img not in images:
                                images.append(img)
                        if not image and images:
                            image = images[0]
                
                # Since we only match active ingredients, all matched ingredients should be active
                # But we verify by checking the INCI collection to get the actual active ingredient names
                matched_ingredients_normalized = [ing.strip().lower() for ing in matched_ingredients]
                active_ingredients = []
                
                if matched_ingredients_normalized:
                    try:
                        # Query INCI collection for categories to verify and get proper names
                        inci_query = {
                            "inciName_normalized": {"$in": matched_ingredients_normalized}
                        }
                        inci_cursor = inci_col.find(inci_query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                        inci_results = await inci_cursor.to_list(length=None)
                        
                        # Build mapping of normalized name -> category and INCI name
                        inci_category_map = {}
                        inci_name_map = {}
                        for inci_doc in inci_results:
                            normalized = inci_doc.get("inciName_normalized", "").strip().lower()
                            category = inci_doc.get("category", "")
                            inci_name = inci_doc.get("inciName", "")
                            if normalized and category:
                                inci_category_map[normalized] = category
                                inci_name_map[normalized] = inci_name
                        
                        # Collect active ingredients from matched ingredients
                        for matched_ing in matched_ingredients:
                            normalized = matched_ing.strip().lower()
                            if normalized in inci_category_map:
                                category = inci_category_map[normalized]
                                if category == "Active":
                                    # Use proper INCI name if available, otherwise use matched name
                                    active_name = inci_name_map.get(normalized, matched_ing)
                                    if active_name not in active_ingredients:
                                        active_ingredients.append(active_name)
                    except Exception as e:
                        print(f"  Warning: Error checking active ingredients: {e}")
                        # Fallback: use matched ingredients as active ingredients
                        active_ingredients = matched_ingredients.copy()
                else:
                    # No matched ingredients, so no active ingredients
                    active_ingredients = []
                
                # active_match_count is the number of input active ingredients that were matched
                active_match_count = len(matched_actives)
                
                # Build product data using correct field names from schema
                product_data = {
                    "id": str(product.get("_id", "")),  # Use 'id' instead of '_id' for Pydantic
                    "productName": product.get("name") or product.get("productName") or product.get("product_name"),
                    "brand": product.get("brand") or product.get("brandName") or product.get("brand_name"),
                    "ingredients": product_ingredients,  # Now it's a parsed list
                    "image": image,
                    "images": images,
                    "price": product.get("price"),
                    "salePrice": product.get("salePrice") or product.get("sale_price"),
                    "description": product.get("description"),
                    "matched_ingredients": matched_ingredients,  # All matched ingredients (should be active)
                    "match_count": active_match_count,  # Number of input active ingredients matched
                    "total_ingredients": len(product_ingredients),
                    "match_percentage": round(active_match_percentage, 2),  # Active match percentage
                    "match_score": round(active_match_percentage, 2),  # Use active match percentage as score
                    "active_match_count": active_match_count,  # Number of active ingredients matched
                    "active_ingredients": active_ingredients  # List of matched active ingredients (verified from INCI)
                }
                
                # Add any other fields from the product (excluding unwanted fields)
                # Exclude: countryOfOrigin, manufacturer, expiryDate, address, and similar fields
                excluded_fields = {
                    "countryOfOrigin", "manufacturer", "expiryDate", "expiry", 
                    "address", "Address", "Expiry Date", "Country of Origin", 
                    "Manufacturer", "Address:", "Expiry Date:", "Country of Origin:"
                }
                for key in ["category", "subcategory", "url"]:
                    if key in product and key not in excluded_fields:
                        product_data[key] = product[key]
                
                # Also filter out any unwanted fields that might be in the product dict
                # Clean description if it contains unwanted info
                if "description" in product_data and product_data["description"]:
                    desc = product_data["description"]
                    # Remove patterns like "Expiry Date: ...", "Country of Origin: ...", etc.
                    import re
                    patterns_to_remove = [
                        r"Expiry Date:\s*[^\n]*",
                        r"Country of Origin:\s*[^\n]*",
                        r"Manufacturer:\s*[^\n]*",
                        r"Address:\s*[^\n]*",
                        r"&nbsp;",
                    ]
                    for pattern in patterns_to_remove:
                        desc = re.sub(pattern, "", desc, flags=re.IGNORECASE)
                    # Clean up extra whitespace
                    desc = re.sub(r"\s+", " ", desc).strip()
                    if desc:
                        product_data["description"] = desc
                    else:
                        # If description becomes empty after cleaning, remove it
                        product_data.pop("description", None)
                
                matched_products.append(product_data)
        
        # AI-Powered Product Ranking (optional enhancement)
        # Use AI to re-rank products based on intelligent analysis
        if claude_client and len(matched_products) > 0 and len(input_actives) > 0:
            try:
                print(f"\n{'='*60}")
                print("AI-Powered Product Ranking...")
                print(f"{'='*60}")
                matched_products = await enhance_product_ranking_with_ai(
                    matched_products,
                    input_actives,
                    ingredients
                )
                print(f"  ✓ AI-enhanced ranking completed")
            except Exception as e:
                print(f"  ⚠️  Error in AI ranking (using default ranking): {e}")
        
        # Sort by: 1) match_percentage (descending - active match percentage), 2) active_match_count (descending)
        # This prioritizes products with highest active ingredient match percentage
        matched_products.sort(
            key=lambda x: (
                x.get("match_percentage", 0),  # Primary sort: active match percentage
                x.get("active_match_count", 0),  # Secondary: number of active matches
            ),
            reverse=True
        )
        
        # Limit to top 10 products
        total_matched_count = len(matched_products)
        matched_products = matched_products[:10]
        
        processing_time = time.time() - start
        
        print(f"\n{'='*60}")
        print(f"Market Research Summary (Active Ingredients Only):")
        print(f"  Input type: {input_type}")
        print(f"  Extracted ingredients: {len(ingredients)}")
        print(f"  Active ingredients to match: {len(input_actives)}")
        print(f"  Sample active ingredients: {input_actives[:5] if input_actives else 'None'}")
        print(f"  Products in database: {len(all_products)}")
        print(f"  Total products matched: {total_matched_count}")
        print(f"  Showing top 10 products: {len(matched_products)}")
        if len(matched_products) > 0:
            top_match = matched_products[0]
            print(f"  Top match: {top_match.get('productName', 'Unknown')[:50]}")
            print(f"    - Active match count: {top_match.get('active_match_count', 0)}/{len(input_actives)}")
            print(f"    - Active match percentage: {top_match.get('match_percentage', 0)}%")
            print(f"    - Matched active ingredients: {top_match.get('active_ingredients', [])[:5]}")
        else:
            print(f"  ⚠️  WARNING: No products matched with active ingredients!")
            if len(all_products) > 0:
                print(f"  Debug: Checked {len(all_products)} products but found no matches")
                print(f"  Debug: Active ingredients searched: {input_actives[:5] if input_actives else 'None'}")
                if len(input_actives) == 0:
                    print(f"  Debug: No active ingredients found in input - market research requires active ingredients")
            else:
                print(f"  Debug: No products found in database to check")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"{'='*60}\n")
        
        # Debug: Log what we're returning
        print(f"\n📤 Returning response with AI analysis:")
        print(f"  ai_analysis: {ai_analysis_message}")
        print(f"  ai_product_type: {ai_product_type}")
        print(f"  ai_reasoning: {ai_reasoning}")
        
        return MarketResearchResponse(
            products=matched_products,
            extracted_ingredients=ingredients,
            total_matched=total_matched_count,  # Show total matched, not just top 10
            processing_time=round(processing_time, 2),
            input_type=input_type,
            ai_analysis=ai_analysis_message,  # AI analysis message
            ai_product_type=ai_product_type,  # Product type identified by AI
            ai_reasoning=ai_reasoning  # AI reasoning for ingredient selection
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in market research: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to perform market research: {str(e)}"
        )
    finally:
        if scraper:
            try:
                await scraper.close()
            except:
                pass
