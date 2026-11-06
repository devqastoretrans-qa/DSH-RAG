import pytest
import time
from fastapi.testclient import TestClient
from app import app
from src.conversation_memory import get_conversation_memory

client = TestClient(app)

def test_chat_sessions_endpoints():
    conv_memory = get_conversation_memory()
    test_sid = f"test_hist_{int(time.time())}"
    
    # 1. Record a turn to create a session
    conv_memory.record_turn(
        user_id="test_user_hist",
        conversation_id=test_sid,
        user_query="What is the science of secure attachment?",
        assistant_answer="Secure attachment is characterized by emotional safety and trust.",
        retrieved_chunks=[],
        mode="generic"
    )

    # 2. Test GET /api/chat/sessions
    res = client.get("/api/chat/sessions")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert any(s["session_id"] == test_sid for s in data["sessions"])
    
    # Check title derivation
    matching_session = next(s for s in data["sessions"] if s["session_id"] == test_sid)
    assert "science of secure attachment" in matching_session["title"].lower()

    # 3. Test GET /api/chat/history
    res_hist = client.get(f"/api/chat/history?session_id={test_sid}&user_id=test_user_hist")
    assert res_hist.status_code == 200
    hist_data = res_hist.json()
    assert len(hist_data["turns"]) >= 2
    assert hist_data["turns"][0]["content"] == "What is the science of secure attachment?"

    # 4. Test DELETE /api/chat/sessions/{session_id}
    res_del = client.delete(f"/api/chat/sessions/{test_sid}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # 5. Verify it's gone from /api/chat/sessions
    res_after = client.get("/api/chat/sessions")
    assert not any(s["session_id"] == test_sid for s in res_after.json()["sessions"])

