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
    print("⚠️ rapidfuzz not available. Install with: pip install rapidfuzz")
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
            print(f"⚠️ Error loading BIS manifest: {e}")
            return {}
    return {}


def save_bis_manifest(manifest: Dict[str, float]):
    """Save manifest file with embedded PDFs and their modification times."""
    try:
        BIS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BIS_MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving BIS manifest: {e}")


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
        print(f"⚠️ Error extracting text from {pdf_path.name}: {e}")
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
            print(f"⚠️ No PDF files found in {BIS_DATA_PATH}")
            if not vectorstore_exists:
                return None
            # If vectorstore exists but no PDFs, just load it
            print("📚 Loading existing BIS vectorstore...")
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
                print(f"📄 New PDF detected: {pdf_name}")
            elif manifest[pdf_name] != current_mtime:
                new_or_modified_pdfs.append((pdf_file, current_mtime))
                print(f"📄 Modified PDF detected: {pdf_name}")
        
        # If vectorstore exists, load it; otherwise create new one
        if vectorstore_exists:
            print("📚 Loading existing BIS vectorstore...")
            vectorstore = Chroma(
                persist_directory=BIS_CHROMA_DB_PATH,
                embedding_function=embedding_model
            )
        else:
            print("📚 Creating new BIS vectorstore...")
            vectorstore = Chroma(
                embedding_function=embedding_model,
                persist_directory=BIS_CHROMA_DB_PATH
            )
            # Mark all PDFs as needing embedding for first-time creation
            new_or_modified_pdfs = [(pdf_file, get_pdf_modification_time(pdf_file)) for pdf_file in pdf_files]
        
        # Process and embed new/modified PDFs
        if new_or_modified_pdfs:
            print(f"🔄 Processing {len(new_or_modified_pdfs)} new/modified PDF(s)...")
            documents = []
            
            for pdf_file, mtime in new_or_modified_pdfs:
                print(f"📄 Processing {pdf_file.name}...")
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
                    print(f"⚠️ Skipping {pdf_file.name} — empty or unreadable")
            
            if documents:
                # Add new documents to existing vectorstore in batches
                batch_size = 50
                for i in range(0, len(documents), batch_size):
                    batch = documents[i:i + batch_size]
                    vectorstore.add_documents(documents=batch)
                
                # Save updated manifest
                save_bis_manifest(manifest)
                print(f"✅ Added {len(documents)} new chunks from {len(new_or_modified_pdfs)} PDF(s)")
            else:
                print("⚠️ No documents extracted from new/modified PDFs")
        else:
            if not vectorstore_exists:
                print("⚠️ No PDFs to process and vectorstore doesn't exist")
                return None
            print("✅ All PDFs are up to date, no new embeddings needed")
        
        # Cache the instance
        _bis_vectorstore_cache = vectorstore
        _bis_vectorstore_initialized = True
        return vectorstore
        
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize BIS vectorstore: {e}")
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
    print("🔄 BIS vectorstore cache cleared")


def normalize_ingredient_name(name: str) -> str:
    """
    Normalize ingredient name for better matching.
    - Removes accents and special characters
    - Converts to lowercase
    - Removes extra whitespace
    - Removes common prefixes/suffixes that might vary
    """
    if not name:
        return ""
    
    # Remove accents and normalize unicode
    normalized = unicodedata.normalize("NFKD", name)
    # Convert to ASCII, ignoring non-ASCII characters
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    
    # Convert to lowercase
    normalized = normalized.lower()
    
    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    # Remove common punctuation that might cause mismatches
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    return normalized


def extract_ingredient_variations(text: str, base_ingredient: str) -> List[str]:
    """
    Extract potential ingredient name variations from text.
    Looks for words/phrases that might be variations of the ingredient name.
    """
    variations = [base_ingredient]
    normalized_base = normalize_ingredient_name(base_ingredient)
    
    # Split base ingredient into words
    base_words = normalized_base.split()
    
    # Look for potential variations in text (case-insensitive)
    text_lower = text.lower()
    
    # Strategy 1: Look for exact word matches
    for word in base_words:
        if len(word) > 3:  # Only for meaningful words
            # Find all occurrences of this word in context
            pattern = rf'\b{re.escape(word)}\w*\b'
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if match not in variations:
                    variations.append(match)
    
    # Strategy 2: Look for chemical compound patterns (e.g., "salicylic acid" might appear as "salicylate")
    if "acid" in normalized_base:
        base_without_acid = normalized_base.replace(" acid", "").strip()
        if base_without_acid:
            # Look for variations like "salicylate" for "salicylic acid"
            pattern = rf'\b{re.escape(base_without_acid[:6])}\w*\b'
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if len(match) > 4 and match not in variations:
                    variations.append(match)
    
    return variations


