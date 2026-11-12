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
