"""
Simple Background Save Implementation
Safe approach that avoids empty fields issue
"""

import json
from datetime import datetime
from fastapi import BackgroundTasks
from typing import Dict, Any

async def safe_background_save(
    collection,
    user_id: str,
    result_data: Dict[str, Any],
    request_data: Dict[str, Any],
    history_id: str = None
):
    """Safe background save that prevents empty fields"""
    
    try:
        # Serialize all data to prevent empty fields
        serialized_result = json.loads(json.dumps(result_data, default=str))
        serialized_request = json.loads(json.dumps(request_data, default=str))
        
        # Build complete document with ALL required fields
        if history_id:
            # Update existing
            update_doc = {
                "status": "completed",
                "comparison_result": serialized_result,
                "processing_time": serialized_result.get("processing_time", 0),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            await collection.update_one(
                {"_id": ObjectId(history_id), "user_id": user_id},
                {"$set": update_doc}
            )
            print(f"Background update completed for history_id: {history_id}")
            
        else:
            # Create new
            history_doc = {
                "user_id": user_id,
                "name": serialized_request.get("name", "Background Save"),
                "tag": serialized_request.get("tag"),
                "notes": serialized_request.get("notes", ""),
                "products": serialized_request.get("products", []),
                "status": "completed",
                "comparison_result": serialized_result,
                "processing_time": serialized_result.get("processing_time", 0),
                "created_at": datetime.utcnow().isoformat()
            }
            
            await collection.insert_one(history_doc)
            print("Background insert completed")
            
    except Exception as e:
        print(f"Background save failed: {e}")
        # Don't raise - background failures shouldn't affect user experience

# Usage in your endpoint:
@router.post("/compare-products")
async def compare_products_with_background(
    payload: CompareProductsRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token)
):
    user_id = current_user.get("user_id") or current_user.get("_id")
    
    # Create initial record synchronously (for immediate history_id)
    initial_doc = {
        "user_id": user_id,
        "name": payload.get("name", "Processing..."),
        "status": "in_progress",
        "products": payload.get("products", []),
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = await compare_history_col.insert_one(initial_doc)
    history_id = str(result.inserted_id)
    
    try:
        # Main processing
        comparison_result = await process_comparison(payload)
        
        # Add background save task
        background_tasks.add_task(
            safe_background_save,
            collection=compare_history_col,
            user_id=user_id,
            result_data=comparison_result.dict(),
            request_data=payload.dict(),
            history_id=history_id
        )
        
        # Return response with history_id
        response = CompareProductsResponse(**comparison_result.dict())
        response.history_id = history_id
        return response
        
    except Exception as e:
        # Update with error status
        await compare_history_col.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        raise
