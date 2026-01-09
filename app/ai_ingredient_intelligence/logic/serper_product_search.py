"""
Serper Product Search Module
============================

Fetches product links from multiple e-commerce platforms using Serper.dev API.
Handles platform normalization, deduplication, and logo management.
"""

import os
import requests
import boto3
from typing import List, Dict, Optional
from urllib.parse import urlparse
from botocore.exceptions import ClientError, NoCredentialsError
import io

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not available. Logo conversion will be skipped.")

from app.ai_ingredient_intelligence.config import SERPER_API_KEY, AWS_S3_BUCKET_PLATFORM_LOGOS

# Platform priority order
PRIORITY_PLATFORMS = [
    "amazon",
    "nykaa",
    "flipkart",
    "tira_beauty",
    "sephora_india",
    "myntra"
]

# Platform domain mappings
PLATFORM_DOMAINS = {
    "amazon": ["amazon.in", "amazon.com"],
    "nykaa": ["nykaa.com"],
    "flipkart": ["flipkart.com"],
    "tira_beauty": ["tiabeauty.in", "tirabeauty.com", "tira"],
    "sephora_india": ["sephora.in", "sephora.co.in"],
    "myntra": ["myntra.com"],
    "purplle": ["purplle.com"],
    "jiomart": ["jiomart.com"],
    "ajio": ["ajio.com"]
}

# Map Serper source names to normalized platform names
SOURCE_TO_PLATFORM = {
    "amazon.in": "amazon",
    "amazon": "amazon",
    "nykaa": "nykaa",
    "myntra": "myntra",
    "tira": "tira_beauty",
    "tiabeauty": "tira_beauty",
    "tirabeauty": "tira_beauty",
    "sephora": "sephora_india",
    "sephora india": "sephora_india",
    "flipkart": "flipkart",
    "purplle": "purplle",
    "purplle.com": "purplle",
    "jiomart": "jiomart",
    "jiomart grocery": "jiomart",
    "ajio": "ajio",
    "ajio.com": "ajio"
}

# Platform display names
PLATFORM_DISPLAY_NAMES = {
    "amazon": "Amazon",
    "nykaa": "Nykaa",
    "flipkart": "Flipkart",
    "tira_beauty": "Tira Beauty",
    "sephora_india": "Sephora India",
    "myntra": "Myntra",
    "purplle": "Purplle",
    "jiomart": "JioMart",
    "ajio": "AJIO"
}

# Platform logo URLs (favicon or logo sources)
PLATFORM_LOGO_URLS = {
    "amazon": "https://www.amazon.in/favicon.ico",
    "nykaa": "https://www.nykaa.com/favicon.ico",
    "flipkart": "https://www.flipkart.com/favicon.ico",
    "tira_beauty": "https://www.tiabeauty.in/favicon.ico",
    "sephora_india": "https://www.sephora.in/favicon.ico",
    "myntra": "https://www.myntra.com/favicon.ico",
    "purplle": "https://www.purplle.com/favicon.ico",
    "jiomart": "https://www.jiomart.com/favicon.ico",
    "ajio": "https://www.ajio.com/favicon.ico"
}


def is_valid_ecommerce_url(url: str) -> bool:
    """
    Check if URL is a valid e-commerce product URL (not a search engine or aggregator).
    
    Args:
        url: URL to check
        
    Returns:
        True if valid e-commerce URL, False otherwise
    """
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Filter out search engines and aggregators
    excluded_domains = [
        "google.com",
        "google.co.in",
        "bing.com",
        "yahoo.com",
        "duckduckgo.com",
        "search.yahoo.com",
        "shopping.google.com",
        "www.google.com/search",
        "google.com/search"
    ]
    
    # Check if URL is from excluded domains
    for excluded in excluded_domains:
        if excluded in url_lower:
            return False
    
    # Filter out URLs that are clearly search pages
    search_indicators = [
        "/search?",
        "?q=",
        "&q=",
        "search?q=",
        "udm=",  # Google Shopping parameter
        "ibp=oshop"  # Google Shopping parameter
    ]
    
    # If URL contains search indicators, it's likely a search page
    if any(indicator in url_lower for indicator in search_indicators):
        # But allow if it's from a known e-commerce platform (they might have search in URL structure)
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Allow if it's from a known e-commerce platform
        for platform, domains in PLATFORM_DOMAINS.items():
            for platform_domain in domains:
                if domain == platform_domain or domain.endswith(f".{platform_domain}"):
                    return True
        
        # Otherwise, it's likely a search engine
        return False
    
    return True


