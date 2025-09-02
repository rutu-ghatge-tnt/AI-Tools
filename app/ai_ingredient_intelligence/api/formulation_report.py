# app/ai_ingredient_intelligence/api/formulation_report.py
import io
import datetime
import os
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from typing import List
from openai import OpenAI
import anthropic
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from jinja2 import Environment, FileSystemLoader

router = APIRouter(tags=["Formulation Reports"])

class FormulationReportRequest(BaseModel):
    inciList: List[str]

# Initialize OpenAI and Claude clients
openai_api_key = os.getenv("OPENAI_API_KEY")
claude_api_key = os.getenv("CLAUDE_API_KEY")

if not openai_api_key:
    print("⚠️ Warning: OPENAI_API_KEY environment variable not set")
if not claude_api_key:
    print("⚠️ Warning: CLAUDE_API_KEY environment variable not set")

openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None
claude_client = anthropic.Anthropic(api_key=claude_api_key) if claude_api_key else None

SYSTEM_PROMPT = """You are FormulationLooker 1.0, a professional cosmetic formulation analyst.
CRITICAL: You MUST generate meaningful content for EVERY table cell. NO EMPTY CELLS ALLOWED.
CRITICAL: Do NOT include any introductory text like "I'll analyze" or "Let me analyze" - start directly with the report sections.
CRITICAL: You MUST include ALL ingredients provided in the INCI list. Do NOT skip any ingredients.

Generate a clean, structured report with these exact sections:

1) Submitted INCI List
   - List EVERY SINGLE ingredient on a separate line
   - One ingredient per line, no dashes or bullets
   - Include ALL ingredients provided - do not skip any
   - Keep it simple and clean

2) Matched vs Unmatched Ingredients
   - Create a table with: Ingredient | Status | Notes
   - Use pipe (|) separators
   - Status: "MATCHED" or "UNMATCHED"
   - MATCHED: Common, well-known cosmetic ingredients with established functions
   - UNMATCHED: Rare, proprietary, or unclear ingredients that need further research
   - Examples of UNMATCHED: Proprietary blends, trade names, unclear chemical names, very rare ingredients
   - Notes: REQUIRED for every ingredient. Examples:
     * Aqua: "Primary solvent, base ingredient"
     * Glycerin: "Humectant, skin conditioning agent"
     * Niacinamide: "Vitamin B3, brightening active"
     * Hyaluronic Acid: "Hydrating polymer, moisture retention"
     * Salicylic Acid: "Beta hydroxy acid, exfoliant"
     * Benzoyl Peroxide: "Antimicrobial, acne treatment"
     * Proprietary Blend XYZ: "Unknown proprietary ingredient, requires manufacturer clarification"
   - FAILURE TO PROVIDE NOTES WILL RESULT IN INCOMPLETE REPORT
   - INCLUDE ALL INGREDIENTS FROM THE INCI LIST - DO NOT SKIP ANY
   - IMPORTANT: Mark at least 10-20% of ingredients as UNMATCHED if they are rare, proprietary, or unclear

3) Actives & Excipients Table
   - Create a table with: Ingredient | Category | Function | Concentration Range
   - Use pipe (|) separators
   - Fill ALL columns with relevant information
   - INCLUDE ALL INGREDIENTS - categorize each one appropriately

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
- DO NOT include any introductory phrases like "I'll analyze", "Let me analyze", "I will analyze" - start directly with "1) Submitted INCI List"
- MOST IMPORTANT: INCLUDE ALL INGREDIENTS PROVIDED - DO NOT SKIP ANY INGREDIENT FROM THE INCI LIST
"""

# store last report text in-memory (simple demo)
last_report = {"text": ""}

