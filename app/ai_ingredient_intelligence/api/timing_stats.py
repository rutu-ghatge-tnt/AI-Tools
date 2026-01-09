"""
Timing Statistics API
=====================

API endpoints for retrieving timing statistics grouped by feature.

ENDPOINTS:
- GET /api/timing-stats/features - Get timing stats grouped by feature
- GET /api/timing-stats/endpoints - Get timing stats for individual endpoints
- GET /api/timing-stats/feature/{feature_name} - Get detailed stats for a specific feature
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.middleware.feature_mapping import (
    get_all_features,
    get_endpoints_for_feature
)
from app.ai_ingredient_intelligence.middleware.timing_middleware import TIMING_EXCEL_FILE

router = APIRouter(prefix="/timing-stats", tags=["Timing Statistics"])


class EndpointStats(BaseModel):
    """Statistics for a single endpoint"""
    path: str
    method: str
    count: int
    avg_time: float
    min_time: float
    max_time: float
    total_time: float
    success_count: int
    error_count: int


class FeatureStats(BaseModel):
    """Statistics for a feature (grouped endpoints)"""
    feature: str
    endpoint_count: int
    total_requests: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    success_count: int
    error_count: int
    endpoints: List[EndpointStats]


class TimingStatsResponse(BaseModel):
    """Response model for timing statistics"""
    features: List[FeatureStats]
    summary: Dict[str, Any]


@router.get("/features", response_model=TimingStatsResponse)
async def get_feature_timing_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    feature: Optional[str] = Query(None, description="Filter by specific feature"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get timing statistics grouped by feature.
    
    Returns aggregated timing data for all features, showing:
    - Total requests per feature
    - Average, min, max execution times
    - Success/error counts
    - Breakdown by individual endpoints
    
    QUERY PARAMS:
    - days: Number of days to look back (default: 7, max: 365)
    - feature: Optional filter for specific feature name
    """
    try:
        # Check if Excel file exists
        if not TIMING_EXCEL_FILE.exists():
            return TimingStatsResponse(
                features=[],
                summary={
                    "total_features": 0,
                    "total_requests": 0,
                    "total_time": 0,
                    "avg_time_per_request": 0,
                    "date_range": {
                        "start": datetime.now().isoformat(),
                        "end": datetime.now().isoformat(),
                        "days": days
                    }
                }
            )
        
        # Read Excel file
        df = pd.read_excel(TIMING_EXCEL_FILE)
        
        # Convert timestamp column to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Filter by date range
        df = df[df['timestamp'] >= start_date]
        
        # Filter by feature if specified
        if feature:
            df = df[df['feature'] == feature]
        
        # Convert to records
        records = df.to_dict('records')
        
        # Group by feature
        feature_data: Dict[str, Dict[str, Any]] = {}
        
        for record in records:
            feat = record.get("feature", "Unknown")
            path = record.get("path", "")
            method = record.get("method", "")
            execution_time = float(record.get("execution_time", 0))
            status_code = int(record.get("status_code", 200))
            
            # Initialize feature if not exists
            if feat not in feature_data:
                feature_data[feat] = {
                    "endpoints": {},
                    "total_requests": 0,
                    "total_time": 0,
                    "times": [],
                    "success_count": 0,
                    "error_count": 0
                }
            
            # Update feature stats
            feature_data[feat]["total_requests"] += 1
            feature_data[feat]["total_time"] += execution_time
            feature_data[feat]["times"].append(execution_time)
            
            if status_code < 400:
                feature_data[feat]["success_count"] += 1
            else:
                feature_data[feat]["error_count"] += 1
            
            # Update endpoint stats
            endpoint_key = f"{method} {path}"
            if endpoint_key not in feature_data[feat]["endpoints"]:
                feature_data[feat]["endpoints"][endpoint_key] = {
                    "path": path,
                    "method": method,
                    "count": 0,
                    "total_time": 0,
                    "times": [],
                    "success_count": 0,
                    "error_count": 0
                }
            
            endpoint = feature_data[feat]["endpoints"][endpoint_key]
            endpoint["count"] += 1
            endpoint["total_time"] += execution_time
            endpoint["times"].append(execution_time)
            
            if status_code < 400:
                endpoint["success_count"] += 1
            else:
                endpoint["error_count"] += 1
        
        # Build response
        feature_stats_list = []
        total_requests = 0
        total_time_all = 0
        
        for feat_name, data in sorted(feature_data.items()):
            times = data["times"]
            if not times:
                continue
            
            # Calculate endpoint stats
            endpoint_stats = []
            for endpoint_key, endpoint_data in sorted(data["endpoints"].items()):
                endpoint_times = endpoint_data["times"]
                endpoint_stats.append(EndpointStats(
                    path=endpoint_data["path"],
                    method=endpoint_data["method"],
                    count=endpoint_data["count"],
                    avg_time=endpoint_data["total_time"] / endpoint_data["count"],
                    min_time=min(endpoint_times),
                    max_time=max(endpoint_times),
                    total_time=endpoint_data["total_time"],
                    success_count=endpoint_data["success_count"],
                    error_count=endpoint_data["error_count"]
                ))
            
            feature_stats_list.append(FeatureStats(
                feature=feat_name,
                endpoint_count=len(endpoint_stats),
                total_requests=data["total_requests"],
                total_time=data["total_time"],
                avg_time=data["total_time"] / data["total_requests"],
                min_time=min(times),
                max_time=max(times),
                success_count=data["success_count"],
                error_count=data["error_count"],
                endpoints=endpoint_stats
            ))
            
            total_requests += data["total_requests"]
            total_time_all += data["total_time"]
        
        # Summary
        summary = {
            "total_features": len(feature_stats_list),
            "total_requests": total_requests,
            "total_time": total_time_all,
            "avg_time_per_request": total_time_all / total_requests if total_requests > 0 else 0,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            }
        }
        
        return TimingStatsResponse(
            features=feature_stats_list,
            summary=summary
        )
    
    except Exception as e:
        print(f"Error getting timing stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving timing statistics: {str(e)}"
        )


