import os
import re
import json
import hmac
import hashlib
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Security, status, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from src.ingestion import ingest_pdf_document
from src.search import search_similar_chunks
from src.rag_service import (
    execute_rag_pipeline, execute_sales_rag_pipeline,
    UserNotFoundError, RAGGenerationError,
    CRISIS_REGEX, VAGUE_DISTRESS_REGEX, COURSE_INQUIRY_REGEX
)
from src.generator import get_generator_service
from src.qdrant_service import get_qdrant_service
from src.document_manager import get_document_manager
from src.ingestion_tracker import get_ingestion_tracker
from src.drive_service import get_drive_service
from src.drive_monitor import get_drive_monitor
from src.logger import get_recent_logs
from src.user_db import get_user_db
from src.embeddings import get_embedding_service
from src.reranker import get_reranker_service
from src.semantic_cache import get_semantic_cache
from src.conversation_memory import get_conversation_memory

logger = logging.getLogger("rag_app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Production Security Sanity Checks
    is_production = os.getenv("ENVIRONMENT", "").strip().lower() in ("production", "prod")
    rag_api_key = os.getenv("RAG_API_KEY", "").strip()
    if is_production and not rag_api_key:
        error_msg = (
            "CRITICAL SECURITY CONFIGURATION ERROR: ENVIRONMENT is set to 'production' but RAG_API_KEY is unset or empty! "
            "The system refuses to start in an unauthenticated state in production."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()
    if is_production and allowed_origins_env in ("*", ""):
        logger.warning(
            "[Security Warning] ALLOWED_ORIGINS is set to '*' in production. "
            "It is strongly recommended to restrict CORS to trusted domains (e.g. 'https://doctorsarahhensley.com')."
        )

    # 1. Eager ML Model Pre-warming (prevents cold-start latency & thread race conditions)
    logger.info("Pre-warming ML models (Embeddings & Re-ranker)...")
    try:
        await run_in_threadpool(get_embedding_service)
        await run_in_threadpool(get_reranker_service)
        logger.info("ML models successfully loaded and pre-warmed in memory.")
    except Exception as e:
        logger.warning(f"ML model pre-warming encountered an issue (will load on-demand): {e}")

    # 2. Startup: Start Google Drive monitor if explicitly enabled via environment variable.
    # In production multi-worker deployments (Option A), ENABLE_DRIVE_MONITOR=false for the web API
    # and the monitor runs as a dedicated single-process background worker container (drive_worker).
    enable_monitor = os.getenv("ENABLE_DRIVE_MONITOR", "false").strip().lower() in ("true", "1", "yes")
    monitor = get_drive_monitor()
    if enable_monitor:
        if monitor.drive_service.is_configured():
            logger.info("Starting Google Drive monitor inside web process (ENABLE_DRIVE_MONITOR=true)...")
            monitor.start()
        else:
            logger.warning("ENABLE_DRIVE_MONITOR is true, but Google Drive service is not configured.")
    else:
        logger.info("Drive monitor background thread disabled in web process (ENABLE_DRIVE_MONITOR=false). Running in dedicated worker.")
    yield
    # Shutdown: Stop Google Drive monitor if running
    if monitor.is_running():
        monitor.stop()

app = FastAPI(
    title="Doctor Sarah Hensley AI - Personalized RAG API",
    description=(
        "Personalized Knowledge Retrieval & Question Answering REST API.\n\n"
        "Integrates Qdrant Vector Search (384-dim MiniLM embeddings) with verified customer purchasing "
        "profiles and GPT-4o-mini generation strictly grounded on Dr. Sarah Hensley's knowledge base."
    ),
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# -----------------------------------------------------------------------------
# CORS Middleware Configuration
# -----------------------------------------------------------------------------
is_production = os.getenv("ENVIRONMENT", "").strip().lower() in ("production", "prod")
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()

trusted_production_origins = [
    "https://doctorsarahhensley.com",
    "https://www.doctorsarahhensley.com",
    "https://dshstaging.doctorsarahhensley.com",
    "https://agent.doctorsarahhensley.com"
]

if allowed_origins_env and allowed_origins_env != "*":
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
elif is_production:
    logger.warning("[Security] Wildcard or empty CORS detected in production. Restricting strictly to trusted practice domains.")
    allowed_origins = trusted_production_origins
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Authentication & Security
# -----------------------------------------------------------------------------
security_bearer = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    api_key: Optional[str] = Security(api_key_header)
):
    """
    Validates API requests using Bearer Token ('Authorization: Bearer <KEY>')
    or Header ('X-API-Key: <KEY>') against the RAG_API_KEY environment variable.
    """
    expected_key = os.getenv("RAG_API_KEY", "").strip()
    is_production = os.getenv("ENVIRONMENT", "").strip().lower() in ("production", "prod")

    if not expected_key:
        if is_production:
            logger.error("[Security] RAG_API_KEY is not configured in production environment. Blocking access.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: API Key authentication is strictly required in production."
            )
        # If RAG_API_KEY is not configured in env, allow access in dev mode
        return True

    token = None
    if auth and auth.scheme.lower() == "bearer":
        token = auth.credentials
    elif api_key:
        token = api_key

    if not token or token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )
    return token


# -----------------------------------------------------------------------------
# Consistent Exception Handlers
# -----------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_err = errors[0] if errors else {}
    field = first_err.get("loc", [""])[-1]
    msg = first_err.get("msg", "Invalid request")
    
    if field and field not in ["body", ""]:
        error_msg = f"{field} is required" if "missing" in msg.lower() else f"{field}: {msg}"
    else:
        error_msg = msg
        
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"success": False, "error": error_msg}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail}
    )


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
@app.api_route("/dsh-rag", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
@app.api_route("/dsh-rag/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
async def serve_ui(request: Request):
    """
    Renders the web UI interface for document ingestion and semantic search.
    """
    return templates.TemplateResponse(request=request, name="index.html")


# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------
class SearchQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language search query", json_schema_extra={"example": "How to avoid being short-tempered?"})
    top_k: int = Field(default=5, ge=1, le=20, description="Number of top matching chunks to retrieve")
    generate_answer: bool = Field(default=True, description="Whether to synthesize an AI answer using retrieved chunks")
    user_id: Optional[str] = Field(default="admin", description="Authenticated user ID to personalize response with purchase history and past records")
    user_profile: Optional[Dict[str, Any]] = Field(default=None, description="Optional direct customer profile passed from frontend (eliminates database duplication)")
    chat_history: Optional[List[Dict[str, str]]] = Field(default=None, description="Optional conversation turns passed directly from frontend")
    mode: Optional[str] = Field(default="generic", description="Response mode: 'generic' or 'sales'")
    conversation_id: Optional[str] = Field(default=None, description="Active conversation tracking identifier for multi-turn chat memory")


class AskRequest(BaseModel):
    user_id: Optional[str] = Field(default="guest", description="Identifies the user asking the question", json_schema_extra={"example": "john"})
    question: str = Field(..., description="The question asked by the user", json_schema_extra={"example": "How can I stay calm when I have ADHD?"})
    user_profile: Optional[Dict[str, Any]] = Field(default=None, description="Direct customer profile passed from frontend (eliminates database duplication and lookups)")
    chat_history: Optional[List[Dict[str, str]]] = Field(default=None, description="Optional conversational history passed directly from frontend")
    conversation_id: Optional[str] = Field(default=None, description="Allows maintaining conversation history", json_schema_extra={"example": "conv_abc123"})
    session_id: Optional[str] = Field(default=None, description="Allows associating the request with a particular session", json_schema_extra={"example": "sess_xyz789"})
    mode: Optional[str] = Field(default="generic", description="Response mode: 'generic' (clinical) or 'sales'")
    folders: Optional[List[str]] = Field(default=None, description="Optional list of clinical subfolders to search ('journals', 'other', 'tools', 'reflections')")


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Unique frontend session ID for conversation tracking", json_schema_extra={"example": "sess_abc123"})
    message: str = Field(..., min_length=1, description="User question or follow-up prompt", json_schema_extra={"example": "How do I communicate with my partner?"})
    user_id: Optional[str] = Field(default="admin", description="WordPress user ID or persona key")
    user_profile: Optional[Dict[str, Any]] = Field(default=None, description="Direct customer profile passed from frontend")
    chat_history: Optional[List[Dict[str, str]]] = Field(default=None, description="Optional conversation turns passed directly from frontend")
    mode: Optional[str] = Field(default="generic", description="Bot lane: 'generic' (clinical) or 'sales'")


class ChatResetRequest(BaseModel):
    session_id: str = Field(..., description="Session ID to clear", json_schema_extra={"example": "sess_abc123"})
    user_id: Optional[str] = Field(default=None, description="Optional user ID")
    mode: Optional[str] = Field(default=None, description="Optional bot lane: 'generic' or 'sales'")


class SourceItem(BaseModel):
    document: str = Field(..., description="Name of the source document in knowledge base", json_schema_extra={"example": "ADHD_Guide.pdf"})
    relevance_score: float = Field(..., description="Cosine / Re-ranking relevance score", json_schema_extra={"example": 0.91})
    page: Optional[int] = Field(default=None, description="Page number where the snippet was found", json_schema_extra={"example": 1})
    chunk_id: Optional[Any] = Field(default=None, description="Chunk sequence identifier", json_schema_extra={"example": 2})


class AskResponse(BaseModel):
    success: bool = Field(default=True, description="Indicates whether the answer was successfully generated")
    user_id: str = Field(..., description="The user ID for whom the response was personalized", json_schema_extra={"example": "john"})
    question: str = Field(..., description="The original question asked", json_schema_extra={"example": "How can I stay calm when I have ADHD?"})
    answer: str = Field(..., description="Personalized answer synthesized by the LLM strictly grounded on knowledge docs and user context")
    answer_html: Optional[str] = Field(default=None, description="Pre-rendered polished HTML version with clean typography, headings, bold styling, and lists")
    sources: List[SourceItem] = Field(default_factory=list, description="List of source documents referenced in the answer")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation tracking ID")
    session_id: Optional[str] = Field(default=None, description="Optional session tracking ID")


class ErrorResponse(BaseModel):
    success: bool = Field(default=False, description="Always false for error responses")
    error: str = Field(..., description="Description of the error that occurred", json_schema_extra={"example": "question is required"})


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Overall health status")
    qdrant: str = Field(..., description="Qdrant vector database status", json_schema_extra={"example": "connected"})
    llm_service: str = Field(..., description="LLM service configuration status", json_schema_extra={"example": "configured"})
    embeddings: str = Field(default="ready", description="Sentence embedding model status", json_schema_extra={"example": "ready"})
    user_database: str = Field(default="ready", description="Customer profile database status", json_schema_extra={"example": "ready (SQLite)"})


@app.get("/health")
async def health_check():
    """
    Health check endpoint returning active statuses for FastAPI, Qdrant,
    Sentence-Transformers embeddings, Google Drive integration, and optional OpenAI.
    """
    qdrant = get_qdrant_service()
    generator = get_generator_service()
    drive_service = get_drive_service()
    drive_monitor = get_drive_monitor()
    tracker = get_ingestion_tracker()
    docs = tracker.list_documents()
    ready_count = sum(1 for d in docs if d.get("status") == "READY")
    mode = f"Cloud ({qdrant.url})" if qdrant.url else "Local In-Memory"

    return {
        "status": "ok",
        "fastapi": "ok",
        "qdrant": {
            "status": "ok",
            "mode": mode,
            "collection_name": qdrant.collection_name
        },
        "embeddings": {
            "status": "ok",
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "dimension": 384
        },
        "google_drive": drive_service.get_status_info(),
        "google_drive_monitor": {
            "running": drive_monitor.is_running(),
            "poll_interval_seconds": drive_monitor.poll_interval,
            "last_scan_time": drive_monitor._last_scan_time
        },
        "llm": {
            "provider": getattr(generator, "provider", "groq"),
            "configured": generator.is_configured(),
            "model": generator.model if generator.is_configured() else None,
            "required_for_ingestion": False
        },
        "openai": {
            "configured": generator.is_configured(),
            "model": generator.model if generator.is_configured() else None,
            "required_for_ingestion": False
        },
        "documents": {
            "total": len(docs),
            "ready": ready_count
        },
        "users_database": get_user_db().get_status(),
        "timezone": "IST (UTC+05:30)",
        "message": "Personalized RAG & Auto-Ingestion service is running"
    }


@app.get("/api/users")
async def list_users():
    """
    Returns list of all registered customer profiles, purchased courses/books,
    and past records for personalization testing.
    """
    user_db = get_user_db()
    return JSONResponse(content={
        "backend": user_db.backend,
        "users": user_db.list_users()
    })


@app.get("/api/users/{user_id}")
async def get_user_profile(user_id: str):
    """
    Returns specific customer profile, purchased courses/books, and past interaction records.
    """
    user_db = get_user_db()
    profile = user_db.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found in database.")
    return JSONResponse(content=profile)


@app.get("/api/qdrant/status")
async def get_qdrant_status():
    """
    Returns live connection details and vector counts from the Qdrant database server.
    """
    qdrant = get_qdrant_service()
    is_dedicated = bool(qdrant.url and qdrant.url.lower() != ":memory:")
    
    points_count = 0
    status = "disconnected"
    try:
        info = qdrant.client.get_collection(qdrant.collection_name)
        points_count = info.points_count or 0
        status = "connected"
    except Exception as e:
        status = f"error: {str(e)}"

    return JSONResponse(content={
        "mode": "Dedicated Qdrant Server" if is_dedicated else "Local Embedded Storage",
        "qdrant_url": qdrant.url if is_dedicated else "./qdrant_db (local)",
        "collection_name": qdrant.collection_name,
        "status": status,
        "vector_dimension": 384,
        "total_vectors_in_server": points_count
    })


@app.get("/drive/status")
async def get_drive_status():
    """
    Returns current status of Google Drive integration and background polling monitor.
    """
    monitor = get_drive_monitor()
    return JSONResponse(content=monitor.get_status())


@app.post("/drive/sync")
async def trigger_drive_sync(force: bool = False):
    """
    Manually triggers an immediate scan and auto-ingestion cycle for Google Drive.
    Pass ?force=true to force re-indexing of all existing files.
    """
    monitor = get_drive_monitor()
    result = monitor.scan_and_process(force_reprocess=force)
    return JSONResponse(content=result)


@app.api_route("/api/v1/cache/clear", methods=["GET", "POST"])
async def clear_system_caches(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
    api_key: Optional[str] = Query(None)
):
    """
    Flushes both the in-memory Semantic Query Cache and User Profile Cache.
    Requires authentication via X-API-Key/X-Admin-API-Key header or api_key query parameter.
    """
    expected_key = os.getenv("RAG_API_KEY") or os.getenv("ADMIN_API_KEY") or "dsh_rag_secret_key_2026"
    provided_key = x_api_key or x_admin_key or api_key

    if not provided_key or provided_key.strip() != expected_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Valid X-API-Key header or api_key query parameter is required to flush system caches."
        )

    from src.semantic_cache import get_semantic_cache
    sem_cache = get_semantic_cache()
    user_db = get_user_db()
    
    sem_cache.clear()
    user_db.clear_cache()
    
    return JSONResponse(content={
        "success": True,
        "message": "Flushed both Semantic Query Cache and User Profile Cache successfully."
    })


@app.get("/documents")
async def list_documents():
    """
    Returns list of all uploaded/ingested documents and their persistent lifecycle statuses.
    """
    tracker = get_ingestion_tracker()
    return JSONResponse(content={"documents": tracker.list_documents()})


@app.get("/documents/{document_id}")
async def get_document_status(document_id: str):
    """
    Returns detailed ingestion status and metadata for a specific document.
    """
    tracker = get_ingestion_tracker()
    doc = tracker.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document with ID '{document_id}' not found.")
    return JSONResponse(content=doc)


@app.get("/logs")
async def get_system_logs(log_type: str = "ingestion", limit: int = 50):
    """
    Returns recent log records formatted in Indian Standard Time (IST).
    Allowed log_type: 'ingestion' or 'application'.
    """
    lines = get_recent_logs(max_lines=min(limit, 200), log_type=log_type)
    return JSONResponse(content={
        "timezone": "IST (UTC+05:30)",
        "log_type": log_type,
        "count": len(lines),
        "lines": lines
    })




@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Automatically executes the complete document ingestion pipeline:
    Validate -> Save & Register -> Extract -> Clean -> Chunk -> Embed -> Store in Qdrant -> Verify -> Mark READY.
    Supports PDF, Word DOCX, and text/transcript files.
    """
    supported_exts = (".pdf", ".docx", ".doc", ".txt", ".md", ".vtt", ".srt")
    if not file.filename or not any(file.filename.lower().endswith(ext) for ext in supported_exts):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: {', '.join(supported_exts)}"
        )

    try:
        contents = await file.read()
        result = await run_in_threadpool(
            ingest_pdf_document,
            file_source=contents,
            filename=file.filename
        )
        return JSONResponse(content=result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {str(e)}")


@app.post("/ingest-sample")
async def ingest_sample():
    """
    Ingests the sample PDF located in documents/sample.pdf through the automated pipeline.
    """
    sample_path = BASE_DIR / "documents" / "sample.pdf"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample PDF not found at documents/sample.pdf")

    try:
        with open(sample_path, "rb") as f:
            contents = f.read()
        result = ingest_pdf_document(file_source=contents, filename="sample.pdf")
        return JSONResponse(content=result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sample ingestion failed: {str(e)}")


@app.post("/search", include_in_schema=False)
async def search_endpoint(request: SearchQueryRequest):
    """
    Dashboard UI Endpoint: Performs semantic vector search + cross-encoder re-ranking + ChatGPT answer synthesis.
    Reuses the unified execute_rag_pipeline service.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        uid = request.user_id or "admin"
        mode = request.mode or "generic"
        rag_res = await run_in_threadpool(
            execute_rag_pipeline,
            query=request.query,
            user_id=uid,
            top_k=request.top_k,
            generate_answer=request.generate_answer,
            mode=mode,
            conversation_id=request.conversation_id,
            user_profile=request.user_profile,
            chat_history=request.chat_history
        )
        return JSONResponse(content={
            "query": rag_res["question"],
            "mode": mode,
            "conversation_id": rag_res.get("conversation_id"),
            "reranked": True,
            "results": rag_res["raw_chunks"],
            "ai_answer": rag_res["answer"] if request.generate_answer else None,
            "ai_answer_html": rag_res.get("answer_html") if request.generate_answer else None,
            "recommended_products": rag_res.get("recommended_products", []),
            "ai_model": rag_res["ai_model"],
            "citations": rag_res["citations"],
            "usage": rag_res["usage"],
            "personalized": rag_res["personalized"],
            "disambiguation_options": rag_res.get("disambiguation_options", []),
            "customer_name": rag_res["user_profile"].get("name") if rag_res["user_profile"] else None,
            "user_profile": rag_res["user_profile"]
        })
    except UserNotFoundError:
        # Fallback to guest context for UI if user not found
        mode = request.mode or "generic"
        rag_res = await run_in_threadpool(
            execute_rag_pipeline,
            query=request.query,
            user_id="guest",
            top_k=request.top_k,
            generate_answer=request.generate_answer,
            mode=mode,
            conversation_id=request.conversation_id,
            user_profile=request.user_profile,
            chat_history=request.chat_history
        )
        return JSONResponse(content={
            "query": rag_res["question"],
            "mode": mode,
            "conversation_id": rag_res.get("conversation_id"),
            "reranked": True,
            "results": rag_res["raw_chunks"],
            "ai_answer": rag_res["answer"],
            "ai_answer_html": rag_res.get("answer_html"),
            "recommended_products": rag_res.get("recommended_products", []),
            "ai_model": rag_res["ai_model"],
            "citations": rag_res["citations"],
            "usage": rag_res["usage"],
            "personalized": False,
            "disambiguation_options": rag_res.get("disambiguation_options", []),
            "customer_name": None,
            "user_profile": rag_res["user_profile"]
        })
    except Exception as e:
        logger.error(f"[Dashboard Search] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# -----------------------------------------------------------------------------
# REST API v1 Endpoints
# -----------------------------------------------------------------------------
@app.post(
    "/api/v1/ask",
    response_model=AskResponse,
    responses={
        200: {"model": AskResponse, "description": "Successful personalized RAG response"},
        400: {"model": ErrorResponse, "description": "Bad Request / Missing parameters"},
        401: {"model": ErrorResponse, "description": "Unauthorized / Invalid API key"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Internal server / LLM error"}
    },
    tags=["RAG API"],
    summary="Personalized Question Answering via Grounded RAG Pipeline"
)
async def ask_api_v1(
    request: AskRequest,
    _auth: Any = Depends(verify_api_key)
):
    """
    Exposes personalized RAG retrieval & generation for external applications.

    - **user_id**: Identifies the customer profile (e.g. `john`, `sarah`, `guest`)
    - **question**: Natural language query asked by the user
    - **conversation_id**: Optional conversation tracking identifier
    - **session_id**: Optional session tracking identifier
    """
    # Validate question
    if not request.question or not request.question.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "question is required"}
        )
    uid = (request.user_id or "").strip()
    if not uid:
        if request.user_profile and isinstance(request.user_profile, dict):
            uid = str(request.user_profile.get("id") or request.user_profile.get("user_id") or "guest")
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "error": "user_id is required"}
            )

    try:
        req_mode = request.mode or "generic"
        res = await run_in_threadpool(
            execute_rag_pipeline,
            query=request.question,
            user_id=uid,
            top_k=5,
            generate_answer=True,
            mode=req_mode,
            conversation_id=request.conversation_id,
            folders=request.folders,
            user_profile=request.user_profile,
            chat_history=request.chat_history
        )
        return {
            "success": True,
            "mode": req_mode,
            "user_id": res["user_id"],
            "question": res["question"],
            "answer": res["answer"],
            "answer_html": res.get("answer_html"),
            "sources": res["sources"],
            "disambiguation_options": res.get("disambiguation_options", []),
            "conversation_id": request.conversation_id,
            "session_id": request.session_id
        }
    except UserNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": "User not found"}
        )
    except ValueError as ve:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": str(ve)}
        )
    except Exception as e:
        logger.error(f"[API v1] /ask failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Unable to generate an answer"}
        )


