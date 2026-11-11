from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import app
from src.config import get_platform_collection_name, resolve_target_collection
from src.conversation_memory import ConversationMemoryManager
from src.generator import OpenAIGeneratorService
from src.rag_service import execute_rag_pipeline
from src.search import search_similar_chunks
from src.session_auth import create_session_token


def _auth_headers(user_id: str = "platform_tester", mode: str = "platform"):
    token = create_session_token(user_id=user_id, mode=mode)["token"]
    return {"Authorization": f"Bearer {token}"}


def test_platform_collection_routing_and_clinical_protection(monkeypatch):
    monkeypatch.delenv("QDRANT_PLATFORM_COLLECTION_NAME", raising=False)
    monkeypatch.setenv("GOOGLE_DRIVE_PLATFORM_FOLDER_ID", "drv_platform_123")

    assert get_platform_collection_name() == "platform_guide"

    # Explicit category routes to platform_guide
    res_cat = resolve_target_collection(category="platform", filename="guide.md")
    assert res_cat["collection_name"] == "platform_guide"
    assert res_cat["category"] == "platform"

    # Dedicated Google Drive Platform folder ID routes to platform_guide
    res_fid = resolve_target_collection(folder_id="drv_platform_123", filename="getting_started.pdf")
    assert res_fid["collection_name"] == "platform_guide"
    assert res_fid["collection_key"] == "platform"

    # Platform folder/file heuristics route to platform_guide
    res_fname = resolve_target_collection(folder_name="Portal Helpdesk", filename="login_steps.md")
    assert res_fname["collection_name"] == "platform_guide"
    assert res_fname["category"] == "platform"

    # Env override applies consistently across folder & filename heuristics
    monkeypatch.setenv("QDRANT_PLATFORM_COLLECTION_NAME", "custom_portal_docs")
    res_override = resolve_target_collection(filename="portal_password_reset.md")
    assert res_override["collection_name"] == "custom_portal_docs"

    # Clinical FAQ filenames must NOT be hijacked into platform_guide
    res_clinical = resolve_target_collection(folder_name="Tools", filename="boundary_ladder_faq.pdf")
    assert res_clinical["category"] == "clinical"
    assert res_clinical["collection_key"] == "tools"


@patch("src.search.get_qdrant_service")
@patch("src.search.get_embedding_service")
def test_search_platform_mode_isolated_and_no_clinical_expansion(mock_embed_svc, mock_qdrant_svc):
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_embed_svc.return_value = embedder

    qdrant = MagicMock()
    qdrant.collection_name = "documents"
    qdrant.search_similar.return_value = [
        {
            "document_id": "p1",
            "document_name": "portal_guide.md",
            "chunk_id": 1,
            "text": "Click Forgot Password on the login page to reset your password.",
            "score": 0.91,
            "category": "platform",
            "collection_key": "platform",
        },
        {
            "document_id": "c1",
            "document_name": "attachment_clinical.pdf",
            "chunk_id": 99,
            "text": "Clinical attachment text that must not leak.",
            "score": 0.95,
            "category": "clinical",
            "collection_key": "journals",
        },
    ]
    mock_qdrant_svc.return_value = qdrant

    res = search_similar_chunks("How do I reset my password?", top_k=5, mode="platform", use_reranker=False)

    # Query must NOT be clinically expanded in platform mode
    embedder.embed_query.assert_called_once_with("How do I reset my password?")
    # Strictly queries platform_guide only
    qdrant.search_similar.assert_called_once()
    assert qdrant.search_similar.call_args.kwargs["collection_name"] == "platform_guide"

    # Clinical/sales leaked payloads are excluded by lane filter
    assert len(res["results"]) == 1
    assert res["results"][0]["document_id"] == "p1"
    assert res["results"][0]["collection_key"] == "platform"