def validate_report_content(report_text: str, expected_ingredient_count: int = None) -> bool:
    """Validate that the report has proper content in all table cells and includes all ingredients"""
    # Check for empty table cells
    if "| |" in report_text or "||" in report_text:
        return False
    
    # Check if the matched vs unmatched table has notes
    if "2) Matched vs Unmatched Ingredients" in report_text:
        # Look for the table structure
        lines = report_text.split('\n')
        in_table = False
        has_notes = False
        ingredient_count = 0
        matched_count = 0
        unmatched_count = 0
        
        for line in lines:
            if "2) Matched vs Unmatched Ingredients" in line:
                in_table = True
                continue
            
            if in_table and line.strip() and "|" in line:
                cells = line.split('|')
                if len(cells) >= 3:  # Should have Ingredient | Status | Notes
                    notes_cell = cells[2].strip()
                    status_cell = cells[1].strip().upper() if len(cells) > 1 else ""
                    
                    if notes_cell and notes_cell not in ['Notes', '']:
                        has_notes = True
                        ingredient_count += 1
                        
                        # Count matched vs unmatched
                        if 'MATCHED' in status_cell:
                            matched_count += 1
                        elif 'UNMATCHED' in status_cell:
                            unmatched_count += 1
                            
                elif len(cells) >= 1 and cells[0].strip() and cells[0].strip() not in ['Ingredient']:
                    # Count ingredient rows (even if notes are missing)
                    ingredient_count += 1
            
            # Stop counting when we hit the next section
            if in_table and line.strip() and line.startswith(('3)', '4)', '5)', '6)', '7)', '8)', '9)', '10)')):
                break
        
        # If we have an expected count, check if we're close
        if expected_ingredient_count and ingredient_count < expected_ingredient_count * 0.8:
            print(f"⚠️ Warning: Only found {ingredient_count} ingredients in report, expected around {expected_ingredient_count}")
            return False
        
        # Check if we have both matched and unmatched ingredients
        if ingredient_count > 0 and unmatched_count == 0:
            print(f"⚠️ Warning: All ingredients marked as MATCHED, but some should be UNMATCHED. Found {matched_count} matched, {unmatched_count} unmatched")
            return False
        
        return has_notes
    
    return True

def clean_ai_response(text: str) -> str:
    """Remove unwanted introductory text from AI responses"""
    # Remove common introductory phrases
    unwanted_phrases = [
        "I'll analyze this",
        "Let me analyze this", 
        "I will analyze this",
        "I'll analyze the",
        "Let me analyze the",
        "I will analyze the",
        "I'll analyze your",
        "Let me analyze your",
        "I will analyze your"
    ]
    
    for phrase in unwanted_phrases:
        if text.startswith(phrase):
            # Find the first section header
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith('1) Submitted INCI List'):
                    text = '\n'.join(lines[i:])
                    break
    
    return text.strip()

