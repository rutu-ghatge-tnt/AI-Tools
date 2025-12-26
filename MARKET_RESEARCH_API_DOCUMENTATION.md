# Market Research API Documentation

## Overview

The Market Research API is an enhanced endpoint that matches products from a URL or INCI ingredient list with products in the database. It includes AI-powered category analysis, intelligent filtering, pagination, and comprehensive market insights.

**Endpoint:** `POST /api/market-research`

**Authentication:** Required (JWT token in Authorization header)

---

## Request Format

### Request Body

```json
{
  "input_type": "url" | "inci",
  "url": "https://example.com/product/...",  // Required if input_type is "url"
  "inci": "Water, Glycerin, Ceramide 3, ...",  // Required if input_type is "inci"
  "page": 1,  // Optional, default: 1
  "page_size": 10  // Optional, default: 10, max: 100
}
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `input_type` | string | Yes | - | Either `"url"` or `"inci"` |
| `url` | string | Conditional | - | Required if `input_type` is `"url"`. Must be a valid HTTP/HTTPS URL |
| `inci` | string | Conditional | - | Required if `input_type` is `"inci"`. Comma-separated ingredient list |
| `page` | integer | No | 1 | Page number (1-indexed) |
| `page_size` | integer | No | 10 | Number of products per page (max: 100) |

---

## Response Format

### Success Response (200 OK)

```json
{
  "products": [
    {
      "id": "690aea3a6751946f74d29ac8",
      "productName": "Product Name",
      "brand": "Brand Name",
      "ingredients": ["Water", "Glycerin", ...],
      "image": "https://...",
      "images": ["https://...", ...],
      "price": 999.99,
      "salePrice": 799.99,
      "description": "Product description",
      "matched_ingredients": ["Ceramide 3", "Sodium Hyaluronate"],
      "match_count": 2,
      "total_ingredients": 25,
      "match_percentage": 66.67,
      "match_score": 66.67,
      "active_match_count": 2,
      "active_ingredients": ["Ceramide 3", "Sodium Hyaluronate"],
      "category": "skincare",
      "subcategory": "moisturizer"
    },
    ...
  ],
  "extracted_ingredients": ["Water", "Glycerin", "Ceramide 3", ...],
  "total_matched": 263,
  "processing_time": 32.12,
  "input_type": "inci",
  
  // AI Analysis Fields
  "ai_interpretation": "This formulation is clearly a facial moisturizer/cream...",
  "primary_category": "skincare",
  "subcategory": "moisturizer",
  "category_confidence": "high",
  "ai_analysis": null,
  "ai_product_type": "moisturizer",
  "ai_reasoning": null,
  
  // Market Research Overview
  "market_research_overview": "# MARKET RESEARCH OVERVIEW: ...",
  
  // Pagination
  "page": 1,
  "page_size": 10,
  "total_pages": 27
}
```

### Response Fields Explanation

#### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `products` | Array | List of matched products (paginated) |
| `extracted_ingredients` | Array | List of ingredients extracted from input |
| `total_matched` | Integer | Total number of matched products (across all pages) |
| `processing_time` | Float | Time taken for processing (in seconds) |
| `input_type` | String | Type of input processed (`"url"` or `"inci"`) |

#### AI Analysis Fields

| Field | Type | Description | When Populated |
|-------|------|-------------|----------------|
| `ai_interpretation` | String \| null | AI's detailed interpretation of the input explaining category determination | Always (when AI is available) |
| `primary_category` | String \| null | Main category: `"haircare"`, `"skincare"`, `"lipcare"`, `"bodycare"`, or `"other"` | Always (when AI is available) |
| `subcategory` | String \| null | Specific product type: `"serum"`, `"cleanser"`, `"shampoo"`, `"moisturizer"`, etc. | Always (when AI is available) |
| `category_confidence` | String \| null | Confidence level: `"high"`, `"medium"`, or `"low"` | Always (when AI is available) |
| `ai_product_type` | String \| null | Product type identified by AI (same as `subcategory` when category analysis succeeds) | When category analysis succeeds OR when no actives found |
| `ai_analysis` | String \| null | AI analysis message (only when NO active ingredients found) | Only when `len(input_actives) == 0` |
| `ai_reasoning` | String \| null | AI reasoning for ingredient selection (only when NO active ingredients found) | Only when `len(input_actives) == 0` |

**Note:** `ai_analysis` and `ai_reasoning` are only populated when the system cannot find active ingredients in the database. When active ingredients ARE found, these fields will be `null` because the system doesn't need AI to suggest matching strategy.

#### Market Research Overview

| Field | Type | Description |
|-------|------|-------------|
| `market_research_overview` | String \| null | Comprehensive AI-generated overview including: summary, key findings, product trends, market insights, and recommendations |

#### Pagination Fields

| Field | Type | Description |
|-------|------|-------------|
| `page` | Integer | Current page number |
| `page_size` | Integer | Number of products per page |
| `total_pages` | Integer | Total number of pages |

#### Product Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Product ID |
| `productName` | String | Product name |
| `brand` | String | Brand name |
| `ingredients` | Array | List of product ingredients |
| `image` | String | Primary product image URL |
| `images` | Array | List of product image URLs |
| `price` | Float | Product price |
| `salePrice` | Float | Sale price (if available) |
| `description` | String | Product description |
| `matched_ingredients` | Array | List of ingredients that matched with input |
| `match_count` | Integer | Number of matched ingredients |
| `total_ingredients` | Integer | Total number of ingredients in product |
| `match_percentage` | Float | Percentage of input active ingredients matched |
| `match_score` | Float | Weighted match score (0-100) |
| `active_match_count` | Integer | Number of active ingredients that matched |
| `active_ingredients` | Array | List of matched active ingredients |
| `category` | String | Product category (from database) |
| `subcategory` | String | Product subcategory (from database) |

---

## Key Features

### 1. AI Category Analysis

The API automatically analyzes the input to determine:
- **Primary Category**: haircare, skincare, lipcare, bodycare, or other
- **Subcategory**: Specific product type (serum, cleanser, shampoo, etc.)
- **Interpretation**: Detailed explanation of category determination
- **Confidence**: High, medium, or low

This analysis happens **before** product matching to ensure relevance.

### 2. Category-Based Filtering

Products are filtered by category to ensure relevance:
- If `category_confidence` is `"high"` or `"medium"`, only products matching the identified category are returned
- Example: Face serum research won't show hair products even if they share active ingredients
- This prevents false positives and improves result quality

### 3. Pagination

- All matched products are returned (not just top 10)
- Use `page` and `page_size` parameters to navigate through results
- Response includes pagination metadata: `page`, `page_size`, `total_pages`

### 4. Active Ingredient Matching

- Only **active ingredients** are used for matching
- Excipients and unknown ingredients are ignored
- Products must match at least one active ingredient to be included

### 5. Market Research Overview

- AI-generated comprehensive overview of research findings
- Includes: summary, key findings, product trends, market insights, and recommendations
- Generated after product matching is complete

---

## Field Population Logic

### When Active Ingredients ARE Found

```json
{
  "ai_interpretation": "This formulation is clearly a facial moisturizer...",
  "primary_category": "skincare",
  "subcategory": "moisturizer",
  "category_confidence": "high",
  "ai_product_type": "moisturizer",  // Populated from subcategory
  "ai_analysis": null,  // null because actives were found
  "ai_reasoning": null  // null because actives were found
}
```

**Why `ai_analysis` and `ai_reasoning` are null:**
- These fields are only populated when the system cannot find active ingredients in the database
- When actives ARE found, the system doesn't need AI to suggest a matching strategy
- The category information is provided via `ai_interpretation`, `primary_category`, and `subcategory`

### When Active Ingredients ARE NOT Found

```json
{
  "ai_interpretation": "...",
  "primary_category": "skincare",
  "subcategory": "cleanser",
  "category_confidence": "medium",
  "ai_product_type": "cleanser",
  "ai_analysis": "This formulation contains no defined active ingredient...",
  "ai_reasoning": "Based on the product type, suggest matching using surfactants..."
}
```

**Why all fields are populated:**
- When no actives are found, AI analyzes the formulation to suggest what to match
- `ai_analysis` explains why no actives were found
- `ai_reasoning` explains the matching strategy
- Category analysis still runs to provide category information

---

## Example Usage

### Example 1: INCI Input with Pagination

```javascript
const response = await fetch('/api/market-research', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    input_type: 'inci',
    inci: 'Water, Glycerin, Ceramide 3, Sodium Hyaluronate, Cetearyl Alcohol',
    page: 1,
    page_size: 20
  })
});

