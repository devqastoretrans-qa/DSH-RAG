import pytest
from unittest.mock import MagicMock, patch
from src.config import resolve_target_collection, get_collection_config, CLINICAL_COLLECTIONS


def test_resolve_target_collection_by_folder_name():
    # Exact folder names
    res_journals = resolve_target_collection(folder_name="Journals")
    assert res_journals["collection_name"] == "clinical_knowledge_journals"
    assert res_journals["collection_key"] == "journals"
    assert res_journals["category"] == "clinical"

    res_tools = resolve_target_collection(folder_name="Tools")
    assert res_tools["collection_name"] == "clinical_knowledge_tools"
    assert res_tools["collection_key"] == "tools"
    assert res_tools["category"] == "clinical"

    res_reflections = resolve_target_collection(folder_name="Reflections")
    assert res_reflections["collection_name"] == "clinical_knowledge_reflections"
    assert res_reflections["collection_key"] == "reflections"
    assert res_reflections["category"] == "clinical"

    res_other = resolve_target_collection(folder_name="Other")
    assert res_other["collection_name"] == "clinical_knowledge_other"
    assert res_other["collection_key"] == "other"
    assert res_other["category"] == "clinical"


def test_resolve_target_collection_by_folder_id():
    # Folder ID for Journals
    journals_id = CLINICAL_COLLECTIONS["journals"]["folder_id"]
    res = resolve_target_collection(folder_id=journals_id)
    assert res["collection_name"] == "clinical_knowledge_journals"
    assert res["collection_key"] == "journals"

    # Folder ID for Tools
    tools_id = CLINICAL_COLLECTIONS["tools"]["folder_id"]
    res_tools = resolve_target_collection(folder_id=tools_id)
    assert res_tools["collection_name"] == "clinical_knowledge_tools"
    assert res_tools["collection_key"] == "tools"


def test_resolve_target_collection_sales():
    res_sales = resolve_target_collection(category="sales")
    assert res_sales["collection_name"] == "documents"
    assert res_sales["category"] == "sales"

    res_pricing = resolve_target_collection(filename="Course_Pricing_Catalog.pdf")
    assert res_pricing["collection_name"] == "documents"
    assert res_pricing["category"] == "sales"


def test_resolve_target_collection_fuzzy_and_clinical_fallback():
    # Fuzzy match folder
    res_fuzzy = resolve_target_collection(folder_name="Attachment Exercises & Worksheets")
    assert res_fuzzy["collection_name"] == "clinical_knowledge_tools"

    # General clinical folder fallback goes to clinical_knowledge_other, NOT documents
    res_fallback = resolve_target_collection(category="clinical", folder_name="General Clinical Knowledge")
    assert res_fallback["collection_name"] == "clinical_knowledge_other"
    assert res_fallback["collection_key"] == "other"
    assert res_fallback["category"] == "clinical"


def test_qdrant_service_collection_override():
    from src.qdrant_service import QdrantService
    mock_client = MagicMock()
    
    col_mock = MagicMock()
    col_mock.name = "clinical_knowledge_journals"
    mock_client.get_collections.return_value.collections = [col_mock]
    
    count_mock = MagicMock()
    count_mock.count = 42
    mock_client.count.return_value = count_mock

    with patch.object(QdrantService, '_init_client', return_value=mock_client):
        qs = QdrantService()
        count = qs.count_document_vectors("doc_123", collection_name="clinical_knowledge_journals")
        assert count == 42
        assert mock_client.count.call_args[1]["collection_name"] == "clinical_knowledge_journals"

        # Test delete with collection_name override
        qs.delete_document_vectors("doc_123", collection_name="clinical_knowledge_journals")
        assert mock_client.delete.call_args[1]["collection_name"] == "clinical_knowledge_journals"


def test_reranker_preserves_chunks_beyond_600_characters():
    """DEF-05: Ensure CrossEncoder receives full chunk context rather than truncating at 600 chars."""
    from src.reranker import RerankerService
    long_text = (
        "[Document: Attachment Framework | Page 1]\n"
        + "Step 1: Notice your body activation and emotional flooding. " * 5  # ~300 chars
        + "Step 2: Core trigger identification and attachment defense deactivation. " * 5  # ~400 chars
        + "Step 3: This crucial clinical step is located well past the 600 character mark and contains the actual resolution."
    )
    assert len(long_text) > 800

    mock_model = MagicMock()
    mock_model.predict.return_value = [2.5]  # logit score

    with patch.object(RerankerService, '_model', mock_model):
        service = RerankerService(model_name="test-model")
        candidates = [{"id": "c1", "text": long_text, "score": 0.85}]

        results = service.rerank(query="how to resolve trigger", candidate_chunks=candidates, top_k=1)

        assert mock_model.predict.called
        pairs_arg = mock_model.predict.call_args[0][0]
        query_sent, text_sent = pairs_arg[0]

        assert query_sent == "how to resolve trigger"
        assert len(text_sent) > 600
        assert "crucial clinical step is located well past the 600 character mark" in text_sent
        assert len(results) == 1
        assert results[0]["rerank_score"] > 0.9


