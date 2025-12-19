# Frontend Implementation Instructions: New Distributor Claim Flow

## Overview
The distributor claim flow has been changed from claiming ingredients directly to claiming suppliers first, then selecting ingredients from those suppliers.

## New Flow
1. User clicks "Claim Distributor" → Claims a **supplier** (not ingredient)
2. After claiming supplier → Get list of all ingredients from that supplier (with pagination)
3. User selects ingredients from that supplier
4. User can add more suppliers and select their ingredients
5. On registration → Distributor is mapped to suppliers and their selected ingredients
6. Response shows detailed supplier-ingredient mappings

---

## API Endpoints

### 1. Get Suppliers (Updated)
**Endpoint:** `GET /suppliers/paginated`

**Query Parameters:**
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 50) - Maximum records to return
- `search` (string, optional) - Search term for supplier name

**Response:**
```json
{
  "suppliers": [
    {
      "supplierId": "507f1f77bcf86cd799439011",
      "supplierName": "Supplier Name"
    }
  ],
  "total": 100,
  "skip": 0,
  "limit": 50,
  "hasMore": true
}
```

**Note:** This endpoint now returns both `supplierId` and `supplierName` (previously only returned names).

---

### 2. Get Ingredients by Supplier (NEW)
**Endpoint:** `GET /suppliers/{supplier_id}/ingredients`

**Path Parameters:**
- `supplier_id` (string, required) - The supplier ID

**Query Parameters:**
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 50) - Maximum records to return
- `search` (string, optional) - Search term to filter ingredients by name

**Response:**
```json
{
  "supplier_id": "507f1f77bcf86cd799439011",
  "supplier_name": "Supplier Name",
  "ingredients": [
    {
      "ingredient_id": "507f191e810c19729de860ea",
      "ingredient_name": "Ingredient Name",
      "original_inci_name": "INCI Name",
      "category": "Category",
      "supplier_id": "507f1f77bcf86cd799439011"
    }
  ],
  "total": 50,
  "skip": 0,
  "limit": 50,
  "hasMore": false
}
```

**Authentication:** Requires JWT token

---

### 3. Register Distributor (UPDATED)
**Endpoint:** `POST /distributor/register`

**Request Body:**
```json
{
  "firmName": "ABC Distributors",
  "category": "Pvt Ltd",
  "registeredAddress": "123 Main St, City",
  "contactPersons": [
    {
      "name": "John Doe",
      "number": "+91-1234567890",
      "email": "contact@abc.com",
      "zones": ["India"]
    }
  ],
  "suppliers": [
    {
      "supplierId": "507f1f77bcf86cd799439011",
      "supplierName": "Supplier 1",
      "selectedIngredientIds": [
        "507f191e810c19729de860ea",
        "507f191e810c19729de860eb"
      ]
    },
    {
      "supplierId": "507f1f77bcf86cd799439012",
      "supplierName": "Supplier 2",
      "selectedIngredientIds": [
        "507f191e810c19729de860ec"
      ]
    }
  ],
  "yourInfo": {
    "name": "John Doe",
    "email": "john@abc.com",
    "designation": "Director",
    "contactNo": "+91-9876543210"
  },
  "acceptTerms": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Distributor registration submitted successfully",
  "distributorId": "507f1f77bcf86cd799439013",
  "details": {
    "firmName": "ABC Distributors",
    "suppliers": [
      {
        "supplierId": "507f1f77bcf86cd799439011",
        "supplierName": "Supplier 1",
        "ingredients": [
          {
            "ingredientId": "507f191e810c19729de860ea",
            "ingredientName": "Ingredient Name 1",
            "originalInciName": "INCI Name 1",
            "category": "Category 1"
          }
        ]
      }
    ],
    "totalSuppliers": 2,
    "totalIngredients": 3
  }
}
```

**Changes:**
- Removed: `ingredientName`, `principlesSuppliers` (old structure)
- Added: `suppliers` array with `supplierId`, `supplierName`, and `selectedIngredientIds`

**Authentication:** Requires JWT token

---

### 4. Get Distributor by Ingredient (UPDATED Response)
**Endpoint:** `GET /distributor/by-ingredient/{ingredient_name}`

**Response now includes:**
```json
[
  {
    "_id": "distributor_id",
    "firmName": "ABC Distributors",
    "ingredientName": "Ingredient Name",
    "supplierIngredientMappings": [
      {
        "supplierId": "507f1f77bcf86cd799439011",
        "supplierName": "Supplier 1",
        "ingredients": [
          {
            "ingredientId": "507f191e810c19729de860ea",
            "ingredientName": "Ingredient Name",
            "originalInciName": "INCI Name",
            "category": "Category"
          }
        ]
      }
    ],
    "principlesSupplierIds": ["507f1f77bcf86cd799439011"],
    "principlesSuppliers": ["Supplier 1"],
    ...
  }
]
```

**New Field:** `supplierIngredientMappings` - Shows detailed mapping of which supplier provides which ingredients

---

## Frontend Implementation Steps

### Step 1: Update Claim Button Handler
**Location:** `DecodeFormulationDetails.tsx` and `DecodeFormulations.tsx`

**Current:** `handleClaimClick(ingredientName, ingredientId)`

**New:** `handleClaimClick(supplierId, supplierName)`

**Example:**
```typescript
const handleClaimClick = useCallback((supplierId: string, supplierName: string) => {
  // Open modal/dialog to claim this supplier
  setSelectedSupplier({ supplierId, supplierName });
  setClaimModalOpen(true);
}, []);
```