const data = await response.json();

// Access results
console.log(`Found ${data.total_matched} products`);
console.log(`Category: ${data.primary_category} > ${data.subcategory}`);
console.log(`Showing page ${data.page} of ${data.total_pages}`);
console.log(`AI Interpretation: ${data.ai_interpretation}`);
console.log(`Market Overview: ${data.market_research_overview}`);

// Display products
data.products.forEach(product => {
  console.log(`${product.productName} - ${product.match_percentage}% match`);
});
```

### Example 2: URL Input

```javascript
const response = await fetch('/api/market-research', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    input_type: 'url',
    url: 'https://example.com/product/serum',
    page: 1,
    page_size: 10
  })
});
```

### Example 3: Pagination Navigation

```javascript
// Get first page
const page1 = await fetchMarketResearch({ page: 1, page_size: 10 });

// Navigate to next page
if (page1.page < page1.total_pages) {
  const page2 = await fetchMarketResearch({ 
    page: page1.page + 1, 
    page_size: 10 
  });
}
```

---

## Error Responses

### 400 Bad Request

```json
{
  "detail": "input_type must be 'url' or 'inci'"
}
```

```json
{
  "detail": "url is required when input_type is 'url'"
}
```

```json
{
  "detail": "Invalid URL format. Must start with http:// or https://"
}
```

### 404 Not Found

```json
{
  "detail": "No ingredients found on the product page. Please ensure the page contains ingredient information."
}
```

### 500 Internal Server Error

```json
{
  "detail": "Failed to perform market research: [error message]"
}
```

---

## Best Practices

### 1. Handle Null Fields Gracefully

```javascript
// Check if fields exist before displaying
if (data.ai_interpretation) {
  displayInterpretation(data.ai_interpretation);
}

