"""
URL Cache Manager
==================

System-wide URL caching for product data to reduce scraping costs and improve performance.
Cache is shared across all users - same URL returns same cached data regardless of user.

CACHE TTL: 30 days (configurable)
CACHE SCOPE: System-wide (not per-user)
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from bson import ObjectId
import re
from urllib.parse import urlparse, parse_qs, urlunparse

from app.ai_ingredient_intelligence.db.collections import url_cache_col

# Cache configuration
CACHE_TTL_DAYS = 30  # 30 days as requested
CACHE_TTL_SECONDS = CACHE_TTL_DAYS * 24 * 60 * 60


async def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent caching.
    Removes tracking parameters and sorts query parameters.
    
    Args:
        url: Original URL
        
    Returns:
        Normalized URL suitable for caching
    """
    try:
        parsed = urlparse(url)
        
        # Remove common tracking parameters
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'twclid', 'ttclid', 'ref', 'source',
            'aff', 'affiliate', 'partner', 'campaign', 'ad', 'click_id'
        }
        
        # Parse query parameters
        query_params = parse_qs(parsed.query)
        
        # Remove tracking parameters
        filtered_params = {
            k: v for k, v in query_params.items() 
            if k.lower() not in tracking_params
        }
        
        # Rebuild query string with sorted parameters
        sorted_params = []
        for key in sorted(filtered_params.keys()):
            values = filtered_params[key]
            if isinstance(values, list):
                for value in sorted(values):
                    sorted_params.append(f"{key}={value}")
            else:
                sorted_params.append(f"{key}={values}")
        
        query_string = "&".join(sorted_params)
        
        # Rebuild normalized URL
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,  # Usually empty
            query_string,
            parsed.fragment  # Keep fragment for anchor links
        ))
        
        return normalized
        
    except Exception as e:
        print(f"Error normalizing URL {url}: {e}")
        return url  # Return original if normalization fails


async def get_cached_url_data(url: str) -> Optional[Dict[str, Any]]:
    """
    Get cached data for a URL if it exists and is not expired.
    
    Args:
        url: URL to fetch from cache
        
    Returns:
        Cached data dict or None if not found/expired
    """
    try:
        normalized_url = await normalize_url(url)
        
        # Find cached entry
        cached_entry = await url_cache_col.find_one({
            "normalized_url": normalized_url,
            "expires_at": {"$gt": datetime.utcnow()}  # Not expired
        })
        
        if cached_entry:
            # Update access statistics
            await url_cache_col.update_one(
                {"_id": cached_entry["_id"]},
                {
                    "$inc": {"access_count": 1},
                    "$set": {"last_accessed": datetime.utcnow()}
                }
            )
            
            print(f"✅ Cache HIT for {url} (accessed {cached_entry['access_count'] + 1} times)")
            return cached_entry["extracted_data"]
        
        print(f"❌ Cache MISS for {url}")
        return None
        
    except Exception as e:
        print(f"Error getting cached URL data for {url}: {e}")
        return None


async def cache_url_data(url: str, data: Dict[str, Any]) -> bool:
    """
    Store scraped data in cache with 30-day TTL.
    
    Args:
        url: Original URL
        data: Scraped product data
        
    Returns:
        True if cached successfully, False otherwise
    """
    try:
        normalized_url = await normalize_url(url)
        
        # Calculate expiration date
        expires_at = datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS)
        
        # Create cache entry
        cache_entry = {
            "url": url,
            "normalized_url": normalized_url,
            "extracted_data": data,
            "scraped_at": datetime.utcnow(),
            "expires_at": expires_at,
            "access_count": 0,
            "last_accessed": datetime.utcnow(),
            "cache_version": "1.0"  # For future compatibility
        }
        
        # Use upsert to handle both new entries and updates
        result = await url_cache_col.replace_one(
            {"normalized_url": normalized_url},
            cache_entry,
            upsert=True
        )
        
        if result.upserted_id or result.modified_count > 0:
            print(f"💾 Cached {url} (expires: {expires_at.strftime('%Y-%m-%d')})")
            return True
        else:
            print(f"⚠️ Failed to cache {url}")
            return False
            
    except Exception as e:
        print(f"Error caching URL data for {url}: {e}")
        return False


