# app/ai_ingredient_intelligence/logic/bis_rag.py
"""
RAG module for Bureau of Indian Standards (BIS) documents
Retrieves caution information about ingredients from official BIS documents
"""
import os
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
import fitz  # PyMuPDF

# Try to import rapidfuzz for fuzzy matching, fallback to basic matching if not available
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    print("WARNING: rapidfuzz not available. Install with: pip install rapidfuzz")
    print("   Falling back to basic string matching.")

# BIS specific ChromaDB path
BIS_CHROMA_DB_PATH = os.path.join(Path(__file__).parent.parent.parent, "chroma_db_bis")
BIS_DATA_PATH = Path(__file__).parent.parent / "db" / "data"
BIS_MANIFEST_PATH = Path(BIS_CHROMA_DB_PATH) / "embed_manifest.json"

# Ensure directories exist
os.makedirs(BIS_CHROMA_DB_PATH, exist_ok=True)

# Global cache for vectorstore instance (singleton pattern)
_bis_vectorstore_cache: Optional[Chroma] = None
_bis_vectorstore_initialized = False


def load_bis_manifest() -> Dict[str, float]:
    """
    Load manifest file tracking embedded PDFs and their modification times.
    Returns dict mapping PDF filename to modification timestamp.
    """
    if BIS_MANIFEST_PATH.exists():
        try:
            with open(BIS_MANIFEST_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"WARNING: Error loading BIS manifest: {e}")
            return {}
    return {}


def save_bis_manifest(manifest: Dict[str, float]):
    """Save manifest file with embedded PDFs and their modification times."""
    try:
        BIS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BIS_MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception as e:
        print(f"WARNING: Error saving BIS manifest: {e}")


