# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException, Form, Request, Depends, Query, BackgroundTasks
from fastapi.responses import Response
import time
import os
import json
import re
import asyncio
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

# Import authentication - JWT
from app.ai_ingredient_intelligence.auth import verify_jwt_token

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
# Import extracted logic functions
from app.ai_ingredient_intelligence.logic.analysis_core import analyze_ingredients_core
from app.ai_ingredient_intelligence.logic.category_computer import (
    fetch_and_compute_categories,
    compute_item_category
)
from app.ai_ingredient_intelligence.logic.distributor_fetcher import fetch_distributors_for_branded_ingredients
# Note: AI analysis functions are imported in market_research.py where they're used
# These functions are not used in analyze_inci.py anymore
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
    DecodeHistoryItem,  # ⬅️ full schema for decode history (detail endpoint)
    DecodeHistoryItemSummary,  # ⬅️ summary schema for decode history (list endpoint)
    SaveDecodeHistoryRequest,  # ⬅️ new schema for saving history
    GetDecodeHistoryResponse,  # ⬅️ new schema for getting history
    DecodeHistoryDetailResponse,  # ⬅️ new schema for getting history detail
    CompareHistoryItem,  # ⬅️ full schema for compare history (detail endpoint)
    CompareHistoryItemSummary,  # ⬅️ summary schema for compare history (list endpoint)
    SaveCompareHistoryRequest,  # ⬅️ new schema for saving compare history
    GetCompareHistoryResponse,  # ⬅️ new schema for getting compare history
    CompareHistoryDetailResponse,  # ⬅️ new schema for getting compare history detail
)
from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import distributor_col, decode_history_col, compare_history_col, branded_ingredients_col, inci_col
from datetime import datetime, timezone, timedelta
from bson import ObjectId


# ============================================================================
# HELPER FUNCTIONS (moved to logic/ - kept here for backward compatibility if needed)
# ============================================================================
# Note: These functions are now imported from logic modules above
# Keeping this section for any remaining helper functions that haven't been extracted yet

# Removed functions (now imported from logic modules):
# - fetch_distributors_for_branded_ingredients -> logic/distributor_fetcher.py
# - compute_item_category -> logic/category_computer.py
# - fetch_and_compute_categories -> logic/category_computer.py
# - analyze_ingredients_core -> logic/analysis_core.py
# - analyze_formulation_and_suggest_matching_with_ai -> logic/ai_analysis.py
# - analyze_product_categories_with_ai -> logic/ai_analysis.py
# - generate_market_research_overview_with_ai -> logic/ai_analysis.py
# - enhance_product_ranking_with_ai -> logic/ai_analysis.py

# ============================================================================
# ROUTER DEFINITION
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
    
    NOTE: This endpoint is PUBLIC (no authentication required) for monitoring purposes.
    """
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
    
    NOTE: This endpoint is PUBLIC (no authentication required) for monitoring purposes.
    """
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
    current_user: dict = Depends(verify_jwt_token),  # JWT token validation
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
async def extract_ingredients_from_url(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/extract-ingredients-from-url")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    if "url" in payload:
        print(f"[DEBUG] URL: {payload['url']}")
    print(f"{'='*80}\n")
    
    start = time.time()
    scraper = None
    
    try:
        # Validate payload
        if "url" not in payload:
            print(f"[DEBUG] ❌ Error: Missing required field: url")
            raise HTTPException(status_code=400, detail="Missing required field: url")
        
        url = payload["url"]
        print(f"[DEBUG] Processing URL: {url}")
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
        if "no meaningful text extracted" in error_msg.lower() or "failed to scrape url" in error_msg.lower():
            raise HTTPException(
                status_code=422,
                detail=f"Unable to extract content from the URL. The page could not be scraped successfully. "
                       f"Possible reasons: 1) The page requires JavaScript that didn't load properly, "
                       f"2) The page is blocking automated access (bot detection), 3) The page structure is different than expected, "
                       f"4) The page content is primarily images/media without text, or 5) Network/timeout issues. "
                       f"Please try a different URL or provide ingredients directly as INCI text."
            )
        elif "chrome" in error_msg.lower() or "webdriver" in error_msg.lower() or "driver" in error_msg.lower():
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


# Core analysis function that can be called directly (without HTTP/authentication)
async def analyze_ingredients_core(ingredients: List[str]) -> AnalyzeInciResponse:
    """
    Core ingredient analysis logic that can be called directly.
    This function performs the analysis without history saving or authentication.
    
    Args:
        ingredients: List of ingredient names to analyze
        
    Returns:
        AnalyzeInciResponse with analysis results
    """
    start = time.time()
    
    try:
        if not ingredients:
            raise ValueError("No ingredients provided")
        
        # OPTIMIZED: Run CAS synonyms and BIS cautions in parallel (they're independent)
        import asyncio
        print("Retrieving synonyms from CAS API and BIS cautions in parallel...")
        synonyms_task = get_synonyms_batch(ingredients)
        bis_cautions_task = get_bis_cautions_for_ingredients(ingredients)
        
        # Wait for both to complete
        synonyms_map, bis_cautions = await asyncio.gather(synonyms_task, bis_cautions_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(synonyms_map, Exception):
            print(f"Warning: Error getting synonyms: {synonyms_map}")
            synonyms_map = {}
        if isinstance(bis_cautions, Exception):
            print(f"Warning: Error getting BIS cautions: {bis_cautions}")
            bis_cautions = {}
        
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        if bis_cautions:
            print(f"[OK] Retrieved BIS cautions for {len(bis_cautions)} ingredients: {list(bis_cautions.keys())}")
        else:
            print("[WARNING] No BIS cautions retrieved - this may indicate an issue with the BIS retriever")
        
        # Match ingredients using new flow
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
    except Exception as e:
        print(f"Error in analyze_ingredients_core: {e}")
        # Show operation stack
        import traceback
        print(f"\n{'='*60}")
        print(f"OPERATION STACK in analyze_ingredients_core:")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"{'='*60}\n")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # OPTIMIZED: Run categories and distributors fetching in parallel (they're independent)
    print("Fetching ingredient categories and distributor information in parallel...")
    categories_task = fetch_and_compute_categories(items)
    distributors_task = fetch_distributors_for_branded_ingredients(items)
    
    # Wait for both to complete
    categories_result, distributor_info = await asyncio.gather(
        categories_task, 
        distributors_task, 
        return_exceptions=True
    )
    
    # Handle exceptions
    if isinstance(categories_result, Exception):
        print(f"Warning: Error fetching categories: {categories_result}")
        inci_categories, items_processed = {}, items
    else:
        inci_categories, items_processed = categories_result
    
    if isinstance(distributor_info, Exception):
        print(f"Warning: Error fetching distributors: {distributor_info}")
        distributor_info = {}
    
    print(f"Found categories for {len(inci_categories)} INCI names")
    if distributor_info:
        print(f"Found distributors for {len(distributor_info)} branded ingredients")
    else:
        print("No distributor information found")

    # 🔹 Group items by exact matched_inci (same INCI names = same group)
    # Multiple branded ingredients with the same matched_inci will be shown together
    detected_dict = defaultdict(list)
    for item in items_processed:
        # Use sorted tuple as key to group items with exact same INCI names
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
    # Sort by number of INCI: more INCI first, then by first INCI name
    detected.sort(key=lambda x: (-len(x.inci_list), x.inci_list[0].lower() if x.inci_list else ""))

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
        distributor_info=distributor_info if distributor_info else None,  # Distributor info for branded ingredients
    )
    
    return response


