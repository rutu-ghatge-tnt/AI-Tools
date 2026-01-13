"""
Merchant Link Resolver

Utility module to resolve Google Shopping URLs (from Serper.dev) into direct
merchant/platform URLs (Amazon, Flipkart, Nykaa, Myntra, etc.).

This module follows redirects from Google Shopping links to extract the actual
product URLs from various e-commerce platforms.
"""

import logging
import re
from typing import Dict, Tuple
from urllib.parse import urlparse

import requests

# Configure logging
logger = logging.getLogger(__name__)

# Browser-like User-Agent to avoid blocking
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Request timeout in seconds
REQUEST_TIMEOUT = 10

# Platform detection patterns
PLATFORM_PATTERNS = {
    "amazon": [
        r"amazon\.(in|com|co\.uk|de|fr|it|es|ca|com\.au|co\.jp)",
        r"amzn\.to",
    ],
    "flipkart": [
        r"flipkart\.com",
    ],
    "nykaa": [
        r"nykaa\.com",
    ],
    "myntra": [
        r"myntra\.com",
    ],
    "1mg": [
        r"1mg\.com",
    ],
    "pharmeasy": [
        r"pharmeasy\.in",
    ],
}


def detect_platform(url: str) -> Tuple[str, str]:
    """
    Detect the platform and domain from a URL.
    
    Args:
        url: The URL to analyze
        
    Returns:
        Tuple of (platform_name, domain)
        platform_name: "amazon", "flipkart", "nykaa", "myntra", "1mg", "pharmeasy", or "unknown"
        domain: The domain name (e.g., "amazon.in") or "unknown"
    """
    if not url:
        return "unknown", "unknown"
    
    url_lower = url.lower()
    
    # Check each platform pattern
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, url_lower)
            if match:
                # Extract domain from URL
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    # Remove www. prefix if present
                    domain = domain.replace("www.", "")
                    return platform, domain
                except Exception:
                    return platform, platform
    
    # No match found
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        return "unknown", domain
    except Exception:
        return "unknown", "unknown"


def resolve_google_shopping_url(google_url: str) -> Dict[str, str]:
    """
    Resolve a Google Shopping URL into the actual merchant/platform URL.
    
    This function:
    - Sends an HTTP GET request to the Google URL
    - Follows redirects (301/302)
    - Uses a browser-like User-Agent
    - Captures the final resolved URL
    - Detects the platform and domain
    
    Args:
        google_url: The Google Shopping or Google redirect URL to resolve
        
    Returns:
        Dictionary with the following keys:
        - original_google_url: The input Google URL
        - resolved_url: The final resolved URL (or original if resolution failed)
        - platform: "amazon", "flipkart", "nykaa", "myntra", "1mg", "pharmeasy", or "unknown"
        - domain: The domain name (e.g., "amazon.in") or "unknown"
        - resolution_method: "redirect", "failed", or "no_redirect"
    """
    logger.info(f"Starting resolution for Google URL: {google_url}")
    
    result = {
        "original_google_url": google_url,
        "resolved_url": google_url,  # Default to original if resolution fails
        "platform": "unknown",
        "domain": "unknown",
        "resolution_method": "failed",
    }
    
    if not google_url or not isinstance(google_url, str):
        logger.warning("Invalid Google URL provided")
        return result
    
    try:
        # Prepare request headers
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # Send GET request with redirect following enabled
        # allow_redirects=True is the default, but being explicit
        response = requests.get(
            google_url,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            stream=False,  # Don't stream, we just need the final URL
        )
        
        # Get the final URL after all redirects
        final_url = response.url
        
        # Check if URL changed (redirect occurred)
        if final_url != google_url:
            result["resolved_url"] = final_url
            result["resolution_method"] = "redirect"
            logger.info(f"Successfully resolved URL: {google_url} -> {final_url}")
        else:
            result["resolved_url"] = final_url
            result["resolution_method"] = "no_redirect"
            logger.info(f"No redirect occurred, using original URL: {final_url}")
        
        # Detect platform from resolved URL
        platform, domain = detect_platform(final_url)
        result["platform"] = platform
        result["domain"] = domain
        
        logger.info(
            f"Resolution complete - Platform: {platform}, Domain: {domain}, "
            f"Method: {result['resolution_method']}"
        )
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while resolving URL: {google_url}")
        result["resolution_method"] = "failed"
        # Try to detect platform from original URL as fallback
        platform, domain = detect_platform(google_url)
        result["platform"] = platform
        result["domain"] = domain
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error while resolving URL {google_url}: {e}")
        result["resolution_method"] = "failed"
        # Try to detect platform from original URL as fallback
        platform, domain = detect_platform(google_url)
        result["platform"] = platform
        result["domain"] = domain
        
    except Exception as e:
        logger.error(f"Unexpected error while resolving URL {google_url}: {e}")
        result["resolution_method"] = "failed"
        # Try to detect platform from original URL as fallback
        platform, domain = detect_platform(google_url)
        result["platform"] = platform
        result["domain"] = domain
    
    return result


# Test snippet
if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Sample Google Shopping URLs for testing
    test_urls = [
        "https://www.google.com/shopping/product/1234567890",
        "https://www.google.com/url?q=https://www.amazon.in/dp/B08XYZ123",
    ]
    
    print("\n" + "="*80)
    print("Testing Merchant Link Resolver")
    print("="*80 + "\n")
    
    for i, url in enumerate(test_urls, 1):
        print(f"Test {i}: {url}")
        print("-" * 80)
        result = resolve_google_shopping_url(url)
        print(f"Original URL: {result['original_google_url']}")
        print(f"Resolved URL: {result['resolved_url']}")
        print(f"Platform: {result['platform']}")
        print(f"Domain: {result['domain']}")
        print(f"Resolution Method: {result['resolution_method']}")
        print()

