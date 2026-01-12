#!/usr/bin/env python3
"""
Export OpenAPI schema from FastAPI app to JSON file.
This can be imported into Postman.
"""
import json
from app.main import app

# Generate OpenAPI schema
openapi_schema = app.openapi()

# Write to file
with open('openapi.json', 'w', encoding='utf-8') as f:
    json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

print("✅ OpenAPI schema exported to 'openapi.json'")
print("📥 You can now import this file into Postman:")
print("   1. Open Postman")
print("   2. Click 'Import' (top left)")
print("   3. Drag and drop 'openapi.json' or click 'Upload Files'")
print("   4. Click 'Import'")





