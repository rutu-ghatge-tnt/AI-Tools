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

from fastapi import FastAPI, Request

# Import chatbot router (with error handling for missing dependencies)
try:
    from app.chatbot.api import router as api_router
except ImportError as e:
    print(f"Warning: Could not import chatbot router: {e}")
    print("   Chatbot API will not be available. This is not critical.")
    api_router = None

from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router   # ✅ import here

# Import formulation report router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.formulation_report import router as formulation_report_router
except ImportError as e:
    print(f"Warning: Could not import formulation_report router: {e}")
    print("   Formulation Report API will not be available. This is not critical.")
    formulation_report_router = None

from app.ai_ingredient_intelligence.api.cost_calculator import router as cost_calculator_router
from app.ai_ingredient_intelligence.api.ingredient_search import router as ingredient_search_router

# Import Formula Generation router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.formula_generation import router as formula_generation_router
except ImportError as e:
    print(f"Warning: Could not import formula_generation router: {e}")
    print("   Formula Generation API will not be available. This is not critical.")
    formula_generation_router = None

# Import Make a Wish router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.make_wish_api import router as make_wish_router
except ImportError as e:
    print(f"Warning: Could not import make_wish router: {e}")
    print("   Make a Wish API will not be available. This is not critical.")
    make_wish_router = None
# from app.product_listing_image_extraction.route import router as image_extractor_router  # Commented out - module doesn't exist
from pathlib import Path

# Add Face Analysis path to Python path
face_analysis_path = Path(__file__).parent / "faceAnalysis"
sys.path.insert(0, str(face_analysis_path))

# Import Face Analysis router (with error handling for missing module)
try:
    from face_analysis.backend.api.main import router as face_analysis_router  # type: ignore
except ImportError as e:
    print(f"Warning: Could not import face_analysis router: {e}")
    print("   Face Analysis API will not be available. This is not critical.")
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
    
    # Get environment variables for server configuration
    import os
    server_url = os.getenv("SERVER_URL")
    node_env = os.getenv("NODE_ENV", "development")  # Default to development is acceptable
    
    if not server_url:
        raise ValueError("SERVER_URL environment variable is required. Please set it in your .env file.")
    
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
    
    # Add security schemes
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

# Override the default OpenAPI function
app.openapi = custom_openapi

# ✅ CORS - Environment-aware configuration
# Production origins (for capi.skinbb.com - production server)
production_origins = [
    "https://tt.skintruth.in", 
    "https://capi.skinbb.com",
    "https://metaverse.skinbb.com",
    "https://formulynx.in",
    "https://www.formulynx.in"
]

# Development origins (for capi.skintruth.in - development server)
development_origins = [
    "https://capi.skintruth.in",  # Development API server
    "https://tt.skintruth.in",     # Development frontend
    "http://localhost:5174", 
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:8501"
]

# Determine environment based on SERVER_URL
# Development: capi.skintruth.in
# Production: capi.skinbb.com
server_url = os.getenv("SERVER_URL", "").lower()
is_production = "capi.skinbb.com" in server_url or "capi.skinbb.in" in server_url
env = os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "")).lower()

# If ENVIRONMENT is explicitly set, use that; otherwise detect from SERVER_URL
if env in ["production", "prod"]:
    is_development = False
elif env in ["development", "dev", "local"]:
    is_development = True
else:
    # Auto-detect from SERVER_URL
    is_development = not is_production

# Combine origins based on environment
if is_development:
    allowed_origins = development_origins.copy()
    print(f"🌍 CORS: Development mode (capi.skintruth.in)")
else:
    allowed_origins = production_origins.copy()
    print(f"🌍 CORS: Production mode (capi.skinbb.com)")

