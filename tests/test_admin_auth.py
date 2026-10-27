import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Ensure test key is configured in test environment
TEST_API_KEY = "test_secret_key_123"
os.environ["RAG_API_KEY"] = TEST_API_KEY

from app import app

@pytest.fixture
def client():
    # Use TestClient with raise_server_exceptions=False so HTTP 500 can be validated
    return TestClient(app, raise_server_exceptions=False)

def test_unauthenticated_upload(client):
    """1. Unauthenticated request to /upload -> 401"""
    files = {"file": ("test.txt", b"dummy content", "text/plain")}
    response = client.post("/upload", files=files)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

def test_unauthenticated_api_users(client):
    """2. Unauthenticated request to /api/users -> 401"""
    response = client.get("/api/users")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

def test_unauthenticated_api_user_detail(client):
    """Unauthenticated request to /api/users/{user_id} -> 401"""
    response = client.get("/api/users/1836")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

def test_unauthenticated_drive_sync(client):
    """3. Unauthenticated request to /drive/sync -> 401"""
    response = client.post("/drive/sync")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

def test_unauthenticated_cache_clear(client):
    """Unauthenticated request to /api/v1/cache/clear -> 401"""
    response = client.post("/api/v1/cache/clear")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

def test_authenticated_api_users_bearer(client, monkeypatch):
    """4. Authenticated request with Bearer token to /api/users -> 200"""
    monkeypatch.setenv("RAG_API_KEY", TEST_API_KEY)
    mock_db = MagicMock()
    mock_db.backend = "MockDatabase"
    mock_db.list_users.return_value = [{"user_id": "1836", "name": "Test User"}]
    with patch("app.get_user_db", return_value=mock_db):
        headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
        response = client.get("/api/users", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert data["users"][0]["user_id"] == "1836"

def test_authenticated_api_users_x_api_key(client, monkeypatch):
    """5. Authenticated request with X-API-Key header to /api/users -> 200"""
    monkeypatch.setenv("RAG_API_KEY", TEST_API_KEY)
    mock_db = MagicMock()
    mock_db.backend = "MockDatabase"
    mock_db.list_users.return_value = [{"user_id": "1836", "name": "Test User"}]
    with patch("app.get_user_db", return_value=mock_db):
        headers = {"X-API-Key": TEST_API_KEY}
        response = client.get("/api/users", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "users" in data

def test_request_with_wrong_key(client, monkeypatch):
    """6. Request with wrong key -> 401"""
    monkeypatch.setenv("RAG_API_KEY", TEST_API_KEY)
    headers = {"Authorization": "Bearer invalid_secret_key_999"}
    response = client.get("/api/users", headers=headers)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    body = response.json()
    assert body.get("error") == "Unauthorized" or body.get("detail") == "Unauthorized"

def test_unset_rag_api_key_returns_500(client, monkeypatch):
    """7. When RAG_API_KEY is unset/empty -> 500 Server misconfigured"""
    monkeypatch.delenv("RAG_API_KEY", raising=False)
    headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
    response = client.get("/api/users", headers=headers)
    assert response.status_code == 500
    assert "Server misconfigured" in response.text

def test_authenticated_cache_clear(client, monkeypatch):
    """Authenticated request to /api/v1/cache/clear -> 200"""
    monkeypatch.setenv("RAG_API_KEY", TEST_API_KEY)
    headers = {"X-API-Key": TEST_API_KEY}
    response = client.post("/api/v1/cache/clear", headers=headers)
    assert response.status_code == 200
    assert response.json().get("success") is True

def test_authenticated_drive_sync_mocked(client, monkeypatch):
    """Authenticated request to /drive/sync with mocked Drive monitor -> 200"""
    monkeypatch.setenv("RAG_API_KEY", TEST_API_KEY)
    mock_monitor = MagicMock()
    mock_monitor.scan_and_process.return_value = {"status": "success", "files_processed": 0}
    with patch("app.get_drive_monitor", return_value=mock_monitor):
        headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
        response = client.post("/drive/sync", headers=headers)
        assert response.status_code == 200
        assert response.json().get("status") == "success"

def test_authenticated_upload_mocked(client, monkeypatch):
    """Authenticated request to /upload with mocked ingestion -> 200"""
    monkeypatch.setenv("RAG_API_KEY", TEST_API_KEY)
    with patch("app.ingest_pdf_document", return_value={"status": "READY", "document_id": "doc123"}):
        headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
        files = {"file": ("test.pdf", b"%PDF-1.4 dummy", "application/pdf")}
        response = client.post("/upload", files=files, headers=headers)
        assert response.status_code == 200
        assert response.json().get("status") == "READY"

def test_public_routes_remain_unauthenticated(client):
    """UI root remains accessible without auth, while chat endpoints support both strict lockdown and migration modes (T9/T10)"""
    # 1. Strict lockdown mode (ENFORCE_CHAT_AUTH=true)
    os.environ["ENFORCE_CHAT_AUTH"] = "true"
    reset_resp_unauth = client.post("/chat/reset", json={"session_id": "test_session_123"})
    assert reset_resp_unauth.status_code == 401

    # 2. Reset with API key succeeds in strict mode
    reset_resp_auth = client.post(
        "/chat/reset",
        json={"session_id": "test_session_123"},
        headers={"Authorization": f"Bearer {TEST_API_KEY}"}
    )
    assert reset_resp_auth.status_code == 200

    # 3. Permissive migration mode (ENFORCE_CHAT_AUTH=false) keeps existing widget functional
    os.environ["ENFORCE_CHAT_AUTH"] = "false"
    reset_resp_perm = client.post("/chat/reset", json={"session_id": "test_session_123"})
    assert reset_resp_perm.status_code == 200

    # UI root remains accessible
    ui_resp = client.get("/")
    assert ui_resp.status_code == 200

def test_api_docs_hidden_in_production(client):
    """API docs (/docs and /openapi.json) return 404 in production mode"""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 404

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 404
