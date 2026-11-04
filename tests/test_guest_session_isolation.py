import pytest
from src.conversation_memory import get_conversation_memory


def test_session_key_never_returns_static_guest_default_conv():
    memory = get_conversation_memory()
    
    # Neither None, empty string, nor 'default_conv' should collapse into guest:default_conv
    key1 = memory._session_key("guest", None)
    key2 = memory._session_key("guest", None)
    key_empty = memory._session_key("guest", "")
    key_default = memory._session_key("guest", "default_conv")

    assert key1 != "guest:default_conv"
    assert key2 != "guest:default_conv"
    assert key_empty != "guest:default_conv"
    assert key_default != "guest:default_conv"

    # Ephemeral guest keys must be unique per invocation when no session ID exists
    assert key1 != key2


def test_guest_without_session_id_has_zero_chat_history():
    memory = get_conversation_memory()
    
    # Clean memory first
    memory.clear()

    # Guest A records a private turn without session_id
    memory.record_turn(
        user_id="guest",
        conversation_id=None,
        user_query="My husband is dismissive avoidant and we had a fight.",
        assistant_answer="I understand dealing with a dismissive avoidant partner can feel lonely.",
        retrieved_chunks=[]
    )

    # Guest B connects without a session_id
    history_b = memory.get_chat_history(user_id="guest", conversation_id=None)
    assert history_b == [], f"Expected empty history for Guest B, got {history_b}"

    # Guest B attempts a follow-up query
    query_b, can_reuse, cached = memory.resolve_follow_up(
        user_id="guest",
        conversation_id=None,
        query="tell me more about it"
    )
    # Must NOT stitch Guest A's topic
    assert query_b == "tell me more about it"
    assert can_reuse is False
    assert cached is None


def test_explicit_guest_sessions_are_strictly_isolated():
    memory = get_conversation_memory()
    memory.clear()

    session_a = "sess_guest_aaa111"
    session_b = "sess_guest_bbb222"

    # User A in session A
    memory.record_turn(
        user_id="guest",
        conversation_id=session_a,
        user_query="How do I practice the SOLACE framework?",
        assistant_answer="The SOLACE framework stands for Stop, Observe, Label...",
        retrieved_chunks=[{"text": "SOLACE steps..."}]
    )

    # User B in session B
    history_b = memory.get_chat_history(user_id="guest", conversation_id=session_b)
    assert len(history_b) == 0, "Session B must have zero history from Session A"

    # User A in session A can view their own history
    history_a = memory.get_chat_history(user_id="guest", conversation_id=session_a)
    assert len(history_a) == 2  # 1 user + 1 assistant turn
    assert "SOLACE" in history_a[0]["content"]

    # User A follow-up works within session A
    rewritten, can_reuse, _ = memory.resolve_follow_up(
        user_id="guest",
        conversation_id=session_a,
        query="tell me more simply"
    )
    assert "solace" in rewritten.lower()


def test_rag_service_auto_assigns_guest_session_id():
    from src.rag_service import execute_rag_pipeline
    
    # Call without conversation_id
    res1 = execute_rag_pipeline(
        query="Hello, what is attachment theory?",
        user_id="guest",
        generate_answer=False
    )
    assert res1["conversation_id"] is not None
    assert res1["conversation_id"].startswith("sess_")
    assert res1["conversation_id"] != "default_conv"

    # Second call without conversation_id gets distinct session
    res2 = execute_rag_pipeline(
        query="What packages are available?",
        user_id="guest",
        generate_answer=False
    )
    assert res2["conversation_id"] is not None
    assert res2["conversation_id"] != res1["conversation_id"]

