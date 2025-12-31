#!/usr/bin/env python3
"""
Test script for /api/analyze-inci endpoint
This script helps you test the API and see the debug logs in the terminal.
"""

import requests
import json

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================

# API endpoint
url = "http://localhost:8000/api/analyze-inci"

# JWT Token - Replace with your actual token
# You can get this from:
# 1. Your frontend application (check browser DevTools -> Network -> Headers -> Authorization)
# 2. Your authentication/login endpoint response
# 3. Or temporarily disable JWT auth for testing (not recommended for production)
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiI2OTI1YjFlMzdiNTk3ODI2NjM2MzQ2NGUiLCJlbWFpbCI6InJ1dHVmb3JtdWxhdG9yQGdtYWlsLmNvbSIsInJvbGVzIjpbImZvcm11bGF0b3IiXSwicm9sZSI6ImZvcm11bGF0b3IiLCJpYXQiOjE3NjcxNjE0MjAsImV4cCI6MTc5ODcxOTAyMH0.9dXvLA3v0Ls6VL9PxaSGAlHSvaYnjbfMyd_bdHDF_WE"  # ⬅️ REPLACE THIS

# Test payload - Modify as needed
payload = {
    "inci_names": [
        "Water",
        "Glycerin",
        "Niacinamide"
    ],
    "input_type": "text"
}

# ============================================================================
# SEND REQUEST
# ============================================================================

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

print("=" * 80)
print("🧪 Testing /api/analyze-inci endpoint")
print("=" * 80)
print(f"\n📡 URL: {url}")
print(f"📦 Payload: {json.dumps(payload, indent=2)}")
print(f"\n⏳ Sending request...\n")

try:
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    
    print("=" * 80)
    print("📥 RESPONSE")
    print("=" * 80)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Success! Response:")
        print(json.dumps(data, indent=2))
        
        # Check for supplier_id in response
        print("\n" + "=" * 80)
        print("🔍 CHECKING SUPPLIER_ID IN RESPONSE")
        print("=" * 80)
        
        if "items" in data:
            for idx, item in enumerate(data["items"][:5]):  # Check first 5 items
                supplier_id = item.get("supplier_id")
                supplier_name = item.get("supplier_name")
                ingredient_name = item.get("ingredient_name")
                print(f"\nItem {idx + 1}: {ingredient_name}")
                print(f"  - supplier_id: {supplier_id} (type: {type(supplier_id).__name__})")
                print(f"  - supplier_name: {supplier_name}")
    else:
        print(f"\n❌ Error! Status: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("\n❌ Connection Error!")
    print("Make sure the server is running on http://localhost:8000")
    print("\nTo start the server, run:")
    print("  python start_backend.py")
    
except requests.exceptions.Timeout:
    print("\n⏱️ Request timed out!")
    print("The API might be taking longer than expected. Check the server logs.")
    
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("💡 TIP: Check the server terminal for detailed debug logs!")
print("   Look for lines starting with [DEBUG] to see supplier_id values")
print("=" * 80)
