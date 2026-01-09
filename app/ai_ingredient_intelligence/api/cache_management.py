"""
URL Cache Management API Endpoints
================================

Admin endpoints for managing the URL cache system.
These endpoints provide cache statistics, cleanup, and management capabilities.

Cache is system-wide (shared across all users) with 30-day TTL.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, Optional

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.logic.url_cache_manager import (
    get_cache_statistics,
    clear_expired_cache,
    clear_all_cache,
    invalidate_cache_for_url,
    is_url_cached
)
from app.ai_ingredient_intelligence.logic.url_fetcher import (
    check_url_cache_status,
    refresh_url_cache
)

router = APIRouter(prefix="/cache", tags=["URL Cache Management"])


# ============================================================================
# CACHE STATISTICS ENDPOINTS
# ============================================================================

@router.get("/stats")
async def get_cache_stats_endpoint(
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Get comprehensive cache statistics"""
    try:
        stats = await get_cache_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check")
async def check_cache_status_endpoint(
    url: str = Query(..., description="URL to check cache status for"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Check if a specific URL is cached"""
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL parameter is required")
        
        status = await check_url_cache_status(url)
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CACHE MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/refresh")
async def refresh_cache_endpoint(
    url: str = Query(..., description="URL to refresh in cache"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Force refresh cache for a specific URL"""
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL parameter is required")
        
        result = await refresh_url_cache(url)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/url")
async def invalidate_url_cache_endpoint(
    url: str = Query(..., description="URL to remove from cache"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Remove specific URL from cache"""
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL parameter is required")
        
        success = await invalidate_cache_for_url(url)
        
        return {
            "success": success,
            "url": url,
            "message": "URL removed from cache successfully" if success else "URL not found in cache"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/expired")
async def clear_expired_cache_endpoint(
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Remove all expired cache entries"""
    try:
        cleared_count = await clear_expired_cache()
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "message": f"Cleared {cleared_count} expired cache entries"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/all")
async def clear_all_cache_endpoint(
    confirm: bool = Query(False, description="Set to true to confirm clearing all cache"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Clear entire cache (DANGEROUS - requires confirmation)"""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400, 
                detail="Set confirm=true to clear entire cache. This action cannot be undone."
            )
        
        cleared_count = await clear_all_cache()
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "message": f"⚠️ Cleared entire cache ({cleared_count} entries). Cache will rebuild as URLs are requested."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CACHE HEALTH ENDPOINTS
# ============================================================================

@router.get("/health")
async def cache_health_endpoint(
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Get cache health and performance metrics"""
    try:
        stats = await get_cache_statistics()
        
        # Determine health status
        total_urls = stats.get("total_cached_urls", 0)
        expired_urls = stats.get("expired_urls", 0)
        hit_rate = float(stats.get("cache_hit_rate_today", "0%").rstrip('%'))
        
        health_status = "healthy"
        warnings = []
        
        if expired_urls > total_urls * 0.1:  # More than 10% expired
            warnings.append(f"High number of expired URLs: {expired_urls}")
            health_status = "warning"
        
        if hit_rate < 50:  # Less than 50% hit rate
            warnings.append(f"Low cache hit rate: {hit_rate}%")
            health_status = "warning"
        
        if total_urls == 0:
            warnings.append("Cache is empty")
            health_status = "info"
        
        return {
            "status": health_status,
            "warnings": warnings,
            "metrics": stats,
            "recommendations": _get_cache_recommendations(stats)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_cache_recommendations(stats: Dict[str, Any]) -> list:
    """Get cache optimization recommendations"""
    recommendations = []
    
    total_urls = stats.get("total_cached_urls", 0)
    expired_urls = stats.get("expired_urls", 0)
    hit_rate = float(stats.get("cache_hit_rate_today", "0%").rstrip('%'))
    
    if expired_urls > 0:
        recommendations.append("Run cache cleanup to remove expired entries")
    
    if hit_rate < 30:
        recommendations.append("Low hit rate - consider increasing TTL or analyzing URL patterns")
    
    if total_urls > 10000:  # Large cache size
        recommendations.append("Large cache size - consider implementing LRU eviction")
    
    if not recommendations:
        recommendations.append("Cache is performing well")
    
    return recommendations


# ============================================================================
# CACHE DEBUG ENDPOINTS
# ============================================================================

@router.get("/debug/urls")
async def get_cached_urls_endpoint(
    limit: int = Query(50, ge=1, le=500, description="Number of URLs to return"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Get list of cached URLs for debugging (limited)"""
    try:
        from app.ai_ingredient_intelligence.db.collections import url_cache_col
        from datetime import datetime
        
        # Build query
        query = {"expires_at": {"$gt": datetime.utcnow()}}  # Only active entries
        
        if platform:
            # Extract platform from URL (simple approach)
            query["url"] = {"$regex": platform, "$options": "i"}
        
        # Get limited list of URLs
        cursor = url_cache_col.find(
            query,
            {
                "url": 1,
                "scraped_at": 1,
                "expires_at": 1,
                "access_count": 1,
                "last_accessed": 1
            }
        ).sort("last_accessed", -1).limit(limit)
        
        cached_urls = []
        async for doc in cursor:
            cached_urls.append({
                "url": doc["url"],
                "scraped_at": doc["scraped_at"],
                "expires_at": doc["expires_at"],
                "access_count": doc.get("access_count", 0),
                "last_accessed": doc.get("last_accessed")
            })
        
        return {
            "cached_urls": cached_urls,
            "total_returned": len(cached_urls),
            "filter_applied": {"platform": platform} if platform else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
