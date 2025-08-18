# app/main.py
from fastapi import FastAPI
from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router
from app.ai_ingredient_intelligence.db.mongodb import db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Ingredient Intelligence — Direct INCI Matcher", debug=True)

# ✅ CORS Configuration: Allow only your frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tt.skintruth.in", "http://localhost:5174", "http://localhost:5173"],     
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
async def root():
    # Basic ping to confirm DB connection
    try:
        await db.command("ping")
        mongo = "ok"
    except Exception as e:
        mongo = f"error: {e}"
    return {"status": "ok", "mongo": mongo, "docs": "/docs"}

app.include_router(analyze_inci_router, prefix="/api")
