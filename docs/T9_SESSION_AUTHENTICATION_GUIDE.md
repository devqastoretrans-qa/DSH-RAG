# 🛡️ T9: Secure Public Chat Endpoints — Implementation & Integration Guide

## 1. Problem Overview & Threat Model

Prior to **Task T9**, the chat endpoints (`/chat`, `/chat/stream`, `/chat/reset`, `/api/chat/history`) were open to unauthenticated HTTP requests.
- **The Risk:** Any automated scraper or bot could spam the endpoints, depleting the OpenAI / Groq LLM API quota and racking up server bills.
- **Why Not Use the Master API Key in Frontend JS?** If `RAG_API_KEY` is embedded in client-side JavaScript, any visitor can open Chrome DevTools (`F12`), inspect network requests or source code, steal the key, and execute arbitrary calls against all admin endpoints (`/upload`, `/api/users`, etc.).

---

## 2. The T9 Solution: Cryptographic Short-Lived Session Tokens

The solution utilizes **short-lived HMAC-SHA256 session tokens** (JSON Web Tokens) with a **1 to 2-hour Time-To-Live (TTL)**.

```
+-----------------------------------------------------------------------------------------+
|                                    T9 TOKEN FLOW                                        |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
| 1. Visitor loads page        +-----------------------+                                  |
|    ------------------------> | WordPress Backend     |                                  |
|                              | (PHP Server)          |                                  |
|                              +-----------------------+                                  |
|                                     |                                                   |
|                                     | Signs temporary token                             |
|                                     | (Method A or Method B)                            |
|                                     v                                                   |
| 2. HTML rendered with token  +-----------------------+                                  |
|    <------------------------ | Visitor's Browser     |                                  |
|                              | (JavaScript Widget)   |                                  |
|                              +-----------------------+                                  |
|                                     |                                                   |
|                                     | 3. POST /chat/stream                              |
|                                     |    Authorization: Bearer <session_token>          |
|                                     v                                                   |
|                              +---------------------------------------------------+      |
|                              | Nginx (Rate Limit: 30r/m, burst 15)               |      |
|                              +---------------------------------------------------+      |
|                                     |                                                   |
|                                     | (Under rate limit)                                |
|                                     v                                                   |
|                              +---------------------------------------------------+      |
|                              | FastAPI Backend (DSH-RAG)                         |      |
|                              | - Verifies HMAC-SHA256 signature                  |      |
|                              | - Checks expiration (exp < now)                   |      |
|                              | - Enforces in-app sliding window (15 msgs/min)    |      |
|                              +---------------------------------------------------+      |
|                                     |                                                   |
|                                     v                                                   |
|                              +---------------------------------------------------+      |
|                              | Synthesize & Stream RAG Response                  |      |
|                              +---------------------------------------------------+      |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Endpoints Protected

| Endpoint | Method | Authentication | Rate Limit |
| :--- | :---: | :--- | :--- |
| `/chat` | `POST` | Session Token or Master API Key | 15 req/min |
| `/chat/stream` | `POST` | Session Token or Master API Key | 15 req/min |
| `/chat/reset` | `POST` / `DELETE` | Session Token or Master API Key | 15 req/min |
| `/api/chat/history` | `GET` | Session Token or Master API Key | 15 req/min |
| `/api/v1/session/token` | `POST` | **Master `RAG_API_KEY` ONLY** | Server-to-server |

---

## 4. WordPress Integration (PHP)

WordPress can generate session tokens in **two ways**:

### Option A: Server-to-Server Token API (Recommended for simplicity)

When WordPress renders the chat page or returns chat config via `wp_localize_script`:

```php
/**
 * Request a short-lived chat session token from the DSH-RAG backend.
 *
 * @param int|string $user_id Current WordPress user ID or 'guest'.
 * @param string $session_id Frontend session ID.
 * @param string $mode 'generic' or 'sales'.
 * @return string|null Session token or null on error.
 */
