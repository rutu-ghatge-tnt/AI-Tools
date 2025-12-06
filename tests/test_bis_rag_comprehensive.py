"""
Comprehensive test suite for BIS RAG functionality
Tests all aspects including initialization, retrieval, error handling, and health checks
"""
import pytest
import asyncio
import os
import time
from pathlib import Path
from typing import List, Dict

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
    check_bis_rag_health,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)


class TestBISRAGHealth:
    """Test health check functionality"""
    
    def test_health_check_basic(self):
        """Test basic health check"""
        health = check_bis_rag_health()
        
        assert isinstance(health, dict), "Health check should return a dict"
        assert "status" in health, "Health check should include status"
        assert "vectorstore_initialized" in health, "Health check should include vectorstore status"
        assert "retriever_created" in health, "Health check should include retriever status"
        assert "pdf_files_found" in health, "Health check should include PDF count"
        
        print(f"\n✅ Health Check Results:")
        print(f"   Status: {health['status']}")
        print(f"   PDF Files: {health['pdf_files_found']}")
        print(f"   Vectorstore: {health['vectorstore_initialized']}")
        print(f"   Retriever: {health['retriever_created']}")
        if health.get('errors'):
            print(f"   Errors: {health['errors']}")


class TestBISRAGInitialization:
    """Test vectorstore and retriever initialization"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test"""
        clear_bis_vectorstore_cache()
        yield
        clear_bis_vectorstore_cache()
    
    def test_vectorstore_initialization(self):
        """Test vectorstore initialization"""
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        if pdf_files:
            assert vectorstore is not None, "Vectorstore should be initialized when PDFs exist"
            print(f"✅ Vectorstore initialized with {len(pdf_files)} PDF(s)")
        else:
            print("⚠️ No PDF files found - vectorstore may be None")
    
    def test_retriever_creation(self):
        """Test retriever creation"""
        retriever = get_bis_retriever()
        
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        if pdf_files or os.path.exists(BIS_CHROMA_DB_PATH):
            if retriever is not None:
                print("✅ Retriever created successfully")
            else:
                print("⚠️ Retriever is None (may indicate initialization issue)")
        else:
            print("⚠️ No PDFs or vectorstore - skipping retriever test")
    
    def test_retriever_query(self):
        """Test that retriever can execute queries"""
        retriever = get_bis_retriever()
        
        if retriever is None:
            pytest.skip("Retriever not available")
        
        try:
            # Test with a simple query
            docs = retriever.invoke("test")
            assert isinstance(docs, list), "Retriever should return a list"
            print(f"✅ Retriever query test passed (returned {len(docs)} docs)")
        except Exception as e:
            pytest.fail(f"Retriever query failed: {e}")


class TestBISRAGIngredientMatching:
    """Test ingredient matching and normalization"""
    
    def test_normalize_ingredient_name(self):
        """Test ingredient name normalization"""
        test_cases = [
            ("Salicylic Acid", "salicylic acid"),
            ("  Benzyl Alcohol  ", "benzyl alcohol"),
            ("Retinyl Palmitate", "retinyl palmitate"),
            ("α-Tocopherol", "tocopherol"),  # Should remove accents
            ("Sodium Hyaluronate", "sodium hyaluronate"),
            ("Hydroquinone", "hydroquinone"),
        ]
        
        for input_name, expected_normalized in test_cases:
            result = normalize_ingredient_name(input_name)
            assert result == expected_normalized, \
                f"Failed for '{input_name}': got '{result}', expected '{expected_normalized}'"
        
        print("✅ All normalization tests passed")
    
    def test_check_ingredient_mention_exact(self):
        """Test exact ingredient mention detection"""
        ingredient = "salicylic acid"
        text_with = "The maximum concentration of salicylic acid should not exceed 2%."
        text_without = "This product contains water and glycerin."
        
        assert check_ingredient_mention(ingredient, text_with, use_fuzzy=False) == True
        assert check_ingredient_mention(ingredient, text_without, use_fuzzy=False) == False
        print("✅ Exact mention detection tests passed")
    
    def test_check_ingredient_mention_fuzzy(self):
        """Test fuzzy ingredient mention detection"""
        ingredient = "salicylic acid"
        text_variations = [
            "salicylic acid maximum 2%",
            "The use of salicylic acid is restricted",
            "salicylate acid",  # Common variation
        ]
        
        for text in text_variations:
            result = check_ingredient_mention(ingredient, text, use_fuzzy=True)
            assert result == True, f"Should detect '{ingredient}' in '{text}'"
        
        print("✅ Fuzzy mention detection tests passed")
    
    def test_fuzzy_match_ingredient(self):
        """Test fuzzy matching function"""
        ingredient = "benzyl alcohol"
        text = "The concentration of benzyl alcohol must not exceed 1% in cosmetic products."
        
        found, confidence, matched_text = fuzzy_match_ingredient(ingredient, text, threshold=0.7)
        assert found == True, "Should find ingredient in text"
        assert confidence >= 0.7, f"Confidence {confidence} should be >= 0.7"
        assert matched_text is not None, "Should return matched text"
        print(f"✅ Fuzzy match test passed (confidence: {confidence:.2f})")