def test_reranker_respects_custom_max_chars_env_variable():
    """Verify RERANK_MAX_CHARS environment variable controls input slice cleanly."""
    import os
    from src.reranker import RerankerService
    custom_text = "A" * 1500
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0]

    with patch.object(RerankerService, '_model', mock_model):
        with patch.dict(os.environ, {"RERANK_MAX_CHARS": "1200"}):
            service = RerankerService(model_name="test-model")
            candidates = [{"id": "c2", "text": custom_text, "score": 0.7}]
            service.rerank(query="test query", candidate_chunks=candidates, top_k=1)

            pairs_arg = mock_model.predict.call_args[0][0]
            _, text_sent = pairs_arg[0]
            assert len(text_sent) == 1200


def test_relevance_gate_triggers_refusal_for_out_of_domain_query():
    """DEF-06: Ensure pre-LLM relevance gate intercepts off-topic queries with low confidence chunks."""
    from src.generator import OpenAIGeneratorService
    gen = OpenAIGeneratorService(api_key="mock-test-key")

    # Off-topic question with noisy, low-confidence retrieved chunks
    low_chunks = [
        {
            "id": "c1",
            "text": "General relationship notes without specific relevance.",
            "vector_score": 0.28,
            "rerank_score": 0.01,
            "score": 0.01
        }
    ]

    res = gen.generate_answer(
        query="Explain quantum computing qubits and superposition",
        retrieved_chunks=low_chunks,
        mode="generic"
    )

    assert res["out_of_domain"] is True
    assert "outside the scope of our verified knowledge base" in res["answer"]


def test_relevance_gate_bypasses_for_follow_up_and_chat_history():
    """DEF-06: Ensure follow-ups and active conversations do not trigger false refusal."""
    from src.generator import OpenAIGeneratorService
    gen = OpenAIGeneratorService(api_key="mock-test-key")

    low_chunks = [
        {
            "id": "c1",
            "text": "General relationship notes.",
            "vector_score": 0.28,
            "rerank_score": 0.01,
            "score": 0.01
        }
    ]

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Active follow-up response"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    with patch.object(OpenAIGeneratorService, 'client', mock_client):
        res = gen.generate_answer(
            query="tell me more about that",
            retrieved_chunks=low_chunks,
            mode="generic",
            is_follow_up=True
        )

        assert res.get("out_of_domain") is not True
        assert "Active follow-up response" in res["answer"]


def test_clinical_nervous_system_query_bypasses_false_refusal():
    """Ensure genuine clinical regulation/abandonment queries are not rejected as out-of-scope."""
    from src.generator import OpenAIGeneratorService
    gen = OpenAIGeneratorService(api_key="mock-test-key")

    low_chunks = [
        {
            "id": "c1",
            "document_name": "Fast Down Shift FAQ",
            "text": "Use the Fast Down Shift tool to calm nervous system activation and abandonment panic.",
            "vector_score": 0.15,
            "rerank_score": 0.01,
            "score": 0.01
        }
    ]

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Practice the Fast Down Shift protocol to regulate your nervous system."
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    with patch.object(OpenAIGeneratorService, 'client', mock_client):
        res = gen.generate_answer(
            query="How can I calm acute nervous system hyperarousal when I feel abandonment panic?",
            retrieved_chunks=low_chunks,
            mode="generic"
        )

        assert res.get("out_of_domain") is not True
        assert "Fast Down Shift" in res["answer"]


