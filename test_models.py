import os
import requests
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY is missing. Please set it in your .env file.")
    exit(1)

# Test different models
models_to_test = [
    "gpt-5",
    "gpt-4",
    "gpt-4o",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k"
]

print("🔍 Testing model access...")
print("=" * 50)

for model in models_to_test:
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hi"}]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ {model}: ACCESSIBLE")
        elif response.status_code == 403:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", "Unknown error")
            print(f"❌ {model}: ACCESS DENIED - {error_msg}")
        elif response.status_code == 429:
            print(f"⚠️ {model}: RATE LIMITED")
        else:
            print(f"❓ {model}: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ {model}: ERROR - {e}")

print("=" * 50)
print("💡 Models marked 'ACCESSIBLE' can be used in your script")
print("💡 Models marked 'ACCESS DENIED' need to be enabled in your project")

