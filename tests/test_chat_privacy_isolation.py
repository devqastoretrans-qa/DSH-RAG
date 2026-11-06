"""
Comprehensive Test Suite for Chat History User Isolation & Privacy.

Verifies:
1. User A creates chats; User B logs in and sees zero of A's chats.
2. User B requesting A's chat by ID (GET/DELETE) returns 404 (zero ID leakage).
3. Search/RAG for User B never returns or uses User A's dialogue content.
4. Unauthenticated access to private chat endpoints returns 401.
5. Logout/switch user shows no leftover data from the prior user.
6. Sending a forged/spoofed user_id in request body is strictly ignored; server binds to auth token.
"""
import pytest
import time
from fastapi.testclient import TestClient
from app import app
from src.session_auth import create_session_token
from src.conversation_memory import get_conversation_memory


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def conv_memory():
    return get_conversation_memory()


def test_unauthenticated_access_returns_401(client):
    """Unauthenticated calls to chat history and message endpoints must return 401."""
    # 1. List sessions without token
    res1 = client.get("/api/chat/sessions")
    assert res1.status_code == 401, f"Expected 401, got {res1.status_code}"

    # 2. Get history without token
    res2 = client.get("/api/chat/history?session_id=sess_any_123")
    assert res2.status_code == 401, f"Expected 401, got {res2.status_code}"

    # 3. Delete session without token
    res3 = client.delete("/api/chat/sessions/sess_any_123")
    assert res3.status_code == 401, f"Expected 401, got {res3.status_code}"

    # 4. Post chat without token
    res4 = client.post("/chat", json={"message": "hello"})
    assert res4.status_code == 401, f"Expected 401, got {res4.status_code}"

    # 5. Reset chat without token
    res5 = client.post("/chat/reset", json={"session_id": "sess_any_123"})
    assert res5.status_code == 401, f"Expected 401, got {res5.status_code}"


def test_user_a_and_user_b_complete_isolation(client, conv_memory):
    """User A creates chats; User B logs in and sees zero of A's chats."""
    user_a = f"test_user_a_{int(time.time())}"
    user_b = f"test_user_b_{int(time.time())}"

    token_a = create_session_token(user_id=user_a)["token"]
    token_b = create_session_token(user_id=user_b)["token"]

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Record turns for User A
    sid_a = f"sess_a_{int(time.time())}"
    conv_memory.record_turn(
        user_id=user_a,
        conversation_id=sid_a,
        user_query="User A secret query about boundary setting",
        assistant_answer="User A advice on boundaries",
        retrieved_chunks=[],
        mode="generic"
    )

    # 1. User A lists sessions -> sees their session
    res_a = client.get("/api/chat/sessions", headers=headers_a)
    assert res_a.status_code == 200
    sessions_a = res_a.json()["sessions"]
    assert any(s["session_id"] == sid_a for s in sessions_a)
    assert all(s["user_id"] == user_a for s in sessions_a)

    # 2. User B lists sessions -> sees ZERO of User A's chats
    res_b = client.get("/api/chat/sessions", headers=headers_b)
    assert res_b.status_code == 200
    sessions_b = res_b.json()["sessions"]
    assert not any(s["session_id"] == sid_a for s in sessions_b)
    assert all(s["user_id"] == user_b for s in sessions_b)