@app.post(
    "/api/v1/sales/ask",
    tags=["Sales Bot API"],
    summary="Soft-Consultative Personalized Sales Bot with Unowned Product Recommendations"
)
async def ask_sales_api_v1(
    request: AskRequest,
    _auth: Any = Depends(verify_api_key)
):
    """
    Dedicated Sales Bot Endpoint:
    - Provides compassionate clinical guidance first grounded on knowledge base.
    - Naturally introduces 1-2 relevant unowned courses, books, or consultations.
    - Strictly never pitches products the user already owns in their profile.
    """
    if not request.question or not request.question.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "question is required"}
        )
    uid = (request.user_id or "").strip()
    if not uid:
        if request.user_profile and isinstance(request.user_profile, dict):
            uid = str(request.user_profile.get("id") or request.user_profile.get("user_id") or "guest")
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "error": "user_id is required"}
            )

    try:
        res = await run_in_threadpool(
            execute_sales_rag_pipeline,
            query=request.question,
            user_id=uid,
            top_k=5,
            generate_answer=True,
            conversation_id=request.conversation_id,
            user_profile=request.user_profile,
            chat_history=request.chat_history
        )
        return {
            "success": True,
            "mode": "sales",
            "user_id": res["user_id"],
            "question": res["question"],
            "answer": res["answer"],
            "answer_html": res.get("answer_html"),
            "recommended_products": res.get("recommended_products", []),
            "sources": res["sources"],
            "conversation_id": request.conversation_id,
            "session_id": request.session_id
        }
    except UserNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": "User not found"}
        )
    except ValueError as ve:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": str(ve)}
        )
    except Exception as e:
        logger.error(f"[Sales API v1] /sales/ask failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Unable to generate an answer"}
        )


