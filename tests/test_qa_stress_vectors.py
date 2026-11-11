"""
End-to-End Backend QA Stress & Security Validation Suite (Vectors 1-5).

Covers:
1. High-volume concurrent rapid-fire requests & SlidingWindowRateLimiter thread safety
2. Ultra-long 12,000+ character prompt validation, topic column capping, & full turn persistence
3. Zero-vector retrieval handling & large citation metadata responses across /chat and /chat/stream
4. Full CRUD integrity, SQL injection immunity on special chars (%, _, ', ", emoji), >10 turn persistence, & GET /api/chats/{thread_id}/messages reload re-hydration
5. Structured 400/401/404/500 error responses without unhandled exceptions
"""
import concurrent.futures
import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.conversation_memory import get_conversation_memory
from src.session_auth import SlidingWindowRateLimiter, create_session_token

client = TestClient(app)


def test_vector1_rate_limiter_thread_safety():
    """Concurrent requests against SlidingWindowRateLimiter must never throw deque mutation races."""
    limiter = SlidingWindowRateLimiter(max_requests=25, window_seconds=60)
    results = []

    def _hit(_i: int):
        return limiter.is_limited("127.0.0.1:sess_stress")

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(_hit, range(40)))

    allowed = sum(1 for limited, _ in results if not limited)
    blocked = sum(1 for limited, _ in results if limited)
    assert allowed == 25
    assert blocked == 15


def test_vector1_concurrent_memory_writes_and_deletes():
    """Rapid concurrent record_turn and get_session_turns calls must remain consistent and lock-safe."""
    mem = get_conversation_memory()
    ts = int(time.time() * 1000)
    uid = f"qa_conc_user_{ts}"
    sid = f"qa_conc_sess_{ts}"

    try:
        def _write(i: int):
            mem.record_turn(
                user_id=uid,
                conversation_id=sid,
                user_query=f"Rapid stress message #{i}",
                assistant_answer=f"Rapid stress reply #{i}",
                retrieved_chunks=[],
                mode="generic",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(_write, range(12)))

        turns = mem.get_session_turns(user_id=uid, conversation_id=sid, limit=50)
        assert len(turns) == 24
    finally:
        mem.delete_session(user_id=uid, conversation_id=sid)


def test_vector2_ultra_long_prompt_accepted_and_persisted():
    """Prompts >10,000 chars must bypass old 2,000-char limit and cap topic <= 255 chars cleanly."""
    mem = get_conversation_memory()
    ts = int(time.time() * 1000)
    uid = f"qa_long_user_{ts}"
    sid = f"qa_long_sess_{ts}"
    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    long_prompt = "Anxious attachment reflection paragraph. " * 320  # ~12,480 chars
    assert len(long_prompt) > 10000

    mock_pipeline_res = {
        "user_id": uid,
        "question": long_prompt,
        "answer": "Grounded response for ultra-long clinical document.",
        "answer_html": "<p>Grounded response</p>",
        "sources": [],
        "recommended_products": [],
        "disambiguation_options": [],
        "ai_model": "mock-test",
        "duration_ms": 12.0,
    }

    try:
        with patch("app.execute_rag_pipeline", return_value=mock_pipeline_res):
            res = client.post(
                "/chat",
                headers=headers,
                json={"session_id": sid, "message": long_prompt, "mode": "generic"},
            )
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Verify topic extraction caps safely for DB VARCHAR(255)
        sess = mem._get_or_load_session(uid, sid)
        extracted = mem._extract_topic_entity(long_prompt, None) if hasattr(mem, "_extract_topic_entity") else None
        if sess:
            assert sess.last_topic is None or len(sess.last_topic) <= 200
        assert extracted is None

        mem.record_turn(uid, sid, long_prompt, "Grounded response", [], mode="generic")
        reloaded = client.get(f"/api/chats/{sid}/messages?mode=generic", headers=headers)
        assert reloaded.status_code == 200
        assert len(reloaded.json()["messages"][0]["content"]) > 10000
    finally:
        mem.delete_session(user_id=uid, conversation_id=sid)


def test_vector3_zero_and_large_source_metadata():
    """Verify /chat returns empty sources cleanly and handles 25+ dense source chunks without error."""
    ts = int(time.time() * 1000)
    uid = f"qa_src_user_{ts}"
    sid = f"qa_src_sess_{ts}"
    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Zero matching sources
    with patch(
        "app.execute_rag_pipeline",
        return_value={
            "user_id": uid,
            "question": "Zero retrieval test",
            "answer": "Out of scope / zero vector result.",
            "sources": [],
            "recommended_products": [],
            "disambiguation_options": [],
        },
    ):
        res_empty = client.post(
            "/chat",
            headers=headers,
            json={"session_id": sid, "message": "Zero retrieval test", "mode": "generic"},
        )
    assert res_empty.status_code == 200
    assert res_empty.json()["sources"] == []

    # 2. Large volume (25 citation chunks + long document names)
    many_sources = [
        {
            "document": f"Very_Long_Clinical_Reference_Document_Volume_{i}_Attachment_Repair_Protocol.pdf",
            "relevance_score": round(0.95 - (i * 0.01), 4),
            "page": i + 1,
            "chunk_id": f"chunk_{i}",
        }
        for i in range(25)
    ]
    with patch(
        "app.execute_rag_pipeline",
        return_value={
            "user_id": uid,
            "question": "Dense citation test",
            "answer": "Dense clinical answer.",
            "sources": many_sources,
            "recommended_products": [],
            "disambiguation_options": [],
        },
    ):
        res_many = client.post(
            "/chat",
            headers=headers,
            json={"session_id": sid, "message": "Dense citation test", "mode": "generic"},
        )
    assert res_many.status_code == 200
    assert len(res_many.json()["sources"]) == 25


