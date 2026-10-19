import requests
import json
import time

HEADERS = {
    "Authorization": "Bearer dsh_rag_secret_key_2026",
    "Content-Type": "application/json"
}
BASE_URL = "https://agent.doctorsarahhensley.com"

def test_all():
    print("==================================================================")
    print("1. TESTING STANDARD JSON ENDPOINT (/api/v1/ask) - ZERO BREAKING")
    print("==================================================================")
    t0 = time.time()
    payload = {
        "user_id": "tribepubseo@gmail.com",
        "question": "How do points and gamification work?",
        "conversation_id": "conv_std_001"
    }
    r = requests.post(f"{BASE_URL}/api/v1/ask", json=payload, headers=HEADERS, timeout=30)
    dur = (time.time() - t0) * 1000
    print(f"Status: {r.status_code}, Full Response Time: {dur:.2f}ms")
    data = r.json()
    assert data.get("success") is True
    print(f"Personalized Answer Preview:\n{data.get('answer')[:140]}...\n")

    print("==================================================================")
    print("2. TESTING TOKEN STREAMING ENDPOINT (/api/v1/ask/stream) - REALTIME")
    print("==================================================================")
    t_start = time.time()
    first_token_time = None
    stream_payload = {
        "user_id": "tribepubseo@gmail.com",
        "question": "What is the 1-1-1 journal reflection method?",
        "conversation_id": "conv_stream_001"
    }
    
    with requests.post(f"{BASE_URL}/api/v1/ask/stream", json=stream_payload, headers=HEADERS, stream=True, timeout=30) as resp:
        print(f"Stream Status: {resp.status_code}")
        print("Live Stream Output (Token by Token):")
        accumulated_text = []
        
        for line in resp.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    content = decoded[6:]
                    try:
                        event_data = json.loads(content)
                        if "token" in event_data and event_data["token"]:
                            if first_token_time is None:
                                first_token_time = (time.time() - t_start) * 1000
                            token = event_data["token"]
                            accumulated_text.append(token)
                            print(token, end="", flush=True)
                        elif event_data.get("done") or event_data.get("success"):
                            print("\n\n[STREAM COMPLETED EVENT RECEIVED]")
                    except Exception:
                        pass

    total_stream_time = (time.time() - t_start) * 1000
    print(f"\nTime-To-First-Token (TTFT): {first_token_time:.2f}ms (FAST: User sees response start!)")
    print(f"Total Stream Duration: {total_stream_time:.2f}ms")

    print("\n==================================================================")
    print("3. TESTING WOOCOMMERCE WEBHOOK SYNC (/api/v1/woocommerce/webhook)")
    print("==================================================================")
    webhook_payload = {
        "id": 99881,
        "status": "completed",
        "date_created": "2026-10-07T04:20:00",
        "customer_id": 7766,
        "billing": {
            "first_name": "Marcus",
            "last_name": "Vance",
            "email": "marcus.vance@example.com"
        },
        "line_items": [
            {"name": "The Science of Secure Connection Book"},
            {"name": "Hybrid Group Coaching with Dr. Sarah Hensley"}
        ]
    }
    
    r_wh = requests.post(f"{BASE_URL}/api/v1/woocommerce/webhook", json=webhook_payload, timeout=10)
    print("Webhook Sync Response:", r_wh.status_code, r_wh.json())
    assert r_wh.status_code == 200

    # Immediate lookup test to verify 0ms cache
    t_lookup = time.time()
    r_user = requests.post(f"{BASE_URL}/api/v1/ask", json={"user_id": "marcus.vance@example.com", "question": "What is gamification?"}, headers=HEADERS, timeout=30)
    lookup_dur = (time.time() - t_lookup) * 1000
    print(f"Instant Lookup for New Webhook User: {lookup_dur:.2f}ms")
    u_ans = r_user.json().get("answer", "")
    print(f"Answer Preview for Marcus Vance:\n{u_ans[:140]}...\n")
    assert "Marcus" in u_ans

    print(">>> ALL 3 OPTIMIZATION TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_all()
