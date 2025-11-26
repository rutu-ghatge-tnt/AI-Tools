# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException, Form
import time
from typing import List, Optional
from collections import defaultdict

from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.logic.bis_rag import get_bis_cautions_for_ingredients
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
from app.ai_ingredient_intelligence.models.schemas import (
    AnalyzeInciRequest,
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup,   # ⬅️ new schema for grouping
    ExtractIngredientsResponse,  # ⬅️ new schema for URL extraction
)

router = APIRouter(tags=["INCI Analysis"])


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
        
        # Process text input
        ingredients = inci_names
        extracted_text = ", ".join(ingredients)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients provided")
        
        # Match ingredients using existing logic
        matched_raw, unmatched = await match_inci_names(ingredients)
        
        # 🔹 Get BIS cautions for all ingredients (runs in parallel with matching)
        print("🔍 Retrieving BIS cautions...")
        bis_cautions = await get_bis_cautions_for_ingredients(ingredients)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_inci: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Group by matched_inci (tuple key so it's hashable)
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

    # 🔹 Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,
        unmatched=unmatched,
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
        extracted_text=extracted_text,
        input_type="text",
        bis_cautions=bis_cautions if bis_cautions else None
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
        print(f"🔍 Scraping URL: {url}")
        extraction_result = await scraper.extract_ingredients_from_url(url)
        
        ingredients = extraction_result["ingredients"]
        extracted_text = extraction_result["extracted_text"]
        platform = extraction_result.get("platform", "unknown")
        
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
        
        print(f"✅ Extracted {len(ingredients)} ingredients from {platform}")
        
        # Clean up scraper
        await scraper.close()
        
        return ExtractIngredientsResponse(
            ingredients=ingredients,
            extracted_text=extracted_text,
            platform=platform,
            url=url,
            processing_time=round(time.time() - start, 3)
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
        # Validate payload format: { inci_names: ["ingredient1", "ingredient2", ...] }
        if "inci_names" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: inci_names")
        
        if not isinstance(payload["inci_names"], list):
            raise HTTPException(status_code=400, detail="inci_names must be a list of strings")
        
        ingredients = payload["inci_names"]
        extracted_text = ", ".join(ingredients)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients provided")
        
        # Match ingredients using existing logic
        matched_raw, unmatched = await match_inci_names(ingredients)
        
        # 🔹 Get BIS cautions for all ingredients (runs in parallel with matching)
        print("🔍 Retrieving BIS cautions...")
        bis_cautions = await get_bis_cautions_for_ingredients(ingredients)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_inci_json: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Group by matched_inci (tuple key so it's hashable)
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

    # 🔹 Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,
        unmatched=unmatched,
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
        extracted_text=extracted_text,
        input_type="text",
        bis_cautions=bis_cautions if bis_cautions else None
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
        print(f"🔍 Scraping URL: {url}")
        extraction_result = await scraper.extract_ingredients_from_url(url)
        
        ingredients = extraction_result["ingredients"]
        extracted_text = extraction_result["extracted_text"]
        platform = extraction_result.get("platform", "unknown")
        
        if not ingredients:
            raise HTTPException(
                status_code=404, 
                detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
            )
        
        print(f"✅ Extracted {len(ingredients)} ingredients from {platform}")
        
        # Match ingredients using existing logic
        matched_raw, unmatched = await match_inci_names(ingredients)
        
        # Get BIS cautions for all ingredients
        print("🔍 Retrieving BIS cautions...")
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

    # Group by matched_inci
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

    # Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,
        unmatched=unmatched,
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
        extracted_text=extracted_text,  # Full scraped text for display
        input_type="url",
        bis_cautions=bis_cautions if bis_cautions else None
    )