def fuzzy_match_ingredient(ingredient: str, text: str, threshold: float = 0.75) -> Tuple[bool, float, Optional[str]]:
    """
    Use fuzzy matching to find ingredient mentions in text.
    Returns: (found, confidence_score, matched_text)
    """
    normalized_ingredient = normalize_ingredient_name(ingredient)
    
    if not normalized_ingredient:
        return False, 0.0, None
    
    # Extract potential ingredient mentions from text (words/phrases of similar length)
    # Look for sequences of 2-5 words that might match
    words = re.findall(r'\b\w+\b', text.lower())
    
    if not words:
        return False, 0.0, None
    
    # Try exact substring match first (fastest)
    if normalized_ingredient in text.lower():
        return True, 1.0, normalized_ingredient
    
    # Try word-by-word matching
    ingredient_words = normalized_ingredient.split()
    if len(ingredient_words) == 1:
        # Single word - check if it appears in text
        if ingredient_words[0] in words:
            return True, 0.9, ingredient_words[0]
    else:
        # Multi-word ingredient - look for consecutive word matches
        for i in range(len(words) - len(ingredient_words) + 1):
            candidate = " ".join(words[i:i + len(ingredient_words)])
            if candidate == normalized_ingredient:
                return True, 1.0, candidate
    
    # Use rapidfuzz for fuzzy matching if available
    if RAPIDFUZZ_AVAILABLE:
        # Extract all potential phrases from text (2-4 word sequences)
        candidates = []
        for i in range(len(words) - 1):
            for j in range(i + 1, min(i + 5, len(words) + 1)):
                candidate = " ".join(words[i:j])
                if len(candidate) > 3:  # Only meaningful phrases
                    candidates.append(candidate)
        
        if candidates:
            # Find best match using rapidfuzz
            best_match = process.extractOne(
                normalized_ingredient,
                candidates,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=int(threshold * 100)
            )
            
            if best_match:
                matched_text, score, _ = best_match
                confidence = score / 100.0
                if confidence >= threshold:
                    return True, confidence, matched_text
    
    return False, 0.0, None


def check_ingredient_mention(ingredient: str, text: str, use_fuzzy: bool = True) -> bool:
    """
    Check if ingredient is mentioned in text, using fuzzy matching if enabled.
    """
    normalized_ingredient = normalize_ingredient_name(ingredient)
    
    if not normalized_ingredient:
        return False
    
    text_lower = text.lower()
    
    # Exact match (fastest)
    if normalized_ingredient in text_lower:
        return True
    
    # Word-by-word match
    ingredient_words = normalized_ingredient.split()
    if len(ingredient_words) == 1:
        # Single word - check if it appears as a whole word
        pattern = rf'\b{re.escape(ingredient_words[0])}\b'
        if re.search(pattern, text_lower):
            return True
    else:
        # Multi-word - check if all words appear (in any order, but close together)
        words_in_text = set(re.findall(r'\b\w+\b', text_lower))
        ingredient_words_set = set(ingredient_words)
        
        # Check if all ingredient words appear in text
        if ingredient_words_set.issubset(words_in_text):
            # Check if they appear close together (within 50 characters)
            for i, word in enumerate(ingredient_words):
                if word in text_lower:
                    # Find position of this word
                    pos = text_lower.find(word)
                    # Check if other words appear nearby
                    nearby_text = text_lower[max(0, pos - 50):pos + len(word) + 50]
                    other_words_found = sum(1 for w in ingredient_words if w in nearby_text and w != word)
                    if other_words_found >= len(ingredient_words) - 1:
                        return True
    
    # Use fuzzy matching if enabled and rapidfuzz is available
    if use_fuzzy and RAPIDFUZZ_AVAILABLE:
        found, confidence, _ = fuzzy_match_ingredient(ingredient, text, threshold=0.7)
        if found and confidence >= 0.7:
            return True
    
    return False


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
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 5, "fetch_k": 10}
    )
    return retriever


