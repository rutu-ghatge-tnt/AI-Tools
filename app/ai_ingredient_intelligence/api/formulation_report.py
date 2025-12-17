# app/ai_ingredient_intelligence/api/formulation_report.py
import io
import datetime
import os
import re
import httpx
import asyncio
from fastapi import APIRouter, HTTPException, Response, Request, Body
from pydantic import BaseModel
from typing import List, Optional, Dict
import anthropic
from jinja2 import Environment, FileSystemLoader
from app.ai_ingredient_intelligence.models.schemas import FormulationReportResponse, FormulationSummary, ReportTableRow

router = APIRouter(tags=["Formulation Reports"])

class FormulationReportRequest(BaseModel):
    inciList: List[str]
    brandedIngredients: List[str] = []  # List of branded ingredient names from analyze_inci
    notBrandedIngredients: List[str] = []  # List of not branded ingredient names from analyze_inci
    bisCautions: Optional[Dict[str, List[str]]] = None  # BIS cautions from analyze_inci
    expectedBenefits: Optional[str] = None  # Expected benefits from user input

class PPTGenerationRequest(BaseModel):
    """Request to generate PPT from existing report JSON"""
    reportData: FormulationReportResponse  # The JSON response from formulation-report-json endpoint

# Initialize Claude client
claude_api_key = os.getenv("CLAUDE_API_KEY")
presenton_api_key = os.getenv("PRESENTON_API_KEY")

if not claude_api_key:
    print("⚠️ Warning: CLAUDE_API_KEY environment variable not set")
if not presenton_api_key:
    print("⚠️ Warning: PRESENTON_API_KEY environment variable not set")

claude_client = anthropic.Anthropic(api_key=claude_api_key) if claude_api_key else None

# Presenton API configuration
PRESENTON_API_BASE_URL = "https://api.presenton.ai/api/v1"
PRESENTON_GENERATE_ENDPOINT = f"{PRESENTON_API_BASE_URL}/ppt/presentation/generate"

