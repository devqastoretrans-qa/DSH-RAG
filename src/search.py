import os
import re
import math
from typing import List, Dict, Any, Optional
from collections import Counter
from src.embeddings import get_embedding_service
from src.qdrant_service import get_qdrant_service
from src.reranker import get_reranker_service


# Colloquial Dating & Pop-Psychology Slang -> Dr. Sarah Hensley's Clinical Terminology
SLANG_EXPANSIONS = {
    r"\bghost(ing|ed)?\b": "avoidant deactivation emotional withdrawal sudden silent cutoff",
    r"\bhot\s+and\s+cold\b": "intermittent reinforcement anxious avoidant dance ambivalent cycle",
    r"\bbreadcrumb(ing|s|ed)?\b": "intermittent reinforcement minimal effort anxious attachment trap",
    r"\blove\s+bomb(ing|ed)?\b": "narcissistic idealization hyper-attentive courtship fast pacing",
    r"\bstonewall(ing|ed)?\b": "emotional shutdown avoidant overwhelm defensiveness silent treatment",
    r"\bwalking\s+on\s+egg\s*shells\b": "hypervigilance anxious appeasement emotional volatility fear of conflict",
    r"\bgaslight(ing|ed)?\b": "reality distortion psychological manipulation invalidation",
    r"\bclingy\b": "anxious attachment hyperactivating strategies protest behavior fear of abandonment",
    r"\bpush\s*pull\b": "anxious avoidant trap pursue withdraw dynamic polarity",
    r"\bemotionally\s+unavailable\b": "dismissive avoidant attachment deactivating strategies emotional suppression",
    r"\bshutting\s+down\b": "avoidant deactivation nervous system flooding overwhelm withdrawal",
    r"\bobsess(ing|ive)?\b": "hyperactivation anxious preoccupation rumination",
    r"\bmixed\s+signals\b": "inconsistent communication ambivalent attachment intermittent reinforcement",
    r"\btoxic\s+ex\b": "unhealed attachment wounding repetitive trauma bond dysregulation",
    r"\btrauma\s+bond(ing|ed)?\b": "intermittent reinforcement addictive attachment cycle dysregulation",
}


def expand_query_semantics(query: str) -> str:
    """
    Expands dating slang, pop-psychology expressions, and colloquial terms
    into Dr. Sarah Hensley's clinical attachment terminology for hybrid retrieval.
    """
    if not query:
        return query

    expanded_terms = []
    clean_lower = query.lower()
    for pattern, clinical_terms in SLANG_EXPANSIONS.items():
        if re.search(pattern, clean_lower):
            expanded_terms.append(clinical_terms)

    if expanded_terms:
        # Preserve user's original words and append clinical expansions
        return f"{query.strip()} " + " ".join(expanded_terms)
    return query.strip()


def compute_bm25_score(query: str, text: str, k1: float = 1.5, b: float = 0.75, avg_doc_len: float = 120.0) -> float:
    """
    Lightweight, fast BM25 sparse keyword relevance scorer.
    """
    query_tokens = [w.lower() for w in re.findall(r'\b\w+\b', query) if len(w) > 1]
    if not query_tokens:
        return 0.0

    doc_tokens = [w.lower() for w in re.findall(r'\b\w+\b', text)]
    doc_len = len(doc_tokens)
    if doc_len == 0:
        return 0.0

    tf = Counter(doc_tokens)
    score = 0.0
    for q in query_tokens:
        count = tf.get(q, 0)
        if count > 0:
            numerator = count * (k1 + 1)
            denominator = count + k1 * (1 - b + b * (doc_len / avg_doc_len))
            score += (numerator / denominator)

    # Normalize roughly to 0..1 range
    return min(1.0, score / max(1.0, len(query_tokens) * 2.0))


from src.config import CLINICAL_COLLECTIONS, get_collection_config


def route_clinical_intent(query: str) -> Optional[List[str]]:
    """
    Multi-category intent router for clinical queries.
    Collects all matching category intents (e.g. asking about Repair Scripts in Reflections
    searches BOTH 'tools' and 'reflections') rather than prematurely truncating.
    """
    if os.getenv("ENABLE_INTENT_ROUTING", "true").lower() in ("0", "false", "no"):
        return None

    q_low = query.lower()
    matched = set()

    tool_keywords = [
        "tool", "tools", "worksheet", "worksheets", "exercise", "exercises",
        "protocol", "fast down shift", "down-shift", "down shift", "boundary ladder",
        "solace", "dare soft", "repair script", "repair scripts"
    ]
    if any(re.search(rf"\b{re.escape(kw)}\b", q_low) for kw in tool_keywords):
        matched.add("tools")

    journal_keywords = ["journal", "prompts", "prompt", "thought log", "log a trigger"]
    if any(re.search(rf"\b{re.escape(kw)}\b", q_low) for kw in journal_keywords):
        matched.add("journals")

    reflection_keywords = ["reflection", "reflections", "pattern reflection"]
    if any(re.search(rf"\b{re.escape(kw)}\b", q_low) for kw in reflection_keywords):
        matched.add("reflections")

    if matched:
        return list(matched)
    return None


