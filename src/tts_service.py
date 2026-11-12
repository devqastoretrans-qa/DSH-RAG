"""
ElevenLabs Text-to-Speech (TTS) Service for DSH-RAG (Phase 1 - Owner Bot Demo).

Provides:
- Speech-friendly Markdown/URL sanitization for RAG answers
- Mode-aware ElevenLabs voice resolution (scoped to 'owner' by default)
- Streaming MP3 synthesis with bounded in-memory LRU audio caching
"""

import hashlib
import os
import re
from collections import OrderedDict
from threading import Lock
from typing import Iterator, Optional, Tuple

import requests


DEFAULT_ELEVENLABS_MODEL = "eleven_flash_v2_5"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_TTS_MAX_CHARS = 0
DEFAULT_TTS_CACHE_MAX_ITEMS = 64
DEFAULT_EDGE_TTS_VOICE = "en-US-AvaNeural"

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")
_MD_LIST_RE = re.compile(r"(?m)^\s*(?:[-*•]+|\d+[.)])\s+")
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>\s?")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|~~)")


class TTSConfigurationError(RuntimeError):
    """Raised when ElevenLabs API key or voice ID is missing."""


class TTSUpstreamError(RuntimeError):
    """Raised when ElevenLabs returns an HTTP or network error."""


def is_tts_all_modes_enabled() -> bool:
    return os.getenv("TTS_ALL_MODES", "false").strip().lower() in ("1", "true", "yes", "on")


def get_elevenlabs_api_key() -> str:
    return os.getenv("ELEVENLABS_API_KEY", "").strip()


def get_elevenlabs_model_id() -> str:
    return os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_ELEVENLABS_MODEL).strip() or DEFAULT_ELEVENLABS_MODEL


def get_tts_provider() -> str:
    provider = os.getenv("TTS_PROVIDER", "auto").strip().lower()
    return provider if provider in ("auto", "elevenlabs", "edge") else "auto"


def is_edge_fallback_enabled() -> bool:
    return os.getenv("TTS_EDGE_FALLBACK", "true").strip().lower() in ("1", "true", "yes", "on")


def get_edge_tts_voice() -> str:
    return os.getenv("EDGE_TTS_VOICE", DEFAULT_EDGE_TTS_VOICE).strip() or DEFAULT_EDGE_TTS_VOICE


def get_tts_max_chars() -> int:
    try:
        val = int(os.getenv("TTS_MAX_CHARS", str(DEFAULT_TTS_MAX_CHARS)))
        if val <= 0:
            return 0
        return max(200, min(val, 40000))
    except ValueError:
        return DEFAULT_TTS_MAX_CHARS


def resolve_voice_id(mode: str = "owner") -> str:
    """Resolve ElevenLabs voice ID for the given agent mode."""
    clean_mode = (mode or "owner").strip().lower()
    if clean_mode == "owner":
        vid = os.getenv("ELEVENLABS_OWNER_VOICE_ID", "").strip()
        if vid:
            return vid
    mode_env = f"ELEVENLABS_VOICE_ID_{clean_mode.upper()}"
    vid = os.getenv(mode_env, "").strip() or os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "").strip()
    return vid


def clean_text_for_speech(text: str, max_chars: Optional[int] = None) -> str:
    """Normalize Markdown-formatted RAG text into natural spoken prose."""
    if not text or not text.strip():
        return ""

    limit = max_chars if max_chars is not None else get_tts_max_chars()
    cleaned = text.replace("\r\n", "\n")

    # Replace fenced code blocks with brief pause or omit verbose blocks
    cleaned = _CODE_FENCE_RE.sub(" ", cleaned)
    # Turn [Course Name](https://...) into just "Course Name"
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
    # Remove any bare URLs
    cleaned = _BARE_URL_RE.sub("", cleaned)
    # Unwrap inline code and strip markdown formatting markers
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _MD_HEADING_RE.sub("", cleaned)
    cleaned = _BLOCKQUOTE_RE.sub("", cleaned)
    cleaned = _MD_LIST_RE.sub("", cleaned)
    cleaned = _EMPHASIS_RE.sub("", cleaned)

    # Pronunciation helpers for domain terms
    cleaned = re.sub(r"\bDr\.", "Doctor", cleaned)
    cleaned = re.sub(r"\bPh\.?D\.?", "PhD", cleaned)
    cleaned = re.sub(r"\b1[-:\s]*1[-:\s]*1\b", "one-one-one", cleaned)
    cleaned = cleaned.replace("→", ", ").replace("—", ", ").replace("–", ", ")

    # Collapse line breaks into natural pauses and normalize whitespace
    cleaned = re.sub(r"\n{2,}", ". ", cleaned)
    cleaned = re.sub(r"\n", " ", cleaned)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    if limit <= 0 or len(cleaned) <= limit:
        return cleaned

    # Truncate cleanly at a sentence or word boundary within limit
    window = cleaned[:limit]
    last_punct = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if last_punct > int(limit * 0.5):
        return window[: last_punct + 1].strip()
    last_space = window.rfind(" ")
    if last_space > 0:
        return window[:last_space].strip() + "..."
    return window.strip()


