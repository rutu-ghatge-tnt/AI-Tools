# SkinBB AI Tools - Comprehensive Skincare Intelligence Platform
A comprehensive AI-powered platform for skincare ingredient analysis, chatbot assistance, and product information extraction using advanced OCR, Claude AI, and MongoDB.

## 🚀 **Project Overview**

SkinBB AI Tools is a multi-module platform that combines:
- **AI Chatbot** with RAG (Retrieval-Augmented Generation) for skincare queries
- **OCR Ingredient Analysis** using Google Vision API + Claude AI
- **Product Image Extraction** for structured data from product images/PDFs
- **Formulation Reports** with detailed cosmetic analysis
- **MongoDB Integration** for ingredient database and matching

## 🏗️ **Architecture**

```
SkinBB AI Tools/
├── app/
│   ├── main.py                          # Main FastAPI application
│   ├── config.py                        # Configuration and environment variables
│   ├── chatbot/                         # AI Chatbot with RAG pipeline
│   ├── ai_ingredient_intelligence/      # OCR and ingredient analysis
│   ├── product_listing_image_extraction/ # Product image/PDF extraction
│   └── templates/                       # HTML templates
├── chroma_db/                           # Vector database for RAG
├── requirements.txt                     # Python dependencies
└── vision_key.json                     # Google Vision API credentials
```

## ✨ **Core Features**

### **1. AI Chatbot (SkinSage)**
- **RAG Pipeline**: Document retrieval with ChromaDB
- **Context Awareness**: Maintains conversation history
- **Offensive Content Filtering**: Built-in content moderation
- **Streaming Responses**: Real-time AI responses

### **2. OCR Ingredient Analysis**
- **Multiple Input Types**: PDF, Image, Camera, Text
- **Google Vision API**: High-accuracy text extraction
- **Claude AI Integration**: Intelligent ingredient identification
- **MongoDB Matching**: Ingredient database lookup and analysis

### **3. Product Image Extraction**
- **Multi-format Support**: Images (JPEG, PNG, GIF, BMP, WebP) and PDFs
- **Structured Data Extraction**: Convert images to JSON data
- **Claude AI Processing**: Intelligent information extraction

### **4. Formulation Reports**
- **Comprehensive Analysis**: 10 detailed analysis sections
- **Regulatory Compliance**: Safety and compliance checking
- **Risk Assessment**: Ingredient risk evaluation
- **Professional Formatting**: Structured report generation

## 🛠️ **Technology Stack**

- **Backend**: FastAPI (Python)
- **AI Models**: Claude AI (Anthropic), OpenAI GPT
- **OCR**: Google Cloud Vision API
- **Database**: MongoDB, ChromaDB (vector database)
- **PDF Processing**: PyMuPDF, pdf2image
- **Image Processing**: Pillow (PIL)
- **Document Processing**: Jinja2 templates

## 📋 **Prerequisites**

- Python 3.8+
- MongoDB instance
- Google Cloud Vision API credentials
- Claude AI API key
- OpenAI API key (for formulation reports)

## 🚀 **Installation & Setup**

### **1. Clone and Setup**
```bash
git clone <repository-url>
cd SkinBB_AI_Tools
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### **2. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **3. Environment Configuration**
Create a `.env` file in the root directory:

```env
# Claude AI Configuration
CLAUDE_API_KEY=your-claude-api-key
MODEL_NAME=claude-3-opus-20240229

# OpenAI Configuration (for formulation reports)
OPENAI_API_KEY=your-openai-api-key

# MongoDB Configuration
MONGO_URI=mongodb://username:password@host:port/database
DB_NAME=skin_bb

# Google Vision API (optional - for OCR features)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/vision_key.json
GOOGLE_CLOUD_PROJECT=your-project-id
```

### **4. Google Vision API Setup (Optional)**
1. Create Google Cloud Project
2. Enable Vision API
3. Create service account and download JSON key
4. Place `vision_key.json` in project root

### **5. Run the Application**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 🌐 **API Endpoints**

### **Core Application**
- **`GET /`** - Welcome message and API info
- **`GET /docs`** - Interactive API documentation

### **Chatbot API**
- **`POST /api/chat`** - AI chatbot with RAG pipeline
  ```json
  {
    "query": "What are the benefits of hyaluronic acid?",
    "history": []
  }
  ```

### **Ingredient Analysis API**
- **`POST /api/analyze-inci`** - OCR ingredient analysis
  - `input_type`: text, pdf, image, camera
  - `inci_names`: List of ingredients (for text input)
  - `pdf_file`: PDF file upload
  - `image_file`: Image file upload
  - `camera_image`: Base64 encoded camera image

### **Product Image Extraction API**
- **`POST /api/extract-from-image`** - Extract structured data from images/PDFs
  - Supports: Images (JPEG, PNG, GIF, BMP, WebP) and PDFs
  - Returns: OCR text + structured JSON data

### **Formulation Reports API**
- **`POST /api/formulation-report`** - Generate detailed cosmetic analysis
  ```json
  {
    "inciList": ["Water", "Glycerin", "Hyaluronic Acid"]
  }
  ```

## 📱 **Usage Examples**

### **1. Chat with SkinSage**
```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about vitamin C in skincare", "history": []}'
```

### **2. Analyze Ingredients from Image**
```bash
curl -X POST "http://localhost:8000/api/analyze-inci" \
  -F "input_type=image" \
  -F "image_file=@ingredients.jpg"