def search_similar_chunks(
    query: str,
    top_k: int = 5,
    use_reranker: bool = True,
    dynamic_threshold: bool = True,
    min_confidence_cutoff: float = 0.02,
    query_vector: Optional[List[float]] = None,
    mode: str = "generic",
    folders: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Advanced Multi-Stage Hybrid Search Pipeline:
    1. Query Expansion (dating slang -> clinical attachment theory).
    2. Dense Vector Embeddings (Sentence-Transformers MiniLM).
    3. Multi-Collection Retrieval:
       - Mode 'sales': searches sales catalog collection ('documents').
       - Mode 'generic': searches across clinical subfolder collections
         (journals, other, tools, reflections) with optional folder routing.
    4. Merging Candidates + BM25 Sparse Keyword Scoring.
    5. Lane-Aware Rank Fusion (50% Dense + 50% BM25 for sales; 70% Dense + 30% BM25 for generic) via RRF.
    6. Cross-Encoder Joint Re-Ranking (ms-marco-MiniLM-L-6-v2) on merged candidates.
    7. Dynamic Top-K Thresholding (prunes weak/noisy outliers).
    """
    if not query or not query.strip():
        return {
            "query": query,
            "results": [],
            "query_vector": []
        }

    clean_query = query.strip()
    expanded_query = expand_query_semantics(clean_query)
    
    # 1. Generate query embedding if not provided (uses expanded query for clinical matching)
    if query_vector is None:
        embedder = get_embedding_service()
        query_vector = embedder.embed_query(expanded_query)

    # 2. Dense Vector Retrieval from Qdrant
    fetch_k = max(top_k * 3, 12) if use_reranker else top_k
    qdrant = get_qdrant_service()

    candidates = []

    if mode == "sales":
        # Sales mode: searches sales collection ('documents')
        candidates = qdrant.search_similar(query_vector, top_k=fetch_k, collection_name=qdrant.collection_name)
    else:
        # Clinical (Generic) mode: determine target collections
        target_keys = []
        if folders:
            # Explicit folders provided by caller
            for f in folders:
                cfg = get_collection_config(f)
                if cfg:
                    target_keys.append(f.lower())
        else:
            # Check intent routing
            routed = route_clinical_intent(clean_query)
            if routed:
                target_keys = routed
            else:
                target_keys = list(CLINICAL_COLLECTIONS.keys())

        if not target_keys:
            target_keys = list(CLINICAL_COLLECTIONS.keys())

        # Retrieve candidates from each target collection and merge
        fetch_per_col = max(top_k * 2, 8) if use_reranker else top_k
        for k in target_keys:
            cfg = CLINICAL_COLLECTIONS.get(k)
            if not cfg:
                continue
            col_name = cfg["collection_name"]
            col_candidates = qdrant.search_similar(
                query_vector,
                top_k=fetch_per_col,
                collection_name=col_name
            )
            for c in col_candidates:
                if not c.get("folder_display"):
                    c["folder_display"] = cfg["display_name"]
                if not c.get("collection_key"):
                    c["collection_key"] = k
            candidates.extend(col_candidates)

    # Strictly filter candidates to only include READY documents
    try:
        from src.ingestion_tracker import get_ingestion_tracker
        tracker = get_ingestion_tracker()
        ready_candidates = [
            c for c in candidates
            if c.get("status") == "READY" or not c.get("document_id") or tracker.is_document_ready(c.get("document_id"))
        ]
        if ready_candidates:
            candidates = ready_candidates
    except Exception:
        pass

    # 2b. Lane Isolation Defense-in-Depth: Clinical mode must NEVER retrieve sales catalogs or pricing files
    if mode == "generic":
        clinical_candidates = [
            c for c in candidates
            if c.get("category") != "sales" and not any(k in (c.get("document_name") or c.get("filename") or "").lower() for k in ("sales", "catalog", "pricing", "checkout"))
        ]
        if clinical_candidates:
            candidates = clinical_candidates

    # 3. Lane-Aware Weights & Reciprocal Rank Fusion (RRF) with Min-Max Normalization
    # Sales lane gives 50/50 balance for exact product names/prices; Generic gives 70/30
    if mode == "sales":
        w_dense = 0.50
        w_sparse = 0.50
    else:
        w_dense = 0.70
        w_sparse = 0.30

    for c in candidates:
        text = c.get("text", "") + " " + c.get("parent_context", "")
        c["bm25_score"] = round(compute_bm25_score(expanded_query, text), 4)
        c["vector_score"] = float(c.get("vector_score", c.get("score", 0.0)))

    # Compute dense and BM25 ranks for Reciprocal Rank Fusion (RRF)
    sorted_by_v = sorted(range(len(candidates)), key=lambda i: candidates[i]["vector_score"], reverse=True)
    sorted_by_b = sorted(range(len(candidates)), key=lambda i: candidates[i]["bm25_score"], reverse=True)
    v_ranks = {orig_idx: rank + 1 for rank, orig_idx in enumerate(sorted_by_v)}
    b_ranks = {orig_idx: rank + 1 for rank, orig_idx in enumerate(sorted_by_b)}

    # Min-max values for score normalization
    v_scores = [c["vector_score"] for c in candidates]
    b_scores = [c["bm25_score"] for c in candidates]
    min_v, max_v = min(v_scores, default=0.0), max(v_scores, default=1.0)
    min_b, max_b = min(b_scores, default=0.0), max(b_scores, default=1.0)
    range_v = max_v - min_v if max_v > min_v else 1.0
    range_b = max_b - min_b if max_b > min_b else 1.0

    RRF_K = 60
    for i, c in enumerate(candidates):
        rank_v = v_ranks[i]
        rank_b = b_ranks[i]
        # RRF score (scale-invariant rank combination)
        c["rrf_score"] = round((w_dense / (RRF_K + rank_v)) + (w_sparse / (RRF_K + rank_b)), 6)

        # Normalized hybrid score (scaled 0..1 for thresholding and downstream compatibility)
        norm_v = (c["vector_score"] - min_v) / range_v
        norm_b = (c["bm25_score"] - min_b) / range_b
        c["hybrid_score"] = round((w_dense * norm_v) + (w_sparse * norm_b), 4)

    # Sort candidates by RRF score before re-ranking and prune low-relevance outliers
    candidates.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    if candidates and len(candidates) > top_k:
        top_rrf = candidates[0].get("rrf_score", 0.0)
        pruned = [c for c in candidates if c.get("rrf_score", 0.0) >= (top_rrf * 0.40)]
        candidates = pruned[:max(top_k + 2, 7)] if pruned else candidates[:top_k]

    # 4. Cross-Encoder Re-Ranking (Smart / Conditional)
    actually_reranked = False
    if use_reranker and candidates:
        top_v = float(candidates[0].get("vector_score", candidates[0].get("score", 0.0)))
        top_h = float(candidates[0].get("hybrid_score", 0.0))
        rerank_threshold = float(os.getenv("RERANK_CONFIDENCE_THRESHOLD", "0.85"))

        # If top candidate is already an exceptional match (>= threshold), skip heavy Cross-Encoder to save CPU
        if max(top_v, top_h) >= rerank_threshold:
            print(f"[Search] High-confidence match (score: {max(top_v, top_h):.3f} >= {rerank_threshold}). Skipping Cross-Encoder to conserve CPU.")
            ranked = candidates[:top_k]
            actually_reranked = False
        else:
            reranker = get_reranker_service()
            ranked = reranker.rerank(query=expanded_query, candidate_chunks=candidates, top_k=top_k)
            actually_reranked = True
    else:
        ranked = candidates[:top_k]

    # 5. Dynamic Top-K Thresholding
    if dynamic_threshold and ranked:
        top_score = float(ranked[0].get("rerank_score", ranked[0].get("score", 0.0)))
        filtered = []
        for r in ranked:
            score = float(r.get("rerank_score", r.get("score", 0.0)))
            # Keep if score meets absolute minimum and is within reasonable relative distance of top score
            if score >= min_confidence_cutoff and (top_score <= 0.1 or score >= top_score * 0.15):
                filtered.append(r)
        final_results = filtered if filtered else ranked[:1]
    else:
        final_results = ranked

    return {
        "query": clean_query,
        "expanded_query": expanded_query,
        "query_vector": query_vector,
        "reranked": actually_reranked,
        "hybrid": True,
        "results": final_results
    }


