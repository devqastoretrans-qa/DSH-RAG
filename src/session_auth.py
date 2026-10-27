import os
import hmac
import hashlib
import json
import base64
import time
import secrets
from collections import defaultdict, deque
from typing import Optional, Dict, Any, Tuple
from fastapi import Request, HTTPException, status
import logging

logger = logging.getLogger(__name__)


def _b64url_encode(data: bytes) -> str:
    """Encodes bytes to base64url string without trailing equals signs."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def _b64url_decode(data: str) -> bytes:
    """Decodes base64url string with proper padding."""
    padding = '=' * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode((data + padding).encode('utf-8'))


def get_session_secret() -> str:
    """
    Returns the secret key used for signing chat session tokens.
    Priority:
    1. CHAT_SESSION_SECRET (dedicated secret)
    2. RAG_API_KEY (master system key)
    3. WC_WEBHOOK_SECRET (fallback shared secret)
    """
    secret = (
        os.getenv("CHAT_SESSION_SECRET", "").strip() or
        os.getenv("RAG_API_KEY", "").strip() or
        os.getenv("WC_WEBHOOK_SECRET", "").strip()
    )
    if not secret:
        raise RuntimeError("No session secret configured. Please set CHAT_SESSION_SECRET or RAG_API_KEY.")
    return secret


def create_session_token(
    user_id: str = "guest",
    session_id: Optional[str] = None,
    mode: str = "generic",
    ttl_seconds: int = 7200,
    secret: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates an HMAC-SHA256 signed JSON Web Token (JWT) valid for ttl_seconds (default 2 hours).
    Returns token string along with metadata (expiry, session_id).
    """
    sign_key = secret or get_session_secret()
    now = int(time.time())
    exp = now + int(ttl_seconds)
    sid = session_id or f"sess_{int(now)}_{secrets.token_hex(4)}"

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "sid": str(sid),
        "mode": str(mode),
        "iat": now,
        "exp": exp
    }

    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')

    header_b64 = _b64url_encode(header_json)
    payload_b64 = _b64url_encode(payload_json)

    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(sign_key.encode('utf-8'), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)

    token = f"{header_b64}.{payload_b64}.{sig_b64}"

    return {
        "success": True,
        "token": token,
        "user_id": str(user_id),
        "session_id": str(sid),
        "mode": str(mode),
        "issued_at": now,
        "expires_at": exp,
        "ttl_seconds": int(ttl_seconds)
    }


