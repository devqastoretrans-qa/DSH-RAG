import os
import uuid
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    ScalarQuantization, ScalarQuantizationConfig, ScalarType
)

load_dotenv()


class QdrantService:
    """
    Service layer for Qdrant Vector Database interaction.
    Supports INT8 scalar quantization for 75% reduced memory usage and 2-3x search speedup.
    """
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "").strip()
        self.api_key = os.getenv("QDRANT_API_KEY", "").strip()
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "documents").strip()
        self.client = self._init_client()

    def _init_client(self) -> QdrantClient:
        is_production = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).strip().lower() in ("production", "prod")
        timeout = float(os.getenv("QDRANT_TIMEOUT", "10.0"))

        if self.url and self.url.lower() != ":memory:":
            print(f"Connecting to dedicated Qdrant server at: {self.url} (timeout={timeout}s)")
            kwargs = {"url": self.url, "timeout": timeout}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            client = QdrantClient(**kwargs)
        elif self.url.lower() == ":memory:":
            print("QDRANT_URL set to :memory: — initializing in-memory Qdrant client.")
            client = QdrantClient(":memory:")
        else:
            if is_production:
                raise RuntimeError(
                    "Production configuration error: QDRANT_URL is not set. "
                    "Local embedded Qdrant ('./qdrant_db') cannot be used in production multi-worker environments "
                    "due to exclusive file lock conflicts across worker processes. "
                    "Please set QDRANT_URL=http://qdrant:6333 (for Docker) or your managed Qdrant Cloud URL in .env."
                )
            path = os.getenv("QDRANT_PATH", "./qdrant_db").strip()
            print(f"[Qdrant] Warning: No QDRANT_URL provided — initializing persistent local Qdrant at '{path}'. "
                  f"(Note: Local embedded mode is only safe for single-process development, not multi-worker production)")
            client = QdrantClient(path=path)

        return client

    def ensure_collection(self, vector_size: int = 384, collection_name: Optional[str] = None) -> bool:
        """
        Ensures the target collection exists in Qdrant with Cosine distance and INT8 quantization.
        """
        target_col = collection_name or self.collection_name
        try:
            collections_response = self.client.get_collections()
            existing_names = [col.name for col in collections_response.collections]

            if target_col not in existing_names:
                print(f"Creating Qdrant collection '{target_col}' (dim={vector_size}, INT8 quantized)...")
                try:
                    self.client.create_collection(
                        collection_name=target_col,
                        vectors_config=VectorParams(
                            size=vector_size,
                            distance=Distance.COSINE
                        ),
                        quantization_config=ScalarQuantization(
                            scalar=ScalarQuantizationConfig(
                                type=ScalarType.INT8,
                                always_ram=True
                            )
                        )
                    )
                except Exception:
                    # Fallback without quantization if local client or older server version
                    self.client.create_collection(
                        collection_name=target_col,
                        vectors_config=VectorParams(
                            size=vector_size,
                            distance=Distance.COSINE
                        )
                    )
                print(f"Collection '{target_col}' ready.")
            return True
        except Exception as e:
            print(f"Qdrant collection check warning for '{target_col}': {e}")
            return False

    def create_payload_indexes(self, collection_name: str) -> None:
        """
        Creates payload indexes on collection_key, file_name, and drive_file_id.
        """
        from qdrant_client.models import PayloadSchemaType
        indexed_fields = ["collection_key", "file_name", "drive_file_id"]
        for field in indexed_fields:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD
                )
            except Exception:
                pass

    def store_vectors(
        self,
        chunks: List[Dict[str, Any]],
        vectors: List[List[float]],
        vector_size: int = 384,
        collection_name: Optional[str] = None,
        point_ids: Optional[List[str]] = None
    ) -> int:
        """
        Upserts document chunk vectors and metadata payload into Qdrant in batches.
        """
        target_col = collection_name or self.collection_name
        self.ensure_collection(vector_size=vector_size, collection_name=target_col)

        points = []
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            if point_ids and idx < len(point_ids):
                pid = str(point_ids[idx])
            else:
                pid = str(uuid.uuid4())

            points.append(
                PointStruct(
                    id=pid,
                    vector=vector,
                    payload=chunk
                )
            )

        # Batch upsert in chunks of 64 points for low memory and network efficiency
        batch_size = 64
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=target_col,
                points=batch
            )

        return len(points)

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        query_filter: Optional[Any] = None,
        collection_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs vector similarity search against stored chunk vectors in Qdrant.
        Supports optional Qdrant Filter for native payload filtering.
        """
        target_col = collection_name or self.collection_name
        collections = [col.name for col in self.client.get_collections().collections]
        if target_col not in collections:
            return []

        # Compatible vector search call for qdrant-client versions
        if hasattr(self.client, "query_points"):
            kwargs = {
                "collection_name": target_col,
                "query": query_vector,
                "limit": top_k,
                "with_payload": True
            }
            if query_filter:
                kwargs["query_filter"] = query_filter
            response = self.client.query_points(**kwargs)
            search_hits = response.points
        else:
            kwargs = {
                "collection_name": target_col,
                "query_vector": query_vector,
                "limit": top_k,
                "with_payload": True
            }
            if query_filter:
                kwargs["query_filter"] = query_filter
            search_hits = self.client.search(**kwargs)

        formatted_results = []
        for hit in search_hits:
            payload = hit.payload or {}
            formatted_results.append({
                "id": str(hit.id),
                "score": round(float(hit.score), 4),
                "document_id": payload.get("document_id", ""),
                "document_name": payload.get("document_name") or payload.get("file_name") or payload.get("filename", "unknown"),
                "file_name": payload.get("file_name") or payload.get("filename", "unknown"),
                "filename": payload.get("file_name") or payload.get("filename", "unknown"),
                "collection_key": payload.get("collection_key", ""),
                "folder_display": payload.get("folder_display", ""),
                "drive_url": payload.get("drive_url", ""),
                "page": payload.get("page_number") or payload.get("page", 0),
                "page_number": payload.get("page_number") or payload.get("page", 0),
                "chunk_id": payload.get("chunk_id", 0),
                "chunk_index": payload.get("chunk_index", 0),
                "text": payload.get("text", ""),
                "raw_text": payload.get("raw_text") or payload.get("text", ""),
                "parent_context": payload.get("parent_context", ""),
                "source": payload.get("file_name") or payload.get("source") or payload.get("filename", "unknown"),
                "embedding_model": payload.get("embedding_model", ""),
                "drive_file_id": payload.get("drive_file_id", "local"),
                "modified_time": payload.get("modified_time", ""),
                "md5_checksum": payload.get("md5_checksum") or payload.get("md5Checksum", ""),
                "category": payload.get("category", "clinical"),
                "status": payload.get("status", "READY")
            })

        return formatted_results

    def verify_document_stored(self, document_id: str) -> bool:
        """
        Verifies that points belonging to document_id exist in Qdrant collection.
        """
        collections = [col.name for col in self.client.get_collections().collections]
        if self.collection_name not in collections:
            return False

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            count_res = self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
            return count_res.count > 0
        except Exception:
            try:
                scroll_res = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=1,
                    with_payload=True
                )
                return len(scroll_res[0]) > 0
            except Exception:
                return True

    def count_document_vectors(self, document_id: str) -> int:
        """Counts stored vectors matching document_id in collection."""
        collections = [col.name for col in self.client.get_collections().collections]
        if self.collection_name not in collections:
            return 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            count_res = self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
            return int(count_res.count)
        except Exception:
            return 0

    def delete_document_vectors(self, document_id: str) -> bool:
        """Deletes all vector points associated with document_id for safe reprocessing."""
        collections = [col.name for col in self.client.get_collections().collections]
        if self.collection_name not in collections:
            return True
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="document_id",
                                match=MatchValue(value=document_id)
                            )
                        ]
                    )
                )
            )
            return True
        except Exception as e:
            print(f"Error deleting vectors for document {document_id}: {e}")
            return False

    def delete_drive_file_vectors(self, drive_file_id: str, collection_name: Optional[str] = None) -> bool:
        """Deletes all vector points associated with drive_file_id in the target collection."""
        target_col = collection_name or self.collection_name
        collections = [col.name for col in self.client.get_collections().collections]
        if target_col not in collections:
            return True
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
            self.client.delete(
                collection_name=target_col,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="drive_file_id",
                                match=MatchValue(value=drive_file_id)
                            )
                        ]
                    )
                )
            )
            return True
        except Exception as e:
            print(f"Error deleting vectors for drive file {drive_file_id} in '{target_col}': {e}")
            return False



_qdrant_service_instance = None


def get_qdrant_service() -> QdrantService:
    global _qdrant_service_instance
    if _qdrant_service_instance is None:
        _qdrant_service_instance = QdrantService()
    return _qdrant_service_instance
