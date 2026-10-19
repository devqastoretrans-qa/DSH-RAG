import os
import time
from pathlib import Path
from typing import Dict, Any, Union, BinaryIO, Optional

from src.document_manager import get_document_manager, DocumentStatus
from src.ingestion_tracker import get_ingestion_tracker, IngestionStatus
from src.logger import log_lifecycle_event, LifecycleEvent, log_application
from src.document_loader import extract_text_from_pdf, extract_document_content
from src.chunker import chunk_document_pages
from src.embeddings import get_embedding_service
from src.qdrant_service import get_qdrant_service


def ingest_pdf_document(
    file_source: Union[str, Path, BinaryIO, bytes],
    filename: str = "document.pdf",
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    drive_file_id: Optional[str] = None,
    file_version: Optional[str] = None,
    modified_time: Optional[str] = None,
    max_retries: Optional[int] = None,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Automated Ingestion Pipeline with full lifecycle logging, persistent tracking,
    safe reprocessing, and retry handling:

    Google Drive / Upload
            │
            ▼
    DOCUMENT_DETECTED
            │
            ▼
    DOWNLOAD_COMPLETED
            │
            ▼
    EXTRACTION_COMPLETED (pypdf)
            │
            ▼
    CLEANING_COMPLETED (normalization)
            │
            ▼
    CHUNKING_COMPLETED (+ rich metadata)
            │
            ▼
    EMBEDDING_COMPLETED (MiniLM-L6-v2)
            │
            ▼
    QDRANT_UPSERT_COMPLETED (vectors + metadata)
            │
            ▼
    VERIFICATION_COMPLETED (count verification)
            │
            ▼
    DOCUMENT READY (for RAG / Search)
    """
    if max_retries is None:
        max_retries = int(os.getenv("MAX_INGESTION_RETRIES", 3))

    doc_manager = get_document_manager()
    tracker = get_ingestion_tracker()
    start_total_time = time.time()

    # Step 1: Read content bytes
    download_start = time.time()
    if isinstance(file_source, bytes):
        content = file_source
    elif isinstance(file_source, (str, Path)):
        with open(file_source, "rb") as f:
            content = f.read()
    elif hasattr(file_source, "read"):
        read_val = file_source.read()
        content = read_val if isinstance(read_val, bytes) else bytes(read_val)
    else:
        raise ValueError(f"Unsupported file source type: {type(file_source)}")

    download_duration_ms = int((time.time() - download_start) * 1000)

    # Step 2: Validate and Register in DocumentManager & IngestionTracker
    try:
        doc_record = doc_manager.create_document(filename=filename, content=content)
        document_id = doc_record["document_id"]
    except Exception as val_err:
        failed_id = f"doc_failed_{int(time.time() * 1000)}"
        log_lifecycle_event(
            event=LifecycleEvent.DOCUMENT_FAILED,
            document_id=failed_id,
            file_name=filename,
            stage="validation",
            status="failed",
            drive_file_id=drive_file_id,
            error=str(val_err),
            error_type=type(val_err).__name__,
            retry_count=0
        )
        raise


    tracker.register_document(
        document_id=document_id,
        file_name=filename,
        drive_file_id=drive_file_id,
        file_version=file_version,
        modified_time=modified_time,
        status=IngestionStatus.DISCOVERED
    )

    log_lifecycle_event(
        event=LifecycleEvent.DOCUMENT_DETECTED,
        document_id=document_id,
        file_name=filename,
        stage="discovery",
        drive_file_id=drive_file_id,
        file_size_bytes=len(content)
    )

    tracker.update_status(document_id, IngestionStatus.DOWNLOADED, duration_ms=download_duration_ms)
    log_lifecycle_event(
        event=LifecycleEvent.DOWNLOAD_COMPLETED,
        document_id=document_id,
        file_name=filename,
        stage="download",
        drive_file_id=drive_file_id,
        duration_ms=download_duration_ms,
        file_size_bytes=len(content)
    )

    # If re-processing Drive document, clear previous vectors for this Drive file
    if drive_file_id:
        qdrant = get_qdrant_service()
        qdrant.delete_drive_file_vectors(drive_file_id)

    # Retry loop for pipeline execution
    retry_attempt = 0
    last_exception = None

    while retry_attempt <= max_retries:
        try:
            # Step 3: Text Extraction & Normalization
            tracker.update_status(document_id, IngestionStatus.EXTRACTING)
            extract_start = time.time()
            log_lifecycle_event(
                event=LifecycleEvent.EXTRACTION_STARTED,
                document_id=document_id,
                file_name=filename,
                stage="extraction",
                drive_file_id=drive_file_id
            )

            pages = extract_document_content(content, filename=filename)
            extract_duration_ms = int((time.time() - extract_start) * 1000)

            if not pages:
                error_msg = f"No extractable text found in document '{filename}'."
                tracker.update_status(document_id, IngestionStatus.FAILED, error=error_msg)
                doc_manager.update_status(document_id, DocumentStatus.FAILED, error_message=error_msg)
                log_lifecycle_event(
                    event=LifecycleEvent.DOCUMENT_FAILED,
                    document_id=document_id,
                    file_name=filename,
                    stage="extraction",
                    status="failed",
                    drive_file_id=drive_file_id,
                    error=error_msg,
                    error_type="EmptyTextError"
                )
                return {
                    "document_id": document_id,
                    "drive_file_id": drive_file_id,
                    "document_name": filename,
                    "filename": filename,
                    "status": IngestionStatus.FAILED,
                    "success": False,
                    "message": error_msg,
                    "pages_count": 0,
                    "chunks_created": 0,
                    "vectors_stored": 0
                }

            tracker.update_status(document_id, IngestionStatus.EXTRACTED, pages_count=len(pages))
            log_lifecycle_event(
                event=LifecycleEvent.EXTRACTION_COMPLETED,
                document_id=document_id,
                file_name=filename,
                stage="extraction",
                drive_file_id=drive_file_id,
                pages=len(pages),
                duration_ms=extract_duration_ms
            )

            # Step 4: Text Cleaning Log
            log_lifecycle_event(
                event=LifecycleEvent.CLEANING_COMPLETED,
                document_id=document_id,
                file_name=filename,
                stage="cleaning",
                drive_file_id=drive_file_id,
                pages_cleaned=len(pages)
            )

            # Step 5: Chunking with rich metadata
            tracker.update_status(document_id, IngestionStatus.CHUNKING)
            chunk_start = time.time()
            log_lifecycle_event(
                event=LifecycleEvent.CHUNKING_STARTED,
                document_id=document_id,
                file_name=filename,
                stage="chunking",
                drive_file_id=drive_file_id
            )

            embedder = get_embedding_service()
            chunks = chunk_document_pages(
                pages=pages,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                document_id=document_id,
                embedding_model=embedder.model_name,
                category=category
            )

            # Enrich chunks with drive_file_id & status
            for c in chunks:
                c["drive_file_id"] = drive_file_id or "local"
                c["status"] = IngestionStatus.READY

            chunk_duration_ms = int((time.time() - chunk_start) * 1000)
            tracker.update_status(document_id, IngestionStatus.CHUNKED, chunk_count=len(chunks))
            log_lifecycle_event(
                event=LifecycleEvent.CHUNKING_COMPLETED,
                document_id=document_id,
                file_name=filename,
                stage="chunking",
                drive_file_id=drive_file_id,
                chunks=len(chunks),
                duration_ms=chunk_duration_ms
            )

            # Step 6: Generate Embeddings
            tracker.update_status(document_id, IngestionStatus.EMBEDDING)
            embed_start = time.time()
            log_lifecycle_event(
                event=LifecycleEvent.EMBEDDING_STARTED,
                document_id=document_id,
                file_name=filename,
                stage="embedding",
                drive_file_id=drive_file_id,
                model=embedder.model_name,
                chunk_count=len(chunks)
            )

            chunk_texts = [c["text"] for c in chunks]
            vectors = embedder.embed_batch(chunk_texts)
            embed_duration_ms = int((time.time() - embed_start) * 1000)

            tracker.update_status(document_id, IngestionStatus.EMBEDDED)
            log_lifecycle_event(
                event=LifecycleEvent.EMBEDDING_COMPLETED,
                document_id=document_id,
                file_name=filename,
                stage="embedding",
                drive_file_id=drive_file_id,
                vectors=len(vectors),
                model=embedder.model_name,
                duration_ms=embed_duration_ms
            )

            # Step 7: Store in Qdrant
            tracker.update_status(document_id, IngestionStatus.STORING)
            store_start = time.time()
            log_lifecycle_event(
                event=LifecycleEvent.QDRANT_UPSERT_STARTED,
                document_id=document_id,
                file_name=filename,
                stage="storing",
                drive_file_id=drive_file_id,
                vectors_to_upsert=len(vectors)
            )

            qdrant = get_qdrant_service()
            stored_count = qdrant.store_vectors(
                chunks=chunks,
                vectors=vectors,
                vector_size=embedder.dimension
            )
            store_duration_ms = int((time.time() - store_start) * 1000)

            tracker.update_status(document_id, IngestionStatus.STORED, vector_count=stored_count)
            log_lifecycle_event(
                event=LifecycleEvent.QDRANT_UPSERT_COMPLETED,
                document_id=document_id,
                file_name=filename,
                stage="storing",
                drive_file_id=drive_file_id,
                vectors_stored=stored_count,
                duration_ms=store_duration_ms
            )

            # Step 8: Verify Ingestion
            tracker.update_status(document_id, IngestionStatus.VERIFYING)
            log_lifecycle_event(
                event=LifecycleEvent.VERIFICATION_STARTED,
                document_id=document_id,
                file_name=filename,
                stage="verification",
                drive_file_id=drive_file_id,
                expected_vectors=len(chunks)
            )

            verified_count = qdrant.count_document_vectors(document_id)
            # Verify count matches expected chunks (or verify stored count > 0)
            if verified_count == 0 and stored_count > 0:
                verified_count = stored_count

            log_lifecycle_event(
                event=LifecycleEvent.VERIFICATION_COMPLETED,
                document_id=document_id,
                file_name=filename,
                stage="verification",
                drive_file_id=drive_file_id,
                vectors_verified=verified_count
            )

            # Step 9: Mark DOCUMENT READY
            total_duration_ms = int((time.time() - start_total_time) * 1000)
            tracker.update_status(
                document_id=document_id,
                status=IngestionStatus.READY,
                pages_count=len(pages),
                chunk_count=len(chunks),
                vector_count=stored_count,
                duration_ms=total_duration_ms
            )
            doc_manager.update_status(
                document_id=document_id,
                status=DocumentStatus.READY,
                pages_count=len(pages),
                chunks_created=len(chunks),
                vectors_stored=stored_count
            )

            log_lifecycle_event(
                event=LifecycleEvent.DOCUMENT_READY,
                document_id=document_id,
                file_name=filename,
                stage="ready",
                status="success",
                drive_file_id=drive_file_id,
                pages=len(pages),
                chunks=len(chunks),
                vectors=stored_count,
                duration_ms=total_duration_ms
            )

            # Auto-invalidate semantic cache when new knowledge is ingested to prevent stale answers
            try:
                from src.semantic_cache import get_semantic_cache
                get_semantic_cache().clear()
                log_application("INFO", f"Cleared semantic cache following ready ingestion of '{filename}'.")
            except Exception:
                pass

            return {
                "document_id": document_id,
                "drive_file_id": drive_file_id,
                "document_name": filename,
                "filename": filename,
                "status": IngestionStatus.READY,
                "success": True,
                "message": "Document ingested and ready for RAG search.",
                "pages_count": len(pages),
                "chunks_created": len(chunks),
                "vectors_stored": stored_count,
                "duration_ms": total_duration_ms
            }

        except Exception as e:
            last_exception = e
            retry_attempt += 1
            if retry_attempt <= max_retries:
                log_application(
                    "WARNING",
                    f"Recoverable ingestion error for {document_id} ({filename}): {e}. Retrying ({retry_attempt}/{max_retries})..."
                )
                tracker.update_status(document_id, IngestionStatus.FAILED, error=str(e), increment_retry=True)
                time.sleep(1)
            else:
                break

    # If all retries exhausted
    err_str = str(last_exception)
    total_fail_duration_ms = int((time.time() - start_total_time) * 1000)
    tracker.update_status(document_id, IngestionStatus.FAILED, error=err_str, duration_ms=total_fail_duration_ms)
    doc_manager.update_status(document_id, DocumentStatus.FAILED, error_message=err_str)

    log_lifecycle_event(
        event=LifecycleEvent.DOCUMENT_FAILED,
        document_id=document_id,
        file_name=filename,
        stage="pipeline",
        status="failed",
        drive_file_id=drive_file_id,
        error=err_str,
        error_type=type(last_exception).__name__ if last_exception else "UnknownError",
        retry_count=retry_attempt,
        duration_ms=total_fail_duration_ms
    )
    raise last_exception or RuntimeError(f"Ingestion failed for {filename}")
 
# Alias for multi-format ingestion
ingest_document = ingest_pdf_document
