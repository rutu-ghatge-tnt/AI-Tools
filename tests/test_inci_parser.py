"""
Test INCI parser with various separators
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string


def test_comma_separated():
    """Test comma-separated ingredients"""
    result = parse_inci_string("Water, Glycerin, Sodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Comma separator test passed")


def test_pipe_separated():
    """Test pipe-separated ingredients"""
    result = parse_inci_string("Water | Glycerin | Sodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Pipe separator test passed")


def test_semicolon_separated():
    """Test semicolon-separated ingredients"""
    result = parse_inci_string("Water; Glycerin; Sodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Semicolon separator test passed")


def test_and_separated():
    """Test 'and' separated ingredients"""
    result = parse_inci_string("Water and Glycerin and Sodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] 'and' separator test passed")


def test_ampersand_separated():
    """Test ampersand separated ingredients"""
    result = parse_inci_string("Water & Glycerin & Sodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Ampersand separator test passed")


def test_hyphen_separated():
    """Test hyphen-separated ingredients (when used as separator)"""
    result = parse_inci_string("Water - Glycerin - Sodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Hyphen separator test passed")


def test_newline_separated():
    """Test newline-separated ingredients"""
    result = parse_inci_string("Water\nGlycerin\nSodium Hyaluronate")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Newline separator test passed")


def test_mixed_separators():
    """Test mixed separators"""
    result = parse_inci_string("Water, Glycerin | Sodium Hyaluronate; Retinol")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate", "Retinol"]
    print("[OK] Mixed separators test passed")


def test_list_input():
    """Test list input (each item may contain separators)"""
    result = parse_inci_string(["Water, Glycerin", "Sodium Hyaluronate | Retinol"])
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate", "Retinol"]
    print("[OK] List input test passed")


def test_ingredient_with_hyphen():
    """Test that ingredient names with hyphens are preserved"""
    result = parse_inci_string("Alpha-Hydroxy Acid, Beta-Hydroxy Acid")
    # Should preserve hyphens within ingredient names
    assert "Alpha-Hydroxy Acid" in result
    assert "Beta-Hydroxy Acid" in result
    print("[OK] Hyphen in ingredient name preserved")


def test_single_ingredient():
    """Test single ingredient (no separators)"""
    result = parse_inci_string("Water")
    assert result == ["Water"]
    print("[OK] Single ingredient test passed")


def test_empty_input():
    """Test empty input"""
    result = parse_inci_string("")
    assert result == []
    result = parse_inci_string([])
    assert result == []
    print("[OK] Empty input test passed")


def test_whitespace_handling():
    """Test whitespace handling"""
    result = parse_inci_string("  Water  ,  Glycerin  ,  Sodium Hyaluronate  ")
    assert result == ["Water", "Glycerin", "Sodium Hyaluronate"]
    print("[OK] Whitespace handling test passed")


def test_combination_with_and_paren():
    """Test combination with (and) when other separators exist"""
    result = parse_inci_string("Water, Xylitylglucoside (and) Anhydroxylitol (and) Xylitol, Glycerin")
    assert "Xylitylglucoside (and) Anhydroxylitol (and) Xylitol" in result
    assert len(result) == 3
    print("[OK] Combination with (and) test passed")


def test_combination_with_ampersand():
    """Test combination with & when other separators exist"""
    result = parse_inci_string("Water, Acacia Senegal Gum & Xanthan Gum, Glycerin")
    assert "Acacia Senegal Gum & Xanthan Gum" in result
    assert len(result) == 3
    print("[OK] Combination with & test passed")


def test_combination_with_and_word():
    """Test combination with 'and' word when other separators exist"""
    result = parse_inci_string("Water, Benzyl Alcohol and Ethylhexylglycerin and Tocopherol, Glycerin")
    assert "Benzyl Alcohol and Ethylhexylglycerin and Tocopherol" in result
    assert len(result) == 3
    print("[OK] Combination with 'and' word test passed")


def test_no_other_separators_and_splits():
    """Test that 'and' splits when no other separators exist"""
    result = parse_inci_string("Water and Glycerin")
    assert result == ["Water", "Glycerin"]
    print("[OK] 'and' splits when no other separators test passed")


def run_all_tests():
    """Run all tests"""
    print("=" * 80)
    print("INCI Parser Tests")
    print("=" * 80)
    
    tests = [
        test_comma_separated,
        test_pipe_separated,
        test_semicolon_separated,
        test_and_separated,
        test_ampersand_separated,
        test_hyphen_separated,
        test_newline_separated,
        test_mixed_separators,
        test_list_input,
        test_ingredient_with_hyphen,
        test_single_ingredient,
        test_empty_input,
        test_whitespace_handling,
        test_combination_with_and_paren,
        test_combination_with_ampersand,
        test_combination_with_and_word,
        test_no_other_separators_and_splits,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAILED] {test.__name__} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