function dsh_get_chat_session_token($user_id = 'guest', $session_id = '', $mode = 'generic') {
    $api_url = 'https://agent.doctorsarahhensley.com/api/v1/session/token';
    $master_key = defined('DSH_RAG_API_KEY') ? DSH_RAG_API_KEY : 'YOUR_MASTER_RAG_API_KEY';

    $response = wp_remote_post($api_url, [
        'headers' => [
            'Content-Type' => 'application/json',
            'X-API-Key'    => $master_key,
        ],
        'body'    => wp_json_encode([
            'user_id'     => (string)$user_id,
            'session_id'  => $session_id ?: ('sess_' . time() . '_' . wp_generate_password(6, false)),
            'mode'        => $mode,
            'ttl_seconds' => 7200, // 2 Hours validity
        ]),
        'timeout' => 5,
    ]);

    if (is_wp_error($response)) {
        error_log('[DSH-RAG] Failed to obtain session token: ' . $response->get_error_message());
        return null;
    }

    $body = json_decode(wp_remote_retrieve_body($response), true);
    return !empty($body['token']) ? $body['token'] : null;
}
```

---

### Option B: Offline Local Token Signing in Pure PHP (Zero HTTP overhead)

If you prefer zero network roundtrips on page load, WordPress can sign the HMAC-SHA256 token directly in PHP using the shared `CHAT_SESSION_SECRET`:

```php
/**
 * Locally sign a standard HMAC-SHA256 JWT session token in pure PHP.
 * Requires NO external Composer dependencies.
 */
function dsh_create_local_session_token($user_id = 'guest', $session_id = '', $mode = 'generic', $ttl = 7200) {
    $secret = defined('DSH_CHAT_SECRET') ? DSH_CHAT_SECRET : 'YOUR_CHAT_SESSION_SECRET';
    $now = time();
    $exp = $now + $ttl;
    $sid = $session_id ?: ('sess_' . $now . '_' . bin2hex(random_bytes(3)));

    $header = json_encode(['alg' => 'HS256', 'typ' => 'JWT']);
    $payload = json_encode([
        'sub'  => (string)$user_id,
        'sid'  => (string)$sid,
        'mode' => (string)$mode,
        'iat'  => $now,
        'exp'  => $exp,
    ]);

    $b64_header  = rtrim(strtr(base64_encode($header), '+/', '-_'), '=');
    $b64_payload = rtrim(strtr(base64_encode($payload), '+/', '-_'), '=');
    $signing_input = "{$b64_header}.{$b64_payload}";

    $signature = hash_hmac('sha256', $signing_input, $secret, true);
    $b64_sig = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');

    return "{$signing_input}.{$b64_sig}";
}
```

---

## 5. Frontend JavaScript Integration

The JavaScript frontend chat widget passes the session token via the `Authorization` header, the `X-Session-Token` header, or directly in the JSON payload:

```javascript
// Example: Sending a message with the session token
async function sendChatMessage(message, sessionToken, sessionId, userId) {
    const response = await fetch('https://agent.doctorsarahhensley.com/chat/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${sessionToken}`, // Standard Bearer token
            // Alternatively: 'X-Session-Token': sessionToken
        },
        body: JSON.stringify({
            message: message,
            session_id: sessionId,
            user_id: userId,
            mode: 'generic'
        })
    });

    if (response.status === 401) {
        console.error("Session token expired or invalid. Please refresh page.");
        return;
    }
    if (response.status === 429) {
        console.warn("Rate limit exceeded. Please wait a moment before sending another message.");
        return;
    }

    // Read SSE stream tokens...
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        console.log("Stream chunk:", chunk);
    }
}
```

---

## 6. Rate Limiting Multi-Layer Defense

1. **Nginx Reverse Proxy Layer:**
   - Zone: `chat_limit` (30 requests/minute per IP, burst=15, nodelay).
   - Zone: `general_limit` (60 requests/minute per IP, burst=30).
   - Exempt: `/api/webhooks/woocommerce` is completely exempt from rate limiting to prevent webhook dropped frames.

2. **FastAPI Application Layer (`SlidingWindowRateLimiter`):**
   - 15 requests per 60 seconds per IP / Session ID.
   - Prevents abuse even if requests bypass Nginx or in local testing.
   - Master `RAG_API_KEY` is exempt from rate limiting for administrative testing and benchmarks.
