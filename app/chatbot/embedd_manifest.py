# app/chatbot/embedd_manifest.py
import json
from pathlib import Path

MANIFEST_PATH = Path("chroma_db/embed_manifest.json")

def load_manifest() -> set:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r") as f:
            return set(json.load(f))
    return set()

def save_manifest(embedded_files: set):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(sorted(list(embedded_files)), f, indent=2)