def test_wc_rest_api_sync_ignores_refunded_and_cancelled_orders():
    """DEF-07A: Verify _get_profile_from_woocommerce only grants ownership for active orders."""
    from src.user_db import UserDatabaseManager
    udb = UserDatabaseManager()
    udb.wp_url = "https://mock-wp.example.com"
    udb.wc_consumer_key = "ck_test"
    udb.wc_consumer_secret = "cs_test"

    mock_orders = [
        {
            "id": 101,
            "date_created": "2026-10-01T12:00:00",
            "status": "completed",
            "line_items": [{"name": "Healing Anxious Attachment Masterclass"}]
        },
        {
            "id": 102,
            "date_created": "2026-10-05T12:00:00",
            "status": "refunded",
            "line_items": [{"name": "Avoidant Attachment Masterclass"}]
        },
        {
            "id": 103,
            "date_created": "2026-10-08T12:00:00",
            "status": "cancelled",
            "line_items": [{"name": "Relationship Communication Toolkit"}]
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_orders

    with patch("requests.get", return_value=mock_resp):
        profile = udb._get_profile_from_woocommerce("student_123")

        assert profile is not None
        # Only completed order should be in courses_purchased / all_purchases
        assert "Healing Anxious Attachment Masterclass" in profile["courses_purchased"]
        assert "Avoidant Attachment Masterclass" not in profile["courses_purchased"]
        assert "Relationship Communication Toolkit" not in profile["courses_purchased"]
        assert "Avoidant Attachment Masterclass" not in profile["all_purchases"]

        # But all orders should be preserved in past_records for clinical context
        record_texts = " ".join(profile["past_records"])
        assert "Healing Anxious Attachment Masterclass" in record_texts
        assert "Avoidant Attachment Masterclass" in record_texts
        assert "Status: refunded" in record_texts


def test_wc_order_webhook_refund_revokes_active_purchase():
    """DEF-07B: Verify ingest_woocommerce_order_webhook revokes refunded items in real-time."""
    from src.user_db import UserDatabaseManager
    udb = UserDatabaseManager()
    test_uid = "test_user_refund_lifecycle"

    # Step 1: User purchases course and workbook via completed order
    order_create_payload = {
        "id": 9901,
        "date_created": "2026-11-01T10:00:00",
        "status": "completed",
        "customer_id": test_uid,
        "billing": {"first_name": "Test", "last_name": "User", "email": "test@example.com"},
        "line_items": [
            {"name": "Attachment Styles Masterclass"},
            {"name": "Science of Attachment Book"}
        ]
    }

    profile_after_purchase = udb.ingest_woocommerce_order_webhook(order_create_payload)
    assert "Attachment Styles Masterclass" in profile_after_purchase["courses_purchased"]
    assert "Science of Attachment Book" in profile_after_purchase["books_purchased"]
    assert len(profile_after_purchase["all_purchases"]) == 2

    # Step 2: Order is refunded in WooCommerce
    order_refund_payload = {
        "id": 9901,
        "date_created": "2026-11-01T10:00:00",
        "status": "refunded",
        "customer_id": test_uid,
        "billing": {"first_name": "Test", "last_name": "User", "email": "test@example.com"},
        "line_items": [
            {"name": "Attachment Styles Masterclass"}
        ]
    }

    profile_after_refund = udb.ingest_woocommerce_order_webhook(order_refund_payload)
    # Masterclass must be removed from active purchases
    assert "Attachment Styles Masterclass" not in profile_after_refund["courses_purchased"]
    assert "Attachment Styles Masterclass" not in profile_after_refund["all_purchases"]
    # The non-refunded book must remain owned
    assert "Science of Attachment Book" in profile_after_refund["books_purchased"]

    # History must record the refund event
    record_texts = " ".join(profile_after_refund["past_records"])
    assert "Refunded 'Attachment Styles Masterclass'" in record_texts or "Refund" in record_texts


from tests.test_wc_order_status_filtering import (
    test_completed_order_active_ownership,
    test_processing_order_active_ownership,
    test_status_case_insensitivity_and_whitespace,
    test_refunded_order_rejected_from_active_ownership,
    test_cancelled_and_failed_orders_blocked_from_ownership,
    test_inactive_orders_recorded_in_past_records_audit_trail,
    test_active_to_refunded_transition_revokes_db_and_cache,
    test_active_to_cancelled_transition_revokes_db_and_cache,
    test_refunded_course_is_unlocked_for_sales_recommendations,
    test_completed_course_remains_blocked_by_anti_collision_guardrail,
    test_missing_or_malformed_status_payload,
    test_duplicate_order_sync_idempotency
)

from tests.test_webhook_security import (
    test_wc_webhook_missing_secret_returns_500_fail_closed,
    test_wc_webhook_missing_signature_returns_401,
    test_wc_webhook_invalid_signature_returns_401,
    test_wc_webhook_valid_signature_ping_returns_200,
    test_wc_webhook_valid_signature_order_event_returns_200,
    test_drive_webhook_missing_token_returns_401,
    test_drive_webhook_invalid_token_returns_401,
    test_drive_webhook_sync_handshake_returns_200,
    test_drive_webhook_atomic_lock_debounces_concurrent_scans
)