---

### Step 2: Create Supplier Claim Modal
Create a modal that:
1. Shows supplier information
2. Fetches ingredients for that supplier using: `GET /suppliers/{supplier_id}/ingredients`
3. Displays ingredients with pagination
4. Allows user to select/deselect ingredients (checkboxes)
5. Has "Add Another Supplier" button to add more suppliers
6. Shows list of selected suppliers and their ingredients

**State Management:**
```typescript
interface SelectedSupplier {
  supplierId: string;
  supplierName: string;
  selectedIngredientIds: string[];
}

const [selectedSuppliers, setSelectedSuppliers] = useState<SelectedSupplier[]>([]);
const [currentSupplierIngredients, setCurrentSupplierIngredients] = useState([]);
const [pagination, setPagination] = useState({ skip: 0, limit: 50, hasMore: false });
```

**API Call Example:**
```typescript
const fetchSupplierIngredients = async (supplierId: string, skip: number = 0, search?: string) => {
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: '50',
    ...(search && { search })
  });
  
  const response = await fetch(
    `/api/suppliers/${supplierId}/ingredients?${params}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  const data = await response.json();
  return data;
};
```

---

### Step 3: Update Registration Form
**Location:** Distributor registration form/modal

**Changes:**
1. Remove `ingredientName` field
2. Remove `principlesSuppliers` field (or keep for display only)
3. Add `suppliers` array field that collects selected suppliers and their ingredients

**Form Data Structure:**
```typescript
const formData = {
  firmName: string,
  category: string,
  registeredAddress: string,
  contactPersons: Array<{
    name: string;
    number: string;
    email: string;
    zones: string[];
  }>,
  suppliers: Array<{
    supplierId: string;
    supplierName: string;
    selectedIngredientIds: string[];
  }>,
  yourInfo: {
    name: string;
    email: string;
    designation: string;
    contactNo: string;
  },
  acceptTerms: boolean
};
```

---

### Step 4: Update Registration API Call
**Location:** Registration submit handler

**Example:**
```typescript
const handleSubmit = async (formData) => {
  try {
    const response = await fetch('/api/distributor/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        ...formData,
        suppliers: selectedSuppliers // Array of { supplierId, supplierName, selectedIngredientIds }
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      // Show success message
      // Display result.details for confirmation
      console.log('Registered suppliers:', result.details.suppliers);
      console.log('Total ingredients:', result.details.totalIngredients);
    }
  } catch (error) {
    // Handle error
  }
};
```

---

### Step 5: Display Distributor Information
**Location:** Where distributor info is displayed (ingredient details, etc.)

**New Fields to Display:**
- `supplierIngredientMappings` - Show which supplier provides which ingredients
- Display supplier names alongside distributor info
- Show ingredient list grouped by supplier

**Example Display:**
```typescript
{distributor.supplierIngredientMappings?.map((mapping) => (
  <div key={mapping.supplierId}>
    <h4>Supplier: {mapping.supplierName}</h4>
    <ul>
      {mapping.ingredients.map((ing) => (
        <li key={ing.ingredientId}>
          {ing.ingredientName} ({ing.originalInciName})
        </li>
      ))}
    </ul>
  </div>
))}
```

---

## UI/UX Recommendations

1. **Claim Button:** Change text from "Claim Distributor" to "Claim Supplier" or keep as is but update tooltip
2. **Modal Flow:**
   - Step 1: Select supplier (if not already selected)
   - Step 2: Load and display ingredients with pagination
   - Step 3: Select ingredients (checkboxes with search)
   - Step 4: Option to "Add Another Supplier" (repeat steps 1-3)
   - Step 5: Review selected suppliers and ingredients
   - Step 6: Fill registration form
   - Step 7: Submit

3. **Ingredient Selection:**
   - Show pagination controls
   - Add search/filter functionality
   - Show selected count: "X ingredients selected"
   - Allow "Select All" / "Deselect All" for current page

4. **Selected Suppliers Display:**
   - Show list of selected suppliers
   - For each supplier, show count of selected ingredients
   - Allow removing suppliers
   - Allow editing ingredient selection for each supplier

5. **Validation:**
   - At least one supplier must be selected
   - At least one ingredient must be selected per supplier
   - Show validation errors clearly

---

## Backward Compatibility

The backend maintains backward compatibility:
- Old distributor records (without `supplierIngredientMappings`) will still work
- Query endpoints will return both old and new format
- `ingredientName` field is still populated for backward compatibility

However, for new registrations, use the new `suppliers` array structure.

---

## Testing Checklist

- [ ] Claim button opens supplier selection
- [ ] Can fetch and display ingredients for a supplier
- [ ] Pagination works for ingredients list
- [ ] Search/filter works for ingredients
- [ ] Can select/deselect ingredients
- [ ] Can add multiple suppliers
- [ ] Can remove suppliers from selection
- [ ] Registration form validates correctly
- [ ] Registration API call includes suppliers array
- [ ] Success response displays supplier-ingredient mappings
- [ ] Distributor display shows supplier-ingredient mappings
- [ ] Existing distributor queries still work

---

## Migration Notes

If you have existing distributor registration forms:
1. Update the form to collect suppliers instead of single ingredient
2. Update the claim button handlers
3. Test thoroughly with both old and new data
4. Consider showing a migration message for users with old registrations