async def get_bis_cautions_for_ingredients(ingredient_names: List[str]) -> Dict[str, List[str]]:
    """
    Get BIS caution information for given ingredients
    Returns dict mapping ingredient names to list of caution texts
    Retrieves ALL cautions/instructions without limiting the count
    """
    try:
        retriever = get_bis_retriever()
        if retriever is None:
            return {}
    except Exception as e:
        print(f"⚠️ BIS retriever not available: {e}")
        return {}
    
    cautions_map = {}
    
    # Expand search keywords for better coverage
    caution_keywords = [
        'caution', 'warning', 'restriction', 'limit', 'maximum', 'minimum',
        'prohibited', 'not allowed', 'should not', 'avoid', 'must not',
        'instruction', 'requirement', 'mandatory', 'compliance', 'regulation',
        'standard', 'guideline', 'specification', 'condition', 'precaution'
    ]
    
    for ingredient in ingredient_names:
        try:
            # Normalize ingredient name for better search
            normalized_ingredient = normalize_ingredient_name(ingredient)
            
            # Use multiple search queries for better coverage
            # Include both original and normalized versions
            queries = [
                f"{ingredient} caution warning restriction",
                f"{normalized_ingredient} caution warning restriction",
                f"{ingredient} limit concentration maximum",
                f"{normalized_ingredient} limit concentration maximum",
                f"{ingredient} instruction requirement",
                f"{normalized_ingredient} instruction requirement",
                f"{ingredient} regulation compliance",
                f"{normalized_ingredient} regulation compliance"
            ]
            
            # Remove duplicate queries
            queries = list(dict.fromkeys(queries))  # Preserves order while removing duplicates
            
            all_docs = []
            seen_doc_ids = set()
            
            # Collect documents from all queries
            for query in queries:
                docs = retriever.invoke(query)
                for doc in docs:
                    # Use source + chunk_index as unique identifier
                    doc_id = f"{doc.metadata.get('source', '')}_{doc.metadata.get('chunk_index', '')}"
                    if doc_id not in seen_doc_ids:
                        seen_doc_ids.add(doc_id)
                        all_docs.append(doc)
            
            # Extract relevant information from all documents
            cautions = []
            
            # Get ingredient variations for better matching
            all_docs_text = " ".join([doc.page_content for doc in all_docs])
            ingredient_variations = extract_ingredient_variations(all_docs_text, ingredient)
            
            for doc in all_docs:
                content = doc.page_content
                content_lower = content.lower()
                
                # Check if document contains caution-related information
                if any(keyword in content_lower for keyword in caution_keywords):
                    # Check if ingredient (or any variation) is mentioned in this document
                    ingredient_mentioned = False
                    matched_variation = None
                    
                    # Try exact match first
                    for variation in ingredient_variations:
                        if check_ingredient_mention(variation, content, use_fuzzy=False):
                            ingredient_mentioned = True
                            matched_variation = variation
                            break
                    
                    # If exact match failed, try fuzzy matching
                    if not ingredient_mentioned:
                        found, confidence, matched_text = fuzzy_match_ingredient(ingredient, content, threshold=0.7)
                        if found:
                            ingredient_mentioned = True
                            matched_variation = matched_text or normalized_ingredient
                    
                    if not ingredient_mentioned:
                        continue
                    
                    # Multiple extraction strategies to catch all cautions
                    
                    # Strategy 1: Split by sentences (period)
                    sentences = content.split('.')
                    for sentence in sentences:
                        sentence_clean = sentence.strip()
                        if sentence_clean:
                            # Check if sentence mentions ingredient (using fuzzy matching)
                            if check_ingredient_mention(ingredient, sentence_clean, use_fuzzy=True):
                                # Check if sentence contains caution keywords
                                if any(keyword in sentence_clean.lower() for keyword in caution_keywords):
                                    cautions.append(sentence_clean)
                    
                    # Strategy 2: Split by newlines (for structured documents)
                    lines = content.split('\n')
                    for line in lines:
                        line_clean = line.strip()
                        if line_clean:
                            if check_ingredient_mention(ingredient, line_clean, use_fuzzy=True):
                                if any(keyword in line_clean.lower() for keyword in caution_keywords):
                                    cautions.append(line_clean)
                    
                    # Strategy 3: Extract paragraphs that mention ingredient and contain caution keywords
                    paragraphs = content.split('\n\n')
                    for para in paragraphs:
                        para_clean = para.strip()
                        if para_clean:
                            if check_ingredient_mention(ingredient, para_clean, use_fuzzy=True):
                                if any(keyword in para_clean.lower() for keyword in caution_keywords):
                                    # If paragraph is short, add as-is; if long, split further
                                    if len(para_clean) < 300:
                                        cautions.append(para_clean)
                                    else:
                                        # Split long paragraphs into sentences
                                        para_sentences = para_clean.split('.')
                                        for sent in para_sentences:
                                            sent_clean = sent.strip()
                                            if sent_clean:
                                                if check_ingredient_mention(ingredient, sent_clean, use_fuzzy=True):
                                                    if any(keyword in sent_clean.lower() for keyword in caution_keywords):
                                                        cautions.append(sent_clean)
            
            if cautions:
                # Remove duplicates while preserving order, but keep ALL unique cautions (no limit)
                unique_cautions = []
                seen = set()
                for caution in cautions:
                    # Normalize for comparison (lowercase, strip whitespace)
                    caution_normalized = caution.lower().strip()
                    if caution_normalized and caution_normalized not in seen:
                        seen.add(caution_normalized)
                        unique_cautions.append(caution)
                
                cautions_map[ingredient] = unique_cautions
                print(f"✅ Retrieved {len(unique_cautions)} caution(s) for {ingredient}")
        except Exception as e:
            print(f"⚠️ Error retrieving BIS cautions for {ingredient}: {e}")
            continue
    
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
        print(f"⚠️ Error retrieving BIS cautions: {e}")
        return "BIS cautions retrieval temporarily unavailable. Proceeding with report generation."

