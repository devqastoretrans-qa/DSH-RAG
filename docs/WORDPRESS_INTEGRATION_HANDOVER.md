# WordPress & WooCommerce Integration Handover Guide
**Target System:** Dr. Sarah Hensley Relationship RAG System (`agent.doctorsarahhensley.com`)  
**Intended Audience:** WordPress Administrator & Theme/Plugin Developer  
**Date:** October 27, 2026  
**Status:** Ready for Deployment  

---

## 1. Executive Summary

This document provides the exact configuration settings and PHP code snippets required to connect the live WordPress/WooCommerce site (`doctorsarahhensley.com`) to the DSH-RAG AI backend. 

There are **two distinct tasks**:
1. **For the WordPress Administrator:** Configure the WooCommerce webhook and generate a read-only Application Password in WP-Admin (10 minutes, no code).
2. **For the WordPress Developer:** Add a lightweight PHP helper function to issue short-lived chat session tokens for logged-in users (15 minutes, copy-paste PHP).

---

## 2. Checklist for the WordPress Administrator (WP-Admin)

### Task 1: Configure WooCommerce Webhooks
Whenever a customer purchases a coaching package or masterclass, WooCommerce automatically notifies DSH-RAG so the user's profile and purchase history are updated in real time.

1. Log in to **WP-Admin**.
2. Go to **WooCommerce $\rightarrow$ Settings $\rightarrow$ Advanced $\rightarrow$ Webhooks**.
3. Click **Add webhook** (or edit existing):
   * **Name:** `DSH-RAG Order Sync`
   * **Status:** `Active`
   * **Topic:** `Order created` (and optionally create a second one for `Order updated`)
   * **Delivery URL:** `https://agent.doctorsarahhensley.com/api/webhooks/woocommerce`
   * **Secret:** Enter a strong 32-character secret (e.g. `dsh_wc_live_secret_k9X2mP8q...`).  
     *(Share this exact string with the DSH-RAG team to put in `.env` as `WC_WEBHOOK_SECRET`).*
   * **API Version:** `WP REST API Integration v3`
4. Click **Save Webhook**.

---

### Task 2: Create a Read-Only Application Password for Nightly ETL
DSH-RAG runs an automated nightly sync at 2:00 AM to ensure no customer purchase records are missed if network outages occur.

1. In WP-Admin, navigate to **Users $\rightarrow$ Add New**.
2. Create a dedicated sync user (e.g., `rag_sync_bot` or use an existing admin).
3. Scroll down to **Application Passwords**.
4. Enter an Application Name (e.g., `DSH-RAG Nightly Sync`) and click **Add New Application Password**.
5. Copy the generated 24-character password (e.g., `abcd efgh ijkl mnop qrst uvwx`).
6. Share the Username and Application Password with the DSH-RAG team to add to `.env`:
   ```ini
   WORDPRESS_USER=rag_sync_bot
   WORDPRESS_APP_PASSWORD=abcd efgh ijkl mnop qrst uvwx
   ```

---

### Task 3: Verify the PAB (Attachment Quiz) Plugin
When a customer chats with Dr. Sarah's bot, the bot checks local storage for their attachment style (Secure, Anxious, Avoidant, Disorganized). If not found, it queries:  
`https://doctorsarahhensley.com/wp-json/pab/v1/inspect/profile?user_id={id}&fresh=true`

* **Action:** Ensure the custom PAB plugin is active and share the pre-configured `PAB_API_KEY` header with the DSH-RAG team.

---

## 3. Checklist for the WordPress Developer (PHP & JS)

### Task 4: Issue Short-Lived Chat Session Tokens (T9 Security)
To prevent unauthorized internet bots from spamming your AI server and racking up OpenAI/Groq API bills, the public chat endpoint (`/chat/stream`) requires an HMAC-SHA256 session token signed by WordPress.

#### Step A: Add Secret to `wp-config.php`
Add this shared secret to your WordPress `wp-config.php` (must match `CHAT_SESSION_SECRET` in DSH-RAG `.env`):
```php
define('CHAT_SESSION_SECRET', 'your_32_byte_random_hex_secret_here');
```

