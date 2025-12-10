# SkinBB AI Skincare Chatbot - Complete API Documentation

**Version:** 1.0  
**Base URL:** `https://capi.skintruth.in`  
**Total Endpoints:** 70+  
**Total API Paths:** 64  
**Documentation Generated:** Auto-generated from OpenAPI 3.1 specification

## 📋 Overview

This is the complete API documentation for the SkinBB AI Skincare Chatbot platform. All endpoints are organized by functionality and include request/response examples.

### Quick Links
- **Swagger UI:** Use `swagger_server.html` or visit `/docs` (if configured)
- **Postman Collection:** Import `SkinBB_API.postman_collection.json`
- **OpenAPI Spec:** `openapi.json`

---

## Table of Contents

1. [Core Endpoints](#core-endpoints)
2. [INCI Analysis](#inci-analysis)
3. [Formulation Reports](#formulation-reports)
4. [Cost Calculator](#cost-calculator)
5. [Formula Generation](#formula-generation)
6. [Inspiration Boards](#inspiration-boards)
7. [Face Analysis](#face-analysis)
8. [Ingredient Search](#ingredient-search)
9. [Market Research](#market-research)
10. [History & Comparison](#history--comparison)

---

## Core Endpoints

### GET `/`
**Description:** Root endpoint with API information

**Response:**
```json
{
  "message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact v1."
}
```

---

### GET `/health`
**Description:** Basic health check endpoint

**Response:**
```json
{
  "status": "healthy",
  "message": "Server is running",
  "endpoints": {
    "api_docs": "/docs",
    "server_health": "/api/server-health",
    "test_selenium": "/api/test-selenium"
  }
}
```

---

## INCI Analysis

### GET `/api/server-health`
**Description:** Comprehensive server health check endpoint. Tests: Chrome availability, Claude API, environment variables.

**Response:**
```json
{
  "status": "healthy",
  "chrome_available": true,
  "claude_api_available": true,
  "environment_variables": {...}
}
```

---

### GET `/api/bis-rag/health`
**Description:** Health check endpoint for BIS RAG functionality.

**Response:**
```json
{
  "status": "healthy",
  "rag_system": "operational"
}
```

---

### GET `/api/test-selenium`
**Description:** Test endpoint to check if Selenium is working

**Response:**
```json
{
  "status": "success",
  "selenium": "working"
}
```

---

### POST `/api/analyze-inci-form`
**Description:** Analyze INCI ingredients from form data

**Request Body (form-urlencoded):**
```
inci_names: ["Water", "Glycerin", "Hyaluronic Acid"]
```

**Response:**
```json
{
  "grouped": [...],
  "unmatched": [...],
  "overall_confidence": 0.95,
  "processing_time": 1.234
}
```

---

### POST `/api/analyze-inci`
**Description:** Analyze INCI ingredients (supports multiple input types)

**Request Body (JSON):**
```json
{
  "input_type": "text|pdf|image|camera",
  "inci_names": ["Water", "Glycerin"],
  "pdf_file": "<file>",
  "image_file": "<file>",
  "camera_image": "<base64>"
}
```

**Response:**
```json
{
  "grouped": [
    {
      "inci_name": "Water",
      "category": "Excipient",
      "function": "Solvent",
      "suppliers": [...],
      "safety_data": {...}
    }
  ],
  "unmatched": [...],
  "overall_confidence": 0.95,
  "extracted_text": "Raw OCR text",
  "processing_time": 2.5
}
```

---

### POST `/api/extract-ingredients-from-url`
**Description:** Extract ingredients from a product URL. This endpoint ONLY extracts ingredients - it does NOT analyze them.

**Request Body (JSON):**
```json
{
  "url": "https://nykaa.com/product/..."
}
```

**Response:**
```json
{
  "ingredients": ["Water", "Glycerin", "Hyaluronic Acid"],
  "extracted_text": "Full scraped text...",
  "platform": "nykaa|amazon|flipkart|purplle",
  "url": "https://...",
  "processing_time": 5.123
}
```

---

### POST `/api/analyze-url`
**Description:** Extract ingredients from a product URL and analyze them. The endpoint will:
1. Scrape the URL to extract text content
2. Use AI to extract ingredient list from the text
3. Analyze the extracted ingredients
4. Return the analysis results with extracted text

**Request Body (JSON):**
```json
{
  "url": "https://example.com/product/..."
}
```

**Response:**
```json
{
  "grouped": [...],
  "unmatched": [...],
  "extracted_text": "...",
  "overall_confidence": 0.92
}
```

---

### GET `/api/suppliers`
**Description:** Get all suppliers from ingre_suppliers collection. Returns list of supplier names.

**Response:**
```json
{
  "suppliers": ["Supplier A", "Supplier B", ...]
}
```

---

### POST `/api/ingredients/categories`
**Description:** Get categories (Active/Excipient) for INCI ingredients from ingre_inci collection

**Request Body (JSON):**
```json
{
  "inci_names": ["INCI1", "INCI2", ...]
}
```

**Response:**
```json
{
  "categories": {
    "INCI1": "Active",
    "INCI2": "Excipient",
    ...
  }
}
```

---

### GET `/api/suppliers/paginated`
**Description:** Get suppliers with pagination

**Query Parameters:**
- `page`: int (default: 1)
- `limit`: int (default: 50)

**Response:**
```json
{
  "suppliers": [...],
  "total": 100,
  "page": 1,
  "limit": 50
}
```

---

### POST `/api/distributor/register`
**Description:** Register a new distributor ingredient

**Request Body (JSON):**
```json
{
  "ingredientName": "Hyaluronic Acid",
  "supplier": "Supplier Name",
  "price": 100.50,
  "unit": "kg"
}
```

---

### GET `/api/distributor/verify-ingredient-id/{ingredient_id}`
**Description:** Verify ingredient by ID

**Path Parameters:**
- `ingredient_id`: string

---

### GET `/api/distributor/by-ingredient/{ingredient_name}`
**Description:** Get distributor information by ingredient name

**Path Parameters:**
- `ingredient_name`: string

---

### POST `/api/compare-products`
**Description:** Compare multiple products by their ingredient lists

**Request Body (JSON):**
```json
{
  "products": [
    {
      "name": "Product 1",
      "ingredients": ["Water", "Glycerin"]
    },
    {
      "name": "Product 2",
      "ingredients": ["Water", "Hyaluronic Acid"]
    }
  ]
}
```

**Response:**
```json
{
  "comparison": {
    "common_ingredients": ["Water"],
    "unique_ingredients": {...},
    "analysis": {...}
  }
}
```

---

## Formulation Reports

### POST `/api/formulation-report-json`
**Description:** Generate formulation report and return as structured JSON

**Request Body (JSON):**
```json
{
  "inciList": ["Water", "Glycerin", "Hyaluronic Acid"],
  "brandedIngredients": ["Hyaluronic Acid"],
  "notBrandedIngredients": ["Water", "Glycerin"],
  "bisCautions": {
    "Hyaluronic Acid": ["Keep away from eyes"]
  },
  "expectedBenefits": "Hydration and anti-aging"
}
```

**Response:**
```json
{
  "inci_list": ["Water", "Glycerin", "Hyaluronic Acid"],
  "sections": [
    {
      "title": "Overview",
      "content": "..."
    },
    {
      "title": "Ingredient Analysis",
      "content": [...]
    }
  ],
  "analysis_table": [...],
  "raw_text": "..."
}
```

---

### POST `/api/formulation-report`
**Description:** Generate formulation report (HTML format)

**Request Body (JSON):**
```json
{
  "inciList": ["Water", "Glycerin", "Niacinamide"]
}
```

**Response:** HTML formatted report

---

### GET `/api/formulation-report/status`
**Description:** Get status of report generation

**Query Parameters:**
- `task_id`: string

---

### POST `/api/formulation-report/ppt`
**Description:** Generate PPT presentation using Presenton API from report JSON data

**Request Body (JSON):**
```json
{
  "reportData": {
    "inci_list": [...],
    "sections": [...],
    "analysis_table": [...]
  }
}
```

**Response:**
```json
{
  "ppt_url": "https://...",
  "status": "success"
}
```

---

### POST `/api/formulation-report/pdf`
**Description:** Generate PDF report

**Request Body (JSON):**
```json
{
  "reportData": {...}
}
```

**Response:** PDF file

---

## Cost Calculator

### GET `/api/cost-calculator/lookup-ingredient`
**Description:** Lookup ingredient cost information

**Query Parameters:**
- `inci`: string (required)

**Response:**
```json
{
  "inci_name": "Hyaluronic Acid",
  "suppliers": [
    {
      "name": "Supplier A",
      "price": 100.50,
      "unit": "kg"
    }
  ],
  "average_price": 95.25
}
```

---

### POST `/api/cost-calculator/analyze`
**Description:** Analyze cost of a formulation

**Request Body (JSON):**
```json
{
  "ingredients": [
    {
      "inci_name": "Water",
      "percentage": 70.0
    },
    {
      "inci_name": "Glycerin",
      "percentage": 5.0
    }
  ]
}
```

**Response:**
```json
{
  "total_cost": 25.50,
  "cost_per_unit": 0.255,
  "breakdown": [...]
}
```

---

### POST `/api/cost-calculator/optimize`
**Description:** Optimize formulation cost

**Request Body (JSON):**
```json
{
  "current_formulation": {...},
  "target_cost": 20.00,
  "constraints": {...}
}
```

**Response:**
```json
{
  "optimized_formulation": {...},
  "cost_reduction": 15.5,
  "recommendations": [...]
}
```

---

### POST `/api/cost-calculator/pricing`
**Description:** Calculate product pricing

**Request Body (JSON):**
```json
{
  "formulation_cost": 25.50,
  "markup_percentage": 300,
  "packaging_cost": 5.00
}
```

**Response:**
```json
{
  "cost_price": 25.50,
  "selling_price": 91.50,
  "profit_margin": 66.50
}
```

---

### POST `/api/cost-calculator/cost-sheet`
**Description:** Generate cost sheet

**Request Body (JSON):**
```json
{
  "formulation": {...},
  "batch_size": 100
}
```

**Response:**
```json
{
  "cost_sheet": {
    "ingredients": [...],
    "total_cost": 25.50,
    "cost_per_unit": 0.255
  }
}
```

---

## Formula Generation

### POST `/api/formula/generate`
**Description:** Generate a cosmetic formulation

**Request Body (JSON):**
```json
{
  "productType": "serum",
  "benefits": ["Brightening", "Hydration"],
  "exclusions": ["Silicone-free", "Paraben-free"],
  "heroIngredients": ["Vitamin C", "Hyaluronic Acid"],
  "costMin": 30,
  "costMax": 60,
  "texture": "gel",
  "fragrance": "none",
  "notes": "Additional requirements"
}
```

**Response:**
```json
{
  "name": "Brightening Serum",
  "version": "v1",
  "cost": 48.5,
  "ph": {"min": 5.0, "max": 5.5},
  "texture": "Lightweight gel",
  "shelfLife": "12 months",
  "phases": [...],
  "insights": [...],
  "warnings": [...],
  "compliance": {...}
}
```

---

### POST `/api/formula/save-wish-history`
**Description:** Save formula generation wish to history

**Request Body (JSON):**
```json
{
  "user_id": "user123",
  "wish_data": {...},
  "generated_formula": {...}
}
```

**Response:**
```json
{
  "history_id": "abc123",
  "status": "saved"
}
```

---

### GET `/api/formula/wish-history`
**Description:** Get wish history for a user

**Query Parameters:**
- `user_id`: string (required)
- `limit`: int (default: 50)
- `offset`: int (default: 0)

**Response:**
```json
{
  "history": [...],
  "total": 10,
  "limit": 50,
  "offset": 0
}
```

---

### GET `/api/formula/wish-history/{history_id}`
**Description:** Get specific wish history entry

**Path Parameters:**
- `history_id`: string

---

### POST `/api/make-wish/generate`
**Description:** Generate formula using Make a Wish API

**Request Body (JSON):**
```json
{
  "productType": "serum",
  "benefits": ["Brightening"],
  "exclusions": ["Paraben-free"],
  "heroIngredients": ["Vitamin C"]
}
```

---

## Inspiration Boards

### POST `/api/inspiration-boards/boards`
**Description:** Create a new inspiration board

**Query Parameters:**
- `user_id`: string (required)

**Request Body (JSON):**
```json
{
  "name": "Vitamin C Serums",
  "description": "Market research",
  "icon": "🍊",
  "color": "orange"
}
```

**Response:**
```json
{
  "board_id": "board123",
  "name": "Vitamin C Serums",
  "description": "Market research",
  "created_at": "2024-01-01T00:00:00Z",
  "product_count": 0
}
```

---

### GET `/api/inspiration-boards/boards`
**Description:** List all boards for a user

**Query Parameters:**
- `user_id`: string (required)
- `limit`: int (default: 50, max: 100)
- `offset`: int (default: 0)

**Response:**
```json
{
  "boards": [...],
  "total": 10,
  "limit": 50,
  "offset": 0
}
```

---

### GET `/api/inspiration-boards/boards/{board_id}`
**Description:** Get board details with products

**Path Parameters:**
- `board_id`: string

**Response:**
```json
{
  "board_id": "board123",
  "name": "Vitamin C Serums",
  "products": [...],
  "statistics": {...}
}
```

---

### PUT `/api/inspiration-boards/boards/{board_id}`
**Description:** Update board

**Path Parameters:**
- `board_id`: string

**Request Body (JSON):**
```json
{
  "name": "Updated Name",
  "description": "Updated description"
}
```

---

### DELETE `/api/inspiration-boards/boards/{board_id}`
**Description:** Delete board and all products

**Path Parameters:**
- `board_id`: string

---

### POST `/api/inspiration-boards/boards/{board_id}/products`
**Description:** Add product from URL to board

**Path Parameters:**
- `board_id`: string

**Query Parameters:**
- `user_id`: string (required)

**Request Body (JSON):**
```json
{
  "url": "https://nykaa.com/minimalist-vitamin-c",
  "notes": "Market leader",
  "tags": ["bestseller", "budget-friendly"]
}
```

---

### POST `/api/inspiration-boards/boards/{board_id}/products/manual`
**Description:** Add product manually to board

**Path Parameters:**
- `board_id`: string

**Query Parameters:**
- `user_id`: string (required)

**Request Body (JSON):**
```json
{
  "name": "Product Name",
  "brand": "Brand Name",
  "price": 999,
  "url": "https://...",
  "ingredients": ["Water", "Glycerin"],
  "notes": "Notes",
  "tags": ["tag1", "tag2"]
}
```

---

### GET `/api/inspiration-boards/products/{product_id}`
**Description:** Get product details

**Path Parameters:**
- `product_id`: string

**Response:**
```json
{
  "product_id": "prod123",
  "name": "Product Name",
  "brand": "Brand",
  "price": 999,
  "ingredients": [...],
  "decoded": true,
  "decoded_data": {...}
}
```

---

### PUT `/api/inspiration-boards/products/{product_id}`
**Description:** Update product (notes, tags, myRating)

**Path Parameters:**
- `product_id`: string

**Request Body (JSON):**
```json
{
  "notes": "Updated notes",
  "tags": ["new-tag"],
  "myRating": 4.5
}
```

---

### DELETE `/api/inspiration-boards/products/{product_id}`
**Description:** Delete product

**Path Parameters:**
- `product_id`: string

---

### POST `/api/inspiration-boards/products/{product_id}/decode`
**Description:** Decode single product

**Path Parameters:**
- `product_id`: string

**Query Parameters:**
- `user_id`: string (required)

**Response:**
```json
{
  "product_id": "prod123",
  "decoded": true,
  "decoded_data": {
    "ingredients": [...],
    "analysis": {...}
  }
}
```

---

### POST `/api/inspiration-boards/boards/{board_id}/decode-all`
**Description:** Batch decode all products in a board

**Path Parameters:**
- `board_id`: string

**Query Parameters:**
- `user_id`: string (required)

**Request Body (JSON):**
```json
{
  "product_ids": ["prod1", "prod2", "prod3"]
}
```

**Response:**
```json
{
  "decoded_count": 3,
  "failed_count": 0,
  "results": [...]
}
```

---

### POST `/api/inspiration-boards/fetch-product`
**Description:** Fetch product data from e-commerce URL

**Request Body (JSON):**
```json
{
  "url": "https://nykaa.com/product/..."
}
```

**Response:**
```json
{
  "name": "Product Name",
  "brand": "Brand",
  "price": 999,
  "ingredients": [...],
  "platform": "nykaa"
}
```

---

### POST `/api/inspiration-boards/analyze`
**Description:** Generate competitor analysis

**Query Parameters:**
- `user_id`: string (required)

**Request Body (JSON):**
```json
{
  "product_ids": ["id1", "id2", "id3"],
  "analysis_type": "overview"
}
```

**Response:**
```json
{
  "analysis": {
    "overview": {...},
    "ingredients": {...},
    "pricing": {...}
  }
}
```

---

### GET `/api/inspiration-boards/tags`
**Description:** Get all available tags

**Response:**
```json
{
  "tags": {
    "category1": ["tag1", "tag2"],
    "category2": ["tag3", "tag4"]
  }
}
```

---

### POST `/api/inspiration-boards/tags/validate`
**Description:** Validate tags

**Request Body (JSON):**
```json
{
  "tags": ["tag1", "tag2", "invalid-tag"]
}
```

**Response:**
```json
{
  "valid": ["tag1", "tag2"],
  "invalid": ["invalid-tag"]
}
```

---

## Face Analysis

### GET `/api/face-analysis/health`
**Description:** Face Analysis health check

---

### POST `/api/face-analysis/analyze`
**Description:** Analyze face image

**Request Body (multipart/form-data):**
- `image`: file (required)

**Response:**
```json
{
  "analysis": {
    "skin_concerns": [...],
    "recommendations": [...],
    "scores": {...}
  }
}
```

---

### POST `/api/face-analysis/analyze/json`
**Description:** Analyze face image (JSON response)

**Request Body (multipart/form-data):**
- `image`: file (required)

---

### POST `/api/face-analysis/privacy-filter`
**Description:** Apply privacy filter to face image

**Request Body (multipart/form-data):**
- `image`: file (required)

**Response:** Filtered image

---

### POST `/api/face-analysis/recommendations`
**Description:** Get product recommendations based on face analysis

**Request Body (JSON):**
```json
{
  "skin_concerns": ["acne", "dryness"],
  "skin_type": "combination"
}
```

**Response:**
```json
{
  "recommendations": [
    {
      "product_name": "Product Name",
      "match_score": 0.95,
      "reason": "..."
    }
  ]
}
```

---

### GET `/api/face-analysis/config`
**Description:** Get face analysis configuration

---

### GET `/api/face-analysis/config/analysis-parameters`
**Description:** Get analysis parameters configuration

---

## Ingredient Search

### POST `/api/ingredients/search`
**Description:** Search for ingredients

**Request Body (JSON):**
```json
{
  "query": "hyaluronic",
  "limit": 10
}
```

**Response:**
```json
{
  "results": [
    {
      "inci_name": "Hyaluronic Acid",
      "category": "Active",
      "function": "Humectant"
    }
  ],
  "total": 1
}
```

---

### GET `/api/ingredients/by-name/{name}`
**Description:** Get ingredient by name

**Path Parameters:**
- `name`: string

**Response:**
```json
{
  "inci_name": "Hyaluronic Acid",
  "category": "Active",
  "function": "Humectant",
  "suppliers": [...],
  "safety_data": {...}
}
```

---

## Market Research

### POST `/api/market-research`
**Description:** Perform market research

**Request Body (JSON):**
```json
{
  "query": "vitamin c serums",
  "filters": {...}
}
```

**Response:**
```json
{
  "products": [...],
  "analysis": {...},
  "trends": [...]
}
```

---

## History & Comparison

### POST `/api/save-decode-history`
**Description:** Save decode history

**Request Body (JSON):**
```json
{
  "user_id": "user123",
  "name": "Product Name",
  "ingredients": [...],
  "analysis_result": {...}
}
```

---

### GET `/api/decode-history`
**Description:** Get decode history

**Query Parameters:**
- `user_id`: string (required)
- `limit`: int
- `offset`: int

---

### GET `/api/decode-history/{history_id}`
**Description:** Get specific decode history entry

**Path Parameters:**
- `history_id`: string

---

### POST `/api/save-compare-history`
**Description:** Save compare history

**Request Body (JSON):**
```json
{
  "user_id": "user123",
  "name": "Comparison Name",
  "products": [...],
  "comparison_result": {...}
}
```

---

### GET `/api/compare-history`
**Description:** Get compare history

**Query Parameters:**
- `user_id`: string (required)
- `limit`: int
- `offset`: int

---

### GET `/api/compare-history/{history_id}`
**Description:** Get specific compare history entry

**Path Parameters:**
- `history_id`: string

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Error message"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "field"],
      "msg": "error message",
      "type": "value_error"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

---

## Authentication

Currently, the API does not require authentication. Some endpoints may require `user_id` as a query parameter for user-specific operations.

---

## Rate Limiting

Rate limiting may be applied. Check response headers for rate limit information.

---

## CORS

The API supports CORS for the following origins:
- `https://tt.skintruth.in`
- `https://capi.skintruth.in`
- `https://metaverse.skinbb.com`
- `http://localhost:5174`
- `http://localhost:5173`
- `http://localhost:3000`
- `http://localhost:8000`
- `http://localhost:8501`

---

## Support

For API support and questions, please refer to:
- Swagger UI: Use `swagger_server.html` or visit `/docs` (if configured)
- Postman Collection: Import `SkinBB_API.postman_collection.json`

---

**Last Updated:** Auto-generated from OpenAPI specification  
**Total Endpoints:** 70+

