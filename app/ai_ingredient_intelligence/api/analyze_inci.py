# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException, Form, Request, Header
from fastapi.responses import Response
import time
import os
import json
import re
from typing import List, Optional, Dict
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
from app.ai_ingredient_intelligence.logic.cas_api import get_synonyms_batch
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
)
from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import distributor_col, decode_history_col, compare_history_col, branded_ingredients_col, inci_col
from datetime import datetime, timezone, timedelta
from bson import ObjectId

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
        "MODEL_NAME": os.getenv("MODEL_NAME", "claude-3-opus-20240229")
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
    start = time.time()
    
    try:
        if not inci_names:
            raise HTTPException(status_code=400, detail="inci_names is required")
        
        # Parse INCI names - handles separators within each item (comma, pipe, hyphen, "and", etc.)
        ingredients = parse_inci_string(inci_names)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No valid ingredients found after parsing. Please check your input format.")
        
        extracted_text = ", ".join(ingredients)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients provided")
        
        # 🔹 Get synonyms from CAS API for better matching
        print("Retrieving synonyms from CAS API...")
        synonyms_map = await get_synonyms_batch(ingredients)
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        
        # Match ingredients using new flow:
        # 1. Direct MongoDB query (exact match)
        # 2. Fuzzy matching (spelling mistakes)
        # 3. CAS synonyms → check branded
        # 4. General INCI collection
        # 5. Unable to decode
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
        # 🔹 Get BIS cautions for all ingredients (runs in parallel with matching)
        print("Retrieving BIS cautions...")
        bis_cautions = await get_bis_cautions_for_ingredients(ingredients)
        if bis_cautions:
            print(f"[OK] Retrieved BIS cautions for {len(bis_cautions)} ingredients: {list(bis_cautions.keys())}")
        else:
            print("[WARNING] No BIS cautions retrieved - this may indicate an issue with the BIS retriever")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_inci: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Separate branded and general ingredients
    branded_items = [item for item in items if item.tag == "B"]
    general_items = [item for item in items if item.tag == "G"]

    # 🔹 Group ALL ingredients by matched_inci (for backward compatibility)
    grouped_dict = defaultdict(list)
    for item in items:
        key = tuple(sorted(item.matched_inci))
        grouped_dict[key].append(item)

    grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in grouped_dict.items()
    ]

    # 🔹 Group BRANDED ingredients by matched_inci (so multiple branded options show per INCI)
    branded_grouped_dict = defaultdict(list)
    for item in branded_items:
        key = tuple(sorted(item.matched_inci))
        branded_grouped_dict[key].append(item)

    branded_grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in branded_grouped_dict.items()
    ]

    # 🔹 Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,  # All matched ingredients (for backward compatibility)
        branded_ingredients=branded_items,  # Branded ingredients only - flat list
        branded_grouped=branded_grouped,  # Branded ingredients grouped by INCI - shows all options per INCI
        general_ingredients_list=general_items,  # General INCI ingredients only - shown at end in "Matched Ingredients" tab
        unmatched=unable_to_decode,  # For backward compatibility
        unable_to_decode=unable_to_decode,  # Ingredients that couldn't be decoded - for "Unable to Decode" tab
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
        extracted_text=extracted_text,
        input_type="text",
        bis_cautions=bis_cautions if bis_cautions else None,
        ingredient_tags=ingredient_tags  # Maps ingredient names to 'B' or 'G'
    )


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
async def analyze_inci(payload: dict):
    start = time.time()
    
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
        raise
    except Exception as e:
        print(f"Error in analyze_inci_json: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Separate branded and general ingredients
    branded_items = [item for item in items if item.tag == "B"]
    general_items = [item for item in items if item.tag == "G"]

    # 🔹 Group ALL ingredients by matched_inci (for backward compatibility)
    grouped_dict = defaultdict(list)
    for item in items:
        key = tuple(sorted(item.matched_inci))
        grouped_dict[key].append(item)

    grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in grouped_dict.items()
    ]

    # 🔹 Group BRANDED ingredients by matched_inci (so multiple branded options show per INCI)
    branded_grouped_dict = defaultdict(list)
    for item in branded_items:
        key = tuple(sorted(item.matched_inci))
        branded_grouped_dict[key].append(item)

    branded_grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in branded_grouped_dict.items()
    ]

    # 🔹 Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,  # All matched ingredients (for backward compatibility)
        branded_ingredients=branded_items,  # Branded ingredients only - flat list
        branded_grouped=branded_grouped,  # Branded ingredients grouped by INCI - shows all options per INCI
        general_ingredients_list=general_items,  # General INCI ingredients only - shown at end in "Matched Ingredients" tab
        unmatched=unable_to_decode,  # For backward compatibility
        unable_to_decode=unable_to_decode,  # Ingredients that couldn't be decoded - for "Unable to Decode" tab
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
        extracted_text=extracted_text,
        input_type="text",
        bis_cautions=bis_cautions if bis_cautions else None,
        ingredient_tags=ingredient_tags
    )


