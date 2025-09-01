# app/ai_ingredient_intelligence/api/formulation_report.py
import io
import datetime
import os
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from typing import List
from openai import OpenAI
# from weasyprint import HTML  # Temporarily commented out due to dependency issues
from jinja2 import Environment, FileSystemLoader

router = APIRouter(tags=["Formulation Reports"])

class FormulationReportRequest(BaseModel):
    inciList: List[str]

# Initialize OpenAI client with environment variable
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are FormulationLooker 2.0, a professional cosmetic formulation analyst.
CRITICAL: You MUST generate meaningful content for EVERY table cell. NO EMPTY CELLS ALLOWED.

Generate a clean, structured report with these exact sections:

1) Submitted INCI List
   - List each ingredient on a separate line
   - One ingredient per line, no dashes or bullets
   - Keep it simple and clean

2) Matched vs Unmatched Ingredients
   - Create a table with: Ingredient | Status | Notes
   - Use pipe (|) separators
   - Status: "MATCHED" or "UNMATCHED"
   - Notes: REQUIRED for every ingredient. Examples:
     * Aqua: "Primary solvent, base ingredient"
     * Glycerin: "Humectant, skin conditioning agent"
     * Niacinamide: "Vitamin B3, brightening active"
     * Hyaluronic Acid: "Hydrating polymer, moisture retention"
     * Salicylic Acid: "Beta hydroxy acid, exfoliant"
     * Benzoyl Peroxide: "Antimicrobial, acne treatment"
   - FAILURE TO PROVIDE NOTES WILL RESULT IN INCOMPLETE REPORT

3) Actives & Excipients Table
   - Create a table with: Ingredient | Category | Function | Concentration Range
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

4) Actives % vs Inactives %
   - Simple percentage breakdown

5) Compliance Panel
   - Create a table with: Regulation | Status | Requirements
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

6) Preservative Efficacy Check
   - Create a table with: Preservative | Efficacy | pH Range | Stability
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

7) Risk Panel
   - Create a table with: Risk Factor | Level | Mitigation
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

8) Cumulative Benefit Panel
   - Create a table with: Benefit | Mechanism | Evidence Level
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

9) Claim Panel
   - Create a table with: Claim | Support Level | Evidence
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

10) Recommended pH Range
    - Clear pH recommendations

