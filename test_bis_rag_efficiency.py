#!/usr/bin/env python3
"""
BIS RAG Efficiency Test Script
Tests the BIS RAG system for document parsing, embedding, retrieval, and extraction efficiency.
Uses AI to analyze and report on the system's performance.
"""

import os
import sys
import time
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import BIS RAG functions
from app.ai_ingredient_intelligence.logic.bis_rag import (
    initialize_bis_vectorstore,
    get_bis_retriever,
    get_bis_cautions_for_ingredients,
    extract_text_from_pdf,
    load_bis_manifest,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH,
    BIS_MANIFEST_PATH,
    clear_bis_vectorstore_cache
)

# Import OpenAI for efficiency analysis
from openai import OpenAI

# Test ingredients (common cosmetic ingredients that might have BIS cautions)
TEST_INGREDIENTS = [
    "Salicylic Acid",
    "Benzoyl Peroxide",
    "Hydroquinone",
    "Retinol",
    "Alpha Hydroxy Acid",
    "Beta Hydroxy Acid",
    "Formaldehyde",
    "Parabens",
    "Triclosan",
    "Lead",
    "Mercury",
    "Zinc Oxide",
    "Titanium Dioxide",
    "Glycerin",
    "Aqua"
]

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_section(text: str):
    """Print formatted section"""
    print(f"\n{Colors.OKCYAN}{Colors.BOLD}▶ {text}{Colors.ENDC}")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.OKBLUE}ℹ️  {text}{Colors.ENDC}")

def test_pdf_files_exist() -> Tuple[bool, List[Path]]:
    """Test 1: Check if BIS PDF files exist"""
    print_section("Test 1: Checking BIS PDF Files")
    
    pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
    
    if not BIS_DATA_PATH.exists():
        print_error(f"BIS data directory does not exist: {BIS_DATA_PATH}")
        return False, []
    
    print_info(f"BIS data directory: {BIS_DATA_PATH}")
    
    if not pdf_files:
        print_error(f"No PDF files found in {BIS_DATA_PATH}")
        return False, []
    
    print_success(f"Found {len(pdf_files)} PDF file(s):")
    for pdf_file in pdf_files:
        file_size = pdf_file.stat().st_size / (1024 * 1024)  # Size in MB
        print(f"   • {pdf_file.name} ({file_size:.2f} MB)")
    
    return True, pdf_files

def test_pdf_text_extraction(pdf_files: List[Path]) -> Dict[str, Dict]:
    """Test 2: Test PDF text extraction"""
    print_section("Test 2: Testing PDF Text Extraction")
    
    results = {}
    
    for pdf_file in pdf_files:
        print_info(f"Extracting text from {pdf_file.name}...")
        start_time = time.time()
        
        try:
            text = extract_text_from_pdf(pdf_file)
            extraction_time = time.time() - start_time
            
            if not text or not text.strip():
                print_error(f"Failed to extract text from {pdf_file.name}")
                results[pdf_file.name] = {
                    "success": False,
                    "text_length": 0,
                    "extraction_time": extraction_time,
                    "error": "Empty text extracted"
                }
                continue
            
            text_length = len(text)
            word_count = len(text.split())
            line_count = len(text.split('\n'))
            
            print_success(f"Extracted {text_length:,} characters, {word_count:,} words, {line_count:,} lines")
            print_info(f"Extraction time: {extraction_time:.3f} seconds")
            
            # Show sample text (first 200 chars)
            sample = text[:200].replace('\n', ' ')
            print(f"   Sample: {sample}...")
            
            results[pdf_file.name] = {
                "success": True,
                "text_length": text_length,
                "word_count": word_count,
                "line_count": line_count,
                "extraction_time": extraction_time
            }
            
        except Exception as e:
            print_error(f"Error extracting text from {pdf_file.name}: {e}")
            results[pdf_file.name] = {
                "success": False,
                "error": str(e)
            }
    
    return results

