import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app import app
from src.session_auth import create_session_token

client = TestClient(app)

def get_auth_headers(user_id: str = "test_student"):
    token = create_session_token(user_id=user_id)["token"]
    return {"Authorization": f"Bearer {token}"}

def test_agent_routes_exist():
    """Verify all 4 dedicated agent endpoints are registered in FastAPI routes."""
    routes = [r.path for r in app.routes]
    assert "/api/v1/agents/platform" in routes
    assert "/api/v1/agents/owner" in routes
    assert "/api/v1/agents/learning" in routes
    assert "/api/v1/agents/coaching" in routes

def test_empty_message_returns_400():
    """Verify missing message returns HTTP 400 error."""
    headers = get_auth_headers()
    for endpoint in [
        "/api/v1/agents/platform",
        "/api/v1/agents/owner",
        "/api/v1/agents/learning",
        "/api/v1/agents/coaching"
    ]:
        res = client.post(endpoint, json={"message": "   "}, headers=headers)
        assert res.status_code == 400
        data = res.json()
        assert data["success"] is False
        assert "message or question is required" in data["error"]

@patch("app.execute_rag_pipeline")
def test_platform_agent_response(mock_rag):
    """Verify Platform Agent returns expected schema and mode."""
    headers = get_auth_headers()
    mock_rag.return_value = {
        "user_id": "test_student",
        "question": "Where can I reset my password?",
        "answer": "To reset your password, click on 'Forgot Password' on the login screen.",
        "answer_html": "<p>To reset your password...</p>",
        "sources": [],
        "ai_model": "test-model",
        "duration_ms": 12.5
    }
    res = client.post("/api/v1/agents/platform", json={"message": "Where can I reset my password?"}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["agent"] == "platform"
    assert "Platform Agent" in data["agent_name"]
    assert "reset your password" in data["answer"]

@patch("app.execute_rag_pipeline")
def test_owner_agent_response(mock_rag):
    """Verify Owner Agent returns expected schema and mode."""
    headers = get_auth_headers()
    mock_rag.return_value = {
        "user_id": "test_student",
        "question": "Why do avoidants pull away?",
        "answer": "In my clinical practice, avoidants pull away when subconscious vulnerability triggers fear.",
        "answer_html": "<p>In my clinical practice...</p>",
        "sources": [],
        "ai_model": "test-model",
        "duration_ms": 15.0
    }
    res = client.post("/api/v1/agents/owner", json={"message": "Why do avoidants pull away?"}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["agent"] == "owner"
    assert "Owner Agent" in data["agent_name"]

@patch("app.execute_rag_pipeline")
def test_learning_agent_response(mock_rag):
    """Verify Learning Agent returns expected schema and mode."""
    headers = get_auth_headers("student_1")
    mock_rag.return_value = {
        "user_id": "student_1",
        "question": "Explain anxious attachment triggers in Module 3.",
        "answer": "Think about what happens to the nervous system when connection feels uncertain.",
        "sources": [],
        "ai_model": "test-model",
        "duration_ms": 14.0
    }
    res = client.post("/api/v1/agents/learning", json={"message": "Explain anxious attachment triggers in Module 3."}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["agent"] == "learning"
    assert "Learning Agent" in data["agent_name"]

@patch("app.execute_rag_pipeline")
def test_coaching_agent_response(mock_rag):
    """Verify Coaching Agent returns expected schema and mode."""
    headers = get_auth_headers()
    mock_rag.return_value = {
        "user_id": "test_student",
        "question": "I had a fight with my husband.",
        "answer": "Let's pause and unpack this. What specific feeling came up right before the reaction?",
        "sources": [],
        "ai_model": "test-model",
        "duration_ms": 18.0
    }
    res = client.post("/api/v1/agents/coaching", json={"message": "I had a fight with my husband."}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["agent"] == "coaching"
    assert "Coaching Agent" in data["agent_name"]

