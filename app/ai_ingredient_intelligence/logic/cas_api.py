# app/ai_ingredient_intelligence/logic/cas_api.py
"""
CAS Common Chemistry API integration for synonym detection
Uses CAS numbers to find synonyms of ingredients
"""
import os
import httpx
from typing import List, Dict, Optional
import asyncio

# CAS API Configuration
CAS_API_BASE_URL = "https://commonchemistry.cas.org/api"
CAS_API_KEY = os.getenv("CAS_API_KEY", "uuh8gV5F4i5C1PbE6hRLl68FpU9xUDS33xKQaUHf")
CAS_API_HEADERS = {
    "X-API-KEY": CAS_API_KEY,  # Note: Header name is X-API-KEY (all caps with hyphens)
    "Accept": "application/json"
}


async def search_cas_by_name(ingredient_name: str, offset: Optional[str] = None, size: Optional[str] = None) -> Optional[Dict]:
    """
    Search CAS Common Chemistry by ingredient name.
    
    Args:
        ingredient_name: Name to search for (case-insensitive, supports wildcards like 'car*')
        offset: Optional pagination offset
        size: Optional page size (max 100)
    
    Returns:
        First matching substance detail with CAS RN and synonyms, or None if not found
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search by name (case-insensitive, supports wildcards)
            search_url = f"{CAS_API_BASE_URL}/search"
            params = {"q": ingredient_name}
            
            # Add optional pagination parameters
            if offset:
                params["offset"] = offset
            if size:
                params["size"] = size
            
            response = await client.get(
                search_url,
                params=params,
                headers=CAS_API_HEADERS
            )
            
            if response.status_code != 200:
                if response.status_code == 404:
                    # No results found - this is normal, not an error
                    return None
                print(f"⚠️ CAS API search failed for '{ingredient_name}': {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            
            # Get results (paginated, max 100 per page)
            # Response format: {"count": "1", "results": [...]}
            results = data.get("results", [])
            if not results:
                return None
            
            # Return first result (most relevant)
            first_result = results[0]
            
            # Get detailed information including synonyms
            cas_rn = first_result.get("rn")
            if cas_rn:
                detail = await get_cas_detail_by_rn(cas_rn)
                if detail:
                    return detail
            
            return first_result
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        print(f"⚠️ CAS API search HTTP error for '{ingredient_name}': {e}")
        return None
    except Exception as e:
        print(f"⚠️ Error searching CAS API for '{ingredient_name}': {e}")
        return None


async def get_cas_detail_by_rn(cas_rn: str) -> Optional[Dict]:
    """
    Get detailed information for a CAS Registry Number.
    
    Args:
        cas_rn: CAS Registry Number (e.g., "50-00-0" or "50000")
                Note: API accepts both formats, but dashes are preferred
    
    Returns:
        Substance details including synonyms, or None if not found
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # API accepts CAS RN with or without dashes
            # Keep original format (with dashes if present)
            detail_url = f"{CAS_API_BASE_URL}/detail"
            params = {"cas_rn": cas_rn}  # Parameter name is 'cas_rn' per Swagger spec
            
            response = await client.get(
                detail_url,
                params=params,
                headers=CAS_API_HEADERS
            )
            
            if response.status_code == 404:
                # Not found - this is normal, not an error
                return None
            
            if response.status_code != 200:
                print(f"⚠️ CAS API detail failed for CAS RN '{cas_rn}': {response.status_code} - {response.text}")
                return None
            
            return response.json()
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        print(f"⚠️ CAS API detail HTTP error for CAS RN '{cas_rn}': {e}")
        return None
    except Exception as e:
        print(f"⚠️ Error getting CAS detail for '{cas_rn}': {e}")
        return None