def test_conversation_memory_preserves_platform_mode_isolation(tmp_path, monkeypatch):
    monkeypatch.delenv("MYSQL_HOST", raising=False)
    mgr = ConversationMemoryManager()
    mgr.has_mysql = False
    mgr.db_path = tmp_path / "test_platform_memory.db"
    mgr._init_sqlite()

    mgr.record_turn(
        user_id="user_42",
        conversation_id="sess_plat_1",
        user_query="Where do I find my workbook download?",
        assistant_answer="Open your Course Dashboard and select Downloads.",
        retrieved_chunks=[],
        mode="platform",
    )
    mgr.record_turn(
        user_id="user_42",
        conversation_id="sess_gen_1",
        user_query="Why do avoidant partners shut down?",
        assistant_answer="Nervous system deactivation protects against overwhelm.",
        retrieved_chunks=[],
        mode="generic",
    )
    mgr.record_turn(
        user_id="user_42",
        conversation_id="sess_sales_1",
        user_query="Which course should I enroll in?",
        assistant_answer="I recommend the Avoidant Attachment course.",
        retrieved_chunks=[],
        mode="sales",
    )

    plat_sessions = mgr.get_recent_sessions("user_42", mode="platform")
    assert len(plat_sessions) == 1
    assert plat_sessions[0]["session_id"] == "sess_plat_1"
    assert plat_sessions[0]["mode"] == "platform"

    gen_sessions = mgr.get_recent_sessions("user_42", mode="generic")
    assert [s["session_id"] for s in gen_sessions] == ["sess_gen_1"]

    # Mode-filtered turn lookup refuses cross-mode leakage
    assert mgr.get_session_turns("user_42", "sess_plat_1", mode="generic") == []
    assert len(mgr.get_session_turns("user_42", "sess_plat_1", mode="platform")) == 2

    # Mode-scoped bulk delete removes only platform turns/sessions
    deleted = mgr.delete_all_sessions("user_42", mode="platform")
    assert deleted == 2
    assert mgr.get_recent_sessions("user_42", mode="platform") == []
    assert len(mgr.get_recent_sessions("user_42", mode="generic")) == 1
    assert len(mgr.get_recent_sessions("user_42", mode="sales")) == 1


def test_generator_platform_mode_prompts_and_empty_or_offtopic_guards(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    gen = OpenAIGeneratorService(api_key="sk-test-key")

    sys_prompt = gen._build_system_prompt(mode="platform")
    assert "Platform Navigation Assistant" in sys_prompt
    assert "MANDATORY OPENING GREETING & DYNAMIC USER CONTEXT" in sys_prompt
    assert "NEVER invent URLs" in sys_prompt

    greeting = gen._get_chit_chat_reply("hi", user_context={"first_name": "Maya"}, mode="platform")
    assert greeting is not None
    assert "Hello Maya!" in greeting
    assert "Platform Navigation Assistant" in greeting

    anon_greeting = gen._get_chit_chat_reply("hi", user_context={"first_name": "Website Visitor"}, mode="platform")
    assert anon_greeting is not None
    assert anon_greeting.startswith("Hi there!")

    # Empty retrieved_chunks on a portal query should NOT emit clinical psychology refusal
    empty_res = gen.generate_answer(
        query="Where do I download my course workbook?",
        retrieved_chunks=[],
        mode="platform",
        user_context={"first_name": "Maya"},
    )
    assert empty_res["out_of_domain"] is True
    assert "Platform Guide knowledge base" in empty_res["answer"]
    assert "I am dedicated exclusively to Dr. Sarah Hensley's relationship psychology" not in empty_res["answer"]

    # Off-topic query emits platform-specific scope refusal
    off_topic = gen.generate_answer(
        query="Write me a python script to scrape websites",
        retrieved_chunks=[],
        mode="platform",
    )
    assert off_topic["out_of_domain"] is True
    assert "Platform Navigation Assistant" in off_topic["answer"]

    # Streaming empty-chunks fallback matches platform mode cleanly
    stream_events = list(gen.generate_answer_stream(
        query="Where is my billing invoice?",
        retrieved_chunks=[],
        mode="platform",
    ))
    assert any(ev.get("done") and "Platform Guide knowledge base" in ev.get("full_answer", "") for ev in stream_events)


def test_generator_platform_mode_grounded_completion(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    gen = OpenAIGeneratorService(api_key="sk-test-key")

    fake_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="1. Go to Login.\n2. Click Forgot Password."))],
        usage=None,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_resp
    gen._client = mock_client

    chunks = [
        {
            "document_id": "doc_p1",
            "document_name": "PLATFORM_PORTAL_GUIDE.md",
            "page": 1,
            "chunk_id": 1,
            "score": 0.25,  # Below min_vector_threshold to prove PLATFORM_DOMAIN_REGEX domain match passes gate
            "vector_score": 0.25,
            "rerank_score": 0.15,
            "text": "Open the Login page and select Forgot Password to reset your password.",
        }
    ]
    res = gen.generate_answer(
        query="How can I reset my portal password?",
        retrieved_chunks=chunks,
        mode="platform",
        user_context={"first_name": "Alex"},
    )
    assert res["answer"].startswith("Hello Alex!")
    assert "Forgot Password" in res["answer"]
    assert len(res["citations"]) == 1
    assert res["citations"][0]["document_name"] == "PLATFORM_PORTAL_GUIDE.md"

    # Unauthenticated Turn 1 falls back to warm generic greeting
    res_anon = gen.generate_answer(
        query="How can I reset my portal password?",
        retrieved_chunks=chunks,
        mode="platform",
        user_context={"first_name": "Website Visitor"},
    )
    assert res_anon["answer"].startswith("Hi there!")

    # Rapid follow-up with prior assistant message avoids repetitive greeting fluff
    res_followup = gen.generate_answer(
        query="What if I don't receive the email?",
        retrieved_chunks=chunks,
        mode="platform",
        user_context={"first_name": "Alex"},
        chat_history=[
            {"role": "user", "content": "How can I reset my portal password?"},
            {"role": "assistant", "content": "Hello Alex!\n\n1. Go to Login.\n2. Click Forgot Password."},
        ],
    )
    assert not res_followup["answer"].startswith("Hello Alex!")
    assert mock_client.chat.completions.create.call_count == 3