class ElevenLabsTTSService:
    """Thread-safe ElevenLabs streaming TTS client with bounded in-memory MP3 cache."""

    def __init__(self, max_cache_items: int = DEFAULT_TTS_CACHE_MAX_ITEMS):
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._max_cache_items = max(1, max_cache_items)
        self._lock = Lock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    @staticmethod
    def _cache_key(voice_id: str, model_id: str, speech_text: str) -> str:
        digest = hashlib.sha256(f"{voice_id}:{model_id}:{speech_text}".encode("utf-8")).hexdigest()
        return digest

    def get_cached_audio(self, voice_id: str, model_id: str, speech_text: str) -> Optional[bytes]:
        key = self._cache_key(voice_id, model_id, speech_text)
        with self._lock:
            audio = self._cache.get(key)
            if audio is not None:
                self._cache.move_to_end(key)
            return audio

    def _put_cached_audio(self, key: str, audio: bytes) -> None:
        if not audio:
            return
        with self._lock:
            self._cache[key] = audio
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_cache_items:
                self._cache.popitem(last=False)

    def _prepare_edge_stream(self, speech_text: str) -> Tuple[Iterator[bytes], bool]:
        """Synthesize MP3 audio via free Microsoft Edge Neural TTS (edge-tts)."""
        edge_voice = get_edge_tts_voice()
        edge_model = "edge-tts"
        key = self._cache_key(edge_voice, edge_model, speech_text)

        cached = self.get_cached_audio(edge_voice, edge_model, speech_text)
        if cached is not None:
            def _cached_iter() -> Iterator[bytes]:
                yield cached
            return _cached_iter(), True

        try:
            import edge_tts
        except ImportError as exc:
            raise TTSConfigurationError("edge-tts package is not installed.") from exc

        communicate = edge_tts.Communicate(speech_text, voice=edge_voice)

        def _stream_and_cache() -> Iterator[bytes]:
            chunks = []
            try:
                for chunk in communicate.stream_sync():
                    if chunk.get("type") == "audio" and chunk.get("data"):
                        data = chunk["data"]
                        chunks.append(data)
                        yield data
            except Exception as exc:
                if not chunks:
                    raise TTSUpstreamError(f"Edge TTS synthesis failed: {exc}") from exc
            if chunks:
                self._put_cached_audio(key, b"".join(chunks))

        return _stream_and_cache(), False

    def prepare_stream(
        self, raw_text: str, mode: str = "owner"
    ) -> Tuple[Iterator[bytes], bool]:
        """
        Validate configuration, sanitize text, check cache, and open TTS stream.
        Uses ElevenLabs by default and automatically falls back to free edge-tts
        when ElevenLabs credits/quota are exhausted (or when TTS_PROVIDER=edge).
        Returns (audio_chunk_iterator, cache_hit).
        """
        speech_text = clean_text_for_speech(raw_text)
        if not speech_text:
            raise ValueError("No speakable text remains after cleaning.")

        provider = get_tts_provider()
        if provider == "edge":
            return self._prepare_edge_stream(speech_text)

        api_key = get_elevenlabs_api_key()
        if not api_key:
            raise TTSConfigurationError("ElevenLabs is not configured (missing ELEVENLABS_API_KEY).")

        voice_id = resolve_voice_id(mode)
        if not voice_id:
            raise TTSConfigurationError(
                f"No ElevenLabs voice ID configured for mode '{mode}' (set ELEVENLABS_OWNER_VOICE_ID)."
            )

        model_id = get_elevenlabs_model_id()
        key = self._cache_key(voice_id, model_id, speech_text)

        cached = self.get_cached_audio(voice_id, model_id, speech_text)
        if cached is not None:
            def _cached_iter() -> Iterator[bytes]:
                yield cached
            return _cached_iter(), True

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": speech_text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.78,
                "style": 0.15,
                "use_speaker_boost": True,
            },
        }
        params = {"output_format": DEFAULT_OUTPUT_FORMAT}

        try:
            resp = requests.post(
                url,
                headers=headers,
                params=params,
                json=payload,
                stream=True,
                timeout=(10, 45),
            )
        except requests.RequestException as exc:
            if provider == "auto" and is_edge_fallback_enabled():
                return self._prepare_edge_stream(speech_text)
            raise TTSUpstreamError(f"Failed to connect to ElevenLabs: {exc}") from exc

        if resp.status_code >= 400:
            detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            status_code = resp.status_code
            resp.close()
            is_quota_or_auth = status_code in (401, 402, 429) or "quota" in detail.lower() or "credit" in detail.lower()
            if provider == "auto" and is_edge_fallback_enabled() and is_quota_or_auth:
                return self._prepare_edge_stream(speech_text)
            raise TTSUpstreamError(f"ElevenLabs API error ({status_code}): {detail}")

        def _stream_and_cache() -> Iterator[bytes]:
            chunks = []
            try:
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        chunks.append(chunk)
                        yield chunk
            finally:
                resp.close()
            if chunks:
                self._put_cached_audio(key, b"".join(chunks))

        return _stream_and_cache(), False


_tts_service: Optional[ElevenLabsTTSService] = None


def get_tts_service() -> ElevenLabsTTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = ElevenLabsTTSService()
    return _tts_service

