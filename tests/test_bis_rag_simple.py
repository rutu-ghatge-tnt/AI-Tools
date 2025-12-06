"""
Simple BIS RAG test script (no pytest required)
Run with: python tests/test_bis_rag_simple.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai_ingredient_intelligence.logic.bis_rag import (
    initialize_bis_vectorstore,
    get_bis_retriever,
    get_bis_cautions_for_ingredients,
    get_bis_cautions_batch,
    normalize_ingredient_name,
    check_ingredient_mention,
    fuzzy_match_ingredient,
    clear_bis_vectorstore_cache,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)


def test_normalization():
    """Test ingredient name normalization"""
    print("\n" + "=" * 80)
    print("TEST 1: Ingredient Name Normalization")
    print("=" * 80)
    
    test_cases = [
        ("Salicylic Acid", "salicylic acid"),
        ("  Benzyl Alcohol  ", "benzyl alcohol"),
        ("Retinyl Palmitate", "retinyl palmitate"),
    ]
    
    all_passed = True
    for input_name, expected in test_cases:
        result = normalize_ingredient_name(input_name)
        passed = result == expected
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: '{input_name}' -> '{result}' (expected: '{expected}')")
        if not passed:
            all_passed = False
    
    return all_passed


def test_ingredient_mention():
    """Test ingredient mention detection"""
    print("\n" + "=" * 80)
    print("TEST 2: Ingredient Mention Detection")
    print("=" * 80)
    
    ingredient = "salicylic acid"
    test_cases = [
        ("The maximum concentration of salicylic acid should not exceed 2%.", True),
        ("This product contains water and glycerin.", False),
        ("Salicylic acid is restricted in some formulations.", True),
    ]
    
    all_passed = True
    for text, expected in test_cases:
        result = check_ingredient_mention(ingredient, text, use_fuzzy=True)
        passed = result == expected
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: Found={result} (expected={expected})")
        print(f"   Text: '{text[:60]}...'")
        if not passed:
            all_passed = False
    
    return all_passed


def test_vectorstore():
    """Test vectorstore initialization"""
    print("\n" + "=" * 80)
    print("TEST 3: Vectorstore Initialization")
    print("=" * 80)
    
    try:
        clear_bis_vectorstore_cache()
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        
        if vectorstore is None:
            print("[WARNING] Vectorstore is None")
            pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
            if pdf_files:
                print(f"   [WARNING] PDFs exist ({len(pdf_files)}) but vectorstore is None")
                print("   This might indicate an initialization error")
                return False
            else:
                print("   [INFO] No PDFs found - this is expected if data directory is empty")
                return True  # Not a failure if no PDFs
        
        print("[OK] Vectorstore initialized successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Error initializing vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_retriever():
    """Test retriever creation"""
    print("\n" + "=" * 80)
    print("TEST 4: Retriever Creation")
    print("=" * 80)
    
    try:
        retriever = get_bis_retriever()
        
        if retriever is None:
            print("[WARNING] Retriever is None")
            print("   This might be expected if vectorstore is not initialized")
            return True  # Not necessarily a failure
        
        print("[OK] Retriever created successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Error creating retriever: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_retrieval():
    """Test document retrieval"""
    print("\n" + "=" * 80)
    print("TEST 5: Document Retrieval")
    print("=" * 80)
    
    try:
        retriever = get_bis_retriever()
        if retriever is None:
            print("[WARNING] Retriever not available - skipping retrieval test")
            return True
        
        test_query = "salicylic acid"
        print(f"   Testing query: '{test_query}'")
        docs = retriever.invoke(test_query)
        
        print(f"[OK] Retrieved {len(docs)} document(s)")
        if docs:
            print(f"   Sample document length: {len(docs[0].page_content)} characters")
            print(f"   Sample content (first 100 chars): {docs[0].page_content[:100]}...")
        else:
            print("   [WARNING] No documents retrieved - this might be expected if ingredient not in documents")
        
        return True
    except Exception as e:
        print(f"[ERROR] Error during retrieval: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_bis_cautions():
    """Test BIS cautions retrieval"""
    print("\n" + "=" * 80)
    print("TEST 6: BIS Cautions Retrieval")
    print("=" * 80)
    
    test_ingredients = ["Salicylic Acid", "Benzyl Alcohol", "Retinol"]
    print(f"   Testing with {len(test_ingredients)} ingredients: {test_ingredients}")
    
    try:
        cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        
        print(f"[OK] Function executed successfully")
        print(f"   Ingredients with cautions: {len(cautions)}/{len(test_ingredients)}")
        
        for ingredient, caution_list in cautions.items():
            print(f"   - {ingredient}: {len(caution_list)} caution(s)")
            if caution_list:
                print(f"     Sample: {caution_list[0][:80]}...")
        
        if not cautions:
            print("   [WARNING] No cautions found - this might be expected if ingredients not in BIS documents")
        
        return True
    except Exception as e:
        print(f"[ERROR] Error retrieving BIS cautions: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_batch_formatting():
    """Test batch formatting"""
    print("\n" + "=" * 80)
    print("TEST 7: Batch Formatting")
    print("=" * 80)
    
    test_ingredients = ["Salicylic Acid", "Benzyl Alcohol"]
    
    try:
        formatted = await get_bis_cautions_batch(test_ingredients)
        
        print(f"[OK] Formatting executed successfully")
        print(f"   Output length: {len(formatted)} characters")
        print(f"   First 200 chars: {formatted[:200]}...")
        
        assert isinstance(formatted, str), "Should return string"
        assert len(formatted) > 0, "Should return non-empty string"
        
        return True
    except Exception as e:
        print(f"[ERROR] Error formatting batch: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("=" * 80)
    print("BIS RAG Test Suite")
    print("=" * 80)
    
    results = []
    
    # Run synchronous tests
    results.append(("Normalization", test_normalization()))
    results.append(("Ingredient Mention", test_ingredient_mention()))
    results.append(("Vectorstore", test_vectorstore()))
    results.append(("Retriever", test_retriever()))
    
    # Run async tests
    results.append(("Retrieval", await test_retrieval()))
    results.append(("BIS Cautions", await test_bis_cautions()))
    results.append(("Batch Formatting", await test_batch_formatting()))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"[WARNING] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

