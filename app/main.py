# Suppress warnings before any imports
import os
import sys
import warnings
import logging

# Suppress TensorFlow/MediaPipe warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['ABSL_MIN_LOG_LEVEL'] = '2'
logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('absl').setLevel(logging.ERROR)
warnings.filterwarnings('ignore', message='.*Feedback manager.*')
warnings.filterwarnings('ignore', category=UserWarning, module='langchain')

from fastapi import FastAPI
from app.chatbot.api import router as api_router
from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router   # ✅ import here
from app.ai_ingredient_intelligence.api.formulation_report import router as formulation_report_router
# from app.product_listing_image_extraction.route import router as image_extractor_router  # Commented out - module doesn't exist
from pathlib import Path

# Add Face Analysis path to Python path
face_analysis_path = Path(__file__).parent / "faceAnalysis"
sys.path.insert(0, str(face_analysis_path))

# Import Face Analysis router
from face_analysis.backend.api.main import router as face_analysis_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SkinBB AI Skincare Chatbot",
    description="An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0"
)

# ✅ CORS - Updated for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tt.skintruth.in", 
        "https://capi.skintruth.in",
        "http://localhost:5174", 
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8501",
        "https://metaverse.skinbb.com"
    ],     
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ✅ Existing chatbot API
app.include_router(api_router, prefix="/api")

# ✅ Add analyze-inci API
app.include_router(analyze_inci_router, prefix="/api")   # <--- added

# ✅ Add formulation report API
app.include_router(formulation_report_router, prefix="/api")

# ✅ New image-to-JSON API - Commented out - module doesn't exist
# app.include_router(image_extractor_router, prefix="/api")

# ✅ Face Analysis API - Include router instead of mounting
app.include_router(face_analysis_router, prefix="/api/face-analysis", tags=["Face Analysis"])

@app.get("/")
async def root():
    return {"message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact v1."}

@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy", 
        "message": "Server is running",
        "endpoints": {
            "api_docs": "/docs",
            "server_health": "/api/server-health",
            "test_selenium": "/api/test-selenium"
        }
    }
