# app/ai_ingredient_intelligence/logic/bis_rag.py
"""
RAG module for Bureau of Indian Standards (BIS) documents
Retrieves caution information about ingredients from official BIS documents
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
import fitz  # PyMuPDF

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
            # Use multiple search queries for better coverage
            queries = [
                f"{ingredient} caution warning restriction",
                f"{ingredient} limit concentration maximum",
                f"{ingredient} instruction requirement",
                f"{ingredient} regulation compliance"
            ]
            
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
            ingredient_lower = ingredient.lower()
            
            for doc in all_docs:
                content = doc.page_content
                content_lower = content.lower()
                
                # Check if document contains caution-related information
                if any(keyword in content_lower for keyword in caution_keywords):
                    # Multiple extraction strategies to catch all cautions
                    
                    # Strategy 1: Split by sentences (period)
                    sentences = content.split('.')
                    for sentence in sentences:
                        sentence_clean = sentence.strip()
                        if sentence_clean and ingredient_lower in sentence_clean.lower():
                            # Check if sentence contains caution keywords
                            if any(keyword in sentence_clean.lower() for keyword in caution_keywords):
                                cautions.append(sentence_clean)
                    
                    # Strategy 2: Split by newlines (for structured documents)
                    lines = content.split('\n')
                    for line in lines:
                        line_clean = line.strip()
                        if line_clean and ingredient_lower in line_clean.lower():
                            if any(keyword in line_clean.lower() for keyword in caution_keywords):
                                cautions.append(line_clean)
                    
                    # Strategy 3: Extract paragraphs that mention ingredient and contain caution keywords
                    paragraphs = content.split('\n\n')
                    for para in paragraphs:
                        para_clean = para.strip()
                        if para_clean and ingredient_lower in para_clean.lower():
                            if any(keyword in para_clean.lower() for keyword in caution_keywords):
                                # If paragraph is short, add as-is; if long, split further
                                if len(para_clean) < 300:
                                    cautions.append(para_clean)
                                else:
                                    # Split long paragraphs into sentences
                                    para_sentences = para_clean.split('.')
                                    for sent in para_sentences:
                                        sent_clean = sent.strip()
                                        if sent_clean and ingredient_lower in sent_clean.lower():
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