MANDATORY RULES:
- Use pipe (|) for all table separators
- Start each section with the exact header (e.g., "1) Submitted INCI List")
- Put ingredients on separate lines, no inline text
- No dashes, bullets, or extra formatting
- Keep tables consistent with same number of columns
- Use clear, concise language
- NEVER leave any table cell empty - always provide relevant information
- For the Notes column, provide brief but meaningful descriptions
- If you leave any cell empty, the report is incomplete and unusable
"""

# store last report text in-memory (simple demo)
last_report = {"text": ""}

def validate_report_content(report_text: str) -> bool:
    """Validate that the report has proper content in all table cells"""
    # Check for empty table cells
    if "| |" in report_text or "||" in report_text:
        return False
    
    # Check if the matched vs unmatched table has notes
    if "2) Matched vs Unmatched Ingredients" in report_text:
        # Look for the table structure
        lines = report_text.split('\n')
        in_table = False
        has_notes = False
        
        for line in lines:
            if "2) Matched vs Unmatched Ingredients" in line:
                in_table = True
                continue
            
            if in_table and line.strip() and "|" in line:
                cells = line.split('|')
                if len(cells) >= 3:  # Should have Ingredient | Status | Notes
                    notes_cell = cells[2].strip()
                    if notes_cell and notes_cell not in ['Notes', '']:
                        has_notes = True
                        break
        
        return has_notes
    
    return True

@router.post("/formulation-report")
async def generate_report(payload: FormulationReportRequest, request: Request):
    try:
        inci_str = ", ".join(payload.inciList)

        # 🔹 Generate report text via OpenAI
        completion = client.completions.create(
            model="gpt-3.5-turbo-instruct",
            prompt=f"{SYSTEM_PROMPT}\n\nGenerate report for this INCI list:\n{inci_str}\n\nREMEMBER: Every table cell must have content. NO EMPTY CELLS!",
            temperature=0.1,  # Lower temperature for more consistent output
            max_tokens=2500   # Increase tokens for more detailed content
        )
        report_text = completion.choices[0].text
        
        # 🔹 Validate and fix empty notes if needed
        max_retries = 3
        retry_count = 0
        
        while not validate_report_content(report_text) and retry_count < max_retries:
            retry_count += 1
            print(f"⚠️ Report validation failed (attempt {retry_count}/{max_retries}). Regenerating...")
            
            # Regenerate with stronger prompt
            retry_prompt = f"{SYSTEM_PROMPT}\n\nCRITICAL: The previous response had empty table cells or missing notes. Regenerate with NO EMPTY CELLS and MEANINGFUL NOTES.\n\nGenerate report for this INCI list:\n{inci_str}\n\nEVERY SINGLE TABLE CELL MUST CONTAIN MEANINGFUL TEXT!\n\nExample of proper notes:\nAqua: Primary solvent, base ingredient\nGlycerin: Humectant, skin conditioning agent\nNiacinamide: Vitamin B3, brightening active"
            
            retry_completion = client.completions.create(
                model="gpt-3.5-turbo-instruct",
                prompt=retry_prompt,
                temperature=0.0,  # Zero temperature for maximum consistency
                max_tokens=2500
            )
            report_text = retry_completion.choices[0].text
        
        if not validate_report_content(report_text):
            print("❌ Failed to generate valid report after multiple attempts")
        
        last_report["text"] = report_text

        # 🔹 Render as HTML (with Download PDF button)
        # Use absolute path for templates
        template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
        env = Environment(loader=FileSystemLoader(template_dir))
        
        try:
            template = env.get_template("formulation_report.html")
        except Exception as e:
            # If template not found, return JSON response instead
            return {
                "title": "FormulationLooker 2.0 – Cumulative Report (Formulator Edition)",
                "date": datetime.date.today().strftime("%d %b %Y"),
                "report_text": report_text,
                "message": "HTML template not found, returning JSON format"
            }

        html_content = template.render({
            "title": "FormulationLooker 2.0 – Cumulative Report (Formulator Edition)",
            "date": datetime.date.today().strftime("%d %b %Y"),
            "report_text": report_text,
            "pdf_url": str(request.base_url) + "api/formulation-report/pdf"
        })

        return Response(content=html_content, media_type="text/html")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/formulation-report/pdf")
async def download_pdf():
    """Download the last generated report as PDF"""
    if not last_report["text"]:
        raise HTTPException(status_code=404, detail="No report generated yet")

    try:
        # Temporarily return error message instead of PDF generation
        raise HTTPException(
            status_code=503, 
            detail="PDF generation temporarily unavailable due to WeasyPrint dependency issues. Please use the HTML endpoint instead."
        )
        
        # Original PDF generation code (commented out):
        # template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
        # env = Environment(loader=FileSystemLoader(template_dir))
        # template = env.get_template("formulation_report.html")
        # 
        # html_content = template.render({
        #     "title": "FormulationLooker 2.0 – Cumulative Report (Formulator Edition)",
        #     "date": datetime.date.today().strftime("%d %b %Y"),
        #     "report_text": last_report["text"],
        #     "pdf_url": "#"
        # })
        # 
        # pdf_io = io.BytesIO()
        # HTML(string=html_content).write_pdf(pdf_io)
        # return Response(
        #     content=pdf_io.getvalue(),
        #     media_type="application/pdf",
        #     headers={"Content-Disposition": "attachment; filename=formulation_report.pdf"}
        # )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@router.get("/formulation-report/status")
async def get_report_status():
    """Get the status of the last generated report"""
    return {
        "has_report": bool(last_report["text"]),
        "report_length": len(last_report["text"]) if last_report["text"] else 0,
        "last_generated": "Available" if last_report["text"] else "No report generated yet"
    }