async def get_cas_detail_by_uri(uri: str) -> Optional[Dict]:
    """
    Get detailed information using URI.
    
    Args:
        uri: Substance URI (e.g., "substance/pt/50000")
    
    Returns:
        Substance details including synonyms, or None if not found
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            detail_url = f"{CAS_API_BASE_URL}/detail"
            params = {"uri": uri}
            
            response = await client.get(
                detail_url,
                params=params,
                headers=CAS_API_HEADERS
            )
            
            if response.status_code == 404:
                return None
            
            if response.status_code != 200:
                print(f"⚠️ CAS API detail failed for URI '{uri}': {response.status_code} - {response.text}")
                return None
            
            return response.json()
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        print(f"⚠️ CAS API detail HTTP error for URI '{uri}': {e}")
        return None
    except Exception as e:
        print(f"⚠️ Error getting CAS detail for URI '{uri}': {e}")
        return None


async def get_cas_detail(cas_rn: Optional[str] = None, uri: Optional[str] = None) -> Optional[Dict]:
    """
    Get detailed information for a CAS Registry Number or URI.
    Convenience function that calls the appropriate endpoint.
    
    Args:
        cas_rn: CAS Registry Number (e.g., "50-00-0")
        uri: Substance URI (e.g., "substance/pt/50000")
    
    Returns:
        Substance details including synonyms, or None if not found
    """
    if uri:
        return await get_cas_detail_by_uri(uri)
    elif cas_rn:
        return await get_cas_detail_by_rn(cas_rn)
    else:
        return None


async def get_synonyms_by_cas(cas_rn: str) -> List[str]:
    """
    Get all synonyms for a given CAS Registry Number.
    
    Args:
        cas_rn: CAS Registry Number (e.g., "50-00-0")
    
    Returns:
        List of synonym names (including the primary name)
    """
    detail = await get_cas_detail_by_rn(cas_rn)
    if not detail:
        return []
    
    synonyms = []
    
    # Extract synonyms from detail response
    # Response structure per Swagger: {"synonyms": ["Formaldehyde", "BFV", ...], "name": "Formaldehyde", ...}
    if "synonyms" in detail and isinstance(detail["synonyms"], list):
        synonyms.extend(detail["synonyms"])
    
    # Also include the primary name if not already in synonyms
    if "name" in detail and detail["name"]:
        primary_name = detail["name"]
        if primary_name not in synonyms:
            synonyms.insert(0, primary_name)  # Put primary name first
    
    # Remove duplicates and normalize (preserve original case for display)
    unique_synonyms = []
    seen = set()
    for synonym in synonyms:
        if synonym and isinstance(synonym, str):
            normalized = synonym.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_synonyms.append(synonym.strip())
    
    return unique_synonyms


async def get_synonyms_for_ingredient(ingredient_name: str) -> List[str]:
    """
    Get synonyms for an ingredient by searching CAS API.
    First searches by name, then gets synonyms from the CAS RN.
    Returns list of synonyms including the original name.
    """
    try:
        # Search for the ingredient
        search_result = await search_cas_by_name(ingredient_name)
        if not search_result:
            return []
        
        # Get CAS RN
        cas_rn = search_result.get("rn")
        if not cas_rn:
            # Try to get from detail if available
            cas_rn = search_result.get("cas_rn")
        
        if not cas_rn:
            return []
        
        # Get all synonyms for this CAS RN
        synonyms = await get_synonyms_by_cas(cas_rn)
        
        # Add original name if not already in synonyms
        if ingredient_name not in synonyms:
            synonyms.insert(0, ingredient_name)
        
        return synonyms
        
    except Exception as e:
        print(f"⚠️ Error getting synonyms for '{ingredient_name}': {e}")
        return []


async def get_synonyms_batch(ingredient_names: List[str]) -> Dict[str, List[str]]:
    """
    Get synonyms for multiple ingredients in batch.
    Returns dict mapping ingredient name to list of synonyms.
    """
    results = {}
    
    # OPTIMIZED: Process in larger batches with reduced delay to avoid rate limiting
    batch_size = 10  # Increased from 5 to 10
    for i in range(0, len(ingredient_names), batch_size):
        batch = ingredient_names[i:i + batch_size]
        
        # Process batch concurrently
        tasks = [get_synonyms_for_ingredient(name) for name in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for ingredient, synonyms in zip(batch, batch_results):
            if isinstance(synonyms, Exception):
                print(f"⚠️ Error getting synonyms for '{ingredient}': {synonyms}")
                results[ingredient] = []
            else:
                results[ingredient] = synonyms
        
        # Reduced delay between batches (from 0.5s to 0.1s) - only if not last batch
        if i + batch_size < len(ingredient_names):
            await asyncio.sleep(0.1)  # Reduced from 0.5s
    
    return results

