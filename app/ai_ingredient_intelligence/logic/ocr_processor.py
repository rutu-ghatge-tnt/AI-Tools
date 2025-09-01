import os
import base64
import io
from typing import List, Optional, Tuple
import fitz  # PyMuPDF for PDF processing
from PIL import Image
import google.cloud.vision as vision
from google.cloud import storage
import tempfile
import anthropic
import json

class OCRProcessor:
    def __init__(self):
        # Initialize Google Vision client
        self.vision_client = vision.ImageAnnotatorClient()
        
        # Initialize Claude client
        self.claude_client = anthropic.Anthropic(
            api_key=os.getenv("CLAUDE_API_KEY")
        )
        
    async def extract_text_from_image(self, image_data: bytes) -> str:
        """Extract text from image using Google Vision API"""
        try:
            # Create image object
            image = vision.Image(content=image_data)
            
            # Perform text detection
            response = self.vision_client.text_detection(image=image)
            
            if response.error.message:
                raise Exception(f"Google Vision API error: {response.error.message}")
            
            # Extract text from response
            texts = response.text_annotations
            if texts:
                return texts[0].description
            else:
                return ""
                
        except Exception as e:
            raise Exception(f"Failed to extract text from image: {str(e)}")
    
    async def extract_text_from_pdf(self, pdf_data: bytes) -> str:
        """Extract text from PDF using PyMuPDF and Google Vision for images"""
        try:
            # Open PDF with PyMuPDF
            pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
            extracted_text = ""
            
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                
                # Try to extract text directly first
                text = page.get_text()
                if text.strip():
                    extracted_text += text + "\n"
                else:
                    # If no text, extract images and use OCR
                    image_list = page.get_images()
                    for img_index, img in enumerate(image_list):
                        xref = img[0]
                        base_image = pdf_document.extract_image(xref)
                        image_bytes = base_image["image"]
                        
                        # Use Google Vision API for image OCR
                        image_text = await self.extract_text_from_image(image_bytes)
                        extracted_text += image_text + "\n"
            
            pdf_document.close()
            return extracted_text.strip()
            
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
    async def extract_text_from_camera(self, base64_image: str) -> str:
        """Extract text from base64 encoded camera image"""
        try:
            # Decode base64 image
            image_data = base64.b64decode(base64_image)
            
            # Use the same image processing logic
            return await self.extract_text_from_image(image_data)
            
        except Exception as e:
            raise Exception(f"Failed to extract text from camera image: {str(e)}")
    
    async def extract_ingredients_with_claude(self, raw_text: str) -> List[str]:
        """Use Claude API to extract and format INCI names from raw text"""
        try:
            # Prepare prompt for Claude
            prompt = f"""
You are an expert cosmetic ingredient analyst. Your task is to extract INCI (International Nomenclature of Cosmetic Ingredients) names from the following raw text extracted from a product label or document.

Please analyze the text and return ONLY a JSON array of INCI names in the exact format shown below.

Requirements:
1. Extract only valid INCI ingredient names
2. Remove any non-ingredient text, headers, or descriptions
3. Clean up formatting (remove extra spaces, punctuation)
4. Return as a simple JSON array of strings
5. If no valid ingredients found, return empty array []

Example output format:
["Water", "Glycerin", "Sodium Hyaluronate", "Hyaluronic Acid"]

Raw text to analyze:
{raw_text}

Return only the JSON array:"""

            # Call Claude API
            response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Extract response content
            claude_response = response.content[0].text.strip()
            
            # Try to parse JSON response
            try:
                # Clean up response to extract just the JSON part
                if '[' in claude_response and ']' in claude_response:
                    start = claude_response.find('[')
                    end = claude_response.rfind(']') + 1
                    json_str = claude_response[start:end]
                    
                    ingredients = json.loads(json_str)
                    
                    # Validate that we got a list of strings
                    if isinstance(ingredients, list) and all(isinstance(item, str) for item in ingredients):
                        return ingredients
                    else:
                        raise Exception("Invalid response format from Claude")
                else:
                    raise Exception("No JSON array found in Claude response")
                    
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse Claude response as JSON: {str(e)}")
                
        except Exception as e:
            raise Exception(f"Failed to extract ingredients with Claude: {str(e)}")
    
    async def process_input(self, input_type: str, **kwargs) -> Tuple[List[str], str]:
        """Main method to process different input types and extract ingredients"""
        try:
            extracted_text = ""
            
            if input_type == "text":
                # Direct text input
                inci_names = kwargs.get('inci_names', [])
                extracted_text = "\n".join(inci_names)
                
            elif input_type == "pdf":
                # PDF file input
                pdf_file = kwargs.get('pdf_file')
                if not pdf_file:
                    raise Exception("PDF file is required for PDF input type")
                
                pdf_data = await pdf_file.read()
                extracted_text = await self.extract_text_from_pdf(pdf_data)
                
            elif input_type == "image":
                # Image file input
                image_file = kwargs.get('image_file')
                if not image_file:
                    raise Exception("Image file is required for image input type")
                
                image_data = await image_file.read()
                extracted_text = await self.extract_text_from_image(image_data)
                
            elif input_type == "camera":
                # Camera image input
                camera_image = kwargs.get('camera_image')
                if not camera_image:
                    raise Exception("Camera image data is required for camera input type")
                
                extracted_text = await self.extract_text_from_camera(camera_image)
                
            else:
                raise Exception(f"Unsupported input type: {input_type}")
            
            # Use Claude API to extract and format ingredients from the raw text
            ingredients = await self.extract_ingredients_with_claude(extracted_text)
            
            if not ingredients:
                raise Exception("No valid ingredients could be extracted from the input")
            
            return ingredients, extracted_text
            
        except Exception as e:
            raise Exception(f"Failed to process input: {str(e)}")
