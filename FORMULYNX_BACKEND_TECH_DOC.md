# Formulynx - Backend Technical Documentation

**Project Name:** Formulynx (AI Ingredient Intelligence Platform)  
**Version:** 1.0  
**Base URL:** `http://localhost:8000` (Local) / `https://capi.skintruth.in` (Production)  
**Documentation Date:** 2025

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Database Structure](#database-structure)
5. [API Features & Endpoints](#api-features--endpoints)
6. [User Flows](#user-flows)
7. [Starting the Backend](#starting-the-backend)
8. [Environment Configuration](#environment-configuration)

---

## Project Overview

Formulynx is an AI-powered ingredient intelligence platform designed for cosmetic formulators and skincare professionals. The backend provides comprehensive APIs for ingredient analysis, formula generation, cost calculation, market research, and competitor analysis.

### Core Capabilities

- **Ingredient Analysis**: OCR-based ingredient extraction and INCI analysis
- **Formula Generation**: AI-powered cosmetic formulation creation
- **Cost Calculator**: Real-time formulation cost analysis and optimization
- **Inspiration Boards**: Competitor product tracking and analysis
- **Market Research**: Product research and trend analysis
- **Formulation Reports**: Comprehensive cosmetic analysis reports

---

## Architecture

### System Architecture

```
Formulynx Backend/
├── app/
│   ├── main.py                          # FastAPI application entry point
│   ├── config.py                        # Configuration management
│   ├── chatbot/                         # AI Chatbot with RAG pipeline
│   ├── ai_ingredient_intelligence/      # Formulynx - Core ingredient intelligence module
│   │   ├── api/                         # API route handlers
│   │   │   ├── analyze_inci.py          # INCI analysis endpoints
│   │   │   ├── formula_generation.py    # Formula generation endpoints
│   │   │   ├── cost_calculator.py       # Cost calculation endpoints
│   │   │   ├── inspiration_boards.py    # Inspiration boards endpoints
│   │   │   ├── formulation_report.py    # Report generation endpoints
│   │   │   └── ingredient_search.py     # Ingredient search endpoints
│   │   ├── logic/                       # Business logic layer
│   │   │   ├── formula_generator.py    # Formula generation engine
│   │   │   ├── bis_rag.py              # BIS regulatory compliance
│   │   │   ├── board_manager.py        # Board management logic
│   │   │   └── product_decoder.py      # Product decoding logic
│   │   ├── db/                          # Database layer
│   │   │   ├── mongodb.py              # MongoDB connection
│   │   │   └── collections.py          # Collection references
│   │   └── models/                      # Pydantic models/schemas
├── chroma_db/                           # Vector database for RAG
└── start_backend.py                     # Backend startup script
```

### Request Flow

1. **Client Request** → FastAPI Router
2. **Route Handler** → Business Logic Layer
3. **Business Logic** → Database/External APIs (MongoDB, Claude AI, etc.)
4. **Response** → JSON formatted data back to client

---

## Technology Stack

### Backend Framework
- **FastAPI**: Modern Python web framework with automatic OpenAPI documentation
- **Uvicorn**: ASGI server for running FastAPI

### AI & ML
- **Claude AI (Anthropic)**: Primary AI model for formula generation and analysis
- **Google Vision API**: OCR for ingredient extraction from images/PDFs
- **ChromaDB**: Vector database for RAG (Retrieval-Augmented Generation)

### Database
- **MongoDB**: Primary database for ingredients, formulations, and user data
- **ChromaDB**: Vector database for semantic search and document retrieval

### Key Libraries
- **Pydantic**: Data validation and serialization
- **PyMongo**: MongoDB driver
- **Selenium**: Web scraping for product data extraction
- **PyMuPDF**: PDF processing

---

## Database Structure

### MongoDB Collections

#### Ingredient Collections
- **`ingre_inci`**: INCI ingredient database with categories, functions, and safety data
- **`ingre_branded_ingredients`**: Branded ingredient variants with supplier information
- **`ingre_suppliers`**: Supplier database
- **`ingre_functional_categories`**: Functional category hierarchy
- **`ingre_chemical_classes`**: Chemical classification system
- **`distributor`**: Distributor pricing and ingredient information

#### User Data Collections
- **`decode_history`**: User ingredient analysis history
- **`compare_history`**: Product comparison history
- **`wish_history`**: Formula generation wish history
- **`market_research_history`**: Market research query history

#### Inspiration Boards Collections
- **`inspiration_boards`**: User-created inspiration boards
- **`inspiration_products`**: Products added to boards
- **`product_tags`**: Product tagging system

### Indexes

The system automatically creates indexes on startup for:
- User ID + timestamp combinations
- Ingredient names
- Board IDs
- Product IDs

---

## API Features & Endpoints

### 1. INCI Analysis

**Purpose**: Analyze cosmetic ingredients from various input sources (text, images, PDFs, URLs)

#### Key Endpoints

**POST `/api/analyze-inci`**
- Analyzes INCI ingredients from multiple input types
- Input types: `text`, `pdf`, `image`, `camera` for now text
- Returns: Grouped ingredients, unmatched items, confidence scores, safety data

**POST `/api/analyze-url`**
- Extracts and analyzes ingredients from product URLs
- Supports: Nykaa, Amazon, Flipkart, Purplle etc 
- Returns: Full ingredient analysis with extracted text

**POST `/api/extract-ingredients-from-url`**
- Extracts ingredients only (no analysis)
- Useful for quick ingredient list extraction

**GET `/api/suppliers`**
- Returns list of all available suppliers
- Supports pagination

**POST `/api/ingredients/categories`**
- Gets Active/Excipient categories for INCI ingredients

#### User Flow
1. User provides ingredient list (text/image/URL)
2. System extracts text using OCR (if needed)
3. AI identifies INCI names from text
4. System matches against MongoDB ingredient database
5. Returns categorized analysis with safety data, suppliers, and functions

---

### 2. Formula Generation

**Purpose**: Generate complete cosmetic formulations based on user requirements

#### Key Endpoints

**POST `/api/formula/generate`**
- Generates complete cosmetic formulation
- Input: Product type, benefits, exclusions, hero ingredients, cost range, texture preferences
- Output: Complete formula with phases, percentages, cost, pH, shelf life, insights, warnings

**POST `/api/make-wish/generate`**
- Alternative formula generation using 5-stage pipeline
- More detailed manufacturing process generation

**POST `/api/formula/save-wish-history`**
- Saves generated formula to user history

**GET `/api/formula/wish-history`**
- Retrieves user's formula generation history

#### User Flow
1. User specifies requirements (product type, benefits, exclusions, cost range)
2. System selects ingredients using AI + rule-based matching
3. Allocates percentages based on product type templates
4. Optimizes with AI for compatibility and effectiveness
5. Organizes into manufacturing phases
6. Validates cost, BIS compliance, and safety
7. Returns complete formula with insights and warnings

#### Formula Structure
- **Phases**: Organized by manufacturing order (Phase A, B, C, etc.)
- **Ingredients**: INCI name, percentage, function, supplier info
- **Metadata**: Cost, pH range, texture, shelf life
- **Compliance**: BIS regulations, safety warnings
- **Insights**: AI-generated recommendations

---

### 3. Cost Calculator

**Purpose**: Calculate and optimize formulation costs

#### Key Endpoints

**POST `/api/cost-calculator/analyze`**
- Analyzes cost of a formulation
- Input: Ingredients with percentages
- Output: Total cost, cost per unit, breakdown by ingredient

**GET `/api/cost-calculator/lookup-ingredient`**
- Looks up ingredient cost information
- Returns: Supplier prices, average price

**POST `/api/cost-calculator/optimize`**
- Optimizes formulation to meet target cost
- Input: Current formulation, target cost, constraints
- Output: Optimized formulation with cost reduction recommendations

**POST `/api/cost-calculator/pricing`**
- Calculates product pricing with markup
- Input: Formulation cost, markup percentage, packaging cost
- Output: Cost price, selling price, profit margin

**POST `/api/cost-calculator/cost-sheet`**
- Generates detailed cost sheet
- Input: Formulation, batch size
- Output: Complete cost breakdown

#### User Flow
1. User provides formulation with ingredient percentages
2. System looks up ingredient prices from distributor database
3. Calculates total cost and cost per unit
4. User can optimize to meet target cost
5. System suggests ingredient substitutions or percentage adjustments
6. Generates cost sheet for manufacturing

---

### 4. Inspiration Boards

**Purpose**: Track and analyze competitor products

#### Key Endpoints

**Board Management**
- **POST `/api/inspiration-boards/boards`**: Create new board
- **GET `/api/inspiration-boards/boards`**: List user's boards
- **GET `/api/inspiration-boards/boards/{board_id}`**: Get board with products
- **PUT `/api/inspiration-boards/boards/{board_id}`**: Update board
- **DELETE `/api/inspiration-boards/boards/{board_id}`**: Delete board

**Product Management**
- **POST `/api/inspiration-boards/boards/{board_id}/products`**: Add product from URL
- **POST `/api/inspiration-boards/boards/{board_id}/products/manual`**: Add product manually
- **GET `/api/inspiration-boards/products/{product_id}`**: Get product details
- **PUT `/api/inspiration-boards/products/{product_id}`**: Update product (notes, tags, rating)
- **DELETE `/api/inspiration-boards/products/{product_id}`**: Delete product

**Product Decoding**
- **POST `/api/inspiration-boards/products/{product_id}/decode`**: Decode single product
- **POST `/api/inspiration-boards/boards/{board_id}/decode-all`**: Batch decode all products

**Analysis**
- **POST `/api/inspiration-boards/analyze`**: Generate competitor analysis
- **POST `/api/inspiration-boards/fetch-product`**: Fetch product data from URL

#### User Flow
1. User creates an inspiration board (e.g., "Vitamin C Serums")
2. User adds products from e-commerce URLs or manually
3. System fetches product data (name, brand, price, ingredients)
4. User can decode products to analyze ingredients
5. System performs batch analysis of all products
6. User views competitor analysis (common ingredients, pricing trends, unique formulations)
7. User can tag, rate, and add notes to products

---

### 5. Formulation Reports

**Purpose**: Generate comprehensive analysis reports for formulations

#### Key Endpoints

**POST `/api/formulation-report-json`**
- Generates structured JSON report
- Input: INCI list, branded ingredients, BIS cautions, expected benefits
- Output: Structured report with sections, analysis table, raw text

**POST `/api/formulation-report`**
- Generates HTML formatted report
- Returns: HTML report ready for display

**POST `/api/formulation-report/pdf`**
- Generates PDF report
- Returns: PDF file download

**POST `/api/formulation-report/ppt`**
- Generates PowerPoint presentation
- Uses Presenton API
- Returns: PPT URL

#### Report Sections
1. Overview
2. Ingredient Analysis
3. Functional Categories
4. Safety Assessment
5. Regulatory Compliance
6. Cost Analysis
7. Benefits & Claims
8. Recommendations
9. Risk Assessment
10. Conclusion

---

### 6. Ingredient Search

**Purpose**: Search and retrieve ingredient information

#### Key Endpoints

**POST `/api/ingredients/search`**
- Searches ingredient database
- Input: Query string, limit
- Output: Matching ingredients with categories and functions

**GET `/api/ingredients/by-name/{name}`**
- Gets detailed ingredient information by name
- Returns: Full ingredient data including suppliers, safety data, functions

---

### 7. History & Comparison

**Purpose**: Track user activity and compare products

#### Key Endpoints

**Decode History**
- **POST `/api/save-decode-history`**: Save ingredient analysis
- **GET `/api/decode-history`**: Get user's decode history
- **GET `/api/decode-history/{history_id}`**: Get specific decode entry

**Compare History**
- **POST `/api/save-compare-history`**: Save product comparison
- **GET `/api/compare-history`**: Get comparison history
- **GET `/api/compare-history/{history_id}`**: Get specific comparison

**Product Comparison**
- **POST `/api/compare-products`**: Compare multiple products
- Input: Array of products with ingredient lists
- Output: Common ingredients, unique ingredients, analysis

---

## User Flows

### Flow 1: Ingredient Analysis from Product Image

1. User provides URL/inci
2. System extracts text using scraping
3. AI (Claude) identifies INCI names from extracted text
4. System matches ingredients against MongoDB database
5. Returns categorized analysis:
   - Active vs Excipient classification
   - Functional categories
   - Safety data
   - Supplier information
   - BIS compliance warnings
   - Claim as indian distributor form

### Flow 2: Formula Generation

1. User specifies requirements:
   - Product type (serum, cream, cleanser, etc.)
   - Desired benefits (brightening, hydration, anti-aging)
   - Exclusions (paraben-free, silicone-free, etc.)
   - Hero ingredients
   - Cost range
   - Texture preferences
2. System selects ingredients:
   - Maps benefits to functional categories
   - Queries MongoDB for matching ingredients
   - Applies exclusions and filters
   - Prioritizes hero ingredients
3. System allocates percentages:
   - Uses product type templates
   - Applies rule-based allocation
   - Ensures total = 100%
4. AI optimization:
   - Fine-tunes percentages
   - Checks compatibility
   - Generates insights
5. Phase organization:
   - Organizes ingredients into manufacturing phases
   - Provides mixing instructions
6. Validation:
   - Cost verification
   - BIS compliance checking
   - Safety validation
7. Returns complete formula with all metadata

### Flow 3: Inspiration Board Analysis

1. User creates board (e.g., "Competitor Vitamin C Serums")
2. User adds products:
   - From e-commerce URLs (Nykaa, Amazon, etc.)
   - Or manually enters product details
3. System fetches product data:
   - Name, brand, price
   - Ingredient list (if available)
4. User triggers decode:
   - Single product or batch decode
   - System analyzes ingredients for each product
5. User requests competitor analysis:
   - System compares all products
   - Identifies common ingredients
   - Highlights unique formulations
   - Analyzes pricing trends
6. User views insights:
   - Market positioning
   - Ingredient trends
   - Pricing analysis
   - Formulation recommendations

### Flow 4: Cost Optimization

1. User has a formulation with ingredient percentages
2. System calculates current cost:
   - Looks up ingredient prices from distributor database
   - Calculates total cost per batch
   - Shows cost per unit
3. User sets target cost
4. System optimizes:
   - Suggests ingredient substitutions
   - Adjusts percentages within safe ranges
   - Maintains product efficacy
5. Returns optimized formulation with cost breakdown

---

## Starting the Backend

### Prerequisites

- Python 3.8 or higher
- MongoDB instance (local or remote)
- Claude API key

### Installation Steps

1. **Navigate to project directory:**
   ```bash
   cd SkinBB_AI_Tools
   ```

2. **Activate virtual environment:**
   ```bash
   # Windows
   venv_main\Scripts\activate
   
   # Linux/Mac
   source venv_main/bin/activate
   ```

3. **Install dependencies (if not already installed):**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   - Create `.env` file in project root
   - Add required variables (see Environment Configuration section)

### Starting the Server

#### Method 1: Using the startup script (Recommended)

```bash
python start_backend.py
```

This script:
- Checks for correct directory
- Starts the server on `http://localhost:8000`
- Enables auto-reload for development
- Provides helpful startup messages

#### Method 2: Using uvicorn directly

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Server Information

Once started, the server provides:
- **API Base URL**: `http://localhost:8000`
- **Interactive API Docs**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative Docs**: `http://localhost:8000/redoc` (ReDoc)
- **Health Check**: `http://localhost:8000/health`

### Stopping the Server

Press `Ctrl+C` in the terminal to stop the server.

---

## Environment Configuration

### Required Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# Claude AI Configuration (Required)
CLAUDE_API_KEY=your-claude-api-key-here
CLAUDE_MODEL=claude-sonnet-4-5-20250929
# Alternative: MODEL_NAME=claude-sonnet-4-5-20250929

# MongoDB Configuration (Required)
MONGO_URI=mongodb://username:password@host:port/database?authSource=admin
DB_NAME=skin_bb

# Google Vision API (Optional - for OCR features)
GOOGLE_APPLICATION_CREDENTIALS=path/to/vision_key.json
GOOGLE_CLOUD_PROJECT=your-project-id

# OpenAI API (Optional - for some features)
OPENAI_API_KEY=your-openai-api-key
```

### Environment Variable Details

- **CLAUDE_API_KEY**: Required for AI-powered features (formula generation, analysis)
- **MONGO_URI**: MongoDB connection string with authentication
- **DB_NAME**: Database name (default: `skin_bb`)
- **GOOGLE_APPLICATION_CREDENTIALS**: Path to Google Vision API JSON key file (for OCR)
- **GOOGLE_CLOUD_PROJECT**: Google Cloud project ID (for OCR)

### CORS Configuration

The backend is configured to accept requests from:
- `https://tt.skintruth.in`
- `https://capi.skintruth.in`
- `https://metaverse.skinbb.com`
- `http://localhost:5174` (Frontend dev server)
- `http://localhost:5173` (Alternative frontend port)
- `http://localhost:3000` (Alternative frontend port)
- `http://localhost:8000` (Backend itself)
- `http://localhost:8501` (Streamlit apps)

---


## Key Features Summary

| Feature | Purpose | Main Endpoint |
|---------|---------|---------------|
| **INCI Analysis** | Analyze cosmetic ingredients | `POST /api/analyze-inci` |
| **Formula Generation** | Generate cosmetic formulations | `POST /api/formula/generate` |
| **Cost Calculator** | Calculate and optimize costs | `POST /api/cost-calculator/analyze` |
| **Inspiration Boards** | Track competitor products | `POST /api/inspiration-boards/boards` |
| **Formulation Reports** | Generate analysis reports | `POST /api/formulation-report-json` |
| **Ingredient Search** | Search ingredient database | `POST /api/ingredients/search` |
| **History** | Track user activity | `GET /api/decode-history` |

---

## Additional Resources

- **Interactive API Documentation**: Visit `http://localhost:8000/docs` when server is running
- **OpenAPI Specification**: Available at `http://localhost:8000/openapi.json`
- **Health Check**: `GET /health` - Basic server status
- **Server Health**: `GET /api/server-health` - Comprehensive health check (Chrome, Claude API, environment)

---

**Document Version**: 1.0  
**Last Updated**: 2025  
**Maintained By**: Formulynx Development Team

