"""
Dashboard Stats API Endpoint
============================

API endpoint that returns counts for dashboard tabs:
- Wishes: Count from wish_history collection
- Decodes: Count from decode_history collection
- Compared: Count from compare_history collection
- Saved: Count from inspiration_products collection
- Calculated: Count from cost_calculator_history collection (if exists, else 0)

ENDPOINT: GET /api/dashboard/stats
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.db.collections import (
    wish_history_col,
    decode_history_col,
    compare_history_col,
    inspiration_products_col
)
from app.ai_ingredient_intelligence.db.mongodb import db

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class DashboardStatsResponse(BaseModel):
    """Response schema for dashboard stats"""
    wishes: int = Field(..., description="Number of wishes created")
    decodes: int = Field(..., description="Number of formulations decoded")
    compared: int = Field(..., description="Number of products compared")
    saved: int = Field(..., description="Number of products saved to inspiration boards")
    calculated: int = Field(..., description="Number of cost calculations performed")


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get dashboard statistics (counts) for all tabs
    
    Returns counts for:
    - Wishes: Number of wishes created by the user
    - Decodes: Number of formulations decoded by the user
    - Compared: Number of product comparisons performed by the user
    - Saved: Number of products saved to inspiration boards by the user
    - Calculated: Number of cost calculations performed by the user
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    
    Response:
    {
        "wishes": 6,
        "decodes": 12,
        "compared": 5,
        "saved": 24,
        "calculated": 8
    }
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
            )
        
        # Count wishes
        wishes_count = await wish_history_col.count_documents({"user_id": user_id})
        
        # Count decodes
        decodes_count = await decode_history_col.count_documents({"user_id": user_id})
        
        # Count compares
        compared_count = await compare_history_col.count_documents({"user_id": user_id})
        
        # Count saved products (from inspiration boards)
        saved_count = await inspiration_products_col.count_documents({"user_id": user_id})
        
        # Count calculated (cost calculator history)
        # Check if cost_calculator_history collection exists
        calculated_count = 0
        try:
            cost_calculator_history_col = db["cost_calculator_history"]
            calculated_count = await cost_calculator_history_col.count_documents({"user_id": user_id})
        except Exception:
            # Collection doesn't exist yet, return 0
            calculated_count = 0
        
        return DashboardStatsResponse(
            wishes=wishes_count,
            decodes=decodes_count,
            compared=compared_count,
            saved=saved_count,
            calculated=calculated_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get dashboard stats: {str(e)}"
        )