```

### **3. Extract Product Information**
```bash
curl -X POST "http://localhost:8000/api/extract-from-image" \
  -F "file=@product_image.jpg"
```

### **4. Generate Formulation Report**
```bash
curl -X POST "http://localhost:8000/api/formulation-report" \
  -H "Content-Type: application/json" \
  -d '{"inciList": ["Water", "Glycerin", "Niacinamide"]}'
```

## 🔧 **Configuration Options**

### **Model Configuration**
- **Claude Model**: Configurable via `MODEL_NAME` environment variable
- **OpenAI Model**: Used for formulation reports
- **RAG Pipeline**: ChromaDB for document retrieval

### **Database Configuration**
- **MongoDB**: Primary database for ingredient data
- **ChromaDB**: Vector database for RAG functionality
- **Connection**: Configurable via environment variables

### **API Configuration**
- **CORS**: Configured for specific origins
- **Rate Limiting**: Built-in request handling
- **Error Handling**: Comprehensive error responses

## 🧪 **Testing**

### **1. Test Setup**
```bash
python test_ocr_setup.py
```

### **2. Test Models**
```bash
python test_models.py
```

### **3. Test Formulation API**
```bash
python app/test_formulation_api.py
```

## 📊 **Response Formats**

### **Chatbot Response**
```json
{
  "response": "Streaming response content",
  "done": false
}
```

### **Ingredient Analysis Response**
```json
{
  "grouped": [...],
  "unmatched": [...],
  "overall_confidence": 0.95,
  "processing_time": 1.234,
  "extracted_text": "Raw OCR text",
  "input_type": "image"
}
```

### **Product Extraction Response**
```json
{
  "ocr_text": "Extracted text from image",
  "structured_data": {
    "product_name": "...",
    "ingredients": [...],
    "claims": [...]
  }
}
```

## 🚨 **Error Handling**

- **Input Validation**: Comprehensive parameter checking
- **File Type Validation**: Supported format verification
- **API Error Handling**: Structured error responses
- **Database Connection**: Graceful fallback handling
- **OCR Processing**: Error recovery and retry logic

## 🔒 **Security Features**

- **Content Moderation**: Offensive content filtering
- **Input Sanitization**: Request validation and cleaning
- **CORS Protection**: Origin-based access control
- **Environment Variables**: Secure credential management
- **File Upload Limits**: Size and type restrictions

## 📈 **Performance Features**

- **Streaming Responses**: Real-time chatbot responses
- **Async Processing**: Non-blocking API operations
- **Database Optimization**: Efficient MongoDB queries
- **Vector Search**: Fast ChromaDB similarity search
- **Caching**: In-memory response caching

## 🐛 **Troubleshooting**

### **Common Issues**

1. **MongoDB Connection Errors**
   - Verify connection string in `.env`
   - Check network connectivity
   - Ensure database is running

2. **API Key Issues**
   - Verify all API keys are set in `.env`
   - Check API quotas and billing
   - Ensure proper model access

3. **OCR Processing Errors**
   - Verify Google Vision credentials
   - Check file format support
   - Ensure proper image quality

4. **ChromaDB Issues**
   - Verify `chroma_db/` directory exists
   - Check file permissions
   - Ensure proper vector database setup

### **Debug Mode**
Enable debug mode in `main.py`:
```python
app = FastAPI(debug=True)
```

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 **License**

This project is proprietary software. All rights reserved.

## 🆘 **Support**

For issues and questions:
- Check the error logs
- Verify environment configuration
- Review API documentation at `/docs`
- Check troubleshooting section above

## 🔮 **Future Enhancements**

- **Multi-language Support**: International ingredient databases
- **Advanced Analytics**: Machine learning insights
- **Mobile App**: Native mobile application
- **API Rate Limiting**: Advanced request management
- **Real-time Updates**: Live ingredient database updates

---

**SkinBB AI Tools** - Empowering skincare professionals with AI-driven ingredient intelligence and analysis.