async def invalidate_cache_for_url(url: str) -> bool:
    """
    Remove specific URL from cache.
    
    Args:
        url: URL to invalidate
        
    Returns:
        True if invalidated successfully
    """
    try:
        normalized_url = await normalize_url(url)
        
        result = await url_cache_col.delete_one({
            "normalized_url": normalized_url
        })
        
        if result.deleted_count > 0:
            print(f"🗑️ Invalidated cache for {url}")
            return True
        else:
            print(f"⚠️ No cache entry found for {url}")
            return False
            
    except Exception as e:
        print(f"Error invalidating cache for {url}: {e}")
        return False


async def clear_expired_cache() -> int:
    """
    Remove all expired cache entries.
    
    Returns:
        Number of entries cleared
    """
    try:
        result = await url_cache_col.delete_many({
            "expires_at": {"$lte": datetime.utcnow()}
        })
        
        if result.deleted_count > 0:
            print(f"🧹 Cleared {result.deleted_count} expired cache entries")
        
        return result.deleted_count
        
    except Exception as e:
        print(f"Error clearing expired cache: {e}")
        return 0


async def get_cache_statistics() -> Dict[str, Any]:
    """
    Get cache performance and storage statistics.
    
    Returns:
        Dictionary with cache stats
    """
    try:
        now = datetime.utcnow()
        
        # Total cached URLs
        total_cached = await url_cache_col.count_documents({})
        
        # Expired entries (to be cleaned)
        expired_count = await url_cache_col.count_documents({
            "expires_at": {"$lte": now}
        })
        
        # Active entries
        active_count = total_cached - expired_count
        
        # Storage statistics
        pipeline = [
            {"$match": {"expires_at": {"$gt": now}}},
            {
                "$group": {
                    "_id": None,
                    "total_accesses": {"$sum": "$access_count"},
                    "oldest_cache": {"$min": "$scraped_at"},
                    "newest_cache": {"$max": "$scraped_at"},
                    "avg_accesses": {"$avg": "$access_count"}
                }
            }
        ]
        
        storage_stats = await url_cache_col.aggregate(pipeline).to_list(length=1)
        stats = storage_stats[0] if storage_stats else {}
        
        # Today's cache activity (approximate)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_accessed = await url_cache_col.count_documents({
            "last_accessed": {"$gte": today_start}
        })
        
        return {
            "total_cached_urls": total_cached,
            "active_cached_urls": active_count,
            "expired_urls": expired_count,
            "cache_hit_rate_today": f"{(today_accessed / max(total_cached, 1)) * 100:.1f}%",
            "urls_accessed_today": today_accessed,
            "total_accesses_all_time": stats.get("total_accesses", 0),
            "avg_accesses_per_url": round(stats.get("avg_accesses", 0), 2),
            "oldest_cache_date": stats.get("oldest_cache", now).strftime("%Y-%m-%d"),
            "newest_cache_date": stats.get("newest_cache", now).strftime("%Y-%m-%d"),
            "cache_ttl_days": CACHE_TTL_DAYS,
            "cache_version": "1.0"
        }
        
    except Exception as e:
        print(f"Error getting cache statistics: {e}")
        return {
            "error": str(e),
            "total_cached_urls": 0,
            "active_cached_urls": 0,
            "expired_urls": 0
        }


async def clear_all_cache() -> int:
    """
    Clear entire cache (use with caution).
    
    Returns:
        Number of entries cleared
    """
    try:
        result = await url_cache_col.delete_many({})
        
        if result.deleted_count > 0:
            print(f"🗑️ Cleared entire cache ({result.deleted_count} entries)")
        
        return result.deleted_count
        
    except Exception as e:
        print(f"Error clearing all cache: {e}")
        return 0


async def is_url_cached(url: str) -> bool:
    """
    Check if URL is cached and not expired.
    
    Args:
        url: URL to check
        
    Returns:
        True if cached and valid
    """
    try:
        normalized_url = await normalize_url(url)
        
        cached_entry = await url_cache_col.find_one({
            "normalized_url": normalized_url,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        return cached_entry is not None
        
    except Exception as e:
        print(f"Error checking if URL is cached: {e}")
        return False


# Cache validation helpers
def validate_cached_data(data: Dict[str, Any]) -> bool:
    """
    Validate that cached data has required structure.
    
    Args:
        data: Cached data to validate
        
    Returns:
        True if data structure is valid
    """
    try:
        # Check for essential fields
        required_fields = ["name", "brand"]  # Minimum required
        
        for field in required_fields:
            if field not in data or not data[field]:
                return False
        
        # Validate data types
        if not isinstance(data.get("price"), (int, float, type(None))):
            return False
        
        return True
        
    except Exception:
        return False
