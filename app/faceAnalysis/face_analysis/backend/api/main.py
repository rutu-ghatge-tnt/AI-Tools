"""
FastAPI Backend for Face Analysis System
Provides REST API endpoints for face analysis and filtering
"""

from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
import json
from pathlib import Path
from typing import Optional, List, Dict
import logging
from datetime import datetime
import uuid

from ..modules.analyzer import FaceAnalyzer
from ..modules.filter import FaceFilter
from ..modules.recommendation import RecommendationEngine
from ..core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router for routes
router = APIRouter()

# Initialize FastAPI app (keep for backward compatibility)
app = FastAPI(
    title="Face Analysis API",
    description="AI-powered facial skin health analysis system",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize modules
analyzer = FaceAnalyzer()
filter_module = FaceFilter()
recommendation_engine = RecommendationEngine()

# Create necessary directories
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.RESULTS_DIR, exist_ok=True)

# Add OPTIONS handler for CORS preflight - must be before other routes
@router.options("/{path:path}")
@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle preflight OPTIONS requests for CORS"""
    return JSONResponse(
        status_code=200,
        content={"message": "OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

# Health check endpoint
@router.get("/")
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Face Analysis API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "analysis": "/analyze",
            "analysis_json": "/analyze/json", 
            "privacy_filter": "/privacy-filter",
            "config": "/config",
            "docs": "/docs"
        }
    }

@router.get("/health")
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Analysis Endpoints
@router.post("/analyze")
@app.post("/analyze")
async def analyze_face(
    file: UploadFile = File(...),
    ethnicity: str = Form(...),
    gender: str = Form(...),
    age: Optional[int] = Form(None)
):
    """Analyze facial skin health from uploaded image"""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Save uploaded file
        file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Perform analysis (use default age for analyzer if not provided)
        analysis_age = age if age is not None else 25
        result = analyzer.analyze_face(file_path, ethnicity, gender, analysis_age)
        
        # Clean up uploaded file
        os.remove(file_path)
        
        return {
            "success": True,
            "analysis": result.get("analysis", {}),
            "overall_score": result.get("overall_score", 0),
            "estimated_age": result.get("estimated_age", "N/A"),
            "estimated_skintype": result.get("estimated_skintype", "N/A"),
            "summary": result.get("summary", ""),
            "analysis_report": result.get("summary", ""),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@router.post("/analyze/json")
@app.post("/analyze/json")
async def analyze_face_json(request: dict):
    """Analyze facial skin health from JSON with base64 image"""
    try:
        image_base64 = request.get("image")
        ethnicity = request.get("ethnicity")
        gender = request.get("gender")
        age = request.get("age")  # Age will be estimated by AI if not provided
        
        if not all([image_base64, ethnicity, gender]):
            raise HTTPException(status_code=400, detail="Missing required fields: image, ethnicity, gender")
        
        # Decode and save image
        import base64
        image_data = base64.b64decode(image_base64)
        file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}_analysis.jpg")
        with open(file_path, "wb") as f:
            f.write(image_data)
        
        # Perform analysis (use default age for analyzer if not provided)
        analysis_age = age if age is not None else 25
        result = analyzer.analyze_face(file_path, ethnicity, gender, analysis_age)
        
        # Clean up uploaded file
        os.remove(file_path)
        
        return {
            "success": True,
            "analysis": result.get("analysis", {}),
            "overall_score": result.get("overall_score", 0),
            "estimated_age": result.get("estimated_age", "N/A"),
            "estimated_skintype": result.get("estimated_skintype", "N/A"),
            "summary": result.get("summary", ""),
            "analysis_report": result.get("summary", ""),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"JSON analysis error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Privacy Filter Endpoints
@router.post("/privacy-filter")
@app.post("/privacy-filter")
async def apply_privacy_filter(file: UploadFile = File(...)):
    """Apply privacy filter to uploaded image"""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Save uploaded file
        file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Apply privacy filter
        filtered_path = filter_module.apply_privacy_filter(file_path)
        
        # Read filtered image and encode as base64
        with open(filtered_path, "rb") as f:
            filtered_image_data = f.read()
        
        import base64
        filtered_base64 = base64.b64encode(filtered_image_data).decode('utf-8')
        
        # Clean up files
        os.remove(file_path)
        os.remove(filtered_path)
        
        return {
            "success": True,
            "filtered_image": filtered_base64,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Privacy filter error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Recommendation Endpoints
@router.post("/recommendations")
@app.post("/recommendations")
async def get_recommendations(request: dict):
    """Get product recommendations based on analysis and budget"""
    try:
        budget = request.get("budget", 0)
        analysis_keywords = request.get("analysis_keywords", [])
        skin_type = request.get("skin_type", "Normal")
        
        if budget <= 0:
            raise HTTPException(status_code=400, detail="Budget must be greater than 0")
        
        # Get recommendations using knapsack algorithm
        recommendations = recommendation_engine.get_recommendations(
            budget=budget,
            analysis_keywords=analysis_keywords,
            skin_type=skin_type
        )
        
        # Get budget summary
        budget_summary = recommendation_engine.get_budget_summary(recommendations, budget)
        
        return {
            "success": True,
            "recommendations": recommendations,
            "budget_summary": budget_summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Recommendation error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Configuration Endpoints
@router.get("/config")
@app.get("/config")
async def get_config():
    """Get application configuration"""
    return {
        "ethnicity_options": settings.ETHNICITY_OPTIONS,
        "gender_options": settings.GENDER_OPTIONS,
        "skin_type_options": settings.SKIN_TYPE_OPTIONS,
        "budget_ranges": settings.BUDGET_RANGES,
        "supported_formats": settings.SUPPORTED_FORMATS,
        "max_file_size": settings.MAX_FILE_SIZE,
        "analysis_parameters": settings.SKIN_ANALYSIS_PARAMETERS
    }

@router.get("/config/analysis-parameters")
@app.get("/config/analysis-parameters")
async def get_analysis_parameters():
    """Get available analysis parameters"""
    return {
        "parameters": [
            {"name": "Hydration", "key": "hydration", "description": "Skin moisture levels"},
            {"name": "Oiliness", "key": "oiliness", "description": "Sebum production"},
            {"name": "Acne", "key": "acne", "description": "Acne presence and severity"},
            {"name": "Dark Circle", "key": "dark_circle", "description": "Under-eye dark circles"},
            {"name": "Wrinkle", "key": "wrinkle", "description": "Fine lines and wrinkles"},
            {"name": "Uneven Skintone", "key": "uneven_skintone", "description": "Skin tone uniformity"}
        ]
    }

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found", "timestamp": datetime.now().isoformat()}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "timestamp": datetime.now().isoformat()}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )