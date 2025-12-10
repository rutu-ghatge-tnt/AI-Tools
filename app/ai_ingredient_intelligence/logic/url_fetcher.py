"""
URL Fetcher for Inspiration Boards - Wraps URLScraper to fetch product data
"""
from typing import Dict, Any, Optional
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper


async def fetch_product_from_url(url: str) -> Dict[str, Any]:
    """
    Fetch product data from e-commerce URL
    
    Returns:
        Dict with product information including name, brand, price, etc.
    """
    scraper = URLScraper()
    
    try:
        # Detect platform
        platform = _detect_platform(url)
        
        # Extract ingredients and basic info
        result = await scraper.extract_ingredients_from_url(url)
        
        # Parse the result
        product_data = {
            "name": None,
            "brand": None,
            "url": url,
            "platform": platform,
            "price": None,
            "size": None,
            "unit": "ml",
            "category": None,
            "rating": None,
            "reviews": None,
            "image": "🧴",
            "ingredients": result.get("ingredients", []),
            "success": True,
            "message": None
        }
        
        # Try to extract additional product info from the scraped text
        extracted_text = result.get("extracted_text", "")
        if extracted_text:
            # Use AI or regex to extract name, brand, price from text
            # For now, we'll set basic info
            product_data["name"] = result.get("product_name") or "Unknown Product"
            product_data["brand"] = _extract_brand_from_text(extracted_text)
            product_data["price"] = _extract_price_from_text(extracted_text)
            product_data["size"] = _extract_size_from_text(extracted_text)
            product_data["rating"] = _extract_rating_from_text(extracted_text)
            product_data["reviews"] = _extract_reviews_from_text(extracted_text)
        
        return product_data
        
    except Exception as e:
        return {
            "name": None,
            "brand": None,
            "url": url,
            "platform": _detect_platform(url),
            "price": None,
            "size": None,
            "unit": "ml",
            "category": None,
            "rating": None,
            "reviews": None,
            "image": "🧴",
            "ingredients": [],
            "success": False,
            "message": f"Failed to fetch product: {str(e)}"
        }
    finally:
        try:
            if hasattr(scraper, 'close') and callable(scraper.close):
                await scraper.close()
        except:
            pass


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


def _extract_brand_from_text(text: str) -> Optional[str]:
    """Extract brand name from text (basic implementation)"""
    # This is a placeholder - can be enhanced with AI or better parsing
    import re
    # Look for common brand patterns
    patterns = [
        r'Brand[:\s]+([A-Z][a-zA-Z\s&]+)',
        r'by\s+([A-Z][a-zA-Z\s&]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


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

