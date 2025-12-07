# app/ai_ingredient_intelligence/api/formulation_report.py
import io
import datetime
import os
import re
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
from app.ai_ingredient_intelligence.models.schemas import FormulationReportResponse, ReportTableRow

router = APIRouter(tags=["Formulation Reports"])

class FormulationReportRequest(BaseModel):
    inciList: List[str]
    brandedIngredients: List[str] = []  # List of branded ingredient names from analyze_inci
    notBrandedIngredients: List[str] = []  # List of not branded ingredient names from analyze_inci
    bisCautions: Optional[Dict[str, List[str]]] = None  # BIS cautions from analyze_inci
    expectedBenefits: Optional[str] = None  # Expected benefits from user input

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
CRITICAL: You MUST output ONLY structured text format (NOT HTML, NOT JSON). Use plain text with pipe (|) separators for tables.
CRITICAL: You MUST generate meaningful content for EVERY table cell. NO EMPTY CELLS ALLOWED.
CRITICAL: Do NOT include any introductory text like "I'll analyze" or "Let me analyze" - start directly with the report sections.
CRITICAL: In the report you MUST include ALL ingredients provided in the INCI list. Do NOT skip any ingredients.
CRITICAL: Do NOT split ingredient names that contain hyphens, numbers, or parentheses (e.g., "Polyacrylate Crosspolymer-6" must stay as one ingredient, not "Polyacrylate Crosspolymer" and "6"; "Citrus Sinensis (Blood Orange) Fruit Extracts" must stay as one ingredient, not split into parts).
CRITICAL: For BIS Cautions, if exact limits, percentages, or amounts are provided, you MUST include them EXACTLY as given. Do NOT use vague phrases like "see column" or "refer to table" - include the actual numbers, percentages, or limits.

Generate a clean, structured report with these exact sections:

1) Submitted INCI List
   - List EVERY SINGLE ingredient on a separate line
   - One ingredient per line, no dashes or bullets
   - Include ALL ingredients provided - do not skip any
   - Keep ingredient names intact - do NOT split names with hyphens, numbers, or parentheses (e.g., "Polyacrylate Crosspolymer-6" must stay as one line; "Citrus Sinensis (Blood Orange) Fruit Extracts" must stay as one complete line)
   - Keep it simple and clean

2) Analysis
   - Create a table with: Ingredient | Category | Functions/Notes | BIS Cautions
   - Use pipe (|) separators
   - Category: For EACH ingredient, write either "ACTIVE" or "EXCIPIENT" (singular, not plural)
     * ACTIVE: Ingredients with therapeutic, functional, or active properties (e.g., Niacinamide, Salicylic Acid, Retinol)
     * EXCIPIENT: Excipients, carriers, solvents, and supporting ingredients (e.g., Aqua, Glycerin, Emulsifiers)
   - IMPORTANT: Each row should have "ACTIVE" or "EXCIPIENT" in the Category column, NOT "ACTIVES" or "EXCIPIENTS"
   - Functions/Notes: REQUIRED for every ingredient. Combine function and notes in one column. Examples:
     * Aqua: "Primary solvent, base ingredient"
     * Glycerin: "Humectant, skin conditioning agent"
     * Niacinamide: "Vitamin B3, brightening active, anti-inflammatory"
     * Hyaluronic Acid: "Hydrating polymer, moisture retention"
     * Salicylic Acid: "Beta hydroxy acid, exfoliant, pore-clearing"
     * Benzoyl Peroxide: "Antimicrobial, acne treatment"
     * Proprietary Blend XYZ: "Unknown proprietary ingredient, requires manufacturer clarification"
   - BIS Cautions: For each ingredient, if BIS cautions are provided in the context, you MUST include ALL of them. THIS IS CRITICAL - MISSING CAUTIONS IS A SERIOUS ERROR.
     * CRITICAL: You MUST include EVERY SINGLE caution that is provided for each ingredient. If 4 cautions are provided, you MUST include all 4. If 5 are provided, include all 5. DO NOT SKIP ANY.
     * CRITICAL: Each caution must be on a SEPARATE LINE within the table cell. Use actual line breaks (newlines) between cautions.
     * CRITICAL: Number each caution starting with 1., 2., 3., 4., etc. on its own line.
     * CRITICAL: Include EXACT limits, percentages, concentrations, and amounts as provided. Copy the exact text from the provided cautions.
     * CRITICAL: Do NOT use vague phrases like "see column" or "refer to table" - include the actual numerical values.
     * CRITICAL: Do NOT combine multiple cautions into one line separated by commas or semicolons - each must be on its own line.
     * CRITICAL: Do NOT summarize or shorten cautions - include the FULL text of each caution exactly as provided.
     * CRITICAL: Do NOT skip any cautions - if 4 cautions are provided, you must include all 4. If 5 are provided, include all 5.
     * Example format within the cell (each caution on its own line):
       1. First caution with exact values (e.g., "maximum 5% w/w")
       2. Second caution with exact values (e.g., "not to exceed 2 mg/kg")
       3. Third caution with exact values
       4. Fourth caution with exact values
     * If no BIS cautions are provided for an ingredient, write "no bis cautions"
     * REMEMBER: Missing even one caution is a CRITICAL ERROR. Count the cautions provided and ensure ALL are included.
   - FAILURE TO PROVIDE ALL COLUMNS WILL RESULT IN INCOMPLETE REPORT
   - INCLUDE ALL INGREDIENTS FROM THE INCI LIST - DO NOT SKIP ANY
   - IMPORTANT: Categorize each ingredient as ACTIVES or EXCIPIENTS appropriately

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
    - Provide clear, concise pH recommendations in a single, well-formatted paragraph
    - Format: "Recommended pH range: X.X-X.X. [Brief explanation of why this range is suitable for the formulation, considering the ingredients present]."
    - Do NOT use bullet points, numbered lists, or multiple lines - keep it as ONE single, continuous paragraph
    - The paragraph should be 2-4 sentences maximum, explaining the pH range and why it's suitable