def test_vectorstore_initialization() -> Tuple[Optional[object], Dict]:
    """Test 3: Test vectorstore initialization"""
    print_section("Test 3: Testing Vectorstore Initialization")
    
    # Clear cache to force fresh initialization
    clear_bis_vectorstore_cache()
    
    start_time = time.time()
    
    try:
        vectorstore = initialize_bis_vectorstore(force_reload=False)
        init_time = time.time() - start_time
        
        if vectorstore is None:
            print_error("Vectorstore initialization failed")
            return None, {
                "success": False,
                "init_time": init_time,
                "error": "Vectorstore is None"
            }
        
        print_success(f"Vectorstore initialized successfully in {init_time:.3f} seconds")
        
        # Check if vectorstore has documents
        try:
            # Try to get collection count (ChromaDB specific)
            collection = vectorstore._collection
            if hasattr(collection, 'count'):
                doc_count = collection.count()
                print_info(f"Vectorstore contains {doc_count:,} document chunks")
            else:
                print_warning("Could not determine document count")
                doc_count = None
        except Exception as e:
            print_warning(f"Could not get document count: {e}")
            doc_count = None
        
        # Check manifest
        manifest = load_bis_manifest()
        print_info(f"Manifest tracks {len(manifest)} PDF file(s)")
        
        return vectorstore, {
            "success": True,
            "init_time": init_time,
            "doc_count": doc_count,
            "manifest_files": len(manifest)
        }
        
    except Exception as e:
        print_error(f"Vectorstore initialization error: {e}")
        import traceback
        traceback.print_exc()
        return None, {
            "success": False,
            "init_time": time.time() - start_time,
            "error": str(e)
        }

def test_retriever_creation() -> Tuple[Optional[object], Dict]:
    """Test 4: Test retriever creation"""
    print_section("Test 4: Testing Retriever Creation")
    
    start_time = time.time()
    
    try:
        retriever = get_bis_retriever()
        creation_time = time.time() - start_time
        
        if retriever is None:
            print_error("Retriever creation failed")
            return None, {
                "success": False,
                "creation_time": creation_time,
                "error": "Retriever is None"
            }
        
        print_success(f"Retriever created successfully in {creation_time:.3f} seconds")
        
        return retriever, {
            "success": True,
            "creation_time": creation_time
        }
        
    except Exception as e:
        print_error(f"Retriever creation error: {e}")
        return None, {
            "success": False,
            "creation_time": time.time() - start_time,
            "error": str(e)
        }

def test_document_retrieval(retriever, test_queries: List[str]) -> Dict[str, Dict]:
    """Test 5: Test document retrieval"""
    print_section("Test 5: Testing Document Retrieval")
    
    results = {}
    
    for query in test_queries:
        print_info(f"Query: '{query}'")
        start_time = time.time()
        
        try:
            docs = retriever.invoke(query)
            retrieval_time = time.time() - start_time
            
            if not docs:
                print_warning(f"No documents retrieved for query: '{query}'")
                results[query] = {
                    "success": False,
                    "doc_count": 0,
                    "retrieval_time": retrieval_time
                }
                continue
            
            print_success(f"Retrieved {len(docs)} document(s) in {retrieval_time:.3f} seconds")
            
            # Analyze retrieved documents
            sources = {}
            total_content_length = 0
            
            for i, doc in enumerate(docs):
                source = doc.metadata.get('source', 'unknown')
                chunk_idx = doc.metadata.get('chunk_index', 'unknown')
                content_length = len(doc.page_content)
                total_content_length += content_length
                
                if source not in sources:
                    sources[source] = []
                sources[source].append({
                    "chunk_index": chunk_idx,
                    "content_length": content_length,
                    "preview": doc.page_content[:100].replace('\n', ' ')
                })
            
            print(f"   Sources: {', '.join(sources.keys())}")
            print(f"   Total content: {total_content_length:,} characters")
            
            results[query] = {
                "success": True,
                "doc_count": len(docs),
                "retrieval_time": retrieval_time,
                "sources": list(sources.keys()),
                "total_content_length": total_content_length
            }
            
        except Exception as e:
            print_error(f"Retrieval error for query '{query}': {e}")
            results[query] = {
                "success": False,
                "error": str(e)
            }
    
    return results

