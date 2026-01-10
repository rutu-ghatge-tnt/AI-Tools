"""
URL Fetcher for Inspiration Boards - Wraps URLScraper to fetch product data
Enhanced with 30-day system-wide caching to reduce scraping costs.
"""
from typing import Dict, Any, Optional, List
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
from app.ai_ingredient_intelligence.logic.url_cache_manager import (
    get_cached_url_data, cache_url_data, invalidate_cache_for_url, is_url_cached
)
import os
import json
import re
from datetime import datetime

# Claude API setup
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


async def fetch_product_from_url(url: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch product data from e-commerce URL with 30-day caching support.
    
    Args:
        url: E-commerce product URL
        force_refresh: If True, bypass cache and scrape fresh data
        
    Returns:
        Dict with product information including name, brand, price, etc.
    """
    # Check cache first (unless force refresh)
    if not force_refresh:
        cached_data = await get_cached_url_data(url)
        if cached_data:
            return cached_data
    
    # Cache miss or force refresh - scrape normally
    print(f"🔄 {'Force refreshing' if force_refresh else 'Cache miss for'} {url} - scraping...")
    
    scraper = URLScraper()
    
    try:
        # Detect platform
        platform = _detect_platform(url)
        
        # Extract ingredients and basic info
        result = await scraper.extract_ingredients_from_url(url)
        
        # Get extracted text for parsing product details
        extracted_text = result.get("extracted_text", "")
        ingredients = result.get("ingredients", [])
        
        # Debug logging
        print(f"📊 Extraction results: {len(ingredients)} ingredients, {len(extracted_text)} chars of text")
        
        # If no extracted text, this is a problem - log it
        if not extracted_text or len(extracted_text.strip()) < 10:
            print(f"⚠️ Warning: Very little or no text extracted from {url}")
            print(f"   Extracted text length: {len(extracted_text) if extracted_text else 0}")
            print(f"   Ingredients found: {len(ingredients) if ingredients else 0}")
        
        # Extract product image from result, fallback to emoji if not found
        product_image = result.get("product_image")
        if not product_image:
            product_image = "🧴"
        
        # Extract product name - prioritize from result, fallback to text extraction
        product_name = result.get("product_name")
        if not product_name or product_name == "Unknown Product":
            product_name = _extract_product_name_from_text(extracted_text)
        if not product_name:
            product_name = _extract_product_name_from_url(url)
        if not product_name:
            product_name = "Unknown Product"
        
        # Extract brand - try multiple sources
        try:
            brand_from_url = _extract_brand_from_url(url)
            brand_from_text = _extract_brand_from_text(extracted_text)
            brand = await _validate_brand_name(brand_from_url, brand_from_text, extracted_text, product_name)
            if not brand:
                brand = brand_from_url or brand_from_text or "Unknown Brand"
        except Exception as e:
            print(f"⚠️ Warning: Failed to extract brand: {e}")
            brand = "Unknown Brand"
        
        # Extract price
        price = _extract_price_from_text(extracted_text)
        if price is None:
            price = 0.0
        
        # Extract size and unit
        size = _extract_size_from_text(extracted_text)
        if size is None:
            size = 0.0
        # Try to extract unit from text
        unit = "ml"  # default
        if extracted_text:
            unit_match = re.search(r'(\d+(?:\.\d+)?)\s*(ml|gm|g|kg|l)', extracted_text, re.IGNORECASE)
            if unit_match:
                unit = unit_match.group(2).lower()
                if unit == "g":
                    unit = "gm"
        
        # Extract category, benefits, tags, and target_audience using Claude
        # Wrap in try/except to ensure we still return data even if this fails
        try:
            category_data = await _extract_category_benefits_tags_with_claude(
                extracted_text, product_name, ingredients
            )
            category = category_data.get("category")
            benefits = category_data.get("benefits", [])
            tags = category_data.get("tags", [])
            target_audience = category_data.get("target_audience", [])
        except Exception as e:
            print(f"⚠️ Warning: Failed to extract category/benefits/tags with Claude: {e}")
            # Fallback: try to extract benefits from text directly
            category = _extract_category_from_text(extracted_text, product_name)
            benefits = _extract_benefits_from_text(extracted_text)
            tags = []
            target_audience = []
        
        # Build standardized response
        response_data = {
            "name": product_name,
            "brand": brand,
            "url": url,
            "platform": platform,
            "price": price,
            "size": size,
            "unit": unit,
            "category": category,
            "image": product_image,
            "ingredients": ingredients,
            "benefits": benefits,
            "tags": tags,
            "target_audience": target_audience,
            "extracted_text": extracted_text,  # Store extracted_text for other features
            "product_name": product_name,  # Store product_name for compatibility
            "product_image": product_image,  # Store product_image for compatibility
            "is_estimated": result.get("is_estimated", False),
            "source": result.get("source", "url_extraction"),
            "success": True,
            "message": None,
            "scraped_at": datetime.utcnow().isoformat(),
            "from_cache": False
        }
        
        # Store in cache for future use (only if scraping was successful)
        # Check if we have ingredients OR if we successfully extracted product details
        has_ingredients = ingredients and len(ingredients) > 0
        has_product_data = product_name and product_name != "Unknown Product"
        
        if has_ingredients or has_product_data:
            await cache_url_data(url, response_data)
            print(f"💾 Cached {url} for 30 days ({len(ingredients)} ingredients, product: {product_name[:50]})")
        else:
            print(f"⚠️ No ingredients or product data extracted for {url}, not caching")
        
        return response_data
        
    except Exception as e:
        error_message = f"Failed to fetch product from {url}: {str(e)}"
        print(f"❌ {error_message}")
        
        return {
            "name": None,
            "brand": None,
            "url": url,
            "platform": _detect_platform(url),
            "price": None,
            "size": None,
            "unit": None,
            "category": None,
            "image": "🧴",
            "ingredients": [],
            "benefits": [],
            "tags": [],
            "target_audience": [],
            "success": False,
            "message": error_message,
            "from_cache": False
        }


# ============================================================================
# CACHED INGREDIENT EXTRACTION FUNCTION
# ============================================================================

async def extract_ingredients_from_url_cached(url: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Extract ingredients from URL with caching support.
    This function provides the same interface as URLScraper.extract_ingredients_from_url()
    but uses the URL cache to avoid redundant scraping.
    
    Args:
        url: E-commerce product URL
        force_refresh: If True, bypass cache and scrape fresh data
        
    Returns:
        Dict with 'ingredients' (List[str]), 'extracted_text' (str), 'platform' (str),
        'is_estimated' (bool), 'source' (str), 'product_name' (str), 'product_image' (str)
    """
    # Check cache first (unless force refresh)
    if not force_refresh:
        cached_data = await get_cached_url_data(url)
        if cached_data:
            # Convert cached product data to extraction result format
            print(f"✅ Using cached data for ingredient extraction: {url}")
            return {
                "ingredients": cached_data.get("ingredients", []),
                "extracted_text": cached_data.get("extracted_text", ""),
                "platform": cached_data.get("platform", "unknown"),
                "url": url,
                "is_estimated": cached_data.get("is_estimated", False),
                "source": cached_data.get("source", "url_extraction"),
                "product_name": cached_data.get("product_name") or cached_data.get("name"),
                "product_image": cached_data.get("product_image") or cached_data.get("image", "🧴")
            }
    
    # Cache miss or force refresh - scrape normally
    print(f"🔄 {'Force refreshing' if force_refresh else 'Cache miss for'} ingredient extraction: {url} - scraping...")
    
    scraper = URLScraper()
    
    try:
        # Extract ingredients and basic info
        result = await scraper.extract_ingredients_from_url(url)
        
        # Cache the result for future use
        # Convert extraction result to cacheable format
        extracted_text = result.get("extracted_text", "")
        ingredients = result.get("ingredients", [])
        product_name = result.get("product_name")
        product_image = result.get("product_image", "🧴")
        platform = result.get("platform", _detect_platform(url))
        
        # Check if we should cache this result
        has_ingredients = ingredients and len(ingredients) > 0
        has_product_data = product_name and product_name != "Unknown Product"
        
        if has_ingredients or has_product_data:
            # Create cacheable data structure
            cache_data = {
                "name": product_name or "Unknown Product",
                "brand": "Unknown Brand",  # Will be extracted if needed
                "url": url,
                "platform": platform,
                "price": 0.0,
                "size": 0.0,
                "unit": "ml",
                "category": None,
                "image": product_image,
                "ingredients": ingredients,
                "benefits": [],
                "tags": [],
                "target_audience": [],
                "extracted_text": extracted_text,
                "product_name": product_name,
                "product_image": product_image,
                "is_estimated": result.get("is_estimated", False),
                "source": result.get("source", "url_extraction"),
                "success": True,
                "message": None,
                "scraped_at": datetime.utcnow().isoformat(),
                "from_cache": False
            }
            
            await cache_url_data(url, cache_data)
            print(f"💾 Cached extraction result for {url} ({len(ingredients)} ingredients)")
        
        return result
        
    except Exception as e:
        error_message = f"Failed to extract ingredients from {url}: {str(e)}"
        print(f"❌ {error_message}")
        
        # Return error format matching URLScraper.extract_ingredients_from_url()
        return {
            "ingredients": [],
            "extracted_text": f"Error: {error_message}",
            "platform": _detect_platform(url),
            "url": url,
            "is_estimated": False,
            "source": "error",
            "product_name": None,
            "product_image": "🧴"
        }


# ============================================================================
# CACHE MANAGEMENT HELPER FUNCTIONS
# ============================================================================

async def check_url_cache_status(url: str) -> Dict[str, Any]:
    """
    Check if URL is cached and return cache information.
    
    Args:
        url: URL to check
        
    Returns:
        Dict with cache status information
    """
    is_cached = await is_url_cached(url)
    
    return {
        "url": url,
        "is_cached": is_cached,
        "cache_ttl_days": 30,
        "message": "URL is cached and valid" if is_cached else "URL not in cache or expired"
    }


async def refresh_url_cache(url: str) -> Dict[str, Any]:
    """
    Force refresh cache for a specific URL.
    
    Args:
        url: URL to refresh
        
    Returns:
        Result of refresh operation
    """
    # Invalidate existing cache
    invalidated = await invalidate_cache_for_url(url)
    
    # Fetch fresh data
    fresh_data = await fetch_product_from_url(url, force_refresh=True)
    
    return {
        "url": url,
        "cache_invalidated": invalidated,
        "refresh_success": fresh_data.get("success", False),
        "product_data": fresh_data if fresh_data.get("success", False) else None,
        "message": "Cache refreshed successfully" if fresh_data.get("success", False) else "Failed to refresh cache"
    }


# ============================================================================
# EXISTING HELPER FUNCTIONS (unchanged)
# ============================================================================

def _detect_platform(url: str) -> str:
    """Detect e-commerce platform from URL"""
    url_lower = url.lower()
    if "nykaa" in url_lower:
        return "nykaa"
    elif "amazon" in url_lower:
        return "amazon"
    elif "flipkart" in url_lower:
        return "flipkart"
    elif "purplle" in url_lower:
        return "purplle"
    else:
        return "other"


# The rest of the existing helper functions continue below...
# (All existing _extract_* functions remain unchanged)


def _extract_product_name_from_text(text: str) -> Optional[str]:
    """Extract product name from scraped text"""
    import re
    # Look for "Product Name: {name}" pattern
    patterns = [
        r'Product Name:\s*([^\n]+)',
        r'Product Name:\s*(.+?)(?:\n|Price:|Brand:|Ratings:)',
        r'Page Title:\s*([^\n|]+)',  # Sometimes page title has product name
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            name = match.group(1).strip()
            # Clean up common suffixes
            name = re.sub(r'\s*-\s*Nykaa.*$', '', name, flags=re.IGNORECASE)
            name = re.sub(r'\s*\|\s*.*$', '', name)
            if name and len(name) > 3 and len(name) < 200:
                return name
    
    # Try to extract from page title if available
    title_match = re.search(r'Page Title:\s*([^\n]+)', text, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
        # Remove common e-commerce suffixes
        title = re.sub(r'\s*-\s*(Nykaa|Amazon|Flipkart|Purplle).*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*\|\s*.*$', '', title)
        if title and len(title) > 3 and len(title) < 200:
            return title
    
    return None


def _extract_brand_from_url(url: str) -> Optional[str]:
    """Extract brand name from URL"""
    import re
    from urllib.parse import unquote, urlparse
    
    try:
        # Decode URL encoding
        url = unquote(url)
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # For Nykaa: /brand-name/product-name/p/ID
        # Pattern: /brand-name/ or /brand-name/product-name/
        nykaa_match = re.search(r'/([^/]+)/(?:[^/]+/)?p/\d+', path)
        if nykaa_match:
            brand_candidate = nykaa_match.group(1)
            # Clean up brand name
            brand_candidate = brand_candidate.replace('-', ' ').title()
            # Filter out common non-brand segments
            excluded = {'product', 'products', 'search', 'category', 'brand', 'brands', 'shop', 'buy'}
            if brand_candidate.lower() not in excluded and len(brand_candidate) > 2:
                return brand_candidate
        
        # For Amazon: /brand-name/dp/ or /dp/PRODUCT_ID (brand might be in product name)
        # For Flipkart: /brand-name/product-name/p/ITEM_ID
        # Generic: look for brand-like segments in path
        path_segments = [s for s in path.split('/') if s and s not in ['', 'p', 'dp', 'gp', 'product']]
        if path_segments:
            # First meaningful segment might be brand
            for segment in path_segments[:2]:  # Check first 2 segments
                segment = segment.replace('-', ' ').replace('_', ' ')
                # Check if it looks like a brand (has letters, reasonable length)
                if re.search(r'[a-zA-Z]{3,}', segment) and len(segment) > 2 and len(segment) < 50:
                    return segment.title()
    except:
        pass
    
    return None


def _extract_brand_from_text(text: str) -> Optional[str]:
    """Extract brand name from text"""
    import re
    
    # Common non-brand words to filter out
    excluded_words = {
        'the', 'and', 'buy', 'online', 'since', 'from', 'with', 'for', 'by', 
        'product', 'price', 'rating', 'reviews', 'description', 'ingredients',
        'benefits', 'features', 'specifications', 'details', 'about', 'shop',
        'store', 'official', 'website', 'home', 'page', 'view', 'add', 'cart'
    }
    
    # Look for common brand patterns - improved to catch more cases
    patterns = [
        r'Brand[:\s]+([A-Z][a-zA-Z\s&]+?)(?:\n|$|Price:|Product Name:)',
        r'Brand[:\s]+([^\n]+)',
        r'by\s+([A-Z][a-zA-Z\s&]+?)(?:\s|$|\n|Price:)',
        # Try to extract from product name (usually first word)
        r'Product Name:\s*([A-Z][a-zA-Z]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            brand = match.group(1).strip()
            # Clean up - remove common suffixes and extra words
            brand = re.sub(r'\s+.*$', '', brand)  # Take only first word if multiple
            # Filter out excluded words
            if brand and brand.lower() not in excluded_words and len(brand) > 2 and len(brand) < 50:
                return brand
    
    # Fallback: try to extract from page title (first word is often brand)
    title_match = re.search(r'Page Title:\s*([^\n|]+)', text, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
        # Extract first meaningful word (skip articles, common words)
        words = title.split()
        for word in words:
            word = re.sub(r'[^\w]', '', word)
            if (word and len(word) > 2 and word[0].isupper() and 
                word.lower() not in excluded_words):
                return word
    
    return None


async def _validate_brand_name(
    brand_from_url: Optional[str], 
    brand_from_text: Optional[str], 
    extracted_text: str,
    product_name: Optional[str]
) -> Optional[str]:
    """
    Validate and determine the correct brand name using AI knowledge
    Prioritizes brand from URL, validates with scraped data
    """
    if not claude_client:
        # If Claude not available, return the best match
        return brand_from_url or brand_from_text
    
    try:
        # Prepare prompt for brand validation
        brand_candidates = []
        if brand_from_url:
            brand_candidates.append(f"From URL: {brand_from_url}")
        if brand_from_text:
            brand_candidates.append(f"From scraped text: {brand_from_text}")
        
        if not brand_candidates:
            return None
        
        text_snippet = extracted_text[:2000] if len(extracted_text) > 2000 else extracted_text
        
        prompt = f"""You are analyzing an e-commerce product page to determine the correct brand name.

Product Name: {product_name or "Unknown"}

Brand candidates found:
{chr(10).join(brand_candidates)}

Scraped text snippet:
{text_snippet}

Your task:
1. Determine the correct brand name from the candidates provided
2. If brand from URL matches brand from text, use that
3. If they differ, choose the one that appears more consistently in the scraped text
4. If neither is clear, infer the brand from the product name (usually the first word)
5. Return ONLY the brand name as a plain text string (no quotes, no explanation)
6. If you cannot determine a brand, return "null"

Brand name:"""

        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=100,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        
        brand = response.content[0].text.strip()
        
        # Clean up response
        if brand.lower() in ["null", "none", "n/a", ""]:
            # Fallback to best candidate
            return brand_from_url or brand_from_text
        
        # Remove quotes if present
        brand = brand.strip('"\'')
        
        return brand if brand else (brand_from_url or brand_from_text)
        
    except Exception as e:
        print(f"Error validating brand name with AI: {e}")
        # Fallback to best candidate
        return brand_from_url or brand_from_text


def _extract_price_from_text(text: str) -> Optional[float]:
    """Extract price from text"""
    import re
    # Look for ₹ symbol followed by numbers
    patterns = [
        r'₹\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        r'Rs\.?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        r'INR\s*(\d+(?:,\d+)*(?:\.\d+)?)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            # Get the first match and clean it
            price_str = matches[0].replace(',', '')
            try:
                return float(price_str)
            except:
                pass
    return None


def _extract_size_from_text(text: str) -> Optional[float]:
    """Extract size from text"""
    import re
    # Look for size patterns like "30ml", "50gm", etc.
    pattern = r'(\d+(?:\.\d+)?)\s*(ml|gm|g|kg|l)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except:
            pass
    return None


def _extract_rating_from_text(text: str) -> Optional[float]:
    """Extract rating from text"""
    import re
    # Look for rating patterns like "4.3", "4.5 stars", etc.
    pattern = r'(\d+\.?\d*)\s*(?:stars?|rating)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            rating = float(match.group(1))
            if 0 <= rating <= 5:
                return rating
        except:
            pass
    return None


def _extract_reviews_from_text(text: str) -> Optional[int]:
    """Extract review count from text"""
    import re
    # Look for review patterns like "12500 reviews", "12.5K reviews", etc.
    patterns = [
        r'(\d+(?:,\d+)*)\s*reviews?',
        r'(\d+\.?\d*)\s*[Kk]\s*reviews?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                count_str = match.group(1).replace(',', '')
                count = float(count_str)
                # If it's in K format, multiply
                if 'k' in text.lower() and count < 1000:
                    count = count * 1000
                return int(count)
            except:
                pass
    return None


def _extract_product_name_from_url(url: str) -> Optional[str]:
    """Extract product name from URL as fallback"""
    import re
    from urllib.parse import unquote
    
    try:
        # Decode URL encoding
        url = unquote(url)
        
        # For Nykaa: /product-name/p/ID
        nykaa_match = re.search(r'/([^/]+)/p/\d+', url)
        if nykaa_match:
            name = nykaa_match.group(1).replace('-', ' ').title()
            if name and len(name) > 3:
                return name
        
        # For Amazon: /dp/PRODUCT_ID or /product-name/dp/PRODUCT_ID
        amazon_match = re.search(r'/([^/]+)/dp/', url) or re.search(r'/([^/]+)/gp/product/', url)
        if amazon_match:
            name = amazon_match.group(1).replace('-', ' ').title()
            if name and len(name) > 3:
                return name
        
        # For Flipkart: /product-name/p/ITEM_ID
        flipkart_match = re.search(r'/([^/]+)/p/', url)
        if flipkart_match:
            name = flipkart_match.group(1).replace('-', ' ').title()
            if name and len(name) > 3:
                return name
        
        # Generic: try to find product-like segments
        segments = url.split('/')
        for segment in reversed(segments):
            segment = segment.split('?')[0]  # Remove query params
            segment = segment.replace('-', ' ').replace('_', ' ')
            if segment and len(segment) > 5 and len(segment) < 100:
                # Check if it looks like a product name (has letters, not just numbers/IDs)
                if re.search(r'[a-zA-Z]{3,}', segment):
                    return segment.title()
    except:
        pass
    
    return None


def _extract_benefits_from_text(text: str) -> list:
    """Extract product benefits from scraped text"""
    import re
    
    benefits = []
    
    # Look for benefits in Description section
    desc_match = re.search(r'Description:\s*(.+?)(?:\n\n|Ingredients:|$)', text, re.IGNORECASE | re.DOTALL)
    if desc_match:
        desc_text = desc_match.group(1)
        # Extract bullet points and sentences that mention benefits
        # Common benefit keywords
        benefit_keywords = [
            r'hydrat(?:es?|ing|ion)',
            r'brighten(?:s?|ing)',
            r'glow(?:ing|y)?',
            r'anti.?age(?:ing)?',
            r'wrinkle(?:s?|.?free)',
            r'smooth(?:es?|ing)',
            r'soft(?:ens?|ening)',
            r'clear(?:s?|ing)',
            r'even(?:s?|ing).*tone',
            r'dark.?spot(?:s?|.?fading)',
            r'pore(?:s?|.?minimiz(?:ing|es?))',
            r'acne(?:.?control|.?treatment)',
            r'exfoliat(?:es?|ing)',
            r'protect(?:s?|ion|ive)',
            r'repair(?:s?|ing)',
            r'calm(?:s?|ing)',
            r'sooth(?:es?|ing)',
            r'reduce(?:s?|ing)',
            r'improve(?:s?|ing)',
            r'enhance(?:s?|ing)',
            r'boost(?:s?|ing)',
            r'strengthen(?:s?|ing)',
            r'firm(?:s?|ing)',
            r'plump(?:s?|ing)',
            r'radiant',
            r'healthy',
            r'vitamin(?:s?|.?rich)',
            r'antioxidant',
            r'anti.?inflammatory',
        ]
        
        # Extract sentences with benefit keywords
        sentences = re.split(r'[.!?]\s+', desc_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10 and len(sentence) < 200:
                # Check if sentence contains benefit keywords
                for keyword in benefit_keywords:
                    if re.search(keyword, sentence, re.IGNORECASE):
                        # Clean up the sentence
                        benefit = re.sub(r'^[•\-\*]\s*', '', sentence)  # Remove bullet points
                        benefit = benefit.strip()
                        if benefit and benefit not in benefits:
                            benefits.append(benefit)
                            break
        
        # Also extract from bullet points
        bullets = re.findall(r'[•\-\*]\s*([^\n]+)', desc_text)
        for bullet in bullets:
            bullet = bullet.strip()
            if len(bullet) > 5 and len(bullet) < 150:
                # Check if it's a benefit statement
                for keyword in benefit_keywords:
                    if re.search(keyword, bullet, re.IGNORECASE):
                        if bullet not in benefits:
                            benefits.append(bullet)
                            break
    
    # Look for explicit "Benefits:" or "Key Benefits:" sections
    benefits_section = re.search(r'(?:Key\s+)?Benefits?[:\s]+(.+?)(?:\n\n|Ingredients:|Description:|$)', text, re.IGNORECASE | re.DOTALL)
    if benefits_section:
        benefits_text = benefits_section.group(1)
        # Extract list items
        items = re.findall(r'[•\-\*]\s*([^\n]+)', benefits_text)
        for item in items:
            item = item.strip()
            if item and len(item) > 5 and item not in benefits:
                benefits.append(item)
    
    # Limit to top 10 benefits to avoid clutter
    return benefits[:10]


async def _extract_category_benefits_tags_with_claude(
    extracted_text: str,
    product_name: str,
    ingredients: List[str]
) -> Dict[str, Any]:
    """
    Extract product category, benefits, tags and target audience using Claude AI
    
    Args:
        extracted_text: Scraped product text
        product_name: Product name
        ingredients: List of ingredient names
        
    Returns:
        Dict with 'category', 'benefits', 'tags' and 'target_audience'
    """
    if not claude_client:
        # Return defaults if Claude is not available
        return {
            "category": "Unknown",
            "benefits": [],
            "tags": [],
            "target_audience": []
        }
    
    try:
        # Get available tags for reference
        from app.ai_ingredient_intelligence.logic.product_tags import get_all_tags
        tags_data = await get_all_tags()
        
        # Build list of all valid tags
        all_valid_tags = []
        for category in tags_data:
            for tag_item in category.get("tags", []):
                all_valid_tags.append(tag_item["tag"])
        
        # Common product categories
        common_categories = [
            "Moisturizer", "Serum", "Cleanser", "Toner", "Sunscreen", "Face Mask",
            "Eye Cream", "Face Oil", "Exfoliant", "Treatment", "Essence", "Ampoule",
            "Shampoo", "Conditioner", "Hair Mask", "Hair Oil", "Hair Serum",
            "Body Lotion", "Body Wash", "Body Scrub", "Hand Cream", "Lip Balm",
            "Foundation", "Concealer", "BB Cream", "CC Cream", "Primer", "Setting Spray"
        ]
        
        # Prepare prompt for Claude
        ingredients_text = ", ".join(ingredients[:20]) if ingredients else "Not available"
        text_snippet = extracted_text[:4000] if len(extracted_text) > 4000 else extracted_text
        
        system_prompt = """You are an expert at analyzing cosmetic and skincare products. 
Your task is to extract comprehensive product information including category, benefits, tags, and target audience.

Return your response as a JSON object with these fields:
- "category": string - Product category (e.g., "Moisturizer", "Serum", "Cleanser", "Shampoo", etc.). Must be a valid category name.
- "benefits": array of strings - Key product benefits (e.g., "Hydrates skin", "Reduces fine lines", "Brightens complexion"). Extract 3-8 specific benefits.
- "tags": array of tag strings - Must be from the provided valid tags list
- "target_audience": array of strings - Who this product is for (e.g., "oily skin", "mature skin", "sensitive skin", "acne-prone", "dry hair", etc.)

IMPORTANT: 
- Category must NOT be null or empty - choose the most appropriate category from common categories or infer from product description
- Benefits must NOT be empty - extract at least 3-5 specific benefits from the product description
- Only use tags from the valid tags list provided. Do not invent new tags."""

        user_prompt = f"""Analyze this product and extract category, benefits, tags, and target audience:

Product Name: {product_name}

Ingredients: {ingredients_text}

Product Description:
{text_snippet}

Common Categories: {', '.join(common_categories)}

Valid Tags (choose from these):
{', '.join(all_valid_tags[:100])}

Return JSON with "category" (string, required), "benefits" (array, at least 3 items), "tags" (array), and "target_audience" (array)."""

        # Call Claude API
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=2048,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return {
                "category": "Unknown",
                "benefits": [],
                "tags": [],
                "target_audience": []
            }
        
        content = response.content[0].text.strip()
        
        # Try to parse JSON from response
        try:
            # Extract JSON from response (might have markdown code blocks)
            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()
            elif '```' in content:
                json_start = content.find('```') + 3
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()
            elif '{' in content and '}' in content:
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                content = content[json_start:json_end]
            
            result = json.loads(content)
            
            # Extract and validate category
            category = result.get("category", "Unknown")
            if not category or category.strip() == "":
                category = "Unknown"
            
            # Extract and validate benefits
            benefits = result.get("benefits", [])
            if not isinstance(benefits, list):
                benefits = []
            # Ensure at least some benefits are extracted
            if len(benefits) == 0:
                # Fallback: try to extract from text using regex
                benefits = _extract_benefits_from_text(extracted_text)
            
            # Validate tags against valid list
            valid_tags = []
            if "tags" in result and isinstance(result["tags"], list):
                for tag in result["tags"]:
                    if tag in all_valid_tags:
                        valid_tags.append(tag)
            
            target_audience = result.get("target_audience", [])
            if not isinstance(target_audience, list):
                target_audience = []
            
            return {
                "category": category.strip(),
                "benefits": benefits[:10],  # Limit to 10 benefits
                "tags": valid_tags,
                "target_audience": target_audience
            }
        except json.JSONDecodeError as e:
            print(f"Failed to parse Claude response as JSON: {e}")
            print(f"Response content: {content[:500]}")
            # Fallback: try to extract category and benefits from text
            category = _extract_category_from_text(extracted_text, product_name)
            benefits = _extract_benefits_from_text(extracted_text)
            return {
                "category": category,
                "benefits": benefits,
                "tags": [],
                "target_audience": []
            }
            
    except Exception as e:
        print(f"Error calling Claude for product extraction: {e}")
        # Fallback: try to extract category and benefits from text
        category = _extract_category_from_text(extracted_text, product_name)
        benefits = _extract_benefits_from_text(extracted_text)
        return {
            "category": category,
            "benefits": benefits,
            "tags": [],
            "target_audience": []
        }


def _extract_category_from_text(text: str, product_name: str) -> str:
    """Extract product category from text as fallback"""
    import re
    
    # Common category keywords
    category_keywords = {
        "moisturizer": ["moisturizer", "moisturising", "moisturizing", "cream", "lotion"],
        "serum": ["serum", "concentrate", "ampoule"],
        "cleanser": ["cleanser", "face wash", "cleansing", "wash"],
        "toner": ["toner", "astringent"],
        "sunscreen": ["sunscreen", "sunblock", "spf", "sun protection"],
        "face mask": ["mask", "face mask", "sheet mask"],
        "eye cream": ["eye cream", "eye care", "under eye"],
        "face oil": ["face oil", "facial oil", "oil"],
        "exfoliant": ["exfoliant", "scrub", "peel"],
        "shampoo": ["shampoo"],
        "conditioner": ["conditioner"],
        "hair mask": ["hair mask", "hair treatment"],
        "hair oil": ["hair oil", "hair serum"],
        "body lotion": ["body lotion", "body cream"],
        "body wash": ["body wash", "shower gel"],
        "lip balm": ["lip balm", "lip care"]
    }
    
    # Check product name first
    name_lower = product_name.lower()
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in name_lower:
                return category.title()
    
    # Check text
    text_lower = text.lower()
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category.title()
    
    return "Unknown"

