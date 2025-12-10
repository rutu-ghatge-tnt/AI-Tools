"""
URL Fetcher for Inspiration Boards - Wraps URLScraper to fetch product data
"""
from typing import Dict, Any, Optional, List
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
import os
import json
import re


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
            "benefits": [],
            "tags": [],
            "target_audience": [],
            "success": True,
            "message": None
        }
        
        # Try to extract additional product info from the scraped text
        extracted_text = result.get("extracted_text", "")
        
        # Extract product name - try multiple sources
        product_name = result.get("product_name")
        if not product_name and extracted_text:
            product_name = _extract_product_name_from_text(extracted_text)
        if not product_name:
            product_name = _extract_product_name_from_url(url)
        product_data["name"] = product_name or "Unknown Product"
        
        # Extract other fields from text if available
        if extracted_text:
            product_data["brand"] = _extract_brand_from_text(extracted_text)
            product_data["price"] = _extract_price_from_text(extracted_text)
            product_data["size"] = _extract_size_from_text(extracted_text)
            product_data["rating"] = _extract_rating_from_text(extracted_text)
            product_data["reviews"] = _extract_reviews_from_text(extracted_text)
            product_data["benefits"] = _extract_benefits_from_text(extracted_text)
            # Extract tags and target audience using Claude
            tags_and_audience = await _extract_tags_and_target_audience_with_claude(extracted_text, product_data.get("name", ""), product_data.get("ingredients", []))
            product_data["tags"] = tags_and_audience.get("tags", [])
            product_data["target_audience"] = tags_and_audience.get("target_audience", [])
        
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
            "benefits": [],
            "tags": [],
            "target_audience": [],
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

