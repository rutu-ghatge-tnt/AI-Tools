"""
Simple Face Analysis App - Single Page Interface
- Upload or capture image
- Apply privacy mask (optional)
- Analyze skin health with AI
- Get budget-aware product recommendations
"""

import streamlit as st
import cv2
import numpy as np
import requests
import base64
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import modules
from face_analysis.backend.modules.filter import FaceFilter
from face_analysis.backend.modules.recommendation import RecommendationEngine

# Page configuration
st.set_page_config(
    page_title="Face Analysis System",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize components
@st.cache_resource
def get_face_filter():
    """Get cached face filter instance"""
    return FaceFilter()

@st.cache_resource
def get_recommendation_engine():
    """Get cached recommendation engine instance"""
    return RecommendationEngine()

def main():
    """Main application function"""
    
    # Header
    st.title("🔍 AI-Powered Face Analysis System")
    st.markdown("**Professional skincare analysis with privacy protection and budget-aware recommendations**")
    
    # Initialize session state
    if 'analysis_results' not in st.session_state:
        st.session_state.analysis_results = None
    if 'recommendations' not in st.session_state:
        st.session_state.recommendations = None
    if 'original_image' not in st.session_state:
        st.session_state.original_image = None
    if 'masked_image' not in st.session_state:
        st.session_state.masked_image = None
    
    # Create two columns for layout
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📸 Image Input")
        
        # Image input method selection
        input_method = st.radio(
            "Choose input method:",
            ["Upload Image", "Camera Capture"],
            horizontal=True
        )
        
        uploaded_image = None
        
        if input_method == "Upload Image":
            uploaded_file = st.file_uploader(
                "Upload a clear photo of your face",
                type=['jpg', 'jpeg', 'png'],
                help="Upload a clear, well-lit photo of your face for best results"
            )
            if uploaded_file is not None:
                uploaded_image = uploaded_file.read()
        
        else:  # Camera Capture
            camera_image = st.camera_input("Take a photo of your face")
            if camera_image is not None:
                uploaded_image = camera_image.read()
        
        # Display uploaded image
        if uploaded_image is not None:
            st.session_state.original_image = uploaded_image
            
            # Convert to OpenCV format for processing
            nparr = np.frombuffer(uploaded_image, np.uint8)
            cv_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
            # Display original image
            st.subheader("📷 Original Image")
            st.image(uploaded_image, use_container_width=True)
            
            # Privacy mask option
            st.subheader("🔒 Privacy Protection")
            apply_mask = st.checkbox(
                "Apply privacy mask (recommended)",
                value=True,
                
            )
            
            if apply_mask:
                try:
                    # Apply privacy filter
                    face_filter = get_face_filter()
                    masked_image = face_filter.apply_privacy_filter_from_bytes(uploaded_image)
                    
                    if masked_image is not None:
                        st.session_state.masked_image = masked_image
                        st.subheader("🎭 Masked Image")
                        st.image(masked_image, use_container_width=True)
                    else:
                        st.warning("Could not apply privacy mask. Analysis will use original image.")
                        
                except Exception as e:
                    st.error(f"Error applying privacy mask: {e}")
                    st.info("Analysis will continue with original image.")
    
    with col2:
        st.header("👤 Personal Information")
        
        # Personal information form
        with st.form("personal_info"):
            ethnicity = st.selectbox(
                "Ethnicity", 
                ["Caucasian", "African American", "Asian", "Indian", 
                 "Hispanic/Latino", "Middle Eastern", "Mixed", "Other"],
                
            )
            
            gender = st.selectbox(
                "Gender", 
                ["Male", "Female", "Non-binary", "Prefer not to say"], 
                
            )
            
            budget = st.slider(
                "Budget (₹)",
                min_value=500,
                max_value=5000,
                value=3500,
                step=100,
                help="Your budget for skincare products in Indian Rupees"
            )
            
            submitted = st.form_submit_button("🔍 Analyze & Get Recommendations", type="primary")
    
    # Analysis and recommendations
    if submitted and uploaded_image is not None:
        
        # Choose image for analysis - ALWAYS use original image for Claude
        analysis_image = st.session_state.original_image
        
        # Show analysis progress
        with st.spinner("🔍 Analyzing image with Claude AI... This may take 1-2 minutes"):
            try:
                # Prepare image for API
                image_base64 = base64.b64encode(analysis_image).decode('utf-8')
                
                # Call analysis API
                api_url = "http://localhost:8000/analyze/json"
                payload = {
                    "image": image_base64,
                    "ethnicity": ethnicity,
                    "gender": gender
                }
                
                response = requests.post(api_url, json=payload, timeout=120)
                
                if response.status_code == 200:
                    results = response.json()
                    
                    if results.get("success", True):
                        st.session_state.analysis_results = results
                        
                        # Display analysis results
                        display_analysis_results(results)
                        
                        # Generate recommendations
                        generate_recommendations(results, budget, ethnicity, gender)
                        
                    else:
                        st.error(f"Analysis failed: {results.get('error', 'Unknown error')}")
                        
                else:
                    st.error(f"API request failed with status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                st.error("⏰ Analysis timed out. Please try again with a smaller image.")
                st.info("💡 Tip: Try uploading a smaller image (under 1MB) for faster processing.")
                
            except requests.exceptions.ConnectionError:
                st.error("🔌 Could not connect to the analysis server.")
                st.info("💡 Make sure the backend server is running on http://localhost:8000")
                
            except Exception as e:
                st.error(f"❌ Error during analysis: {e}")
                st.info("💡 Please try again or contact support if the issue persists.")

def display_analysis_results(results: Dict):
    """Display the analysis results in a professional format"""
    
    st.header("📊 Analysis Results")
    
    # Overall score header
    col1, col2 = st.columns([2, 1])
    
    with col1:
        overall_score = results.get("overall_score", 0)
        estimated_age = results.get("estimated_age", "N/A")
        estimated_skin_type = results.get("estimated_skintype", "N/A")
        
        st.metric("Overall Skin Health Score", f"{overall_score}/100")
        
    with col2:
        st.metric("Estimated Age", estimated_age)
        st.metric("Skin Type", estimated_skin_type)
    
    # Analysis parameters
    analysis = results.get("analysis", {})
    if analysis:
        st.subheader("📈 Detailed Analysis")
        
        # Create expandable sections for each parameter
        for param_name, param_data in analysis.items():
            if isinstance(param_data, dict):
                score = param_data.get("score", 0)
                observation = param_data.get("observation", "")
                recommendation = param_data.get("recommendation", "")
                
                with st.expander(f"{param_name.title()}: {score}/100", expanded=False):
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        st.write("**Observation:**")
                        st.write(observation)
                    
                    with col2:
                        st.write("**Recommendation:**")
                        st.write(recommendation)
    
    # Summary
    summary = results.get("summary", "")
    if summary:
        st.subheader("📝 Summary")
        st.info(summary)

def generate_recommendations(results: Dict, budget: float, ethnicity: str, gender: str):
    """Generate and display product recommendations"""
    
    st.header("🛍️ Product Recommendations")
    
    # Extract analysis keywords for recommendations
    analysis = results.get("analysis", {})
    analysis_keywords = []
    
    for param_name, param_data in analysis.items():
        if isinstance(param_data, dict):
            observation = param_data.get("observation", "").lower()
            recommendation = param_data.get("recommendation", "").lower()
            
            # Extract keywords from observations and recommendations
            keywords = []
            if "acne" in observation or "acne" in recommendation:
                keywords.append("acne")
            if "dry" in observation or "hydration" in recommendation:
                keywords.append("hydration")
            if "oil" in observation or "oil" in recommendation:
                keywords.append("oiliness")
            if "dark" in observation or "dark" in recommendation:
                keywords.append("dark_circle")
            if "wrinkle" in observation or "wrinkle" in recommendation:
                keywords.append("wrinkle")
            if "uneven" in observation or "tone" in recommendation:
                keywords.append("uneven_skintone")
            
            analysis_keywords.extend(keywords)
    
    # Remove duplicates
    analysis_keywords = list(set(analysis_keywords))
    
    # Get skin type
    estimated_skin_type = results.get("estimated_skintype", "Normal")
    
    try:
        # Get recommendations
        recommendation_engine = get_recommendation_engine()
        recommendations = recommendation_engine.get_recommendations(
            budget=budget,
            analysis_keywords=analysis_keywords,
            skin_type=estimated_skin_type
        )
        
        if recommendations:
            st.session_state.recommendations = recommendations
            
            # Budget summary
            budget_summary = recommendation_engine.get_budget_summary(recommendations, budget)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Cost", f"₹{budget_summary['total_cost']:.1f}")
            with col2:
                st.metric("Budget Used", f"{budget_summary['budget_used_percent']:.1f}%")
            with col3:
                remaining = budget_summary['remaining']
                if remaining >= 0:
                    st.metric("Remaining", f"₹{remaining:.1f}")
                else:
                    st.metric("Over Budget", f"₹{abs(remaining):.1f}")
            
            # Display recommendations
            st.subheader(f"🌅 Complete Skincare Routine")
            st.success(f"✅ {budget_summary['products_count']}/{budget_summary['target_count']} products recommended for your complete routine")
            
            # Group by category
            categories = {}
            for rec in recommendations:
                category = rec.get('category', 'Other')
                if category not in categories:
                    categories[category] = []
                categories[category].append(rec)
            
            # Display by category
            for category, products in categories.items():
                with st.expander(f"{category} ({len(products)} product{'s' if len(products) > 1 else ''})", expanded=True):
                    for product in products:
                        st.write(f"**{product['name']}** - ₹{product['price_inr']:.1f}")
                        st.write(f"*Brand:* {product['brand']}")
                        st.write(f"*Price:* ₹{product['price_inr']:.1f}")
                        st.write(f"*Skin Types:* {', '.join(product['skin_types'])}")
                        st.write(f"*Concerns:* {', '.join(product['concerns'])}")
                        st.write(f"**🎯 Why This Product:**")
                        st.write(product['reasoning'])
                        
                        if product['ingredients']:
                            st.write(f"*Key Ingredients:* {', '.join(product['ingredients'][:5])}")
                        
                        if product['url']:
                            st.write(f"*Buy:* {product['url']}")
                        
                        st.divider()
            
            # Warnings
            if budget_summary['over_budget']:
                st.warning("⚠️ Recommendations exceed your budget. Consider increasing budget for complete routine.")
            
            missing_categories = budget_summary['target_count'] - budget_summary['products_count']
            if missing_categories > 0:
                st.warning(f"⚠️ Missing categories: {missing_categories} products. Try increasing your budget to get a complete routine.")
        
        else:
            st.warning("No products found matching your criteria. Try adjusting your budget or analysis parameters.")
            
    except Exception as e:
        st.error(f"Error generating recommendations: {e}")

if __name__ == "__main__":
    main()