9) Expected Benefits Analysis (REQUIRED if expected benefits are provided)
   - Create a table with: Expected Benefit | Can Be Achieved? | Supporting Ingredients | Evidence/Mechanism | Limitations
   - Use pipe (|) separators
   - For each expected benefit, analyze if it can be achieved (YES/NO/PARTIALLY)
   - List which ingredients support each benefit
   - Explain the evidence/mechanism
   - Note any limitations or concerns
   - Fill ALL columns with relevant information

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
                # New format: Ingredient | Category | Functions/Notes | BIS Cautions (4 columns)
                # Old format: Ingredient | Status | Category | Functions/Notes | BIS Cautions (5 columns) - for backward compatibility
                # Very old format: Ingredient | Status | Notes (3 columns) - for backward compatibility
                if len(cells) >= 3:  # Should have at least Ingredient | Category | Notes or more
                    # Check for Functions/Notes column
                    notes_cell = ""
                    if len(cells) >= 4:
                        # Could be new 4-column format or old 5-column format
                        # In new format: Ingredient | Category | Functions/Notes | BIS Cautions (cells[2] is Functions/Notes)
                        # In old format: Ingredient | Status | Category | Functions/Notes | BIS Cautions (cells[3] is Functions/Notes)
                        # Check if second cell is "Status" (old format) or "Category" (new format)
                        if cells[1].strip().upper() in ['BRANDED', 'NOT BRANDED', 'MATCHED', 'UNMATCHED']:
                            notes_cell = cells[3].strip()  # Old 5-column format
                        else:
                            notes_cell = cells[2].strip()  # New 4-column format
                    else:
                        notes_cell = cells[2].strip()  # Very old 3-column format or new 4-column with missing BIS
                    
                    if notes_cell and notes_cell not in ['Notes', 'Functions/Notes', '']:
                        has_notes = True
                        ingredient_count += 1
                            
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

def validate_bis_cautions_in_report(report_text: str, bis_cautions: Optional[Dict[str, List[str]]] = None) -> Dict[str, bool]:
    """
    Validate that all BIS cautions are present in the report
    Returns a dict mapping ingredient names to whether all their cautions were found
    """
    if not bis_cautions or len(bis_cautions) == 0:
        return {}
    
    validation_results = {}
    report_lower = report_text.lower()
    
    for ingredient, cautions in bis_cautions.items():
        if not cautions or len(cautions) == 0:
            continue
        
        ingredient_lower = ingredient.lower()
        # Check if ingredient appears in report
        if ingredient_lower not in report_lower:
            validation_results[ingredient] = False
            print(f"⚠️ WARNING: Ingredient '{ingredient}' not found in report!")
            continue
        
        # Check for each caution
        cautions_found = 0
        for i, caution in enumerate(cautions, 1):
            # Check for numbered caution (1., 2., etc.)
            if f"{i}." in report_text:
                # Also check if key words from caution appear
                caution_words = caution.split()[:5]  # First 5 words
                if len(caution_words) >= 3:
                    search_text = " ".join(caution_words).lower()
                    if search_text in report_lower:
                        cautions_found += 1
            else:
                # Check if caution text appears even without number
                caution_words = caution.split()[:5]
                if len(caution_words) >= 3:
                    search_text = " ".join(caution_words).lower()
                    if search_text in report_lower:
                        cautions_found += 1
        
        all_found = cautions_found >= len(cautions) * 0.8  # Allow 80% match (some variation in wording)
        validation_results[ingredient] = all_found
        
        if not all_found:
            print(f"⚠️ WARNING: Only {cautions_found}/{len(cautions)} cautions found for '{ingredient}'")
        else:
            print(f"✅ All {len(cautions)} cautions found for '{ingredient}'")
    
    return validation_results