print(f"📋 Allowed CORS origins: {allowed_origins}")
print(f"🔍 SERVER_URL: {server_url}")
print(f"🔍 ENVIRONMENT: {env}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ✅ Existing chatbot API
if api_router is not None:
    app.include_router(api_router, prefix="/api")
else:
    print("Warning: Chatbot router not available, skipping registration")

# ✅ Add analyze-inci API
app.include_router(analyze_inci_router, prefix="/api")   # <--- added

# ✅ Add formulation report API
if formulation_report_router is not None:
    app.include_router(formulation_report_router, prefix="/api")
else:
    print("Warning: Formulation Report router not available, skipping registration")

# ✅ Add cost calculator API
app.include_router(cost_calculator_router, prefix="/api")

# ✅ Add ingredient search API
app.include_router(ingredient_search_router, prefix="/api")

# ✅ Add formula generation API
if formula_generation_router is not None:
    app.include_router(formula_generation_router, prefix="/api")
else:
    print("Warning: Formula Generation router not available, skipping registration")

# ✅ Add Make a Wish API
if make_wish_router is not None:
    app.include_router(make_wish_router, prefix="/api")
else:
    print("Warning: Make a Wish router not available, skipping registration")

# ✅ Add Inspiration Boards API
try:
    from app.ai_ingredient_intelligence.api.inspiration_boards import router as inspiration_boards_router
    app.include_router(inspiration_boards_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import inspiration_boards router: {e}")
    print("   Inspiration Boards API will not be available. This is not critical.")

# ✅ Add Dashboard Stats API
try:
    from app.ai_ingredient_intelligence.api.dashboard_stats import router as dashboard_stats_router
    app.include_router(dashboard_stats_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import dashboard_stats router: {e}")
    print("   Dashboard Stats API will not be available. This is not critical.")

# ✅ Add Authentication API (JWT login, refresh, etc.)
try:
    from app.ai_ingredient_intelligence.auth import auth_router
    app.include_router(auth_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import auth router: {e}")
    print("   Authentication API will not be available.")

# ✅ Add Dashboard Stats API
try:
    from app.ai_ingredient_intelligence.api.dashboard_stats import router as dashboard_stats_router
    app.include_router(dashboard_stats_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import dashboard_stats router: {e}")
    print("   Dashboard Stats API will not be available. This is not critical.")

# ✅ Add Authentication API (JWT login, refresh, etc.)
try:
    from app.ai_ingredient_intelligence.auth import auth_router
    app.include_router(auth_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import auth router: {e}")
    print("   Authentication API will not be available.")

# ✅ New image-to-JSON API - Commented out - module doesn't exist
# app.include_router(image_extractor_router, prefix="/api")

# ✅ Face Analysis API - Include router instead of mounting
if face_analysis_router is not None:
    app.include_router(face_analysis_router, prefix="/api/face-analysis", tags=["Face Analysis"])
else:
    print("Warning: Face Analysis router not available, skipping registration")

@app.on_event("startup")
async def create_indexes():
    """Create indexes for MongoDB collections on startup"""
    try:
        # Create indexes for distributor collection
        await distributor_col.create_index("ingredientName")
        await distributor_col.create_index("createdAt")
        await distributor_col.create_index([("ingredientName", 1), ("createdAt", -1)])
        print("Distributor collection indexes created successfully")
        
        # Create indexes for decode history collection
        from app.ai_ingredient_intelligence.db.collections import decode_history_col, compare_history_col
        await decode_history_col.create_index("user_id")
        await decode_history_col.create_index("created_at")
        await decode_history_col.create_index([("user_id", 1), ("created_at", -1)])
        await decode_history_col.create_index([("user_id", 1), ("name", "text")])
        print("Decode history collection indexes created successfully")
        
        # Create indexes for compare history collection
        await compare_history_col.create_index("user_id")
        await compare_history_col.create_index("created_at")
        await compare_history_col.create_index([("user_id", 1), ("created_at", -1)])
        await compare_history_col.create_index([("user_id", 1), ("name", "text")])
        print("Compare history collection indexes created successfully")
        
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
        print("Inspiration boards collection indexes created successfully")
    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")
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

@app.get("/cors-debug")
async def cors_debug(request: Request):
    """Debug endpoint to check CORS configuration"""
    origin = request.headers.get("origin", "No origin header")
    return {
        "origin": origin,
        "allowed_origins": allowed_origins,
        "is_development": is_development,
        "server_url": server_url,
        "environment": env,
        "origin_allowed": origin in allowed_origins if origin != "No origin header" else None
    }
