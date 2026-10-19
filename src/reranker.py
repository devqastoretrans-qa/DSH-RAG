import os
import math
import threading
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder


def sigmoid(x: float) -> float:
    """Maps arbitrary logit score to [0, 1] range."""
    return 1.0 / (1.0 + math.exp(-x))


class RerankerService:
    """
    Singleton service wrapper around SentenceTransformer CrossEncoder
    to re-rank vector search candidate pairs with joint self-attention.
    Thread-safe initialization with double-checked locking to prevent cold-start race conditions.
    """
    _instance = None
    _model = None
    _lock = threading.Lock()

    def __init__(self, model_name: str = None):
        if model_name is None:
            model_name = os.getenv("RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.model_name = model_name
        self._ensure_model_loaded()

    def _ensure_model_loaded(self):
        if RerankerService._model is None:
            with RerankerService._lock:
                if RerankerService._model is None:
                    print(f"Initializing Cross-Encoder re-ranker model: {self.model_name}...")
                    model = CrossEncoder(self.model_name)
                    RerankerService._model = model
                    print("Cross-Encoder re-ranker initialized successfully.")

    def rerank(self, query: str, candidate_chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Takes candidate chunks from vector search, scores each (query, chunk_text) pair,
        and returns the top_k chunks sorted by re-rank score.
        Uses torch.inference_mode for fast CPU inference.
        """
        if not candidate_chunks:
            return []

        # Prune candidates to top 6-8 max to avoid wasted Cross-Encoder compute
        pruned_candidates = candidate_chunks[:max(top_k + 2, 7)]
        pairs = [(query, chunk.get("text", "")[:600]) for chunk in pruned_candidates]

        try:
            import torch
            with torch.inference_mode():
                raw_scores = RerankerService._model.predict(pairs, batch_size=len(pairs), show_progress_bar=False)
        except Exception:
            raw_scores = RerankerService._model.predict(pairs, batch_size=len(pairs), show_progress_bar=False)

        reranked = []
        for chunk, raw_score in zip(pruned_candidates, raw_scores):
            score_val = float(raw_score)
            normalized_score = round(sigmoid(score_val), 4)

            updated_chunk = dict(chunk)
            updated_chunk["vector_score"] = chunk.get("score", 0.0)
            updated_chunk["rerank_score"] = normalized_score
            updated_chunk["raw_rerank_score"] = round(score_val, 4)
            # Use normalized rerank score as primary score
            updated_chunk["score"] = normalized_score
            reranked.append(updated_chunk)

        # Sort descending by re-rank score
        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]


_reranker_instance = None
_reranker_lock = threading.Lock()


def get_reranker_service() -> RerankerService:
    """
    Returns global cached instance of RerankerService (thread-safe).
    """
    global _reranker_instance
    if _reranker_instance is None:
        with _reranker_lock:
            if _reranker_instance is None:
                _reranker_instance = RerankerService()
    return _reranker_instance
