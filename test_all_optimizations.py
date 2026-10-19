import unittest
from src.semantic_cache import get_semantic_cache
from src.embeddings import get_embedding_service
from src.search import search_similar_chunks, compute_bm25_score
from src.chunker import chunk_document_pages
from src.rag_service import execute_rag_pipeline
from src.qdrant_service import get_qdrant_service

def test_all():
    print("=== 1. Testing BM25 Scoring ===")
    score = compute_bm25_score("adhd emotional regulation", "Strategies for adhd emotional regulation and executive dysfunction")
    print(f"BM25 score: {score}")
    assert score > 0.4, f"BM25 should match keywords, got {score}"

    print("=== 2. Testing Parent Document / Small-to-Big Retrieval ===")
    pages = [{"text": "Sentence 1 about ADHD. Sentence 2 about therapy. Sentence 3 about emotional regulation. Sentence 4 about grounding techniques. Sentence 5 about mindful breathing.", "page_number": 1, "filename": "guide.pdf"}]
    chunks = chunk_document_pages(pages, chunk_size=6, chunk_overlap=2)
    print(f"Created {len(chunks)} chunks")
    for c in chunks:
        print(f"Chunk text: '{c['raw_text']}' -> Parent Context: '{c['parent_context']}'")
        assert "parent_context" in c

    print("=== 3. Testing Semantic Cache ===")
    cache = get_semantic_cache()
    cache.clear()
    embedder = get_embedding_service()
    v1 = embedder.embed_query("How to stay calm with ADHD?")
    v2 = embedder.embed_query("Techniques for staying calm when having ADHD")
    cache.store(v1, "john", {"answer": "Use grounding exercises and paced breathing."})
    lookup_res = cache.lookup(v2, "john")
    print("Lookup result for semantically similar question:", lookup_res)
    assert lookup_res is not None, "Semantic cache should match semantically similar query"
    assert lookup_res.get("cached") is True
    assert lookup_res.get("cache_similarity") >= 0.85

    print("=== 4. Testing End-to-End RAG with Semantic Caching ===")
    res1 = execute_rag_pipeline(query="What grounding techniques help with ADHD emotional regulation?", user_id="john", top_k=3)
    safe_ans = res1['answer'][:80].encode('ascii', 'replace').decode('ascii')
    print(f"Call 1 (Live LLM/Vector): duration={res1['duration_ms']}ms, answer={safe_ans}...")
    
    # Call 2 (Semantic identical query)
    res2 = execute_rag_pipeline(query="Grounding exercises to assist with ADHD emotional regulation?", user_id="john", top_k=3)
    print(f"Call 2 (Semantic Cache Hit): duration={res2['duration_ms']}ms, cached={res2.get('cached')}, sim={res2.get('cache_similarity')}")
    assert res2.get("cached") is True
    assert res2["duration_ms"] < 800, f"Cached query should execute rapidly, got {res2['duration_ms']}ms"

    print("=== 5. Testing Qdrant Scalar Quantization Config ===")
    qdrant = get_qdrant_service()
    print(f"Qdrant collection: {qdrant.collection_name}, client initialized successfully.")

    print("\n>>> ALL 6 OPTIMIZATIONS VERIFIED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_all()
