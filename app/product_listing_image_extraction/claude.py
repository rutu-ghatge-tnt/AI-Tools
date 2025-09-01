#claude.py
import os
import httpx
import re
import json
from app.product_listing_image_extraction.prompt_template import build_prompt  # ✅ Import shared prompt

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-3-opus-20240229"  # Recommended model version

async def extract_structured_info(ocr_text: str) -> dict:
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": build_prompt(ocr_text)
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(CLAUDE_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.ReadTimeout:
        return {"error": "Claude API timed out. Try again later."}
    except httpx.RequestError as e:
        return {"error": f"Claude API request failed: {str(e)}"}

    try:
        raw_text = data["content"][0]["text"]
    except Exception:
        return {"error": "Claude response parsing failed", "raw": str(data)}

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON", "raw": raw_text}

    return {"error": "No JSON found in Claude response", "raw": raw_text}
