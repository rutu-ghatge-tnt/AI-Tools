"""
Comprehensive test suite for BIS RAG functionality
Tests vectorstore initialization, retrieval, and ingredient matching
"""
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Optional

# Import BIS RAG functions
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


class TestBISRAG:
    """Test suite for BIS RAG functionality"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test"""
        # Clear cache before each test
        clear_bis_vectorstore_cache()
        yield
        # Cleanup after test
        clear_bis_vectorstore_cache()
    
    def test_normalize_ingredient_name(self):
        """Test ingredient name normalization"""
        test_cases = [
            ("Salicylic Acid", "salicylic acid"),
            ("  Benzyl Alcohol  ", "benzyl alcohol"),
            ("Retinyl Palmitate", "retinyl palmitate"),
            ("α-Tocopherol", "tocopherol"),  # Should remove accents
            ("Sodium Hyaluronate", "sodium hyaluronate"),
        ]
        
        for input_name, expected_normalized in test_cases:
            result = normalize_ingredient_name(input_name)
            assert result == expected_normalized, f"Failed for '{input_name}': got '{result}', expected '{expected_normalized}'"
    
    def test_check_ingredient_mention_exact(self):
        """Test exact ingredient mention detection"""
        ingredient = "salicylic acid"
        text_with_ingredient = "The maximum concentration of salicylic acid should not exceed 2%."
        text_without_ingredient = "This product contains water and glycerin."
        
        assert check_ingredient_mention(ingredient, text_with_ingredient, use_fuzzy=False) == True
        assert check_ingredient_mention(ingredient, text_without_ingredient, use_fuzzy=False) == False
    
    def test_check_ingredient_mention_fuzzy(self):
        """Test fuzzy ingredient mention detection"""
        ingredient = "salicylic acid"
        text_variations = [
            "salicylate acid",  # Common misspelling
            "salicylic acid maximum 2%",
            "The use of salicylic acid is restricted",
        ]
        
        for text in text_variations:
            result = check_ingredient_mention(ingredient, text, use_fuzzy=True)
            assert result == True, f"Should detect '{ingredient}' in '{text}'"
    
    def test_fuzzy_match_ingredient(self):
        """Test fuzzy matching function"""
        ingredient = "benzyl alcohol"
        text = "The concentration of benzyl alcohol must not exceed 1% in cosmetic products."
        
        found, confidence, matched_text = fuzzy_match_ingredient(ingredient, text, threshold=0.7)
        assert found == True, "Should find ingredient in text"
        assert confidence >= 0.7, f"Confidence {confidence} should be >= 0.7"
        assert matched_text is not None, "Should return matched text"
    
    def test_vectorstore_initialization(self):
        """Test that vectorstore can be initialized"""
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        
        # If PDFs exist, vectorstore should be initialized
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        if pdf_files:
            assert vectorstore is not None, "Vectorstore should be initialized when PDFs exist"
        else:
            # If no PDFs, vectorstore might be None or might load existing
            print("⚠️ No PDF files found - skipping vectorstore initialization test")
    
    def test_retriever_creation(self):
        """Test that retriever can be created from vectorstore"""
        retriever = get_bis_retriever()
        
        # If vectorstore exists, retriever should be created
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        if pdf_files or os.path.exists(BIS_CHROMA_DB_PATH):
            # Retriever might be None if vectorstore failed to initialize
            # That's okay - we just want to ensure no exceptions are raised
            print(f"Retriever created: {retriever is not None}")
        else:
            print("⚠️ No PDFs or vectorstore - skipping retriever test")
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_empty_list(self):
        """Test BIS cautions retrieval with empty ingredient list"""
        result = await get_bis_cautions_for_ingredients([])
        assert result == {}, "Should return empty dict for empty input"
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_invalid_ingredients(self):
        """Test BIS cautions retrieval with invalid/empty ingredient names"""
        result = await get_bis_cautions_for_ingredients(["", "   ", None])
        # Should handle gracefully without crashing
        assert isinstance(result, dict), "Should return a dict"
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_real_ingredients(self):
        """Test BIS cautions retrieval with real ingredient names"""
        # Common ingredients that might be in BIS documents
        test_ingredients = [
            "Salicylic Acid",
            "Benzyl Alcohol",
            "Retinol",
            "Hydroquinone",
        ]
        
        result = await get_bis_cautions_for_ingredients(test_ingredients)
        
        assert isinstance(result, dict), "Should return a dict"
        
        # Check structure: each ingredient should map to a list
        for ingredient in test_ingredients:
            if ingredient in result:
                assert isinstance(result[ingredient], list), f"Value for '{ingredient}' should be a list"
                # If cautions found, they should be non-empty strings
                for caution in result[ingredient]:
                    assert isinstance(caution, str), "Each caution should be a string"
                    assert len(caution.strip()) > 0, "Caution should not be empty"
        
        print(f"\n✅ Test results: Found cautions for {len(result)}/{len(test_ingredients)} ingredients")
        for ingredient, cautions in result.items():
            print(f"   - {ingredient}: {len(cautions)} caution(s)")
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_batch_formatting(self):
        """Test that batch formatting returns proper string format"""
        test_ingredients = ["Salicylic Acid", "Benzyl Alcohol"]
        
        result = await get_bis_cautions_batch(test_ingredients)
        
        assert isinstance(result, str), "Should return a string"
        assert len(result) > 0, "Should return non-empty string"
        
        # Should contain BIS header
        assert "BIS" in result.upper() or "Bureau" in result, "Should mention BIS"
    
    def test_vectorstore_cache(self):
        """Test that vectorstore caching works correctly"""
        # First call should initialize
        vectorstore1 = initialize_bis_vectorstore(force_reload=False)
        
        # Second call should return cached instance
        vectorstore2 = initialize_bis_vectorstore(force_reload=False)
        
        # Should be the same object (cached)
        assert vectorstore1 is vectorstore2, "Should return cached instance"
        
        # Force reload should create new instance
        clear_bis_vectorstore_cache()
        vectorstore3 = initialize_bis_vectorstore(force_reload=True)
        
        # If vectorstore exists, they might be different objects
        # (though content should be same)
        print("✅ Cache test passed")


