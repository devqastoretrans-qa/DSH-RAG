from unittest.mock import MagicMock, patch

from src.config import get_owner_collection_name, resolve_target_collection
from src.conversation_memory import ConversationMemoryManager
from src.drive_service import GoogleDriveService
from src.generator import OpenAIGeneratorService
from src.search import search_similar_chunks


def test_owner_collection_routing_and_isolation(monkeypatch):
    monkeypatch.delenv("QDRANT_OWNER_COLLECTION_NAME", raising=False)
    monkeypatch.setenv("GOOGLE_DRIVE_OWNER_FOLDER_ID", "drv_owner_123")

    assert get_owner_collection_name() == "owner_voice"

    # Explicit category routes to owner_voice
    res_cat = resolve_target_collection(category="owner", filename="bio.pdf")
    assert res_cat["collection_name"] == "owner_voice"
    assert res_cat["category"] == "owner"

    # Dedicated Drive Owner folder ID routes to owner_voice
    res_fid = resolve_target_collection(folder_id="drv_owner_123", filename="episode_01.txt")
    assert res_fid["collection_name"] == "owner_voice"
    assert res_fid["collection_key"] == "owner"

    # Folder and filename heuristics route to owner_voice
    res_folder = resolve_target_collection(folder_name="Founder Podcast", filename="notes.pdf")
    assert res_folder["collection_name"] == "owner_voice"
    assert res_folder["category"] == "owner"

    res_file = resolve_target_collection(filename="DSH_OWNER_VOICE_GUIDE.pdf")
    assert res_file["collection_name"] == "owner_voice"
    assert res_file["category"] == "owner"

    # Env override applies consistently
    monkeypatch.setenv("QDRANT_OWNER_COLLECTION_NAME", "custom_owner_docs")
    assert get_owner_collection_name() == "custom_owner_docs"
    res_override = resolve_target_collection(category="owner", filename="story.md")
    assert res_override["collection_name"] == "custom_owner_docs"

    # Platform and Clinical docs must NOT be hijacked into owner_voice
    res_plat = resolve_target_collection(filename="DSH_PLATFORM_USER_GUIDE.pdf")
    assert res_plat["category"] == "platform"
    res_clin = resolve_target_collection(folder_name="Tools", filename="boundary_ladder_faq.pdf")
    assert res_clin["category"] == "clinical"


def test_owner_search_merges_owner_voice_and_clinical_with_lane_isolation():
    called_collections = []

    def fake_search_similar(query_vector, top_k=10, collection_name=None, query_filter=None):
        called_collections.append(collection_name)
        if collection_name == "owner_voice":
            return [{
                "id": "own_1",
                "score": 0.89,
                "document_id": "doc_owner",
                "document_name": "DSH_OWNER_VOICE_GUIDE.pdf",
                "filename": "DSH_OWNER_VOICE_GUIDE.pdf",
                "text": "Dr. Sarah Hensley earned her Ph.D. in Experimental Psychology from the University of Kentucky.",
                "category": "owner",
                "status": "READY",
            }]
        if collection_name == "clinical_knowledge_tools":
            return [{
                "id": "clin_1",
                "score": 0.72,
                "document_id": "doc_clin",
                "document_name": "Attachment_Tool.pdf",
                "filename": "Attachment_Tool.pdf",
                "text": "Earned secure attachment grows through nervous system regulation and behavioral change.",
                "category": "clinical",
                "status": "READY",
            }, {
                "id": "leak_sales",
                "score": 0.99,
                "document_id": "doc_sales",
                "document_name": "Sales_Catalog.pdf",
                "filename": "Sales_Catalog.pdf",
                "text": "Course pricing $499",
                "category": "sales",
                "status": "READY",
            }]
        return []

    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1] * 384

    mock_qdrant = MagicMock()
    mock_qdrant.collection_name = "documents"
    mock_qdrant.search_similar.side_effect = fake_search_similar

    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = lambda query, candidate_chunks, top_k=5: [
        {**c, "rerank_score": 0.95 - idx * 0.1, "vector_score": c["score"]}
        for idx, c in enumerate(candidate_chunks[:top_k])
    ]

    with patch("src.search.get_embedding_service", return_value=mock_embedder), \
         patch("src.search.get_qdrant_service", return_value=mock_qdrant), \
         patch("src.search.get_reranker_service", return_value=mock_reranker):
        res = search_similar_chunks("Tell me about Dr. Sarah Hensley's PhD and attachment model", top_k=5, mode="owner")

    assert "owner_voice" in called_collections
    assert any(c.startswith("clinical_knowledge_") for c in called_collections)
    assert "documents" not in called_collections

    doc_names = [r["document_name"] for r in res["results"]]
    assert "DSH_OWNER_VOICE_GUIDE.pdf" in doc_names
    assert "Attachment_Tool.pdf" in doc_names
    assert "Sales_Catalog.pdf" not in doc_names

    # Generic mode must NOT query owner_voice
    called_collections.clear()
    with patch("src.search.get_embedding_service", return_value=mock_embedder), \
         patch("src.search.get_qdrant_service", return_value=mock_qdrant), \
         patch("src.search.get_reranker_service", return_value=mock_reranker):
        search_similar_chunks("What is anxious attachment?", top_k=5, mode="generic")
    assert "owner_voice" not in called_collections


