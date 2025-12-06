"""
Debug script to check BIS vectorstore contents
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ai_ingredient_intelligence.logic.bis_rag import (
    initialize_bis_vectorstore,
    get_bis_retriever,
    BIS_DATA_PATH,
    BIS_CHROMA_DB_PATH
)
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
import os

def check_vectorstore_contents():
    """Check what's actually in the vectorstore"""
    print("=" * 80)
    print("BIS Vectorstore Debug")
    print("=" * 80)
    
    # Check PDF files
    print("\n1. Checking PDF files...")
    pdf_files = list(BIS_DATA_PATH.glob("*.pdf"))
    print(f"   Found {len(pdf_files)} PDF file(s):")
    for pdf in pdf_files:
        print(f"   - {pdf.name} ({pdf.stat().st_size / 1024:.1f} KB)")
    
    # Check vectorstore directory
    print("\n2. Checking vectorstore directory...")
    if os.path.exists(BIS_CHROMA_DB_PATH):
        files = list(Path(BIS_CHROMA_DB_PATH).glob("*"))
        print(f"   Vectorstore path exists: {BIS_CHROMA_DB_PATH}")
        print(f"   Files in vectorstore: {len(files)}")
        for f in files[:10]:
            print(f"   - {f.name}")
    else:
        print(f"   Vectorstore path does NOT exist: {BIS_CHROMA_DB_PATH}")
    
    # Try to load vectorstore and check document count
    print("\n3. Loading vectorstore and checking document count...")
    try:
        embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )
        
        if os.path.exists(BIS_CHROMA_DB_PATH) and os.listdir(BIS_CHROMA_DB_PATH):
            vectorstore = Chroma(
                persist_directory=BIS_CHROMA_DB_PATH,
                embedding_function=embedding_model
            )
            
            # Try to get collection info
            try:
                collection = vectorstore._collection
                count = collection.count()
                print(f"   [OK] Vectorstore loaded successfully")
                print(f"   [INFO] Document count: {count}")
                
                if count > 0:
                    # Try to get a few sample documents
                    print("\n4. Sampling documents...")
                    try:
                        results = collection.get(limit=3)
                        if results and 'ids' in results:
                            print(f"   Found {len(results['ids'])} sample document(s)")
                            if 'metadatas' in results and results['metadatas']:
                                for i, metadata in enumerate(results['metadatas'][:3]):
                                    print(f"   Sample {i+1}: {metadata}")
                    except Exception as e:
                        print(f"   [WARNING] Could not sample documents: {e}")
                    
                    # Try a simple similarity search
                    print("\n5. Testing similarity search...")
                    try:
                        # Try with a very generic query
                        test_queries = ["ingredient", "cosmetic", "standard", "concentration"]
                        for query in test_queries:
                            docs = vectorstore.similarity_search(query, k=3)
                            print(f"   Query '{query}': {len(docs)} docs")
                            if docs:
                                print(f"      First doc preview: {docs[0].page_content[:100]}...")
                    except Exception as e:
                        print(f"   [WARNING] Similarity search failed: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("   [WARNING] Vectorstore is EMPTY - no documents found!")
                    print("   [INFO] Solution: Re-embed the PDFs by deleting the vectorstore and re-running")
            except Exception as e:
                print(f"   [WARNING] Could not get collection info: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("   [WARNING] Vectorstore directory is empty or doesn't exist")
            print("   [INFO] Solution: Initialize vectorstore with PDFs")
            
    except Exception as e:
        print(f"   [ERROR] Error loading vectorstore: {e}")
        import traceback
        traceback.print_exc()
    
    # Test retriever
    print("\n6. Testing retriever...")
    try:
        retriever = get_bis_retriever()
        if retriever:
            # Try very generic queries
            test_queries = ["test", "ingredient", "cosmetic", "standard"]
            for query in test_queries:
                try:
                    docs = retriever.invoke(query)
                    print(f"   Query '{query}': {len(docs)} docs")
                except Exception as e:
                    print(f"   Query '{query}' failed: {e}")
        else:
            print("   [WARNING] Retriever is None")
    except Exception as e:
        print(f"   [ERROR] Retriever test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_vectorstore_contents()