# ============================================================================
# BACKGROUND HISTORY SAVING FUNCTION
# ============================================================================

async def save_inci_history_background(
    user_id: Optional[str],
    payload: dict,
    analysis_result: dict,
    status: str,
    processing_time: float,
    history_id: Optional[str] = None
):
    """
    Background task to save INCI analysis history.
    Runs after response is sent to client.
    
    Args:
        user_id: User ID from JWT token
        payload: Original request payload with name, tag, notes, expected_benefits, inci_names, input_data
        analysis_result: Full analysis result dict (serialized response)
        status: "completed" or "failed"
        processing_time: Processing time in seconds
        history_id: Optional existing history_id for regeneration (UPDATE instead of INSERT)
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🔵 BACKGROUND TASK STARTED: save_inci_history_background")
    print(f"[DEBUG] Timestamp: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] User ID: {user_id}")
    print(f"[DEBUG] History ID: {history_id or 'None (will create new)'}")
    print(f"[DEBUG] Status: {status}")
    print(f"[DEBUG] Processing time: {processing_time}s")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    print(f"[DEBUG] Analysis result keys: {list(analysis_result.keys())}")
    print(f"{'='*80}\n")
    
    try:
        if not user_id:
            print(f"[DEBUG] ⚠️  Skipping save - no user_id provided")
            print(f"[HISTORY] Skipping save - no user_id")
            return
        
        # Extract input_data - prioritize explicit input_data, then parse inci_names
        print(f"[DEBUG] 📝 Extracting input_data from payload...")
        input_data = payload.get("input_data")
        if not input_data:
            print(f"[DEBUG]   No explicit input_data, parsing from inci_names...")
            inci_input = payload.get("inci_names", [])
            if isinstance(inci_input, str):
                ingredients = parse_inci_string(inci_input)
                input_data = ", ".join(ingredients) if ingredients else inci_input
                print(f"[DEBUG]   Parsed {len(ingredients)} ingredients from string")
            elif isinstance(inci_input, list):
                input_data = ", ".join(inci_input)
                print(f"[DEBUG]   Joined {len(inci_input)} ingredients from list")
            else:
                input_data = str(inci_input)
                print(f"[DEBUG]   Converted to string")
        else:
            print(f"[DEBUG]   Using explicit input_data (length: {len(input_data)} chars)")
        
        print(f"[DEBUG] ✅ Input data extracted: {input_data[:100]}{'...' if len(input_data) > 100 else ''}")
        
        # Generate display name
        print(f"[DEBUG] 📝 Generating display name...")
        name = payload.get("name")
        if name is None:
            name = ""
        elif isinstance(name, str):
            name = name.strip()
        else:
            name = str(name).strip()
        
        print(f"[DEBUG]   Name from payload: {repr(name)}")
        
        if not name:
            # Try to get name from history if history_id exists
            if history_id and ObjectId.is_valid(history_id):
                try:
                    existing_history = await decode_history_col.find_one({"_id": ObjectId(history_id)})
                    if existing_history and existing_history.get("name"):
                        name = existing_history["name"]
                        print(f"[DEBUG]   Using name from existing history: {name}")
                except Exception as e:
                    print(f"[DEBUG]   Could not fetch name from history: {e}")
            
            # If still no name, generate from first ingredient
            if not name:
                ingredients_preview = parse_inci_string(payload.get("inci_names", ""))
                if ingredients_preview:
                    first_ing = ingredients_preview[0]
                    name = first_ing + "..." if len(first_ing) > 20 else first_ing
                    print(f"[DEBUG]   Generated name from first ingredient: {name}")
                else:
                    name = "Untitled Analysis"
                    print(f"[DEBUG]   Using default name: {name}")
        else:
            print(f"[DEBUG]   ✅ Using provided name: {name}")
        
        # Truncate name if too long
        if len(name) > 100:
            name = name[:97] + "..."
            print(f"[DEBUG]   Truncated name to 100 chars")
        
        # Prepare history document
        print(f"[DEBUG] 📦 Preparing history document...")
        history_doc = {
            "user_id": user_id,
            "name": name,
            "tag": payload.get("tag"),
            "notes": payload.get("notes", ""),
            "expected_benefits": payload.get("expected_benefits"),
            "input_type": "inci",
            "input_data": input_data,
            "status": status,
            "analysis_result": analysis_result,
            "processing_time": processing_time,
            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        print(f"[DEBUG]   History doc keys: {list(history_doc.keys())}")
        print(f"[DEBUG]   Analysis result size: {len(str(analysis_result))} chars")
        print(f"[DEBUG]   Input data size: {len(input_data)} chars")
        
        # REGENERATE: Update existing history item
        if history_id and ObjectId.is_valid(history_id):
            print(f"[DEBUG] 🔄 REGENERATE MODE: Updating existing history {history_id}...")
            try:
                result = await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id},
                    {"$set": history_doc}
                )
                print(f"[DEBUG]   Update result - matched: {result.matched_count}, modified: {result.modified_count}")
                if result.matched_count > 0:
                    print(f"[DEBUG] ✅ Successfully updated existing history {history_id}")
                    print(f"[HISTORY] Updated existing history {history_id} (status: {status})")
                    print(f"{'='*80}\n")
                    return
                else:
                    print(f"[DEBUG] ⚠️  History ID {history_id} not found, will create new one")
                    print(f"[HISTORY] Warning: history_id {history_id} not found, creating new one")
            except Exception as e:
                print(f"[DEBUG] ❌ Error updating history: {e}")
                print(f"[HISTORY] Error updating history {history_id}: {e}")
                # Fall through to INSERT
        
        # NEW ANALYSIS: Insert new history item
        print(f"[DEBUG] ➕ NEW ANALYSIS MODE: Inserting new history item...")
        result = await decode_history_col.insert_one(history_doc)
        new_history_id = str(result.inserted_id)
        print(f"[DEBUG] ✅ Successfully created new history with ID: {new_history_id}")
        print(f"[HISTORY] Created new history {new_history_id} (status: {status})")
        print(f"{'='*80}\n")
        
    except Exception as e:
        # Log but don't fail - background task errors shouldn't crash
        print(f"\n{'='*80}")
        print(f"[DEBUG] ❌ BACKGROUND TASK ERROR: {type(e).__name__}: {e}")
        print(f"[HISTORY SAVE FAILED] {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")


# Simple JSON endpoint for frontend compatibility
@router.post("/analyze-inci", response_model=AnalyzeInciResponse)
async def analyze_inci(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Analyze INCI ingredients with automatic background history saving.
    
    Auto-saving behavior:
    - History is saved in background after response is returned (non-blocking)
    - If history_id is provided, updates existing history item (for regenerate)
    - If no history_id, creates new history item
    - Saving errors don't fail the analysis (graceful degradation)
    - Background task only runs when response is successfully returned
    
    Request body:
    {
        "inci_names": ["ingredient1", "ingredient2", ...] or "ingredient1, ingredient2",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "expected_benefits": "Expected benefits" (optional),
        "history_id": "existing_history_id" (optional, for regenerate)
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    import logging
    logger = logging.getLogger(__name__)
    
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/analyze-inci")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    print(f"[DEBUG] Payload size: {len(str(payload))} characters")
    if "inci_names" in payload:
        inci_preview = str(payload["inci_names"])[:200] + "..." if len(str(payload["inci_names"])) > 200 else str(payload["inci_names"])
        print(f"[DEBUG] INCI names preview: {inci_preview}")
    print(f"{'='*80}\n")
    
    # Extract user_id from JWT token (already verified by verify_jwt_token)
    user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
    print(f"[DEBUG] User ID extracted: {user_id_value}")
    
    # Validate and parse input
    if "inci_names" not in payload:
        raise HTTPException(status_code=400, detail="Missing required field: inci_names")
    
    inci_input = payload["inci_names"]
    ingredients = parse_inci_string(inci_input)
    
    if not ingredients:
        raise HTTPException(
            status_code=400, 
            detail="No valid ingredients found after parsing. Please check your input format."
        )
    
    # Validate history_id if provided (for regenerate)
    history_id = None
    provided_history_id = payload.get("history_id")
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                # Verify the history item exists and belongs to the user
                existing_history = await decode_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_history:
                    history_id = provided_history_id
                    print(f"[HISTORY] Using existing history_id for regenerate: {history_id}")
                else:
                    print(f"[HISTORY] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, will create new one")
            else:
                print(f"[HISTORY] Warning: Invalid history_id format: {provided_history_id}, will create new one")
        except Exception as e:
            print(f"[HISTORY] Warning: Error validating history_id: {e}, will create new one")
    
    # 🔹 Create history item upfront (if name/tag provided) so frontend gets history_id immediately
    # This allows frontend to track the analysis and update it later
    if user_id_value and not history_id and (payload.get("name") or payload.get("tag")):
        try:
            # Generate name if not provided
            name = payload.get("name", "").strip()
            if not name:
                if ingredients:
                    first_ing = ingredients[0]
                    name = first_ing + "..." if len(first_ing) > 20 else first_ing
                else:
                    name = "Untitled Analysis"
            
            # Truncate name if too long
            if len(name) > 100:
                name = name[:97] + "..."
            
            # Create history document with "in_progress" status
            history_doc = {
                "user_id": user_id_value,
                "name": name,
                "tag": payload.get("tag"),
                "notes": payload.get("notes", ""),
                "expected_benefits": payload.get("expected_benefits"),
                "input_type": "inci",
                "input_data": payload.get("inci_names", ""),
                "status": "in_progress",
                "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
            }
            
            result = await decode_history_col.insert_one(history_doc)
            history_id = str(result.inserted_id)
            print(f"[HISTORY] ✅ Created upfront history item: {history_id} with 'in_progress' status")
        except Exception as e:
            print(f"[HISTORY] ⚠️  Warning: Failed to create upfront history item: {e}")
            import traceback
            traceback.print_exc()
            # Continue without history_id - background task will create it
    
    # Run analysis
    try:
        print(f"\n{'='*80}")
        print(f"[DEBUG] 🚀 Starting analyze_ingredients_core for {len(ingredients)} ingredients")
        print(f"[DEBUG] Ingredients: {ingredients[:5]}{'...' if len(ingredients) > 5 else ''}")
        print(f"{'='*80}\n")
        
        response = await analyze_ingredients_core(ingredients)
        
        print(f"\n{'='*80}")
        print(f"[DEBUG] ✅ Analysis completed successfully!")
        print(f"[DEBUG] Response type: {type(response)}")
        print(f"[DEBUG] Processing time: {response.processing_time}s")
        print(f"[DEBUG] Detected groups: {len(response.detected)}")
        print(f"[DEBUG] Unable to decode: {len(response.unable_to_decode)}")
        print(f"[DEBUG] Response keys: {list(response.dict().keys())}")
        print(f"{'='*80}\n")
        
    except Exception as e:
        # Analysis failed - show error but don't save to history
        print(f"\n{'='*80}")
        print(f"[DEBUG] ❌ Error in analyze_inci: {e}")
        print(f"{'='*80}\n")
        import traceback
        print(f"\n{'='*60}")
        print(f"OPERATION STACK in analyze_inci:")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"{'='*60}\n")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    
    # ✅ SUCCESS: Response is ready, now add background task
    # Serialize response once for background task
    print(f"\n{'='*80}")
    print(f"[DEBUG] 📦 Serializing response for background task...")
    analysis_result_dict = response.dict(exclude_none=True)
    print(f"[DEBUG] Serialized response keys: {list(analysis_result_dict.keys())}")
    print(f"[DEBUG] Serialized response size: {len(str(analysis_result_dict))} characters")
    print(f"{'='*80}\n")
    
    # Add background task to save history (only runs after response is sent)
    if user_id_value:
        print(f"\n{'='*80}")
        print(f"[DEBUG] 🔄 Adding background task to save history...")
        print(f"[DEBUG] User ID: {user_id_value}")
        print(f"[DEBUG] History ID: {history_id or 'NEW (will create)'}")
        print(f"[DEBUG] Payload keys: {list(payload.keys())}")
        print(f"[DEBUG] Analysis result keys: {list(analysis_result_dict.keys())}")
        print(f"[DEBUG] Status: completed")
        print(f"[DEBUG] Processing time: {response.processing_time}s")
        print(f"{'='*80}\n")
        
        background_tasks.add_task(
            save_inci_history_background,
            user_id=user_id_value,
            payload=payload,
            analysis_result=analysis_result_dict,
            status="completed",
            processing_time=response.processing_time,
            history_id=history_id  # None for new, ID for regenerate
        )
        print(f"[HISTORY] ✅ Background task added for saving history (history_id: {history_id or 'new'})")
        print(f"[DEBUG] ⚠️  Note: Background task will execute AFTER response is sent to client")
    else:
        print(f"[DEBUG] ⚠️  No user_id_value, skipping background task")
    
    # Add history_id to response if available
    if history_id:
        # Create a new response object with history_id
        response_dict = response.dict(exclude_none=True)
        response_dict["history_id"] = history_id
        response = AnalyzeInciResponse(**response_dict)
        print(f"[HISTORY] ✅ Added history_id to response: {history_id}")
    
    # Return response immediately (background task runs after this)
    print(f"\n{'='*80}")
    print(f"[DEBUG] 📤 Returning response to client...")
    print(f"[DEBUG] Response summary:")
    print(f"  - Detected: {len(response.detected)} groups")
    print(f"  - Unable to decode: {len(response.unable_to_decode)} items")
    print(f"  - Processing time: {response.processing_time}s")
    if history_id:
        print(f"  - History ID: {history_id}")
    print(f"{'='*80}\n")
    
    return response


# URL-based ingredient analysis endpoint
@router.post("/analyze-url", response_model=AnalyzeInciResponse)
async def analyze_url(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Extract ingredients from a product URL and analyze them with automatic history saving.
    
    Auto-saving behavior:
    - If name is provided, automatically saves to decode history
    - Saves with "in_progress" status before analysis
    - Updates with "completed" status and analysis_result after analysis
    - Saving errors don't fail the analysis (graceful degradation)
    - If history_id is provided, updates existing history item instead of creating new one
    
    Request body:
    {
        "url": "https://example.com/product/...",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "expected_benefits": "Expected benefits" (optional),
        "history_id": "existing_history_id" (optional, if frontend already created history item)
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    
    The endpoint will:
    1. Scrape the URL to extract text content
    2. Use AI to extract ingredient list from the text
    3. Analyze the extracted ingredients
    4. Return the analysis results with extracted text
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/analyze-url")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    if "url" in payload:
        print(f"[DEBUG] URL: {payload['url']}")
    print(f"{'='*80}\n")
    
    start = time.time()
    scraper = None
    history_id = None
    
    # Extract user_id from JWT token (already verified by verify_jwt_token)
    user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
    print(f"[DEBUG] User ID extracted: {user_id_value}")
    name = payload.get("name", "").strip()
    tag = payload.get("tag")
    notes = payload.get("notes", "")
    expected_benefits = payload.get("expected_benefits")
    
    # 🔹 Check if history_id is provided (frontend may have already created a history item)
    provided_history_id = payload.get("history_id")
    if provided_history_id:
        # Validate the provided history_id
        try:
            if ObjectId.is_valid(provided_history_id):
                # Verify the history item exists and belongs to the user
                existing_history = await decode_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_history:
                    history_id = provided_history_id
                    print(f"[AUTO-SAVE] Using existing history_id: {history_id}")
                else:
                    print(f"[AUTO-SAVE] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, creating new one")
                    provided_history_id = None  # Reset to None so we create a new one
            else:
                print(f"[AUTO-SAVE] Warning: Invalid history_id format: {provided_history_id}, creating new one")
                provided_history_id = None
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Error validating history_id: {e}, creating new one")
            provided_history_id = None
    
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
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided and no existing history_id
        # Auto-save always happens if user_id is provided (name is optional, will use default if not provided)
        if user_id_value and not history_id:
            try:
                # 🔹 BUG FIX: Check if a history item with the same input_data (URL) already exists for this user
                # This prevents creating duplicate history items when the same analysis is run multiple times
                existing_history_item = await decode_history_col.find_one({
                    "user_id": user_id_value,
                    "input_type": "url",
                    "input_data": url
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same URL, reusing history_id: {history_id}")
                    # Update the existing item's status to "in_progress" if it was completed/failed
                    if existing_history_item.get("status") in ["completed", "failed"]:
                        await decode_history_col.update_one(
                            {"_id": existing_history_item["_id"]},
                            {"$set": {"status": "in_progress"}}
                        )
                        print(f"[AUTO-SAVE] Reset existing history item {history_id} status to 'in_progress'")
                else:
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
        
        # OPTIMIZED: Run CAS synonyms and BIS cautions in parallel (they're independent)
        import asyncio
        print("Retrieving synonyms from CAS API and BIS cautions in parallel...")
        synonyms_task = get_synonyms_batch(ingredients)
        bis_cautions_task = get_bis_cautions_for_ingredients(ingredients)
        
        # Wait for both to complete
        synonyms_map, bis_cautions = await asyncio.gather(synonyms_task, bis_cautions_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(synonyms_map, Exception):
            print(f"Warning: Error getting synonyms: {synonyms_map}")
            synonyms_map = {}
        if isinstance(bis_cautions, Exception):
            print(f"Warning: Error getting BIS cautions: {bis_cautions}")
            bis_cautions = {}
        
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        if bis_cautions:
            print(f"[OK] Retrieved BIS cautions for {len(bis_cautions)} ingredients: {list(bis_cautions.keys())}")
        else:
            print("[WARNING] No BIS cautions retrieved - this may indicate an issue with the BIS retriever")
        
        # Match ingredients using new flow
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
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

    # OPTIMIZED: Run categories and distributors fetching in parallel (they're independent)
    print("Fetching ingredient categories and distributor information in parallel...")
    categories_task = fetch_and_compute_categories(items)
    distributors_task = fetch_distributors_for_branded_ingredients(items)
    
    # Wait for both to complete
    categories_result, distributor_info = await asyncio.gather(
        categories_task, 
        distributors_task, 
        return_exceptions=True
    )
    
    # Handle exceptions
    if isinstance(categories_result, Exception):
        print(f"Warning: Error fetching categories: {categories_result}")
        inci_categories, items_processed = {}, items
    else:
        inci_categories, items_processed = categories_result
    
    if isinstance(distributor_info, Exception):
        print(f"Warning: Error fetching distributors: {distributor_info}")
        distributor_info = {}
    
    print(f"Found categories for {len(inci_categories)} INCI names")
    if distributor_info:
        print(f"Found distributors for {len(distributor_info)} branded ingredients")
    else:
        print("No distributor information found")

    # 🔹 Group items by exact matched_inci (same INCI names = same group)
    # Multiple branded ingredients with the same matched_inci will be shown together
    detected_dict = defaultdict(list)
    for item in items_processed:
        # Use sorted tuple as key to group items with exact same INCI names
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
    # Sort by number of INCI: more INCI first, then by first INCI name
    detected.sort(key=lambda x: (-len(x.inci_list), x.inci_list[0].lower() if x.inci_list else ""))

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
        distributor_info=distributor_info if distributor_info else None,  # Distributor info for branded ingredients
        history_id=history_id if history_id else None,  # Include history_id in response
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
async def get_suppliers(current_user: dict = Depends(verify_jwt_token)):  # JWT token validation
    """
    Get all valid suppliers from ingre_suppliers collection
    Returns list of supplier names (only suppliers with isValid: true)
    """
    try:
        suppliers_collection = db["ingre_suppliers"]
        # Only return valid suppliers
        cursor = suppliers_collection.find({"isValid": True}, {"supplierName": 1, "_id": 0})
        suppliers = await cursor.to_list(length=None)
        
        # Extract supplier names and sort alphabetically
        supplier_names = sorted([s.get("supplierName", "") for s in suppliers if s.get("supplierName")])
        
        return {"suppliers": supplier_names}
    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch suppliers: {str(e)}")


@router.post("/ingredients/categories")
async def get_ingredient_categories(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
    Get valid suppliers with pagination and search (only suppliers with isValid: true)
    """
    try:
        suppliers_collection = db["ingre_suppliers"]
        
        # Build query - only valid suppliers
        query = {"isValid": True}
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
async def register_distributor(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
async def verify_ingredient_id(
    ingredient_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
async def get_distributor_by_ingredient(
    ingredient_name: str,
    ingredient_id: Optional[str] = None,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
async def get_distributors_by_ingredients(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/compare-products")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    if "products" in payload:
        print(f"[DEBUG] Number of products to compare: {len(payload['products']) if isinstance(payload.get('products'), list) else 'N/A'}")
    print(f"{'='*80}\n")
    
    start = time.time()
    scraper = None
    
    try:
        # Parse products from payload
        if "products" not in payload or not payload["products"]:
            print(f"[DEBUG] ❌ Error: Missing required field: 'products' array")
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
        
        # Use the shared INCI parser utility
        from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
        
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
                # INCI input - parse directly first, then use Claude to clean if needed
                product_data["text"] = product_input
                product_data["inci"] = parse_inci_string(product_input)
                # Use Claude to clean and validate INCI list if we have a scraper
                if product_scraper and product_data["inci"]:
                    try:
                        cleaned_inci = await product_scraper.extract_ingredients_from_text(product_input)
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
        from app.config import CLAUDE_MODEL
        model_name = CLAUDE_MODEL if CLAUDE_MODEL else (os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929")
        
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
        
        # Convert to ProductComparisonItem objects
        product_items = [ProductComparisonItem(**product_data) for product_data in final_products_data]
        
        # Build response
        response_data = {
            "products": product_items,
            "processing_time": processing_time
        }
        
        return CompareProductsResponse(**response_data)
        
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
async def save_decode_history(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Create a decode history item with "in_progress" status (for frontend to track pending analyses)
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/save-decode-history")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    print(f"{'='*80}\n")
    
    """
    
    This endpoint allows the frontend to create a history item upfront before analysis starts.
    The history item will be updated later by /analyze-inci or /analyze-url endpoints when analysis completes.
    
    HISTORY FUNCTIONALITY:
    - Creates a history item with "in_progress" status
    - Returns the MongoDB ObjectId (not UUID) for use in subsequent PATCH requests
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
        "notes": "optional notes",
        "status": "in_progress" (default, can also be "completed" or "failed")
    }
    
    Returns:
    {
        "success": True,
        "id": "MongoDB ObjectId string (24 hex characters)",
        "message": "History item created successfully"
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token
        user_id_value = current_user.get("user_id") or current_user.get("_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Extract payload fields
        name = payload.get("name", "").strip()
        if not name:
            # Generate from input_data if available
            input_data = payload.get("input_data", "")
            if input_data:
                # Try to extract first ingredient or product name
                if payload.get("input_type") == "inci":
                    ingredients = parse_inci_string(input_data)
                    if ingredients:
                        first_ing = ingredients[0]
                        name = first_ing + "..." if len(first_ing) > 20 else first_ing
                    else:
                        name = "Untitled Analysis"
                else:
                    name = "Untitled Analysis"
            else:
                name = "Untitled Analysis"
        
        # Truncate name if too long
        if len(name) > 100:
            name = name[:97] + "..."
        
        # Validate required fields
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["inci", "url"]:
            raise HTTPException(status_code=400, detail="input_type must be 'inci' or 'url'")
        
        input_data = payload.get("input_data", "").strip()
        if not input_data:
            raise HTTPException(status_code=400, detail="input_data is required")
        
        # Get status (default to "in_progress" for new items)
        status = payload.get("status", "in_progress")
        if status not in ["in_progress", "completed", "failed"]:
            status = "in_progress"
        
        # Create history document
        history_doc = {
            "user_id": user_id_value,
            "name": name,
            "tag": payload.get("tag"),
            "notes": payload.get("notes", ""),
            "input_type": input_type,
            "input_data": input_data,
            "status": status,
            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        
        # Only include analysis_result if status is "completed"
        if status == "completed" and "analysis_result" in payload:
            history_doc["analysis_result"] = payload.get("analysis_result")
        
        # Insert into database
        result = await decode_history_col.insert_one(history_doc)
        history_id = str(result.inserted_id)
        
        print(f"[HISTORY] Created new decode history item: {history_id} for user {user_id_value}, name: {name}, status: {status}")
        
        return {
            "success": True,
            "id": history_id,  # Return MongoDB ObjectId (not UUID)
            "message": "History item created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create decode history: {str(e)}"
        )


@router.get("/decode-history")
async def get_decode_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get decode history with optional unified search by name or tag (user-specific)
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/decode-history")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Query params - search: {search}, limit: {limit}, skip: {skip}")
    print(f"{'='*80}\n")
    
    """
    
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
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
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
        
        # Fetch items - only get summary fields (exclude large fields)
        cursor = decode_history_col.find(
            query,
            {
                "_id": 1,
                "user_id": 1,
                "name": 1,
                "tag": 1,
                "input_type": 1,
                "input_data": 1,
                "status": 1,
                "notes": 1,
                "created_at": 1,
                "analysis_result": 1,  # Check if exists, but don't return full data
                "report_data": 1  # Check if exists, but don't return full data
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert to summary format (exclude large fields)
        summary_items = []
        for item in items:
            item_id = str(item["_id"])
            del item["_id"]
            
            # Map status for frontend: "in_progress" -> "pending", "completed" -> "analyzed"
            status_mapping = {
                "in_progress": "pending",
                "pending": "pending",  # Handle if already mapped
                "completed": "analyzed",
                "failed": "failed"
            }
            raw_status = item.get("status")
            if raw_status:
                status = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
            else:
                status = "pending"  # Default to pending if status is missing (likely in progress)
            
            # Truncate input_data for preview (max 100 chars)
            input_data = item.get("input_data", "")
            if input_data and len(input_data) > 100:
                input_data = input_data[:100] + "..."
            
            summary_item = {
                "id": item_id,
                "user_id": item.get("user_id"),
                "name": item.get("name", ""),
                "tag": item.get("tag"),
                "input_type": item.get("input_type", ""),
                "input_data": input_data,
                "status": status,
                "notes": item.get("notes"),
                "created_at": item.get("created_at"),
                "has_analysis": item.get("analysis_result") is not None and status == "analyzed",
                "has_report": item.get("report_data") is not None and status == "analyzed"
            }
            summary_items.append(summary_item)
        
        return GetDecodeHistoryResponse(
            items=[DecodeHistoryItemSummary(**item) for item in summary_items],
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


@router.get("/decode-history/{history_id}/details", response_model=DecodeHistoryDetailResponse)
async def get_decode_history_detail(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/decode-history/{history_id}/details")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"{'='*80}\n")
    """
    Get full details of a specific decode history item (includes all large fields)
    
    This endpoint returns the complete data including:
    - Full analysis_result (large Dict)
    - Full report_data (large HTML string)
    - All other fields
    
    Use this endpoint when you need to display the full analysis or report.
    The list endpoint (/decode-history) only returns summaries.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Fetch full item (including large fields)
        item = await decode_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Convert ObjectId to string
        item["id"] = str(item["_id"])
        del item["_id"]
        
        # Ensure all fields are included
        if "report_data" not in item:
            item["report_data"] = ""
        if "analysis_result" not in item:
            item["analysis_result"] = {}
        
        # Map status for frontend
        status_mapping = {
            "in_progress": "pending",
            "pending": "pending",  # Handle if already mapped
            "completed": "analyzed",
            "failed": "failed"
        }
        raw_status = item.get("status")
        if raw_status:
            item["status"] = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
        else:
            item["status"] = "pending"  # Default to pending if status is missing (likely in progress)
        
        # Ensure analysis_result and report_data are empty (not null) if status is pending or failed
        if item.get("status") in ["pending", "failed"]:
            item["analysis_result"] = {}
            item["report_data"] = ""
        
        return DecodeHistoryDetailResponse(
            item=DecodeHistoryItem(**item)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching decode history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch decode history detail: {str(e)}"
        )


# OPTIONS handler removed - CORS middleware handles this automatically

@router.patch("/decode-history/{history_id}")
async def update_decode_history(
    history_id: str,
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/decode-history/{history_id} (PATCH)")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    print(f"{'='*80}\n")
    """
    Update a decode history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating analysis results, report data, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the decode history item
    - tag: Update or add a categorization tag
    - notes: Update user notes
    - input_data: Update input data (for regeneration)
    - input_type: Update input type (for regeneration)
    - report_data: Update report data (for regeneration)
    - status: Update status (for regeneration)
    - analysis_result: Update analysis result (for regeneration)
    - expected_benefits: Update expected benefits (for regeneration)
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId - check if it's a valid MongoDB ObjectId format
        # MongoDB ObjectIds are 24-character hex strings (no dashes)
        # UUIDs have dashes and are 36 characters, so we can detect them
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        if uuid_pattern.match(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format: UUID detected. The decode history uses MongoDB ObjectIds (24 hex characters, no dashes). Please use the ObjectId returned from the backend when creating/retrieving history items. Received UUID: {history_id}"
            )
        
        if not ObjectId.is_valid(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format. Expected MongoDB ObjectId (24 hex characters), got: {history_id[:50]}"
            )
        
        # Build update document - allow all fields except user_id and created_at
        update_doc = {}
        excluded_fields = ["user_id", "created_at", "_id"]  # These should never be updated
        
        for key, value in payload.items():
            if key not in excluded_fields:
                update_doc[key] = value
        
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
async def delete_decode_history(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/decode-history/{history_id} (DELETE)")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"{'='*80}\n")
    """
    Delete a decode history item by ID (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Permanently deletes a decode history item from user's history
    - Only the owner (matching user_id) can delete their own history items
    - Deletion is permanent and cannot be undone
    - Useful for cleaning up old or unwanted history items
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
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
async def save_compare_history(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    [DISABLED] Save compare history with name and tag (user-specific)
    Supports both 2-product and multi-product comparisons
    
    ⚠️ THIS ENDPOINT IS CURRENTLY DISABLED TO PREVENT DUPLICATE SAVES ⚠️
    This endpoint returns success but does not save to prevent duplicates.
    
    HISTORY FUNCTIONALITY:
    - All product comparison operations should be automatically saved by compare endpoints
    - History is user-specific and isolated by user_id
    - Supports status tracking: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Name and tags can be used for organization and categorization
    - History items can be searched by name or tag
    - History persists across sessions and page refreshes
    - Supports both 2-product (input1/input2) and multi-product (products array) comparisons
    
    Request body (2-product format - backward compatible):
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
    
    Request body (multi-product format):
    {
        "name": "Comparison Name",
        "tag": "optional-tag",
        "products": [
            {"input": "URL or INCI", "input_type": "url" or "inci"},
            {"input": "URL or INCI", "input_type": "url" or "inci"},
            ...
        ],
        "comparison_result": {...} (optional if status is "in_progress"),
        "status": "in_progress" | "completed" | "failed" (default: "completed")
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # ⚠️ ENDPOINT DISABLED - Return success without saving to prevent duplicates
        # Extract user_id and name for logging (do minimal validation to prevent crashes)
        user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
        name = payload.get("name", "Unknown")
        
        # Log that this endpoint was called but is disabled
        print(f"⚠️ [DISABLED] /save-compare-history called for user {user_id_value}, name: {name}")
        print(f"   This endpoint is disabled to prevent duplicate saves.")
        
        # Return success response without actually saving
        # Generate a dummy ID for frontend compatibility
        import uuid
        dummy_id = str(uuid.uuid4())
        
        return {
            "success": True,
            "id": dummy_id,
            "message": "Compare history save endpoint disabled - use compare endpoints which auto-save"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in disabled save-compare-history endpoint: {e}")
        # Still return success to prevent frontend crashes
        import uuid
        return {
            "success": True,
            "id": str(uuid.uuid4()),
            "message": "Compare history save endpoint disabled - use compare endpoints which auto-save"
        }


# OPTIONS handler removed - CORS middleware handles this automatically


# OPTIONS handler removed - CORS middleware handles this automatically


@router.get("/compare-history")
async def get_compare_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
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
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
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
        
        # Fetch items - only get summary fields (exclude large fields)
        cursor = compare_history_col.find(
            query,
            {
                "_id": 1,
                "user_id": 1,
                "name": 1,
                "tag": 1,
                "input1": 1,
                "input2": 1,
                "input1_type": 1,
                "input2_type": 1,
                "products": 1,
                "status": 1,
                "notes": 1,
                "created_at": 1,
                "comparison_result": 1  # Check if exists, but don't return full data
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert to summary format (exclude large fields and normalize to products array)
        summary_items = []
        for item in items:
            item_id = str(item["_id"])
            del item["_id"]
            
            # Map status for frontend: "in_progress" -> "pending", "completed" -> "analyzed"
            status_mapping = {
                "in_progress": "pending",
                "pending": "pending",  # Handle if already mapped
                "completed": "analyzed",
                "failed": "failed"
            }
            raw_status = item.get("status")
            if raw_status:
                status = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
            else:
                status = "pending"  # Default to pending if status is missing (likely in progress)
            
            # Normalize to products array format (convert input1/input2 if present)
            products = item.get("products")
            if not products or not isinstance(products, list):
                # Convert legacy input1/input2 to products array
                products = []
                if item.get("input1") and item.get("input1_type"):
                    products.append({
                        "input": item["input1"],
                        "input_type": item["input1_type"]
                    })
                if item.get("input2") and item.get("input2_type"):
                    products.append({
                        "input": item["input2"],
                        "input_type": item["input2_type"]
                    })
            
            # Truncate products inputs for preview (max 100 chars)
            product_count = len(products) if products else 0
            truncated_products = []
            for product in products:
                if isinstance(product, dict):
                    truncated_product = product.copy()
                    if "input" in truncated_product and truncated_product["input"]:
                        input_val = truncated_product["input"]
                        if len(input_val) > 100:
                            truncated_product["input"] = input_val[:100] + "..."
                    truncated_products.append(truncated_product)
            
            summary_item = {
                "id": item_id,
                "user_id": item.get("user_id"),
                "name": item.get("name", ""),
                "tag": item.get("tag"),
                "products": truncated_products,
                "status": status,
                "notes": item.get("notes"),
                "created_at": item.get("created_at"),
                "has_comparison": item.get("comparison_result") is not None and status == "analyzed",
                "product_count": product_count
            }
            summary_items.append(summary_item)
        
        return GetCompareHistoryResponse(
            items=[CompareHistoryItemSummary(**item) for item in summary_items],
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


@router.get("/compare-history/{history_id}/details", response_model=CompareHistoryDetailResponse)
async def get_compare_history_detail(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get full details of a specific compare history item (includes all large fields)
    
    This endpoint returns the complete data including:
    - Full comparison_result (large Dict with all comparison data)
    - All other fields
    
    Use this endpoint when you need to display the full comparison results.
    The list endpoint (/compare-history) only returns summaries.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Fetch full item (including large fields)
        item = await compare_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Convert ObjectId to string
        item["id"] = str(item["_id"])
        del item["_id"]
        
        # Ensure all fields are included
        if "comparison_result" not in item:
            item["comparison_result"] = None
        
        # Normalize to products array format (convert input1/input2 if present)
        products = item.get("products")
        if not products or not isinstance(products, list):
            # Convert legacy input1/input2 to products array
            products = []
            if item.get("input1") and item.get("input1_type"):
                products.append({
                    "input": item["input1"],
                    "input_type": item["input1_type"]
                })
            if item.get("input2") and item.get("input2_type"):
                products.append({
                    "input": item["input2"],
                    "input_type": item["input2_type"]
                })
        
        # Remove legacy fields and set normalized products array
        item["products"] = products
        # Remove input1/input2 fields from response (redundant)
        item.pop("input1", None)
        item.pop("input2", None)
        item.pop("input1_type", None)
        item.pop("input2_type", None)
        
        # Map status for frontend
        status_mapping = {
            "in_progress": "pending",
            "pending": "pending",  # Handle if already mapped
            "completed": "analyzed",
            "failed": "failed"
        }
        raw_status = item.get("status")
        if raw_status:
            item["status"] = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
        else:
            item["status"] = "pending"  # Default to pending if status is missing (likely in progress)
        
        # Ensure comparison_result is None if status is pending or failed
        if item.get("status") in ["pending", "failed"]:
            item["comparison_result"] = None
        
        return CompareHistoryDetailResponse(
            item=CompareHistoryItem(**item)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching compare history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch compare history detail: {str(e)}"
        )


@router.patch("/compare-history/{history_id}")
async def update_compare_history(
    history_id: str, 
    payload: dict, 
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update a compare history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating comparison results, input data, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the compare history item
    - tag: Update or add a categorization tag
    - notes: Update user notes
    - input1: Update input1 (URL or INCI) - for 2-product comparisons (for regeneration)
    - input2: Update input2 (URL or INCI) - for 2-product comparisons (for regeneration)
    - input1_type: Update input1_type - for 2-product comparisons (for regeneration)
    - input2_type: Update input2_type - for 2-product comparisons (for regeneration)
    - products: Update products array - for multi-product comparisons (for regeneration)
    - status: Update status (for regeneration)
    - comparison_result: Update comparison result (for regeneration)
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Build update document - allow all fields except user_id and created_at
        update_doc = {}
        excluded_fields = ["user_id", "created_at", "_id"]  # These should never be updated
        
        for key, value in payload.items():
            if key not in excluded_fields:
                update_doc[key] = value
        
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
async def delete_compare_history(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Delete a compare history item by ID (user-specific)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
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



# Note: AI analysis functions have been moved to logic/ai_analysis.py
# They are imported at the top of this file.


