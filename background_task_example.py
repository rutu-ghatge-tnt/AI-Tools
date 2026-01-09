"""
Robust Background Task Implementation Example
This avoids the empty fields issue by proper data serialization
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from bson import ObjectId
import json

class BackgroundTaskManager:
    """Manages background tasks with proper error handling and serialization"""
    
    def __init__(self, db_collections: Dict[str, Any]):
        self.collections = db_collections
        self.task_queue = asyncio.Queue()
        self.running = False
    
    async def start_background_processor(self):
        """Start the background task processor"""
        self.running = True
        while self.running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                await self._process_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Background processor error: {e}")
    
    async def add_save_task(self, 
                           collection_name: str,
                           user_id: str,
                           data: Dict[str, Any],
                           operation: str = "insert"):
        """Add a save task to the queue"""
        task = {
            "operation": operation,
            "collection": collection_name,
            "user_id": user_id,
            "data": self._serialize_data(data),
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": 0
        }
        await self.task_queue.put(task)
    
    def _serialize_data(self, data: Any) -> Dict[str, Any]:
        """Properly serialize data to avoid empty fields"""
        if hasattr(data, 'dict'):
            return data.dict(exclude_none=True)
        elif hasattr(data, 'model_dump'):
            return data.model_dump(exclude_none=True)
        elif isinstance(data, dict):
            # Recursively serialize nested objects
            return {k: self._serialize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._serialize_data(item) for item in data]
        else:
            return data
    
    async def _process_task(self, task: Dict[str, Any]):
        """Process a single background task with retry logic"""
        max_retries = 3
        base_delay = 1.0
        
        while task["retry_count"] < max_retries:
            try:
                collection = self.collections[task["collection"]]
                
                if task["operation"] == "insert":
                    result = await collection.insert_one(task["data"])
                    print(f"Background insert successful: {result.inserted_id}")
                    return
                    
                elif task["operation"] == "update":
                    query = {"_id": ObjectId(task["data"]["_id"])}
                    update_data = {"$set": task["data"]["update_fields"]}
                    result = await collection.update_one(query, update_data)
                    print(f"Background update successful: {result.modified_count} documents")
                    return
                
            except Exception as e:
                task["retry_count"] += 1
                if task["retry_count"] >= max_retries:
                    print(f"Task failed after {max_retries} retries: {e}")
                    # Could add to dead letter queue here
                    return
                
                delay = base_delay * (2 ** task["retry_count"])  # Exponential backoff
                await asyncio.sleep(delay)
                print(f"Retry {task['retry_count']}/{max_retries} after error: {e}")

# Usage in your API endpoints
async def save_comparison_result_background(
    task_manager: BackgroundTaskManager,
    user_id: str,
    comparison_result: Dict[str, Any],
    request_data: Dict[str, Any]
):
    """Background task to save comparison results"""
    
    # Prepare history document with all required fields
    history_doc = {
        "user_id": user_id,
        "name": request_data.get("name", "Untitled Comparison"),
        "tag": request_data.get("tag"),
        "notes": request_data.get("notes", ""),
        "products": request_data.get("products", []),
        "status": "completed",
        "comparison_result": comparison_result,
        "created_at": datetime.utcnow().isoformat(),
        "processing_time": comparison_result.get("processing_time", 0)
    }
    
    await task_manager.add_save_task(
        collection_name="compare_history",
        user_id=user_id,
        data=history_doc,
        operation="insert"
    )

# Example API endpoint usage
async def compare_products_with_background_save(
    payload: CompareProductsRequest,
    current_user: dict = Depends(verify_jwt_token),
    task_manager: BackgroundTaskManager = Depends(get_task_manager)
):
    """Compare products with background save"""
    
    user_id = current_user.get("user_id") or current_user.get("_id")
    
    # 1. Create initial history record synchronously (for immediate feedback)
    initial_history = {
        "user_id": user_id,
        "name": payload.get("name", "Processing..."),
        "status": "in_progress",
        "products": payload.get("products", []),
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Save initial record synchronously to get history_id
    from app.ai_ingredient_intelligence.db.collections import compare_history_col
    result = await compare_history_col.insert_one(initial_history)
    history_id = str(result.inserted_id)
    
    try:
        # 2. Do main processing
        comparison_result = await process_comparison(payload)
        
        # 3. Add background task to update with results
        update_data = {
            "_id": history_id,
            "update_fields": {
                "status": "completed",
                "comparison_result": comparison_result.dict(),
                "processing_time": comparison_result.processing_time,
                "name": payload.get("name", "Comparison Complete")
            }
        }
        
        await task_manager.add_save_task(
            collection_name="compare_history",
            user_id=user_id,
            data=update_data,
            operation="update"
        )
        
        # 4. Return response with history_id
        response = CompareProductsResponse(**comparison_result.dict())
        response.history_id = history_id
        return response
        
    except Exception as e:
        # Update history with error status
        error_update = {
            "_id": history_id,
            "update_fields": {
                "status": "failed",
                "error": str(e),
                "name": payload.get("name", "Failed Comparison")
            }
        }
        
        await task_manager.add_save_task(
            collection_name="compare_history",
            user_id=user_id,
            data=error_update,
            operation="update"
        )
        raise
