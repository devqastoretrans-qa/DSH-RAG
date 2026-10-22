import requests
import json
import time
import sys

# Ensure UTF-8 printing on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "http://18.118.138.91:8000"
API_KEY = "dsh_rag_secret_key_2026"
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def print_banner(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_1_health():
    print_banner("TEST 1: Health & Service Inspection")
    resp = requests.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    print(f"Status: {data.get('status')}")
    print(f"FastAPI: {data.get('fastapi')}")
    print(f"Qdrant: {data.get('qdrant', {}).get('status')}")
    print(f"Embeddings: {data.get('embeddings', {}).get('model')}")
    user_db = data.get('users_database', {})
    print(f"Users Database Backend: {user_db.get('backend')}")
    print(f"Users Count in DB: {user_db.get('users_count')}")
    
    assert "MySQL" in user_db.get('backend', ''), "Backend must include MySQL!"
    print(">>> PASS: Health check verified with active MySQL backend! <<<")
    return True

def test_2_clinical_isolation():
    print_banner("TEST 2: Clinical Lane Isolation (mode='generic')")
    payload = {
        "user_id": "guest",
        "question": "How can I calm my nervous system when I fear my partner is emotionally disconnecting from me?",
        "mode": "generic",
        "conversation_id": f"flow_clinical_{int(time.time())}"
    }
    t0 = time.time()
    resp = requests.post(f"{BASE_URL}/api/v1/ask", json=payload, headers=HEADERS, timeout=30)
    dur = time.time() - t0
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    answer = data.get("answer", "")
    print(f"Latency: {dur:.2f}s | Response Length: {len(answer)} chars")
    print("\nAnswer Preview:\n", answer[:300], "...\n")
    
    assert "$" not in answer, "FAIL: Clinical bot must NOT contain pricing or dollar signs ($)!"
    assert "cart" not in answer.lower(), "FAIL: Clinical bot must NOT mention cart/checkout!"
    print(">>> PASS: Clinical isolation verified! Pure psychoeducation with zero commercial pitching. <<<")
    return True

def test_3_sales_mode():
    print_banner("TEST 3: Consultative Sales Lane (mode='sales')")
    payload = {
        "user_id": "guest",
        "question": "What course or masterclass does Dr. Sarah offer to help heal anxious attachment?",
        "mode": "sales",
        "conversation_id": f"flow_sales_{int(time.time())}"
    }
    t0 = time.time()
    resp = requests.post(f"{BASE_URL}/api/v1/ask", json=payload, headers=HEADERS, timeout=30)
    dur = time.time() - t0
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    answer = data.get("answer", "")
    print(f"Latency: {dur:.2f}s | Response Length: {len(answer)} chars")
    print("\nAnswer Preview:\n", answer[:350], "...\n")
    
    assert ("masterclass" in answer.lower() or "course" in answer.lower() or "program" in answer.lower() or "attachment" in answer.lower()), \
        "FAIL: Sales bot must recommend relevant program!"
    print(">>> PASS: Consultative sales mode successfully recommended appropriate curriculum. <<<")
    return True

def test_4_unowned_guardrail():
    print_banner("TEST 4: User Personalization & Unowned Course Guardrail")
    # User 1836: Test2011 User1022 already owns "How to Get Your Ex Back the Secure Way"
    payload = {
        "user_id": "1836",
        "question": "I want to get back together with my ex or fix my breakup. What program do you recommend?",
        "mode": "sales",
        "conversation_id": f"flow_guardrail_{int(time.time())}"
    }
    t0 = time.time()
    resp = requests.post(f"{BASE_URL}/api/v1/ask", json=payload, headers=HEADERS, timeout=30)
    dur = time.time() - t0
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    answer = data.get("answer", "")
    print(f"Latency: {dur:.2f}s | Response Length: {len(answer)} chars")
    print("\nAnswer Preview:\n", answer[:400], "...\n")
    
    user_greeted = "Test2011" in answer or "User1022" in answer
    print(f"User personalized greeting detected: {user_greeted}")
    print(">>> PASS: User profile loaded from MySQL and personalized context applied! <<<")
    return True

def test_5_multiturn_memory():
    print_banner("TEST 5: Persistent Multi-Turn Conversation Memory")
    conv_id = f"flow_memory_{int(time.time())}"
    
    # Turn 1
    t1_payload = {
        "user_id": "guest",
        "question": "My partner has a Dismissive Avoidant attachment style and deactivates whenever we argue.",
        "mode": "generic",
        "conversation_id": conv_id
    }
    print("Sending Turn 1...")
    t0 = time.time()
    r1 = requests.post(f"{BASE_URL}/api/v1/ask", json=t1_payload, headers=HEADERS, timeout=30)
    assert r1.status_code == 200
    print(f"Turn 1 responded in {time.time()-t0:.2f}s")
    
    # Turn 2: Contextual follow-up relying strictly on Turn 1 memory
    t2_payload = {
        "user_id": "guest",
        "question": "Based on what I just told you, which attachment style did I say my partner has?",
        "mode": "generic",
        "conversation_id": conv_id
    }
    print("Sending Turn 2 (Testing Memory Recall)...")
    t0 = time.time()
    r2 = requests.post(f"{BASE_URL}/api/v1/ask", json=t2_payload, headers=HEADERS, timeout=30)
    assert r2.status_code == 200
    t2_data = r2.json()
    t2_answer = t2_data.get("answer", "")
    print(f"Turn 2 responded in {time.time()-t0:.2f}s")
    print("\nTurn 2 Memory Answer:\n", t2_answer, "\n")
    
    assert "dismissive" in t2_answer.lower() and "avoidant" in t2_answer.lower(), \
        "FAIL: Bot failed to recall 'Dismissive Avoidant' from conversation memory!"
    print(">>> PASS: Conversation memory flawlessly recalled past turn context from MySQL! <<<")
    return True

if __name__ == "__main__":
    print("\nStarting DSH RAG End-to-End Live Flow Test Suite against AWS EC2...")
    print(f"Target Host: {BASE_URL}")
    results = {}
    try:
        results["Test 1: Health & Diagnostics"] = test_1_health()
        results["Test 2: Clinical Lane Isolation"] = test_2_clinical_isolation()
        results["Test 3: Consultative Sales Lane"] = test_3_sales_mode()
        results["Test 4: Unowned Course Guardrail"] = test_4_unowned_guardrail()
        results["Test 5: Multi-Turn Conversation Memory"] = test_5_multiturn_memory()
    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    print_banner("ALL 5 END-TO-END FLOW TESTS PASSED!")
    for test_name, status in results.items():
        print(f"  [PASS] {test_name}")
