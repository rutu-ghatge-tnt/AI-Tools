"""
JWT Token Authentication
========================

FastAPI dependency for JWT token validation via Authorization header.

USAGE:
    from app.ai_ingredient_intelligence.auth import verify_jwt_token
    
    @router.post("/endpoint")
    async def my_endpoint(
        request: MyRequest,
        current_user: dict = Depends(verify_jwt_token)
    ):
        # Your endpoint logic here
        # current_user contains decoded token payload
        pass
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

try:
    import jwt
except ImportError:
    raise ImportError(
        "PyJWT is required for JWT authentication. Install it with: pip install PyJWT"
    )

# JWT Configuration from environment
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "SKINBBMAINSUPERSECRET")
ACCESS_TOKEN_EXPIRY = os.getenv("ACCESS_TOKEN_EXPIRY", "1d")
REFRESH_TOKEN_SECRET = os.getenv("REFRESH_TOKEN_SECRET", "SKINBBREFERSHMAINSUPERSECRET")
REFRESH_TOKEN_EXPIRY = os.getenv("REFRESH_TOKEN_EXPIRY", "2d")

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


def parse_expiry(expiry_str: str) -> timedelta:
    """
    Parse expiry string (e.g., "1d", "2h", "30m") to timedelta.
    
    Args:
        expiry_str: String like "1d", "2h", "30m", "7d"
    
    Returns:
        timedelta object
    """
    expiry_str = expiry_str.strip().lower()
    
    if expiry_str.endswith('d'):
        days = int(expiry_str[:-1])
        return timedelta(days=days)
    elif expiry_str.endswith('h'):
        hours = int(expiry_str[:-1])
        return timedelta(hours=hours)
    elif expiry_str.endswith('m'):
        minutes = int(expiry_str[:-1])
        return timedelta(minutes=minutes)
    elif expiry_str.endswith('s'):
        seconds = int(expiry_str[:-1])
        return timedelta(seconds=seconds)
    else:
        # Default to days if no unit specified
        return timedelta(days=int(expiry_str))


def create_access_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Dictionary containing user data (e.g., {"user_id": "123", "email": "user@example.com"})
    
    Returns:
        Encoded JWT token string
    """
    expiry = parse_expiry(ACCESS_TOKEN_EXPIRY)
    expire_datetime = datetime.utcnow() + expiry
    
    # PyJWT accepts datetime objects, but ensure it's properly handled
    # Convert to timestamp for explicit control (PyJWT 2.x handles datetime, but be explicit)
    payload = {
        **data,
        "exp": int(expire_datetime.timestamp()),  # Explicit timestamp conversion
        "iat": int(datetime.utcnow().timestamp()),  # Explicit timestamp conversion
        "type": "access"
    }
    
    # Ensure secret is a string (not bytes) for consistency
    secret = str(ACCESS_TOKEN_SECRET)
    
    # Debug: Log token creation details
    secret_preview = secret[:10] + "..." if len(secret) > 10 else secret
    print(f"🔨 Creating token with secret: {secret_preview} (length: {len(secret)}, type: {type(secret).__name__})")
    print(f"📝 Token payload: {list(payload.keys())}")
    
    # PyJWT 2.x returns string, but ensure it's a string
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    # Ensure token is a string (PyJWT 2.x should return string, but be safe)
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    
    print(f"✅ Token created: {token[:20]}... (length: {len(token)})")
    return token


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Dictionary containing user data (e.g., {"user_id": "123"})
    
    Returns:
        Encoded JWT refresh token string
    """
    expiry = parse_expiry(REFRESH_TOKEN_EXPIRY)
    expire_datetime = datetime.utcnow() + expiry
    
    # PyJWT accepts datetime objects, but ensure it's properly handled
    payload = {
        **data,
        "exp": int(expire_datetime.timestamp()),  # Explicit timestamp conversion
        "iat": int(datetime.utcnow().timestamp()),  # Explicit timestamp conversion
        "type": "refresh"
    }
    
    # Ensure secret is a string (not bytes) for consistency
    secret = str(REFRESH_TOKEN_SECRET)
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    # Ensure token is a string
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    
    return token


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode an access token.
    
    Supports both Python-generated tokens and Node.js-generated tokens.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token payload (normalized for compatibility)
    
    Raises:
        HTTPException: If token is invalid, expired, or wrong type
    """
    # Try multiple secret keys (for Node.js compatibility)
    # Since user confirmed both use ACCESS_TOKEN_SECRET, try that first
    possible_secrets = [
        ACCESS_TOKEN_SECRET,  # Primary - should match Node.js
        os.getenv("JWT_SECRET", ""),  # Common Node.js env var name
        os.getenv("JWT_ACCESS_SECRET", ""),  # Alternative name
    ]
    # Remove empty strings and duplicates
    possible_secrets = list(dict.fromkeys([s for s in possible_secrets if s]))
    
    print(f"🔍 Will try {len(possible_secrets)} secret key(s)")
    
    last_error = None
    
    for idx, secret in enumerate(possible_secrets, 1):
        try:
            # Ensure secret is a string (not bytes) for consistency with token creation
            secret_str = str(secret)
            
            # Debug: Check secret key
            secret_key_preview = secret_str[:10] + "..." if len(secret_str) > 10 else secret_str
            print(f"🔐 [{idx}/{len(possible_secrets)}] Trying secret key: {secret_key_preview} (length: {len(secret_str)}, type: {type(secret_str).__name__})")
            
            # Ensure token is a string if it's bytes
            token_str = token if isinstance(token, str) else token.decode('utf-8') if isinstance(token, bytes) else str(token)
            
            payload = jwt.decode(token_str, secret_str, algorithms=["HS256"])
            
            # Debug: Log full payload structure
            print(f"📋 Token payload keys: {list(payload.keys())}")
            token_type = payload.get("type", "not specified")
            print(f"📋 Token type: {token_type}")
            
            # Normalize user ID field (Node.js uses _id, Python uses user_id)
            if "_id" in payload and "user_id" not in payload:
                payload["user_id"] = payload["_id"]
                print(f"🔄 Normalized _id to user_id: {payload['user_id']}")
            
            # Verify token type (if present - Node.js tokens might not have this)
            token_type = payload.get("type")
            if token_type is not None:
                # If type is explicitly set, check it
                if token_type == "refresh":
                    print(f"❌ Token type is 'refresh', expected 'access'")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token type. Access token required.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                elif token_type != "access":
                    print(f"⚠️ Token type is '{token_type}', expected 'access' (allowing anyway)")
            else:
                # If no type field, assume it's an access token (Node.js compatibility)
                payload["type"] = "access"
                print("ℹ️ Token has no 'type' field, assuming 'access' (Node.js compatibility)")
            
            user_id = payload.get("user_id") or payload.get("_id", "unknown")
            print(f"✅ Token verified successfully for user: {user_id}")
            return payload
        
        except jwt.ExpiredSignatureError:
            print("❌ Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please refresh your token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        except jwt.InvalidSignatureError:
            last_error = f"Invalid signature with secret: {secret_key_preview}"
            print(f"⚠️ {last_error}")
            continue  # Try next secret
        
        except jwt.InvalidTokenError as e:
            last_error = str(e)
            print(f"❌ Invalid token error: {last_error}")
            # If it's not a signature error, don't try other secrets
            if "signature" not in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {str(e)}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            continue  # Try next secret
    
    # If we get here, all secrets failed
    print(f"❌ All secret keys failed. Last error: {last_error}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token signature. Secret key mismatch. Please ensure ACCESS_TOKEN_SECRET matches your Node.js JWT_SECRET.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_refresh_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a refresh token.
    
    Args:
        token: JWT refresh token string
    
    Returns:
        Decoded token payload
    
    Raises:
        HTTPException: If token is invalid, expired, or wrong type
    """
    try:
        payload = jwt.decode(token, REFRESH_TOKEN_SECRET, algorithms=["HS256"])
        
        # Verify token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Refresh token required.",
            )
        
        return payload
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please login again.",
        )
    
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
        )


def get_token_from_header(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Extract JWT token from Authorization header.
    
    Supports multiple extraction methods for compatibility:
    1. HTTPBearer (standard FastAPI method)
    2. Direct header extraction (fallback)
    
    Args:
        request: FastAPI Request object for direct header access
        credentials: HTTPBearer credentials (injected by FastAPI)
    
    Returns:
        Token string if present, None otherwise
    """
    token = None
    
    # Method 1: Try HTTPBearer extraction
    if credentials:
        token = credentials.credentials
        if token:
            print(f"🔑 Token received via HTTPBearer: {token[:20]}... (length: {len(token)})")
            return token
    
    # Method 2: Try direct header extraction (fallback)
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header:
        print(f"🔍 Found Authorization header: {auth_header[:30]}...")
        # Check if it starts with "Bearer "
        if auth_header.startswith("Bearer ") or auth_header.startswith("bearer "):
            token = auth_header[7:].strip()  # Remove "Bearer " prefix
            if token:
                print(f"🔑 Token extracted from header: {token[:20]}... (length: {len(token)})")
                return token
        else:
            print(f"⚠️ Authorization header doesn't start with 'Bearer ': {auth_header[:50]}")
    
    # No token found
    print("⚠️ No credentials found in Authorization header")
    print("   This might indicate:")
    print("   - Header not sent: Check frontend is sending 'Authorization: Bearer <token>'")
    print("   - Header format wrong: Must be exactly 'Bearer <token>' (case-sensitive)")
    print("   - CORS blocking: Check browser console for CORS errors")
    print(f"   - Available headers: {list(request.headers.keys())}")
    
    return None


def verify_jwt_token(token: Optional[str] = Depends(get_token_from_header)) -> Dict[str, Any]:
    """
    Verify JWT token from Authorization header.
    
    This is a FastAPI dependency that validates JWT tokens.
    
    VALIDATION LOGIC:
    1. Extracts token from Authorization: Bearer <token> header
    2. Verifies token signature and expiration
    3. Returns decoded token payload
    
    USAGE:
        @router.post("/endpoint")
        async def my_endpoint(
            request: MyRequest,
            current_user: dict = Depends(verify_jwt_token)
        ):
            user_id = current_user.get("user_id")
            # Your logic here
    
    ARGUMENTS:
    - token: JWT token from header (injected by FastAPI dependency)
    
    RETURNS:
    - dict: Decoded token payload containing user information
    
    RAISES:
    - HTTPException 401: If token is missing, invalid, or expired
    """
    # Check if token is provided
    if not token:
        print("❌ No token provided in Authorization header")
        print("   Debug info:")
        print(f"   - Token value: {token}")
        print(f"   - Token type: {type(token)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid JWT token in Authorization: Bearer <token> header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify and decode token
    print(f"🔍 Verifying token: {token[:30]}...")
    try:
        payload = verify_access_token(token)
        print(f"✅ Token verified successfully")
        return payload
    except HTTPException as e:
        print(f"❌ Token verification failed: {e.detail}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error during token verification: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_jwt_token_optional(token: Optional[str] = Depends(get_token_from_header)) -> Optional[Dict[str, Any]]:
    """
    Optionally verify JWT token from Authorization header.
    
    This is a FastAPI dependency that validates JWT tokens if provided,
    but allows requests without authentication.
    
    VALIDATION LOGIC:
    1. If token is provided, verifies token signature and expiration
    2. If token is missing, returns None (allows anonymous access)
    3. If token is invalid, raises HTTPException
    
    USAGE:
        @router.post("/endpoint")
        async def my_endpoint(
            request: MyRequest,
            current_user: Optional[dict] = Depends(verify_jwt_token_optional)
        ):
            if current_user:
                user_id = current_user.get("user_id")
                # Handle authenticated user
            else:
                # Handle anonymous user
            # Your logic here
    
    ARGUMENTS:
    - token: JWT token from header (injected by FastAPI dependency)
    
    RETURNS:
    - dict: Decoded token payload if token is valid
    - None: If no token is provided (allows anonymous access)
    
    RAISES:
    - HTTPException 401: If token is provided but invalid or expired
    """
    # If no token provided, allow anonymous access
    if not token:
        print("ℹ️ No token provided - allowing anonymous access")
        return None
    
    # Verify and decode token if provided
    print(f"🔍 Verifying optional token...")
    try:
        payload = verify_access_token(token)
        return payload
    except HTTPException:
        # Re-raise authentication errors
        raise
    except Exception as e:
        # For optional auth, we might want to allow invalid tokens
        # But for security, we'll still reject invalid tokens
        print(f"❌ Error verifying optional token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def refresh_access_token(refresh_token: str) -> Dict[str, str]:
    """
    Generate new access token from refresh token.
    
    Args:
        refresh_token: Valid refresh token
    
    Returns:
        Dictionary with new access_token and refresh_token
    
    Raises:
        HTTPException: If refresh token is invalid
    """
    # Verify refresh token
    payload = verify_refresh_token(refresh_token)
    
    # Extract user data (remove token metadata)
    user_data = {k: v for k, v in payload.items() if k not in ["exp", "iat", "type"]}
    
    # Generate new tokens
    new_access_token = create_access_token(user_data)
    new_refresh_token = create_refresh_token(user_data)
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token
    }

