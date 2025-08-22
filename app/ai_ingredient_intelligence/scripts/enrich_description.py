# app/ai_ingredient_intelligence/scripts/enrich_description.py
"""Script to enrich ingredient descriptions using LLM"""

import os
import json
import random
import asyncio
import aiohttp
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm
from typing import Optional

# Load .env variables
load_dotenv()

# ✅ Read env vars correctly
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("DB_NAME", "ingredients_db")
CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY") or ""

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"   # ✅ fixed (URL not key)


# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_branded_ingredients"]


# ------------------ Claude Call ------------------ #
async def call_claude(session, ingredient_name: Optional[str], description: Optional[str] = None) -> dict:
    """
    Ask Claude to decide category & return rephrased/generated description in strict JSON.
    Retries up to 3 times with exponential backoff.
    """
    ingredient_name = ingredient_name or "Unknown Ingredient"
    description = description or "N/A"

    prompt = f"""
You are given a branded cosmetic ingredient.

Your tasks:
1. Decide whether it is an **Active** ingredient (functional, therapeutic, biologically active) 
   or an **Excipient** (carrier, filler, stabilizer, non-active).
2. If a description exists, rephrase it:
   - ~200 words if Active
   - ~50 words if Excipient
3. If description is missing, generate one from your knowledge:
   - ~200 words if Active
   - ~50 words if Excipient

Always respond strictly in JSON like this:
{{
  "category": "Active",
  "description": "...."
}}

Ingredient: {ingredient_name}
Description: {description}
"""

    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}]
    }

    for attempt in range(3):  # Retry with backoff
        try:
            # ✅ fixed: use CLAUDE_API_URL not CLAUDE_API_KEY
            async with session.post(CLAUDE_API_URL, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise Exception(f"Claude API error {resp.status}: {await resp.text()}")

                data = await resp.json()
                text = data["content"][0]["text"]

                # Expect strict JSON
                result = json.loads(text)
                return result

        except Exception as e:
            wait = 2 ** attempt + random.random()
            print(f"⚠️ Retry {attempt+1} for {ingredient_name}: {e}")
            await asyncio.sleep(wait)

    raise Exception(f"Claude failed for {ingredient_name} after retries")


# ------------------ Worker ------------------ #
async def process_ingredient(session, ingredient):
    name = ingredient.get("ingredient_name", "Unknown Ingredient")
    desc = ingredient.get("description")

    try:
        result = await call_claude(session, name, desc)
        await collection.update_one(
            {"_id": ingredient["_id"]},
            {"$set": {
                "category_decided": result["category"],
                "rephrased_description": result["description"]
            }}
        )
    except Exception as e:
        print(f"❌ {name} failed: {e}")


# ------------------ Main ------------------ #
async def main(batch_size=20):
    # Skip docs already processed
    query = {
        "$or": [
            {"rephrased_description": {"$exists": False}},
            {"rephrased_description": None},
            {"rephrased_description": ""}
        ]
    }
    total = await collection.count_documents(query)
    print(f"🔎 Processing {total} branded ingredients...\n")

    async with aiohttp.ClientSession() as session:
        cursor = collection.find(query)
        tasks = []

        pbar = tqdm(total=total, desc="Enriching", unit="ingredient")

        async for ingredient in cursor:
            tasks.append(process_ingredient(session, ingredient))

            if len(tasks) >= batch_size:
                await tqdm_asyncio.gather(*tasks)
                pbar.update(len(tasks))
                tasks.clear()

        if tasks:  # Remaining
            await tqdm_asyncio.gather(*tasks)
            pbar.update(len(tasks))

        pbar.close()
        print("✅ All ingredients processed.")


if __name__ == "__main__":
    asyncio.run(main())