def normalize_platform_from_source(source: str) -> str:
    """
    Normalize platform name from Serper source field.
    
    Args:
        source: Source field from Serper API (e.g., "Amazon.in", "Myntra", "Nykaa")
        
    Returns:
        Normalized platform name (e.g., "amazon", "nykaa")
    """
    if not source:
        return "unknown"
    
    source_lower = source.lower().strip()
    
    # Check direct mappings first
    for source_key, platform in SOURCE_TO_PLATFORM.items():
        if source_key in source_lower:
            return platform
    
    # Check if source contains known platform names
    if "amazon" in source_lower:
        return "amazon"
    elif "nykaa" in source_lower:
        return "nykaa"
    elif "myntra" in source_lower:
        return "myntra"
    elif "tira" in source_lower:
        return "tira_beauty"
    elif "sephora" in source_lower:
        return "sephora_india"
    elif "flipkart" in source_lower:
        return "flipkart"
    elif "purplle" in source_lower:
        return "purplle"
    elif "jiomart" in source_lower:
        return "jiomart"
    elif "ajio" in source_lower:
        return "ajio"
    
    # Extract base name from source
    # Remove common suffixes like ".com", " - ", etc.
    source_clean = source_lower.replace(".com", "").replace(".in", "").replace(" - ", " ").strip()
    parts = source_clean.split()
    if parts:
        return parts[0].lower()
    
    return "unknown"


