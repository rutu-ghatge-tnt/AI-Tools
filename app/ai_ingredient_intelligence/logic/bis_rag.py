# app/ai_ingredient_intelligence/logic/bis_rag.py
"""
RAG module for Bureau of Indian Standards (BIS) documents
Retrieves caution information about ingredients from official BIS documents
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import fitz  # PyMuPDF

# BIS specific ChromaDB path
BIS_CHROMA_DB_PATH = os.path.join(Path(__file__).parent.parent.parent, "chroma_db_bis")
BIS_DATA_PATH = Path(__file__).parent.parent / "db" / "data"

# Ensure directories exist
os.makedirs(BIS_CHROMA_DB_PATH, exist_ok=True)


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


def initialize_bis_vectorstore() -> Optional[Chroma]:
    """Initialize or load BIS vectorstore"""
    try:
        # Check if vectorstore already exists
        if os.path.exists(BIS_CHROMA_DB_PATH) and os.listdir(BIS_CHROMA_DB_PATH):
            print("📚 Loading existing BIS vectorstore...")
            vectorstore = Chroma(
                persist_directory=BIS_CHROMA_DB_PATH,
                embedding_function=HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-mpnet-base-v2"
                )
            )
            return vectorstore
        
        # If not exists, create from PDFs
        print("📚 Creating BIS vectorstore from PDFs...")
        pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
        
        if not pdf_files:
            print(f"⚠️ No PDF files found in {BIS_DATA_PATH}")
            return None
        
        documents = []
        for pdf_file in pdf_files:
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
        
        if not documents:
            print("⚠️ No documents extracted from PDFs")
            return None
        
        # Create vectorstore
        embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )
        
        # Create empty vectorstore first, then add documents
        vectorstore = Chroma(
            embedding_function=embedding_model,
            persist_directory=BIS_CHROMA_DB_PATH
        )
        
        # Add documents in batches to avoid memory issues
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            vectorstore.add_documents(documents=batch)
        
        print(f"✅ Created BIS vectorstore with {len(documents)} chunks")
        return vectorstore
        
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize BIS vectorstore: {e}")
        print("   Reports will continue without BIS cautions. This is not critical.")
        import traceback
        traceback.print_exc()
        return None


def get_bis_retriever():
    """Get BIS document retriever"""
    vectorstore = initialize_bis_vectorstore()
    if vectorstore is None:
        return None
    
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

