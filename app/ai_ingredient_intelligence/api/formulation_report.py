# app/ai_ingredient_intelligence/api/formulation_report.py
import io
import datetime
import os
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from typing import List, Optional, Dict
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
    brandedIngredients: List[str] = []  # List of branded ingredient names from analyze_inci
    notBrandedIngredients: List[str] = []  # List of not branded ingredient names from analyze_inci
    bisCautions: Optional[Dict[str, List[str]]] = None  # BIS cautions from analyze_inci

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
CRITICAL: In the report you MUST include ALL ingredients provided in the INCI list. Do NOT skip any ingredients.

Generate a clean, structured report with these exact sections:

1) Submitted INCI List
   - List EVERY SINGLE ingredient on a separate line
   - One ingredient per line, no dashes or bullets
   - Include ALL ingredients provided - do not skip any
   - Keep it simple and clean

2) Analysis
   - Create a table with: Ingredient | Status | Category | Functions/Notes | BIS Cautions
   - Use pipe (|) separators
   - Status: "BRANDED" or "NOT BRANDED"
     * BRANDED: Ingredients that are part of proprietary branded ingredient systems or trade name products
     * NOT BRANDED: Standard, non-proprietary cosmetic ingredients (INCI names)
     * Examples of BRANDED: Proprietary blends, trade names, branded actives, supplier-specific formulations
     * Examples of NOT BRANDED: Standard INCI names like Aqua, Glycerin, Niacinamide, Hyaluronic Acid
   - Category: "ACTIVE" or "INACTIVE"
     * ACTIVE: Ingredients with therapeutic, functional, or active properties (e.g., Niacinamide, Salicylic Acid, Retinol)
     * INACTIVE: Excipients, carriers, solvents, and supporting ingredients (e.g., Aqua, Glycerin, Emulsifiers)
   - Functions/Notes: REQUIRED for every ingredient. Combine function and notes in one column. Examples:
     * Aqua: "Primary solvent, base ingredient"
     * Glycerin: "Humectant, skin conditioning agent"
     * Niacinamide: "Vitamin B3, brightening active, anti-inflammatory"
     * Hyaluronic Acid: "Hydrating polymer, moisture retention"
     * Salicylic Acid: "Beta hydroxy acid, exfoliant, pore-clearing"
     * Benzoyl Peroxide: "Antimicrobial, acne treatment"
     * Proprietary Blend XYZ: "Unknown proprietary ingredient, requires manufacturer clarification"
   - BIS Cautions: For each ingredient, if BIS cautions are provided in the context, list them here. If no BIS cautions are provided for an ingredient, write "no bis cautions"
   - FAILURE TO PROVIDE ALL COLUMNS WILL RESULT IN INCOMPLETE REPORT
   - INCLUDE ALL INGREDIENTS FROM THE INCI LIST - DO NOT SKIP ANY
   - IMPORTANT: Mark ingredients as BRANDED if they are proprietary/trade name products, otherwise mark as NOT BRANDED
   - IMPORTANT: Categorize each ingredient as ACTIVE or INACTIVE appropriately

3) Compliance Panel
   - Create a table with: Regulation | Status | Requirements
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

4) Preservative Efficacy Check
   - Create a table with: Preservative | Efficacy | pH Range | Stability
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

5) Risk Panel
   - Create a table with: Risk Factor | Level | Mitigation
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

6) Cumulative Benefit Panel
   - Create a table with: Benefit | Mechanism | Evidence Level
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

7) Claim Panel
   - Create a table with: Claim | Support Level | Evidence
   - Use pipe (|) separators
   - Fill ALL columns with relevant information

8) Recommended pH Range
    - Clear pH recommendations

