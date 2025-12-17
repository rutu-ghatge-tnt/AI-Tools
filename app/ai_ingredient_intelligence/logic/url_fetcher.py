"""
URL Fetcher for Inspiration Boards - Wraps URLScraper to fetch product data
"""
from typing import Dict, Any, Optional, List
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
import os
import json
import re

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
        # Extract product image from result, fallback to emoji if not found
        product_image = result.get("product_image")
        if not product_image:
            product_image = "🧴"
        
        product_data = {
            "name": None,
            "brand": None,
            "url": url,
            "platform": platform,
            "price": None,
            "size": None,
            "unit": "ml",
            "category": None,
            "image": product_image,
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
            # Extract category, benefits, tags and target audience using Claude
            claude_data = await _extract_category_benefits_tags_with_claude(extracted_text, product_data.get("name", ""), product_data.get("ingredients", []))
            product_data["category"] = claude_data.get("category")
            product_data["benefits"] = claude_data.get("benefits", [])
            product_data["tags"] = claude_data.get("tags", [])
            product_data["target_audience"] = claude_data.get("target_audience", [])
        
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

