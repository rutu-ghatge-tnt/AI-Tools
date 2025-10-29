"""
Face Analysis Module
Handles facial skin health analysis using Claude 3 Opus API
"""

import base64
import io
import json
import os
from typing import Dict, List, Optional, Tuple
import anthropic
from google.cloud import vision
from PIL import Image
import cv2
import numpy as np
import signal
from ..core.config import settings

class FaceAnalyzer:
    def __init__(self):
        """Initialize the Face Analyzer with API keys."""
        self.claude_client = None
        self.analysis_prompt = self._create_analysis_prompt()
        
        # Initialize Claude client only when needed
        if settings.ANTHROPIC_API_KEY:
            try:
                self.claude_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            except Exception as e:
                print(f"Warning: Could not initialize Claude client: {e}")
                print("Analysis will not be available without a valid API key.")
    
    def _create_analysis_prompt(self) -> str:
        """Create the analysis prompt for Claude."""
        return f"""
        You are a professional dermatologist analyzing facial skin health. Please analyze the provided facial image for the following parameters:
        {', '.join(settings.SKIN_ANALYSIS_PARAMETERS)}
        
        For each parameter, provide:
        1. A score from 0-100 (100 being the best)
        2. A detailed observation about the skin condition
        3. Specific notes and suggestions for improvement
        
        Additionally, please provide:
        4. An estimated age based on facial features and skin condition (make your own independent assessment)
        5. An estimated skin type (Oily, Dry, Combination, Normal, Sensitive) based on visual analysis
        
        Consider the person's ethnicity and gender when making your assessment, but provide your own independent estimates for age and skin type based on what you observe in the image.
        Pay attention to lighting conditions and how they might affect the appearance.
        
        Provide your response in JSON format with the following structure:
        {{
            "analysis": {{
                "acne": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "dark_spot": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "dark_circle": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "wrinkle": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "uneven_skintone": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "pores": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "pigmentation": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "dullness": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}},
                "overall_skin_health": {{"observation": "Detailed observation", "score": 0-100, "recommendation": "Specific suggestions"}}
            }},
            "overall_score": "Overall score out of 100 (average of all parameter scores)",
            "estimated_age": "Estimated age in years based on facial analysis",
            "estimated_skintype": "Estimated skin type (Oily/Dry/Combination/Normal/Sensitive)",
            "summary": "Comprehensive assessment summary with lighting considerations",
            "recommendations": "Personalized skincare routine recommendations based on ethnicity and age"
        }}
        """
    
    def encode_image(self, image_path: str) -> str:
        """Encode image to base64 string for API."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def encode_pil_image(self, image: Image.Image) -> str:
        """Encode PIL Image to base64 string for API."""
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    def preprocess_image(self, image_path: str) -> str:
        """Preprocess image for better analysis."""
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image from {image_path}")
        
        # Convert to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Enhance image quality
        # Apply slight sharpening
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(image_rgb, -1, kernel)
        
        # Convert back to PIL Image
        pil_image = Image.fromarray(sharpened)
        
        # Resize if too large (API has size limits) - smaller for faster processing
        max_size = 800  # Reduced from 1024 for faster processing
        if pil_image.width > max_size or pil_image.height > max_size:
            pil_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        return self.encode_pil_image(pil_image)
    
    def analyze_face(self, image_path: str, ethnicity: str, gender: str, age: int) -> Dict:
        """
        Analyze facial skin health using Claude API.
        
        Args:
            image_path: Path to the facial image
            ethnicity: User's ethnicity
            gender: User's gender  
            age: User's age in years
            
        Returns:
            Dictionary containing analysis results
        """
        try:
            # Check if Claude client is available
            if not self.claude_client:
                return {
                    "error": "Claude API client not available. Please check your ANTHROPIC_API_KEY.",
                    "analysis": {},
                    "overall_score": 0,
                    "estimated_age": "N/A",
                    "estimated_skintype": "N/A",
                    "summary": "Analysis unavailable - API key not configured"
                }
            
            # Preprocess and encode image
            base64_image = self.preprocess_image(image_path)
            
            # Create the analysis prompt with user context
            context_prompt = f"""
            Patient Information:
            - Ethnicity: {ethnicity}
            - Gender: {gender}
            
            IMPORTANT: Please provide your own independent estimates for age and skin type based on visual analysis of the facial image. Do not rely on any pre-provided age information.
            
            {self.analysis_prompt}
            """
            
            # Call Claude API
            print("🔍 Using Claude 3 Opus for analysis...")
            print(f"📊 Analyzing image for: {ethnicity}, {gender}, {age} years old")
            print("⏰ This may take 30-90 seconds depending on image complexity...")
            response = self.claude_client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1500,  # Reduced for faster response
                temperature=0.2,  # Lower temperature for more consistent, faster responses
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": context_prompt
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64_image
                                }
                            }
                        ]
                    }
                ]
            )
            
            # Parse response
            analysis_text = response.content[0].text
            print(f"📝 Claude API response length: {len(analysis_text)} characters")
            
            # Try to extract JSON from response with better error handling
            try:
                # Clean the response text first
                analysis_text = analysis_text.strip()
                
                # Find JSON in the response
                start_idx = analysis_text.find('{')
                end_idx = analysis_text.rfind('}') + 1
                
                if start_idx != -1 and end_idx != 0:
                    json_str = analysis_text[start_idx:end_idx]
                    
                    # Clean the JSON string of any control characters
                    json_str = ''.join(char for char in json_str if ord(char) >= 32 or char in '\n\r\t')
                    
                    print(f"🔍 Parsing JSON: {json_str[:200]}...")
                    analysis_result = json.loads(json_str)
                else:
                    # If no JSON found, create a structured response from text
                    return {
                        "error": "Claude API returned unstructured response",
                        "raw_response": analysis_text[:500] + "..." if len(analysis_text) > 500 else analysis_text,
                        "suggestion": "Please try uploading a clearer image or try again."
                    }
            except (json.JSONDecodeError, ValueError) as e:
                # If JSON parsing fails, return structured error
                return {
                    "error": f"Failed to parse Claude API response: {str(e)}",
                    "raw_response": analysis_text[:500] + "..." if len(analysis_text) > 500 else analysis_text,
                    "suggestion": "The AI response format was invalid. Please try again."
                }
            
            print("✅ Claude 3 Opus analysis completed successfully!")
            return analysis_result
            
        except Exception as e:
            # Fallback to Google Vision API
            try:
                return self._analyze_with_google_vision(image_path, ethnicity, gender, age)
            except Exception as fallback_error:
                return {
                    "error": f"Analysis failed: {str(e)}. Fallback also failed: {str(fallback_error)}",
                    "raw_response": None
                }
    
    def _analyze_with_google_vision(self, image_path: str, ethnicity: str, gender: str, age: int) -> Dict:
        """Fallback analysis using Google Vision API."""
        try:
            print("🔄 Claude failed, trying Google Vision API...")
            # Set Google credentials
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = settings.GOOGLE_APPLICATION_CREDENTIALS
            
            # Initialize Google Vision client
            client = vision.ImageAnnotatorClient()
            
            # Read image file
            with open(image_path, 'rb') as image_file:
                image_bytes = image_file.read()
            
            # Create image object
            image = vision.Image(content=image_bytes)
            
            # Perform face detection
            response = client.face_detection(image=image)
            faces = response.face_annotations
            
            if not faces:
                return {"error": "No faces detected in the image"}
            
            # Get the first face
            face = faces[0]
            
            # Analyze skin quality based on face detection
            analysis_result = {
                "analysis": {},
                "overall_score": 0,
                "summary": "Analysis using Google Vision API",
                "recommendations": "Consider professional dermatological consultation"
            }
            
            # Basic scoring based on face detection confidence
            confidence = face.detection_confidence
            base_score = int(confidence * 100)
            
            # Create analysis for each parameter
            for param in settings.SKIN_ANALYSIS_PARAMETERS:
                analysis_result["analysis"][param] = {
                    "observation": f"Basic analysis using computer vision (confidence: {confidence:.2f})",
                    "score": base_score,
                    "notes": "Limited analysis - consider professional consultation"
                }
            
            analysis_result["overall_score"] = base_score
            
            print("✅ Google Vision API analysis completed successfully!")
            return analysis_result
            
        except Exception as e:
            # Final fallback to local computer vision
            try:
                return self._analyze_with_local_cv(image_path, ethnicity, gender, age)
            except Exception as local_error:
                return {"error": f"Google Vision API failed: {str(e)}. Local analysis also failed: {str(local_error)}"}
    
    def _analyze_with_local_cv(self, image_path: str, ethnicity: str, gender: str, age: int) -> Dict:
        """Final fallback using local OpenCV analysis."""
        try:
            print("🔄 Google Vision failed, using local OpenCV analysis...")
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not load image from {image_path}")
            
            # Convert to grayscale for analysis
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Basic skin analysis using OpenCV
            # Calculate image quality metrics
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            # Basic scoring based on image quality
            quality_score = min(100, max(0, int((laplacian_var / 1000) * 50 + (mean_brightness / 255) * 30 + (std_brightness / 100) * 20)))
            
            analysis_result = {
                "analysis": {},
                "overall_score": quality_score,
                "summary": "Basic local computer vision analysis",
                "recommendations": "This is a basic analysis. For accurate results, consult a dermatologist."
            }
            
            # Create analysis for each parameter
            for param in settings.SKIN_ANALYSIS_PARAMETERS:
                analysis_result["analysis"][param] = {
                    "observation": f"Basic computer vision analysis (image quality: {quality_score}/100)",
                    "score": quality_score,
                    "notes": "Limited local analysis - professional consultation recommended"
                }
            
            print("✅ Local OpenCV analysis completed successfully!")
            return analysis_result
            
        except Exception as e:
            return {"error": f"Local computer vision analysis failed: {str(e)}"}
    
    def get_overall_score(self, analysis: Dict) -> float:
        """Calculate overall skin health score from individual parameter scores."""
        if "analysis" not in analysis:
            return 0.0
        
        scores = []
        for param in settings.SKIN_ANALYSIS_PARAMETERS:
            if param in analysis["analysis"] and "score" in analysis["analysis"][param]:
                scores.append(analysis["analysis"][param]["score"])
        
        return sum(scores) / len(scores) if scores else 0.0

