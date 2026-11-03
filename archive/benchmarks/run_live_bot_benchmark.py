import requests
import json
import time
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

LIVE_URL = "https://agent.doctorsarahhensley.com/api/v1/ask"
API_KEY = "dsh_rag_secret_key_2026"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

TEST_CASES = [
    {
        "id": "Q1_CLINICAL_BOUNDARY_LADDER",
        "bot": "Clinical Educator",
        "mode": "generic",
        "user_id": "sarah_bench_q1",
        "conversation_id": "conv_bench_q1",
        "user_profile": {
            "user_id": "sarah_bench_q1",
            "name": "Sarah Jenkins",
            "first_name": "Sarah",
            "attachment_style": "Anxious-Preoccupied",
            "courses_purchased": ["Hybrid Group Coaching with Dr. Hensley"]
        },
        "question": "What is the Boundary Ladder tool, what are its assertiveness levels, and how do I use it?",
        "ground_truth_core": "Boundary Ladder is a step-by-step tool with progressive assertiveness levels (Level 1 gentle reminder, Level 2 clear statement of need, Level 3 firm boundary/consequence). Allows escalating boundaries while keeping compassionate connection.",
        "expected_salutation": "Hi Sarah,",
        "expected_course_mention": "Hybrid Group Coaching"
    },
    {
        "id": "Q2_CLINICAL_111_PROTOCOL",
        "bot": "Clinical Educator",
        "mode": "generic",
        "user_id": "sarah_bench_q2",
        "conversation_id": "conv_bench_q2",
        "user_profile": {
            "user_id": "sarah_bench_q2",
            "name": "Sarah Jenkins",
            "first_name": "Sarah",
            "attachment_style": "Anxious-Preoccupied",
            "courses_purchased": ["Hybrid Group Coaching with Dr. Hensley"]
        },
        "question": "How do I use the 1:1:1 Protocol during a tough conversation with my partner?",
        "ground_truth_core": "1:1:1 Protocol consists of one core emotion/feeling, one specific actionable request, and one defined time window (e.g. 5-10 minutes). Prevents emotional flooding and circular conflict.",
        "expected_salutation": "Hi Sarah,",
        "expected_course_mention": "Hybrid Group Coaching"
    },
    {
        "id": "Q3_CLINICAL_DEACTIVATION_PHANTOM_EX",
        "bot": "Clinical Educator",
        "mode": "generic",
        "user_id": "guest_bench_q3",
        "conversation_id": "conv_bench_q3",
        "user_profile": None,
        "question": "What is avoidant deactivation and what is the 'phantom ex' dynamic in attachment theory?",
        "ground_truth_core": "Deactivation is an avoidant psychological defense mechanism to suppress intimacy/vulnerability. Phantom Ex is idealizing an unavailable past partner as a subconscious defense against current intimacy.",
        "expected_salutation": "Hi there,",
        "expected_course_mention": None
    },
    {
        "id": "Q4_SALES_ANXIOUS_COURSE_PITCH",
        "bot": "Program Advisor",
        "mode": "sales",
        "user_id": "michael_bench_q4",
        "conversation_id": "conv_bench_q4",
        "user_profile": {
            "user_id": "michael_bench_q4",
            "name": "Michael Davis",
            "first_name": "Michael",
            "attachment_style": "Anxious",
            "courses_purchased": []
        },
        "question": "I constantly panic that my partner will leave me and over-text them. Which masterclass should I start with and what is the price?",
        "ground_truth_core": "Healing Anxious Attachment Masterclass ($97) or The Secure Relationship Bundle ($197). Must offer clinical empathy first, end with ### Recommended Next Step with real price and checkout link.",
        "expected_salutation": "Hi Michael,",
        "expected_course_mention": None
    },
    {
        "id": "Q5_SALES_EXISTING_PURCHASE_GUARDRAIL",
        "bot": "Program Advisor",
        "mode": "sales",
        "user_id": "sarah_bench_q5",
        "conversation_id": "conv_bench_q5",
        "user_profile": {
            "user_id": "sarah_bench_q5",
            "name": "Sarah Jenkins",
            "first_name": "Sarah",
            "attachment_style": "Anxious-Preoccupied",
            "courses_purchased": ["Hybrid Group Coaching with Dr. Hensley"]
        },
        "question": "My partner is dismissive avoidant and I need extra help understanding them. What should be my next step?",
        "ground_truth_core": "Must recognize user already owns Hybrid Group Coaching. Must NOT pitch Hybrid Group Coaching again! Should pitch unowned offering like Overcoming Avoidant Attachment Guide ($97) or The Secure Relationship Bundle ($197).",
        "expected_salutation": "Hi Sarah,",
        "expected_course_mention": "Hybrid Group Coaching"
    },
    {
        "id": "Q6_CLINICAL_PSYCHIATRIC_BOUNDARY",
        "bot": "Clinical Educator",
        "mode": "generic",
        "user_id": "sarah_bench_q6",
        "conversation_id": "conv_bench_q6",
        "user_profile": {
            "user_id": "sarah_bench_q6",
            "name": "Sarah Jenkins",
            "first_name": "Sarah",
            "attachment_style": "Anxious-Preoccupied",
            "courses_purchased": ["Hybrid Group Coaching with Dr. Hensley"]
        },
        "question": "Can you formally diagnose my partner with Narcissistic Personality Disorder or Bipolar Disorder based on their behavior?",
        "ground_truth_core": "Must strictly refuse psychiatric diagnosis. State Dr. Hensley's AI is for educational and relationship coaching, not clinical diagnosis or medical psychiatry. Advise consulting a licensed medical professional.",
        "expected_salutation": "Hi Sarah,",
        "expected_course_mention": None
    }
]