@router.get("/feature/{feature_name}")
async def get_feature_detail(
    feature_name: str,
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get detailed timing statistics for a specific feature.
    
    Returns the same data as /features but filtered to a single feature.
    """
    return await get_feature_timing_stats(days=days, feature=feature_name, current_user=current_user)


@router.get("/endpoints")
async def get_endpoint_timing_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    path: Optional[str] = Query(None, description="Filter by endpoint path"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get timing statistics for individual endpoints (not grouped by feature).
    
    Useful for seeing which specific endpoints are slowest.
    """
    try:
        # Check if Excel file exists
        if not TIMING_EXCEL_FILE.exists():
            return {
                "endpoints": [],
                "count": 0,
                "date_range": {
                    "start": datetime.now().isoformat(),
                    "end": datetime.now().isoformat(),
                    "days": days
                }
            }
        
        # Read Excel file
        df = pd.read_excel(TIMING_EXCEL_FILE)
        
        # Convert timestamp column to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Filter by date range
        df = df[df['timestamp'] >= start_date]
        
        # Filter by path if specified
        if path:
            df = df[df['path'].str.contains(path, case=False, na=False)]
        
        # Group by endpoint and calculate stats
        grouped = df.groupby(['path', 'method']).agg({
            'execution_time': ['count', 'sum', 'mean', 'min', 'max'],
            'status_code': lambda x: (x < 400).sum()  # success count
        }).reset_index()
        
        # Flatten column names
        grouped.columns = ['path', 'method', 'count', 'total_time', 'avg_time', 'min_time', 'max_time', 'success_count']
        
        # Calculate error count
        grouped['error_count'] = grouped['count'] - grouped['success_count']
        
        # Sort by total_time descending
        grouped = grouped.sort_values('total_time', ascending=False)
        
        # Convert to list of dicts
        endpoints = []
        for _, row in grouped.iterrows():
            endpoints.append({
                "path": row['path'],
                "method": row['method'],
                "count": int(row['count']),
                "avg_time": round(row['avg_time'], 4),
                "min_time": round(row['min_time'], 4),
                "max_time": round(row['max_time'], 4),
                "total_time": round(row['total_time'], 4),
                "success_count": int(row['success_count']),
                "error_count": int(row['error_count'])
            })
        
        return {
            "endpoints": endpoints,
            "count": len(endpoints),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            }
        }
    
    except Exception as e:
        print(f"Error getting endpoint timing stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving endpoint timing statistics: {str(e)}"
        )

