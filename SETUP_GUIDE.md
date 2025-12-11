# Setup Guide - SkinBB AI Chatbot

## ✅ Setup Status

### Completed Steps:
1. ✅ Python 3.13.7 detected
2. ✅ Virtual environment (`venv`) exists
3. ✅ Core dependencies installed (FastAPI, Uvicorn, LangChain, Anthropic, etc.)

### ⚠️ Known Issues:
- **MediaPipe**: Not compatible with Python 3.13 yet. Face Analysis will use OpenCV fallback.

## 📋 Quick Start

### 1. Create `.env` File

Create a `.env` file in the project root with the following content:

```env
# Claude AI Configuration (REQUIRED)
CLAUDE_API_KEY=your-claude-api-key-here
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# OpenAI Configuration (Optional - for formulation reports)
OPENAI_API_KEY=your-openai-api-key-here

# MongoDB Configuration (Already configured with default, but can override)
MONGO_URI=mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin
DB_NAME=skin_bb

# Google Vision API (Optional - for OCR features)
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/vision_key.json
# GOOGLE_CLOUD_PROJECT=your-project-id
```

**Important**: Replace `your-claude-api-key-here` with your actual Claude API key.

### 2. Activate Virtual Environment

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Start the Server

**Option A: Using the startup script**
```bash
python start_backend.py
```

**Option B: Direct uvicorn command**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Access the Application

- **API Server**: http://localhost:8000/
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🔧 Installation Details

### Dependencies Installed:
- ✅ FastAPI & Uvicorn (Web framework)
- ✅ LangChain & Anthropic (AI/LLM)
- ✅ ChromaDB (Vector database)
- ✅ MongoDB drivers (pymongo, motor)
- ✅ OpenAI (for formulation reports)
- ✅ Google Cloud Vision (for OCR)
- ✅ All other required packages

### Missing (Optional):
- ⚠️ MediaPipe (not compatible with Python 3.13) - Face Analysis will use OpenCV fallback

## 🚀 Running the Project

### Step-by-Step:

1. **Ensure you're in the project directory:**
   ```bash
   cd D:\formulation\AI-CHATBOT
   ```

2. **Activate virtual environment:**
   ```bash
   venv\Scripts\activate
   ```

3. **Create `.env` file** (if not already created) with your API keys

4. **Start the server:**
   ```bash
   python start_backend.py
   ```
   
   Or directly:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Verify it's running:**
   - Open http://localhost:8000/health in your browser
   - Check http://localhost:8000/docs for API documentation

## 📝 Environment Variables

### Required:
- `CLAUDE_API_KEY` - Your Anthropic Claude API key

### Optional:
- `OPENAI_API_KEY` - For formulation reports
- `MONGO_URI` - MongoDB connection string (default already set)
- `DB_NAME` - Database name (default: skin_bb)
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to Google Vision API credentials JSON

## 🐛 Troubleshooting

### Issue: "CLAUDE_API_KEY is not set"
**Solution**: Create a `.env` file in the project root with your API key.

### Issue: MongoDB connection errors
**Solution**: The default MongoDB URI is already configured. If you have connection issues, check:
- Network connectivity
- MongoDB server status
- Firewall settings

### Issue: MediaPipe import errors
**Solution**: This is expected with Python 3.13. Face Analysis will automatically use OpenCV fallback.

### Issue: Port 8000 already in use
**Solution**: Change the port:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## 📚 API Endpoints

Once running, you can access:

- `GET /` - Welcome message
- `GET /health` - Health check
- `GET /docs` - Interactive API documentation (Swagger UI)
- `POST /api/chat` - AI chatbot endpoint
- `POST /api/analyze-inci` - Ingredient analysis
- `POST /api/formulation-report` - Generate formulation reports
- And many more...

See http://localhost:8000/docs for full API documentation.

## 🎯 Next Steps

1. Set up your `.env` file with API keys
2. Start the server using `python start_backend.py`
3. Visit http://localhost:8000/docs to explore the API
4. Test the `/health` endpoint to verify everything is working

---

**Note**: If you encounter any issues, check the console output for error messages and refer to the troubleshooting section above.

