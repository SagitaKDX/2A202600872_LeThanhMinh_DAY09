import sys
from pathlib import Path
import os

# Clean up proxy environment variables containing ::1 to prevent httpx url parsing bug
for var in ["no_proxy", "NO_PROXY", "No_Proxy"]:
    if var in os.environ:
        os.environ[var] = ",".join([p for p in os.environ[var].split(",") if "::1" not in p])

# Add src to python path to run directly if needed
sys.path.append(str(Path(__file__).resolve().parent))


from app.config import Settings
from rag.embeddings import SentenceTransformerEmbeddings
from rag.vector_store import ChromaPolicyStore
from rag.parser import parse_policy_markdown

def main():
    print("=== RAG Pipeline Chunking & Embedding ===")
    settings = Settings.load()
    
    # 1. Test Markdown Chunking Parser
    print(f"Reading policy document: {settings.policy_path}...")
    if not settings.policy_path.exists():
        print(f"Error: Policy file not found at {settings.policy_path}")
        sys.exit(1)
        
    with open(settings.policy_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()
        
    chunks = parse_policy_markdown(markdown_text)
    print(f"Successfully chunked policy into {len(chunks)} passages.")
    
    # Preview a sample chunk
    if chunks:
        print("\n--- Previewing Chunk 1 ---")
        print(f"H2 Section: {chunks[0]['section_h2']}")
        print(f"H3 Section: {chunks[0]['section_h3']}")
        print(f"Citation:   {chunks[0]['citation']}")
        print(f"Content Length: {len(chunks[0]['rendered_text'])} characters")
        print("---------------------------")

    # 2. Test Chroma Vector DB Indexing
    print(f"\nInitializing SentenceTransformerEmbeddings with model: {settings.embedding_model_name}...")
    embedding_model = SentenceTransformerEmbeddings(settings.embedding_model_name)
    
    print(f"Initializing Chroma persistent client at: {settings.chroma_dir}...")
    policy_store = ChromaPolicyStore(
        persist_directory=settings.chroma_dir,
        embedding_model=embedding_model
    )
    
    print("Rebuilding Chroma vector collection (embedding documents)...")
    policy_store.rebuild(settings.policy_path)
    print("Index rebuild completed successfully!")

    # 3. RAG Retrieval Evaluation Suite
    print("\n=== Evaluating RAG Retrieval Quality ===")
    
    eval_cases = [
        {
            "query": "Chính sách hoàn trả hàng ra sao?",
            "expected_subsections": ["5.1. Điều kiện chung để gửi yêu cầu", "5. Chính sách đổi trả và hoàn tiền"]
        },
        {
            "query": "Giao hàng tiêu chuẩn thường mất bao lâu?",
            "expected_subsections": ["4.3. Thời gian giao hàng dự kiến", "4. Chính sách giao hàng"]
        },
        {
            "query": "Khách có được kiểm hàng khi nhận không?",
            "expected_subsections": ["4.6. Kiểm hàng khi nhận"]
        },
        {
            "query": "Voucher có được hoàn lại khi hủy đơn không?",
            "expected_subsections": ["6.5. Hoàn lại voucher khi đơn bị hủy"]
        },
        {
            "query": "Khách tự gửi trả thì có được hỗ trợ phí không?",
            "expected_subsections": ["5.8. Chi phí vận chuyển chiều hoàn"]
        }
    ]
    
    passed_count = 0
    
    for idx, case in enumerate(eval_cases):
        query = case["query"]
        expected_subs = case["expected_subsections"]
        
        print(f"\nTest {idx+1}: Query = '{query}'")
        hits = policy_store.search(query, top_k=4)
        
        retrieved_citations = [hit["citation"] for hit in hits]
        print(f"Top 3 retrieved citations:")
        for rank, hit in enumerate(hits[:3]):
            print(f"  {rank+1}. {hit['citation']} (distance: {hit['distance']:.4f})")
            
        # Check if expected is in retrieved citations
        matched_expected = None
        for expected in expected_subs:
            if any(expected in cit for cit in retrieved_citations):
                matched_expected = expected
                break
                
        if matched_expected:
            print(f"✅ PASS: Found expected section content matching '{matched_expected}'")
            passed_count += 1
        else:
            print(f"❌ FAIL: Expected section containing one of {expected_subs} not found in top-4 hits.")
            
    accuracy = (passed_count / len(eval_cases)) * 100
    print(f"\n=== Evaluation Summary ===")
    print(f"Passed: {passed_count}/{len(eval_cases)}")
    print(f"Accuracy: {accuracy:.1f}%")
    
    if accuracy >= 80.0:
        print("🎉 SUCCESS: RAG Retrieval pipeline works exceptionally well!")
    else:
        print("⚠️ WARNING: Retrieval quality is lower than expected. Please check your parser or embedding settings.")

if __name__ == "__main__":
    main()
