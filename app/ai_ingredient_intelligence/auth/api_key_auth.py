"""
API Key Authentication
=====================

FastAPI dependency for API key validation via header.

USAGE:
    from app.ai_ingredient_intelligence.auth import verify_api_key
    
    @router.post("/endpoint")
    async def my_endpoint(
        request: MyRequest,
        api_key: str = Depends(verify_api_key)
    ):
        # Your endpoint logic here
        pass
"""

import os
from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import APIKeyHeader

# API Key Header Name
API_KEY_HEADER_NAME = "X-API-Key"

# Create APIKeyHeader security scheme
api_key_header = APIKeyHeader(
    name=API_KEY_HEADER_NAME,
    auto_error=False  # We'll handle errors manually for better control
)


def get_api_key_header(api_key: Optional[str] = Depends(api_key_header)) -> Optional[str]:
    """
    Extract API key from header.
    
    Returns:
        API key string if present, None otherwise
    """
    return api_key


def verify_api_key(api_key: Optional[str] = Depends(get_api_key_header)) -> str:
    """
    Verify API key from request header.
    
    This is a FastAPI dependency that validates the API key.
    
    VALIDATION LOGIC:
    1. Checks if API key is provided in X-API-Key header
    2. Validates against environment variable API_KEYS (comma-separated)
    3. Raises HTTPException if invalid or missing
    
    ENVIRONMENT VARIABLES:
    - API_KEYS: Comma-separated list of valid API keys
      Example: API_KEYS=key1,key2,key3
    
    ARGUMENTS:
    - api_key: API key from header (injected by FastAPI dependency)
    
    RETURNS:
    - str: Validated API key
    
    RAISES:
    - HTTPException 401: If API key is missing
    - HTTPException 403: If API key is invalid
    """
    # Get valid API keys from environment
    valid_api_keys_str = os.getenv("API_KEYS", "").strip()
    
    # If no API keys configured, allow all requests (backward compatibility)
    # Set API_KEYS="" to disable authentication
    if not valid_api_keys_str:
        # In production, you might want to raise an error here
        # For now, we'll allow requests if no keys are configured
        print("⚠️  WARNING: API_KEYS not configured. All requests are allowed.")
        if api_key:
            return api_key  # Return provided key if any
        return "no-auth-required"  # Return placeholder
    
    # Parse comma-separated API keys
    valid_api_keys = [key.strip() for key in valid_api_keys_str.split(",") if key.strip()]
    
    if not valid_api_keys:
        print("⚠️  WARNING: API_KEYS is empty. All requests are allowed.")
        if api_key:
            return api_key
        return "no-auth-required"
    
    # Check if API key is provided
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Validate API key
    if api_key not in valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key. Please check your API key and try again.",
        )
    
    # API key is valid
    return api_key


class APIKeyAuth:
    """
    Optional class-based approach for API key authentication.
    
    USAGE:
        auth = APIKeyAuth()
        
        @router.post("/endpoint")
        async def my_endpoint(
            request: MyRequest,
            api_key: str = Depends(auth.verify)
        ):
            pass
    """
    
    def __init__(self, header_name: str = API_KEY_HEADER_NAME):
        self.header_name = header_name
        self.api_key_header = APIKeyHeader(name=header_name, auto_error=False)
    
    def verify(self, api_key: Optional[str] = Depends(get_api_key_header)) -> str:
        """Verify API key - same as verify_api_key function."""
        return verify_api_key(api_key)


