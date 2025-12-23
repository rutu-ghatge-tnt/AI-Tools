# Suppress warnings before any imports
import os
import sys
import warnings
import logging

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Suppress TensorFlow/MediaPipe warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['ABSL_MIN_LOG_LEVEL'] = '2'
logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('absl').setLevel(logging.ERROR)
warnings.filterwarnings('ignore', message='.*Feedback manager.*')
warnings.filterwarnings('ignore', category=UserWarning, module='langchain')

logger = logging.getLogger(__name__)

# Run startup validation
try:
    from app.core.startup_validation import validate_startup
    is_valid, validation_results = validate_startup()
    
    if validation_results['errors']:
        logger.error("❌ Startup validation failed with errors:")
        for error in validation_results['errors']:
            logger.error(f"  - {error}")
        # Don't crash, but log the errors
    
    if validation_results['warnings']:
        logger.warning("⚠️  Startup validation warnings:")
        for warning in validation_results['warnings']:
            logger.warning(f"  - {warning}")
    
    if validation_results['info']:
        logger.info("ℹ️  Startup validation info:")
        for info in validation_results['info'][:5]:  # Limit to first 5
            logger.info(f"  - {info}")
except Exception as e:
    logger.warning(f"⚠️  Startup validation failed: {e}. Continuing anyway...")

from fastapi import FastAPI

# Import chatbot router (with error handling for missing dependencies)
try:
    from app.chatbot.api import router as api_router
    logger.info("✅ Chatbot router loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️  Could not import chatbot router: {e}")
    logger.warning("   Chatbot API will not be available. This is not critical.")
    api_router = None
except Exception as e:
    logger.error(f"❌ Unexpected error importing chatbot router: {e}", exc_info=True)
    api_router = None

# Import analyze_inci router (critical - should always be available)
try:
    from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router
    logger.info("✅ Analyze INCI router loaded successfully")
except Exception as e:
    logger.error(f"❌ Critical: Could not import analyze_inci router: {e}", exc_info=True)
    analyze_inci_router = None

# Import formulation report router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.formulation_report import router as formulation_report_router
    logger.info("✅ Formulation report router loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️  Could not import formulation_report router: {e}")
    logger.warning("   Formulation Report API will not be available. This is not critical.")
    formulation_report_router = None
except Exception as e:
    logger.error(f"❌ Unexpected error importing formulation_report router: {e}", exc_info=True)
    formulation_report_router = None

# Import cost calculator and ingredient search routers (should be available)
try:
    from app.ai_ingredient_intelligence.api.cost_calculator import router as cost_calculator_router
    from app.ai_ingredient_intelligence.api.ingredient_search import router as ingredient_search_router
    logger.info("✅ Cost calculator and ingredient search routers loaded successfully")
except Exception as e:
    logger.error(f"❌ Could not import cost_calculator or ingredient_search routers: {e}", exc_info=True)
    cost_calculator_router = None
    ingredient_search_router = None

# Import Formula Generation router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.formula_generation import router as formula_generation_router
    logger.info("✅ Formula generation router loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️  Could not import formula_generation router: {e}")
    logger.warning("   Formula Generation API will not be available. This is not critical.")
    formula_generation_router = None
except Exception as e:
    logger.error(f"❌ Unexpected error importing formula_generation router: {e}", exc_info=True)
    formula_generation_router = None

# Import Make a Wish router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.make_wish_api import router as make_wish_router
    logger.info("✅ Make a Wish router loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️  Could not import make_wish router: {e}")
    logger.warning("   Make a Wish API will not be available. This is not critical.")
    make_wish_router = None
except Exception as e:
    logger.error(f"❌ Unexpected error importing make_wish router: {e}", exc_info=True)
    make_wish_router = None
# from app.product_listing_image_extraction.route import router as image_extractor_router  # Commented out - module doesn't exist
from pathlib import Path

# Add Face Analysis path to Python path
face_analysis_path = Path(__file__).parent / "faceAnalysis"
sys.path.insert(0, str(face_analysis_path))