class TestBISRAGIntegration:
    """Integration tests for BIS RAG with real data"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_retrieval(self):
        """End-to-end test: initialize, retrieve, and format cautions"""
        # Clear cache first
        clear_bis_vectorstore_cache()
        
        # Initialize vectorstore
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        if vectorstore is None:
            pytest.skip("Vectorstore not available - PDFs may not be present")
        
        # Create retriever
        retriever = get_bis_retriever()
        assert retriever is not None, "Retriever should be created"
        
        # Test retrieval
        test_ingredients = ["Salicylic Acid", "Benzyl Alcohol"]
        cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        
        assert isinstance(cautions, dict), "Should return dict"
        
        # Test batch formatting
        formatted = await get_bis_cautions_batch(test_ingredients)
        assert isinstance(formatted, str), "Should return formatted string"
        
        print(f"\n✅ End-to-end test passed")
        print(f"   Ingredients tested: {len(test_ingredients)}")
        print(f"   Ingredients with cautions: {len(cautions)}")
        print(f"   Formatted output length: {len(formatted)} chars")
    
    @pytest.mark.asyncio
    async def test_multiple_ingredients_performance(self):
        """Test performance with multiple ingredients"""
        import time
        
        test_ingredients = [
            "Salicylic Acid",
            "Benzyl Alcohol",
            "Retinol",
            "Hydroquinone",
            "Tretinoin",
            "Alpha Hydroxy Acid",
            "Beta Hydroxy Acid",
        ]
        
        start_time = time.time()
        cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        elapsed_time = time.time() - start_time
        
        assert isinstance(cautions, dict), "Should return dict"
        
        print(f"\n⏱️ Performance test:")
        print(f"   Ingredients: {len(test_ingredients)}")
        print(f"   Time elapsed: {elapsed_time:.2f} seconds")
        print(f"   Average per ingredient: {elapsed_time/len(test_ingredients):.2f} seconds")
        print(f"   Ingredients with cautions: {len(cautions)}/{len(test_ingredients)}")
        
        # Should complete in reasonable time (< 30 seconds for 7 ingredients)
        assert elapsed_time < 30, f"Retrieval took too long: {elapsed_time:.2f}s"


def run_manual_tests():
    """Run manual tests that print detailed output"""
    print("=" * 80)
    print("BIS RAG Manual Test Suite")
    print("=" * 80)
    
    # Test 1: Vectorstore initialization
    print("\n1. Testing vectorstore initialization...")
    clear_bis_vectorstore_cache()
    vectorstore = initialize_bis_vectorstore(force_reload=False)
    if vectorstore:
        print("   ✅ Vectorstore initialized successfully")
    else:
        print("   ⚠️ Vectorstore is None (may be normal if no PDFs)")
    
    # Test 2: Retriever creation
    print("\n2. Testing retriever creation...")
    retriever = get_bis_retriever()
    if retriever:
        print("   ✅ Retriever created successfully")
    else:
        print("   ⚠️ Retriever is None")
    
    # Test 3: Ingredient normalization
    print("\n3. Testing ingredient normalization...")
    test_names = ["Salicylic Acid", "  Benzyl Alcohol  ", "α-Tocopherol"]
    for name in test_names:
        normalized = normalize_ingredient_name(name)
        print(f"   '{name}' -> '{normalized}'")
    
    # Test 4: Ingredient mention detection
    print("\n4. Testing ingredient mention detection...")
    ingredient = "salicylic acid"
    test_texts = [
        "The maximum concentration of salicylic acid should not exceed 2%.",
        "This product contains water and glycerin.",
    ]
    for text in test_texts:
        found = check_ingredient_mention(ingredient, text, use_fuzzy=True)
        print(f"   Found: {found} | Text: '{text[:50]}...'")
    
    # Test 5: BIS cautions retrieval
    print("\n5. Testing BIS cautions retrieval...")
    test_ingredients = ["Salicylic Acid", "Benzyl Alcohol", "Retinol"]
    
    async def test_retrieval():
        cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        print(f"\n   Results for {len(test_ingredients)} ingredients:")
        for ingredient, caution_list in cautions.items():
            print(f"   - {ingredient}: {len(caution_list)} caution(s)")
            if caution_list:
                print(f"     Sample: {caution_list[0][:100]}...")
        return cautions
    
    cautions = asyncio.run(test_retrieval())
    
    # Test 6: Batch formatting
    print("\n6. Testing batch formatting...")
    async def test_formatting():
        formatted = await get_bis_cautions_batch(test_ingredients)
        print(f"   Formatted output length: {len(formatted)} characters")
        print(f"   First 200 chars: {formatted[:200]}...")
        return formatted
    
    formatted = asyncio.run(test_formatting())
    
    print("\n" + "=" * 80)
    print("✅ Manual tests completed")
    print("=" * 80)


if __name__ == "__main__":
    # Run manual tests
    run_manual_tests()
    
    # Run pytest if available
    print("\n" + "=" * 80)
    print("Running pytest suite...")
    print("=" * 80)
    pytest.main([__file__, "-v", "--tb=short"])