def parse_report_to_json(report_text: str) -> FormulationReportResponse:
    """Parse report text into structured JSON format"""
    lines = report_text.split('\n')
    
    inci_list = []
    analysis_table = []
    compliance_panel = []
    preservative_efficacy = []
    risk_panel = []
    cumulative_benefit = []
    claim_panel = []
    recommended_ph_range = None
    expected_benefits_analysis = []
    
    current_section = None
    in_table = False
    table_headers = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Detect section headers
        if line.startswith('1) Submitted INCI List'):
            current_section = 'inci_list'
            in_table = False
            i += 1
            continue
        elif line.startswith('2) Analysis'):
            current_section = 'analysis'
            in_table = False
            i += 1
            # Skip header line if present
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        elif line.startswith('3) Compliance Panel'):
            current_section = 'compliance'
            in_table = False
            i += 1
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        elif line.startswith('4) Preservative Efficacy Check'):
            current_section = 'preservative'
            in_table = False
            i += 1
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        elif line.startswith('5) Risk Panel'):
            current_section = 'risk'
            in_table = False
            i += 1
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        elif line.startswith('6) Cumulative Benefit Panel'):
            current_section = 'cumulative_benefit'
            in_table = False
            i += 1
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        elif line.startswith('7) Claim Panel'):
            current_section = 'claim'
            in_table = False
            i += 1
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        elif line.startswith('8) Recommended pH Range'):
            current_section = 'ph_range'
            in_table = False
            i += 1
            # Collect all text until next section
            ph_text = []
            while i < len(lines) and not lines[i].strip().startswith('9)'):
                if lines[i].strip():
                    ph_text.append(lines[i].strip())
                i += 1
            recommended_ph_range = ' '.join(ph_text) if ph_text else None
            continue
        elif line.startswith('9) Expected Benefits Analysis'):
            current_section = 'expected_benefits'
            in_table = False
            i += 1
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            continue
        
        # Process content based on current section
        if current_section == 'inci_list':
            # Add ingredient if it's not a header or empty
            if line and not line.startswith('-') and '|' not in line:
                inci_list.append(line)
        elif '|' in line:
            # This is a table row
            # Handle potential multi-line cells (especially for BIS Cautions)
            # Collect lines until we have a complete row (4 columns for analysis table)
            row_lines = [line]
            j = i + 1
            expected_columns = 4 if current_section == 'analysis' else 3
            
            # Check if this line has the expected number of columns
            cell_count = len([c for c in line.split('|') if c.strip()])
            
            # If we have fewer columns than expected, check if next lines are continuation
            # (This handles cases where BIS Cautions column has newlines)
            if cell_count < expected_columns and j < len(lines):
                # Look ahead to see if next lines are part of this row
                # Stop if we hit another row (starts with non-whitespace and has |) or section header
                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    # If next line starts a new section, stop
                    if next_line.startswith(('1)', '2)', '3)', '4)', '5)', '6)', '7)', '8)', '9)', '10)')):
                        break
                    # If next line is a complete table row (has | and enough columns), stop
                    if '|' in next_line:
                        next_cell_count = len([c for c in next_line.split('|') if c.strip()])
                        # If it looks like a complete row, stop
                        if next_cell_count >= expected_columns:
                            break
                        # Otherwise, it might be a continuation
                        row_lines.append(next_line)
                        j += 1
                    else:
                        # Continuation line without | - append to last cell
                        row_lines.append(next_line)
                        j += 1
                    # Safety limit
                    if j - i > 10:
                        break
            
            # Reconstruct the row from collected lines
            # For multi-line cells, especially BIS Cautions, we need to handle carefully
            # Strategy: If we have continuation lines without |, they're likely part of the last cell (BIS Cautions)
            if len(row_lines) > 1 and current_section == 'analysis':
                # Check if continuation lines are part of BIS Cautions column
                first_line = row_lines[0]
                first_cells = [c.strip() for c in first_line.split('|') if c.strip()]
                
                # If first line has exactly 3 cells (missing BIS Cautions), continuation lines are BIS Cautions
                if len(first_cells) == 3:
                    cells = first_cells[:3]
                    # Collect continuation lines as BIS Cautions (preserve newlines)
                    bis_cautions_parts = []
                    for continuation_line in row_lines[1:]:
                        if '|' not in continuation_line.strip():
                            bis_cautions_parts.append(continuation_line.strip())
                        else:
                            break  # New row detected
                    bis_cautions_merged = '\n'.join(bis_cautions_parts) if bis_cautions_parts else ''
                    cells.append(bis_cautions_merged)
                else:
                    # Standard parsing - join with space, but preserve structure for BIS Cautions
                    full_row = ' '.join(row_lines)
                    cells = [cell.strip() for cell in full_row.split('|') if cell.strip()]
                    # If more than 4 cells, merge extras into BIS Cautions
                    if len(cells) > 4:
                        reconstructed = cells[:3]
                        bis_cautions_merged = ' '.join(cells[3:])
                        reconstructed.append(bis_cautions_merged)
                        cells = reconstructed
            else:
                # Standard parsing for single-line rows or other tables
                full_row = ' '.join(row_lines)
                cells = [cell.strip() for cell in full_row.split('|') if cell.strip()]
                # For analysis table, if we have more than 4 cells, merge extras into BIS Cautions (last column)
                if current_section == 'analysis' and len(cells) > 4:
                    reconstructed = cells[:3]  # First 3 columns: Ingredient, Category, Functions/Notes
                    # Merge remaining cells into BIS Cautions
                    bis_cautions_merged = ' '.join(cells[3:])
                    reconstructed.append(bis_cautions_merged)
                    cells = reconstructed
            
            if cells and len(cells) > 1:  # Skip header rows (they're usually all caps or have specific keywords)
                # Check if it's a header row (all caps or contains "Ingredient", "Category", etc.)
                is_header = any(c.upper() in ['INGREDIENT', 'CATEGORY', 'FUNCTIONS/NOTES', 'BIS CAUTIONS', 
                                                  'REGULATION', 'STATUS', 'REQUIREMENTS', 'PRESERVATIVE', 'EFFICACY',
                                                  'RISK FACTOR', 'LEVEL', 'MITIGATION', 'BENEFIT', 'MECHANISM',
                                                  'CLAIM', 'SUPPORT LEVEL', 'EVIDENCE'] for c in cells)
                if not is_header:
                    if current_section == 'analysis':
                        analysis_table.append(ReportTableRow(cells=cells))
                    elif current_section == 'compliance':
                        compliance_panel.append(ReportTableRow(cells=cells))
                    elif current_section == 'preservative':
                        preservative_efficacy.append(ReportTableRow(cells=cells))
                    elif current_section == 'risk':
                        risk_panel.append(ReportTableRow(cells=cells))
                    elif current_section == 'cumulative_benefit':
                        cumulative_benefit.append(ReportTableRow(cells=cells))
                    elif current_section == 'claim':
                        claim_panel.append(ReportTableRow(cells=cells))
                    elif current_section == 'expected_benefits':
                        expected_benefits_analysis.append(ReportTableRow(cells=cells))
            
            # Skip the lines we've already processed
            i = j
            continue
        
        i += 1
    
    # Add default headers for each table if they don't exist
    # Analysis table headers
    if analysis_table and len(analysis_table) > 0:
        # Check if first row is a header, if not, prepend default headers
        first_row_cells = analysis_table[0].cells if analysis_table else []
        is_header = any(c.upper() in ['INGREDIENT', 'CATEGORY', 'FUNCTIONS/NOTES', 'BIS CAUTIONS'] for c in first_row_cells)
        if not is_header:
            # Prepend header row
            analysis_table.insert(0, ReportTableRow(cells=["Ingredient", "Category", "Functions/Notes", "BIS Cautions"]))
    
    # Compliance panel headers
    if compliance_panel and len(compliance_panel) > 0:
        first_row_cells = compliance_panel[0].cells if compliance_panel else []
        is_header = any(c.upper() in ['REGULATION', 'STATUS', 'REQUIREMENTS'] for c in first_row_cells)
        if not is_header:
            compliance_panel.insert(0, ReportTableRow(cells=["Regulation", "Status", "Requirements"]))
    
    # Preservative efficacy headers
    if preservative_efficacy and len(preservative_efficacy) > 0:
        first_row_cells = preservative_efficacy[0].cells if preservative_efficacy else []
        is_header = any(c.upper() in ['PRESERVATIVE', 'EFFICACY', 'PH RANGE', 'STABILITY'] for c in first_row_cells)
        if not is_header:
            preservative_efficacy.insert(0, ReportTableRow(cells=["Preservative", "Efficacy", "pH Range", "Stability"]))
    
    # Risk panel headers
    if risk_panel and len(risk_panel) > 0:
        first_row_cells = risk_panel[0].cells if risk_panel else []
        is_header = any(c.upper() in ['RISK FACTOR', 'LEVEL', 'MITIGATION'] for c in first_row_cells)
        if not is_header:
            risk_panel.insert(0, ReportTableRow(cells=["Risk Factor", "Level", "Mitigation"]))
    
    # Cumulative benefit headers
    if cumulative_benefit and len(cumulative_benefit) > 0:
        first_row_cells = cumulative_benefit[0].cells if cumulative_benefit else []
        is_header = any(c.upper() in ['BENEFIT', 'MECHANISM', 'EVIDENCE LEVEL'] for c in first_row_cells)
        if not is_header:
            cumulative_benefit.insert(0, ReportTableRow(cells=["Benefit", "Mechanism", "Evidence Level"]))
    
    # Claim panel headers
    if claim_panel and len(claim_panel) > 0:
        first_row_cells = claim_panel[0].cells if claim_panel else []
        is_header = any(c.upper() in ['CLAIM', 'SUPPORT LEVEL', 'EVIDENCE'] for c in first_row_cells)
        if not is_header:
            claim_panel.insert(0, ReportTableRow(cells=["Claim", "Support Level", "Evidence"]))
    
    # Expected benefits analysis headers
    if expected_benefits_analysis and len(expected_benefits_analysis) > 0:
        first_row_cells = expected_benefits_analysis[0].cells if expected_benefits_analysis else []
        is_header = any(c.upper() in ['EXPECTED BENEFIT', 'CAN BE ACHIEVED', 'SUPPORTING INGREDIENTS'] for c in first_row_cells)
        if not is_header:
            expected_benefits_analysis.insert(0, ReportTableRow(cells=["Expected Benefit", "Can Be Achieved?", "Supporting Ingredients", "Evidence/Mechanism", "Limitations"]))
    
    return FormulationReportResponse(
        inci_list=inci_list,
        analysis_table=analysis_table,
        compliance_panel=compliance_panel,
        preservative_efficacy=preservative_efficacy,
        risk_panel=risk_panel,
        cumulative_benefit=cumulative_benefit,
        claim_panel=claim_panel,
        recommended_ph_range=recommended_ph_range,
        expected_benefits_analysis=expected_benefits_analysis,
        raw_text=report_text
    )

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
            
            # Check if it's a conclusion section header
            if 'CONCLUSION' in line.upper() and 'EXPECTED BENEFITS' in line.upper():
                # Format conclusion section with proper styling (same as other section headers)
                story.append(Spacer(1, 12))
                story.append(Paragraph(line, header_style))
            # Check if it's a benefit name line (format: "Benefit Name: Brightening")
            elif line and 'Benefit Name:' in line:
                # Extract and format benefit name
                benefit_name = line.split('Benefit Name:')[-1].strip()
                if benefit_name:
                    story.append(Spacer(1, 10))
                    # Use a subheading style that matches other sections
                    story.append(Paragraph(f"<b>{benefit_name}</b>", ParagraphStyle(
                        'BenefitHeading',
                        parent=header_style,
                        fontSize=14,
                        fontName='Helvetica-Bold',
                        spaceAfter=8,
                        spaceBefore=0,
                        textColor=colors.HexColor('#007bff')
                    )))
            # Check if it's a benefit subheading (Assessment, Supporting Ingredients, Reasoning, Suggestion)
            elif line and ('Assessment:' in line or 'Supporting Ingredients:' in line or 'Reasoning:' in line or 'Suggestion:' in line):
                # Format as bold subheading with proper spacing (matching other sections)
                story.append(Spacer(1, 6))
                story.append(Paragraph(f"<b>{line}</b>", ParagraphStyle(
                    'BenefitSubheading',
                    parent=normal_style,
                    fontSize=11,
                    fontName='Helvetica-Bold',
                    spaceAfter=4
                )))
            # Check if it's an ingredient (simple heuristic)
            elif (line and len(line) < 100 and 
                not line.startswith(('Ingredient', 'Status', 'Notes', 'Category', 'Function', 'CONCLUSION', 'Assessment', 'Supporting', 'Reasoning', 'Suggestion', 'Benefit')) and
                any(keyword in line for keyword in ['Aqua', 'Water', 'Glycerin', 'Acid', 'Oil', 'Extract', 'Alcohol', 'Ester'])):
                # Format as ingredient tag
                story.append(Paragraph(f"<b>{line}</b>", normal_style))
            else:
                # Regular content text
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
    bis_cautions: Optional[Dict[str, List[str]]] = None,
    expected_benefits: Optional[str] = None
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
    
    # Clean and reformat BIS cautions using Claude to make them proper sentences
    cleaned_bis_cautions = {}
    if bis_cautions and len(bis_cautions) > 0:
        print(f"🧹 Cleaning and reformatting BIS cautions with Claude...")
        if claude_client:
            for ingredient, cautions in bis_cautions.items():
                if cautions and len(cautions) > 0:
                    try:
                        # Ask Claude to reformat cautions into proper sentences
                        reformat_prompt = f"""You are a regulatory compliance expert. Below are raw BIS (Bureau of Indian Standards) caution fragments extracted from documents for the ingredient: {ingredient}

RAW CAUTION FRAGMENTS:
{chr(10).join(f'{i+1}. {caution}' for i, caution in enumerate(cautions))}

TASK: Reform each fragment into a complete, proper sentence that makes regulatory sense. 

REQUIREMENTS:
1. Each caution must be a complete, grammatically correct sentence
2. Include all numerical values, percentages, limits, CAS numbers, and regulatory information
3. Make it clear and professional (e.g., "Maximum concentration: 5% w/w" not just "5% w/w")
4. If a fragment is incomplete or malformed, reconstruct it into a meaningful sentence based on context
5. Remove fragments that are just CAS numbers, ingredient names, or incomplete text
6. Each reformatted caution should be on a separate line, numbered 1., 2., 3., etc.

Return ONLY the reformatted cautions, one per line, numbered. If a fragment cannot be made into a proper sentence, skip it.

REFORMATTED CAUTIONS:"""

                        response = claude_client.messages.create(
                            model="claude-3-opus-20240229",
                            max_tokens=2000,
                            temperature=0.1,
                            messages=[{"role": "user", "content": reformat_prompt}]
                        )
                        
                        reformatted_text = response.content[0].text.strip()
                        # Parse the reformatted cautions (one per line, numbered)
                        reformatted_cautions = []
                        for line in reformatted_text.split('\n'):
                            line = line.strip()
                            if line and (line[0].isdigit() or line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or line.startswith('4.') or line.startswith('5.')):
                                # Remove numbering and clean
                                cleaned = re.sub(r'^\d+\.\s*', '', line).strip()
                                if cleaned and len(cleaned) > 10:  # Must be meaningful
                                    reformatted_cautions.append(cleaned)
                        
                        if reformatted_cautions:
                            cleaned_bis_cautions[ingredient] = reformatted_cautions
                            print(f"   ✅ {ingredient}: Reformatted {len(reformatted_cautions)} caution(s) from {len(cautions)} fragments")
                        else:
                            # Fallback: use original if reformatting failed
                            cleaned_bis_cautions[ingredient] = cautions
                            print(f"   ⚠️ {ingredient}: Reformatting failed, using original {len(cautions)} caution(s)")
                    except Exception as e:
                        print(f"   ❌ Error reformatting cautions for {ingredient}: {e}")
                        # Fallback to original
                        cleaned_bis_cautions[ingredient] = cautions
        else:
            # No Claude client, use original
            cleaned_bis_cautions = bis_cautions
            print("⚠️ Claude client not available, using original BIS cautions")
        
        # Use cleaned cautions
        bis_cautions = cleaned_bis_cautions
    
    # Build BIS cautions context if provided
    bis_cautions_info = ""
    if bis_cautions and len(bis_cautions) > 0:
        total_cautions = sum(len(cautions) for cautions in bis_cautions.values() if cautions)
        print(f"📋 Including cleaned BIS cautions for {len(bis_cautions)} ingredients (total {total_cautions} cautions)")
        bis_cautions_info = "\n\n" + "=" * 70 + "\n"
        bis_cautions_info += "BUREAU OF INDIAN STANDARDS (BIS) CAUTIONS & REGULATORY NOTES\n"
        bis_cautions_info += "=" * 70 + "\n"
        bis_cautions_info += "CRITICAL INSTRUCTIONS FOR BIS CAUTIONS:\n"
        bis_cautions_info += "1. You MUST include ALL cautions listed below for each ingredient\n"
        bis_cautions_info += "2. Each caution must be on a SEPARATE LINE within the table cell\n"
        bis_cautions_info += "3. Number each caution (1., 2., 3., etc.)\n"
        bis_cautions_info += "4. Include EXACT numerical values (percentages, limits, concentrations)\n"
        bis_cautions_info += "5. Do NOT combine multiple cautions into one line\n"
        bis_cautions_info += "6. Do NOT use vague phrases - include actual values\n"
        bis_cautions_info += "\n" + "-" * 70 + "\n"
        bis_cautions_info += "BIS CAUTIONS BY INGREDIENT:\n"
        bis_cautions_info += "-" * 70 + "\n"
        for ingredient, cautions in bis_cautions.items():
            if cautions and len(cautions) > 0:
                bis_cautions_info += f"\n[{ingredient}] - {len(cautions)} caution(s) - YOU MUST INCLUDE ALL {len(cautions)} CAUTIONS:\n"
                for i, caution in enumerate(cautions, 1):
                    # Format each caution on a new line with proper numbering
                    bis_cautions_info += f"  CAUTION {i} of {len(cautions)}: {caution}\n"
                bis_cautions_info += f"  → REMEMBER: This ingredient has {len(cautions)} cautions. Include ALL {len(cautions)} in the report!\n"
                bis_cautions_info += "\n"
        bis_cautions_info += "\n" + "=" * 70 + "\n"
        bis_cautions_info += "FORMATTING REQUIREMENTS FOR TABLE CELL:\n"
        bis_cautions_info += "When you write BIS cautions in the 'BIS Cautions' column of the Analysis table:\n"
        bis_cautions_info += "- Put each caution on its own line (use actual line breaks, not commas)\n"
        bis_cautions_info += "- Start each line with the number and period (1., 2., 3., etc.)\n"
        bis_cautions_info += "- Use actual newline characters to separate cautions within the cell\n"
        bis_cautions_info += "- CRITICAL: If an ingredient has multiple cautions, you MUST write each one on a separate line\n"
        bis_cautions_info += "- Example format for an ingredient with 4 cautions:\n"
        bis_cautions_info += "  Ingredient Name | Category | Functions/Notes | 1. First caution with exact values\n"
        bis_cautions_info += "  2. Second caution with exact values\n"
        bis_cautions_info += "  3. Third caution with exact values\n"
        bis_cautions_info += "  4. Fourth caution with exact values\n"
        bis_cautions_info += "- DO NOT write all cautions on one line separated by commas or semicolons\n"
        bis_cautions_info += "- DO NOT skip any cautions - include ALL of them\n"
        bis_cautions_info += "- DO NOT summarize or combine cautions - list each one separately\n"
        bis_cautions_info += "=" * 70 + "\n"
    else:
        print("⚠️ No BIS cautions provided or empty")
    
    # Build expected benefits context if provided
    expected_benefits_info = ""
    if expected_benefits and expected_benefits.strip():
        expected_benefits_info = f"\n\nEXPECTED BENEFITS FROM USER:\n{expected_benefits.strip()}\n\nCRITICAL: You MUST add a section at the end of the report (after section 8) titled:\n\n9) Expected Benefits Analysis\n\nFor each expected benefit mentioned by the user, analyze:\n- Can this benefit be achieved from this formulation? (YES/NO/PARTIALLY)\n- Which ingredients support this benefit?\n- What is the evidence/mechanism?\n- Any limitations or concerns?\n\nFormat as a table with columns: Expected Benefit | Can Be Achieved? | Supporting Ingredients | Evidence/Mechanism | Limitations\n\nThis is a CRITICAL section - DO NOT SKIP IT!\n"
    
    user_prompt = f"Generate report for this INCI list:\n{inci_str}{categorization_info}{bis_cautions_info}{expected_benefits_info}\n\nREMEMBER: Every table cell must have content. NO EMPTY CELLS!\n\nCRITICAL FOR BIS CAUTIONS - THIS IS MANDATORY:\n- If BIS cautions are provided above for an ingredient, you MUST include ALL of them - DO NOT SKIP ANY\n- Count the number of cautions provided for each ingredient and ensure ALL are included\n- Each caution must be on a SEPARATE LINE within the BIS Cautions column (use actual line breaks)\n- Number each caution starting with 1., 2., 3., 4., etc. on its own line\n- Do NOT combine multiple cautions into one line separated by commas or semicolons\n- Do NOT skip any cautions - if 4 are provided, include all 4; if 5 are provided, include all 5\n- Do NOT summarize or shorten - include the FULL text of each caution exactly as provided\n- Write each caution exactly as provided, preserving all numerical values, percentages, limits, and exact wording\n- Missing even one caution is a CRITICAL ERROR - verify you have included every single caution listed above"
    
    # Try Claude first
    if claude_client:
        try:
            print("🔄 Attempting to generate report with Claude...")
            if bis_cautions and len(bis_cautions) > 0:
                total_cautions = sum(len(c) for c in bis_cautions.values() if c)
                print(f"📊 Sending {total_cautions} total BIS cautions to Claude for {len(bis_cautions)} ingredients")
                for ing, cautions in bis_cautions.items():
                    if cautions:
                        print(f"   - {ing}: {len(cautions)} caution(s)")
            
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
            
            # Debug: Check if BIS cautions are in the response
            if bis_cautions and len(bis_cautions) > 0:
                print("\n🔍 Checking BIS cautions in Claude response:")
                for ingredient, cautions in bis_cautions.items():
                    if cautions:
                        # Count how many times the ingredient appears in the report
                        ingredient_lower = ingredient.lower()
                        report_lower = report_text.lower()
                        count = report_lower.count(ingredient_lower)
                        # Check if caution numbers appear (1., 2., 3., etc.)
                        caution_numbers_found = sum(1 for i in range(1, len(cautions) + 1) if f"{i}." in report_text)
                        # Also check for actual caution text snippets
                        caution_text_found = 0
                        for caution in cautions:
                            # Check if key parts of the caution appear in the report
                            caution_words = caution.split()[:5]  # First 5 words
                            if len(caution_words) >= 3:
                                search_text = " ".join(caution_words).lower()
                                if search_text in report_lower:
                                    caution_text_found += 1
                        print(f"   - {ingredient}: appears {count} time(s), found {caution_numbers_found}/{len(cautions)} caution numbers, {caution_text_found}/{len(cautions)} caution texts")
                        if caution_numbers_found < len(cautions):
                            print(f"      ⚠️ WARNING: Only {caution_numbers_found} out of {len(cautions)} cautions detected in response!")
            
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