async def test_ingredient_caution_extraction(test_ingredients: List[str]) -> Dict[str, Dict]:
    """Test 6: Test ingredient caution extraction"""
    print_section("Test 6: Testing Ingredient Caution Extraction")
    
    results = {}
    
    for ingredient in test_ingredients:
        print_info(f"Testing ingredient: {ingredient}")
        start_time = time.time()
        
        try:
            cautions_map = await get_bis_cautions_for_ingredients([ingredient])
            extraction_time = time.time() - start_time
            
            if not cautions_map:
                print_warning(f"No cautions found for {ingredient}")
                results[ingredient] = {
                    "success": False,
                    "caution_count": 0,
                    "extraction_time": extraction_time
                }
                continue
            
            if ingredient not in cautions_map:
                print_warning(f"Ingredient '{ingredient}' not in cautions map")
                results[ingredient] = {
                    "success": False,
                    "caution_count": 0,
                    "extraction_time": extraction_time
                }
                continue
            
            cautions = cautions_map[ingredient]
            caution_count = len(cautions)
            
            if caution_count == 0:
                print_warning(f"No cautions found for {ingredient}")
                results[ingredient] = {
                    "success": False,
                    "caution_count": 0,
                    "extraction_time": extraction_time
                }
            else:
                print_success(f"Found {caution_count} caution(s) for {ingredient} in {extraction_time:.3f} seconds")
                
                # Show first caution preview
                if cautions:
                    first_caution = cautions[0][:150].replace('\n', ' ')
                    print(f"   First caution: {first_caution}...")
                
                results[ingredient] = {
                    "success": True,
                    "caution_count": caution_count,
                    "extraction_time": extraction_time,
                    "cautions_preview": [c[:200] for c in cautions[:3]]  # First 3 cautions, first 200 chars
                }
            
        except Exception as e:
            print_error(f"Error extracting cautions for {ingredient}: {e}")
            results[ingredient] = {
                "success": False,
                "error": str(e)
            }
    
    return results

def generate_efficiency_report(test_results: Dict) -> str:
    """Generate efficiency report using AI"""
    print_section("Generating AI Efficiency Analysis")
    
    # Prepare summary data
    summary = {
        "test_timestamp": datetime.now().isoformat(),
        "pdf_files_test": test_results.get("pdf_files_test", {}),
        "text_extraction_test": test_results.get("text_extraction_test", {}),
        "vectorstore_test": test_results.get("vectorstore_test", {}),
        "retriever_test": test_results.get("retriever_test", {}),
        "retrieval_test": test_results.get("retrieval_test", {}),
        "caution_extraction_test": test_results.get("caution_extraction_test", {})
    }
    
    # Calculate statistics
    stats = {
        "pdf_files_found": len(test_results.get("pdf_files", [])),
        "pdf_extraction_success_rate": 0,
        "vectorstore_initialized": test_results.get("vectorstore_test", {}).get("success", False),
        "retriever_created": test_results.get("retriever_test", {}).get("success", False),
        "avg_retrieval_time": 0,
        "ingredients_with_cautions": 0,
        "total_cautions_found": 0
    }
    
    # Calculate extraction success rate
    extraction_results = test_results.get("text_extraction_test", {})
    if extraction_results:
        successful = sum(1 for r in extraction_results.values() if r.get("success", False))
        total = len(extraction_results)
        stats["pdf_extraction_success_rate"] = (successful / total * 100) if total > 0 else 0
    
    # Calculate average retrieval time
    retrieval_results = test_results.get("retrieval_test", {})
    if retrieval_results:
        times = [r.get("retrieval_time", 0) for r in retrieval_results.values() if r.get("success", False)]
        stats["avg_retrieval_time"] = sum(times) / len(times) if times else 0
    
    # Calculate caution extraction stats
    caution_results = test_results.get("caution_extraction_test", {})
    if caution_results:
        ingredients_with_cautions = sum(1 for r in caution_results.values() if r.get("success", False) and r.get("caution_count", 0) > 0)
        total_cautions = sum(r.get("caution_count", 0) for r in caution_results.values())
        stats["ingredients_with_cautions"] = ingredients_with_cautions
        stats["total_cautions_found"] = total_cautions
    
    # Create prompt for AI analysis
    prompt = f"""You are an AI efficiency analyst. Analyze the following BIS RAG system test results and provide a comprehensive efficiency report.

TEST RESULTS SUMMARY:
{json.dumps(stats, indent=2)}

DETAILED RESULTS:
{json.dumps(summary, indent=2, default=str)}

Please provide:
1. Overall System Health Assessment (Excellent/Good/Fair/Poor)
2. Key Strengths of the RAG system
3. Key Weaknesses and Issues
4. Performance Metrics Analysis:
   - Document parsing efficiency
   - Embedding quality
   - Retrieval accuracy and speed
   - Caution extraction effectiveness
5. Specific Recommendations for Improvement
6. Efficiency Score (0-100) with justification

Format your response as a structured report with clear sections."""

    # Get OpenAI API key
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print_warning("OPENAI_API_KEY not found. Skipping AI analysis.")
        return "AI analysis skipped - OPENAI_API_KEY not set"
    
    try:
        client = OpenAI(api_key=openai_api_key)
        
        print_info("Requesting AI efficiency analysis...")
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert AI systems analyst specializing in RAG (Retrieval Augmented Generation) systems. Provide detailed, technical, and actionable efficiency analysis."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_completion_tokens=2000
        )
        
        ai_report = response.choices[0].message.content
        print_success("AI efficiency analysis generated")
        return ai_report
        
    except Exception as e:
        print_error(f"Error generating AI report: {e}")
        return f"AI analysis failed: {str(e)}"

