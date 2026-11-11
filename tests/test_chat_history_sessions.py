import pytest
import time
from fastapi.testclient import TestClient
from app import app
from src.session_auth import create_session_token
from src.conversation_memory import get_conversation_memory

client = TestClient(app)

def test_chat_sessions_endpoints():
    conv_memory = get_conversation_memory()
    test_sid = f"test_hist_{int(time.time())}"
    uid = "test_user_hist"
    
    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Record a turn to create a session
    conv_memory.record_turn(
        user_id=uid,
        conversation_id=test_sid,
        user_query="What is the science of secure attachment?",
        assistant_answer="Secure attachment is characterized by emotional safety and trust.",
        retrieved_chunks=[],
        mode="generic"
    )

    # 2. Test GET /api/chat/sessions
    res = client.get("/api/chat/sessions", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert any(s["session_id"] == test_sid for s in data["sessions"])
    
    # Check title derivation
    matching_session = next(s for s in data["sessions"] if s["session_id"] == test_sid)
    assert "science of secure attachment" in matching_session["title"].lower()

    # 3. Test GET /api/chat/history
    res_hist = client.get(f"/api/chat/history?session_id={test_sid}", headers=headers)
    assert res_hist.status_code == 200
    hist_data = res_hist.json()
    assert len(hist_data["turns"]) >= 2
    assert hist_data["turns"][0]["content"] == "What is the science of secure attachment?"

    # 4. Test DELETE /api/chat/sessions/{session_id}
    res_del = client.delete(f"/api/chat/sessions/{test_sid}", headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # 5. Verify it's gone from /api/chat/sessions
    res_after = client.get("/api/chat/sessions", headers=headers)
    assert not any(s["session_id"] == test_sid for s in res_after.json()["sessions"])


def test_chat_sessions_mode_isolation():
    conv_memory = get_conversation_memory()
    ts = int(time.time() * 1000)
    generic_sid = f"test_generic_mode_{ts}"
    sales_sid = f"test_sales_mode_{ts}"
    uid = f"test_user_mode_{ts}"

    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    conv_memory.record_turn(
        user_id=uid,
        conversation_id=generic_sid,
        user_query="Explain anxious attachment calmly.",
        assistant_answer="Anxious attachment relates to heightened threat sensitivity.",
        retrieved_chunks=[],
        mode="generic"
    )
    conv_memory.record_turn(
        user_id=uid,
        conversation_id=sales_sid,
        user_query="Which course helps with breakup recovery?",
        assistant_answer="The Anxious Attachment Masterclass ($97) covers this.",
        retrieved_chunks=[],
        mode="sales"
    )

    try:
        # 1. Generic filter only returns generic session
        res_gen = client.get("/api/chat/sessions?mode=generic", headers=headers)
        assert res_gen.status_code == 200
        gen_sids = {s["session_id"] for s in res_gen.json()["sessions"]}
        assert generic_sid in gen_sids
        assert sales_sid not in gen_sids

        # 2. Sales filter only returns sales session
        res_sales = client.get("/api/chat/sessions?mode=sales", headers=headers)
        assert res_sales.status_code == 200
        sales_sids = {s["session_id"] for s in res_sales.json()["sessions"]}
        assert sales_sid in sales_sids
        assert generic_sid not in sales_sids

        # 3. Unfiltered returns both for backward compatibility
        res_all = client.get("/api/chat/sessions", headers=headers)
        assert res_all.status_code == 200
        all_sids = {s["session_id"] for s in res_all.json()["sessions"]}
        assert generic_sid in all_sids
        assert sales_sid in all_sids

        # 4. Mode-scoped history lookup
        res_mismatch = client.get(f"/api/chat/history?session_id={sales_sid}&mode=generic", headers=headers)
        assert res_mismatch.status_code == 404
        res_match = client.get(f"/api/chat/history?session_id={sales_sid}&mode=sales", headers=headers)
        assert res_match.status_code == 200
    finally:
        client.delete(f"/api/chat/sessions/{generic_sid}", headers=headers)
        client.delete(f"/api/chat/sessions/{sales_sid}", headers=headers)


def test_read_only_history_not_rate_limited():
    conv_memory = get_conversation_memory()
    ts = int(time.time() * 1000)
    sid = f"test_ratelimit_read_{ts}"
    uid = f"test_user_rl_{ts}"

    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    conv_memory.record_turn(
        user_id=uid,
        conversation_id=sid,
        user_query="Quick check turn",
        assistant_answer="Recorded answer",
        retrieved_chunks=[],
        mode="sales"
    )

    try:
        for _ in range(20):
            r_sess = client.get("/api/chat/sessions?mode=sales", headers=headers)
            assert r_sess.status_code == 200
            r_hist = client.get(f"/api/chat/history?session_id={sid}&mode=sales", headers=headers)
            assert r_hist.status_code == 200
    finally:
        client.delete(f"/api/chat/sessions/{sid}", headers=headers)


def test_sequential_numbering_and_clear_all_sessions():
    conv_memory = get_conversation_memory()
    ts = int(time.time() * 1000)
    uid = f"test_user_seq_{ts}"
    other_uid = f"test_user_seq_other_{ts}"
    s1 = f"test_seq_1_{ts}"
    s2 = f"test_seq_2_{ts}"
    sg = f"test_seq_gen_{ts}"
    s_other = f"test_seq_other_{ts}"

    token = create_session_token(user_id=uid)["token"]
    headers = {"Authorization": f"Bearer {token}"}
    other_token = create_session_token(user_id=other_uid)["token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    conv_memory.record_turn(uid, s1, "First sales chat", "Answer 1", [], mode="sales")
    time.sleep(0.02)
    conv_memory.record_turn(uid, s2, "Second sales chat", "Answer 2", [], mode="sales")
    conv_memory.record_turn(uid, sg, "First clinical chat", "Clinical 1", [], mode="generic")
    conv_memory.record_turn(other_uid, s_other, "Other user sales", "Other answer", [], mode="sales")

    try:
        # 1. Verify chronological 1st, 2nd numbering
        res = client.get("/api/chat/sessions?mode=sales", headers=headers)
        assert res.status_code == 200
        sessions = res.json()["sessions"]
        assert [s["session_id"] for s in sessions] == [s1, s2]
        assert [s["chat_number"] for s in sessions] == [1, 2]

        # 2. Unauthenticated clear returns 401
        assert client.delete("/api/chat/sessions?mode=sales").status_code == 401

        # 3. Clear only active user's sales sessions
        res_clr = client.delete("/api/chat/sessions?mode=sales", headers=headers)
        assert res_clr.status_code == 200
        assert res_clr.json()["success"] is True

        # Sales sessions cleared, generic preserved, other user untouched
        assert client.get("/api/chat/sessions?mode=sales", headers=headers).json()["sessions"] == []
        gen_sessions = client.get("/api/chat/sessions?mode=generic", headers=headers).json()["sessions"]
        assert len(gen_sessions) == 1 and gen_sessions[0]["session_id"] == sg and gen_sessions[0]["chat_number"] == 1
        other_sessions = client.get("/api/chat/sessions?mode=sales", headers=other_headers).json()["sessions"]
        assert len(other_sessions) == 1 and other_sessions[0]["session_id"] == s_other
    finally:
        client.delete("/api/chat/sessions", headers=headers)
        client.delete("/api/chat/sessions", headers=other_headers)


def test_rename_chat_session_isolation():
    conv_memory = get_conversation_memory()
    ts = int(time.time() * 1000)
    uid = f"test_user_ren_{ts}"
    other_uid = f"test_other_ren_{ts}"
    sid = f"test_ren_{ts}"

    headers = {"Authorization": f"Bearer {create_session_token(user_id=uid)['token']}"}
    other_headers = {"Authorization": f"Bearer {create_session_token(user_id=other_uid)['token']}"}

    conv_memory.record_turn(uid, sid, "Initial message title", "Response", [], mode="generic")
    try:
        # 1. Unauthenticated rename returns 401
        assert client.patch(f"/api/chat/sessions/{sid}", json={"title": "Hacked"}).status_code == 401

        # 2. Other user attempting rename returns 404
        res_other = client.patch(
            f"/api/chat/sessions/{sid}",
            json={"title": "Stolen"},
            headers=other_headers
        )
        assert res_other.status_code == 404

        # 3. Owner renames successfully and list reflects custom title
        res_ok = client.patch(
            f"/api/chat/sessions/{sid}",
            json={"title": "Renamed Clinical Topic"},
            headers=headers
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["title"] == "Renamed Clinical Topic"

        sessions = client.get("/api/chat/sessions?mode=generic", headers=headers).json()["sessions"]
        matched = next(s for s in sessions if s["session_id"] == sid)
        assert matched["title"] == "Renamed Clinical Topic"
    finally:
        client.delete("/api/chat/sessions", headers=headers)


def test_react_ui_served():
    res = client.get("/")
    assert res.status_code == 200
    assert '<div id="root"></div>' in res.text
    assert "/assets/" in res.text