SYSTEM_PROMPT = """You are FormulationLooker 1.0, a professional cosmetic formulation analyst.
CRITICAL: You MUST output ONLY structured text format (NOT HTML, NOT JSON). Use plain text with pipe (|) separators for tables.
CRITICAL: You MUST generate meaningful content for EVERY table cell. NO EMPTY CELLS ALLOWED.
CRITICAL: Do NOT include any introductory text like "I'll analyze" or "Let me analyze" - start directly with the report sections.
CRITICAL: In the report you MUST include ALL ingredients provided in the INCI list. Do NOT skip any ingredients.
CRITICAL: Do NOT split ingredient names that contain hyphens, numbers, or parentheses (e.g., "Polyacrylate Crosspolymer-6" must stay as one ingredient, not "Polyacrylate Crosspolymer" and "6"; "Citrus Sinensis (Blood Orange) Fruit Extracts" must stay as one ingredient, not split into parts).
CRITICAL: For BIS Cautions, if exact limits, percentages, or amounts are provided, you MUST include them EXACTLY as given. Do NOT use vague phrases like "see column" or "refer to table" - include the actual numbers, percentages, or limits.

Generate a clean, structured report with these exact sections:

0) Executive Summary
   - Provide structured summary fields for the formulation analysis
   - Format as a table with: Field | Value
   - Use pipe (|) separators
   - Required fields (MUST include all):
     * Formulation Type: Overall formulation type (e.g., "Water-based Serum", "Oil-based Formula")
     * Key Active Ingredients: Comma-separated list of main active ingredients (e.g., "Niacinamide, Hyaluronic Acid, Retinol")
     * Primary Benefits: Comma-separated list of main benefits (e.g., "Brightening, Hydration, Anti-aging")
     * Recommended pH Range: pH range value (e.g., "5.0-6.5")
     * Compliance Status: Overall status (e.g., "Compliant", "Review Needed", "Non-compliant")
     * Critical Concerns: List any critical concerns or warnings, or "None" if no concerns (comma-separated if multiple)
   - Each field must be on a separate row
   - Example format:
     Formulation Type | Water-based Serum
     Key Active Ingredients | Niacinamide, Hyaluronic Acid
     Primary Benefits | Brightening, Hydration
     Recommended pH Range | 5.0-6.5
     Compliance Status | Compliant
     Critical Concerns | None

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
   - Functions/Notes: REQUIRED for every ingredient. Combine function and notes in one column. DO NOT include branding information (e.g., "BRANDED per database") in this column - only include functional descriptions. Examples:
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

9) Expected Benefits Analysis (ONLY include this section if expected benefits are provided by the user)
   - This section should ONLY appear if expected benefits were provided in the user input
   - If no expected benefits were provided, DO NOT include this section at all - end the report after section 8
   - If expected benefits WERE provided, create a table with: Expected Benefit | Can Be Achieved? | Supporting Ingredients | Evidence/Mechanism | Limitations
   - Use pipe (|) separators
   - For each expected benefit, analyze if it can be achieved (YES/NO/PARTIALLY)
   - List which ingredients support each benefit
   - Explain the evidence/mechanism
   - Note any limitations or concerns
   - Fill ALL columns with relevant information

MANDATORY RULES:
- Use pipe (|) for all table separators
- Start each section with the exact header (e.g., "0) Executive Summary", "1) Submitted INCI List")
- Put ingredients on separate lines, no inline text
- No dashes, bullets, or extra formatting
- Keep tables consistent with same number of columns
- Use clear, concise language
- NEVER leave any table cell empty - always provide relevant information
- For the Functions/Notes column, provide brief but meaningful descriptions combining function and notes
- For the BIS Cautions column, if cautions are provided, list them; if not, write "no bis cautions"
- If you leave any cell empty, the report is incomplete and unusable
- DO NOT include any introductory phrases like "I'll analyze", "Let me analyze", "I will analyze" - start directly with "0) Executive Summary"
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
            if in_table and line.strip() and line.startswith(('0)', '3)', '4)', '5)', '6)', '7)', '8)', '9)', '10)')):
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
                if line.strip().startswith('0) Executive Summary') or line.strip().startswith('1) Submitted INCI List'):
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
    if not report_text or not report_text.strip():
        print("⚠️ WARNING: Empty report text provided to parse_report_to_json")
        return FormulationReportResponse(
            summary=None,
            inci_list=[],
            analysis_table=[],
            compliance_panel=[],
            preservative_efficacy=[],
            risk_panel=[],
            cumulative_benefit=[],
            claim_panel=[],
            recommended_ph_range=None,
            expected_benefits_analysis=[],
            raw_text=report_text
        )
    
    lines = report_text.split('\n')
    
    summary_data = {
        "formulation_type": None,
        "key_active_ingredients": [],
        "primary_benefits": [],
        "recommended_ph_range": None,
        "compliance_status": None,
        "critical_concerns": []
    }
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
        if line.startswith('0) Executive Summary'):
            current_section = 'summary'
            in_table = True
            i += 1
            # Skip header line if present
            if i < len(lines) and '|' in lines[i]:
                table_headers = [h.strip() for h in lines[i].split('|')]
                i += 1
            # Parse summary table rows
            while i < len(lines) and not lines[i].strip().startswith('1)'):
                line = lines[i].strip()
                if '|' in line:
                    cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                    if len(cells) >= 2:
                        field_name = cells[0].strip().lower()
                        field_value = cells[1].strip()
                        
                        # Map field names to summary data (case-insensitive matching)
                        if 'formulation type' in field_name or 'formulation' in field_name and 'type' in field_name:
                            summary_data["formulation_type"] = field_value
                        elif 'key active' in field_name or ('active' in field_name and 'ingredient' in field_name):
                            # Split comma-separated values
                            ingredients = [ing.strip() for ing in field_value.split(',') if ing.strip()]
                            summary_data["key_active_ingredients"] = ingredients
                        elif 'primary benefit' in field_name or ('benefit' in field_name and 'primary' in field_name):
                            # Split comma-separated values
                            benefits = [ben.strip() for ben in field_value.split(',') if ben.strip()]
                            summary_data["primary_benefits"] = benefits
                        elif 'recommended ph' in field_name or 'ph range' in field_name or ('ph' in field_name and 'range' in field_name):
                            # Extract just the pH range value (e.g., "5.0-6.5")
                            import re
                            ph_match = re.search(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)', field_value)
                            if ph_match:
                                summary_data["recommended_ph_range"] = f"{ph_match.group(1)}-{ph_match.group(2)}"
                            else:
                                summary_data["recommended_ph_range"] = field_value
                        elif 'compliance status' in field_name or ('compliance' in field_name and 'status' in field_name):
                            summary_data["compliance_status"] = field_value
                        elif 'critical concern' in field_name or ('concern' in field_name and 'critical' in field_name):
                            # Split comma-separated values or handle "None"
                            if field_value.lower() in ['none', 'no concerns', 'no critical concerns', 'n/a', 'na']:
                                summary_data["critical_concerns"] = []
                            else:
                                concerns = [concern.strip() for concern in field_value.split(',') if concern.strip()]
                                summary_data["critical_concerns"] = concerns
                i += 1
            continue
        elif line.startswith('1) Submitted INCI List'):
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
                    if next_line.startswith(('0)', '1)', '2)', '3)', '4)', '5)', '6)', '7)', '8)', '9)', '10)')):
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
    
    # Extract pH from section 8 if not in summary
    if not summary_data["recommended_ph_range"] and recommended_ph_range:
        # Try to extract pH range from the recommended_ph_range text
        import re
        ph_match = re.search(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)', recommended_ph_range)
        if ph_match:
            summary_data["recommended_ph_range"] = f"{ph_match.group(1)}-{ph_match.group(2)}"
        else:
            # Use the full text if no range pattern found
            summary_data["recommended_ph_range"] = recommended_ph_range
    
    # Create summary object if any fields are populated
    summary_obj = None
    if any([
        summary_data["formulation_type"],
        summary_data["key_active_ingredients"],
        summary_data["primary_benefits"],
        summary_data["recommended_ph_range"],
        summary_data["compliance_status"],
        summary_data["critical_concerns"]
    ]):
        summary_obj = FormulationSummary(
            formulation_type=summary_data["formulation_type"],
            key_active_ingredients=summary_data["key_active_ingredients"],
            primary_benefits=summary_data["primary_benefits"],
            recommended_ph_range=summary_data["recommended_ph_range"],
            compliance_status=summary_data["compliance_status"],
            critical_concerns=summary_data["critical_concerns"]
        )
    
    return FormulationReportResponse(
        summary=summary_obj,
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


async def generate_report_text(
    inci_str: str, 
    branded_ingredients: Optional[List[str]] = None, 
    not_branded_ingredients: Optional[List[str]] = None,
    bis_cautions: Optional[Dict[str, List[str]]] = None,
    expected_benefits: Optional[str] = None
) -> str:
    """Generate report text using Claude"""
    
    # Build categorization context if provided
    categorization_info = ""
    if branded_ingredients or not_branded_ingredients:
        categorization_info = "\n\nINGREDIENT CATEGORIZATION FROM DATABASE ANALYSIS:\n"
        if branded_ingredients:
            categorization_info += f"- BRANDED Ingredients (found in database): {', '.join(branded_ingredients)}\n"
        if not_branded_ingredients:
            categorization_info += f"- NOT BRANDED Ingredients (not found in database): {', '.join(not_branded_ingredients)}\n"
        # Note: This categorization is for internal reference only - do not add "BRANDED per database" to Functions/Notes
    
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
                            model=os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929",
                            max_tokens=4096,  # Maximum allowed for claude-3-opus-20240229
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
    
    # Build expected benefits context if provided (optional - only include if provided)
    expected_benefits_info = ""
    if expected_benefits and expected_benefits.strip():
        expected_benefits_info = f"\n\nEXPECTED BENEFITS FROM USER:\n{expected_benefits.strip()}\n\nCRITICAL: You MUST add a section at the end of the report (after section 8) titled:\n\n9) Expected Benefits Analysis\n\nFor each expected benefit mentioned by the user, analyze:\n- Can this benefit be achieved from this formulation? (YES/NO/PARTIALLY)\n- Which ingredients support this benefit?\n- What is the evidence/mechanism?\n- Any limitations or concerns?\n\nFormat as a table with columns: Expected Benefit | Can Be Achieved? | Supporting Ingredients | Evidence/Mechanism | Limitations\n\nThis section should ONLY be included if expected benefits are provided above. If no expected benefits are provided, DO NOT include section 9 - end the report after section 8.\n"
    
    user_prompt = f"Generate report for this INCI list:\n{inci_str}{categorization_info}{bis_cautions_info}{expected_benefits_info}\n\nREMEMBER: Every table cell must have content. NO EMPTY CELLS!\n\nCRITICAL FOR BIS CAUTIONS - THIS IS MANDATORY:\n- If BIS cautions are provided above for an ingredient, you MUST include ALL of them - DO NOT SKIP ANY\n- Count the number of cautions provided for each ingredient and ensure ALL are included\n- Each caution must be on a SEPARATE LINE within the BIS Cautions column (use actual line breaks)\n- Number each caution starting with 1., 2., 3., 4., etc. on its own line\n- Do NOT combine multiple cautions into one line separated by commas or semicolons\n- Do NOT skip any cautions - if 4 are provided, include all 4; if 5 are provided, include all 5\n- Do NOT summarize or shorten - include the FULL text of each caution exactly as provided\n- Write each caution exactly as provided, preserving all numerical values, percentages, limits, and exact wording\n- Missing even one caution is a CRITICAL ERROR - verify you have included every single caution listed above\n\nCRITICAL: You MUST generate ALL 9 sections (or 8 if no expected benefits). Do NOT stop after section 2. Include sections 3-9:\n- 3) Compliance Panel\n- 4) Preservative Efficacy Check\n- 5) Risk Panel\n- 6) Cumulative Benefit Panel\n- 7) Claim Panel\n- 8) Recommended pH Range\n- 9) Expected Benefits Analysis (if expected benefits provided)"
    
    # Use Claude for report generation
    if claude_client:
        try:
            print("🔄 Generating report with Claude...")
            if bis_cautions and len(bis_cautions) > 0:
                total_cautions = sum(len(c) for c in bis_cautions.values() if c)
                print(f"📊 Sending {total_cautions} total BIS cautions to Claude for {len(bis_cautions)} ingredients")
                for ing, cautions in bis_cautions.items():
                    if cautions:
                        print(f"   - {ing}: {len(cautions)} caution(s)")
            
            # Use Claude API to generate report
            message = claude_client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4096,  # Maximum allowed for claude-3-opus-20240229
                temperature=0.1,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            report_text = message.content[0].text
            report_text = clean_ai_response(report_text)
            
            # Debug: Check if all sections are present
            sections_found = []
            for i in range(0, 10):
                if f"{i})" in report_text:
                    sections_found.append(i)
            print(f"📋 Sections found in report: {sections_found}")
            if len(sections_found) < 9:
                print(f"⚠️ WARNING: Only {len(sections_found)} sections found, expected at least 9 (including summary)!")
            
            # Debug: Check if BIS cautions are in the response
            if bis_cautions and len(bis_cautions) > 0:
                print("\n🔍 Checking BIS cautions in Claude response:")
                for ingredient, cautions in bis_cautions.items():
                    if cautions:
                        ingredient_lower = ingredient.lower()
                        report_lower = report_text.lower()
                        count = report_lower.count(ingredient_lower)
                        caution_numbers_found = sum(1 for i in range(1, len(cautions) + 1) if f"{i}." in report_text)
                        caution_text_found = 0
                        for caution in cautions:
                            caution_words = caution.split()[:5]
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
            raise HTTPException(status_code=500, detail=f"Claude report generation failed: {str(e)}")
    
    # If Claude not available
    raise HTTPException(status_code=500, detail="Claude API not available. Please check your CLAUDE_API_KEY environment variable.")

@router.post("/formulation-report-json", response_model=FormulationReportResponse)
async def generate_report_json(payload: FormulationReportRequest):
    """Generate report and return as structured JSON"""
    try:
        # Validate input
        if not payload.inciList or len(payload.inciList) == 0:
            raise HTTPException(status_code=400, detail="No ingredients provided in inciList")
        
        print(f"📋 Generating report for {len(payload.inciList)} ingredients")
        print(f"📋 First few ingredients: {payload.inciList[:5]}")
        
        inci_str = ", ".join(payload.inciList)

        # Generate report text using Claude
        print("🤖 Generating report text with Claude...")
        report_text = await generate_report_text(
            inci_str, 
            branded_ingredients=payload.brandedIngredients,
            not_branded_ingredients=payload.notBrandedIngredients,
            bis_cautions=payload.bisCautions,
            expected_benefits=payload.expectedBenefits
        )
        
        if not report_text or not report_text.strip():
            raise HTTPException(status_code=500, detail="Report text generation returned empty result")
        
        print(f"✅ Report text generated ({len(report_text)} characters)")
        print(f"📄 First 500 chars of report: {report_text[:500]}")
        
        # Validate BIS cautions are present
        if payload.bisCautions:
            validation_results = validate_bis_cautions_in_report(report_text, payload.bisCautions)
            missing_cautions = [ing for ing, found in validation_results.items() if not found]
            if missing_cautions:
                print(f"⚠️ WARNING: BIS cautions validation failed for: {', '.join(missing_cautions)}")
        
        # Parse report text into JSON structure
        print("🔍 Parsing report text into JSON structure...")
        report_json = parse_report_to_json(report_text)
        
        print(f"✅ Parsed report - INCI list: {len(report_json.inci_list)}, Analysis rows: {len(report_json.analysis_table)}")
        
        return report_json
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating report JSON: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

@router.post("/formulation-report")
async def generate_report(payload: FormulationReportRequest, request: Request):
    try:
        inci_str = ", ".join(payload.inciList)

        # 🔹 Generate report text using OpenAI with categorization info, BIS cautions, and expected benefits
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
            
            # Build expected benefits info for retry (optional - only include if provided)
            retry_expected_benefits = ""
            if payload.expectedBenefits and payload.expectedBenefits.strip():
                retry_expected_benefits = f"\n\nEXPECTED BENEFITS FROM USER:\n{payload.expectedBenefits.strip()}\n\nCRITICAL: You MUST add a section at the end of the report (after section 8) titled:\n\n9) Expected Benefits Analysis\n\nFor each expected benefit mentioned by the user, analyze:\n- Can this benefit be achieved from this formulation? (YES/NO/PARTIALLY)\n- Which ingredients support this benefit?\n- What is the evidence/mechanism?\n- Any limitations or concerns?\n\nFormat as a table with columns: Expected Benefit | Can Be Achieved? | Supporting Ingredients | Evidence/Mechanism | Limitations\n\nThis section should ONLY be included if expected benefits are provided above. If no expected benefits are provided, DO NOT include section 9 - end the report after section 8.\n"
            
            # Regenerate with stronger prompt
            retry_prompt = f"{SYSTEM_PROMPT}\n\nCRITICAL: The previous response had empty table cells, missing notes, missing ingredients, missing BIS cautions, or was missing sections. Regenerate with NO EMPTY CELLS, MEANINGFUL NOTES, ALL INGREDIENTS INCLUDED, ALL BIS CAUTIONS INCLUDED, AND ALL SECTIONS.\n\nGenerate report for this INCI list:\n{inci_str}{retry_categorization}{retry_bis_cautions}{retry_expected_benefits}\n\nEVERY SINGLE TABLE CELL MUST CONTAIN MEANINGFUL TEXT!\nINCLUDE ALL {ingredient_count} INGREDIENTS - DO NOT SKIP ANY!\n\nCRITICAL: You MUST generate ALL sections starting with section 0:\n- 0) Executive Summary (MANDATORY - must be first, format as table with Field | Value)\n- 1) Submitted INCI List\n- 2) Analysis\n- 3) Compliance Panel\n- 4) Preservative Efficacy Check\n- 5) Risk Panel\n- 6) Cumulative Benefit Panel\n- 7) Claim Panel\n- 8) Recommended pH Range\n- 9) Expected Benefits Analysis (if expected benefits provided)\n\nDO NOT skip section 0 (Executive Summary). You MUST include ALL sections!\n\nCRITICAL FOR BIS CAUTIONS:\n- If BIS cautions are provided above, you MUST include ALL of them for each ingredient\n- Count the cautions provided and ensure ALL are included - missing even one is an error\n- Each caution must be on a SEPARATE LINE with proper numbering (1., 2., 3., etc.)\n- Do NOT combine cautions into one line - each must be on its own line\n- Include the FULL text of each caution with exact numerical values\n\nExample of proper notes:\nAqua: Primary solvent, base ingredient\nGlycerin: Humectant, skin conditioning agent\nNiacinamide: Vitamin B3, brightening active\nProprietary Blend XYZ: Unknown proprietary ingredient, requires manufacturer clarification"
            
            # Regenerate with Claude
            if claude_client:
                try:
                    retry_message = claude_client.messages.create(
                        model="claude-3-opus-20240229",
                        max_tokens=4096,  # Maximum allowed for claude-3-opus-20240229
                        temperature=0.1,
                        system=SYSTEM_PROMPT,
                        messages=[
                            {"role": "user", "content": retry_prompt}
                        ]
                    )
                    report_text = retry_message.content[0].text
                except Exception as e:
                    print(f"❌ Claude retry failed: {type(e).__name__}: {e}")
                    raise HTTPException(status_code=500, detail=f"Claude retry failed: {str(e)}")
            else:
                raise HTTPException(status_code=500, detail="Claude API not available for retry")
            
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
            "report_text": report_text
        })

        return Response(content=html_content, media_type="text/html")

    except Exception as e:
        print(f"❌ Error in generate_report: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/formulation-report/status")
async def get_report_status():
    """Get the status of the last generated report"""
    return {
        "has_report": bool(last_report["text"]),
        "report_length": len(last_report["text"]) if last_report["text"] else 0,
        "last_generated": "Available" if last_report["text"] else "No report generated yet"
    }

async def generate_presenton_prompt(report_data: FormulationReportResponse) -> Dict:
    """Generate Presenton API JSON prompt using Claude from formulation report data"""
    if not claude_client:
        raise HTTPException(status_code=500, detail="Claude API not available")
    
    # Convert report data to JSON string for Claude
    import json
    report_json = json.dumps(report_data.dict(), indent=2)
    
    claude_prompt = f"""You are a presentation expert. Convert the following cosmetic formulation report data into a JSON format suitable for Presenton API.

