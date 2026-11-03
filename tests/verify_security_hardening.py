import os
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = os.getenv("DSH_BASE_URL", "https://agent.doctorsarahhensley.com").rstrip("/")
ADMIN_KEY = os.getenv("RAG_API_KEY", os.getenv("ADMIN_API_KEY", "dsh_rag_secret_key_2026"))

print("==================================================")
print("🛡️ RUNNING LIVE PRODUCTION SECURITY HARDENING VERIFICATION")
print("==================================================")

# Test 1: Sanitized /health
print("\n[Test 1] Testing /health sanitization...")
r_health = requests.get(f"{BASE_URL}/health", timeout=10)
print(f"Status Code: {r_health.status_code}")
health_data = r_health.json()
print("Health Data:", json.dumps(health_data, indent=2))
assert r_health.status_code == 200, "Health endpoint must return 200"
assert "127.0.0.1" not in json.dumps(health_data), "Internal IP 127.0.0.1 must NOT be leaked in /health"
assert "service_account.json" not in json.dumps(health_data), "Service account file path must NOT be leaked"
print("✅ Test 1 PASSED: /health is cleanly sanitized.")

# Test 2: Unauthenticated /documents access
print("\n[Test 2] Testing /documents access control...")
r_docs_unauth = requests.get(f"{BASE_URL}/documents", timeout=10)
print(f"Unauthenticated Status Code: {r_docs_unauth.status_code} (Expected 401)")
assert r_docs_unauth.status_code == 401, "Unauthenticated access to /documents must be blocked with 401"

r_docs_auth = requests.get(f"{BASE_URL}/documents", headers={"X-API-Key": ADMIN_KEY}, timeout=10)
print(f"Authenticated with API Key Status Code: {r_docs_auth.status_code} (Expected 200)")
assert r_docs_auth.status_code == 200, "Authenticated access to /documents must succeed with 200"
print("✅ Test 2 PASSED: /documents is strictly protected.")

# Test 3: Unauthenticated /drive/status access
print("\n[Test 3] Testing /drive/status access control...")
r_drive_unauth = requests.get(f"{BASE_URL}/drive/status", timeout=10)
print(f"Unauthenticated Status Code: {r_drive_unauth.status_code} (Expected 401)")
assert r_drive_unauth.status_code == 401, "Unauthenticated access to /drive/status must be blocked with 401"

r_drive_auth = requests.get(f"{BASE_URL}/drive/status", headers={"X-API-Key": ADMIN_KEY}, timeout=10)
print(f"Authenticated with API Key Status Code: {r_drive_auth.status_code} (Expected 200)")
assert r_drive_auth.status_code == 200, "Authenticated access to /drive/status must succeed with 200"
print("✅ Test 3 PASSED: /drive/status is strictly protected.")

# Test 4: Public Chat IDOR / User Impersonation Prevention
print("\n[Test 4] Testing User ID Impersonation on public /chat...")
unauth_payload = {
    "session_id": "test_security_idor_probe_001",
    "message": "What is deactivation?",
    "user_id": "sarah@thelovedoc.com",  # Attempting to impersonate Sarah without a session token or API key
    "mode": "generic"
}
# Sending without X-API-Key or Bearer token (pure public guest caller)
r_chat = requests.post(f"{BASE_URL}/chat", json=unauth_payload, timeout=25)
print(f"Public Chat Status Code: {r_chat.status_code}")
chat_data = r_chat.json()
returned_user_id = chat_data.get("user_id")
print(f"Claimed user_id in payload: 'sarah@thelovedoc.com'")
print(f"Enforced user_id by server: '{returned_user_id}' (Expected 'guest')")
assert returned_user_id == "guest", f"Server must force unauthenticated callers to 'guest', got '{returned_user_id}'"
print("✅ Test 4 PASSED: IDOR / User ID Impersonation is completely prevented!")

print("\n==================================================")
print("🎉 ALL PRODUCTION SECURITY HARDENING TESTS PASSED!")
print("==================================================")
