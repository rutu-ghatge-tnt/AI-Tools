"""
Authentication Routes
====================

API endpoints for authentication: login, refresh token, etc.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from app.ai_ingredient_intelligence.auth.jwt_auth import (
    create_access_token,
    create_refresh_token,
    refresh_access_token,
    verify_refresh_token
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request model"""
    user_id: str
    email: Optional[str] = None
    # Add other user fields as needed


class LoginResponse(BaseModel):
    """Login response model"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds


class RefreshTokenRequest(BaseModel):
    """Refresh token request model"""
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """Refresh token response model"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Login endpoint - generates access and refresh tokens.
    
    REQUEST:
    {
        "user_id": "user123",
        "email": "user@example.com"  // optional
    }
    
    RESPONSE:
    {
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",
        "token_type": "Bearer",
        "expires_in": 86400  // 1 day in seconds
    }
    """
    # Prepare user data for token
    user_data = {
        "user_id": request.user_id,
    }
    
    if request.email:
        user_data["email"] = request.email
    
    # Generate tokens
    access_token = create_access_token(user_data)
    refresh_token = create_refresh_token(user_data)
    
    # Calculate expiry in seconds (default 1 day = 86400 seconds)
    from app.ai_ingredient_intelligence.auth.jwt_auth import parse_expiry, ACCESS_TOKEN_EXPIRY
    expiry_delta = parse_expiry(ACCESS_TOKEN_EXPIRY)
    expires_in = int(expiry_delta.total_seconds())
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=expires_in
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token.
    
    REQUEST:
    {
        "refresh_token": "eyJ..."
    }
    
    RESPONSE:
    {
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",
        "token_type": "Bearer"
    }
    """
    try:
        tokens = refresh_access_token(request.refresh_token)
        return RefreshTokenResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_type="Bearer"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing token: {str(e)}"
        )


@router.post("/test-create-verify")
async def test_create_and_verify():
    """
    Test endpoint: Create a token and immediately verify it.
    This helps debug secret key mismatches.
    """
    from app.ai_ingredient_intelligence.auth.jwt_auth import create_access_token, verify_access_token, ACCESS_TOKEN_SECRET
    
    # Create a test token
    test_data = {
        "user_id": "test_user_123",
        "email": "test@example.com"
    }
    
    try:
        print(f"\n🧪 TEST: Creating token with secret: {ACCESS_TOKEN_SECRET[:10]}... (length: {len(ACCESS_TOKEN_SECRET)})")
        token = create_access_token(test_data)
        
        print(f"\n🧪 TEST: Verifying token we just created...")
        payload = verify_access_token(token)
        
        return {
            "success": True,
            "message": "Token created and verified successfully",
            "token": token,
            "payload": payload,
            "secret_used": ACCESS_TOKEN_SECRET[:10] + "..." if len(ACCESS_TOKEN_SECRET) > 10 else ACCESS_TOKEN_SECRET,
            "secret_length": len(ACCESS_TOKEN_SECRET)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "secret_used": ACCESS_TOKEN_SECRET[:10] + "..." if len(ACCESS_TOKEN_SECRET) > 10 else ACCESS_TOKEN_SECRET,
            "secret_length": len(ACCESS_TOKEN_SECRET),
            "error_type": type(e).__name__
        }


@router.post("/verify")
async def verify_token(token: str):
    """
    Verify if a token is valid (for testing/debugging).
    
    REQUEST:
    {
        "token": "eyJ..."
    }
    
    RESPONSE:
    {
        "valid": true,
        "payload": {...}
    }
    """
    from app.ai_ingredient_intelligence.auth.jwt_auth import verify_access_token, ACCESS_TOKEN_SECRET
    import jwt
    from datetime import datetime
    
    # First, try to decode without verification to see structure
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        print(f"📋 Unverified token payload: {unverified}")
    except Exception as e:
        print(f"⚠️ Could not decode token (even without verification): {e}")
        unverified = None
    
    # Now verify properly
    try:
        payload = verify_access_token(token)
        return {
            "valid": True,
            "payload": payload,
            "unverified_payload": unverified,
            "secret_used": ACCESS_TOKEN_SECRET[:10] + "..." if len(ACCESS_TOKEN_SECRET) > 10 else ACCESS_TOKEN_SECRET
        }
    except HTTPException as e:
        return {
            "valid": False,
            "error": e.detail,
            "unverified_payload": unverified,
            "secret_tried": ACCESS_TOKEN_SECRET[:10] + "..." if len(ACCESS_TOKEN_SECRET) > 10 else ACCESS_TOKEN_SECRET,
            "hint": "Check if token was created with the same secret key"
        }