def test_owner_search_resilient_when_owner_collection_missing():
    def fake_search_similar(query_vector, top_k=10, collection_name=None, query_filter=None):
        if collection_name == "owner_voice":
            raise RuntimeError("Collection owner_voice not found")
        if collection_name == "clinical_knowledge_other":
            return [{
                "id": "clin_2",
                "score": 0.85,
                "document_id": "doc_c2",
                "document_name": "Attachment_Foundations.pdf",
                "filename": "Attachment_Foundations.pdf",
                "text": "Dismissive avoidant deactivation can be soothed through nervous system safety.",
                "category": "clinical",
                "status": "READY",
            }]
        return []

    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.2] * 384
    mock_qdrant = MagicMock()
    mock_qdrant.search_similar.side_effect = fake_search_similar
    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = lambda query, candidate_chunks, top_k=5: [
        {**c, "rerank_score": 0.90, "vector_score": c["score"]} for c in candidate_chunks[:top_k]
    ]

    with patch("src.search.get_embedding_service", return_value=mock_embedder), \
         patch("src.search.get_qdrant_service", return_value=mock_qdrant), \
         patch("src.search.get_reranker_service", return_value=mock_reranker):
        res = search_similar_chunks("How does avoidant deactivation work?", top_k=5, mode="owner")

    assert len(res["results"]) == 1
    assert res["results"][0]["document_name"] == "Attachment_Foundations.pdf"


def test_owner_domain_matching_and_prompts():
    assert OpenAIGeneratorService._has_domain_match("Tell me about Dr. Sarah Hensley's podcast", "owner") is True
    assert OpenAIGeneratorService._has_domain_match("What is The Hensley Change Model?", "owner") is True
    assert OpenAIGeneratorService._has_domain_match("Why does avoidant attachment deactivate?", "owner") is True
    assert OpenAIGeneratorService._has_domain_match("Who is Virat Kohli?", "owner") is False

    prompt = OpenAIGeneratorService._build_system_prompt(mode="owner")
    assert "Dr. Sarah Hensley" in prompt
    assert "Founder, CEO, Social Psychologist" in prompt
    assert "Do NOT include bracketed citations" in prompt
    assert "EVERGREEN COHORT & SCHEDULING PHRASING" in prompt

    oos = OpenAIGeneratorService._build_out_of_scope_reply("Hello there!\n\n", mode="owner", reason="out_of_scope")
    assert "Digital Twin and Owner Agent" in oos
    assert "Hensley Change Model" in oos