@patch("src.rag_service.get_semantic_cache")
@patch("src.rag_service.get_generator_service")
@patch("src.rag_service.search_similar_chunks")
@patch("src.rag_service.get_embedding_service")
@patch("src.rag_service.get_user_db")
@patch("src.conversation_memory.get_conversation_memory")
def test_pipeline_platform_vague_help_and_greeting(
    mock_mem_svc, mock_user_db, mock_embed_svc, mock_search, mock_gen_svc, mock_cache_svc, monkeypatch
):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    db = MagicMock()
    db.get_user_profile.return_value = None
    mock_user_db.return_value = db

    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_embed_svc.return_value = embedder

    mem = MagicMock()
    mem.resolve_follow_up.return_value = ("help me", False, [])
    mem.get_history.return_value = []
    mock_mem_svc.return_value = mem

    cache = MagicMock()
    cache.lookup.return_value = None
    mock_cache_svc.return_value = cache

    mock_search.return_value = {"results": [], "query_vector": [0.1]}
    gen = OpenAIGeneratorService(api_key="sk-test-key")
    mock_gen_svc.return_value = gen

    # 1. Greeting hits fast platform greeting router without vector search or LLM call
    res_greet = execute_rag_pipeline(
        query="hello",
        user_id="guest",
        mode="platform",
        conversation_id="sess_greet_1",
    )
    assert res_greet["ai_model"] == "system-greeting-router"
    assert "Membership Portal Guide" in res_greet["answer"]
    mock_search.assert_not_called()

    # 2. Ambiguous "help me" in platform mode skips clinical vague distress triage
    res_help = execute_rag_pipeline(
        query="help me",
        user_id="guest",
        mode="platform",
        conversation_id="sess_help_1",
    )
    assert res_help["ai_model"] != "diagnostic-distress-router"
    assert "Platform Navigation Assistant" in res_help["answer"]


def test_chat_and_sessions_endpoints_support_platform_mode():
    client = TestClient(app)
    headers = _auth_headers(user_id="platform_user_1", mode="platform")

    with patch("app.execute_rag_pipeline") as mock_rag:
        mock_rag.return_value = {
            "user_id": "platform_user_1",
            "question": "Where is my course dashboard?",
            "answer": "Select My Courses from the top portal menu.",
            "answer_html": "<p>Select My Courses from the top portal menu.</p>",
            "sources": [],
            "recommended_products": [],
            "disambiguation_options": [],
            "ai_model": "gpt-4o-mini",
            "duration_ms": 8.4,
        }
        res_chat = client.post(
            "/chat",
            json={"session_id": "sess_plat_http", "message": "Where is my course dashboard?", "mode": "platform"},
            headers=headers,
        )
        assert res_chat.status_code == 200
        assert res_chat.json()["mode"] == "platform"
        assert mock_rag.call_args.kwargs["mode"] == "platform"

        res_agent = client.post(
            "/api/v1/agents/platform",
            json={"session_id": "sess_plat_agent", "message": "Where is my course dashboard?"},
            headers=headers,
        )
        assert res_agent.status_code == 200
        assert res_agent.json()["mode"] == "platform"
        assert res_agent.json()["agent"] == "platform"

    with patch("app.get_conversation_memory") as mock_get_mem:
        mem = MagicMock()
        mem.get_recent_sessions.return_value = [
            {"session_id": "sess_plat_http", "mode": "platform", "title": "Where is my course dashboard?"}
        ]
        mock_get_mem.return_value = mem

        res_sessions = client.get("/api/chat/sessions?mode=platform", headers=headers)
        assert res_sessions.status_code == 200
        assert res_sessions.json()["count"] == 1
        mem.get_recent_sessions.assert_called_once_with(
            user_id="platform_user_1",
            limit=50,
            mode="platform",
            search_query=None,
        )