if (data.market_research_overview) {
  displayOverview(data.market_research_overview);
}

// ai_analysis and ai_reasoning may be null when actives are found
if (data.ai_analysis) {
  displayAnalysis(data.ai_analysis);
}
```

### 2. Use Pagination for Large Results

```javascript
// Don't try to load all products at once
const pageSize = 20;
let currentPage = 1;
let allProducts = [];

do {
  const response = await fetchMarketResearch({
    page: currentPage,
    page_size: pageSize
  });
  
  allProducts.push(...response.products);
  currentPage++;
} while (currentPage <= response.total_pages);
```

### 3. Display Category Information

```javascript
// Show category information prominently
if (data.primary_category && data.subcategory) {
  displayCategoryBadge({
    category: data.primary_category,
    subcategory: data.subcategory,
    confidence: data.category_confidence
  });
}
```

### 4. Show AI Interpretation

```javascript
// Display AI interpretation to help users understand the analysis
if (data.ai_interpretation) {
  displayCard({
    title: 'Product Analysis',
    content: data.ai_interpretation,
    type: 'info'
  });
}
```

### 5. Display Market Research Overview

```javascript
// Show comprehensive overview in a dedicated section
if (data.market_research_overview) {
  displayMarkdown({
    content: data.market_research_overview,
    title: 'Market Research Overview'
  });
}
```

---

## Response Field Summary

### Always Populated (when AI available)
- ✅ `ai_interpretation`
- ✅ `primary_category`
- ✅ `subcategory`
- ✅ `category_confidence`
- ✅ `ai_product_type` (from subcategory when category analysis succeeds)

### Conditionally Populated
- ⚠️ `ai_analysis` - Only when NO active ingredients found
- ⚠️ `ai_reasoning` - Only when NO active ingredients found
- ⚠️ `market_research_overview` - Only when products are matched

### Always Populated
- ✅ `products` (array, may be empty)
- ✅ `extracted_ingredients`
- ✅ `total_matched`
- ✅ `processing_time`
- ✅ `input_type`
- ✅ `page`
- ✅ `page_size`
- ✅ `total_pages`

---

## Notes

1. **Category Filtering**: Products are filtered by category only when `category_confidence` is `"high"` or `"medium"`. If confidence is `"low"`, category filtering is not applied.

2. **Active Ingredient Matching**: Only products with at least one matching active ingredient are included in results.

3. **Pagination**: Maximum `page_size` is 100. If a larger value is provided, it will be capped at 100.

4. **Processing Time**: The API may take 20-40 seconds depending on:
   - Number of products in database
   - Number of matched products
   - AI analysis complexity

5. **Null Fields**: `ai_analysis` and `ai_reasoning` being `null` is **expected behavior** when active ingredients are found. Use `ai_interpretation` for category information instead.

---

## Support

For questions or issues, contact the backend team or refer to the API documentation at `/docs`.

