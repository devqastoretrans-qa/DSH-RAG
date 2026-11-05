import os
import json
import hmac
import hashlib
import base64
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import app as app_module
from app import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# =========================================================================
# 1. DEF-01: WOOCOMMERCE WEBHOOK HMAC VERIFICATION (FAIL-CLOSED)
# =========================================================================

def test_wc_webhook_missing_secret_returns_500_fail_closed(client, monkeypatch):
    """DEF-01: Unset WC_WEBHOOK_SECRET must fail-closed with HTTP 500, refusing unauthenticated processing."""
    monkeypatch.delenv("WC_WEBHOOK_SECRET", raising=False)
    
    payload = json.dumps({"id": 101, "status": "completed"}).encode("utf-8")
    response = client.post("/api/webhooks/woocommerce", content=payload, headers={"Content-Type": "application/json"})
    
    assert response.status_code == 500
    assert "Server webhook secret is not configured" in response.text


def test_wc_webhook_missing_signature_returns_401(client, monkeypatch):
    """DEF-01: Configured secret with missing x-wc-webhook-signature header must return 401."""
    secret = "test_webhook_secret_abc123"
    monkeypatch.setenv("WC_WEBHOOK_SECRET", secret)
    
    payload = json.dumps({"id": 102, "status": "completed"}).encode("utf-8")
    response = client.post("/api/webhooks/woocommerce", content=payload, headers={"Content-Type": "application/json"})
    
    assert response.status_code == 401
    assert "Missing webhook signature header" in response.text


def test_wc_webhook_invalid_signature_returns_401(client, monkeypatch):
    """DEF-01: Invalid or tampered signature must return 401 Unauthorized."""
    secret = "test_webhook_secret_abc123"
    monkeypatch.setenv("WC_WEBHOOK_SECRET", secret)
    
    payload = json.dumps({"id": 103, "status": "completed"}).encode("utf-8")
    bad_signature = "invalid_base64_sig=="
    headers = {
        "Content-Type": "application/json",
        "x-wc-webhook-signature": bad_signature
    }
    response = client.post("/api/webhooks/woocommerce", content=payload, headers=headers)
    
    assert response.status_code == 401
    assert "Invalid webhook signature" in response.text


def test_wc_webhook_valid_signature_ping_returns_200(client, monkeypatch):
    """DEF-01: Valid HMAC signature on WordPress ping event succeeds with 200."""
    secret = "test_webhook_secret_abc123"
    monkeypatch.setenv("WC_WEBHOOK_SECRET", secret)
    
    payload = json.dumps({"webhook_id": 99}).encode("utf-8")
    valid_sig = base64.b64encode(hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()).decode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-wc-webhook-signature": valid_sig,
        "x-wc-webhook-topic": "webhook.ping"
    }
    response = client.post("/api/webhooks/woocommerce", content=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Webhook ping verified successfully"


def test_wc_webhook_valid_signature_order_event_returns_200(client, monkeypatch):
    """DEF-01: Valid HMAC signature on order event successfully processes and syncs."""
    secret = "test_webhook_secret_abc123"
    monkeypatch.setenv("WC_WEBHOOK_SECRET", secret)
    
    order_data = {
        "id": 104,
        "status": "completed",
        "customer_id": "cust_104",
        "billing": {"first_name": "Verified", "last_name": "Buyer", "email": "buyer104@example.com"},
        "line_items": [{"name": "The Secure Relationship Bundle"}]
    }
    payload = json.dumps(order_data).encode("utf-8")
    valid_sig = base64.b64encode(hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()).decode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-wc-webhook-signature": valid_sig,
        "x-wc-webhook-topic": "order.created"
    }
    response = client.post("/api/webhooks/woocommerce", content=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["event"] == "order.updated"
    assert data["order_id"] == 104


# =========================================================================
# 2. DEF-03: GOOGLE DRIVE WEBHOOK CHANNEL TOKEN & ATOMIC LOCK
# =========================================================================

def test_drive_webhook_missing_token_returns_401(client, monkeypatch):
    """DEF-03: When DRIVE_WEBHOOK_TOKEN is configured, missing header must return 401."""
    monkeypatch.setenv("DRIVE_WEBHOOK_TOKEN", "secret_drive_token_xyz")
    
    headers = {"x-goog-resource-state": "change", "x-goog-channel-id": "chan_1"}
    response = client.post("/drive/webhook", headers=headers)
    
    assert response.status_code == 401
    assert "Missing X-Goog-Channel-Token header" in response.text


def test_drive_webhook_invalid_token_returns_401(client, monkeypatch):
    """DEF-03: When DRIVE_WEBHOOK_TOKEN is configured, wrong token must return 401."""
    monkeypatch.setenv("DRIVE_WEBHOOK_TOKEN", "secret_drive_token_xyz")
    
    headers = {
        "x-goog-resource-state": "change",
        "x-goog-channel-id": "chan_1",
        "x-goog-channel-token": "wrong_attacker_token"
    }
    response = client.post("/drive/webhook", headers=headers)
    
    assert response.status_code == 401
    assert "Invalid channel token" in response.text


def test_drive_webhook_sync_handshake_returns_200(client, monkeypatch):
    """DEF-03: Valid token on initial Google sync handshake acknowledges without triggering scan."""
    token = "secret_drive_token_xyz"
    monkeypatch.setenv("DRIVE_WEBHOOK_TOKEN", token)
    
    headers = {
        "x-goog-resource-state": "sync",
        "x-goog-channel-id": "chan_sync",
        "x-goog-channel-token": token
    }
    response = client.post("/drive/webhook", headers=headers)
    
    assert response.status_code == 200
    assert response.json()["status"] == "sync_acknowledged"


def test_drive_webhook_atomic_lock_debounces_concurrent_scans(client, monkeypatch):
    """DEF-03: When an ingestion scan is already active, incoming notifications are debounced."""
    token = "secret_drive_token_xyz"
    monkeypatch.setenv("DRIVE_WEBHOOK_TOKEN", token)
    
    headers = {
        "x-goog-resource-state": "update",
        "x-goog-channel-id": "chan_update",
        "x-goog-message-number": "42",
        "x-goog-channel-token": token
    }

    # Simulate scan in progress by holding the atomic lock
    app_module._drive_scan_lock.acquire(blocking=True)
    try:
        response = client.post("/drive/webhook", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scan_already_in_progress"
        assert "debounced" in data["message"].lower()
    finally:
        app_module._drive_scan_lock.release()

