"""
Health Checks API Endpoint
==========================

Health check endpoints for monitoring system status.
Extracted from analyze_inci.py for better modularity.
"""

import os
import subprocess
from fastapi import APIRouter
from app.ai_ingredient_intelligence.logic.bis_rag import (
    check_bis_rag_health,
    get_bis_retriever,
    get_bis_cautions_for_ingredients,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)

router = APIRouter(tags=["Health Checks"])


@router.get("/server-health")
async def server_health():
    """
    Comprehensive server health check endpoint.
    Tests: Chrome availability, Claude API, environment variables.
    
    NOTE: This endpoint is PUBLIC (no authentication required) for monitoring purposes.
    """
    health_status = {
        "status": "healthy",
        "checks": {},
        "errors": []
    }
    
    # Check Chrome/Chromium
    chrome_available = False
    chrome_version = None
    try:
        result = subprocess.run(
            ["google-chrome", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            chrome_available = True
            chrome_version = result.stdout.strip()
    except:
        try:
            result = subprocess.run(
                ["chromium-browser", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                chrome_available = True
                chrome_version = result.stdout.strip()
        except:
            pass
    
    health_status["checks"]["chrome"] = {
        "available": chrome_available,
        "version": chrome_version
    }
    if not chrome_available:
        health_status["errors"].append("Chrome/Chromium not found. Install with: sudo apt-get install -y google-chrome-stable")
    
    # Check environment variables
    claude_key = os.getenv("CLAUDE_API_KEY")
    headless_mode = os.getenv("HEADLESS_MODE", "true")
    
    health_status["checks"]["environment"] = {
        "CLAUDE_API_KEY": "set" if claude_key else "missing",
        "HEADLESS_MODE": headless_mode,
        "MODEL_NAME": os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"
    }
    if not claude_key:
        health_status["errors"].append("CLAUDE_API_KEY not set in environment")
        health_status["status"] = "unhealthy"
    
    # Check if Selenium can initialize (quick test)
    selenium_ok = False
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        selenium_ok = True
    except Exception as e:
        health_status["errors"].append(f"Selenium import failed: {str(e)}")
        health_status["status"] = "unhealthy"
    
    health_status["checks"]["selenium"] = {
        "imported": selenium_ok
    }
    
    # Overall status
    if health_status["errors"]:
        health_status["status"] = "unhealthy"
    
    return health_status


@router.get("/bis-rag/health")
async def bis_rag_health():
    """
    Health check endpoint for BIS RAG functionality.
    Uses the comprehensive health check function from bis_rag module.
    
    NOTE: This endpoint is PUBLIC (no authentication required) for monitoring purposes.
    """
    from pathlib import Path
    
    # Get comprehensive health check
    health = check_bis_rag_health()
    
    # Format response with additional details
    health_status = {
        "status": health.get("status", "unknown"),
        "checks": {
            "pdf_files": {
                "status": "ok" if health.get("pdf_files_found", 0) > 0 else "warning",
                "count": health.get("pdf_files_found", 0),
                "path": str(BIS_DATA_PATH),
                "files": [f.name for f in list(BIS_DATA_PATH.glob("*.pdf"))[:5]] if BIS_DATA_PATH.exists() else []
            },
            "vectorstore_directory": {
                "status": "ok" if health.get("vectorstore_path_exists", False) else "warning",
                "exists": health.get("vectorstore_path_exists", False),
                "path": str(BIS_CHROMA_DB_PATH)
            },
            "vectorstore_initialization": {
                "status": "ok" if health.get("vectorstore_initialized", False) else "error",
                "initialized": health.get("vectorstore_initialized", False)
            },
            "retriever_creation": {
                "status": "ok" if health.get("retriever_created", False) else "error",
                "created": health.get("retriever_created", False),
                "test_query_results": health.get("retriever_test_query", 0)
            }
        },
        "errors": health.get("errors", []),
        "warnings": []
    }
    
    # Add warnings based on status
    if health.get("pdf_files_found", 0) == 0:
        health_status["warnings"].append("No PDF files found in data directory")
    if not health.get("vectorstore_path_exists", False):
        health_status["warnings"].append("Vectorstore directory does not exist or is empty")
    if health.get("status") != "healthy":
        health_status["warnings"].append(f"BIS RAG status: {health.get('status')}")
    
    # Set overall status based on errors
    if health_status["errors"]:
        health_status["status"] = "unhealthy"
    elif health_status["warnings"] and health_status["status"] == "healthy":
        health_status["status"] = "degraded"
    
    retriever = None
    try:
        retriever = get_bis_retriever()
    except:
        pass
    
    # Check 5: Test retrieval (if retriever is available)
    if retriever is not None:
        try:
            # Test with a common ingredient
            test_query = "salicylic acid"
            test_docs = retriever.invoke(test_query)
            health_status["checks"]["test_retrieval"] = {
                "status": "ok",
                "query": test_query,
                "documents_retrieved": len(test_docs),
                "sample_doc_length": len(test_docs[0].page_content) if test_docs else 0
            }
        except Exception as e:
            health_status["checks"]["test_retrieval"] = {
                "status": "error",
                "error": str(e)
            }
            health_status["errors"].append(f"Test retrieval failed: {e}")
    else:
        health_status["checks"]["test_retrieval"] = {
            "status": "skipped",
            "reason": "Retriever not available"
        }
    
    # Check 6: Test full BIS cautions function
    try:
        test_ingredients = ["Salicylic Acid"]
        test_cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        health_status["checks"]["bis_cautions_function"] = {
            "status": "ok",
            "test_ingredients": test_ingredients,
            "ingredients_with_cautions": len(test_cautions),
            "total_cautions": sum(len(c) for c in test_cautions.values())
        }
    except Exception as e:
        health_status["checks"]["bis_cautions_function"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["errors"].append(f"BIS cautions function test failed: {e}")
    
    # Overall status
    if health_status["errors"]:
        health_status["status"] = "unhealthy"
    elif health_status["warnings"]:
        health_status["status"] = "degraded"
    
    return health_status


@router.get("/test-selenium")
async def test_selenium():
    """Test endpoint to check if Selenium is working"""
    import asyncio
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        def test():
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            print("Installing ChromeDriver...")
            service = Service(ChromeDriverManager().install())
            print("Starting Chrome...")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("Loading page...")
            driver.get("https://www.google.com")
            title = driver.title
            print(f"Page loaded: {title}")
            driver.quit()
            return title
        
        loop = asyncio.get_event_loop()
        title = await loop.run_in_executor(None, test)
        
        return {"status": "success", "message": f"Selenium is working! Page title: {title}"}
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Selenium test error: {error_trace}")
        return {
            "status": "error", 
            "message": str(e), 
            "type": type(e).__name__,
            "traceback": error_trace
        }

