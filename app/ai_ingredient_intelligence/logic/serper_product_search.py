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
    "tira_beauty": ["tiabeauty.in", "tirabeauty.com"],
    "sephora_india": ["sephora.in", "sephora.co.in"],
    "myntra": ["myntra.com"]
}

# Platform display names
PLATFORM_DISPLAY_NAMES = {
    "amazon": "Amazon",
    "nykaa": "Nykaa",
    "flipkart": "Flipkart",
    "tira_beauty": "Tira Beauty",
    "sephora_india": "Sephora India",
    "myntra": "Myntra"
}

# Platform logo URLs (favicon or logo sources)
PLATFORM_LOGO_URLS = {
    "amazon": "https://www.amazon.in/favicon.ico",
    "nykaa": "https://www.nykaa.com/favicon.ico",
    "flipkart": "https://www.flipkart.com/favicon.ico",
    "tira_beauty": "https://www.tiabeauty.in/favicon.ico",
    "sephora_india": "https://www.sephora.in/favicon.ico",
    "myntra": "https://www.myntra.com/favicon.ico"
}


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
        "country": "IN",
        "num": num,
        "page": page
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Serper results: {str(e)}")
        return None


def deduplicate_by_platform(results: List[Dict]) -> List[Dict]:
    """
    Deduplicate results by platform, keeping best match per platform.
    
    Args:
        results: List of result dicts with 'link', 'position', 'title', 'price'
        
    Returns:
        Deduplicated list with one result per platform
    """
    platform_results = {}
    
    for result in results:
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
        return None
    
    try:
        key = f"{platform}.png"
        s3_client.head_object(Bucket=AWS_S3_BUCKET_PLATFORM_LOGOS, Key=key)
        
        # Construct S3 URL
        region = s3_client.meta.region_name if hasattr(s3_client.meta, 'region_name') else 'us-east-1'
        return f"https://{AWS_S3_BUCKET_PLATFORM_LOGOS}.s3.{region}.amazonaws.com/{key}"
    except ClientError:
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
        return None
    
    # Check if already exists
    existing_url = check_logo_exists_in_s3(platform, s3_client)
    if existing_url:
        return existing_url
    
    # Fetch logo
    logo_bytes = fetch_logo_image(platform)
    if not logo_bytes:
        return None
    
    # Convert to PNG
    png_bytes = convert_to_png(logo_bytes)
    if not png_bytes:
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
        return f"https://{AWS_S3_BUCKET_PLATFORM_LOGOS}.s3.{region}.amazonaws.com/{key}"
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
            break
        
        # Extract shopping results
        shopping_results = response.get("shopping", [])
        if not shopping_results:
            break
        
        # Process results
        for item in shopping_results:
            all_results.append({
                "link": item.get("link", ""),
                "title": item.get("title", ""),
                "price": item.get("price"),
                "position": item.get("position", 999)
            })
        
        # Check if there are more pages
        # Serper API doesn't always indicate if more pages exist,
        # so we stop if we get fewer results than requested
        if len(shopping_results) < 10:
            break
        
        page += 1
    
    # Deduplicate by platform
    deduplicated = deduplicate_by_platform(all_results)
    
    # Sort by priority
    sorted_results = sort_by_priority(deduplicated)
    
    # Get S3 client for logo uploads
    s3_client = get_s3_client()
    
    # Build final response with platform info and logos
    final_results = []
    for result in sorted_results:
        platform = normalize_platform(result.get("link", ""))
        platform_display_name = get_platform_display_name(platform)
        
        # Get or upload logo
        logo_url = check_logo_exists_in_s3(platform, s3_client)
        if not logo_url:
            logo_url = upload_logo_to_s3(platform, s3_client)
        
        final_results.append({
            "platform": platform,
            "platform_display_name": platform_display_name,
            "url": result.get("link", ""),
            "logo_url": logo_url,
            "title": result.get("title", ""),
            "price": result.get("price"),
            "position": result.get("position", 999)
        })
    
    return final_results

