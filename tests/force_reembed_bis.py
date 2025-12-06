"""
Force re-embedding of BIS PDFs
"""
import sys
from pathlib import Path
import os
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai_ingredient_intelligence.logic.bis_rag import (
    clear_bis_vectorstore_cache,
    initialize_bis_vectorstore,
    BIS_CHROMA_DB_PATH,
    BIS_MANIFEST_PATH
)

def force_reembed():
    """Force re-embedding of all PDFs"""
    print("=" * 80)
    print("Force Re-embedding BIS PDFs")
    print("=" * 80)
    
    # Clear cache
    print("\n1. Clearing cache...")
    clear_bis_vectorstore_cache()
    
    # Delete manifest to force re-processing
    print("\n2. Deleting manifest...")
    if BIS_MANIFEST_PATH.exists():
        BIS_MANIFEST_PATH.unlink()
        print(f"   Deleted: {BIS_MANIFEST_PATH}")
    else:
        print("   Manifest doesn't exist")
    
    # Delete vectorstore directory
    print("\n3. Deleting vectorstore...")
    if os.path.exists(BIS_CHROMA_DB_PATH):
        try:
            shutil.rmtree(BIS_CHROMA_DB_PATH)
            print(f"   Deleted: {BIS_CHROMA_DB_PATH}")
        except Exception as e:
            print(f"   Error deleting vectorstore: {e}")
    else:
        print("   Vectorstore doesn't exist")
    
    # Force re-initialization
    print("\n4. Re-initializing vectorstore (this will take a while)...")
    try:
        vectorstore = initialize_bis_vectorstore(force_reload=True)
        if vectorstore:
            # Check document count
            try:
                count = vectorstore._collection.count()
                print(f"\n[OK] Vectorstore initialized with {count} document chunks")
                return True
            except Exception as e:
                print(f"\n[WARNING] Could not get document count: {e}")
                return True
        else:
            print("\n[ERROR] Vectorstore initialization failed")
            return False
    except Exception as e:
        print(f"\n[ERROR] Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = force_reembed()
    sys.exit(0 if success else 1)