def normalize_platform(url: str) -> str:
    """
    Normalize platform name from URL.
    
    Args:
        url: Product URL
        
    Returns:
        Normalized platform name (e.g., "amazon", "nykaa")
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        
        # Check against known platform domains
        for platform, domains in PLATFORM_DOMAINS.items():
            for platform_domain in domains:
                if domain == platform_domain or domain.endswith(f".{platform_domain}"):
                    return platform
        
        # Extract base domain for unknown platforms
        # e.g., "purplle.com" -> "purplle"
        parts = domain.split(".")
        if len(parts) >= 2:
            base_domain = parts[-2]  # Get second-to-last part
            return base_domain.lower()
        
        return domain.split(".")[0] if "." in domain else domain
    except Exception:
        return "unknown"


def get_platform_display_name(platform: str) -> str:
    """Get human-readable platform name."""
    return PLATFORM_DISPLAY_NAMES.get(platform, platform.replace("_", " ").title())


def get_favicon_url_fallback(platform: str, product_url: str = None) -> Optional[str]:
    """
    Generate favicon URL as fallback when S3 logo is not available.
    
    Args:
        platform: Normalized platform name
        product_url: Product URL to extract domain from (optional)
        
    Returns:
        Favicon URL or None
    """
    # First check if platform has a known favicon URL
    if platform in PLATFORM_LOGO_URLS:
        return PLATFORM_LOGO_URLS[platform]
    
    # Try to generate favicon URL from product URL
    if product_url:
        try:
            parsed = urlparse(product_url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            
            # Generate favicon URL
            return f"https://{domain}/favicon.ico"
        except Exception:
            pass
    
    # Try to generate from platform name if we know the domain
    if platform in PLATFORM_DOMAINS:
        domains = PLATFORM_DOMAINS[platform]
        if domains:
            return f"https://www.{domains[0]}/favicon.ico"
    
    return None


def fetch_serper_results(product_name: str, page: int = 1, num: int = 10) -> Optional[Dict]:
    """
    Fetch results from Serper API.
    
    Args:
        product_name: Product name to search
        page: Page number (1-indexed)
        num: Number of results per page
        
    Returns:
        API response dict or None if error
    """
    if not SERPER_API_KEY:
        raise ValueError("SERPER_API_KEY is not set in environment variables")
    
    url = "https://google.serper.dev/shopping"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "q": product_name,
        "type": "shopping",
        "gl": "in",  # Google location code for India
        "hl": "en",  # Language: English
        "location": "India",  # Explicit location for better India results
        "num": num,
        "page": page
    }
    
    print(f"Serper API request - Query: {product_name}, Location: in (India), Page: {page}")
    
    try:
        print(f"Serper API Request Payload: {payload}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        # Debug: Check what location was actually used
        search_params = result.get("searchParameters", {})
        actual_gl = search_params.get("gl", "not found")
        print(f"Serper API Response - Actual location used: {actual_gl}")
        
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Serper results: {str(e)}")
        return None


def deduplicate_by_platform(results: List[Dict]) -> List[Dict]:
    """
    Deduplicate results by platform, keeping best match per platform.
    
    Args:
        results: List of result dicts with 'link', 'position', 'title', 'price', 'platform_from_source'
        
    Returns:
        Deduplicated list with one result per platform
    """
    platform_results = {}
    
    for result in results:
        # Use pre-calculated platform from source if available, otherwise fall back to URL
        platform = result.get("platform_from_source")
        if not platform:
            platform = normalize_platform(result.get("link", ""))
        
        if platform not in platform_results:
            platform_results[platform] = result
        else:
            # Keep the one with lower position (better match)
            existing_position = platform_results[platform].get("position", 999)
            current_position = result.get("position", 999)
            
            if current_position < existing_position:
                platform_results[platform] = result
            elif current_position == existing_position:
                # If same position, prefer one with price
                if result.get("price") and not platform_results[platform].get("price"):
                    platform_results[platform] = result
    
    return list(platform_results.values())


def sort_by_priority(results: List[Dict]) -> List[Dict]:
    """
    Sort results by platform priority.
    
    Args:
        results: List of result dicts
        
    Returns:
        Sorted list with prioritized platforms first
    """
    def get_priority(result: Dict) -> int:
        platform = normalize_platform(result.get("link", ""))
        try:
            return PRIORITY_PLATFORMS.index(platform)
        except ValueError:
            return len(PRIORITY_PLATFORMS)  # Unknown platforms go to end
    
    # Sort by priority, then alphabetically for unknown platforms
    sorted_results = sorted(results, key=lambda x: (get_priority(x), normalize_platform(x.get("link", ""))))
    return sorted_results


def get_s3_client():
    """Get boto3 S3 client."""
    try:
        return boto3.client('s3')
    except NoCredentialsError:
        print("Warning: AWS credentials not found. Logo uploads will be skipped.")
        return None


def check_logo_exists_in_s3(platform: str, s3_client) -> Optional[str]:
    """
    Check if logo exists in S3 and return URL.
    
    Args:
        platform: Normalized platform name
        s3_client: boto3 S3 client
        
    Returns:
        S3 URL if exists, None otherwise
    """
    if not s3_client:
        print(f"Logo existence check skipped for {platform}: No S3 client available")
        return None
    
    try:
        key = f"{platform}.png"
        s3_client.head_object(Bucket=AWS_S3_BUCKET_PLATFORM_LOGOS, Key=key)
        
        # Construct S3 URL
        region = s3_client.meta.region_name if hasattr(s3_client.meta, 'region_name') else 'us-east-1'
        url = f"https://{AWS_S3_BUCKET_PLATFORM_LOGOS}.s3.{region}.amazonaws.com/{key}"
        print(f"Logo exists in S3 for {platform}: {url}")
        return url
    except ClientError as e:
        print(f"Logo not found in S3 for {platform}: {str(e)}")
        return None


def fetch_logo_image(platform: str) -> Optional[bytes]:
    """
    Fetch logo image from URL.
    
    Args:
        platform: Normalized platform name
        
    Returns:
        Image bytes or None
    """
    logo_url = PLATFORM_LOGO_URLS.get(platform)
    if not logo_url:
        # Try favicon for unknown platforms
        return None
    
    try:
        response = requests.get(logo_url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error fetching logo for {platform}: {str(e)}")
        return None


def convert_to_png(image_bytes: bytes) -> Optional[bytes]:
    """
    Convert image to PNG format.
    
    Args:
        image_bytes: Image bytes in any format
        
    Returns:
        PNG image bytes or None
    """
    if not PIL_AVAILABLE:
        # If PIL not available, return original bytes (might work for some formats)
        return image_bytes
    
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # Convert to RGB if necessary (for formats like PNG with transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Convert to PNG
        output = io.BytesIO()
        img.save(output, format='PNG')
        return output.getvalue()
    except Exception as e:
        print(f"Error converting image to PNG: {str(e)}")
        return None


def upload_logo_to_s3(platform: str, s3_client) -> Optional[str]:
    """
    Upload platform logo to S3.
    
    Args:
        platform: Normalized platform name
        s3_client: boto3 S3 client
        
    Returns:
        S3 URL of uploaded logo or None
    """
    if not s3_client:
        print(f"Logo upload skipped for {platform}: No S3 client available")
        return None
    
    # Check if already exists (redundant check for safety)
    existing_url = check_logo_exists_in_s3(platform, s3_client)
    if existing_url:
        print(f"Logo already exists for {platform}: {existing_url}")
        return existing_url
    
    print(f"Uploading new logo for platform: {platform}")
    
    # Fetch logo
    logo_bytes = fetch_logo_image(platform)
    if not logo_bytes:
        print(f"Failed to fetch logo image for {platform}")
        return None
    
    # Convert to PNG
    png_bytes = convert_to_png(logo_bytes)
    if not png_bytes:
        print(f"Failed to convert logo to PNG for {platform}")
        return None
    
    # Upload to S3
    try:
        key = f"{platform}.png"
        s3_client.put_object(
            Bucket=AWS_S3_BUCKET_PLATFORM_LOGOS,
            Key=key,
            Body=png_bytes,
            ContentType='image/png',
            ACL='public-read'  # Make publicly accessible
        )
        
        # Construct S3 URL
        region = s3_client.meta.region_name if hasattr(s3_client.meta, 'region_name') else 'us-east-1'
        url = f"https://{AWS_S3_BUCKET_PLATFORM_LOGOS}.s3.{region}.amazonaws.com/{key}"
        print(f"Successfully uploaded logo for {platform}: {url}")
        return url
    except Exception as e:
        print(f"Error uploading logo to S3 for {platform}: {str(e)}")
        return None


def fetch_platforms(product_name: str) -> List[Dict]:
    """
    Fetch all platform links for a product.
    
    Args:
        product_name: Name of the product to search
        
    Returns:
        List of platform objects with:
        - platform: normalized platform name
        - platform_display_name: human-readable name
        - url: product URL
        - logo_url: S3 URL of platform logo
        - title: product title
        - price: product price (if available)
        - position: original search position
    """
    if not SERPER_API_KEY:
        raise ValueError("SERPER_API_KEY is not set in environment variables")
    
    all_results = []
    page = 1
    max_pages = 50  # Limit to 500 results max
    
    # Fetch all pages
    while page <= max_pages:
        response = fetch_serper_results(product_name, page=page)
        
        if not response:
            print(f"No response from Serper API for page {page}")
            break
        
        # Extract shopping results
        shopping_results = response.get("shopping", [])
        
        if not shopping_results:
            print(f"No shopping results in response for page {page}")
            # Check if there are other result types we can use
            if page == 1:
                print(f"Response keys: {list(response.keys())}")
                print(f"Full response sample: {str(response)[:500]}")
            break
        
        print(f"Page {page}: Found {len(shopping_results)} shopping results")
        
        # Process results - use source field to identify platform
        valid_count = 0
        for item in shopping_results:
            link = item.get("link", "")
            source = item.get("source", "")
            
            # Use source field to identify platform (more reliable than URL for Google Shopping)
            platform_from_source = normalize_platform_from_source(source)
            
            # Skip if platform is unknown or invalid
            if platform_from_source == "unknown":
                print(f"  Skipping unknown platform from source: {source}")
                continue
            
            # Skip search engines even if they appear in source
            if platform_from_source in ["google", "bing", "yahoo"]:
                print(f"  Skipping search engine: {source}")
                continue
            
            valid_count += 1
            all_results.append({
                "link": link,  # Keep Google Shopping redirect link (it will redirect to actual product)
                "title": item.get("title", ""),
                "price": item.get("price"),
                "position": item.get("position", 999),
                "source": source,  # Store source for reference
                "platform_from_source": platform_from_source  # Pre-calculated platform
            })
        
        print(f"Page {page}: {valid_count} valid e-commerce platforms after filtering")
        
        # If we got results but they're all filtered out, log for debugging
        if len(shopping_results) > 0 and valid_count == 0:
            print(f"  Warning: All {len(shopping_results)} results were filtered out on page {page}")
            print(f"  Sample sources: {[item.get('source', 'N/A') for item in shopping_results[:5]]}")
        
        # Check if there are more pages
        # Serper API doesn't always indicate if more pages exist,
        # so we stop if we get fewer results than requested
        if len(shopping_results) < 10:
            print(f"Page {page}: Only {len(shopping_results)} results, stopping pagination")
            break
        
        page += 1
    
    print(f"Total results collected: {len(all_results)}")
    
    # Deduplicate by platform
    deduplicated = deduplicate_by_platform(all_results)
    
    # Sort by priority
    sorted_results = sort_by_priority(deduplicated)
    
    # Get S3 client for logo uploads
    s3_client = get_s3_client()
    
    # Cache for platform logos to avoid redundant S3 calls within the same request
    logo_cache = {}  # platform -> logo_url
    
    # Build final response with platform info and logos
    final_results = []
    for result in sorted_results:
        link = result.get("link", "")
        
        # Use pre-calculated platform from source if available
        platform = result.get("platform_from_source")
        if not platform:
            # Fallback to URL-based detection (but this won't work for Google Shopping links)
            platform = normalize_platform(link)
        
        # Skip if platform is "google" or other search engines
        if platform in ["google", "bing", "yahoo", "duckduckgo", "unknown"]:
            continue
        
        platform_display_name = get_platform_display_name(platform)
        
        # Get logo URL from cache or fetch/upload it
        if platform in logo_cache:
            logo_url = logo_cache[platform]
        else:
            # Check if logo exists in S3, if not upload it
            logo_url = check_logo_exists_in_s3(platform, s3_client)
            if not logo_url:
                logo_url = upload_logo_to_s3(platform, s3_client)
            
            # Fallback to favicon URL if S3 logo is not available
            if not logo_url:
                logo_url = get_favicon_url_fallback(platform, link)
                if logo_url:
                    print(f"Using favicon fallback for {platform}: {logo_url}")
            
            # Cache the result (even if None, to avoid redundant S3 calls)
            logo_cache[platform] = logo_url
        
        final_results.append({
            "platform": platform,
            "platform_display_name": platform_display_name,
            "url": link,  # Google Shopping redirect link (will redirect to actual product page)
            "logo_url": logo_url,
            "title": result.get("title", ""),
            "price": result.get("price"),
            "position": result.get("position", 999)
        })
    
    print(f"Final results: {len(final_results)} platforms found")
    print(f"Logo cache stats: {len(logo_cache)} platforms processed, {sum(1 for url in logo_cache.values() if url)}/{len(logo_cache)} logos available")
    return final_results

