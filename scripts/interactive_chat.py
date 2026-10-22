import requests
import json
import time
import sys
import uuid

# Ensure UTF-8 printing on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "http://18.118.138.91:8000"
API_KEY = "dsh_rag_secret_key_2026"
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def print_banner():
    print("=" * 70)
    print("   Doctor Sarah Hensley AI — Interactive Terminal Chat Session")
    print("   Connected to: " + BASE_URL)
    print("=" * 70)

def main():
    print_banner()
    
    # 1. Choose User Profile
    print("\nSelect a User Profile for personalized testing:")
    print("  [1] guest                  (New visitor / no purchases)")
    print("  [2] 1836 (Test2011 User)   (Owns: 'How to Get Your Ex Back', 'Group Coaching')")
    print("  [3] 1832 (SEO TribePUB)    (Owns: 'How to Get Your Ex Back', 'Secure Connection')")
    print("  [4] Custom User ID")
    
    choice = input("\nEnter choice [1-4, default=1]: ").strip()
    if choice == "2":
        user_id = "1836"
    elif choice == "3":
        user_id = "1832"
    elif choice == "4":
        user_id = input("Enter custom user ID / email: ").strip() or "guest"
    else:
        user_id = "guest"
        
    # 2. Choose Mode
    print("\nSelect Bot Lane / Mode:")
    print("  [1] Clinical Mode ('generic') — Therapeutic psychoeducation (0 pitches)")
    print("  [2] Sales Mode    ('sales')   — Consultative recommendations & pricing ($97)")
    
    m_choice = input("Enter choice [1-2, default=1]: ").strip()
    mode = "sales" if m_choice == "2" else "generic"
    
    conversation_id = f"cli_{uuid.uuid4().hex[:8]}"
    
    print("\n" + "-" * 70)
    print(f"Session Active | User ID: {user_id} | Mode: {mode.upper()} | Conv ID: {conversation_id}")
    print("Type 'exit' to quit, 'mode' to switch modes, 'clear' to reset conversation.")
    print("-" * 70 + "\n")
    
    while True:
        try:
            prompt = input(f"[{user_id} @ {mode}] > ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q"):
                print("\nEnding session. Goodbye!")
                break
            if prompt.lower() == "mode":
                mode = "sales" if mode == "generic" else "generic"
                print(f"\n[Switched bot mode to: {mode.upper()}]\n")
                continue
            if prompt.lower() == "clear":
                conversation_id = f"cli_{uuid.uuid4().hex[:8]}"
                print(f"\n[Conversation reset. New Session ID: {conversation_id}]\n")
                continue
                
            payload = {
                "user_id": user_id,
                "question": prompt,
                "mode": mode,
                "conversation_id": conversation_id
            }
            
            t0 = time.time()
            resp = requests.post(f"{BASE_URL}/api/v1/ask", json=payload, headers=HEADERS, timeout=40)
            latency = time.time() - t0
            
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                cached = data.get("cached", False)
                
                print("\n" + "-" * 40)
                print(answer)
                print("-" * 40)
                print(f"[Latency: {latency:.2f}s | Cached: {cached} | Mode: {mode}]\n")
            else:
                print(f"\n[Error {resp.status_code}]: {resp.text}\n")
                
        except KeyboardInterrupt:
            print("\nSession interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n[Request Error]: {e}\n")

if __name__ == "__main__":
    main()