# Import Face Analysis router (with error handling for missing module)
# Face Analysis uses MediaPipe which is heavy - make it optional
face_analysis_router = None
try:
    # Use lazy import to prevent MediaPipe from loading at startup
    from app.core.lazy_loader import FeatureFlag
    
    # Feature flag for face analysis
    FACE_ANALYSIS_ENABLED = os.getenv("ENABLE_FACE_ANALYSIS", "true").lower() == "true"
    face_analysis_flag = FeatureFlag("Face Analysis", enabled=FACE_ANALYSIS_ENABLED)
    
    if face_analysis_flag.enabled:
        from face_analysis.backend.api.main import router as face_analysis_router  # type: ignore
        logger.info("✅ Face Analysis router loaded successfully")
    else:
        logger.info("🚫 Face Analysis disabled via ENABLE_FACE_ANALYSIS=false")
except ImportError as e:
    logger.warning(f"⚠️  Could not import face_analysis router: {e}")
    logger.warning("   Face Analysis API will not be available. This is not critical.")
    face_analysis_router = None
except Exception as e:
    logger.error(f"❌ Unexpected error importing face_analysis router: {e}", exc_info=True)
    face_analysis_router = None
from fastapi.middleware.cors import CORSMiddleware
from app.ai_ingredient_intelligence.db.collections import distributor_col
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="SkinBB API Documentation",
    description="API documentation for SkinBB - An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI - explicitly enabled
    redoc_url="/redoc",  # ReDoc alternative - explicitly enabled
    openapi_url="/openapi.json"  # OpenAPI JSON schema - explicitly enabled
)

