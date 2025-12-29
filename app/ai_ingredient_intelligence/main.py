# app/ai_ingredient_intelligence/main.py
from fastapi import FastAPI, HTTPException
from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router
from app.ai_ingredient_intelligence.api.formulation_report import router as formulation_report_router
from app.ai_ingredient_intelligence.api.formula_generation import router as formula_generation_router
from app.ai_ingredient_intelligence.api.distributor_management import router as distributor_management_router
from app.ai_ingredient_intelligence.api.product_comparison import router as product_comparison_router
from app.ai_ingredient_intelligence.api.ingredient_history import router as ingredient_history_router
from app.ai_ingredient_intelligence.api.market_research import router as market_research_router
from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.logic.ocr_processor import OCRProcessor
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(
    title="SkinBB AI Tools - INCI Analysis with OCR + Claude AI", 
    description="AI-powered ingredient analysis for cosmetic products using OCR and Claude AI",
    version="1.0.0",
    debug=True
)

# ✅ CORS Configuration: Allow only your frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tt.skintruth.in", "http://localhost:5174", "http://localhost:5173"],     
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OCR processor
ocr_processor = OCRProcessor()

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint with health check and system status"""
    try:
        # Test MongoDB connection
        await db.command("ping")
        mongo_status = "✅ Connected"
    except Exception as e:
        mongo_status = f"❌ Error: {str(e)}"
    
    # Check environment variables
    env_status = {
        "google_vision": "✅ Set" if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") else "❌ Missing",
        "claude_api": "✅ Set" if os.getenv("CLAUDE_API_KEY") else "❌ Missing",
        "mongo_uri": "✅ Set" if os.getenv("MONGO_URI") else "❌ Missing"
    }
    
    return {
        "status": "SkinBB AI Tools is running! 🚀",
        "version": "1.0.0",
        "features": [
            "OCR Processing with Google Vision API",
            "Ingredient Extraction with Claude AI",
            "Multiple Input Types (PDF, Image, Camera, Text)",
            "Ingredient Matching with MongoDB",
            "Formulation Reports"
        ],
        "database": mongo_status,
        "environment": env_status,
        "docs": "/docs",
        "endpoints": {
            "ocr_analysis": "/api/analyze-inci",
            "formulation_report": "/api/formulation-report",
            "health": "/health"
        }
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check endpoint"""
    try:
        # Test MongoDB
        await db.command("ping")
        mongo_ok = True
        mongo_error = None
    except Exception as e:
        mongo_ok = False
        mongo_error = str(e)
    
    # Test OCR processor
    try:
        # Simple test - just check if it can be initialized
        test_processor = OCRProcessor()
        ocr_ok = True
        ocr_error = None
    except Exception as e:
        ocr_ok = False
        ocr_error = str(e)
    
    return {
        "status": "healthy" if mongo_ok and ocr_ok else "unhealthy",
        "timestamp": "2024-01-01T00:00:00Z",  # You can add datetime.now() here
        "services": {
            "mongodb": {
                "status": "healthy" if mongo_ok else "unhealthy",
                "error": mongo_error
            },
            "ocr_processor": {
                "status": "healthy" if ocr_ok else "unhealthy",
                "error": ocr_error
            }
        },
        "environment": {
            "google_vision_creds": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
            "claude_api_key": bool(os.getenv("CLAUDE_API_KEY")),
            "mongo_uri": bool(os.getenv("MONGO_URI"))
        }
    }

@app.get("/api", tags=["API Info"])
async def api_info():
    """API information and available endpoints"""
    return {
        "name": "SkinBB AI Tools API",
        "version": "1.0.0",
        "description": "AI-powered ingredient analysis for cosmetic products",
        "endpoints": {
            "ocr_analysis": {
                "url": "/api/analyze-inci",
                "method": "POST",
                "description": "Analyze ingredients from PDF, image, camera, or text input",
                "input_types": ["text", "pdf", "image", "camera"]
            },
            "formulation_report": {
                "url": "/api/formulation-report",
                "method": "POST",
                "description": "Generate detailed formulation analysis reports"
            },
            "health_check": {
                "url": "/health",
                "method": "GET",
                "description": "Detailed system health status"
            }
        },
        "documentation": "/docs"
    }

# Include all routers
app.include_router(analyze_inci_router, prefix="/api")
app.include_router(formulation_report_router, prefix="/api")
app.include_router(formula_generation_router, prefix="/api")
app.include_router(distributor_management_router, prefix="/api")
app.include_router(product_comparison_router, prefix="/api")
app.include_router(ingredient_history_router, prefix="/api")
app.include_router(market_research_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.ai_ingredient_intelligence.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