def test_owner_multi_turn_follow_up_action_step_vs_off_topic():
    mem = ConversationMemoryManager()
    uid = "test_owner_followup_user"
    cid = "sess_owner_followup_test"
    mem.clear_session(session_id=cid, user_id=uid, mode="owner")

    mem.record_turn(
        user_id=uid,
        conversation_id=cid,
        user_query="Explain fearful avoidant push-pull dynamics in your own words",
        assistant_answer="Fearful avoidant attachment involves an inner conflict between craving closeness and fearing hurt.",
        retrieved_chunks=[{"document_name": "DSH_OWNER_VOICE_GUIDE.pdf", "text": "Hensley Change Model"}],
        mode="owner",
    )

    rewritten_step, _, _ = mem.resolve_follow_up(
        user_id=uid,
        conversation_id=cid,
        query="Give me one practical step I can practice tonight."
    )
    assert rewritten_step != "Give me one practical step I can practice tonight."
    assert "fearful avoidant push-pull dynamics" in rewritten_step.lower()

    rewritten_off, _, _ = mem.resolve_follow_up(
        user_id=uid,
        conversation_id=cid,
        query="Who is Virat Kohli?"
    )
    assert rewritten_off == "Who is Virat Kohli?"
    mem.clear_session(session_id=cid, user_id=uid, mode="owner")


def test_drive_service_mock_and_env_owner_folder(monkeypatch):
    # Case 1: Dedicated GOOGLE_DRIVE_OWNER_FOLDER_ID env var
    monkeypatch.setenv("GOOGLE_DRIVE_OWNER_FOLDER_ID", "drv_owner_env")
    svc = GoogleDriveService()
    mock_client = MagicMock()

    def list_env_side_effect(**kwargs):
        q = kwargs.get("q", "")
        resp = MagicMock()
        if "folder" in q:
            resp.execute.return_value = {"files": []}
        elif "'drv_owner_env' in parents" in q:
            resp.execute.return_value = {
                "files": [{
                    "id": "file_own_env",
                    "name": "Podcast_Ep1.txt",
                    "modifiedTime": "2026-11-11T12:00:00Z",
                    "size": "1200",
                    "version": "1",
                    "mimeType": "text/plain",
                }]
            }
        else:
            resp.execute.return_value = {"files": []}
        return resp

    mock_client.files.return_value.list.side_effect = list_env_side_effect
    monkeypatch.setattr(svc, "_get_drive_client", lambda: mock_client)
    env_files = svc.list_pdf_files()
    assert len(env_files) == 1
    assert env_files[0]["category"] == "owner"

    # Case 2: Subfolder auto-discovery under root Drive folder
    monkeypatch.delenv("GOOGLE_DRIVE_OWNER_FOLDER_ID", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_CLINICAL_FOLDER_ID", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_SALES_FOLDER_ID", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_PLATFORM_FOLDER_ID", raising=False)

    def list_auto_side_effect(**kwargs):
        q = kwargs.get("q", "")
        resp = MagicMock()
        if f"'{svc.folder_id}' in parents" in q and "folder" in q:
            resp.execute.return_value = {
                "files": [{"id": "sub_owner_1", "name": "Owner Voice & Podcast"}]
            }
        elif "folder" in q:
            resp.execute.return_value = {"files": []}
        elif "'sub_owner_1' in parents" in q:
            resp.execute.return_value = {
                "files": [{
                    "id": "file_own_1",
                    "name": "DSH_OWNER_VOICE_GUIDE.pdf",
                    "modifiedTime": "2026-11-11T12:00:00Z",
                    "size": "6720",
                    "version": "1",
                    "mimeType": "application/pdf",
                }]
            }
        else:
            resp.execute.return_value = {"files": []}
        return resp

    mock_client.files.return_value.list.side_effect = list_auto_side_effect
    files = svc.list_pdf_files()
    owner_files = [f for f in files if f["name"] == "DSH_OWNER_VOICE_GUIDE.pdf"]
    assert len(owner_files) == 1
    assert owner_files[0]["category"] == "owner"