@router.post("/formulation-report-json", response_model=FormulationReportResponse)
async def generate_report_json(payload: FormulationReportRequest):
    """Generate report and return as structured JSON"""
    try:
        inci_str = ", ".join(payload.inciList)

        # Generate report text using OpenAI or Claude fallback
        report_text = await generate_report_text(
            inci_str, 
            branded_ingredients=payload.brandedIngredients,
            not_branded_ingredients=payload.notBrandedIngredients,
            bis_cautions=payload.bisCautions,
            expected_benefits=payload.expectedBenefits
        )
        
        # Validate BIS cautions are present
        if payload.bisCautions:
            validation_results = validate_bis_cautions_in_report(report_text, payload.bisCautions)
            missing_cautions = [ing for ing, found in validation_results.items() if not found]
            if missing_cautions:
                print(f"⚠️ WARNING: BIS cautions validation failed for: {', '.join(missing_cautions)}")
        
        # Parse report text into JSON structure
        report_json = parse_report_to_json(report_text)
        
        return report_json
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating report JSON: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

@router.post("/formulation-report")
async def generate_report(payload: FormulationReportRequest, request: Request):
    try:
        inci_str = ", ".join(payload.inciList)

        # 🔹 Generate report text using OpenAI or Claude fallback with categorization info, BIS cautions, and expected benefits
        report_text = await generate_report_text(
            inci_str, 
            branded_ingredients=payload.brandedIngredients,
            not_branded_ingredients=payload.notBrandedIngredients,
            bis_cautions=payload.bisCautions,
            expected_benefits=payload.expectedBenefits
        )
        
        # 🔹 Validate and fix empty notes if needed
        max_retries = 3
        retry_count = 0
        ingredient_count = len(payload.inciList)
        
        # Check if BIS cautions are missing
        bis_cautions_missing = False
        if payload.bisCautions:
            validation_results = validate_bis_cautions_in_report(report_text, payload.bisCautions)
            missing_cautions = [ing for ing, found in validation_results.items() if not found]
            if missing_cautions:
                bis_cautions_missing = True
                print(f"⚠️ BIS cautions validation failed for: {', '.join(missing_cautions)}")
        
        # Retry if report content is invalid OR if BIS cautions are missing
        while (not validate_report_content(report_text, ingredient_count) or bis_cautions_missing) and retry_count < max_retries:
            retry_count += 1
            if bis_cautions_missing:
                print(f"⚠️ BIS cautions missing (attempt {retry_count}/{max_retries}). Regenerating with stronger BIS cautions emphasis...")
            else:
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
            
            # Build BIS cautions info for retry (use same detailed format as initial generation)
            retry_bis_cautions = ""
            if payload.bisCautions and len(payload.bisCautions) > 0:
                total_cautions = sum(len(cautions) for cautions in payload.bisCautions.values() if cautions)
                retry_bis_cautions = "\n\n" + "=" * 70 + "\n"
                retry_bis_cautions += "BUREAU OF INDIAN STANDARDS (BIS) CAUTIONS & REGULATORY NOTES\n"
                retry_bis_cautions += "=" * 70 + "\n"
                retry_bis_cautions += "CRITICAL INSTRUCTIONS FOR BIS CAUTIONS:\n"
                retry_bis_cautions += "1. You MUST include ALL cautions listed below for each ingredient\n"
                retry_bis_cautions += "2. Each caution must be on a SEPARATE LINE within the table cell\n"
                retry_bis_cautions += "3. Number each caution (1., 2., 3., etc.)\n"
                retry_bis_cautions += "4. Include EXACT numerical values (percentages, limits, concentrations)\n"
                retry_bis_cautions += "5. Do NOT combine multiple cautions into one line\n"
                retry_bis_cautions += "6. Do NOT use vague phrases - include actual values\n"
                retry_bis_cautions += "\n" + "-" * 70 + "\n"
                retry_bis_cautions += "BIS CAUTIONS BY INGREDIENT:\n"
                retry_bis_cautions += "-" * 70 + "\n"
                for ingredient, cautions in payload.bisCautions.items():
                    if cautions and len(cautions) > 0:
                        retry_bis_cautions += f"\n[{ingredient}] - {len(cautions)} caution(s) - YOU MUST INCLUDE ALL {len(cautions)} CAUTIONS:\n"
                        for i, caution in enumerate(cautions, 1):
                            retry_bis_cautions += f"  CAUTION {i} of {len(cautions)}: {caution}\n"
                        retry_bis_cautions += f"  → REMEMBER: This ingredient has {len(cautions)} cautions. Include ALL {len(cautions)} in the report!\n"
                        retry_bis_cautions += "\n"
                retry_bis_cautions += "\n" + "=" * 70 + "\n"
                retry_bis_cautions += "FORMATTING REQUIREMENTS FOR TABLE CELL:\n"
                retry_bis_cautions += "When you write BIS cautions in the 'BIS Cautions' column of the Analysis table:\n"
                retry_bis_cautions += "- Put each caution on its own line (use actual line breaks, not commas)\n"
                retry_bis_cautions += "- Start each line with the number and period (1., 2., 3., etc.)\n"
                retry_bis_cautions += "- Use actual newline characters to separate cautions within the cell\n"
                retry_bis_cautions += "- CRITICAL: If an ingredient has multiple cautions, you MUST write each one on a separate line\n"
                retry_bis_cautions += "- Example format for an ingredient with 4 cautions:\n"
                retry_bis_cautions += "  Ingredient Name | Category | Functions/Notes | 1. First caution with exact values\n"
                retry_bis_cautions += "  2. Second caution with exact values\n"
                retry_bis_cautions += "  3. Third caution with exact values\n"
                retry_bis_cautions += "  4. Fourth caution with exact values\n"
                retry_bis_cautions += "- DO NOT write all cautions on one line separated by commas or semicolons\n"
                retry_bis_cautions += "- DO NOT skip any cautions - include ALL of them\n"
                retry_bis_cautions += "- DO NOT summarize or combine cautions - list each one separately\n"
                retry_bis_cautions += "=" * 70 + "\n"
            
            # Build expected benefits info for retry
            retry_expected_benefits = ""
            if payload.expectedBenefits and payload.expectedBenefits.strip():
                retry_expected_benefits = f"\n\nEXPECTED BENEFITS FROM USER:\n{payload.expectedBenefits.strip()}\n\nCRITICAL: You MUST add a section at the end of the report (after section 8) titled:\n\n9) Expected Benefits Analysis\n\nFor each expected benefit mentioned by the user, analyze:\n- Can this benefit be achieved from this formulation? (YES/NO/PARTIALLY)\n- Which ingredients support this benefit?\n- What is the evidence/mechanism?\n- Any limitations or concerns?\n\nFormat as a table with columns: Expected Benefit | Can Be Achieved? | Supporting Ingredients | Evidence/Mechanism | Limitations\n\nThis is a CRITICAL section - DO NOT SKIP IT!\n"
            
            # Regenerate with stronger prompt
            retry_prompt = f"{SYSTEM_PROMPT}\n\nCRITICAL: The previous response had empty table cells, missing notes, missing ingredients, or missing BIS cautions. Regenerate with NO EMPTY CELLS, MEANINGFUL NOTES, ALL INGREDIENTS INCLUDED, AND ALL BIS CAUTIONS INCLUDED.\n\nGenerate report for this INCI list:\n{inci_str}{retry_categorization}{retry_bis_cautions}{retry_expected_benefits}\n\nEVERY SINGLE TABLE CELL MUST CONTAIN MEANINGFUL TEXT!\nINCLUDE ALL {ingredient_count} INGREDIENTS - DO NOT SKIP ANY!\n\nCRITICAL FOR BIS CAUTIONS:\n- If BIS cautions are provided above, you MUST include ALL of them for each ingredient\n- Count the cautions provided and ensure ALL are included - missing even one is an error\n- Each caution must be on a SEPARATE LINE with proper numbering (1., 2., 3., etc.)\n- Do NOT combine cautions into one line - each must be on its own line\n- Include the FULL text of each caution with exact numerical values\n\nExample of proper notes:\nAqua: Primary solvent, base ingredient\nGlycerin: Humectant, skin conditioning agent\nNiacinamide: Vitamin B3, brightening active\nProprietary Blend XYZ: Unknown proprietary ingredient, requires manufacturer clarification"
            
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
            
            # Clean the retry response
            report_text = clean_ai_response(report_text)
            
            # Re-validate BIS cautions after retry
            if payload.bisCautions:
                validation_results = validate_bis_cautions_in_report(report_text, payload.bisCautions)
                missing_cautions = [ing for ing, found in validation_results.items() if not found]
                bis_cautions_missing = len(missing_cautions) > 0
                if bis_cautions_missing:
                    print(f"⚠️ BIS cautions still missing after retry: {', '.join(missing_cautions)}")
                else:
                    print("✅ All BIS cautions now present in report")
        
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
