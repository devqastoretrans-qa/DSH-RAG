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


