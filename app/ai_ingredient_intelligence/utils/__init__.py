"""
Utility functions for INCI ingredient intelligence
"""
from app.ai_ingredient_intelligence.utils.inci_parser import (
    parse_inci_string,
    normalize_ingredient_name
)

__all__ = [
    "parse_inci_string",
    "normalize_ingredient_name",
]

