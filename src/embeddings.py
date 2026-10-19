import os
import threading
from typing import List
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """
    Singleton service wrapper around SentenceTransformer to compute local text embeddings.
    Thread-safe initialization with double-checked locking to prevent cold-start race conditions.
    """
    _instance = None
    _model = None
    _dimension = None
    _lock = threading.Lock()

    def __init__(self, model_name: str = None):
        if model_name is None:
            model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        self.model_name = model_name
        self._ensure_model_loaded()

    def _ensure_model_loaded(self):
        if EmbeddingService._model is None:
            with EmbeddingService._lock:
                if EmbeddingService._model is None:
                    print(f"Initializing embedding model: {self.model_name}...")
                    model = SentenceTransformer(self.model_name)
                    # Programmatically verify vector dimension
                    dummy = model.encode("Vector dimension verification query", convert_to_numpy=True)
                    EmbeddingService._dimension = int(dummy.shape[0])
                    # Publish model only after full verification to prevent half-initialized read race
                    EmbeddingService._model = model
                    print(f"Embedding model initialized successfully. Vector Dimension: {EmbeddingService._dimension}")

    @property
    def dimension(self) -> int:
        """Returns the programmatic embedding vector dimension (e.g. 384)."""
        return EmbeddingService._dimension

    def embed_text(self, text: str) -> List[float]:
        """
        Generates embedding vector for a single document passage or text chunk with L2 normalization.
        """
        try:
            import torch
            with torch.inference_mode():
                vector = EmbeddingService._model.encode(text, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        except Exception:
            vector = EmbeddingService._model.encode(text, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()

    def embed_query(self, query: str) -> List[float]:
        """
        Generates embedding vector for a search query.
        Automatically applies query instruction prefix for asymmetric models (such as BGE).
        """
        query_text = query.strip()
        if "bge" in self.model_name.lower():
            query_text = f"Represent this sentence for searching relevant passages: {query_text}"
        
        try:
            import torch
            with torch.inference_mode():
                vector = EmbeddingService._model.encode(query_text, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        except Exception:
            vector = EmbeddingService._model.encode(query_text, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embedding vectors for a batch of strings with L2 normalization.
        """
        if not texts:
            return []
        try:
            import torch
            with torch.inference_mode():
                vectors = EmbeddingService._model.encode(texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        except Exception:
            vectors = EmbeddingService._model.encode(texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Alias for embed_batch for compatibility."""
        return self.embed_batch(texts)


_embedding_service_instance = None
_service_lock = threading.Lock()


def get_embedding_service() -> EmbeddingService:
    """
    Returns global cached instance of EmbeddingService (thread-safe).
    """
    global _embedding_service_instance
    if _embedding_service_instance is None:
        with _service_lock:
            if _embedding_service_instance is None:
                _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance
