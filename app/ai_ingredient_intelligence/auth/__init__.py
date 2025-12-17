"""
Authentication and Authorization Module
=======================================

Provides JWT token validation and authentication dependencies for FastAPI endpoints.
"""

# JWT Authentication (Primary)
from .jwt_auth import (
    verify_jwt_token,
    create_access_token,
    create_refresh_token,
    refresh_access_token,
    verify_access_token,
    verify_refresh_token,
    get_token_from_header
)

# API Key Authentication (Legacy - can be used alongside JWT)
from .api_key_auth import verify_api_key, get_api_key_header, APIKeyAuth

# Auth routes
from .auth_routes import router as auth_router

__all__ = [
    # JWT Authentication
    "verify_jwt_token",
    "create_access_token",
    "create_refresh_token",
    "refresh_access_token",
    "verify_access_token",
    "verify_refresh_token",
    "get_token_from_header",
    # API Key Authentication (Legacy)
    "verify_api_key",
    "get_api_key_header",
    "APIKeyAuth",
    # Routes
    "auth_router"
]

