# app/test_formulation_api.py
"""Test script for the Formulation Report API"""

import requests
import json

# Test the formulation report API
def test_formulation_report():
    base_url = "http://localhost:8000"
    
    # Test data
    test_inci_list = [
        "Aqua",
        "Glycerin", 
        "Niacinamide",
        "Hyaluronic Acid",
        "Salicylic Acid",
        "Benzoyl Peroxide"
    ]
    
    payload = {
        "inciList": test_inci_list
    }
    
    try:
        # First test the status endpoint to verify API is working
        print("🧪 Testing GET /api/formulation-report/status...")
        status_response = requests.get(f"{base_url}/api/formulation-report/status")
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            print("✅ Status endpoint working!")
            print(f"📊 Status: {json.dumps(status_data, indent=2)}")
        else:
            print(f"❌ Status endpoint failed: {status_response.status_code}")
            return
            
        # Test POST /api/formulation-report
        print("\n🧪 Testing POST /api/formulation-report...")
        response = requests.post(
            f"{base_url}/api/formulation-report",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            print("✅ Formulation report generated successfully!")
            print(f"📄 Response length: {len(response.text)} characters")
            
            # Test status again to see if report was stored
            print("\n🧪 Testing status after report generation...")
            status_response = requests.get(f"{base_url}/api/formulation-report/status")
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print("✅ Status endpoint working!")
                print(f"📊 Status: {json.dumps(status_data, indent=2)}")
            else:
                print(f"❌ Status endpoint failed: {status_response.status_code}")
                
        else:
            print(f"❌ Formulation report failed: {response.status_code}")
            print(f"Error: {response.text}")
            
            # If OpenAI API fails, suggest checking the API key
            if "PermissionDeniedError" in response.text or "model_not_found" in response.text:
                print("\n💡 OpenAI API Issue Detected:")
                print("   - Check if OPENAI_API_KEY environment variable is set")
                print("   - Verify your OpenAI API key is valid and has credits")
                print("   - Make sure you have access to GPT models")
                print("   - You can set the API key with: $env:OPENAI_API_KEY='your-key-here'")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure the FastAPI server is running on localhost:8000")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")

if __name__ == "__main__":
    test_formulation_report()
