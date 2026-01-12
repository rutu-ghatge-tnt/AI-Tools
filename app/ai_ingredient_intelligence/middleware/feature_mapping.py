"""
Feature Mapping Configuration
=============================

Maps API endpoints to features for aggregated timing analysis.

Features are determined by the endpoint path prefix.
"""

# Feature mapping based on endpoint paths
FEATURE_MAPPING = {
    # Cost Calculator Feature
    "/api/cost-calculator": "Cost Calculator",
    
    # INCI Analysis Feature
    "/api/analyze-inci": "INCI Analysis",
    "/api/decode": "INCI Analysis",  # Alias
    
    # Formulation Reports Feature
    "/api/formulation-report": "Formulation Reports",
    
    # Market Research Feature
    "/api/market-research": "Market Research",
    
    # Product Comparison Feature
    "/api/compare": "Product Comparison",
    "/api/product-comparison": "Product Comparison",
    
    # Ingredient Search Feature
    "/api/ingredient-search": "Ingredient Search",
    "/api/search": "Ingredient Search",  # Alias
    
    # Formula Generation Feature
    "/api/formula-generation": "Formula Generation",
    "/api/generate-formula": "Formula Generation",  # Alias
    
    # Inspiration Boards Feature
    "/api/inspiration-boards": "Inspiration Boards",
    "/api/boards": "Inspiration Boards",  # Alias
    
    # Dashboard Stats Feature
    "/api/dashboard": "Dashboard Stats",
    "/api/stats": "Dashboard Stats",  # Alias
    
    # Authentication Feature
    "/api/auth": "Authentication",
    "/api/login": "Authentication",
    "/api/register": "Authentication",
    
    # Face Analysis Feature
    "/api/face-analysis": "Face Analysis",
    
    # Chatbot Feature
    "/api/chat": "Chatbot",
    "/api/chatbot": "Chatbot",  # Alias
    
    # Ingredient History Feature
    "/api/ingredient-history": "Ingredient History",
    "/api/history": "Ingredient History",  # Alias
    
    # Distributor Management Feature
    "/api/distributor": "Distributor Management",
    
    # Make a Wish Feature
    "/api/make-wish": "Make a Wish",
    "/api/wish": "Make a Wish",  # Alias
    
    # Health Checks (not a feature, but tracked)
    "/api/health": "System Health",
    "/api/server-health": "System Health",
}


def get_feature_for_endpoint(path: str) -> str:
    """
    Determine which feature an endpoint belongs to based on its path.
    
    Args:
        path: The endpoint path (e.g., "/api/cost-calculator/analyze")
    
    Returns:
        Feature name (e.g., "Cost Calculator") or "Unknown" if not mapped
    """
    # Check for exact matches first
    if path in FEATURE_MAPPING:
        return FEATURE_MAPPING[path]
    
    # Check for prefix matches (most common case)
    for prefix, feature in FEATURE_MAPPING.items():
        if path.startswith(prefix):
            return feature
    
    # Default to "Unknown" for unmapped endpoints
    return "Unknown"


def get_all_features() -> list:
    """Get a list of all known features."""
    return sorted(set(FEATURE_MAPPING.values()))


def get_endpoints_for_feature(feature: str) -> list:
    """
    Get all endpoint prefixes that belong to a feature.
    
    Args:
        feature: Feature name (e.g., "Cost Calculator")
    
    Returns:
        List of endpoint prefixes
    """
    return [prefix for prefix, f in FEATURE_MAPPING.items() if f == feature]




