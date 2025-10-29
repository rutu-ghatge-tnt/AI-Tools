"""
Product Recommendation Engine
Handles skincare product recommendations based on analysis results and budget
"""

import os
import pandas as pd
from typing import List, Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class RecommendationEngine:
    """Handles product recommendations from CSV data"""
    
    def __init__(self, csv_path: Optional[str] = None):
        """Initialize the recommendation engine with CSV data"""
        self.csv_path = csv_path or self._get_default_csv_path()
        self.products = self._load_products()
        
    def _get_default_csv_path(self) -> str:
        """Get the default CSV path"""
        # Get project root (where main.py is located)
        project_root = Path(__file__).parent.parent.parent.parent
        return str(project_root / "skincare_products.csv")
    
    def _load_products(self) -> List[Dict]:
        """Load products from CSV file"""
        try:
            if not os.path.exists(self.csv_path):
                logger.error(f"CSV file not found: {self.csv_path}")
                return []
                
            df = pd.read_csv(self.csv_path)
            df['price_inr'] = pd.to_numeric(
                df['price'].str.replace('£', ''), errors='coerce'
            ) * 100  # Convert GBP to INR (approximate)
            
            products = []
            for _, row in df.iterrows():
                product = {
                    'product_name': row.get('product_name', 'Unknown Product'),
                    'brand': 'Unknown',  # CSV doesn't have brand column
                    'product_type': row.get('product_type', 'Unknown'),
                    'price_inr': row.get('price_inr', 0),
                    'ingredients': row.get('ingredients', ''),
                    'description': '',  # CSV doesn't have description
                    'product_url': row.get('product_url', ''),
                    'image_url': '',
                    'country_of_origin': '',
                    'manufacturer': '',
                    'expiry_date': '',
                    's3_uploaded': False,
                    's3_image': ''
                }
                products.append(product)
                
            logger.info(f"Loaded {len(products)} products from CSV")
            return products
            
        except Exception as e:
            logger.error(f"Error loading products from CSV: {e}")
            return []
    
    def get_product_category(self, product: Dict) -> str:
        """Determine product category based on name and type"""
        name = product.get('product_name', '').lower()
        product_type = product.get('product_type', '').lower()
        
        # Check for sunscreen first (SPF products)
        if 'spf' in name or 'spf' in product_type or 'sun protection' in name:
            return 'sunscreen'
        elif any(keyword in name for keyword in ['cleanser', 'face wash', 'facewash', 'cleansing']):
            return 'cleanser'
        elif any(keyword in name for keyword in ['serum']):
            return 'serum'
        elif 'moisturiser' in product_type or 'moisturizer' in product_type:
            return 'moisturizer'
        else:
            return 'other'
    
    def score_product(self, product: Dict, analysis_keywords: List[str], skin_type: str) -> float:
        """Score a product based on analysis keywords and skin type"""
        score = 0
        
        # Base score
        score += 50
        
        # Analysis keyword matching
        ingredients = product.get('ingredients', '').lower()
        name = product.get('product_name', '').lower()
        
        for keyword in analysis_keywords:
            if keyword.lower() in ingredients or keyword.lower() in name:
                score += 20
        
        # Skin type matching
        if skin_type.lower() == 'dry' and any(k in ingredients for k in ['hyaluronic', 'glycerin', 'ceramide']):
            score += 30
        elif skin_type.lower() == 'oily' and any(k in ingredients for k in ['salicylic', 'niacinamide', 'oil-free']):
            score += 30
        elif skin_type.lower() == 'sensitive' and any(k in ingredients for k in ['gentle', 'fragrance-free', 'hypoallergenic']):
            score += 30
        
        # Price efficiency (lower price = higher score for same quality)
        price = product.get('price_inr', 0)
        if price > 0:
            score += max(0, 100 - price/50)  # Higher score for lower prices
        
        return score
    
    def get_recommendations(self, budget: float, analysis_keywords: List[str], 
                          skin_type: str, num_products: int = 4) -> List[Dict]:
        """
        Get product recommendations using knapsack algorithm
        
        Args:
            budget: Available budget in INR
            analysis_keywords: Keywords from skin analysis
            skin_type: Estimated skin type
            num_products: Number of products to recommend (default: 4)
            
        Returns:
            List of recommended products
        """
        if not self.products:
            logger.warning("No products available for recommendations")
            return []
        
        # Define required categories
        required_categories = ['cleanser', 'moisturizer', 'serum', 'sunscreen']
        recommendations = []
        remaining_budget = budget
        
        # FIRST: Ensure sunscreen is always included (MANDATORY)
        sunscreen_products = [
            p for p in self.products 
            if self.get_product_category(p) == 'sunscreen'
        ]
        
        if sunscreen_products:
            # Score and sort sunscreen products
            for product in sunscreen_products:
                product['score'] = self.score_product(product, analysis_keywords, skin_type)
            
            best_sunscreen = max(sunscreen_products, key=lambda x: x['score'])
            
            recommendations.append({
                'name': best_sunscreen['product_name'],
                'brand': best_sunscreen.get('brand', 'Unknown'),
                'category': 'Sunscreen',
                'price_inr': best_sunscreen['price_inr'],
                'rating': None,
                'description': f"Essential sunscreen for {skin_type} skin",
                'ingredients': best_sunscreen['ingredients'].split(', ') if best_sunscreen['ingredients'] else [],
                'skin_types': [skin_type],
                'concerns': analysis_keywords,
                'size': None,
                'availability': None,
                'url': best_sunscreen.get('product_url', ''),
                'reasoning': f"SPF protection is mandatory for skin health. Addresses concerns: {', '.join(analysis_keywords)}."
            })
            
            remaining_budget -= best_sunscreen['price_inr']
        else:
            # If no sunscreen found, try to find any SPF product
            spf_fallback = [
                p for p in self.products 
                if 'spf' in p.get('product_name', '').lower()
            ]
            if spf_fallback:
                best_spf = min(spf_fallback, key=lambda x: x.get('price_inr', 0))
                recommendations.append({
                    'name': best_spf['product_name'],
                    'brand': best_spf.get('brand', 'Unknown'),
                    'category': 'Sunscreen',
                    'price_inr': best_spf['price_inr'],
                    'rating': None,
                    'description': f"Essential sunscreen for {skin_type} skin",
                    'ingredients': best_spf['ingredients'].split(', ') if best_spf['ingredients'] else [],
                    'skin_types': [skin_type],
                    'concerns': analysis_keywords,
                    'size': None,
                    'availability': None,
                    'url': best_spf.get('product_url', ''),
                    'reasoning': f"SPF protection is mandatory for skin health. This product provides essential UV protection."
                })
                remaining_budget -= best_spf['price_inr']
        
        # SECOND: Fill remaining categories with remaining budget
        other_categories = ['cleanser', 'moisturizer', 'serum']
        
        for category in other_categories:
            if remaining_budget <= 0:
                break
                
            # Filter products for this category
            category_products = [
                p for p in self.products 
                if self.get_product_category(p) == category
                and p.get('price_inr', 0) <= remaining_budget
            ]
            
            if category_products:
                # Score products
                for product in category_products:
                    product['score'] = self.score_product(product, analysis_keywords, skin_type)
                
                # Select the best product for this category
                best_product = max(category_products, key=lambda x: x['score'])
                
                # Add to recommendations
                recommendations.append({
                    'name': best_product['product_name'],
                    'brand': best_product.get('brand', 'Unknown'),
                    'category': category.title(),
                    'price_inr': best_product['price_inr'],
                    'rating': None,
                    'description': f"Recommended {category} for {skin_type} skin",
                    'ingredients': best_product['ingredients'].split(', ') if best_product['ingredients'] else [],
                    'skin_types': [skin_type],
                    'concerns': analysis_keywords,
                    'size': None,
                    'availability': None,
                    'url': best_product.get('product_url', ''),
                    'reasoning': f"Addresses your specific concerns: {', '.join(analysis_keywords)}. Excellent value for money."
                })
                
                remaining_budget -= best_product['price_inr']
        
        return recommendations
    
    def get_budget_summary(self, recommendations: List[Dict], budget: float) -> Dict:
        """Get budget summary for recommendations"""
        total_cost = sum(rec.get('price_inr', 0) for rec in recommendations)
        budget_used = (total_cost / budget) * 100 if budget > 0 else 0
        remaining = budget - total_cost
        
        return {
            'total_cost': total_cost,
            'budget_used_percent': budget_used,
            'remaining': remaining,
            'over_budget': remaining < 0,
            'products_count': len(recommendations),
            'target_count': 4
        }
