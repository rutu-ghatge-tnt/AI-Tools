def build_prompt(ocr_text: str) -> str:
    return f"""
You are an expert product info extractor.

Given the following OCR text from a skincare or supplement product label, extract all available info and return a single JSON object only with these fields:

- productName (string)
- genericName (string)
- packSize (number)
- packSizeUnit (string)
- keyIngredients (list of strings)
- tags (list of strings)
- claims (list of strings)
- ingredients (list of strings)
- marketedBy (string)
- manufacturedBy (string)
- website (string)
- manufacturingDate (ISO date string, YYYY-MM-DD)
- contactNumber (string)
- capturedBy (string)
- description (string)
- mrp (number)
- productCategory (string)
- mrpPerUnit (number)
- shelfLife (string)
- licenseNo (string)
- customerCareNumber (string)
- customerCareEmail (string)

If any field is not present in the text, omit it from the JSON.

OCR Text:
---
{ocr_text}
---
Return only valid JSON with no explanations.
"""