def get_pdf_modification_time(pdf_path: Path) -> float:
    """Get modification time of PDF file."""
    try:
        return pdf_path.stat().st_mtime
    except Exception:
        return 0.0


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF file"""
    try:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"WARNING: Error extracting text from {pdf_path.name}: {e}")
        return ""


def initialize_bis_vectorstore(force_reload: bool = False) -> Optional[Chroma]:
    """
    Initialize or load BIS vectorstore with caching and incremental embedding.
    
    Automatically detects new or modified PDFs and only embeds those,
    preserving existing embeddings for unchanged PDFs.
    
    Args:
        force_reload: If True, force re-initialization even if cached instance exists.
                      Useful for refreshing after adding new PDFs.
    
    Returns:
        Chroma vectorstore instance or None if initialization fails.
    """
    global _bis_vectorstore_cache, _bis_vectorstore_initialized
    
    # Return cached instance if available and not forcing reload
    if _bis_vectorstore_cache is not None and not force_reload:
        return _bis_vectorstore_cache
    
    try:
        embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )
        
        # Load manifest to track embedded PDFs
        manifest = load_bis_manifest()
        vectorstore_exists = os.path.exists(BIS_CHROMA_DB_PATH) and os.listdir(BIS_CHROMA_DB_PATH)
        
        # Get all PDF files
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        
        if not pdf_files:
            print(f"WARNING: No PDF files found in {BIS_DATA_PATH}")
            if not vectorstore_exists:
                return None
            # If vectorstore exists but no PDFs, just load it
            print("Loading existing BIS vectorstore...")
            vectorstore = Chroma(
                persist_directory=BIS_CHROMA_DB_PATH,
                embedding_function=embedding_model
            )
            _bis_vectorstore_cache = vectorstore
            _bis_vectorstore_initialized = True
            return vectorstore
        
        # Detect new or modified PDFs
        new_or_modified_pdfs = []
        for pdf_file in pdf_files:
            pdf_name = pdf_file.name
            current_mtime = get_pdf_modification_time(pdf_file)
            
            # Check if PDF is new or modified
            if pdf_name not in manifest:
                new_or_modified_pdfs.append((pdf_file, current_mtime))
                print(f"New PDF detected: {pdf_name}")
            elif manifest[pdf_name] != current_mtime:
                new_or_modified_pdfs.append((pdf_file, current_mtime))
                print(f"Modified PDF detected: {pdf_name}")
        
        # If vectorstore exists, load it; otherwise create new one
        if vectorstore_exists:
            print("Loading existing BIS vectorstore...")
            vectorstore = Chroma(
                persist_directory=BIS_CHROMA_DB_PATH,
                embedding_function=embedding_model
            )
        else:
            print("Creating new BIS vectorstore...")
            vectorstore = Chroma(
                embedding_function=embedding_model,
                persist_directory=BIS_CHROMA_DB_PATH
            )
            # Mark all PDFs as needing embedding for first-time creation
            new_or_modified_pdfs = [(pdf_file, get_pdf_modification_time(pdf_file)) for pdf_file in pdf_files]
        
        # Process and embed new/modified PDFs
        if new_or_modified_pdfs:
            print(f"Processing {len(new_or_modified_pdfs)} new/modified PDF(s)...")
            documents = []
            
            for pdf_file, mtime in new_or_modified_pdfs:
                print(f"Processing {pdf_file.name}...")
                text = extract_text_from_pdf(pdf_file)
                if text.strip():
                    # Split text into chunks
                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=1000,
                        chunk_overlap=200,
                        separators=["\n\n", "\n", ". ", " "]
                    )
                    chunks = splitter.split_text(text)
                    
                    for i, chunk in enumerate(chunks):
                        documents.append(Document(
                            page_content=chunk,
                            metadata={
                                "source": pdf_file.name,
                                "chunk_index": i,
                                "document_type": "BIS_Standard"
                            }
                        ))
                    
                    # Update manifest with new modification time
                    manifest[pdf_file.name] = mtime
                else:
                    print(f"WARNING: Skipping {pdf_file.name} - empty or unreadable")
            
            if documents:
                # Add new documents to existing vectorstore in batches
                batch_size = 50
                for i in range(0, len(documents), batch_size):
                    batch = documents[i:i + batch_size]
                    vectorstore.add_documents(documents=batch)
                
                # Save updated manifest
                save_bis_manifest(manifest)
                print(f"Added {len(documents)} new chunks from {len(new_or_modified_pdfs)} PDF(s)")
            else:
                print("WARNING: No documents extracted from new/modified PDFs")
        else:
            if not vectorstore_exists:
                print("WARNING: No PDFs to process and vectorstore doesn't exist")
                return None
            print("All PDFs are up to date, no new embeddings needed")
        
        # Cache the instance
        _bis_vectorstore_cache = vectorstore
        _bis_vectorstore_initialized = True
        return vectorstore
        
    except Exception as e:
        print(f"WARNING: Could not initialize BIS vectorstore: {e}")
        print("   Reports will continue without BIS cautions. This is not critical.")
        import traceback
        traceback.print_exc()
        return None


def clear_bis_vectorstore_cache():
    """
    Clear the cached BIS vectorstore instance.
    Useful when you've added new PDFs and want to force re-initialization.
    Next call to get_bis_retriever() will reload the vectorstore.
    """
    global _bis_vectorstore_cache, _bis_vectorstore_initialized
    _bis_vectorstore_cache = None
    _bis_vectorstore_initialized = False
    print("BIS vectorstore cache cleared")


def get_bis_retriever():
    """
    Get BIS document retriever.
    Uses cached vectorstore instance for efficiency.
    Creates a new retriever from the cached vectorstore (lightweight operation).
    """
    vectorstore = initialize_bis_vectorstore()
    if vectorstore is None:
        return None
    
    # Creating a retriever is lightweight - it's just a wrapper around the vectorstore
    # The vectorstore itself is cached, so this is efficient
    # Increase k and fetch_k for better coverage
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 10, "fetch_k": 20}  # Increased for better retrieval
    )
    return retriever


async def get_bis_cautions_for_single_ingredient(ingredient: str, retriever) -> Tuple[str, List[str]]:
    """
    Get BIS cautions for a single ingredient (helper function for parallelization).
    Returns tuple of (ingredient_name, cautions_list).
    """
    import re
    
    # Early exit for water-related ingredients
    ingredient_lower = ingredient.lower()
    water_related_keywords = ['water', 'aqua']
    if any(water_term in ingredient_lower for water_term in water_related_keywords):
        return (ingredient, [])
    
    try:
        # Reduced queries from 13 to 4 most effective ones
        queries = [
            f"{ingredient}",
            f"{ingredient} caution",
            f"{ingredient} limit maximum",
            f"{ingredient} regulation"
        ]
        
        all_docs = []
        seen_doc_ids = set()
        
        # Collect documents from all queries
        for query in queries:
            try:
                docs = retriever.invoke(query)
                for doc in docs:
                    doc_id = f"{doc.metadata.get('source', '')}_{doc.metadata.get('chunk_index', '')}"
                    if doc_id not in seen_doc_ids:
                        seen_doc_ids.add(doc_id)
                        all_docs.append(doc)
            except Exception as e:
                print(f"Warning: Error in query '{query}': {e}")
                continue
        
        # Extract relevant information from all documents
        cautions = []
        
        # Expand search keywords for better coverage - focus on numerical limits
        caution_keywords = [
            'caution', 'warning', 'restriction', 'limit', 'maximum', 'minimum',
            'prohibited', 'not allowed', 'should not', 'avoid', 'must not',
            'instruction', 'requirement', 'mandatory', 'compliance', 'regulation',
            'standard', 'guideline', 'specification', 'condition', 'precaution',
            'percent', 'percentage', '%', 'w/w', 'w/v', 'concentration', 'amount',
            'not exceed', 'shall not exceed', 'must not exceed', 'should not exceed',
            'column', 'table', 'mg/kg', 'ppm', 'g/kg', 'mg/l', 'g/l'
        ]
        
        # Pattern to match numerical values (percentages, limits, concentrations)
        number_pattern = re.compile(r'\d+\.?\d*\s*(?:%|percent|w/w|w/v|mg/kg|ppm|g/kg|mg/l|g/l|mg|g|kg|ml|l)?', re.IGNORECASE)
        
        for doc in all_docs:
            content = doc.page_content
            content_lower = content.lower()
            
            # Check if document contains caution-related information
            if any(keyword in content_lower for keyword in caution_keywords):
                # PRIORITY: Extract sentences/paragraphs with NUMBERS (limits, percentages, concentrations)
                # Strategy 1: Extract complete sentences with numbers and ingredient mention
                sentences = content.split('.')
                for sentence in sentences:
                    sentence_clean = sentence.strip()
                    if sentence_clean and ingredient_lower in sentence_clean.lower():
                        # Prioritize sentences with numbers (limits, percentages)
                        has_number = bool(number_pattern.search(sentence_clean))
                        has_caution_keyword = any(keyword in sentence_clean.lower() for keyword in caution_keywords)
                        
                        if has_caution_keyword:
                            # If it has a number, prioritize it; otherwise include if it has caution keywords
                            if has_number:
                                # Ensure sentence is complete and includes the number
                                if len(sentence_clean) > 20:  # Avoid very short fragments
                                    cautions.insert(0, sentence_clean)  # Insert at beginning (higher priority)
                            else:
                                cautions.append(sentence_clean)
                
                # Strategy 2: Extract lines with numbers (for structured documents like tables)
                lines = content.split('\n')
                for line in lines:
                    line_clean = line.strip()
                    if line_clean and ingredient_lower in line_clean.lower():
                        has_number = bool(number_pattern.search(line_clean))
                        has_caution_keyword = any(keyword in line_clean.lower() for keyword in caution_keywords)
                        
                        if has_caution_keyword:
                            if has_number:
                                if len(line_clean) > 15:  # Avoid very short fragments
                                    cautions.insert(0, line_clean)  # Insert at beginning (higher priority)
                            else:
                                cautions.append(line_clean)
                
                # Strategy 3: Extract paragraphs with numbers
                paragraphs = content.split('\n\n')
                for para in paragraphs:
                    para_clean = para.strip()
                    if para_clean and ingredient_lower in para_clean.lower():
                        has_number = bool(number_pattern.search(para_clean))
                        has_caution_keyword = any(keyword in para_clean.lower() for keyword in caution_keywords)
                        
                        if has_caution_keyword:
                            if has_number:
                                # If paragraph has numbers, prioritize it
                                if len(para_clean) < 500:  # Keep reasonable length
                                    cautions.insert(0, para_clean)  # Insert at beginning
                                else:
                                    # Split long paragraphs but keep sentences with numbers
                                    para_sentences = para_clean.split('.')
                                    for sent in para_sentences:
                                        sent_clean = sent.strip()
                                        if sent_clean and ingredient_lower in sent_clean.lower():
                                            if bool(number_pattern.search(sent_clean)):
                                                if len(sent_clean) > 20:
                                                    cautions.insert(0, sent_clean)
                            else:
                                # Paragraph without numbers but has caution keywords
                                if len(para_clean) < 300:
                                    cautions.append(para_clean)
                                else:
                                    # Split long paragraphs
                                    para_sentences = para_clean.split('.')
                                    for sent in para_sentences:
                                        sent_clean = sent.strip()
                                        if sent_clean and ingredient_lower in sent_clean.lower():
                                            if any(keyword in sent_clean.lower() for keyword in caution_keywords):
                                                cautions.append(sent_clean)
        
        if cautions:
            # Remove duplicates while preserving order, prioritizing cautions with numbers
            unique_cautions = []
            seen = set()
            
            # First pass: Add cautions with numbers (prioritized)
            for caution in cautions:
                caution_normalized = caution.lower().strip()
                if caution_normalized and caution_normalized not in seen:
                    has_number = bool(re.search(r'\d+\.?\d*\s*(?:%|percent|w/w|w/v|mg/kg|ppm|g/kg|mg/l|g/l|mg|g|kg|ml|l)', caution, re.IGNORECASE))
                    if has_number:
                        seen.add(caution_normalized)
                        unique_cautions.append(caution)
            
            # Second pass: Add remaining cautions without numbers
            for caution in cautions:
                caution_normalized = caution.lower().strip()
                if caution_normalized and caution_normalized not in seen:
                    seen.add(caution_normalized)
                    unique_cautions.append(caution)
            
            # Clean up: Remove vague references like "column given" and replace with actual context
            cleaned_cautions = []
            
            # Common ingredients that shouldn't have generic safety cautions (unless they have specific numerical limits)
            common_ingredients_no_generic_cautions = [
                'glycerin', 'glycerol', 'dimethicone', 
                'propylene glycol', 'butylene glycol', 'squalane', 'squalene'
            ]
            
            is_common_ingredient = any(common in ingredient_lower for common in common_ingredients_no_generic_cautions)
            
            for caution in unique_cautions:
                # If caution mentions "column" but doesn't have actual numbers, try to find context
                if 'column' in caution.lower() and not re.search(r'\d+\.?\d*', caution):
                    # Skip vague column references without numbers
                    continue
                
                # For common ingredients, filter out generic safety cautions unless they have numerical limits
                if is_common_ingredient:
                    caution_lower = caution.lower()
                    # Skip generic safety cautions that don't have numerical values
                    generic_safety_phrases = [
                        'avoid contact with eyes',
                        'avoid contact with eye',
                        'keep away from eyes',
                        'keep away from eye',
                        'do not get in eyes',
                        'do not get in eye',
                        'not for use in eyes',
                        'for external use only',
                        'external use only'
                    ]
                    # Additional filtering for terms that should not appear in responses
                    unwanted_terms = [
                        'pregnancy safe',
                        'pregnancy-safe',
                        'fungal acne',
                        'fungal-acne',
                        'acne free',
                        'acne-free'
                    ]
                    has_generic_phrase = any(phrase in caution_lower for phrase in generic_safety_phrases)
                    has_unwanted_term = any(term in caution_lower for term in unwanted_terms)
                    has_numerical_limit = bool(re.search(r'\d+\.?\d*\s*(?:%|percent|w/w|w/v|mg/kg|ppm|g/kg|mg/l|g/l|mg|g|kg|ml|l)', caution, re.IGNORECASE))
                    
                    # Skip generic safety cautions that don't have numerical limits OR contain unwanted terms
                    if (has_generic_phrase and not has_numerical_limit) or has_unwanted_term:
                        continue
                
                # Ensure caution is meaningful (at least 15 characters - reduced threshold for better coverage)
                if len(caution.strip()) >= 15:
                    cleaned_cautions.append(caution.strip())
            
            if cleaned_cautions:
                # Limit to top 10 most relevant cautions to avoid overwhelming
                final_cautions = cleaned_cautions[:10]
                print(f"✅ Retrieved {len(final_cautions)} caution(s) for {ingredient} (from {len(all_docs)} documents)")
                return (ingredient, final_cautions)
            else:
                print(f"⚠️ No valid cautions found for {ingredient} (searched {len(all_docs)} documents)")
                return (ingredient, [])
        else:
            print(f"⚠️ No cautions found for {ingredient}")
            return (ingredient, [])
    except Exception as e:
        print(f"WARNING: Error retrieving BIS cautions for {ingredient}: {e}")
        return (ingredient, [])


async def get_bis_cautions_for_ingredients(ingredient_names: List[str]) -> Dict[str, List[str]]:
    """
    Get BIS caution information for given ingredients (OPTIMIZED: parallelized).
    Returns dict mapping ingredient names to list of caution texts
    Retrieves ALL cautions/instructions without limiting the count
    """
    import asyncio
    
    try:
        retriever = get_bis_retriever()
        if retriever is None:
            return {}
    except Exception as e:
        print(f"WARNING: BIS retriever not available: {e}")
        return {}
    
    # Filter out water-related ingredients early (before parallelization)
    filtered_ingredients = []
    for ingredient in ingredient_names:
        ingredient_lower = ingredient.lower()
        water_related_keywords = ['water', 'aqua']
        if not any(water_term in ingredient_lower for water_term in water_related_keywords):
            filtered_ingredients.append(ingredient)
    
    if not filtered_ingredients:
        return {}
    
    # Process all ingredients in parallel
    tasks = [get_bis_cautions_for_single_ingredient(ingredient, retriever) for ingredient in filtered_ingredients]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Build result map - include all ingredients (even with empty lists) to maintain exact behavior
    cautions_map = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"WARNING: Exception in BIS retrieval: {result}")
            continue
        ingredient, cautions = result
        # Always add ingredient to map (even if empty list) to maintain exact behavior
        cautions_map[ingredient] = cautions
    
    return cautions_map


async def get_bis_cautions_batch(ingredient_names: List[str]) -> str:
    """
    Get BIS cautions for all ingredients in batch and format as text
    Returns formatted string for LLM prompt
    """
    try:
        cautions_map = await get_bis_cautions_for_ingredients(ingredient_names)
        
        if not cautions_map:
            return "No specific BIS cautions found for the provided ingredients."
        
        formatted_cautions = ["Bureau of Indian Standards (BIS) Cautions:"]
        formatted_cautions.append("=" * 50)
        
        for ingredient, cautions in cautions_map.items():
            formatted_cautions.append(f"\n{ingredient}:")
            for i, caution in enumerate(cautions, 1):
                formatted_cautions.append(f"  {i}. {caution}")
        
        return "\n".join(formatted_cautions)
    except Exception as e:
        print(f"WARNING: Error retrieving BIS cautions: {e}")
        return "BIS cautions retrieval temporarily unavailable. Proceeding with report generation."


def check_bis_rag_health() -> Dict[str, any]:
    """
    Comprehensive health check for BIS RAG system.
    Returns dict with status, errors, and diagnostic information.
    """
    health = {
        "status": "unknown",
        "errors": [],
        "pdf_files": 0,
        "vectorstore_exists": False,
        "vectorstore_initialized": False,
        "retriever_created": False,
        "test_query_successful": False
    }
    
    try:
        # Check PDF files
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        health["pdf_files"] = len(pdf_files)
        
        # Check vectorstore existence
        health["vectorstore_exists"] = os.path.exists(BIS_CHROMA_DB_PATH) and bool(os.listdir(BIS_CHROMA_DB_PATH))
        
        # Try to initialize vectorstore
        try:
            vectorstore = initialize_bis_vectorstore()
            health["vectorstore_initialized"] = vectorstore is not None
        except Exception as e:
            health["errors"].append(f"Vectorstore initialization failed: {str(e)}")
        
        # Try to create retriever
        try:
            retriever = get_bis_retriever()
            health["retriever_created"] = retriever is not None
        except Exception as e:
            health["errors"].append(f"Retriever creation failed: {str(e)}")
        
        # Try a test query
        if health["retriever_created"]:
            try:
                retriever = get_bis_retriever()
                test_docs = retriever.invoke("test")
                health["test_query_successful"] = len(test_docs) > 0 if test_docs else False
            except Exception as e:
                health["errors"].append(f"Test query failed: {str(e)}")
        
        # Determine overall status
        if health["vectorstore_initialized"] and health["retriever_created"]:
            if health["test_query_successful"]:
                health["status"] = "healthy"
            else:
                health["status"] = "retriever_failed"
        else:
            health["status"] = "unhealthy"
            
    except Exception as e:
        health["status"] = "error"
        health["errors"].append(f"Health check failed: {str(e)}")
    
    return health