#### Step B: Add PHP Token Generator to `functions.php`
Drop this helper function into your active child theme's `functions.php` or custom plugin:

```php
/**
 * Generate a cryptographically signed session token for Dr. Sarah's AI Chat.
 *
 * @param int|string $user_id Current WordPress user ID or 'guest'.
 * @param int $ttl Lifetime in seconds (default: 7200 = 2 hours).
 * @return string HMAC-SHA256 session token.
 */
function dsh_generate_chat_token($user_id = null, $ttl = 7200) {
    if (!$user_id) {
        $user_id = is_user_logged_in() ? get_current_user_id() : 'guest_' . wp_generate_password(8, false);
    }

    $secret = defined('CHAT_SESSION_SECRET') ? CHAT_SESSION_SECRET : '';
    if (empty($secret)) {
        return '';
    }

    $session_id = 'sess_' . bin2hex(random_bytes(8));
    $exp = time() + $ttl;
    $payload = "{$user_id}:{$session_id}:{$exp}";
    $signature = hash_hmac('sha256', $payload, $secret);

    return "{$payload}:{$signature}";
}
```

#### Step C: Inject the Token into the Chat Frontend Script
When enqueuing your chat widget JavaScript, pass the session token:

```php
add_action('wp_enqueue_scripts', function() {
    // Only enqueue on pages displaying the AI chat
    if (is_page('ai-relationship-assistant') || is_page('chat')) {
        wp_enqueue_script('dsh-chat-widget', get_stylesheet_directory_uri() . '/js/chat-widget.js', [], '1.0', true);

        wp_localize_script('dsh-chat-widget', 'DSH_CHAT_CONFIG', [
            'api_url'       => 'https://agent.doctorsarahhensley.com',
            'session_token' => dsh_generate_chat_token(),
            'user_id'       => is_user_logged_in() ? (string)get_current_user_id() : '',
        ]);
    }
});
```

#### Step D: Update the Frontend `fetch()` Call
In your frontend JavaScript (`chat-widget.js`), pass the token in the `Authorization` header:

```javascript
const response = await fetch(`${DSH_CHAT_CONFIG.api_url}/chat/stream`, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${DSH_CHAT_CONFIG.session_token}`
    },
    body: JSON.stringify({
        session_id: activeSessionId,
        user_id: DSH_CHAT_CONFIG.user_id,
        message: userQuery,
        mode: 'clinical' // or 'sales'
    })
});
```

---

## 4. Shared Credentials Summary

Before switching to strict production mode, the following 4 values must be agreed upon between WordPress and DSH-RAG:

| Variable Name | Stored In WordPress | Stored In DSH-RAG (`.env`) | Purpose |
|---|---|---|---|
| `WC_WEBHOOK_SECRET` | WooCommerce Settings $\rightarrow$ Webhooks | `WC_WEBHOOK_SECRET` | Validates WooCommerce order creation webhooks. |
| `CHAT_SESSION_SECRET` | `wp-config.php` | `CHAT_SESSION_SECRET` | Signs and verifies user chat tokens. |
| `WORDPRESS_APP_PASSWORD`| Users $\rightarrow$ Application Passwords | `WORDPRESS_APP_PASSWORD` | Allows nightly ETL script to pull past orders. |
| `ALLOWED_ORIGINS` | `https://doctorsarahhensley.com` | `ALLOWED_ORIGINS` | Whitelists WordPress domain for browser CORS. |

---

## 5. Support & Rollout Verification

* **Staging Mode (Zero Risk):** The DSH-RAG backend is currently running with `ENFORCE_CHAT_AUTH=false`. This means WordPress can deploy the token generator and test it without breaking current chat sessions.
* **Live Test Command:** Once configured, WordPress can send a test ping from **WooCommerce $\rightarrow$ Webhooks $\rightarrow$ Send Ping**. A successful response returns:
  ```json
  {"status": "success", "message": "Webhook ping verified successfully"}
  ```
* **Full Lockdown:** Once the WordPress developer confirms tokens are sending with chat queries, the DSH-RAG team will switch `ENFORCE_CHAT_AUTH=true` in `.env` to complete full bot defense.
