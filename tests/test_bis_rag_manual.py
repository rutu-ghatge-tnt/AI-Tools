"""
Manual test runner for BIS RAG functionality
Can be run without pytest to verify BIS RAG is working
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
    check_bis_rag_health,
    normalize_ingredient_name,
    check_ingredient_mention,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)


def test_health_check():
    """Test health check"""
    print("\n" + "=" * 80)
    print("TEST 1: Health Check")
    print("=" * 80)
    
    health = check_bis_rag_health()
    
    print(f"Status: {health['status']}")
    print(f"PDF Files Found: {health['pdf_files_found']}")
    print(f"Vectorstore Initialized: {health['vectorstore_initialized']}")
    print(f"Retriever Created: {health['retriever_created']}")
    
    if health.get('errors'):
        print(f"\nErrors:")
        for error in health['errors']:
            print(f"  - {error}")
    
    if health['status'] == 'healthy':
        print("\n✅ Health check PASSED")
        return True
    else:
        print(f"\n⚠️ Health check shows status: {health['status']}")
        return False


def test_normalization():
    """Test ingredient name normalization"""
    print("\n" + "=" * 80)
    print("TEST 2: Ingredient Name Normalization")
    print("=" * 80)
    
    test_cases = [
        ("Salicylic Acid", "salicylic acid"),
        ("  Benzyl Alcohol  ", "benzyl alcohol"),
        ("α-Tocopherol", "tocopherol"),
    ]
    
    all_passed = True
    for input_name, expected in test_cases:
        result = normalize_ingredient_name(input_name)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"{status} '{input_name}' -> '{result}' (expected: '{expected}')")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✅ Normalization tests PASSED")
    else:
        print("\n❌ Some normalization tests FAILED")
    
    return all_passed


def test_ingredient_mention():
    """Test ingredient mention detection"""
    print("\n" + "=" * 80)
    print("TEST 3: Ingredient Mention Detection")
    print("=" * 80)
    
    ingredient = "salicylic acid"
    text_with = "The maximum concentration of salicylic acid should not exceed 2%."
    text_without = "This product contains water and glycerin."
    
    found_with = check_ingredient_mention(ingredient, text_with, use_fuzzy=False)
    found_without = check_ingredient_mention(ingredient, text_without, use_fuzzy=False)
    
    print(f"Text with ingredient: {found_with} (expected: True)")
    print(f"Text without ingredient: {found_without} (expected: False)")
    
    if found_with and not found_without:
        print("\n✅ Mention detection tests PASSED")
        return True
    else:
        print("\n❌ Mention detection tests FAILED")
        return False


async def test_vectorstore_initialization():
    """Test vectorstore initialization"""
    print("\n" + "=" * 80)
    print("TEST 4: Vectorstore Initialization")
    print("=" * 80)
    
    try:
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        if vectorstore is not None:
            print("✅ Vectorstore initialized successfully")
            return True
        else:
            print("⚠️ Vectorstore is None (may be normal if no PDFs)")
            return False
    except Exception as e:
        print(f"❌ Vectorstore initialization failed: {e}")
        return False


async def test_retriever_creation():
    """Test retriever creation"""
    print("\n" + "=" * 80)
    print("TEST 5: Retriever Creation")
    print("=" * 80)
    
    try:
        retriever = get_bis_retriever()
        if retriever is not None:
            print("✅ Retriever created successfully")
            
            # Test a simple query
            try:
                docs = retriever.invoke("test")
                print(f"✅ Test query executed successfully (returned {len(docs) if docs else 0} docs)")
                return True
            except Exception as e:
                print(f"⚠️ Test query failed: {e}")
                return False
        else:
            print("❌ Retriever is None")
            return False
    except Exception as e:
        print(f"❌ Retriever creation failed: {e}")
        return False


async def test_bis_cautions_retrieval():
    """Test BIS cautions retrieval"""
    print("\n" + "=" * 80)
    print("TEST 6: BIS Cautions Retrieval")
    print("=" * 80)
    
    test_ingredients = ["Salicylic Acid", "Benzyl Alcohol"]
    
    try:
        print(f"Testing with ingredients: {', '.join(test_ingredients)}")
        result = await get_bis_cautions_for_ingredients(test_ingredients)
        
        if isinstance(result, dict):
            print(f"✅ Retrieved cautions for {len(result)}/{len(test_ingredients)} ingredients")
            
            for ingredient, cautions in result.items():
                print(f"  - {ingredient}: {len(cautions)} caution(s)")
                if cautions:
                    print(f"    Sample: {cautions[0][:100]}...")
            
            # Test batch formatting
            formatted = await get_bis_cautions_batch(test_ingredients)
            print(f"\n✅ Batch formatting successful ({len(formatted)} characters)")
            
            return True
        else:
            print(f"❌ Unexpected result type: {type(result)}")
            return False
    except Exception as e:
        print(f"❌ Retrieval failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("=" * 80)
    print("BIS RAG Manual Test Suite")
    print("=" * 80)
    
    results = {}
    
    # Run synchronous tests
    results['health_check'] = test_health_check()
    results['normalization'] = test_normalization()
    results['ingredient_mention'] = test_ingredient_mention()
    
    # Run asynchronous tests
    results['vectorstore'] = await test_vectorstore_initialization()
    results['retriever'] = await test_retriever_creation()
    results['cautions_retrieval'] = await test_bis_cautions_retrieval()
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:30} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests PASSED!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)

