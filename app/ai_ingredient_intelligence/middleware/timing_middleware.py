"""
Timing Middleware for FastAPI
=============================

Automatically tracks execution time for all API endpoints and stores
the data in an Excel file. Groups endpoints by feature for aggregated reporting.

Usage:
    from app.ai_ingredient_intelligence.middleware.timing_middleware import TimingMiddleware
    app.add_middleware(TimingMiddleware)
"""

import time
import os
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from app.ai_ingredient_intelligence.middleware.feature_mapping import get_feature_for_endpoint

# Excel file path
TIMING_EXCEL_FILE = Path("endpoint_timing.xlsx")


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that tracks execution time for all endpoints.
    
    Records:
    - Endpoint path and method
    - Execution time in seconds
    - Timestamp
    - Feature name (based on endpoint path)
    - User ID (if available from JWT)
    - Status code
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip timing for certain paths (docs, health checks, etc.)
        skip_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/health",
        ]
        
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)
        
        # Start timing
        start_time = time.time()
        
        # Extract endpoint info
        method = request.method
        path = request.url.path
        feature = get_feature_for_endpoint(path)
        
        # Try to extract user ID from JWT token (optional - won't fail if not present)
        user_id = None
        try:
            # Try to get token from Authorization header
            auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
            if auth_header and (auth_header.startswith("Bearer ") or auth_header.startswith("bearer ")):
                token = auth_header[7:].strip()
                # Try to decode token without verification (just to get user_id)
                # We don't verify here to avoid performance impact - just extract if possible
                try:
                    import jwt
                    # Decode without verification (just to get user_id for tracking)
                    # This is safe because we're only using it for logging/tracking
                    payload = jwt.decode(token, options={"verify_signature": False})
                    user_id = payload.get("user_id") or payload.get("_id")
                except ImportError:
                    pass  # PyJWT not available, skip user extraction
                except:
                    pass  # If decoding fails, just continue without user_id
        except:
            pass  # If anything fails, just continue without user_id
        
        # Execute the endpoint
        try:
            response = await call_next(request)
            status_code = response.status_code
            error = None
        except Exception as e:
            # If there's an exception, still record the timing
            status_code = 500
            error = str(e)
            raise
        finally:
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Store timing data asynchronously (don't block the response)
            asyncio.create_task(
                self._store_timing_data(
                    method=method,
                    path=path,
                    feature=feature,
                    execution_time=execution_time,
                    status_code=status_code,
                    user_id=user_id,
                    error=error
                )
            )
        
        return response
    
    async def _store_timing_data(
        self,
        method: str,
        path: str,
        feature: str,
        execution_time: float,
        status_code: int,
        user_id: str = None,
        error: str = None
    ):
        """
        Store timing data in Excel file.
        This runs asynchronously and won't block the response.
        Appends a new row to the Excel file.
        """
        try:
            timestamp = datetime.now(timezone.utc)
            
            # Create new row data
            new_row = {
                "timestamp": timestamp.isoformat(),
                "method": method,
                "path": path,
                "feature": feature,
                "execution_time": round(execution_time, 4),
                "status_code": status_code,
                "user_id": user_id or "",
                "error": error or ""
            }
            
            # Run Excel write in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._append_to_excel, new_row)
            
        except Exception as e:
            # Don't fail the request if timing storage fails
            print(f"Warning: Failed to store timing data: {e}")
    
    def _append_to_excel(self, new_row: dict):
        """
        Append a new row to the Excel file.
        Creates the file if it doesn't exist.
        Note: For high concurrency, consider batching writes or using a queue.
        """
        try:
            # Check if file exists
            if TIMING_EXCEL_FILE.exists():
                # Read existing data
                try:
                    df = pd.read_excel(TIMING_EXCEL_FILE, engine='openpyxl')
                    # Ensure all required columns exist
                    required_cols = [
                        "timestamp", "method", "path", "feature", 
                        "execution_time", "status_code", "user_id", "error"
                    ]
                    for col in required_cols:
                        if col not in df.columns:
                            df[col] = ""
                except Exception as e:
                    # If file is corrupted or empty, create new DataFrame
                    print(f"Warning: Error reading Excel file, creating new: {e}")
                    df = pd.DataFrame(columns=[
                        "timestamp", "method", "path", "feature", 
                        "execution_time", "status_code", "user_id", "error"
                    ])
            else:
                # Create new DataFrame with columns
                df = pd.DataFrame(columns=[
                    "timestamp", "method", "path", "feature", 
                    "execution_time", "status_code", "user_id", "error"
                ])
            
            # Append new row
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            # Write back to Excel
            df.to_excel(TIMING_EXCEL_FILE, index=False, engine='openpyxl')
            
        except Exception as e:
            # If file is locked or other error, just log it (don't fail the request)
            print(f"Warning: Could not write timing data to Excel: {e}")
            # Optionally, you could queue this for retry later

