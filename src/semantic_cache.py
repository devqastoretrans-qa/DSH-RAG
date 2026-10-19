import os
import time
import threading
from typing import Dict, Any, List, Optional
import numpy as np


class SemanticQueryCache:
    """
    High-Performance In-Memory Semantic Query Cache.
    
    Caches query embeddings, user context, and generated answers.
    When a semantically equivalent question is asked (cosine similarity >= threshold),
    returns the cached RAG response in <15ms with 0 token/vector search costs.
    """

    def __init__(self, max_size: int = 500, similarity_threshold: Optional[float] = None):
        self.max_size = max_size
        env_threshold = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.88"))
        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else env_threshold
        self._lock = threading.RLock()
        # Storage: list of dicts { user_id, vector, response, timestamp }
        self._cache: List[Dict[str, Any]] = []

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        a = np.array(v1, dtype=np.float32)
        b = np.array(v2, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def lookup(
        self,
        query_vector: List[float],
        user_id: str,
        threshold: Optional[float] = None,
        mode: str = "generic"
    ) -> Optional[Dict[str, Any]]:
        """
        Looks up cached answers for the user_id and mode with cosine similarity >= threshold.
        Falls back to global non-personalized cache (__global__) if user-specific match is not found.
        """
        thresh = threshold or self.similarity_threshold
        with self._lock:
            best_match = None
            best_score = -1.0
            global_match = None
            global_score = -1.0

            for entry in self._cache:
                entry_mode = entry.get("mode", "generic")
                if entry_mode != mode:
                    continue

                entry_uid = entry.get("user_id", "")
                sim = self._cosine_similarity(query_vector, entry["vector"])
                if sim < thresh:
                    continue

                # 1. User-specific match priority
                if entry_uid == user_id:
                    if sim > best_score:
                        best_score = sim
                        best_match = entry
                # 2. Global fallback match
                elif entry_uid == "__global__":
                    if sim > global_score:
                        global_score = sim
                        global_match = entry

            match_to_use = best_match or global_match
            score_to_use = best_score if best_match else global_score

            if match_to_use:
                cached_data = dict(match_to_use["response"])
                cached_data["cached"] = True
                cached_data["cache_similarity"] = round(score_to_use, 4)
                cached_data["cache_tier"] = "user" if best_match else "global"
                return cached_data

        return None

    def store(
        self,
        query_vector: List[float],
        user_id: str,
        response: Dict[str, Any],
        mode: str = "generic"
    ) -> None:
        """
        Stores an answer in the semantic cache partitioned by user_id and mode.
        If the response is non-personalized (pure psychoeducation), also stores in the __global__ tier.
        """
        with self._lock:
            # Evict oldest if limit reached
            if len(self._cache) >= self.max_size:
                self._cache.pop(0)

            now = time.time()
            self._cache.append({
                "user_id": user_id,
                "mode": mode,
                "vector": query_vector,
                "response": response,
                "timestamp": now
            })

            # Two-Tier Promotion: Store in __global__ tier if unpersonalized generic clinical answer
            is_personalized = bool(response.get("personalized", False))
            cust_name = response.get("customer_name")
            ans_text = response.get("answer", "")
            
            # Check that answer is not personally addressed
            if not is_personalized and mode == "generic" and user_id != "__global__":
                if not cust_name or not ans_text.startswith(f"Hi {cust_name}"):
                    if len(self._cache) >= self.max_size:
                        self._cache.pop(0)
                    self._cache.append({
                        "user_id": "__global__",
                        "mode": mode,
                        "vector": query_vector,
                        "response": response,
                        "timestamp": now
                    })

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# Singleton
_cache_instance: Optional[SemanticQueryCache] = None


def get_semantic_cache() -> SemanticQueryCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticQueryCache()
    return _cache_instance