The report data is:
{report_json}

Generate a JSON object with the following structure for Presenton API:
{{
  "instructions": "Clear, structured instructions for creating the presentation. Include guidance on slide structure, tone, and organization.",
  "content": "The main content material to include in the presentation. Format it as a comprehensive text that covers all sections of the report."
}}

REQUIREMENTS:
1. The "instructions" field should provide clear guidance on:
   - How to structure the slides (title slide, sections, etc.)
   - The tone and style (professional, technical, clear)
   - How to organize the content (one section per slide, use tables where appropriate)
   - Visual guidance (use charts for data, tables for comparisons)

2. The "content" field should include ALL the information from the report:
   - INCI ingredient list
   - Analysis table with ingredient details
   - Compliance panel
   - Preservative efficacy information
   - Risk panel
   - Cumulative benefits
   - Claim panel
   - Recommended pH range
   - Expected benefits analysis (if present)

3. Format the content in a way that's suitable for presentation slides - clear, concise, but comprehensive.

4. Return ONLY valid JSON, no markdown formatting, no code blocks.

Return the JSON object now:"""
    
    try:
        print("🤖 Generating Presenton prompt with Claude...")
        message = claude_client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=4096,  # Maximum allowed for claude-3-opus-20240229
            temperature=0.3,
            messages=[
                {"role": "user", "content": claude_prompt}
            ]
        )
        
        response_text = message.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            # Extract JSON from code block
            lines = response_text.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = '\n'.join(lines)
        
        # Parse JSON
        presenton_prompt = json.loads(response_text)
        
        # Validate structure
        if "instructions" not in presenton_prompt or "content" not in presenton_prompt:
            raise ValueError("Generated prompt missing required fields: instructions or content")
        
        print("✅ Presenton prompt generated successfully")
        return presenton_prompt
        
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse Claude response as JSON: {e}")
        print(f"Response text: {response_text[:500]}")
        raise HTTPException(status_code=500, detail=f"Failed to parse Claude response as JSON: {str(e)}")
    except Exception as e:
        print(f"❌ Error generating Presenton prompt: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating Presenton prompt: {str(e)}")

@router.post("/formulation-report/ppt")
async def generate_ppt(body: dict = Body(...)):
    """Generate PPT presentation using Presenton API from report JSON data"""
    try:
        if not presenton_api_key:
            raise HTTPException(
                status_code=500,
                detail="PRESENTON_API_KEY environment variable not set. Please configure it in your .env file."
            )
        
        # Validate request body
        if not body or not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Request body must be a JSON object with 'reportData' field. Got: {type(body).__name__}"
            )
        
        print(f"📥 Received PPT request - body type: {type(body)}, keys: {list(body.keys()) if isinstance(body, dict) else 'N/A'}")
        
        if "reportData" not in body:
            raise HTTPException(
                status_code=400,
                detail=f"Missing 'reportData' in request body. Expected: {{'reportData': {{...}}}}. Got keys: {list(body.keys())}"
            )
        
        # Parse reportData into FormulationReportResponse
        from app.ai_ingredient_intelligence.models.schemas import FormulationReportResponse
        try:
            report_data = FormulationReportResponse(**body["reportData"])
        except Exception as e:
            print(f"❌ Error parsing reportData: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reportData format: {str(e)}"
            )
        
        print(f"✅ Parsed report data - INCI list: {len(report_data.inci_list)}, Analysis rows: {len(report_data.analysis_table)}")
        
        # Generate Presenton prompt using Claude
        try:
            presenton_prompt = await generate_presenton_prompt(report_data)
            print(f"📝 Generated Presenton prompt with instructions and content")
        except Exception as e:
            print(f"❌ Error generating Presenton prompt: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error generating Presenton prompt: {str(e)}"
            )
        
        # Call Presenton API to generate presentation
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Generate PPTX presentation
            generate_response = await client.post(
                PRESENTON_GENERATE_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {presenton_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "instructions": presenton_prompt["instructions"],
                    "content": presenton_prompt["content"],
                    "export_as": "pptx",
                    "theme": "light-rose"
                }
            )
            
            if generate_response.status_code not in [200, 201]:
                error_text = generate_response.text
                try:
                    error_json = generate_response.json()
                    error_text = str(error_json)
                except:
                    pass
                raise HTTPException(
                    status_code=generate_response.status_code,
                    detail=f"Presenton API error: {error_text}"
                )
            
            try:
                generate_data = generate_response.json()
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Presenton API returned invalid JSON: {generate_response.text[:200]}"
                )
            
            # Presenton API returns presentation_id, path, and edit_path
            presentation_id = generate_data.get("presentation_id")
            file_path = generate_data.get("path")
            edit_path = generate_data.get("edit_path")
            
            if not presentation_id or not file_path:
                raise HTTPException(
                    status_code=500,
                    detail=f"Presenton API did not return required fields. Response: {generate_data}"
                )
            
            # Download the PPTX file from Presenton
            # Handle different path formats: full URL, relative path, or absolute path
            if file_path.startswith("http://") or file_path.startswith("https://"):
                download_url = file_path
            elif file_path.startswith("/"):
                download_url = f"https://api.presenton.ai{file_path}"
            else:
                download_url = f"https://api.presenton.ai/{file_path}"
            
            print(f"📥 Downloading PPTX from: {download_url}")
            
            download_response = await client.get(
                download_url,
                headers={
                    "Authorization": f"Bearer {presenton_api_key}"
                }
            )
            
            if download_response.status_code != 200:
                raise HTTPException(
                    status_code=download_response.status_code,
                    detail="Failed to download PPTX file from Presenton"
                )
            
            # Return the PPTX file with edit_path in headers for live editor access
            pptx_bytes = download_response.content
            if isinstance(pptx_bytes, str):
                pptx_bytes = pptx_bytes.encode('latin-1')
            
            headers = {
                "Content-Disposition": "attachment; filename=formulation_report.pptx",
                "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            }
            
            # Add edit_path to response headers if available
            if edit_path:
                headers["X-Presenton-Edit-Path"] = f"https://presenton.ai{edit_path}"
                headers["X-Presenton-Presentation-Id"] = presentation_id
            
            return Response(
                content=pptx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                headers=headers
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PPT generation failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PPT generation failed: {str(e)}")

@router.post("/formulation-report/test-ppt")
async def test_generate_ppt():
    """Test endpoint to generate PPT with sample data - for Swagger testing"""
    # Sample formulation report data based on your example
    sample_report_data = FormulationReportResponse(
        inci_list=[
            "Water",
            "Butylene Glycol",
            "Glycerin",
            "Caprylic/Capric Triglyceride",
            "Cetearyl Alcohol",
            "Niacinamide"
        ],
        analysis_table=[
            ReportTableRow(cells=["Ingredient", "Category", "Functions/Notes", "BIS Cautions"]),
            ReportTableRow(cells=["Water", "EXCIPIENT", "Primary solvent, base vehicle for the emulsion", "no bis cautions"]),
            ReportTableRow(cells=["Niacinamide", "ACTIVE", "Vitamin B3, brightening and tone-evening, barrier support", "no bis cautions"])
        ],
        compliance_panel=[
            ReportTableRow(cells=["Regulation", "Status", "Requirements"]),
            ReportTableRow(cells=["India Cosmetics Rules, 2020", "Generally compliant", "Provide complete ingredient list"])
        ],
        preservative_efficacy=[
            ReportTableRow(cells=["Preservative", "Efficacy", "pH Range", "Stability"]),
            ReportTableRow(cells=["1,2-Hexanediol", "Good broad-spectrum booster", "~3.0-10.0", "Thermally stable"])
        ],
        risk_panel=[
            ReportTableRow(cells=["Risk Factor", "Level", "Mitigation"]),
            ReportTableRow(cells=["Retinal irritation", "Medium", "Use low, well-validated dose"])
        ],
        cumulative_benefit=[
            ReportTableRow(cells=["Benefit", "Mechanism", "Evidence Level"]),
            ReportTableRow(cells=["Hydration", "Humectants attract/retain water", "Strong"])
        ],
        claim_panel=[
            ReportTableRow(cells=["Claim", "Support Level", "Evidence"]),
            ReportTableRow(cells=["Hydrates skin", "High", "Glycerin demonstrates strong humectancy"])
        ],
        recommended_ph_range="Recommended pH range: 5.5-6.2. This range optimizes stability and efficacy.",
        expected_benefits_analysis=[],
        raw_text="Sample formulation report for testing"
    )
    
    # Use the existing generate_ppt logic
    body = {"reportData": sample_report_data.dict()}
    return await generate_ppt(body)

@router.post("/formulation-report/test-pdf")
async def test_generate_pdf():
    """Test endpoint to generate PDF with sample data - for Swagger testing"""
    # Sample formulation report data based on your example
    sample_report_data = FormulationReportResponse(
        inci_list=[
            "Water",
            "Butylene Glycol",
            "Glycerin",
            "Caprylic/Capric Triglyceride",
            "Cetearyl Alcohol",
            "Niacinamide"
        ],
        analysis_table=[
            ReportTableRow(cells=["Ingredient", "Category", "Functions/Notes", "BIS Cautions"]),
            ReportTableRow(cells=["Water", "EXCIPIENT", "Primary solvent, base vehicle for the emulsion", "no bis cautions"]),
            ReportTableRow(cells=["Niacinamide", "ACTIVE", "Vitamin B3, brightening and tone-evening, barrier support", "no bis cautions"])
        ],
        compliance_panel=[
            ReportTableRow(cells=["Regulation", "Status", "Requirements"]),
            ReportTableRow(cells=["India Cosmetics Rules, 2020", "Generally compliant", "Provide complete ingredient list"])
        ],
        preservative_efficacy=[
            ReportTableRow(cells=["Preservative", "Efficacy", "pH Range", "Stability"]),
            ReportTableRow(cells=["1,2-Hexanediol", "Good broad-spectrum booster", "~3.0-10.0", "Thermally stable"])
        ],
        risk_panel=[
            ReportTableRow(cells=["Risk Factor", "Level", "Mitigation"]),
            ReportTableRow(cells=["Retinal irritation", "Medium", "Use low, well-validated dose"])
        ],
        cumulative_benefit=[
            ReportTableRow(cells=["Benefit", "Mechanism", "Evidence Level"]),
            ReportTableRow(cells=["Hydration", "Humectants attract/retain water", "Strong"])
        ],
        claim_panel=[
            ReportTableRow(cells=["Claim", "Support Level", "Evidence"]),
            ReportTableRow(cells=["Hydrates skin", "High", "Glycerin demonstrates strong humectancy"])
        ],
        recommended_ph_range="Recommended pH range: 5.5-6.2. This range optimizes stability and efficacy.",
        expected_benefits_analysis=[],
        raw_text="Sample formulation report for testing"
    )
    
    # Use the existing generate_pdf logic
    body = {"reportData": sample_report_data.dict()}
    return await generate_pdf(body)

@router.post("/formulation-report/pdf")
async def generate_pdf(body: dict = Body(...)):
    """Generate PDF presentation using Presenton API from report JSON data"""
    try:
        if not presenton_api_key:
            raise HTTPException(
                status_code=500,
                detail="PRESENTON_API_KEY environment variable not set. Please configure it in your .env file."
            )
        
        # Validate request body
        if not body or not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Request body must be a JSON object with 'reportData' field. Got: {type(body).__name__}"
            )
        
        if "reportData" not in body:
            raise HTTPException(
                status_code=400,
                detail=f"Missing 'reportData' in request body. Expected: {{'reportData': {{...}}}}. Got keys: {list(body.keys())}"
            )
        
        # Parse reportData into FormulationReportResponse
        from app.ai_ingredient_intelligence.models.schemas import FormulationReportResponse
        try:
            report_data = FormulationReportResponse(**body["reportData"])
        except Exception as e:
            print(f"❌ Error parsing reportData: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reportData format: {str(e)}"
            )
        
        print(f"✅ Parsed report data for PDF - INCI list: {len(report_data.inci_list)}, Analysis rows: {len(report_data.analysis_table)}")
        
        # Generate Presenton prompt using Claude
        try:
            presenton_prompt = await generate_presenton_prompt(report_data)
            print(f"📝 Generated Presenton prompt with instructions and content")
        except Exception as e:
            print(f"❌ Error generating Presenton prompt: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error generating Presenton prompt: {str(e)}"
            )
        
        # Call Presenton API to generate PDF
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Generate PDF presentation
            generate_response = await client.post(
                PRESENTON_GENERATE_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {presenton_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "instructions": presenton_prompt["instructions"],
                    "content": presenton_prompt["content"],
                    "export_as": "pdf",
                    "theme": "light-rose"
                }
            )
            
            if generate_response.status_code not in [200, 201]:
                error_text = generate_response.text
                try:
                    error_json = generate_response.json()
                    error_text = str(error_json)
                except:
                    pass
                raise HTTPException(
                    status_code=generate_response.status_code,
                    detail=f"Presenton API error: {error_text}"
                )
            
            try:
                generate_data = generate_response.json()
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Presenton API returned invalid JSON: {generate_response.text[:200]}"
                )
            
            # Presenton API returns presentation_id, path, and edit_path
            presentation_id = generate_data.get("presentation_id")
            file_path = generate_data.get("path")
            edit_path = generate_data.get("edit_path")
            
            if not presentation_id or not file_path:
                raise HTTPException(
                    status_code=500,
                    detail=f"Presenton API did not return required fields. Response: {generate_data}"
                )
            
            # Download the PDF file from Presenton
            # Handle different path formats: full URL, relative path, or absolute path
            if file_path.startswith("http://") or file_path.startswith("https://"):
                download_url = file_path
            elif file_path.startswith("/"):
                download_url = f"https://api.presenton.ai{file_path}"
            else:
                download_url = f"https://api.presenton.ai/{file_path}"
            
            print(f"📥 Downloading PDF from: {download_url}")
            
            download_response = await client.get(
                download_url,
                headers={
                    "Authorization": f"Bearer {presenton_api_key}"
                }
            )
            
            if download_response.status_code != 200:
                raise HTTPException(
                    status_code=download_response.status_code,
                    detail="Failed to download PDF file from Presenton"
                )
            
            # Return the PDF file with edit_path in headers for live editor access
            pdf_bytes = download_response.content
            if isinstance(pdf_bytes, str):
                pdf_bytes = pdf_bytes.encode('latin-1')
            
            headers = {
                "Content-Disposition": "attachment; filename=formulation_report.pdf",
                "Content-Type": "application/pdf"
            }
            
            # Add edit_path to response headers if available
            if edit_path:
                headers["X-Presenton-Edit-Path"] = f"https://presenton.ai{edit_path}"
                headers["X-Presenton-Presentation-Id"] = presentation_id
            
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers=headers
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PDF generation failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