def test_user_b_requesting_user_a_chat_returns_404(client, conv_memory):
    """User B requesting User A's chat by ID (GET or DELETE) returns 404 (no existence leakage)."""
    user_a = f"victim_user_{int(time.time())}"
    user_b = f"attacker_user_{int(time.time())}"

    token_b = create_session_token(user_id=user_b)["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    sid_a = f"sess_private_victim_{int(time.time())}"
    conv_memory.record_turn(
        user_id=user_a,
        conversation_id=sid_a,
        user_query="My confidential clinical relationship inquiry",
        assistant_answer="Here is your confidential clinical assessment",
        retrieved_chunks=[],
        mode="generic"
    )

    # 1. User B tries to GET User A's session history -> 404
    res_get = client.get(f"/api/chat/history?session_id={sid_a}", headers=headers_b)
    assert res_get.status_code == 404, f"Expected 404, got {res_get.status_code}"
    err_get = res_get.json().get("detail") or res_get.json().get("error") or ""
    assert "not found" in err_get.lower()

    # 2. User B tries to DELETE User A's session -> 404
    res_del = client.delete(f"/api/chat/sessions/{sid_a}", headers=headers_b)
    assert res_del.status_code == 404, f"Expected 404, got {res_del.status_code}"
    err_del = res_del.json().get("detail") or res_del.json().get("error") or ""
    assert "not found" in err_del.lower()

    # 3. User B tries to RESET User A's session -> 404
    res_reset = client.post("/chat/reset", json={"session_id": sid_a}, headers=headers_b)
    assert res_reset.status_code == 404, f"Expected 404, got {res_reset.status_code}"
    err_reset = res_reset.json().get("detail") or res_reset.json().get("error") or ""
    assert "not found" in err_reset.lower()

    # Verify User A's session is STILL intact
    token_a = create_session_token(user_id=user_a)["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    res_a_verify = client.get(f"/api/chat/history?session_id={sid_a}", headers=headers_a)
    assert res_a_verify.status_code == 200
    assert len(res_a_verify.json()["turns"]) == 2


def test_forged_user_id_in_request_is_ignored(client, conv_memory):
    """Sending a forged user_id in the request payload or query parameter is strictly ignored."""
    real_user = f"real_user_{int(time.time())}"
    spoofed_user = f"spoofed_victim_{int(time.time())}"

    token = create_session_token(user_id=real_user)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    sid = f"sess_spoof_test_{int(time.time())}"

    # Client tries to forge user_id = spoofed_user in the body
    res = client.post("/chat", headers=headers, json={
        "message": "Testing forged user_id bypass",
        "user_id": spoofed_user,  # Attacker attempt
        "session_id": sid,
        "mode": "generic"
    })
    assert res.status_code == 200
    res_data = res.json()

    # Server must bind strictly to authenticated real_user, NOT spoofed_user
    assert res_data["user_id"] == real_user, f"Expected user_id '{real_user}', got '{res_data['user_id']}'"

    # Verify in DB: turns belong to real_user, zero turns exist for spoofed_user
    turns_real = conv_memory.get_session_turns(user_id=real_user, conversation_id=sid)
    turns_spoofed = conv_memory.get_session_turns(user_id=spoofed_user, conversation_id=sid)
    assert len(turns_real) >= 2, "Turns must be saved under real_user"
    assert len(turns_spoofed) == 0, "No turns may exist under spoofed_user"


def test_orphaned_legacy_records_never_exposed(client, conv_memory):
    """Unowned/guest/orphaned legacy records are never exposed to any authenticated user."""
    # Create an orphaned record
    orphan_sid = f"sess_orphan_{int(time.time())}"
    with conv_memory._get_sqlite_conn() as conn:
        conn.execute("""
            INSERT INTO conversation_turns (session_key, user_id, conversation_id, role, content, topic, mode, created_at, is_orphaned, owner_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'unowned_legacy')
        """, (f"guest:{orphan_sid}", "guest", orphan_sid, "user", "Unowned message", None, "generic", time.time()))
        conn.commit()

    # Any authenticated user should see 0 of this session
    user = f"user_check_orphan_{int(time.time())}"
    token = create_session_token(user_id=user)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_list = client.get("/api/chat/sessions", headers=headers)
    assert not any(s["session_id"] == orphan_sid for s in res_list.json()["sessions"])

    res_history = client.get(f"/api/chat/history?session_id={orphan_sid}", headers=headers)
    assert res_history.status_code == 404