MANDATORY RULES:
- Use pipe (|) for all table separators
- Start each section with the exact header (e.g., "1) Submitted INCI List")
- Put ingredients on separate lines, no inline text
- No dashes, bullets, or extra formatting
- Keep tables consistent with same number of columns
- Use clear, concise language
- NEVER leave any table cell empty - always provide relevant information
- For the Functions/Notes column, provide brief but meaningful descriptions combining function and notes
- For the BIS Cautions column, if cautions are provided, list them; if not, write "no bis cautions"
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
    
    # Check if the Analysis table has all required columns
    if "2) Analysis" in report_text or "2) Branded vs Not Branded Ingredients" in report_text or "2) Matched vs Unmatched Ingredients" in report_text:
        # Look for the table structure
        lines = report_text.split('\n')
        in_table = False
        has_notes = False
        ingredient_count = 0
        branded_count = 0
        not_branded_count = 0
        
        for line in lines:
            if "2) Analysis" in line or "2) Branded vs Not Branded Ingredients" in line or "2) Matched vs Unmatched Ingredients" in line:
                in_table = True
                continue
            
            if in_table and line.strip() and "|" in line:
                cells = line.split('|')
                # New format: Ingredient | Status | Category | Functions/Notes | BIS Cautions (5 columns)
                # Old format: Ingredient | Status | Notes (3 columns) - for backward compatibility
                if len(cells) >= 3:  # Should have at least Ingredient | Status | Notes or more
                    # Check for Functions/Notes column (could be 4th column in new format or 3rd in old)
                    notes_cell = ""
                    if len(cells) >= 4:
                        notes_cell = cells[3].strip()  # Functions/Notes in new format
                    else:
                        notes_cell = cells[2].strip()  # Notes in old format
                    
                    status_cell = cells[1].strip().upper() if len(cells) > 1 else ""
                    
                    if notes_cell and notes_cell not in ['Notes', 'Functions/Notes', '']:
                        has_notes = True
                        ingredient_count += 1
                        
                        # Count branded vs not branded (also check for old MATCHED/UNMATCHED for backward compatibility)
                        if 'BRANDED' in status_cell or 'MATCHED' in status_cell:
                            branded_count += 1
                        elif 'NOT BRANDED' in status_cell or 'UNMATCHED' in status_cell:
                            not_branded_count += 1
                            
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
        
        # It's okay if all are one category - just check that we have notes
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

async def generate_report_text(
    inci_str: str, 
    branded_ingredients: Optional[List[str]] = None, 
    not_branded_ingredients: Optional[List[str]] = None,
    bis_cautions: Optional[Dict[str, List[str]]] = None
) -> str:
    """Generate report text using Claude first, fallback to OpenAI if Claude fails"""
    
    # Build categorization context if provided
    categorization_info = ""
    if branded_ingredients or not_branded_ingredients:
        categorization_info = "\n\nINGREDIENT CATEGORIZATION FROM DATABASE ANALYSIS:\n"
        if branded_ingredients:
            categorization_info += f"- BRANDED Ingredients (found in database): {', '.join(branded_ingredients)}\n"
        if not_branded_ingredients:
            categorization_info += f"- NOT BRANDED Ingredients (not found in database): {', '.join(not_branded_ingredients)}\n"
        categorization_info += "\nUse this categorization information to accurately mark ingredients as BRANDED or NOT BRANDED in the report.\n"
    
    # Build BIS cautions context if provided
    bis_cautions_info = ""
    if bis_cautions:
        bis_cautions_info = "\n\nBUREAU OF INDIAN STANDARDS (BIS) CAUTIONS & REGULATORY NOTES:\n"
        bis_cautions_info += "=" * 50 + "\n"
        for ingredient, cautions in bis_cautions.items():
            bis_cautions_info += f"\n{ingredient}:\n"
            for i, caution in enumerate(cautions, 1):
                bis_cautions_info += f"  {i}. {caution}\n"
        bis_cautions_info += "\nIMPORTANT: Include these BIS cautions in section 2) Analysis table, in the 'BIS Cautions' column. For each ingredient that has BIS cautions, list them in that column. For ingredients without BIS cautions, write 'no bis cautions'.\n"
    
    user_prompt = f"Generate report for this INCI list:\n{inci_str}{categorization_info}{bis_cautions_info}\n\nREMEMBER: Every table cell must have content. NO EMPTY CELLS!"
    
    # Try Claude first
    if claude_client:
        try:
            print("🔄 Attempting to generate report with Claude...")
            response = claude_client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": f"{SYSTEM_PROMPT}\n\n{user_prompt}"
                    }
                ]
            )
            report_text = response.content[0].text
            report_text = clean_ai_response(report_text)
            print("✅ Report generated successfully with Claude")
            return report_text
            
        except Exception as e:
            print(f"❌ Claude failed: {type(e).__name__}: {e}")
            if "quota" in str(e).lower() or "rate" in str(e).lower():
                print("🔄 Claude quota exceeded, falling back to OpenAI...")
            else:
                print("🔄 Claude error, falling back to OpenAI...")
    
    # Fallback to OpenAI
    if openai_client:
        try:
            print("🔄 Attempting to generate report with OpenAI...")
            # Remove temperature parameter as GPT-5 only supports default (1)
            completion = openai_client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=4000
            )
            report_text = completion.choices[0].message.content
            report_text = clean_ai_response(report_text)
            print("✅ Report generated successfully with OpenAI")
            return report_text
            
        except Exception as e:
            print(f"❌ OpenAI also failed: {type(e).__name__}: {e}")
            raise HTTPException(status_code=500, detail=f"Both Claude and OpenAI failed. OpenAI error: {str(e)}")
    
    # If both fail
    raise HTTPException(status_code=500, detail="No AI service available. Please check your API keys.")

