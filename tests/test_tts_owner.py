import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.tts_service import ElevenLabsTTSService, clean_text_for_speech


def test_clean_text_for_speech_strips_markdown_and_urls():
    raw = (
        "### Understanding Push-Pull\n\n"
        "Hi there, **Dr. Sarah** here! Use the `1-1-1` protocol and visit "
        "[Attachment Guide](https://doctorsarahhensley.com/guide) or https://example.com/raw.\n\n"
        "- Pause and breathe\n"
        "- Choose a secure action"
    )
    cleaned = clean_text_for_speech(raw)
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "https://" not in cleaned
    assert "Attachment Guide" in cleaned
    assert "Doctor Sarah" in cleaned
    assert "one-one-one" in cleaned


def test_clean_text_for_speech_truncates_at_sentence_boundary():
    long_text = "First sentence here. " + ("A" * 180) + ". Trailing part that exceeds limit."
    cleaned = clean_text_for_speech(long_text, max_chars=210)
    assert len(cleaned) <= 210
    assert cleaned.endswith(".")


def test_clean_text_for_speech_does_not_truncate_by_default(monkeypatch):
    monkeypatch.delenv("TTS_MAX_CHARS", raising=False)
    long_text = ("Sentence one. " * 220) + "Final closing paragraph."
    assert len(long_text) > 2500
    cleaned = clean_text_for_speech(long_text)
    assert cleaned.endswith("Final closing paragraph.")
    assert len(cleaned) > 2500


@pytest.fixture
def tts_client(monkeypatch):
    monkeypatch.setenv("RAG_API_KEY", "test_tts_secret_key")
    monkeypatch.setenv("ENFORCE_CHAT_AUTH", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el_test_key")
    monkeypatch.setenv("ELEVENLABS_OWNER_VOICE_ID", "voice_owner_123")
    monkeypatch.setenv("TTS_ALL_MODES", "false")

    import app as app_module
    from src.tts_service import get_tts_service

    get_tts_service().clear_cache()
    return TestClient(app_module.app)


def test_tts_stream_requires_auth(tts_client):
    resp = tts_client.post("/api/v1/tts/stream", json={"text": "Hello", "mode": "owner"})
    assert resp.status_code == 401


def test_tts_stream_rejects_non_owner_modes_in_demo(tts_client):
    resp = tts_client.post(
        "/api/v1/tts/stream",
        headers={"X-API-Key": "test_tts_secret_key"},
        json={"text": "Hello from sales", "mode": "sales"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "Owner Agent demo" in (body.get("error") or body.get("detail") or "")


def test_tts_stream_returns_503_when_elevenlabs_unconfigured(tts_client, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    resp = tts_client.post(
        "/api/v1/tts/stream",
        headers={"X-API-Key": "test_tts_secret_key"},
        json={"text": "Hello world", "mode": "owner"},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert "ELEVENLABS_API_KEY" in (body.get("error") or body.get("detail") or "")


def test_tts_stream_synthesizes_and_caches_owner_audio(tts_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_content.return_value = [b"ID3_FAKE_MP3_", b"CHUNK_DATA"]

    with patch("src.tts_service.requests.post", return_value=mock_resp) as mock_post:
        r1 = tts_client.post(
            "/api/v1/tts/stream",
            headers={"X-API-Key": "test_tts_secret_key"},
            json={"text": "**Hi!** Welcome to Dr. Sarah's podcast.", "mode": "owner"},
        )
        assert r1.status_code == 200
        assert r1.headers["content-type"].startswith("audio/mpeg")
        assert r1.headers.get("X-TTS-Cache") == "MISS"
        assert r1.content == b"ID3_FAKE_MP3_CHUNK_DATA"
        assert mock_post.call_count == 1

        # Second identical request must serve from cache without hitting ElevenLabs
        r2 = tts_client.post(
            "/api/v1/tts/stream",
            headers={"X-API-Key": "test_tts_secret_key"},
            json={"text": "**Hi!** Welcome to Dr. Sarah's podcast.", "mode": "owner"},
        )
        assert r2.status_code == 200
        assert r2.headers.get("X-TTS-Cache") == "HIT"
        assert r2.content == b"ID3_FAKE_MP3_CHUNK_DATA"
        assert mock_post.call_count == 1


def test_tts_stream_falls_back_to_edge_tts_on_quota_error(tts_client):
    el_resp = MagicMock()
    el_resp.status_code = 401
    el_resp.text = '{"detail":{"status":"quota_exceeded","message":"Credits exhausted"}}'

    fake_comm = MagicMock()
    fake_comm.stream_sync.return_value = [
        {"type": "audio", "data": b"EDGE_MP3_1_"},
        {"type": "audio", "data": b"EDGE_MP3_2"},
    ]

    with patch("src.tts_service.requests.post", return_value=el_resp), \
         patch("edge_tts.Communicate", return_value=fake_comm) as mock_edge:
        r1 = tts_client.post(
            "/api/v1/tts/stream",
            headers={"X-API-Key": "test_tts_secret_key"},
            json={"text": "Testing fallback voice.", "mode": "owner"},
        )
        assert r1.status_code == 200
        assert r1.headers["content-type"].startswith("audio/mpeg")
        assert r1.headers.get("X-TTS-Cache") == "MISS"
        assert r1.content == b"EDGE_MP3_1_EDGE_MP3_2"
        assert mock_edge.call_count == 1

        # Second call serves edge-tts audio from cache
        r2 = tts_client.post(
            "/api/v1/tts/stream",
            headers={"X-API-Key": "test_tts_secret_key"},
            json={"text": "Testing fallback voice.", "mode": "owner"},
        )
        assert r2.status_code == 200
        assert r2.headers.get("X-TTS-Cache") == "HIT"
        assert r2.content == b"EDGE_MP3_1_EDGE_MP3_2"
        assert mock_edge.call_count == 1


def test_tts_stream_direct_edge_provider_without_elevenlabs_key(tts_client, monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "edge")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    fake_comm = MagicMock()
    fake_comm.stream_sync.return_value = [{"type": "audio", "data": b"DIRECT_EDGE_MP3"}]

    with patch("edge_tts.Communicate", return_value=fake_comm):
        resp = tts_client.post(
            "/api/v1/tts/stream",
            headers={"X-API-Key": "test_tts_secret_key"},
            json={"text": "Direct edge provider test.", "mode": "owner"},
        )
        assert resp.status_code == 200
        assert resp.content == b"DIRECT_EDGE_MP3"
