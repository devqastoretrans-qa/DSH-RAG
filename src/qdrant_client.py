"""
Qdrant client interface module.
Re-exports QdrantService for consistency with requested project structure.
"""
from src.qdrant_service import QdrantService, get_qdrant_service

__all__ = ["QdrantService", "get_qdrant_service"]