def test_floating_platform_widget_routes_and_sandboxed_chat():
    from src.session_auth import platform_widget_rate_limiter

    platform_widget_rate_limiter.reset()
    client = TestClient(app)

    res_js = client.get("/platform-widget.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers.get("content-type", "")
    assert "dsh-platform-bot-host" in res_js.text
    assert "/api/platform-widget/chat" in res_js.text

    res_page = client.get("/platform-bot")
    assert res_page.status_code == 200
    assert "Platform Help" in res_page.text
    assert "/platform-widget.js" in res_page.text

    res_ctx_anon = client.get("/api/platform-widget/context?current_page=/courses")
    assert res_ctx_anon.status_code == 200
    ctx_anon = res_ctx_anon.json()
    assert ctx_anon["success"] is True
    assert ctx_anon["authenticated"] is False
    assert ctx_anon["user_first_name"] == ""
    assert ctx_anon["greeting_line"] == "Hi there!"
    assert ctx_anon["current_page"] == "/courses"
    assert len(ctx_anon["suggested_actions"]) == 4

    with patch("app.get_user_db") as mock_get_db:
        db = MagicMock()
        db.get_user_profile.return_value = {"user_id": "1836", "name": "Maya Lin"}
        mock_get_db.return_value = db

        bearer_headers = _auth_headers(user_id="1836", mode="platform")

        res_ctx_auth = client.get(
            "/api/platform-widget/context?current_page=/billing",
            headers=bearer_headers,
        )
        assert res_ctx_auth.status_code == 200
        ctx_auth = res_ctx_auth.json()
        assert ctx_auth["authenticated"] is True
        assert ctx_auth["user_id"] == "1836"
        assert ctx_auth["user_first_name"] == "Maya"
        assert ctx_auth["greeting_line"] == "Hello Maya!"
        assert ctx_auth["current_page"] == "/billing"
        assert any("billing" in chip["label"].lower() or "subscription" in chip["label"].lower() for chip in ctx_auth["suggested_actions"])

    with patch("app.execute_rag_pipeline") as mock_rag:
        mock_rag.return_value = {
            "question": "How do I reset my password?",
            "answer": "Click Forgot Password on the login page.",
            "answer_html": "<p>Click Forgot Password on the login page.</p>",
            "sources": [],
            "ai_model": "gpt-4o-mini",
            "duration_ms": 9.1,
        }
        res_chat = client.post(
            "/api/platform-widget/chat",
            json={
                "session_id": "plat_demo_1",
                "message": "How do I reset my password?",
                "current_page": "/login",
            },
        )
        assert res_chat.status_code == 200
        payload = res_chat.json()
        assert payload["success"] is True
        assert payload["mode"] == "platform"
        assert payload["session_id"] == "plat_demo_1"
        assert payload["current_page"] == "/login"
        assert len(payload["suggested_actions"]) == 4
        assert "Forgot Password" in payload["answer"]
        assert mock_rag.call_args.kwargs["mode"] == "platform"
        assert mock_rag.call_args.kwargs["user_id"] == "plat_visitor_plat_demo_1"
        assert mock_rag.call_args.kwargs["user_profile"]["has_history"] is False
        assert mock_rag.call_args.kwargs["user_profile"]["current_page"] == "/login"

        with patch("app.get_user_db") as mock_get_db:
            db = MagicMock()
            db.get_user_profile.return_value = {"user_id": "1836", "name": "Maya Lin"}
            mock_get_db.return_value = db

            res_auth_chat = client.post(
                "/api/platform-widget/chat",
                json={
                    "session_id": "plat_demo_auth",
                    "message": "Where do I open my workbook?",
                    "current_page": "/courses",
                },
                headers=bearer_headers,
            )
            assert res_auth_chat.status_code == 200
            auth_payload = res_auth_chat.json()
            assert auth_payload["user_first_name"] == "Maya"
            assert mock_rag.call_args.kwargs["user_id"] == "1836"
            assert mock_rag.call_args.kwargs["user_profile"]["first_name"] == "Maya"



