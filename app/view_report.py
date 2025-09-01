# app/view_report.py
"""Script to view the generated formulation report"""

import requests
import json
import webbrowser
import tempfile
import os

def view_formulation_report():
    base_url = "http://127.0.0.1:8000"
    
    try:
        # First check if there's a report available
        print("🔍 Checking for available reports...")
        status_response = requests.get(f"{base_url}/api/formulation-report/status")
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data["has_report"]:
                print(f"✅ Found report: {status_data['report_length']} characters")
                
                # Generate a new report to see the full HTML
                print("\n🧪 Generating a sample report...")
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
                    print("✅ Report generated successfully!")
                    
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
                    
                    print("\n💡 The report has been opened in your browser!")
                    print("   - You can save it as an HTML file")
                    print("   - Print it to PDF using browser print function")
                    print("   - The temporary file will be cleaned up automatically")
                    
                else:
                    print(f"❌ Failed to generate report: {response.status_code}")
                    print(f"Error: {response.text}")
            else:
                print("❌ No report available. Generate one first using the test script.")
                
        else:
            print(f"❌ Status check failed: {status_response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure the FastAPI server is running on localhost:8000")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    view_formulation_report()