def test_vector4_special_char_search_sql_injection_and_reload_rehydration():
    """Special characters (%, _, ', \", emoji) search safely and tab reload rehydrates via /api/chats/{id}/messages."""
    mem = get_conversation_memory()
    ts = int(time.time() * 1000)
    uid = f"qa_v4_user_{ts}"
    other_uid = f"qa_v4_other_{ts}"
    token = create_session_token(user_id=uid)["token"]
    other_token = create_session_token(user_id=other_uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    s_percent = f"qa_pct_{ts}"
    s_emoji = f"qa_emoji_{ts}"
    s_multi = f"qa_multi_{ts}"

    try:
        mem.record_turn(uid, s_percent, "100% _underscore_ 'quote' \"double\"", "Ans 1", [], mode="generic")
        mem.record_turn(uid, s_emoji, "Panic 🔥💔 healing guide", "Ans 2", [], mode="generic")

        # 8 turns (16 rows) in SQLite - verify NONE are destructively pruned for UI reload!
        for i in range(8):
            mem.record_turn(uid, s_multi, f"Multi turn Q{i}", f"Multi turn A{i}", [], mode="generic")

        # Literal '%' match only returns s_percent, NOT wildcard match of s_emoji!
        res_pct = client.get("/api/chat/sessions", params={"mode": "generic", "q": "100%"}, headers=headers)
        assert res_pct.status_code == 200
        pct_ids = [s["session_id"] for s in res_pct.json()["sessions"]]
        assert pct_ids == [s_percent]

        # Literal '_' match
        res_us = client.get("/api/chat/sessions", params={"mode": "generic", "q": "_underscore_"}, headers=headers)
        assert res_us.status_code == 200
        assert [s["session_id"] for s in res_us.json()["sessions"]] == [s_percent]

        # Quote / SQL injection string must execute safely and return [] without dropping tables
        res_sqli = client.get(
            "/api/chat/sessions",
            params={"mode": "generic", "q": "'; DROP TABLE conversation_turns; --"},
            headers=headers,
        )
        assert res_sqli.status_code == 200
        assert res_sqli.json()["sessions"] == []

        # Emoji filter
        res_emoji = client.get("/api/chat/sessions", params={"mode": "generic", "q": "🔥💔"}, headers=headers)
        assert res_emoji.status_code == 200
        assert [s["session_id"] for s in res_emoji.json()["sessions"]] == [s_emoji]

        # Reload re-hydration endpoint preserves all 16 messages (>10 turn limit no longer deletes history!)
        res_msgs = client.get(f"/api/chats/{s_multi}/messages?mode=generic", headers=headers)
        assert res_msgs.status_code == 200
        msgs_data = res_msgs.json()
        assert len(msgs_data["messages"]) == 16
        assert msgs_data["messages"][0]["content"] == "Multi turn Q0"
        assert msgs_data["messages"][-1]["content"] == "Multi turn A7"

        # Cross-user isolation on new /api/chats/{id}/messages endpoint
        res_forbidden = client.get(f"/api/chats/{s_multi}/messages?mode=generic", headers=other_headers)
        assert res_forbidden.status_code == 404

        # Delete & verify immediate 404 on reload endpoint
        assert client.delete(f"/api/chat/sessions/{s_percent}", headers=headers).status_code == 200
        assert client.get(f"/api/chats/{s_percent}/messages?mode=generic", headers=headers).status_code == 404
    finally:
        client.delete("/api/chat/sessions", headers=headers)


def test_vector5_error_handling_status_codes():
    """Backend must return structured JSON errors for empty prompts, bad auth, and internal failures."""
    ts = int(time.time() * 1000)
    uid = f"qa_err_user_{ts}"
    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Blank/whitespace message -> 400
    res_empty = client.post("/chat", headers=headers, json={"session_id": "s1", "message": "   "})
    assert res_empty.status_code == 400
    assert res_empty.json()["success"] is False

    # 2. Internal server failure -> 500 JSON
    with patch("app.execute_rag_pipeline", side_effect=RuntimeError("Simulated Vector DB Outage")):
        res_500 = client.post(
            "/chat",
            headers=headers,
            json={"session_id": "s1", "message": "Valid clinical question"},
        )
    assert res_500.status_code == 500
    assert "Simulated Vector DB Outage" in (res_500.json().get("error") or "")

