"""
Ingredient History Management API Endpoints
==========================================

API endpoints for managing ingredient analysis history and comparison history.
Extracted from analyze_inci.py for better modularity.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import re
import uuid

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.db.collections import decode_history_col, compare_history_col
from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
from app.ai_ingredient_intelligence.models.schemas import (
    DecodeHistoryItem,
    DecodeHistoryItemSummary,
    GetDecodeHistoryResponse,
    DecodeHistoryDetailResponse,
    CompareHistoryItem,
    CompareHistoryItemSummary,
    GetCompareHistoryResponse,
    CompareHistoryDetailResponse,
)

router = APIRouter(tags=["Ingredient History"])


# ========== DECODE HISTORY ENDPOINTS ==========

@router.post("/save-decode-history")
async def save_decode_history(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    ⚠️ DEPRECATED: This endpoint is no longer needed!
    
    Auto-save functionality is now built into:
    - /analyze-inci - automatically saves history
    - /analyze-url - automatically saves history  
    - /formulation-report-json - automatically saves history
    - /analyze-inci-with-report - automatically saves history (NEW MERGED ENDPOINT - USE THIS!)
    
    This endpoint is kept for backward compatibility only. Please use the endpoints above
    which handle history saving automatically - no need to call this endpoint separately.
    
    Create a decode history item with "in_progress" status (for frontend to track pending analyses)
    
    This endpoint allows the frontend to create a history item upfront before analysis starts.
    The history item will be updated later by /analyze-inci or /analyze-url endpoints when analysis completes.
    
    HISTORY FUNCTIONALITY:
    - Creates a history item with "in_progress" status
    - Returns the MongoDB ObjectId (not UUID) for use in subsequent PATCH requests
    - History is user-specific and isolated by user_id
    - Supports status tracking: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Name and tags can be edited later using PATCH /decode-history/{history_id}
    - Input data (INCI or URL) cannot be changed after creation
    - History items can be searched by name or tag
    - History persists across sessions and page refreshes
    
    Request body:
    {
        "name": "Product Name",
        "tag": "optional-tag",
        "input_type": "inci" or "url",
        "input_data": "ingredient list or URL",
        "notes": "optional notes",
        "status": "in_progress" (default, can also be "completed" or "failed")
    }
    
    Returns:
    {
        "success": True,
        "id": "MongoDB ObjectId string (24 hex characters)",
        "message": "History item created successfully"
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token
        user_id_value = current_user.get("user_id") or current_user.get("_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Extract payload fields - name is required
        name = payload.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        # Truncate name if too long
        if len(name) > 100:
            name = name[:97] + "..."
        
        # Validate required fields
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["inci", "url"]:
            raise HTTPException(status_code=400, detail="input_type must be 'inci' or 'url'")
        
        input_data = payload.get("input_data", "").strip()
        if not input_data:
            raise HTTPException(status_code=400, detail="input_data is required")
        
        # Get status (default to "in_progress" for new items)
        status = payload.get("status", "in_progress")
        if status not in ["in_progress", "completed", "failed"]:
            status = "in_progress"
        
        # Create history document
        history_doc = {
            "user_id": user_id_value,
            "name": name,
            "tag": payload.get("tag"),
            "notes": payload.get("notes", ""),
            "input_type": input_type,
            "input_data": input_data,
            "status": status,
            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        
        # Only include analysis_result if status is "completed"
        if status == "completed" and "analysis_result" in payload:
            history_doc["analysis_result"] = payload.get("analysis_result")
        
        # Insert into database
        result = await decode_history_col.insert_one(history_doc)
        history_id = str(result.inserted_id)
        
        print(f"[HISTORY] Created new decode history item: {history_id} for user {user_id_value}, name: {name}, status: {status}")
        
        return {
            "success": True,
            "id": history_id,  # Return MongoDB ObjectId (not UUID)
            "message": "History item created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create decode history: {str(e)}"
        )


@router.get("/decode-history", response_model=GetDecodeHistoryResponse)
async def get_decode_history(
    search: Optional[str] = Query(None),
    limit: int = Query(50),
    skip: int = Query(0),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get decode history with optional unified search by name or tag (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Returns all decode history items for the authenticated user
    - Status field indicates: "pending" (analysis in progress), "analyzed" (completed), or "failed"
    - Frontend can use status to determine if analysis is complete or still pending
    - If page refreshes before analysis completes, status="pending" indicates input is preserved
    - Items with status="pending" will have analysis_result=None
    - Supports pagination with limit and skip parameters
    - Search works across both name and tag fields
    
    Query parameters:
    - search: Search term for name or tag (optional, searches both)
    - limit: Number of results (default: 50)
    - skip: Number of results to skip (default: 0)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Build query - ALWAYS filter by user_id
        query = {"user_id": user_id}
        
        # Unified search: search both name and tag
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"tag": {"$regex": search, "$options": "i"}}
            ]
        
        # Get total count
        total = await decode_history_col.count_documents(query)
        
        # Fetch items - only get summary fields (exclude large fields)
        cursor = decode_history_col.find(
            query,
            {
                "_id": 1,
                "user_id": 1,
                "name": 1,
                "tag": 1,
                "input_type": 1,
                "input_data": 1,
                "status": 1,
                "notes": 1,
                "created_at": 1,
                "analysis_result": 1,  # Check if exists, but don't return full data
                "report_data": 1  # Check if exists, but don't return full data
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert to summary format (exclude large fields)
        summary_items = []
        for item in items:
            item_id = str(item["_id"])
            del item["_id"]
            
            # Map status for frontend: "in_progress" -> "pending", "completed" -> "analyzed"
            status_mapping = {
                "in_progress": "pending",
                "pending": "pending",  # Handle if already mapped
                "completed": "analyzed",
                "failed": "failed"
            }
            raw_status = item.get("status")
            if raw_status:
                status = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
            else:
                status = "pending"  # Default to pending if status is missing (likely in progress)
            
            # Truncate input_data for preview (max 100 chars)
            # Handle both string and list formats (some old data might be stored as list)
            input_data_raw = item.get("input_data", "")
            if isinstance(input_data_raw, list):
                input_data = ", ".join(str(x) for x in input_data_raw if x)
            elif isinstance(input_data_raw, str):
                input_data = input_data_raw
            else:
                input_data = str(input_data_raw) if input_data_raw else ""
            
            if input_data and len(input_data) > 100:
                input_data = input_data[:100] + "..."
            
            summary_item = {
                "id": item_id,
                "user_id": item.get("user_id"),
                "name": item.get("name", ""),
                "tag": item.get("tag"),
                "input_type": item.get("input_type", ""),
                "input_data": input_data,
                "status": status,
                "notes": item.get("notes"),
                "created_at": item.get("created_at"),
                "has_analysis": item.get("analysis_result") is not None and status == "analyzed",
                "has_report": item.get("report_data") is not None and status == "analyzed"
            }
            summary_items.append(summary_item)
        
        return GetDecodeHistoryResponse(
            items=[DecodeHistoryItemSummary(**item) for item in summary_items],
            total=total
        )
        
    except Exception as e:
        print(f"Error fetching decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch decode history: {str(e)}"
        )


@router.get("/decode-history/{history_id}/details", response_model=DecodeHistoryDetailResponse)
async def get_decode_history_detail(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get full details of a specific decode history item (includes all large fields)
    
    This endpoint returns the complete data including:
    - Full analysis_result (large Dict)
    - Full report_data (large HTML string)
    - All other fields
    
    Use this endpoint when you need to display the full analysis or report.
    The list endpoint (/decode-history) only returns summaries.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Fetch full item (including large fields)
        item = await decode_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Convert ObjectId to string
        item["id"] = str(item["_id"])
        del item["_id"]
        
        # Ensure all fields are included
        if "report_data" not in item:
            item["report_data"] = ""
        if "analysis_result" not in item:
            item["analysis_result"] = {}
        
        # Map status for frontend
        status_mapping = {
            "in_progress": "pending",
            "pending": "pending",  # Handle if already mapped
            "completed": "analyzed",
            "failed": "failed"
        }
        raw_status = item.get("status")
        if raw_status:
            item["status"] = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
        else:
            item["status"] = "pending"  # Default to pending if status is missing (likely in progress)
        
        # Ensure analysis_result and report_data are empty (not null) if status is pending or failed
        if item.get("status") in ["pending", "failed"]:
            item["analysis_result"] = {}
            item["report_data"] = ""
        
        # Handle input_data - convert list to string if needed (for backward compatibility with old data)
        input_data_raw = item.get("input_data", "")
        if isinstance(input_data_raw, list):
            item["input_data"] = ", ".join(str(x) for x in input_data_raw if x)
        elif not isinstance(input_data_raw, str):
            item["input_data"] = str(input_data_raw) if input_data_raw else ""
        
        # Normalize analysis_result to ensure all items have supplier_id field
        # This ensures backward compatibility with old data that might not have supplier_id
        if item.get("analysis_result") and isinstance(item["analysis_result"], dict):
            analysis_result = item["analysis_result"]
            if "detected" in analysis_result and isinstance(analysis_result["detected"], list):
                for group in analysis_result["detected"]:
                    if isinstance(group, dict) and "items" in group and isinstance(group["items"], list):
                        for item_data in group["items"]:
                            if isinstance(item_data, dict):
                                # Ensure supplier_id is present (set to None if missing)
                                if "supplier_id" not in item_data:
                                    item_data["supplier_id"] = None
                                # Also ensure ingredient_id and supplier_name are present for consistency
                                if "ingredient_id" not in item_data:
                                    item_data["ingredient_id"] = None
                                if "supplier_name" not in item_data:
                                    item_data["supplier_name"] = None
        
        return DecodeHistoryDetailResponse(
            item=DecodeHistoryItem(**item)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching decode history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch decode history detail: {str(e)}"
        )


@router.patch("/decode-history/{history_id}")
async def update_decode_history(
    history_id: str,
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update a decode history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating analysis results, report data, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the decode history item
    - tag: Update or add a categorization tag
    - notes: Update user notes
    - input_data: Update input data (for regeneration)
    - input_type: Update input type (for regeneration)
    - report_data: Update report data (for regeneration)
    - status: Update status (for regeneration)
    - analysis_result: Update analysis result (for regeneration)
    - expected_benefits: Update expected benefits (for regeneration)
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId - check if it's a valid MongoDB ObjectId format
        # MongoDB ObjectIds are 24-character hex strings (no dashes)
        # UUIDs have dashes and are 36 characters, so we can detect them
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        if uuid_pattern.match(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format: UUID detected. The decode history uses MongoDB ObjectIds (24 hex characters, no dashes). Please use the ObjectId returned from the backend when creating/retrieving history items. Received UUID: {history_id}"
            )
        
        if not ObjectId.is_valid(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format. Expected MongoDB ObjectId (24 hex characters), got: {history_id[:50]}"
            )
        
        # Build update document - allow all fields except user_id and created_at
        update_doc = {}
        excluded_fields = ["user_id", "created_at", "_id"]  # These should never be updated
        
        for key, value in payload.items():
            if key not in excluded_fields:
                update_doc[key] = value
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Only update if it belongs to the user
        result = await decode_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to update it")
        
        return {
            "success": True,
            "message": "History updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update decode history: {str(e)}"
        )


@router.delete("/decode-history/{history_id}")
async def delete_decode_history(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Delete a decode history item by ID (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Permanently deletes a decode history item from user's history
    - Only the owner (matching user_id) can delete their own history items
    - Deletion is permanent and cannot be undone
    - Useful for cleaning up old or unwanted history items
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Only delete if it belongs to the user
        result = await decode_history_col.delete_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to delete it")
        
        return {
            "success": True,
            "message": "History item deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting decode history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete decode history: {str(e)}"
        )


# ========== COMPARE HISTORY ENDPOINTS ==========

@router.post("/save-compare-history")
async def save_compare_history(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    [DISABLED] Save compare history with name and tag (user-specific)
    Supports both 2-product and multi-product comparisons
    
    ⚠️ THIS ENDPOINT IS CURRENTLY DISABLED TO PREVENT DUPLICATE SAVES ⚠️
    This endpoint returns success but does not save to prevent duplicates.
    
    HISTORY FUNCTIONALITY:
    - All product comparison operations should be automatically saved by compare endpoints
    - History is user-specific and isolated by user_id
    - Supports status tracking: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Name and tags can be used for organization and categorization
    - History items can be searched by name or tag
    - History persists across sessions and page refreshes
    - Supports both 2-product (input1/input2) and multi-product (products array) comparisons
    
    Request body (2-product format - backward compatible):
    {
        "name": "Comparison Name",
        "tag": "optional-tag",
        "input1": "URL or INCI",
        "input2": "URL or INCI",
        "input1_type": "url" or "inci",
        "input2_type": "url" or "inci",
        "comparison_result": {...} (optional if status is "in_progress"),
        "status": "in_progress" | "completed" | "failed" (default: "completed")
    }
    
    Request body (multi-product format):
    {
        "name": "Comparison Name",
        "tag": "optional-tag",
        "products": [
            {"input": "URL or INCI", "input_type": "url" or "inci"},
            {"input": "URL or INCI", "input_type": "url" or "inci"},
            ...
        ],
        "comparison_result": {...} (optional if status is "in_progress"),
        "status": "in_progress" | "completed" | "failed" (default: "completed")
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # ⚠️ ENDPOINT DISABLED - Return success without saving to prevent duplicates
        # Extract user_id and name for logging (do minimal validation to prevent crashes)
        user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
        name = payload.get("name", "Unknown")
        
        # Log that this endpoint was called but is disabled
        print(f"⚠️ [DISABLED] /save-compare-history called for user {user_id_value}, name: {name}")
        print(f"   This endpoint is disabled to prevent duplicate saves.")
        
        # Return success response without actually saving
        # Generate a dummy ID for frontend compatibility
        dummy_id = str(uuid.uuid4())
        
        return {
            "success": True,
            "id": dummy_id,
            "message": "Compare history save endpoint disabled - use compare endpoints which auto-save"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in disabled save-compare-history endpoint: {e}")
        # Still return success to prevent frontend crashes
        return {
            "success": True,
            "id": str(uuid.uuid4()),
            "message": "Compare history save endpoint disabled - use compare endpoints which auto-save"
        }


@router.get("/compare-history", response_model=GetCompareHistoryResponse)
async def get_compare_history(
    search: Optional[str] = Query(None),
    limit: int = Query(50),
    skip: int = Query(0),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get compare history with optional unified search by name or tag (user-specific)
    
    HISTORY FUNCTIONALITY:
    - Returns all comparison history items for the authenticated user
    - Status field indicates: "in_progress" (pending), "completed" (analyzed), or "failed"
    - Frontend can use status to determine if comparison is complete or still pending
    - If page refreshes before comparison completes, status="in_progress" indicates inputs are preserved
    - Items with status="in_progress" will have comparison_result=None
    - Supports pagination with limit and skip parameters
    - Search works across both name and tag fields
    
    Query parameters:
    - search: Search term for name or tag (optional, searches both)
    - limit: Number of results (default: 50)
    - skip: Number of results to skip (default: 0)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Build query - ALWAYS filter by user_id
        query = {"user_id": user_id}
        
        # Unified search: search both name and tag
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"tag": {"$regex": search, "$options": "i"}}
            ]
        
        # Get total count
        total = await compare_history_col.count_documents(query)
        
        # Fetch items - only get summary fields (exclude large fields)
        cursor = compare_history_col.find(
            query,
            {
                "_id": 1,
                "user_id": 1,
                "name": 1,
                "tag": 1,
                "input1": 1,
                "input2": 1,
                "input1_type": 1,
                "input2_type": 1,
                "products": 1,
                "status": 1,
                "notes": 1,
                "created_at": 1,
                "comparison_result": 1  # Check if exists, but don't return full data
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert to summary format (exclude large fields and normalize to products array)
        summary_items = []
        for item in items:
            item_id = str(item["_id"])
            del item["_id"]
            
            # Map status for frontend: "in_progress" -> "pending", "completed" -> "analyzed"
            status_mapping = {
                "in_progress": "pending",
                "pending": "pending",  # Handle if already mapped
                "completed": "analyzed",
                "failed": "failed"
            }
            raw_status = item.get("status")
            if raw_status:
                status = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
            else:
                status = "pending"  # Default to pending if status is missing (likely in progress)
            
            # Normalize to products array format (convert input1/input2 if present)
            products = item.get("products")
            if not products or not isinstance(products, list):
                # Convert legacy input1/input2 to products array
                products = []
                if item.get("input1") and item.get("input1_type"):
                    products.append({
                        "input": item["input1"],
                        "input_type": item["input1_type"]
                    })
                if item.get("input2") and item.get("input2_type"):
                    products.append({
                        "input": item["input2"],
                        "input_type": item["input2_type"]
                    })
            
            # Truncate products inputs for preview (max 100 chars)
            product_count = len(products) if products else 0
            truncated_products = []
            for product in products:
                if isinstance(product, dict):
                    truncated_product = product.copy()
                    if "input" in truncated_product and truncated_product["input"]:
                        input_val = truncated_product["input"]
                        if len(input_val) > 100:
                            truncated_product["input"] = input_val[:100] + "..."
                    truncated_products.append(truncated_product)
            
            summary_item = {
                "id": item_id,
                "user_id": item.get("user_id"),
                "name": item.get("name", ""),
                "tag": item.get("tag"),
                "products": truncated_products,
                "status": status,
                "notes": item.get("notes"),
                "created_at": item.get("created_at"),
                "has_comparison": item.get("comparison_result") is not None and status == "analyzed",
                "product_count": product_count
            }
            summary_items.append(summary_item)
        
        return GetCompareHistoryResponse(
            items=[CompareHistoryItemSummary(**item) for item in summary_items],
            total=total
        )
        
    except Exception as e:
        print(f"Error fetching compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch compare history: {str(e)}"
        )


@router.get("/compare-history/{history_id}/details", response_model=CompareHistoryDetailResponse)
async def get_compare_history_detail(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get full details of a specific compare history item (includes all large fields)
    
    This endpoint returns the complete data including:
    - Full comparison_result (large Dict with all comparison data)
    - All other fields
    
    Use this endpoint when you need to display the full comparison results.
    The list endpoint (/compare-history) only returns summaries.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Fetch full item (including large fields)
        item = await compare_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Convert ObjectId to string
        item["id"] = str(item["_id"])
        del item["_id"]
        
        # Ensure all fields are included
        if "comparison_result" not in item:
            item["comparison_result"] = None
        
        # Normalize to products array format (convert input1/input2 if present)
        products = item.get("products")
        if not products or not isinstance(products, list):
            # Convert legacy input1/input2 to products array
            products = []
            if item.get("input1") and item.get("input1_type"):
                products.append({
                    "input": item["input1"],
                    "input_type": item["input1_type"]
                })
            if item.get("input2") and item.get("input2_type"):
                products.append({
                    "input": item["input2"],
                    "input_type": item["input2_type"]
                })
        
        # Remove legacy fields and set normalized products array
        item["products"] = products
        # Remove input1/input2 fields from response (redundant)
        item.pop("input1", None)
        item.pop("input2", None)
        item.pop("input1_type", None)
        item.pop("input2_type", None)
        
        # Map status for frontend
        status_mapping = {
            "in_progress": "pending",
            "pending": "pending",  # Handle if already mapped
            "completed": "analyzed",
            "failed": "failed"
        }
        raw_status = item.get("status")
        if raw_status:
            item["status"] = status_mapping.get(raw_status, raw_status)  # Keep original if not in mapping
        else:
            item["status"] = "pending"  # Default to pending if status is missing (likely in progress)
        
        # Ensure comparison_result is None if status is pending or failed
        if item.get("status") in ["pending", "failed"]:
            item["comparison_result"] = None
        
        return CompareHistoryDetailResponse(
            item=CompareHistoryItem(**item)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching compare history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch compare history detail: {str(e)}"
        )


@router.patch("/compare-history/{history_id}")
async def update_compare_history(
    history_id: str, 
    payload: dict, 
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update a compare history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating comparison results, input data, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the compare history item
    - tag: Update or add a categorization tag
    - notes: Update user notes
    - input1: Update input1 (URL or INCI) - for 2-product comparisons (for regeneration)
    - input2: Update input2 (URL or INCI) - for 2-product comparisons (for regeneration)
    - input1_type: Update input1_type - for 2-product comparisons (for regeneration)
    - input2_type: Update input2_type - for 2-product comparisons (for regeneration)
    - products: Update products array - for multi-product comparisons (for regeneration)
    - status: Update status (for regeneration)
    - comparison_result: Update comparison result (for regeneration)
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Build update document - allow all fields except user_id and created_at
        update_doc = {}
        excluded_fields = ["user_id", "created_at", "_id"]  # These should never be updated
        
        for key, value in payload.items():
            if key not in excluded_fields:
                update_doc[key] = value
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Only update if it belongs to the user
        result = await compare_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to update it")
        
        return {
            "success": True,
            "message": "History updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update compare history: {str(e)}"
        )


@router.delete("/compare-history/{history_id}")
async def delete_compare_history(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Delete a compare history item by ID (user-specific)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Only delete if it belongs to the user
        result = await compare_history_col.delete_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to delete it")
        
        return {
            "success": True,
            "message": "Compare history item deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting compare history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete compare history: {str(e)}"
        )