async def main_async():
    """Main test execution (async)"""
    print_header("BIS RAG Efficiency Test Suite")
    
    print_info(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Project root: {project_root}")
    print_info(f"BIS data path: {BIS_DATA_PATH}")
    print_info(f"BIS ChromaDB path: {BIS_CHROMA_DB_PATH}")
    
    test_results = {}
    
    # Test 1: Check PDF files
    pdf_files_exist, pdf_files = test_pdf_files_exist()
    test_results["pdf_files"] = [str(p) for p in pdf_files]  # Convert Path to string for JSON
    test_results["pdf_files_test"] = {"success": pdf_files_exist, "count": len(pdf_files)}
    
    if not pdf_files_exist:
        print_error("Cannot proceed without PDF files. Exiting.")
        return
    
    # Test 2: PDF text extraction
    extraction_results = test_pdf_text_extraction(pdf_files)
    test_results["text_extraction_test"] = extraction_results
    
    # Test 3: Vectorstore initialization
    vectorstore, vectorstore_info = test_vectorstore_initialization()
    test_results["vectorstore_test"] = vectorstore_info
    
    if not vectorstore:
        print_error("Cannot proceed without vectorstore. Exiting.")
        return
    
    # Test 4: Retriever creation
    retriever, retriever_info = test_retriever_creation()
    test_results["retriever_test"] = retriever_info
    
    if not retriever:
        print_error("Cannot proceed without retriever. Exiting.")
        return
    
    # Test 5: Document retrieval
    test_queries = [
        "salicylic acid caution warning",
        "benzoyl peroxide restriction",
        "hydroquinone limit",
        "formaldehyde prohibited",
        "parabens regulation"
    ]
    retrieval_results = test_document_retrieval(retriever, test_queries)
    test_results["retrieval_test"] = retrieval_results
    
    # Test 6: Ingredient caution extraction (async)
    caution_results = await test_ingredient_caution_extraction(TEST_INGREDIENTS)
    test_results["caution_extraction_test"] = caution_results
    
    # Generate AI efficiency report
    ai_report = generate_efficiency_report(test_results)
    
    # Print final summary
    print_header("Test Summary")
    
    print_section("PDF Files")
    print(f"   Found: {len(pdf_files)} file(s)")
    
    print_section("Text Extraction")
    extraction_success = sum(1 for r in extraction_results.values() if r.get("success", False))
    print(f"   Success rate: {extraction_success}/{len(extraction_results)} ({extraction_success/len(extraction_results)*100:.1f}%)")
    
    print_section("Vectorstore")
    print(f"   Initialized: {'Yes' if vectorstore_info.get('success') else 'No'}")
    if vectorstore_info.get('doc_count'):
        print(f"   Document chunks: {vectorstore_info.get('doc_count'):,}")
    
    print_section("Retriever")
    print(f"   Created: {'Yes' if retriever_info.get('success') else 'No'}")
    
    print_section("Document Retrieval")
    retrieval_success = sum(1 for r in retrieval_results.values() if r.get("success", False))
    print(f"   Success rate: {retrieval_success}/{len(retrieval_results)} ({retrieval_success/len(retrieval_results)*100:.1f}%)")
    
    print_section("Caution Extraction")
    ingredients_with_cautions = sum(1 for r in caution_results.values() if r.get("success", False) and r.get("caution_count", 0) > 0)
    total_cautions = sum(r.get("caution_count", 0) for r in caution_results.values())
    print(f"   Ingredients with cautions: {ingredients_with_cautions}/{len(TEST_INGREDIENTS)}")
    print(f"   Total cautions found: {total_cautions}")
    
    # Print AI report
    print_header("AI Efficiency Analysis Report")
    print(ai_report)
    
    # Save results to file
    output_file = project_root / "bis_rag_test_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_timestamp": datetime.now().isoformat(),
                "test_results": test_results,
                "ai_report": ai_report
            }, f, indent=2, default=str)
        print_success(f"Test results saved to: {output_file}")
    except Exception as e:
        print_warning(f"Could not save results to file: {e}")
    
    print_header("Test Complete")
    print_info(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    """Main entry point - runs async main"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()

