"""
Make A Wish Rules Engine
=========================

This module implements the rules engine for the Make A Wish module based on
the comprehensive rules document. It validates user selections and applies
auto-selections/locks before sending to AI, reducing AI dependency and costs.

The rules engine implements:
- Category → Product Type rules
- Product Type → Benefit auto-selection
- Benefit conflicts and compatibility
- Texture restrictions
- Ingredient conflicts
- Age group restrictions
- Skin type validations

This reduces the need for AI to handle these validations, making prompts shorter
and more focused on actual formulation decisions.
"""

from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class ValidationSeverity(Enum):
    """Severity levels for validation results"""
    BLOCK = "block"  # Cannot proceed
    WARN = "warn"  # Warning but can proceed
    INFO = "info"  # Informational
    SUGGEST = "suggest"  # Suggestion


class ValidationResult:
    """Result of a validation check"""
    def __init__(
        self,
        severity: ValidationSeverity,
        message: str,
        field: Optional[str] = None,
        auto_fix: Optional[Dict[str, Any]] = None
    ):
        self.severity = severity
        self.message = message
        self.field = field
        self.auto_fix = auto_fix or {}


class MakeWishRulesEngine:
    """
    Rules engine for Make A Wish module.
    
    Validates user selections and applies rules from the comprehensive
    rules document to ensure valid combinations before AI processing.
    """
    
    def __init__(self):
        """Initialize the rules engine with rule definitions"""
        self._initialize_rules()
    
    def _initialize_rules(self):
        """Initialize all rule definitions"""
        
        # Product Type → Benefit Auto-Selection Rules
        self.auto_lock_benefits = {
            # Skincare
            'sunscreen': {'primary': 'sun-protection', 'locked': True},
            'exfoliator': {'primary': 'exfoliation', 'locked': True},
            'spot-treatment': {'primary': 'acne-control', 'locked': True},
            # Haircare
            'shampoo': {'primary': 'cleansing', 'locked': True},
            'conditioner': {'primary': 'deep-conditioning', 'locked': True},
            'hair-mask': {'primary': 'damage-repair', 'locked': False},  # Can change
        }
        
        # Product Type → Texture Auto-Selection Rules
        self.auto_lock_textures = {
            'toner': 'lightweight',
            'face-oil': 'oil',
            'lip-care': 'balm',
            'mist': 'lightweight',
            'hair-oil': 'oil',
            'conditioner': 'creamy',
        }
        
        # Benefit Conflicts (cannot select together)
        self.benefit_conflicts = {
            'oil-control': ['hydration', 'nourishing'],
            'hydration': ['oil-control'],
            'acne-control': ['nourishing'],
            'sun-protection': ['exfoliation'],
            'dandruff': ['color-protect'],
        }
        
        # Skin Type Conflicts (mutually exclusive)
        self.skin_type_conflicts = {
            'oily': ['dry'],
            'dry': ['oily'],
            'normal': ['oily', 'dry', 'sensitive', 'acne-prone'],
        }
        
        # Age Group Restrictions by Benefit
        self.age_restrictions = {
            'anti-aging': {'block': ['teens', 'all-ages']},
            'firming': {'block': ['teens']},
            'dark-spots': {'block': ['teens']},
        }
        
        # Ingredient Conflicts
        self.ingredient_conflicts = {
            'vitamin-c': ['retinol'],  # Block together
            'retinol': ['vitamin-c'],
        }
    
    def validate_wish_data(self, wish_data: Dict[str, Any]) -> Tuple[bool, List[ValidationResult], Dict[str, Any]]:
        """
        Validate and auto-fix wish data based on rules.
        
        Args:
            wish_data: User's wish data dictionary
            
        Returns:
            Tuple of:
            - can_proceed: Whether validation passed
            - results: List of validation results (warnings, errors, etc.)
            - fixed_data: Wish data with auto-fixes applied
        """
        results = []
        fixed_data = wish_data.copy()
        can_proceed = True
        
        category = fixed_data.get('category', 'skincare')
        product_type = fixed_data.get('productType')
        benefits = fixed_data.get('benefits', [])
        primary_benefit = benefits[0] if benefits else None
        texture = fixed_data.get('texture')
        age_group = fixed_data.get('ageGroup')
        skin_types = fixed_data.get('skinType', [])
        must_have_ingredients = fixed_data.get('mustHaveIngredients', [])
        
        # Rule 1: Product Type → Benefit Auto-Selection
        if product_type in self.auto_lock_benefits:
            rule = self.auto_lock_benefits[product_type]
            auto_benefit = rule['primary']
            is_locked = rule.get('locked', False)
            
            if primary_benefit != auto_benefit:
                if is_locked:
                    # Auto-fix: Set the locked benefit
                    if not benefits:
                        benefits = []
                    if len(benefits) == 0:
                        benefits.append(auto_benefit)
                    else:
                        benefits[0] = auto_benefit
                    fixed_data['benefits'] = benefits
                    results.append(ValidationResult(
                        ValidationSeverity.INFO,
                        f"{auto_benefit.replace('-', ' ').title()} is automatically selected for {product_type}",
                        field='benefits'
                    ))
                else:
                    # Suggest the default
                    results.append(ValidationResult(
                        ValidationSeverity.SUGGEST,
                        f"{auto_benefit.replace('-', ' ').title()} is recommended for {product_type}",
                        field='benefits'
                    ))
        
        # Rule 2: Product Type → Texture Auto-Selection
        if product_type in self.auto_lock_textures:
            auto_texture = self.auto_lock_textures[product_type]
            if texture != auto_texture:
                fixed_data['texture'] = auto_texture
                results.append(ValidationResult(
                    ValidationSeverity.INFO,
                    f"Texture automatically set to {auto_texture} for {product_type}",
                    field='texture'
                ))
        
        # Rule 3: Benefit Conflicts
        if primary_benefit in self.benefit_conflicts:
            conflicting = self.benefit_conflicts[primary_benefit]
            secondary_benefit = benefits[1] if len(benefits) > 1 else None
            if secondary_benefit in conflicting:
                results.append(ValidationResult(
                    ValidationSeverity.WARN,
                    f"{primary_benefit.replace('-', ' ').title()} conflicts with {secondary_benefit.replace('-', ' ').title()}. Consider separate products.",
                    field='benefits'
                ))
        
        # Rule 4: Skin Type Conflicts
        for skin_type in skin_types:
            if skin_type in self.skin_type_conflicts:
                conflicts = self.skin_type_conflicts[skin_type]
                for conflict in conflicts:
                    if conflict in skin_types:
                        results.append(ValidationResult(
                            ValidationSeverity.BLOCK,
                            f"{skin_type.title()} and {conflict.title()} cannot be selected together",
                            field='skinType'
                        ))
                        can_proceed = False
        
        # Rule 5: Age Group Restrictions
        if primary_benefit in self.age_restrictions:
            restrictions = self.age_restrictions[primary_benefit]
            blocked_ages = restrictions.get('block', [])
            if age_group in blocked_ages:
                results.append(ValidationResult(
                    ValidationSeverity.BLOCK,
                    f"{primary_benefit.replace('-', ' ').title()} is not recommended for {age_group.replace('-', ' ').title()}",
                    field='ageGroup'
                ))
                can_proceed = False
        
        # Rule 6: Ingredient Conflicts
        for ingredient in must_have_ingredients:
            if ingredient in self.ingredient_conflicts:
                conflicts = self.ingredient_conflicts[ingredient]
                for conflict in conflicts:
                    if conflict in must_have_ingredients:
                        results.append(ValidationResult(
                            ValidationSeverity.BLOCK,
                            f"{ingredient.replace('-', ' ').title()} and {conflict.replace('-', ' ').title()} cannot be used together. Use in separate AM/PM products.",
                            field='mustHaveIngredients'
                        ))
                        can_proceed = False
        
        return can_proceed, results, fixed_data
    
    def get_disabled_options(
        self,
        field: str,
        wish_data: Dict[str, Any]
    ) -> List[str]:
        """
        Get list of disabled options for a field based on current selections.
        
        Args:
            field: Field name (e.g., 'benefits', 'texture', 'skinType')
            wish_data: Current wish data
            
        Returns:
            List of disabled option IDs
        """
        disabled = []
        
        category = wish_data.get('category', 'skincare')
        product_type = wish_data.get('productType')
        benefits = wish_data.get('benefits', [])
        primary_benefit = benefits[0] if benefits else None
        
        if field == 'benefits':
            # Disable conflicting secondary benefits
            if primary_benefit in self.benefit_conflicts:
                disabled.extend(self.benefit_conflicts[primary_benefit])
            
            # Disable same benefit as primary
            if primary_benefit:
                disabled.append(primary_benefit)
        
        elif field == 'texture':
            # Disable textures based on product type
            if product_type == 'serum':
                disabled.extend(['balm', 'cream'])
            elif product_type == 'sunscreen':
                disabled.extend(['balm', 'oil'])
            elif product_type == 'cleanser':
                disabled.extend(['balm', 'cream'])
        
        elif field == 'skinType':
            # Disable conflicting skin types
            current_skin_types = wish_data.get('skinType', [])
            for skin_type in current_skin_types:
                if skin_type in self.skin_type_conflicts:
                    disabled.extend(self.skin_type_conflicts[skin_type])
        
        return list(set(disabled))  # Remove duplicates
    
    def get_highlighted_options(
        self,
        field: str,
        wish_data: Dict[str, Any]
    ) -> List[str]:
        """
        Get list of highlighted/recommended options for a field.
        
        Args:
            field: Field name
            wish_data: Current wish data
            
        Returns:
            List of highlighted option IDs
        """
        highlighted = []
        
        category = wish_data.get('category', 'skincare')
        product_type = wish_data.get('productType')
        benefits = wish_data.get('benefits', [])
        primary_benefit = benefits[0] if benefits else None
        skin_types = wish_data.get('skinType', [])
        
        if field == 'benefits':
            # Highlight recommended benefits based on product type
            if product_type in self.auto_lock_benefits:
                rule = self.auto_lock_benefits[product_type]
                highlighted.append(rule['primary'])
        
        elif field == 'texture':
            # Highlight textures based on skin type
            if 'oily' in skin_types:
                highlighted.extend(['lightweight', 'gel'])
            elif 'dry' in skin_types:
                highlighted.extend(['cream', 'oil', 'balm'])
            elif 'sensitive' in skin_types:
                highlighted.extend(['lotion', 'cream'])
        
        return list(set(highlighted))


# Global rules engine instance
_rules_engine: Optional[MakeWishRulesEngine] = None


def get_rules_engine() -> MakeWishRulesEngine:
    """Get or create the global rules engine instance"""
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = MakeWishRulesEngine()
    return _rules_engine