# URL-based ingredient analysis endpoint
@router.post("/analyze-url", response_model=AnalyzeInciResponse)
async def analyze_url(payload: dict):
    """
    Extract ingredients from a product URL and analyze them.
    
    Request body:
    {
        "url": "https://example.com/product/..."
    }
    
    The endpoint will:
    1. Scrape the URL to extract text content
    2. Use AI to extract ingredient list from the text
    3. Analyze the extracted ingredients
    4. Return the analysis results with extracted text
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
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise
    except Exception as e:
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

    # 🔹 Separate branded and general ingredients
    branded_items = [item for item in items if item.tag == "B"]
    general_items = [item for item in items if item.tag == "G"]

    # 🔹 Group ALL ingredients by matched_inci (for backward compatibility)
    grouped_dict = defaultdict(list)
    for item in items:
        key = tuple(sorted(item.matched_inci))
        grouped_dict[key].append(item)

    grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in grouped_dict.items()
    ]

    # 🔹 Group BRANDED ingredients by matched_inci (so multiple branded options show per INCI)
    branded_grouped_dict = defaultdict(list)
    for item in branded_items:
        key = tuple(sorted(item.matched_inci))
        branded_grouped_dict[key].append(item)

    branded_grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in branded_grouped_dict.items()
    ]

    # Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,  # All matched ingredients (for backward compatibility)
        branded_ingredients=branded_items,  # Branded ingredients only - flat list
        branded_grouped=branded_grouped,  # Branded ingredients grouped by INCI - shows all options per INCI
        general_ingredients_list=general_items,  # General INCI ingredients only - shown at end in "Matched Ingredients" tab
        unmatched=unable_to_decode,  # For backward compatibility
        unable_to_decode=unable_to_decode,  # Ingredients that couldn't be decoded - for "Unable to Decode" tab
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
        extracted_text=extracted_text,  # Full scraped text for display
        input_type="url",
        bis_cautions=bis_cautions if bis_cautions else None,
        ingredient_tags=ingredient_tags
    )


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
        model_name = CLAUDE_MODEL if CLAUDE_MODEL else "claude-3-opus-20240229"
        
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
            max_tokens=4000,
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
                    max_tokens=2000,
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
                    max_tokens=2000,
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
    
    Request body:
    {
        "name": "Product Name",
        "tag": "optional-tag",
        "input_type": "inci" or "url",
        "input_data": "ingredient list or URL",
        "analysis_result": {...}
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
        if "analysis_result" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: analysis_result")
        
        name = payload["name"]
        tag = payload.get("tag")
        input_type = payload["input_type"]
        input_data = payload["input_data"]
        analysis_result = payload["analysis_result"]
        report_data = payload.get("report_data")  # Optional report data
        
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
            "analysis_result": analysis_result,
            "report_data": report_data,  # Store report if available
            "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
        }
        
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
    Update a decode history item (e.g., add report data)
    
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
        if "report_data" in payload:
            update_doc["report_data"] = payload["report_data"]
        
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
    
    Request body:
    {
        "name": "Comparison Name",
        "tag": "optional-tag",
        "input1": "URL or INCI",
        "input2": "URL or INCI",
        "input1_type": "url" or "inci",
        "input2_type": "url" or "inci",
        "comparison_result": {...}
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
        if "comparison_result" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: comparison_result")
        
        name = payload["name"]
        tag = payload.get("tag")
        input1 = payload["input1"]
        input2 = payload["input2"]
        input1_type = payload["input1_type"]
        input2_type = payload["input2_type"]
        comparison_result = payload["comparison_result"]
        
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
            "comparison_result": comparison_result,
            "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
        }
        
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