# Custom OpenAPI schema configuration
def custom_openapi():
    """
    Custom OpenAPI schema with servers, security schemes, and enhanced metadata.
    Similar to swagger-jsdoc configuration but for FastAPI.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    try:
        # Get environment variables for server configuration
        import os
        server_url = os.getenv("SERVER_URL", "https://capi.skintruth.in")
        node_env = os.getenv("NODE_ENV", "development")
        
        try:
            openapi_schema = get_openapi(
                title=app.title,
                version=app.version,
                openapi_version="3.1.0",
                description=app.description,
                routes=app.routes,
                terms_of_service="https://www.formulynx.in/terms",
                contact={
                    "name": "SkinBB API Support",
                    "url": "https://www.formulynx.in/contact",
                    "email": "support@formulynx.in"
                },
                license_info={
                    "name": "Proprietary",
                    "url": "https://www.formulynx.in/license"
                },
                tags=[
                    {
                        "name": "Chatbot",
                        "description": "AI-powered skincare chatbot endpoints for querying and document retrieval"
                    },
                    {
                        "name": "INCI Analysis",
                        "description": "INCI name analysis and ingredient decoding endpoints"
                    },
                    {
                        "name": "Formulation Reports",
                        "description": "Generate comprehensive formulation reports in PDF and PPT formats"
                    },
                    {
                        "name": "Cost Calculator",
                        "description": "Calculate formulation costs and pricing"
                    },
                    {
                        "name": "Ingredient Search",
                        "description": "Search and retrieve ingredient information from databases"
                    },
                    {
                        "name": "Formula Generation",
                        "description": "AI-powered formula generation based on requirements"
                    },
                    {
                        "name": "Inspiration Boards",
                        "description": "Manage inspiration boards and product collections"
                    },
                    {
                        "name": "Face Analysis",
                        "description": "Facial analysis and skin condition assessment endpoints"
                    },
                    {
                        "name": "Authentication",
                        "description": "JWT-based authentication and user management"
                    },
                    {
                        "name": "Dashboard",
                        "description": "Dashboard statistics and analytics endpoints"
                    },
                    {
                        "name": "Make a Wish",
                        "description": "Feature request and wishlist management"
                    }
                ]
            )
        except Exception as inner_e:
            logger.warning(f"⚠️  Error generating OpenAPI schema with tags: {inner_e}")
            # Fallback: generate schema without tags
            openapi_schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes
            )
        
        # Add servers configuration
        openapi_schema["servers"] = [
            {
                "url": server_url,
                "description": "Production server" if node_env == "production" else "Development server",
            },
            {
                "url": "https://capi.skinbb.com",
                "description": "Production server",
            },
            {
                "url": "https://capi.skintruth.in",
                "description": "Development server",
            },
            {
                "url": "http://localhost:8000",
                "description": "Local development server",
            },
        ]
        
        # Add security schemes (ensure components exists)
        if "components" not in openapi_schema:
            openapi_schema["components"] = {}
        openapi_schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token authentication. Include the token in the Authorization header as: Bearer <token>"
            }
        }
        
        # Set default security (optional - can be overridden per route)
        # Note: This makes all endpoints require authentication by default in the docs
        # Individual routes can opt out by not using the security dependency
        openapi_schema["security"] = [
            {
                "bearerAuth": []
            }
        ]
        
        # Add external documentation
        openapi_schema["externalDocs"] = {
            "description": "SkinBB API Documentation",
            "url": "https://www.formulynx.in/api-docs"
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    except Exception as e:
        logger.warning(f"⚠️  Error generating custom OpenAPI schema: {e}")
        logger.warning("   Falling back to default OpenAPI schema generation.")
        # Fall back to default OpenAPI generation
        try:
            from fastapi.openapi.utils import get_openapi as default_get_openapi
            return default_get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes
            )
        except Exception as fallback_e:
            logger.error(f"❌ Even default OpenAPI generation failed: {fallback_e}", exc_info=True)
            # Return minimal schema
            return {
                "openapi": "3.0.0",
                "info": {
                    "title": app.title,
                    "version": app.version
                },
                "paths": {}
            }

# Override the default OpenAPI function
app.openapi = custom_openapi

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
        "https://metaverse.skinbb.com",
        "https://formulynx.in",
        "https://www.formulynx.in"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ✅ Existing chatbot API
if api_router is not None:
    app.include_router(api_router, prefix="/api")
    logger.info("✅ Chatbot API routes registered")
else:
    logger.warning("⚠️  Chatbot router not available, skipping registration")

# ✅ Add analyze-inci API (critical - should always be available)
if analyze_inci_router is not None:
    app.include_router(analyze_inci_router, prefix="/api")
    logger.info("✅ Analyze INCI API routes registered")
else:
    logger.error("❌ CRITICAL: Analyze INCI router not available!")

# ✅ Add formulation report API
if formulation_report_router is not None:
    app.include_router(formulation_report_router, prefix="/api")
    logger.info("✅ Formulation Report API routes registered")
else:
    logger.warning("⚠️  Formulation Report router not available, skipping registration")

# ✅ Add cost calculator API
if cost_calculator_router is not None:
    app.include_router(cost_calculator_router, prefix="/api")
    logger.info("✅ Cost Calculator API routes registered")
else:
    logger.error("❌ Cost Calculator router not available!")

# ✅ Add ingredient search API
if ingredient_search_router is not None:
    app.include_router(ingredient_search_router, prefix="/api")
    logger.info("✅ Ingredient Search API routes registered")
else:
    logger.error("❌ Ingredient Search router not available!")

# ✅ Add formula generation API
if formula_generation_router is not None:
    app.include_router(formula_generation_router, prefix="/api")
    logger.info("✅ Formula Generation API routes registered")
else:
    logger.warning("⚠️  Formula Generation router not available, skipping registration")

# ✅ Add Make a Wish API
if make_wish_router is not None:
    app.include_router(make_wish_router, prefix="/api")
    logger.info("✅ Make a Wish API routes registered")
else:
    logger.warning("⚠️  Make a Wish router not available, skipping registration")

# ✅ Add Inspiration Boards API
try:
    from app.ai_ingredient_intelligence.api.inspiration_boards import router as inspiration_boards_router
    app.include_router(inspiration_boards_router, prefix="/api")
    logger.info("✅ Inspiration Boards API routes registered")
except ImportError as e:
    logger.warning(f"⚠️  Could not import inspiration_boards router: {e}")
    logger.warning("   Inspiration Boards API will not be available. This is not critical.")
except Exception as e:
    logger.error(f"❌ Unexpected error importing inspiration_boards router: {e}", exc_info=True)

# ✅ Add Dashboard Stats API
try:
    from app.ai_ingredient_intelligence.api.dashboard_stats import router as dashboard_stats_router
    app.include_router(dashboard_stats_router, prefix="/api")
    logger.info("✅ Dashboard Stats API routes registered")
except ImportError as e:
    logger.warning(f"⚠️  Could not import dashboard_stats router: {e}")
    logger.warning("   Dashboard Stats API will not be available. This is not critical.")
except Exception as e:
    logger.error(f"❌ Unexpected error importing dashboard_stats router: {e}", exc_info=True)

# ✅ Add Authentication API (JWT login, refresh, etc.)
try:
    from app.ai_ingredient_intelligence.auth import auth_router
    app.include_router(auth_router, prefix="/api")
    logger.info("✅ Authentication API routes registered")
except ImportError as e:
    logger.warning(f"⚠️  Could not import auth router: {e}")
    logger.warning("   Authentication API will not be available.")
except Exception as e:
    logger.error(f"❌ Unexpected error importing auth router: {e}", exc_info=True)

# ✅ New image-to-JSON API - Commented out - module doesn't exist
# app.include_router(image_extractor_router, prefix="/api")

# ✅ Face Analysis API - Include router instead of mounting
if face_analysis_router is not None:
    app.include_router(face_analysis_router, prefix="/api/face-analysis", tags=["Face Analysis"])
    logger.info("✅ Face Analysis API routes registered")
else:
    logger.warning("⚠️  Face Analysis router not available, skipping registration")

@app.on_event("startup")
async def create_indexes():
    """Create indexes for MongoDB collections on startup"""
    try:
        # Create indexes for distributor collection
        await distributor_col.create_index("ingredientName")
        await distributor_col.create_index("createdAt")
        await distributor_col.create_index([("ingredientName", 1), ("createdAt", -1)])
        logger.info("✅ Distributor collection indexes created successfully")
        
        # Create indexes for decode history collection
        from app.ai_ingredient_intelligence.db.collections import decode_history_col, compare_history_col
        await decode_history_col.create_index("user_id")
        await decode_history_col.create_index("created_at")
        await decode_history_col.create_index([("user_id", 1), ("created_at", -1)])
        await decode_history_col.create_index([("user_id", 1), ("name", "text")])
        logger.info("✅ Decode history collection indexes created successfully")
        
        # Create indexes for compare history collection
        await compare_history_col.create_index("user_id")
        await compare_history_col.create_index("created_at")
        await compare_history_col.create_index([("user_id", 1), ("created_at", -1)])
        await compare_history_col.create_index([("user_id", 1), ("name", "text")])
        logger.info("✅ Compare history collection indexes created successfully")
        
        # Create indexes for inspiration boards collections
        from app.ai_ingredient_intelligence.db.collections import (
            inspiration_boards_col, inspiration_products_col
        )
        await inspiration_boards_col.create_index("user_id")
        await inspiration_boards_col.create_index("created_at")
        await inspiration_boards_col.create_index([("user_id", 1), ("created_at", -1)])
        await inspiration_products_col.create_index("board_id")
        await inspiration_products_col.create_index("user_id")
        await inspiration_products_col.create_index([("board_id", 1), ("decoded", 1)])
        await inspiration_products_col.create_index([("user_id", 1), ("created_at", -1)])
        logger.info("✅ Inspiration boards collection indexes created successfully")
    except Exception as e:
        logger.warning(f"⚠️  Could not create indexes: {e}")
        # Don't fail startup if indexes already exist

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

# Global exception handlers
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.error_handlers import sanitize_error_message

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to catch all unhandled exceptions.
    Prevents stack traces from leaking to users.
    """
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    
    # Determine appropriate status code
    status_code = 500
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
    elif "not found" in str(exc).lower():
        status_code = 404
    elif "unauthorized" in str(exc).lower() or "authentication" in str(exc).lower():
        status_code = 401
    elif "forbidden" in str(exc).lower():
        status_code = 403
    elif "validation" in str(exc).lower() or "invalid" in str(exc).lower():
        status_code = 400
    
    # Create safe error response
    detail = sanitize_error_message(exc, include_details=False)
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": type(exc).__name__,
            "detail": detail,
            "path": str(request.url.path)
        }
    )
