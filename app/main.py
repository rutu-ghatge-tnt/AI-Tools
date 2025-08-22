from fastapi import FastAPI
from app.chatbot.api import router as api_router
from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router   # ✅ import here
from app.image_extractor.route import router as image_extractor_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SkinBB AI Skincare Chatbot",
    description="An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0"
)

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tt.skintruth.in", "http://localhost:5174", "http://localhost:5173"],     
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Existing chatbot API
app.include_router(api_router, prefix="/api")

# ✅ Add analyze-inci API
app.include_router(analyze_inci_router, prefix="/api")   # <--- added

# ✅ New image-to-JSON API
app.include_router(image_extractor_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact v1."}
