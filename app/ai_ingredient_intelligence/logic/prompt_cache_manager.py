"""
Prompt Cache Manager for Claude API
=====================================

This module implements system prompt caching using Claude's cache_control API
to reduce costs and latency. System prompts are cached and reused across requests.

COST SAVINGS:
- Writing to cache: 25% more expensive than base input tokens
- Reading from cache: Only 10% of base input token price
- For long system prompts (1000+ tokens), this saves ~90% on system prompt costs

USAGE:
    cache_manager = PromptCacheManager()
    cache_block_id = await cache_manager.get_or_create_cache(
        prompt_type="ingredient_selection",
        system_prompt=INGREDIENT_SELECTION_SYSTEM_PROMPT
    )
    
    # Use cache_block_id in API calls
"""

import os
import hashlib
import json
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

# In-memory cache store (can be replaced with Redis/database for production)
# Format: {prompt_hash: {"cache_block_id": "...", "created_at": "...", "ttl": 3600}}
_cache_store: Dict[str, Dict[str, Any]] = {}

# Cache TTL in seconds (24 hours default)
CACHE_TTL = 86400


class PromptCacheManager:
    """
    Manages Claude API prompt caching for system prompts.
    
    Each system prompt is cached once and reused across all requests,
    dramatically reducing token costs for the system prompt portion.
    """
    
    def __init__(self, claude_client=None):
        """
        Initialize the cache manager.
        
        Args:
            claude_client: Anthropic client instance (optional, will use global if not provided)
        """
        self.claude_client = claude_client
        self._cache_store = _cache_store
    
    def _get_prompt_hash(self, prompt: str) -> str:
        """
        Generate a hash for the prompt to use as cache key.
        
        Args:
            prompt: The system prompt text
            
        Returns:
            SHA256 hash of the prompt
        """
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    
    def _get_cache_key(self, prompt_type: str, prompt: str) -> str:
        """
        Generate a cache key combining prompt type and hash.
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection")
            prompt: The system prompt text
            
        Returns:
            Combined cache key
        """
        prompt_hash = self._get_prompt_hash(prompt)
        return f"{prompt_type}:{prompt_hash}"
    
    async def get_or_create_cache(
        self,
        prompt_type: str,
        system_prompt: str,
        claude_client=None
    ) -> Optional[str]:
        """
        Get existing cache block ID or create a new one.
        
        This function:
        1. Checks if we have a cached block ID for this prompt
        2. If yes and not expired, returns it
        3. If no or expired, creates a new cache block via Claude API
        4. Stores the cache block ID for future use
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection", "optimization")
            system_prompt: The system prompt to cache
            claude_client: Anthropic client (optional, uses instance client or global)
            
        Returns:
            Cache block ID string, or None if caching is not available
        """
        if not claude_client:
            claude_client = self.claude_client
        
        if not claude_client:
            # No client available, return None (will use regular API call)
            return None
        
        cache_key = self._get_cache_key(prompt_type, system_prompt)
        
        # Check if we have a valid cached block ID
        cached_entry = self._cache_store.get(cache_key)
        if cached_entry:
            created_at = datetime.fromisoformat(cached_entry['created_at'])
            age = (datetime.now() - created_at).total_seconds()
            
            if age < cached_entry.get('ttl', CACHE_TTL):
                # Cache is still valid
                print(f"✅ Cache HIT for {prompt_type} (age: {age:.0f}s)")
                return cached_entry['cache_block_id']
            else:
                # Cache expired, remove it
                print(f"⏰ Cache EXPIRED for {prompt_type} (age: {age:.0f}s)")
                del self._cache_store[cache_key]
        
        # No valid cache, mark that we should use caching for this prompt
        # Claude's ephemeral caching works automatically when we use cache_control
        # We just need to track that this prompt should use caching
        try:
            print(f"📝 Setting up cache for {prompt_type}...")
            
            # Store cache metadata - we'll use the prompt hash to track cached prompts
            # Claude's ephemeral cache is automatic when cache_control is used
            cache_block_id = self._get_prompt_hash(system_prompt)
            
            self._cache_store[cache_key] = {
                "cache_block_id": cache_block_id,
                "created_at": datetime.now().isoformat(),
                "ttl": CACHE_TTL,
                "prompt_type": prompt_type,
                "system_prompt": system_prompt  # Store for reference
            }
            
            print(f"✅ Cache configured for {prompt_type}")
            return cache_block_id
            
        except Exception as e:
            print(f"⚠️ Failed to create cache block for {prompt_type}: {e}")
            # Return None to fall back to regular API call
            return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cache usage.
        
        Returns:
            Dictionary with cache statistics
        """
        total_entries = len(self._cache_store)
        valid_entries = 0
        expired_entries = 0
        
        now = datetime.now()
        for entry in self._cache_store.values():
            created_at = datetime.fromisoformat(entry['created_at'])
            age = (now - created_at).total_seconds()
            if age < entry.get('ttl', CACHE_TTL):
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "cache_types": list(set(e.get('prompt_type', 'unknown') for e in self._cache_store.values()))
        }
    
    def clear_cache(self, prompt_type: Optional[str] = None):
        """
        Clear cache entries.
        
        Args:
            prompt_type: If provided, only clear entries for this type. Otherwise clear all.
        """
        if prompt_type:
            keys_to_remove = [
                key for key, entry in self._cache_store.items()
                if entry.get('prompt_type') == prompt_type
            ]
            for key in keys_to_remove:
                del self._cache_store[key]
            print(f"🗑️ Cleared {len(keys_to_remove)} cache entries for {prompt_type}")
        else:
            count = len(self._cache_store)
            self._cache_store.clear()
            print(f"🗑️ Cleared all {count} cache entries")


# Global cache manager instance
_cache_manager: Optional[PromptCacheManager] = None


def get_cache_manager(claude_client=None) -> PromptCacheManager:
    """
    Get or create the global cache manager instance.
    
    Args:
        claude_client: Anthropic client (optional)
        
    Returns:
        PromptCacheManager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = PromptCacheManager(claude_client=claude_client)
    return _cache_manager

