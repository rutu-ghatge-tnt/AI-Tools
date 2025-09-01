# app/view_existing_report.py
"""Script to view the existing formulation report without generating a new one"""

import requests
import json
import webbrowser
import tempfile
import os

def view_existing_report():
    base_url = "http://127.0.0.1:8000"
    
    try:
        # Check if there's a report available
        print("🔍 Checking for existing reports...")
        status_response = requests.get(f"{base_url}/api/formulation-report/status")
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data["has_report"]:
                print(f"✅ Found existing report: {status_data['report_length']} characters")
                
                # Get the existing report by making a simple GET request
                print("\n📄 Fetching existing report...")
                
                # We need to make a POST request to get the HTML, but with minimal data
                # Let's use the same test data that was already used
                test_inci_list = [
                    "Aqua", "Glycerin", "Niacinamide", 
                    "Hyaluronic Acid", "Salicylic Acid", "Benzoyl Peroxide"
                ]
                
                payload = {"inciList": test_inci_list}
                response = requests.post(
                    f"{base_url}/api/formulation-report",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    print("✅ Report fetched successfully!")
                    
                    # Save HTML to a temporary file and open in browser
                    html_content = response.text
                    
                    # Create a temporary HTML file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                        f.write(html_content)
                        temp_file = f.name
                    
                    print(f"📄 Opening report in browser...")
                    print(f"📁 Temporary file: {temp_file}")
                    
                    # Open in default browser
                    webbrowser.open(f'file://{temp_file}')
                    
                    print("\n💡 The existing report has been opened in your browser!")
                    print("   - This shows the report with REAL OpenAI-generated notes")
                    print("   - You can save it as an HTML file")
                    print("   - Print it to PDF using browser print function")
                    
                else:
                    print(f"❌ Failed to fetch report: {response.status_code}")
                    print(f"Error: {response.text}")
            else:
                print("❌ No existing report available. Generate one first using the test script.")
                
        else:
            print(f"❌ Status check failed: {status_response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure the FastAPI server is running on localhost:8000")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    view_existing_report()