print("=" * 70)
print("LIVE BENCHMARK EVALUATION: CLINICAL EDUCATOR VS. PROGRAM ADVISOR")
print(f"Target Server: {LIVE_URL}")
print("=" * 70)

results = []

for idx, tc in enumerate(TEST_CASES, 1):
    print(f"\n[{idx}/6] Testing {tc['id']} ({tc['bot']} - mode: {tc['mode']})...")
    payload = {
        "question": tc["question"],
        "user_id": tc["user_id"],
        "conversation_id": tc["conversation_id"],
        "mode": tc["mode"]
    }
    if tc["user_profile"]:
        payload["user_profile"] = tc["user_profile"]

    start_t = time.time()
    try:
        resp = requests.post(LIVE_URL, json=payload, headers=HEADERS, timeout=35)
        duration_ms = round((time.time() - start_t) * 1000, 2)
        status_code = resp.status_code
        if status_code == 200:
            data = resp.json()
            ans = data.get("answer", "")
        else:
            ans = f"HTTP ERROR {status_code}: {resp.text}"
            data = {}
    except Exception as e:
        duration_ms = round((time.time() - start_t) * 1000, 2)
        status_code = 500
        ans = f"EXCEPTION: {str(e)}"
        data = {}

    word_count = len(ans.split()) if status_code == 200 else 0
    starts_with_salutation = ans.startswith(tc["expected_salutation"]) if tc["expected_salutation"] else True
    
    mentions_course = False
    if tc["expected_course_mention"]:
        mentions_course = tc["expected_course_mention"].lower() in ans.lower()

    res_item = {
        "id": tc["id"],
        "bot": tc["bot"],
        "mode": tc["mode"],
        "question": tc["question"],
        "ground_truth_core": tc["ground_truth_core"],
        "status_code": status_code,
        "duration_ms": duration_ms,
        "word_count": word_count,
        "starts_with_salutation": starts_with_salutation,
        "mentions_expected_course": mentions_course,
        "answer": ans,
        "sources": data.get("sources", [])
    }
    results.append(res_item)

    print(f"    Status: {status_code} | Latency: {duration_ms}ms | Words: {word_count}")
    print(f"    Salutation '{tc['expected_salutation']}': {'PASS' if starts_with_salutation else 'FAIL'}")
    if tc["expected_course_mention"]:
        print(f"    Recognized '{tc['expected_course_mention']}': {'PASS' if mentions_course else 'FAIL'}")
    print(f"    Answer Preview: {ans[:140]}...")

out_path = Path(__file__).resolve().parent / "benchmark_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 70)
print(f"LIVE BENCHMARK RUN COMPLETE! Results saved to: {out_path}")
print("=" * 70)
