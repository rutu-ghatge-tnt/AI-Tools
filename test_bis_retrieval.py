"""
Quick diagnostic script to test BIS cautions retrieval
Run this to verify BIS system is working correctly
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.ai_ingredient_intelligence.logic.bis_rag import (
    get_bis_retriever,
    get_bis_cautions_for_ingredients,
    initialize_bis_vectorstore,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)
import os


async def test_bis_retrieval():
    """Test BIS cautions retrieval with common ingredients"""
    print("=" * 80)
    print("BIS RETRIEVAL DIAGNOSTIC TEST")
    print("=" * 80)
    
    # Check PDF files
    print("\n1. Checking PDF files...")
    pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
    print(f"   Found {len(pdf_files)} PDF file(s):")
    for pdf in pdf_files:
        print(f"   - {pdf.name}")
    
    # Check vectorstore
    print("\n2. Checking vectorstore...")
    vectorstore_exists = os.path.exists(BIS_CHROMA_DB_PATH) and os.listdir(BIS_CHROMA_DB_PATH)
    print(f"   Vectorstore exists: {vectorstore_exists}")
    if vectorstore_exists:
        print(f"   Path: {BIS_CHROMA_DB_PATH}")
    
    # Initialize vectorstore
    print("\n3. Initializing vectorstore...")
    try:
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        if vectorstore is None:
            print("   ❌ ERROR: Vectorstore is None!")
            print("   This means the BIS system cannot retrieve cautions.")
            return False
        else:
            print("   ✅ Vectorstore initialized successfully")
    except Exception as e:
        print(f"   ❌ ERROR initializing vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test retriever
    print("\n4. Testing retriever...")
    try:
        retriever = get_bis_retriever()
        if retriever is None:
            print("   ❌ ERROR: Retriever is None!")
            return False
        else:
            print("   ✅ Retriever created successfully")
            
            # Test a simple query
            print("\n5. Testing simple query...")
            test_docs = retriever.invoke("salicylic acid")
            print(f"   Query 'salicylic acid' returned {len(test_docs)} document(s)")
            if test_docs:
                print(f"   Sample document preview: {test_docs[0].page_content[:150]}...")
    except Exception as e:
        print(f"   ❌ ERROR creating retriever: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test BIS cautions retrieval
    print("\n6. Testing BIS cautions retrieval...")
    test_ingredients = [
        "Salicylic Acid",
        "Benzyl Alcohol", 
        "Retinol",
        "Phenoxyethanol",
        "Hydroquinone"
    ]
    
    print(f"   Testing with {len(test_ingredients)} ingredients:")
    for ing in test_ingredients:
        print(f"   - {ing}")
    
    try:
        cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        
        print(f"\n   Results:")
        print(f"   - Ingredients with cautions: {len(cautions)}/{len(test_ingredients)}")
        
        if cautions:
            print("\n   ✅ SUCCESS! BIS cautions are being retrieved:")
            for ingredient, caution_list in cautions.items():
                print(f"\n   [{ingredient}] - {len(caution_list)} caution(s):")
                for i, caution in enumerate(caution_list[:3], 1):  # Show first 3
                    preview = caution[:120] + "..." if len(caution) > 120 else caution
                    print(f"      {i}. {preview}")
        else:
            print("\n   ⚠️ WARNING: No cautions retrieved for any ingredients!")
            print("   This could mean:")
            print("   - The ingredients don't have BIS restrictions")
            print("   - The ingredient names don't match what's in the PDFs")
            print("   - The retrieval logic needs adjustment")
        
        return len(cautions) > 0
        
    except Exception as e:
        print(f"   ❌ ERROR retrieving cautions: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n")
    success = asyncio.run(test_bis_retrieval())
    print("\n" + "=" * 80)
    if success:
        print("✅ DIAGNOSTIC PASSED: BIS system is working!")
    else:
        print("❌ DIAGNOSTIC FAILED: BIS system has issues - check errors above")
    print("=" * 80 + "\n")