@app.post(
    "/api/v1/ask/stream",
    tags=["RAG API"],
    summary="Token Streaming Question Answering via Server-Sent Events (SSE)"
)
async def ask_api_v1_stream(
    request: AskRequest,
    _auth: Any = Depends(verify_api_key)
):
    """
    Real-time Token Streaming Endpoint with Concurrent Backend Acceleration:
    - Concurrently resolves user profile and vector search/reranking.
    - Resolves semantic cache hits in <15ms.
    - Streams synthesized tokens in real-time over Server-Sent Events (`text/event-stream`).
    """
    import json
    import concurrent.futures
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    uid = (request.user_id or "").strip()
    if not uid:
        if request.user_profile and isinstance(request.user_profile, dict):
            uid = str(request.user_profile.get("id") or request.user_profile.get("user_id") or "guest")
        else:
            raise HTTPException(status_code=400, detail="user_id is required")

    clean_query = request.question.strip()
    req_mode = request.mode or "generic"
    user_db = get_user_db()
    cache = get_semantic_cache()
    conv_memory = get_conversation_memory()

    # 0. Immediate Crisis Safety Guardrail Check (<1ms)
    if CRISIS_REGEX.search(clean_query):
        crisis_text = (
            "If you or someone you know is in acute distress, having thoughts of self-harm, or in an unsafe environment, please know you are not alone and free, confidential support is available 24/7:\n\n"
            "• **National Suicide & Crisis Lifeline**: Call or text **988** (Available 24/7 in the US & Canada).\n"
            "• **The Crisis Text Line**: Text **HOME** to **741741** to connect with a crisis counselor.\n"
            "• **National Domestic Violence Hotline**: Call **1-800-799-SAFE (7233)** or text **START** to **88788**.\n"
            "• **International Resources**: If you are outside the US, please visit [findahelpline.com](https://findahelpline.com) or contact your local emergency services (e.g., 911, 999, 112).\n\n"
            "While I am an AI assistant focused on relationship psychology and attachment theory, your immediate physical and emotional safety comes first. Please reach out to these trained professionals right away."
        )
        logger.warning(f"[Streaming RAG] Crisis safety guardrail triggered for user '{uid}' on query: '{clean_query}'")

        def crisis_stream():
            words = crisis_text.split(" ")
            for i, w in enumerate(words):
                prefix = "" if i == 0 else " "
                yield f"event: token\ndata: {json.dumps({'token': prefix + w})}\n\n"
            done_payload = {
                "success": True,
                "user_id": uid,
                "question": clean_query,
                "answer": crisis_text,
                "sources": [],
                "conversation_id": request.conversation_id,
                "session_id": request.session_id
            }
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

        return StreamingResponse(
            crisis_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    # 1. Resolve Multi-Turn Follow-Ups and Entity Stitching (<0.1ms)
    resolved_query, can_reuse_chunks, cached_chunks = conv_memory.resolve_follow_up(
        user_id=uid,
        conversation_id=request.conversation_id,
        query=clean_query
    )
    is_follow_up = (resolved_query != clean_query) or can_reuse_chunks

    # 2. Concurrent Execution: Fetch User Profile + Vector Search & Chunks simultaneously
    user_profile = None
    if request.user_profile and isinstance(request.user_profile, dict):
        raw_p = request.user_profile
        clean_name = raw_p.get("name") or raw_p.get("display_name") or raw_p.get("first_name") or uid.capitalize()
        owned = raw_p.get("owned_products") or raw_p.get("purchased_products") or raw_p.get("courses_purchased") or []
        user_profile = {
            "user_id": str(raw_p.get("user_id") or raw_p.get("id") or uid),
            "name": clean_name,
            "first_name": raw_p.get("first_name") or clean_name.split()[0],
            "display_name": clean_name,
            "email": raw_p.get("email") or f"{uid}@example.com",
            "courses_purchased": raw_p.get("courses_purchased") or owned,
            "books_purchased": raw_p.get("books_purchased") or [],
            "all_purchases": owned,
            "owned_products": owned,
            "attachment_style": raw_p.get("attachment_style"),
            "streaks": raw_p.get("streaks") or [],
            "recent_activities": raw_p.get("recent_activities") or [],
            "past_records": raw_p.get("past_records") or [],
            "has_history": bool(owned or raw_p.get("streaks") or raw_p.get("past_records")),
            "backend": "Stateless Request Payload"
        }

    if can_reuse_chunks and cached_chunks:
        if user_profile is None:
            user_profile = user_db.get_user_profile(uid)
        retrieved_chunks = cached_chunks
        query_vector = None
    else:
        if user_profile is not None:
            search_output = await run_in_threadpool(search_similar_chunks, query=resolved_query, top_k=5, mode=req_mode)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_profile = executor.submit(user_db.get_user_profile, uid)
                future_search = executor.submit(search_similar_chunks, query=resolved_query, top_k=5, mode=req_mode)
                user_profile = future_profile.result()
                search_output = future_search.result()

        query_vector = search_output.get("query_vector")
        retrieved_chunks = search_output.get("results", [])
        disambiguation_options = search_output.get("disambiguation_options", [])

    if not user_profile:
        fallback_name = uid.split("@")[0].replace(".", " ").replace("_", " ").title() if "@" in uid else uid.capitalize()
        user_profile = {
            "user_id": uid,
            "name": fallback_name,
            "first_name": fallback_name.split()[0] if fallback_name else "Guest",
            "email": f"{uid}@example.com" if "@" not in uid else uid,
            "courses_purchased": [],
            "books_purchased": [],
            "all_purchases": [],
            "owned_products": [],
            "past_records": [],
            "has_history": False,
            "backend": "Graceful Fallback"
        }

    # Check Semantic Cache for instant response (strictly bypassed on greetings & follow-ups)
    is_greeting = bool(re.match(r"^\s*(hi|hello|hey|greetings|howdy|good\s+(morning|afternoon|evening))\b", clean_query, re.I))
    cached_result = None
    if query_vector and not is_greeting:
        cached_result = cache.lookup(query_vector, user_id=uid, mode=req_mode)

    if request.chat_history is not None:
        chat_history = request.chat_history
    else:
        chat_history = conv_memory.get_chat_history(user_id=uid, conversation_id=request.conversation_id, max_turns=3)
    generator = get_generator_service()

    def event_stream():
        # Handle Instant Cache Hit
        if cached_result:
            cached_ans = cached_result.get("answer", "")
            words = cached_ans.split(" ")
            for i, w in enumerate(words):
                prefix = "" if i == 0 else " "
                yield f"event: token\ndata: {json.dumps({'token': prefix + w})}\n\n"

            done_payload = {
                "success": True,
                "user_id": uid,
                "question": clean_query,
                "answer": cached_ans,
                "answer_html": cached_result.get("answer_html"),
                "sources": cached_result.get("sources", []),
                "disambiguation_options": cached_result.get("disambiguation_options", []),
                "cached": True,
                "cache_similarity": cached_result.get("cache_similarity"),
                "conversation_id": request.conversation_id,
                "session_id": request.session_id
            }
            if cached_ans and not cached_ans.startswith("Error"):
                conv_memory.record_turn(
                    user_id=uid,
                    conversation_id=request.conversation_id or request.session_id,
                    user_query=clean_query,
                    assistant_answer=cached_ans,
                    retrieved_chunks=cached_result.get("sources", []),
                    mode=req_mode
                )
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
            return

        # Handle Normal LLM Generation Stream
        full_text_accum = []
        for event in generator.generate_answer_stream(
            query=resolved_query if is_follow_up else clean_query,
            retrieved_chunks=retrieved_chunks,
            user_context=user_profile,
            mode=req_mode,
            chat_history=chat_history,
            is_follow_up=is_follow_up
        ):
            if not event.get("done"):
                token = event.get("token", "")
                full_text_accum.append(token)
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
            else:
                full_answer = event.get("full_answer") or event.get("token") or "".join(full_text_accum)
                from src.generator import strip_citation_markers
                full_answer = strip_citation_markers(full_answer)
                # Generate HTML for final output
                answer_html = None
                try:
                    from markdown_it import MarkdownIt
                    md = MarkdownIt("commonmark", {"breaks": True, "html": False})
                    answer_html = md.render(full_answer)
                except Exception:
                    answer_html = full_answer

                # Format clean sources
                sources = []
                for chunk in retrieved_chunks:
                    doc_name = chunk.get("document_name") or chunk.get("filename") or "Document"
                    score = float(chunk.get("rerank_score", chunk.get("score", 0.0)))
                    sources.append({
                        "document": doc_name,
                        "relevance_score": round(score, 4),
                        "page": chunk.get("page") or chunk.get("page_number"),
                        "chunk_id": chunk.get("chunk_id")
                    })

                done_payload = {
                    "success": True,
                    "mode": req_mode,
                    "user_id": request.user_id,
                    "question": clean_query,
                    "answer": full_answer,
                    "answer_html": answer_html,
                    "personalized": bool(user_profile and user_profile.get("first_name") and user_profile.get("first_name") != "there"),
                    "customer_name": user_profile.get("first_name") if user_profile else None,
                    "recommended_products": event.get("recommended_products", []),
                    "disambiguation_options": disambiguation_options if 'disambiguation_options' in locals() else [],
                    "sources": sources,
                    "conversation_id": request.conversation_id,
                    "session_id": request.session_id
                }

                # Record turn in conversational memory
                if full_answer and not full_answer.startswith("Error") and not full_answer.startswith("No relevant"):
                    conv_memory.record_turn(
                        user_id=uid,
                        conversation_id=request.conversation_id,
                        user_query=clean_query,
                        assistant_answer=full_answer,
                        retrieved_chunks=retrieved_chunks,
                        mode=req_mode
                    )

                # Store into semantic cache for subsequent calls (never cache greetings or errors)
                if query_vector and full_answer and not full_answer.startswith("Error") and not is_greeting:
                    cache.store(query_vector=query_vector, user_id=uid, response=done_payload, mode=req_mode)

                yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



# -----------------------------------------------------------------------------
# Dedicated Chat UI Endpoints (with Session ID & Multi-Turn Memory)
# -----------------------------------------------------------------------------
@app.post(
    "/chat",
    tags=["Chat API"],
    summary="Interactive Chat Window Endpoint"
)
async def chat_endpoint(request: ChatRequest):
    """
    Primary endpoint for the chat interface. Handles session_id and keeps last 5 exchanges in SQLite.
    """
    clean_msg = request.message.strip()
    if not clean_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    uid = request.user_id or "admin"
    req_mode = request.mode or "generic"
    sid = request.session_id or f"sess_{int(time.time())}"

    try:
        rag_res = await run_in_threadpool(
            execute_rag_pipeline,
            query=clean_msg,
            user_id=uid,
            top_k=5,
            generate_answer=True,
            mode=req_mode,
            conversation_id=sid,
            user_profile=request.user_profile,
            chat_history=request.chat_history
        )
        return JSONResponse(status_code=200, content={
            "success": True,
            "session_id": sid,
            "mode": req_mode,
            "user_id": uid,
            "question": rag_res["question"],
            "answer": rag_res["answer"],
            "answer_html": rag_res.get("answer_html"),
            "recommended_products": rag_res.get("recommended_products", []),
            "disambiguation_options": rag_res.get("disambiguation_options", []),
            "ai_model": rag_res.get("ai_model"),
            "duration_ms": rag_res.get("duration_ms")
        })
    except UserNotFoundError:
        rag_res = await run_in_threadpool(
            execute_rag_pipeline,
            query=clean_msg,
            user_id="guest",
            top_k=5,
            generate_answer=True,
            mode=req_mode,
            conversation_id=sid,
            user_profile=request.user_profile,
            chat_history=request.chat_history
        )
        return JSONResponse(status_code=200, content={
            "success": True,
            "session_id": sid,
            "mode": req_mode,
            "user_id": "guest",
            "question": rag_res["question"],
            "answer": rag_res["answer"],
            "answer_html": rag_res.get("answer_html"),
            "recommended_products": rag_res.get("recommended_products", []),
            "disambiguation_options": rag_res.get("disambiguation_options", []),
            "ai_model": rag_res.get("ai_model"),
            "duration_ms": rag_res.get("duration_ms")
        })
    except Exception as e:
        logger.error(f"[Chat Endpoint] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {str(e)}")


@app.post(
    "/chat/stream",
    tags=["Chat API"],
    summary="Interactive Chat SSE Streaming Endpoint"
)
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint for the UI. Streams tokens live and records turn under session_id.
    """
    ask_req = AskRequest(
        user_id=request.user_id or "admin",
        question=request.message.strip(),
        conversation_id=request.session_id,
        session_id=request.session_id,
        mode=request.mode or "generic",
        user_profile=request.user_profile,
        chat_history=request.chat_history
    )
    return await ask_api_v1_stream(ask_req)


@app.post(
    "/chat/reset",
    tags=["Chat API"],
    summary="Reset Chat Session History"
)
@app.delete(
    "/chat/reset",
    tags=["Chat API"],
    summary="Reset Chat Session History"
)
async def chat_reset_endpoint(request: Request):
    """
    Clears memory and SQLite turns for the session.
    Accepts JSON body: {"session_id": "..."} or query parameter ?session_id=...
    """
    sid = None
    uid = None
    req_mode = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            sid = body.get("session_id")
            uid = body.get("user_id")
            req_mode = body.get("mode")
    except Exception:
        pass

    if not sid:
        sid = request.query_params.get("session_id")
    if not uid:
        uid = request.query_params.get("user_id")
    if not req_mode:
        req_mode = request.query_params.get("mode")

    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required to reset chat session.")

    conv_memory = get_conversation_memory()
    conv_memory.clear_session(session_id=sid, user_id=uid, mode=req_mode)
    return JSONResponse(status_code=200, content={
        "success": True,
        "message": f"Chat session '{sid}' reset successfully.",
        "session_id": sid,
        "mode": req_mode
    })


@app.get(
    "/api/chat/history",
    tags=["Chat API"],
    summary="Get conversation history for session"
)
async def get_chat_history_endpoint(session_id: str, user_id: Optional[str] = "guest"):
    """
    Returns recent multi-turn conversation turns for the active session.
    """
    conv_memory = get_conversation_memory()
    history = conv_memory.get_chat_history(user_id=user_id, conversation_id=session_id, max_turns=10)
    return JSONResponse(status_code=200, content={
        "session_id": session_id,
        "user_id": user_id,
        "turns": history
    })


@app.get(
    "/api/system/stats",
    tags=["System Health"],
    summary="Get real-time system stats and database counts"
)
async def get_system_stats():
    """
    Returns live MySQL table counts, cache metrics, and system status for the UI inspector.
    """
    user_db = get_user_db()
    cache = get_semantic_cache()

    mysql_counts = {}
    if getattr(user_db, "has_mysql", False):
        try:
            with user_db._get_mysql_conn() as conn:
                with conn.cursor() as cur:
                    for tbl in ("users", "purchases", "past_records", "conversation_turns"):
                        cur.execute(f"SELECT COUNT(*) as cnt FROM {tbl}")
                        res = cur.fetchone()
                        mysql_counts[tbl] = res.get("cnt") if isinstance(res, dict) else res[0]
        except Exception:
            pass

    return JSONResponse(status_code=200, content={
        "status": "ok",
        "backend": user_db.backend,
        "mysql_counts": mysql_counts,
        "cache_entries": len(getattr(cache, "_cache", {}))
    })


@app.post(
    "/api/webhooks/woocommerce",
    tags=["WooCommerce Integration"],
    summary="WooCommerce Real-Time Order & Customer Webhook"
)
@app.post(
    "/api/v1/woocommerce/webhook",
    tags=["WooCommerce Integration"],
    summary="WooCommerce Real-Time Order & Customer Webhook (Legacy Route)"
)
async def woocommerce_webhook(request: Request):
    """
    Receives real-time push events from WooCommerce (Customer Created, Customer Updated, Order Created, Order Updated).
    Cryptographically verifies the HMAC-SHA256 signature, syncs users and orders directly to MySQL,
    and appends event telemetry to logs/sync.log.
    """
    raw_body = await request.body()
    secret = os.getenv("WC_WEBHOOK_SECRET", "dsh_wc_webhook_secret_2026_k9X2").strip()

    # 1. Cryptographic HMAC-SHA256 Signature Verification
    signature = request.headers.get("x-wc-webhook-signature", "").strip()
    if secret and signature:
        expected_sig = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("utf-8")
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning(f"[WooCommerce Webhook] Unauthorized: Invalid HMAC signature. Received='{signature}'")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 2. Parse Payload & Headers
    topic = request.headers.get("x-wc-webhook-topic", "").strip().lower()
    resource = request.headers.get("x-wc-webhook-resource", "").strip().lower()
    webhook_id = request.headers.get("x-wc-webhook-id", "")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 3. Handle WordPress Test Ping
    if not payload or payload.get("webhook_id") or topic in ("ping", "webhook.ping"):
        logger.info(f"[WooCommerce Webhook] Acknowledged WordPress test ping (ID: {webhook_id or payload.get('webhook_id')})")
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "Webhook ping verified successfully",
            "webhook_id": webhook_id or payload.get("webhook_id")
        })

    user_db = get_user_db()
    sync_log_path = Path(__file__).resolve().parent / "logs" / "sync.log"
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

    try:
        # 4. Route Customer Created / Updated Events
        if "customer" in topic or resource == "customer" or ("username" in payload and "line_items" not in payload):
            profile = user_db.ingest_woocommerce_customer_webhook(payload)
            log_line = f"{timestamp_str} [INFO] [WEBHOOK] New Customer Joined: {profile.get('name')} ({profile.get('email')})\n"
            try:
                with open(sync_log_path, "a", encoding="utf-8") as lf:
                    lf.write(log_line)
            except Exception:
                pass
            logger.info(f"[WooCommerce Webhook] Synced new customer: {profile.get('name')} ({profile.get('email')})")
            return JSONResponse(status_code=200, content={
                "status": "success",
                "event": "customer.created",
                "user_id": profile.get("user_id"),
                "name": profile.get("name"),
                "email": profile.get("email")
            })

        # 5. Route Order Created / Updated Events
        profile = user_db.ingest_woocommerce_order_webhook(payload)
        order_id = payload.get("id")
        order_status = payload.get("status", "completed")
        purchases_count = len(profile.get("all_purchases", []))
        log_line = f"{timestamp_str} [INFO] [WEBHOOK] Order #{order_id} ({order_status}): {profile.get('name')} ({profile.get('email')}) - {purchases_count} items active\n"
        try:
            with open(sync_log_path, "a", encoding="utf-8") as lf:
                lf.write(log_line)
        except Exception:
            pass

        logger.info(f"[WooCommerce Webhook] Synced order #{order_id} ({order_status}) for {profile.get('name')}")
        return JSONResponse(status_code=200, content={
            "status": "success",
            "event": "order.updated",
            "order_id": order_id,
            "order_status": order_status,
            "user_id": profile.get("user_id"),
            "email": profile.get("email"),
            "purchases_count": purchases_count
        })

    except Exception as e:
        logger.error(f"[WooCommerce Webhook] Error processing payload: {str(e)}", exc_info=True)
        return JSONResponse(status_code=200, content={
            "status": "skipped",
            "reason": str(e)
        })


@app.post(
    "/drive/webhook",
    tags=["Google Drive Ingestion"],
    summary="Google Drive Push Notification Webhook"
)
@app.post(
    "/api/v1/drive/webhook",
    tags=["Google Drive Ingestion"],
    summary="Google Drive Push Notification Webhook"
)
async def google_drive_webhook(request: Request):
    """
    Receives instant push notifications from Google Drive Watch API.
    When a file is uploaded, modified, or deleted in the target Drive folder,
    Google sends a webhook notification here, triggering instant ingestion.
    """
    import threading
    headers = dict(request.headers)
    resource_state = headers.get("x-goog-resource-state", "unknown")
    channel_id = headers.get("x-goog-channel-id", "")
    message_number = headers.get("x-goog-message-number", "")

    logger.info(
        f"[Google Drive Webhook] Notification received: state='{resource_state}', channel='{channel_id}', msg='{message_number}'"
    )

    if resource_state.lower() == "sync":
        return JSONResponse(status_code=200, content={"status": "sync_acknowledged"})

    monitor = get_drive_monitor()
    threading.Thread(target=monitor.scan_and_process, name="DriveWebhookIngestion", daemon=True).start()

    return JSONResponse(status_code=200, content={"status": "ingestion_triggered", "state": resource_state})


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["RAG API"],
    summary="Health check for REST API and dependencies"
)
async def health_api_v1():
    """
    Returns dependency availability (Qdrant, LLM service, embeddings, customer database)
    without exposing credentials or sensitive internals.
    """
    qdrant = get_qdrant_service()
    generator = get_generator_service()
    user_db = get_user_db()
    
    qdrant_status = "connected"
    try:
        qdrant.client.get_collection(qdrant.collection_name)
    except Exception:
        qdrant_status = "disconnected"

    return {
        "status": "ok",
        "qdrant": qdrant_status,
        "llm_service": "configured" if generator.is_configured() else "not configured",
        "embeddings": "ready",
        "user_database": f"ready ({user_db.backend})"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

