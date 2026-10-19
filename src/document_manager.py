import os
import re
import uuid
import threading
from datetime import datetime, timezone
from src.logger import IST
from pathlib import Path
from typing import Dict, Any, List, Optional


class DocumentStatus:
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    STORING = "STORING"
    READY = "READY"
    FAILED = "FAILED"


SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt", ".md", ".vtt", ".srt")


def validate_document_file(filename: str, content: bytes, max_size_mb: int = 50) -> None:
    """
    Validates document filename, content size, and file format headers.
    Supports PDF, Word DOCX, and text/transcript files.
    """
    if not filename or not any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        ext_list = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"Invalid file format. Supported formats: {ext_list}")

    if not content or len(content) == 0:
        raise ValueError("Uploaded file is empty (0 bytes).")

    max_bytes = max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(
            f"File size exceeds maximum allowed limit of {max_size_mb} MB (received {len(content) / (1024*1024):.2f} MB)."
        )

    # Check for PDF magic header (%PDF-) if PDF
    if filename.lower().endswith(".pdf") and not content.startswith(b"%PDF-"):
        raise ValueError("File corrupted or not a valid PDF format (missing %PDF- header).")


# Backward compatibility alias
validate_pdf_file = validate_document_file


class DocumentManager:
    """
    Thread-safe Document Manager responsible for:
    - Document validation and document ID generation
    - Preserving raw document files in storage
    - Ingestion lifecycle status tracking (UPLOADED -> EXTRACTING -> CHUNKING -> EMBEDDING -> STORING -> READY / FAILED)
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        base_dir = Path(__file__).resolve().parent.parent
        self.storage_dir = storage_dir or (base_dir / "documents" / "storage")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._registry: Dict[str, Dict[str, Any]] = {}

    def create_document(self, filename: str, content: bytes) -> Dict[str, Any]:
        """
        Validates, assigns document_id, saves original file to storage,
        and initializes ingestion status as UPLOADED.
        """
        validate_document_file(filename=filename, content=content)

        clean_name = re.sub(r"[^\w\-.]", "_", Path(filename).name)
        document_id = f"doc_{uuid.uuid4().hex[:8]}"
        saved_filename = f"{document_id}_{clean_name}"
        saved_path = self.storage_dir / saved_filename

        with open(saved_path, "wb") as f:
            f.write(content)

        now_iso = datetime.now(IST).isoformat()
        record = {
            "document_id": document_id,
            "document_name": filename,
            "saved_filename": saved_filename,
            "file_path": str(saved_path),
            "file_size_bytes": len(content),
            "status": DocumentStatus.UPLOADED,
            "error_message": None,
            "pages_count": 0,
            "chunks_created": 0,
            "vectors_stored": 0,
            "created_at": now_iso,
            "updated_at": now_iso
        }

        with self._lock:
            self._registry[document_id] = record

        return dict(record)

    def update_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
        pages_count: Optional[int] = None,
        chunks_created: Optional[int] = None,
        vectors_stored: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Updates document ingestion stage and metadata in the registry.
        """
        now_iso = datetime.now(IST).isoformat()
        with self._lock:
            if document_id not in self._registry:
                raise KeyError(f"Document ID '{document_id}' not found.")

            doc = self._registry[document_id]
            doc["status"] = status
            doc["updated_at"] = now_iso

            if error_message is not None:
                doc["error_message"] = error_message
            if pages_count is not None:
                doc["pages_count"] = pages_count
            if chunks_created is not None:
                doc["chunks_created"] = chunks_created
            if vectors_stored is not None:
                doc["vectors_stored"] = vectors_stored

            return dict(doc)

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            doc = self._registry.get(document_id)
            return dict(doc) if doc else None

    def list_documents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(doc) for doc in reversed(list(self._registry.values()))]


_document_manager_instance: Optional[DocumentManager] = None


def get_document_manager() -> DocumentManager:
    global _document_manager_instance
    if _document_manager_instance is None:
        _document_manager_instance = DocumentManager()
    return _document_manager_instance
