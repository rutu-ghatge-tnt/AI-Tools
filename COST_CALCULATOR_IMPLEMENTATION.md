# Cost Calculator Backend Implementation

## Overview

Complete backend implementation for the cost calculator with 4 tabs. Uses **mathematical algorithms only** - no AI required.

## Architecture

### Algorithm Choice: **Linear Programming** (not Knapsack)

**Why Linear Programming?**
- **Better for continuous variables**: Ingredient percentages are continuous (e.g., 5.25%), not discrete items
- **Handles constraints**: Can set min/max percentages, fixed ingredients, phase totals
- **Optimizes cost**: Minimizes total cost while maintaining formulation integrity
- **Industry standard**: Used in production planning, resource allocation, and cost optimization

**Why not Knapsack?**
- Knapsack is for discrete items (0 or 1, can't take half)
- Percentages are continuous (can be any value between min and max)
- Linear programming is the correct algorithm for this problem

## File Structure

```
app/ai_ingredient_intelligence/
├── models/
│   └── cost_calculator_schemas.py      # Request/Response schemas
├── logic/
│   ├── cost_calculator.py              # Cost calculation logic
│   ├── cost_optimizer.py               # Linear programming optimization
│   ├── cost_pricing.py                 # Pricing scenarios
│   └── cost_sheet.py                   # Cost sheet generation
└── api/
    └── cost_calculator.py               # API endpoints
```

## API Endpoints

### 1. Cost Analysis (`POST /api/cost-calculator/analyze`)

**Purpose**: Calculate detailed cost breakdown

**Input**:
- Batch settings (size, unit size, packaging, labeling, overhead)
- Phases with ingredients (percentage, cost per kg)

**Output**:
- Ingredient costs (per batch, per unit, per gram)
- Phase costs
- Total costs (raw materials, packaging, labeling, manufacturing)
- Top cost contributors
- Cost by category

**Calculations**:
```
grams_needed = (percent / 100) * batch_grams
cost_for_batch = (grams_needed / 1000) * cost_per_kg
cost_per_unit = cost_for_batch / batch_size
```

### 2. Cost Optimization (`POST /api/cost-calculator/optimize`)

**Purpose**: Optimize formulation to reduce cost

**Algorithm**: Linear Programming (scipy.optimize.linprog)

**How it works**:
1. **Objective**: Minimize total cost
2. **Variables**: Ingredient percentages
3. **Constraints**:
   - Total percentage = 100%
   - Min/max percentages for each ingredient
   - Fixed percentages for hero ingredients (optional)
   - Phase total constraints (optional)
4. **Solve**: Using HiGHS solver (fast and reliable)

**Input**:
- Same as analyze, plus:
  - Target cost per unit (optional)
  - Target cost reduction % (optional)
  - Constraints (min/max percentages)
  - Preserve hero ingredients flag

**Output**:
- Original vs optimized cost
- Cost reduction amount and percentage
- New percentages for each ingredient
- Cost savings per ingredient
- Optimization summary

**Example**:
```python
# Original: 5% Niacinamide at ₹1200/kg
# Optimized: 4% Niacinamide at ₹1200/kg
# Savings: 1% reduction saves ₹X per unit
```

### 3. Pricing Scenarios (`POST /api/cost-calculator/pricing`)

**Purpose**: Calculate pricing for different multipliers

**Input**: Same as analyze

**Output**:
- Scenarios for multipliers: 2x, 2.5x, 3x, 4x
- MRP, profit per unit, profit margin %, total profit
- Recommended pricing (typically 3x for cosmetics = 67% margin)

**Calculations**:
```
MRP = cost_per_unit * multiplier
profit_per_unit = MRP - cost_per_unit
profit_margin = (profit_per_unit / MRP) * 100
total_profit = profit_per_unit * batch_size
```

### 4. Cost Sheet (`POST /api/cost-calculator/cost-sheet`)

**Purpose**: Generate export-ready cost sheet

**Input**: Same as analyze

**Output**:
- Flattened list of all ingredients with costs
- Cost summary
- Phase summaries
- Ready for export (JSON, CSV, Excel)

## Usage Examples

### Example 1: Basic Cost Analysis

```python
import requests

url = "http://localhost:8000/api/cost-calculator/analyze"

data = {
    "batch_settings": {
        "batch_size": 1000,
        "unit_size": 30,
        "packaging_cost_per_unit": 18,
        "labeling_cost_per_unit": 3,
        "manufacturing_overhead_percent": 15
    },
    "phases": [
        {
            "id": "A",
            "name": "Water Phase",
            "ingredients": [
                {
                    "id": 1,
                    "name": "Purified Water",
                    "inci": "Aqua",
                    "percent": 74.30,
                    "cost_per_kg": 0.15,
                    "function": "Solvent"
                },
                {
                    "id": 2,
                    "name": "Niacinamide",
                    "inci": "Niacinamide",
                    "percent": 5.00,
                    "cost_per_kg": 1200,
                    "function": "Brightening",
                    "is_hero": True
                }
            ]
        }
    ],
    "formula_name": "Brightening Serum"
}

response = requests.post(url, json=data)
result = response.json()

print(f"Cost per unit: ₹{result['cost_per_unit']:.2f}")
print(f"Total batch cost: ₹{result['total_batch_cost']:.2f}")
```

### Example 2: Cost Optimization

```python
url = "http://localhost:8000/api/cost-calculator/optimize"

data = {
    "batch_settings": {...},
    "phases": [...],
    "target_cost_reduction_percent": 10.0,
    "constraints": [
        {
            "ingredient_id": 2,  # Niacinamide
            "min_percent": 4.0,
            "max_percent": 6.0
        }
    ],
    "preserve_hero_ingredients": True
}

response = requests.post(url, json=data)
result = response.json()

print(f"Original cost: ₹{result['original_cost_per_unit']:.2f}")
print(f"Optimized cost: ₹{result['optimized_cost_per_unit']:.2f}")
print(f"Cost reduction: {result['cost_reduction_percent']:.2f}%")
```

## Mathematical Formulas

### Cost Calculation
```
batch_grams = batch_size * unit_size
grams_needed = (percent / 100) * batch_grams
cost_for_batch = (grams_needed / 1000) * cost_per_kg
cost_per_unit = cost_for_batch / batch_size
```

### Total Costs
```
raw_material_cost = Σ(ingredient costs)
packaging_cost_total = packaging_cost_per_unit * batch_size
labeling_cost_total = labeling_cost_per_unit * batch_size
subtotal = raw_material_cost + packaging_cost_total + labeling_cost_total
manufacturing_cost = subtotal * (manufacturing_overhead_percent / 100)
total_batch_cost = subtotal + manufacturing_cost
cost_per_unit = total_batch_cost / batch_size
```

### Optimization (Linear Programming)
```
Minimize: Σ(cost_coefficient_i * percent_i)
Subject to:
  - Σ(percent_i) = 100
  - min_percent_i ≤ percent_i ≤ max_percent_i
  - (Optional) percent_hero = fixed_value
```

## Dependencies

- **scipy**: For linear programming optimization (`scipy.optimize.linprog`)
- **numpy**: For numerical operations
- **fastapi**: For API endpoints
- **pydantic**: For data validation

All dependencies are already in `requirements.txt`.

## Testing

Test the endpoints using:

```bash
# Start the server
python start_backend.py

# Test analyze endpoint
curl -X POST "http://localhost:8000/api/cost-calculator/analyze" \
  -H "Content-Type: application/json" \
  -d @test_cost_calculator.json
```

## Key Features

✅ **No AI Required** - Pure mathematical calculations
✅ **Linear Programming** - Optimal algorithm for continuous optimization
✅ **4 Complete Tabs** - Analysis, Optimize, Pricing, Cost Sheet
✅ **Flexible Constraints** - Min/max percentages, fixed ingredients
✅ **Hero Ingredient Preservation** - Keep important ingredients fixed
✅ **Export Ready** - JSON, CSV, Excel formats
✅ **Comprehensive** - All cost components included

## Algorithm Explanation

### Why Linear Programming?

**Problem**: Minimize cost while maintaining formulation integrity

**Variables**: Ingredient percentages (continuous, 0-100%)

**Constraints**:
- Total must equal 100%
- Each ingredient has min/max bounds
- Some ingredients may be fixed (hero ingredients)

**Solution**: Linear programming finds the optimal percentages that minimize cost while satisfying all constraints.

**Example**:
- Original: 5% expensive ingredient, 95% cheap ingredient
- Optimized: 3% expensive ingredient, 97% cheap ingredient
- Result: Lower cost, same total percentage (100%), within bounds

This is exactly what linear programming solves efficiently!