def verify_session_token(token: str, secret: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifies an HMAC-SHA256 signed session token.
    Validates structure, signature, and expiration timestamp.
    Raises ValueError on invalid format, bad signature, or expiry.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Missing or invalid token string.")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token format. Expected header.payload.signature.")

    header_b64, payload_b64, sig_b64 = parts
    sign_key = secret or get_session_secret()

    # 1. Verify Signature
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    expected_sig = hmac.new(sign_key.encode('utf-8'), signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception as e:
        raise ValueError(f"Invalid signature encoding: {str(e)}")

    if not secrets.compare_digest(actual_sig, expected_sig):
        raise ValueError("Invalid token signature.")

    # 2. Decode and Validate Payload
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Corrupt token payload: {str(e)}")

    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")

    # 3. Expiration Check
    now = time.time()
    exp = payload.get("exp")
    if exp is not None:
        try:
            exp_float = float(exp)
        except (ValueError, TypeError):
            raise ValueError("Invalid expiration claim in token.")
        if now > exp_float:
            raise ValueError("Session token has expired.")

    return payload


class SlidingWindowRateLimiter:
    """
    In-memory sliding window rate limiter for defense-in-depth protection.
    Limits requests to max_requests within window_seconds per key (IP address or session ID).
    """
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.history: Dict[str, deque] = defaultdict(deque)

    def is_limited(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - self.window_seconds
        queue = self.history[key]

        # Purge timestamps outside the sliding window
        while queue and queue[0] < window_start:
            queue.popleft()

        if len(queue) >= self.max_requests:
            oldest = queue[0]
            retry_after = max(1, int(oldest + self.window_seconds - now))
            return True, retry_after

        queue.append(now)
        return False, 0

    def reset(self, key: Optional[str] = None):
        """Clears rate limit state (useful for testing)."""
        if key:
            self.history.pop(key, None)
        else:
            self.history.clear()


# Default singleton rate limiter: 15 messages per 60 seconds per client
chat_rate_limiter = SlidingWindowRateLimiter(max_requests=15, window_seconds=60)


async def verify_chat_access(request: Request) -> Dict[str, Any]:
    """
    FastAPI Security Dependency for Chat Endpoints (/chat, /chat/stream, /chat/reset).
    Validates either:
    1. Master RAG_API_KEY (Admin / Test access, bypasses rate limit)
    2. Short-Lived HMAC-SHA256 Session Token (WordPress frontend visitors)

    Extracts token from:
    - 'Authorization: Bearer <token>'
    - 'X-Session-Token: <token>'
    - 'X-API-Key: <token>'
    - Query parameter '?token=<token>' or '?session_token=<token>'
    - JSON body field 'session_token'
    """
    master_key = os.getenv("RAG_API_KEY", "").strip()

    # 1. Look for token in HTTP Headers
    candidate_token = None
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        candidate_token = auth_header[7:].strip()
    elif "x-session-token" in request.headers:
        candidate_token = request.headers.get("x-session-token", "").strip()
    elif "x-api-key" in request.headers:
        candidate_token = request.headers.get("x-api-key", "").strip()

    # 2. Look in Query Parameters
    if not candidate_token:
        candidate_token = request.query_params.get("token") or request.query_params.get("session_token")

    # 3. Look in JSON Body if available and not yet found
    if not candidate_token:
        try:
            body_bytes = await request.body()
            if body_bytes:
                body_dict = json.loads(body_bytes.decode("utf-8"))
                if isinstance(body_dict, dict):
                    candidate_token = body_dict.get("session_token")
        except Exception:
            pass

    enforce_auth = os.getenv("ENFORCE_CHAT_AUTH", "false").strip().lower() in ("true", "1", "yes")

    if not candidate_token:
        if not enforce_auth:
            # Permissive transition mode: allows existing WordPress frontend without breaking changes
            # Still strictly enforces IP rate-limiting to prevent bot spam
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                request.headers.get("x-real-ip", "").strip() or
                (request.client.host if request.client else "unknown_ip")
            )
            rate_key = f"legacy:{client_ip}"
            is_limited, retry_after = chat_rate_limiter.is_limited(rate_key)
            if is_limited:
                logger.warning(f"[Session Auth - Legacy] Rate limit exceeded for {rate_key}. Retry-After: {retry_after}s")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Maximum 15 messages per minute allowed.",
                    headers={"Retry-After": str(retry_after)}
                )
            return {
                "auth_type": "legacy_permissive",
                "user_id": "guest",
                "session_id": None,
                "mode": "generic",
                "is_admin": False
            }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid session token or API key required.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # A. Check Master API Key (Admin bypass)
    if master_key and secrets.compare_digest(candidate_token.encode("utf-8"), master_key.encode("utf-8")):
        return {
            "auth_type": "api_key",
            "user_id": "admin",
            "session_id": None,
            "mode": "generic",
            "is_admin": True
        }

    # B. Validate Session Token (HMAC-SHA256 JWT)
    try:
        claims = verify_session_token(candidate_token)
    except ValueError as e:
        err_msg = str(e)
        status_code = status.HTTP_401_UNAUTHORIZED
        logger.warning(f"[Session Auth] Token verification rejected: {err_msg}")
        raise HTTPException(
            status_code=status_code,
            detail=f"Unauthorized: {err_msg}",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # C. Apply In-App Rate Limiting for Session Tokens
    # Key based on client IP or user session ID
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip", "").strip() or
        (request.client.host if request.client else "unknown_ip")
    )
    rate_key = f"{client_ip}:{claims.get('sid') or claims.get('sub', 'guest')}"
    is_limited, retry_after = chat_rate_limiter.is_limited(rate_key)
    if is_limited:
        logger.warning(f"[Session Auth] Rate limit exceeded for {rate_key}. Retry-After: {retry_after}s")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum 15 messages per minute allowed.",
            headers={"Retry-After": str(retry_after)}
        )

    claims["auth_type"] = "session_token"
    claims["is_admin"] = False
    return claims