@router.post("/formulation-report")
async def generate_report(payload: FormulationReportRequest, request: Request):
    try:
        inci_str = ", ".join(payload.inciList)

        # 🔹 Generate report text using OpenAI or Claude fallback with categorization info and BIS cautions
        report_text = await generate_report_text(
            inci_str, 
            branded_ingredients=payload.brandedIngredients,
            not_branded_ingredients=payload.notBrandedIngredients,
            bis_cautions=payload.bisCautions
        )
        
        # 🔹 Validate and fix empty notes if needed
        max_retries = 3
        retry_count = 0
        ingredient_count = len(payload.inciList)
        
        while not validate_report_content(report_text, ingredient_count) and retry_count < max_retries:
            retry_count += 1
            print(f"⚠️ Report validation failed (attempt {retry_count}/{max_retries}). Regenerating...")
            
            # Build categorization info for retry
            retry_categorization = ""
            if payload.brandedIngredients or payload.notBrandedIngredients:
                retry_categorization = "\n\nINGREDIENT CATEGORIZATION FROM DATABASE ANALYSIS:\n"
                if payload.brandedIngredients:
                    retry_categorization += f"- BRANDED Ingredients (found in database): {', '.join(payload.brandedIngredients)}\n"
                if payload.notBrandedIngredients:
                    retry_categorization += f"- NOT BRANDED Ingredients (not found in database): {', '.join(payload.notBrandedIngredients)}\n"
                retry_categorization += "\nUse this categorization information to accurately mark ingredients as BRANDED or NOT BRANDED in the report.\n"
            
            # Build BIS cautions info for retry
            retry_bis_cautions = ""
            if payload.bisCautions:
                retry_bis_cautions = "\n\nBUREAU OF INDIAN STANDARDS (BIS) CAUTIONS & REGULATORY NOTES:\n"
                retry_bis_cautions += "=" * 50 + "\n"
                for ingredient, cautions in payload.bisCautions.items():
                    retry_bis_cautions += f"\n{ingredient}:\n"
                    for i, caution in enumerate(cautions, 1):
                        retry_bis_cautions += f"  {i}. {caution}\n"
                retry_bis_cautions += "\nIMPORTANT: Include these BIS cautions in section 2) Analysis table, in the 'BIS Cautions' column. For each ingredient that has BIS cautions, list them in that column. For ingredients without BIS cautions, write 'no bis cautions'.\n"
            
            # Regenerate with stronger prompt
            retry_prompt = f"{SYSTEM_PROMPT}\n\nCRITICAL: The previous response had empty table cells, missing notes, or missing ingredients. Regenerate with NO EMPTY CELLS, MEANINGFUL NOTES, ALL INGREDIENTS INCLUDED.\n\nGenerate report for this INCI list:\n{inci_str}{retry_categorization}{retry_bis_cautions}\n\nEVERY SINGLE TABLE CELL MUST CONTAIN MEANINGFUL TEXT!\nINCLUDE ALL {ingredient_count} INGREDIENTS - DO NOT SKIP ANY!\n\nExample of proper notes:\nAqua: Primary solvent, base ingredient\nGlycerin: Humectant, skin conditioning agent\nNiacinamide: Vitamin B3, brightening active\nProprietary Blend XYZ: Unknown proprietary ingredient, requires manufacturer clarification"
            
            # Try to regenerate with Claude first (same as initial generation)
            if claude_client:
                try:
                    retry_response = claude_client.messages.create(
                        model="claude-3-opus-20240229",
                        max_tokens=4000,
                        temperature=0.0,
                        messages=[{"role": "user", "content": retry_prompt}]
                    )
                    report_text = retry_response.content[0].text
                except:
                    # If Claude fails on retry, try OpenAI
                    if openai_client:
                        retry_completion = openai_client.chat.completions.create(
                            model="gpt-5",
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": retry_prompt.split("\n\n")[-1] if "\n\n" in retry_prompt else retry_prompt}
                            ],
                            max_completion_tokens=4000
                        )
                        report_text = retry_completion.choices[0].message.content
            elif openai_client:
                try:
                    retry_completion = openai_client.chat.completions.create(
                        model="gpt-5",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": retry_prompt.split("\n\n")[-1] if "\n\n" in retry_prompt else retry_prompt}
                        ],
                        max_completion_tokens=4000
                    )
                    report_text = retry_completion.choices[0].message.content
                except:
                    # If OpenAI fails on retry, try Claude
                    if claude_client:
                        retry_response = claude_client.messages.create(
                            model="claude-3-opus-20240229",
                            max_tokens=4000,
                            temperature=0.0,
                            messages=[{"role": "user", "content": retry_prompt}]
                        )
                        report_text = retry_response.content[0].text
        
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