def generate_pdf_from_text(report_text: str) -> bytes:
    """Generate PDF from report text using reportlab"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Create custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#007bff')
    )
    
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.HexColor('#007bff')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        alignment=TA_JUSTIFY
    )
    
    # Build the story (content)
    story = []
    
    # Title
    story.append(Paragraph("FormulationLooker 1.0", title_style))
    story.append(Paragraph("Professional Cosmetic Formulation Analysis", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Parse the report text
    lines = report_text.split('\n')
    current_table = []
    in_table = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for section headers
        if line.startswith(('1)', '2)', '3)', '4)', '5)', '6)', '7)', '8)', '9)', '10)')):
            # End any current table
            if in_table and current_table:
                story.append(create_table_from_data(current_table))
                current_table = []
                in_table = False
            
            story.append(Paragraph(line, header_style))
            
        # Check for table rows (containing |)
        elif '|' in line and line.count('|') >= 2:
            if not in_table:
                in_table = True
                current_table = []
            
            # Split by | and clean up
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            if cells:
                current_table.append(cells)
        
        # Regular text lines
        else:
            # End any current table
            if in_table and current_table:
                story.append(create_table_from_data(current_table))
                current_table = []
                in_table = False
            
            # Check if it's an ingredient (simple heuristic)
            if (line and len(line) < 100 and 
                not line.startswith(('Ingredient', 'Status', 'Notes', 'Category', 'Function')) and
                any(keyword in line for keyword in ['Aqua', 'Water', 'Glycerin', 'Acid', 'Oil', 'Extract', 'Alcohol', 'Ester'])):
                # Format as ingredient tag
                story.append(Paragraph(f"<b>{line}</b>", normal_style))
            else:
                story.append(Paragraph(line, normal_style))
    
    # Handle any remaining table
    if in_table and current_table:
        story.append(create_table_from_data(current_table))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def create_table_from_data(table_data):
    """Create a formatted table from data"""
    if not table_data:
        return Spacer(1, 12)
    
    # Create table with proper styling
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table

async def generate_report_text(inci_str: str) -> str:
    """Generate report text using OpenAI first, fallback to Claude if OpenAI fails"""
    
    # Try OpenAI first
    if openai_client:
        try:
            print("🔄 Attempting to generate report with OpenAI...")
            completion = openai_client.completions.create(
                model="gpt-5",
                prompt=f"{SYSTEM_PROMPT}\n\nGenerate report for this INCI list:\n{inci_str}\n\nREMEMBER: Every table cell must have content. NO EMPTY CELLS!",
                temperature=0.1,
                max_tokens=2500
            )
            report_text = completion.choices[0].text
            report_text = clean_ai_response(report_text)
            print("✅ Report generated successfully with OpenAI")
            return report_text
            
        except Exception as e:
            print(f"❌ OpenAI failed: {type(e).__name__}: {e}")
            if "quota" in str(e).lower() or "rate" in str(e).lower():
                print("🔄 OpenAI quota exceeded, falling back to Claude...")
            else:
                print("🔄 OpenAI error, falling back to Claude...")
    
    # Fallback to Claude
    if claude_client:
        try:
            print("🔄 Attempting to generate report with Claude...")
            response = claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": f"{SYSTEM_PROMPT}\n\nGenerate report for this INCI list:\n{inci_str}\n\nREMEMBER: Every table cell must have content. NO EMPTY CELLS!"
                    }
                ]
            )
            report_text = response.content[0].text
            report_text = clean_ai_response(report_text)
            print("✅ Report generated successfully with Claude")
            return report_text
            
        except Exception as e:
            print(f"❌ Claude also failed: {type(e).__name__}: {e}")
            raise HTTPException(status_code=500, detail=f"Both OpenAI and Claude failed. Claude error: {str(e)}")
    
    # If both fail
    raise HTTPException(status_code=500, detail="No AI service available. Please check your API keys.")

@router.post("/formulation-report")
async def generate_report(payload: FormulationReportRequest, request: Request):
    try:
        inci_str = ", ".join(payload.inciList)

        # 🔹 Generate report text using OpenAI or Claude fallback
        report_text = await generate_report_text(inci_str)
        
        # 🔹 Validate and fix empty notes if needed
        max_retries = 3
        retry_count = 0
        ingredient_count = len(payload.inciList)
        
        while not validate_report_content(report_text, ingredient_count) and retry_count < max_retries:
            retry_count += 1
            print(f"⚠️ Report validation failed (attempt {retry_count}/{max_retries}). Regenerating...")
            
            # Regenerate with stronger prompt
            retry_prompt = f"{SYSTEM_PROMPT}\n\nCRITICAL: The previous response had empty table cells, missing notes, missing ingredients, or no UNMATCHED ingredients. Regenerate with NO EMPTY CELLS, MEANINGFUL NOTES, ALL INGREDIENTS INCLUDED, and SOME INGREDIENTS MARKED AS UNMATCHED.\n\nGenerate report for this INCI list:\n{inci_str}\n\nEVERY SINGLE TABLE CELL MUST CONTAIN MEANINGFUL TEXT!\nINCLUDE ALL {ingredient_count} INGREDIENTS - DO NOT SKIP ANY!\nMARK SOME INGREDIENTS AS UNMATCHED - NOT ALL CAN BE MATCHED!\n\nExample of proper notes:\nAqua: Primary solvent, base ingredient\nGlycerin: Humectant, skin conditioning agent\nNiacinamide: Vitamin B3, brightening active\nProprietary Blend XYZ: Unknown proprietary ingredient, requires manufacturer clarification"
            
            # Try to regenerate with the same service that worked
            if openai_client and "OpenAI" in str(report_text):
                try:
                    retry_completion = openai_client.completions.create(
                        model="gpt-5",
                        prompt=retry_prompt,
                        temperature=0.0,
                        max_tokens=2500
                    )
                    report_text = retry_completion.choices[0].text
                except:
                    # If OpenAI fails on retry, try Claude
                    if claude_client:
                        retry_response = claude_client.messages.create(
                            model="claude-3-5-sonnet-20241022",
                            max_tokens=4000,
                            temperature=0.0,
                            messages=[{"role": "user", "content": retry_prompt}]
                        )
                        report_text = retry_response.content[0].text
            elif claude_client:
                try:
                    retry_response = claude_client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=4000,
                        temperature=0.0,
                        messages=[{"role": "user", "content": retry_prompt}]
                    )
                    report_text = retry_response.content[0].text
                except:
                    # If Claude fails on retry, try OpenAI
                    if openai_client:
                        retry_completion = openai_client.completions.create(
                            model="gpt-5",
                            prompt=retry_prompt,
                            temperature=0.0,
                            max_tokens=2500
                        )
                        report_text = retry_completion.choices[0].text
        
        if not validate_report_content(report_text):
            print("❌ Failed to generate valid report after multiple attempts")
        
        last_report["text"] = report_text

        # 🔹 Render as HTML (with Download PDF button)
        # Use absolute path for templates - check both possible locations
        template_dir1 = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
        template_dir2 = os.path.join(os.path.dirname(__file__), "..", "..", "..", "templates")
        
        # Try the first path, then the second
        if os.path.exists(template_dir1):
            template_dir = template_dir1
        elif os.path.exists(template_dir2):
            template_dir = template_dir2
        else:
            # Fallback to current directory
            template_dir = os.path.dirname(__file__)
        
        env = Environment(loader=FileSystemLoader(template_dir))
        
        try:
            template = env.get_template("formulation_report.html")
        except Exception as e:
            # If template not found, return JSON response instead
            return {
                "title": "FormulationLooker 1.0 – Cumulative Report (Formulator Edition)",
                "date": datetime.date.today().strftime("%d %b %Y"),
                "report_text": report_text,
                "message": "HTML template not found, returning JSON format"
            }

        html_content = template.render({
            "title": "FormulationLooker 1.0 – Cumulative Report (Formulator Edition)",
            "date": datetime.date.today().strftime("%d %b %Y"),
            "report_text": report_text,
            "pdf_url": str(request.base_url) + "api/formulation-report/pdf"
        })

        return Response(content=html_content, media_type="text/html")

    except Exception as e:
        print(f"❌ Error in generate_report: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/formulation-report/pdf")
async def download_pdf():
    """Download the last generated report as PDF"""
    if not last_report["text"]:
        raise HTTPException(status_code=404, detail="No report generated yet")

    try:
        # Generate PDF using reportlab
        pdf_content = generate_pdf_from_text(last_report["text"])
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=formulation_report.pdf"}
        )
        
    except Exception as e:
        print(f"❌ PDF generation failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@router.get("/formulation-report/status")
async def get_report_status():
    """Get the status of the last generated report"""
    return {
        "has_report": bool(last_report["text"]),
        "report_length": len(last_report["text"]) if last_report["text"] else 0,
        "last_generated": "Available" if last_report["text"] else "No report generated yet"
    }