class TestBISRAGRetrieval:
    """Test BIS cautions retrieval"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test"""
        clear_bis_vectorstore_cache()
        yield
        clear_bis_vectorstore_cache()
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_empty_list(self):
        """Test BIS cautions retrieval with empty ingredient list"""
        result = await get_bis_cautions_for_ingredients([])
        assert result == {}, "Should return empty dict for empty input"
        print("✅ Empty list test passed")
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_invalid_ingredients(self):
        """Test BIS cautions retrieval with invalid/empty ingredient names"""
        result = await get_bis_cautions_for_ingredients(["", "   ", None])
        assert isinstance(result, dict), "Should return a dict"
        print("✅ Invalid ingredients test passed")
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_single_ingredient(self):
        """Test BIS cautions retrieval with a single ingredient"""
        test_ingredients = ["Salicylic Acid"]
        
        result = await get_bis_cautions_for_ingredients(test_ingredients)
        
        assert isinstance(result, dict), "Should return a dict"
        
        # Check structure
        for ingredient in test_ingredients:
            if ingredient in result:
                assert isinstance(result[ingredient], list), \
                    f"Value for '{ingredient}' should be a list"
                for caution in result[ingredient]:
                    assert isinstance(caution, str), "Each caution should be a string"
                    assert len(caution.strip()) > 0, "Caution should not be empty"
        
        print(f"✅ Single ingredient test passed")
        print(f"   Found cautions for {len(result)}/{len(test_ingredients)} ingredient(s)")
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_multiple_ingredients(self):
        """Test BIS cautions retrieval with multiple ingredients"""
        test_ingredients = [
            "Salicylic Acid",
            "Benzyl Alcohol",
            "Retinol",
            "Hydroquinone",
        ]
        
        start_time = time.time()
        result = await get_bis_cautions_for_ingredients(test_ingredients)
        elapsed_time = time.time() - start_time
        
        assert isinstance(result, dict), "Should return a dict"
        
        # Validate structure
        for ingredient in test_ingredients:
            if ingredient in result:
                assert isinstance(result[ingredient], list), \
                    f"Value for '{ingredient}' should be a list"
                for caution in result[ingredient]:
                    assert isinstance(caution, str), "Each caution should be a string"
                    assert len(caution.strip()) > 0, "Caution should not be empty"
        
        print(f"\n✅ Multiple ingredients test passed")
        print(f"   Ingredients tested: {len(test_ingredients)}")
        print(f"   Ingredients with cautions: {len(result)}")
        print(f"   Time elapsed: {elapsed_time:.2f} seconds")
        print(f"   Average per ingredient: {elapsed_time/len(test_ingredients):.2f} seconds")
        
        # Should complete in reasonable time
        assert elapsed_time < 60, f"Retrieval took too long: {elapsed_time:.2f}s"
    
    @pytest.mark.asyncio
    async def test_get_bis_cautions_batch_formatting(self):
        """Test that batch formatting returns proper string format"""
        test_ingredients = ["Salicylic Acid", "Benzyl Alcohol"]
        
        result = await get_bis_cautions_batch(test_ingredients)
        
        assert isinstance(result, str), "Should return a string"
        assert len(result) > 0, "Should return non-empty string"
        
        # Should contain BIS header
        assert "BIS" in result.upper() or "Bureau" in result, "Should mention BIS"
        
        print("✅ Batch formatting test passed")
        print(f"   Formatted output length: {len(result)} characters")


class TestBISRAGIntegration:
    """Integration tests for BIS RAG with real data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test"""
        clear_bis_vectorstore_cache()
        yield
        clear_bis_vectorstore_cache()
    
    @pytest.mark.asyncio
    async def test_end_to_end_retrieval(self):
        """End-to-end test: initialize, retrieve, and format cautions"""
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
    async def test_performance_with_many_ingredients(self):
        """Test performance with many ingredients"""
        test_ingredients = [
            "Salicylic Acid",
            "Benzyl Alcohol",
            "Retinol",
            "Hydroquinone",
            "Tretinoin",
            "Alpha Hydroxy Acid",
            "Beta Hydroxy Acid",
            "Niacinamide",
            "Vitamin C",
            "Tocopherol",
        ]
        
        start_time = time.time()
        cautions = await get_bis_cautions_for_ingredients(test_ingredients)
        elapsed_time = time.time() - start_time
        
        assert isinstance(cautions, dict), "Should return dict"
        
        print(f"\n⏱️ Performance test with {len(test_ingredients)} ingredients:")
        print(f"   Time elapsed: {elapsed_time:.2f} seconds")
        print(f"   Average per ingredient: {elapsed_time/len(test_ingredients):.2f} seconds")
        print(f"   Ingredients with cautions: {len(cautions)}/{len(test_ingredients)}")
        
        # Should complete in reasonable time (< 2 minutes for 10 ingredients)
        assert elapsed_time < 120, f"Retrieval took too long: {elapsed_time:.2f}s"


class TestBISRAGErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_handles_missing_vectorstore_gracefully(self):
        """Test that system handles missing vectorstore gracefully"""
        # Clear cache to force re-initialization
        clear_bis_vectorstore_cache()
        
        # If no PDFs exist, should return empty dict, not crash
        result = await get_bis_cautions_for_ingredients(["Test Ingredient"])
        assert isinstance(result, dict), "Should return dict even if vectorstore unavailable"
        print("✅ Graceful handling of missing vectorstore")
    
    @pytest.mark.asyncio
    async def test_handles_special_characters(self):
        """Test handling of special characters in ingredient names"""
        test_ingredients = [
            "α-Tocopherol",
            "β-Carotene",
            "Vitamin C (Ascorbic Acid)",
            "Sodium Hyaluronate (HA)",
        ]
        
        result = await get_bis_cautions_for_ingredients(test_ingredients)
        assert isinstance(result, dict), "Should handle special characters"
        print("✅ Special characters handled correctly")


def run_comprehensive_tests():
    """Run all comprehensive tests"""
    print("=" * 80)
    print("BIS RAG Comprehensive Test Suite")
    print("=" * 80)
    
    # Run pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])


if __name__ == "__main__":
    run_comprehensive_tests()

