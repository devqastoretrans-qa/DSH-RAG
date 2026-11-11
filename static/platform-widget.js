(function () {
  "use strict";

  if (window.__dshPlatformWidgetLoaded) return;
  window.__dshPlatformWidgetLoaded = true;

  var scriptEl = document.currentScript || (function () {
    var scripts = document.getElementsByTagName("script");
    for (var i = scripts.length - 1; i >= 0; i--) {
      if (scripts[i].src && scripts[i].src.indexOf("platform-widget.js") !== -1) {
        return scripts[i];
      }
    }
    return null;
  })();

  var userCfg = window.DSH_PLATFORM_WIDGET_CONFIG || {};
  var detectedOrigin = "";
  if (scriptEl && scriptEl.src) {
    try {
      detectedOrigin = new URL(scriptEl.src, window.location.href).origin;
    } catch (_) {
      detectedOrigin = "";
    }
  }

  var apiBase = (
    userCfg.apiUrl ||
    (scriptEl && scriptEl.getAttribute("data-api-url")) ||
    detectedOrigin ||
    window.location.origin
  ).replace(/\/+$/, "");

  var openByDefault = Boolean(
    userCfg.openByDefault ||
    (scriptEl && scriptEl.getAttribute("data-open") === "true")
  );

  var SID_KEY = "dsh_platform_widget_sid";
  function createSessionId() {
    var rand = Math.random().toString(36).slice(2, 12);
    return "plat_" + Date.now().toString(36) + "_" + rand;
  }
  function getSessionId() {
    try {
      var existing = sessionStorage.getItem(SID_KEY);
      if (existing && existing.trim()) return existing.trim();
      var fresh = createSessionId();
      sessionStorage.setItem(SID_KEY, fresh);
      return fresh;
    } catch (_) {
      return createSessionId();
    }
  }
  function resetSessionId() {
    var fresh = createSessionId();
    try {
      sessionStorage.setItem(SID_KEY, fresh);
    } catch (_) {}
    return fresh;
  }

  var sessionId = getSessionId();
  var isOpen = openByDefault;
  var isSending = false;

  var host = document.createElement("div");
  host.id = "dsh-platform-bot-host";
  document.body.appendChild(host);

  var shadow = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

  var styles = document.createElement("style");
  styles.textContent = [
    ":host { all: initial; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Inter, sans-serif; }",
    ".dsh-wrap { position: fixed; right: 20px; bottom: 20px; z-index: 2147483000; display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }",
    ".dsh-launcher { display: inline-flex; align-items: center; gap: 10px; border: 1px solid rgba(16,185,129,0.45); background: linear-gradient(135deg, #0f172a 0%, #064e3b 100%); color: #f8fafc; border-radius: 9999px; padding: 11px 18px; font-size: 13.5px; font-weight: 600; cursor: pointer; box-shadow: 0 12px 30px rgba(2,6,23,0.42); transition: transform .15s ease, box-shadow .15s ease; }",
    ".dsh-launcher:hover { transform: translateY(-2px); box-shadow: 0 16px 36px rgba(2,6,23,0.52); }",
    ".dsh-dot { width: 9px; height: 9px; border-radius: 9999px; background: #34d399; box-shadow: 0 0 0 3px rgba(52,211,153,0.25); }",
    ".dsh-panel { width: 380px; max-width: calc(100vw - 24px); height: 530px; max-height: calc(100vh - 96px); background: #0b1120; color: #e2e8f0; border: 1px solid #1e293b; border-radius: 18px; box-shadow: 0 24px 60px rgba(2,6,23,0.62); display: none; flex-direction: column; overflow: hidden; }",
    ".dsh-panel.open { display: flex; }",
    ".dsh-header { display: flex; align-items: center; justify-content: space-between; padding: 13px 15px; background: linear-gradient(135deg, #0f172a 0%, #064e3b 100%); border-bottom: 1px solid rgba(148,163,184,0.16); }",
    ".dsh-title-group { display: flex; align-items: center; gap: 10px; }",
    ".dsh-avatar { width: 32px; height: 32px; border-radius: 10px; background: rgba(16,185,129,0.18); border: 1px solid rgba(52,211,153,0.35); color: #6ee7b7; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }",
    ".dsh-title { font-size: 14px; font-weight: 700; color: #f8fafc; line-height: 1.2; }",
    ".dsh-subtitle { font-size: 11px; color: #a7f3d0; margin-top: 2px; }",
    ".dsh-actions { display: flex; align-items: center; gap: 6px; }",
    ".dsh-icon-btn { border: 1px solid rgba(148,163,184,0.22); background: rgba(15,23,42,0.5); color: #cbd5e1; border-radius: 8px; padding: 5px 9px; font-size: 11px; cursor: pointer; }",
    ".dsh-icon-btn:hover { background: rgba(30,41,59,0.9); color: #fff; }",
    ".dsh-body { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; background: #0b1120; }",
    ".dsh-msg { max-width: 88%; padding: 10px 13px; border-radius: 14px; font-size: 13px; line-height: 1.5; word-break: break-word; }",
    ".dsh-msg.bot { align-self: flex-start; background: #131c31; border: 1px solid #1e293b; color: #e2e8f0; border-bottom-left-radius: 4px; }",
    ".dsh-msg.bot p { margin: 0 0 8px 0; } .dsh-msg.bot p:last-child { margin-bottom: 0; }",
    ".dsh-msg.bot ol, .dsh-msg.bot ul { margin: 4px 0 8px 0; padding-left: 18px; } .dsh-msg.bot li { margin-bottom: 3px; }",
    ".dsh-msg.bot a { color: #34d399; text-decoration: underline; }",
    ".dsh-msg.user { align-self: flex-end; background: #059669; color: #ffffff; border-bottom-right-radius: 4px; }",
    ".dsh-quick { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 14px 10px 14px; background: #0b1120; }",
    ".dsh-chip { border: 1px solid #1e293b; background: #131c31; color: #a7f3d0; border-radius: 9999px; padding: 6px 10px; font-size: 11.5px; cursor: pointer; text-align: left; transition: border-color .15s; }",
    ".dsh-chip:hover { border-color: #10b981; background: #16243d; }",
    ".dsh-footer { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid #1e293b; background: #0f172a; }",
    ".dsh-input { flex: 1; background: #131c31; color: #f8fafc; border: 1px solid #334155; border-radius: 10px; padding: 9px 11px; font-size: 13px; outline: none; font-family: inherit; }",
    ".dsh-input:focus { border-color: #10b981; }",
    ".dsh-send { background: #10b981; color: #052e16; border: none; border-radius: 10px; padding: 0 14px; font-size: 13px; font-weight: 700; cursor: pointer; }",
    ".dsh-send:disabled { opacity: 0.55; cursor: not-allowed; }",
    ".dsh-note { text-align: center; font-size: 10.5px; color: #64748b; padding: 4px 10px 7px; background: #0f172a; }"
  ].join("\n");

  var wrap = document.createElement("div");
  wrap.className = "dsh-wrap";

  var panel = document.createElement("section");
  panel.className = "dsh-panel" + (isOpen ? " open" : "");
  panel.setAttribute("aria-label", "Platform Navigation Assistant");

  panel.innerHTML = [
    "<div class='dsh-header'>",
    "  <div class='dsh-title-group'>",
    "    <div class='dsh-avatar' aria-hidden='true'>",
    "      <svg width='17' height='17' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'></circle><path d='M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3'></path><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>",
    "    </div>",
    "    <div>",
    "      <div class='dsh-title'>Platform Help Assistant</div>",
    "      <div class='dsh-subtitle'>Website, Login, Portal & Billing Guide</div>",
    "    </div>",
    "  </div>",
    "  <div class='dsh-actions'>",
    "    <button type='button' class='dsh-icon-btn' data-action='reset' title='New conversation'>New</button>",
    "    <button type='button' class='dsh-icon-btn' data-action='close' aria-label='Close'>&#10005;</button>",
    "  </div>",
    "</div>",
    "<div class='dsh-body' data-role='messages'></div>",
    "<div class='dsh-quick' data-role='quick'>",
    "  <button type='button' class='dsh-chip' data-q='How do I log into my account?'>How do I log in?</button>",
    "  <button type='button' class='dsh-chip' data-q='How do I reset a forgotten password?'>Forgot password</button>",
    "  <button type='button' class='dsh-chip' data-q='Where do I find my course dashboard and download workbooks?'>Course & workbooks</button>",
    "  <button type='button' class='dsh-chip' data-q='How do I check my billing receipts or contact support?'>Billing & support</button>",
    "</div>",
    "<form class='dsh-footer' data-role='form'>",
    "  <input class='dsh-input' data-role='input' type='text' maxlength='1000' placeholder='Ask about login, courses, downloads, billing...' autocomplete='off' />",
    "  <button class='dsh-send' data-role='send' type='submit'>Send</button>",
    "</form>",
    "<div class='dsh-note'>Dedicated Platform Guide &bull; Answers strictly from portal docs</div>"
  ].join("");

  var launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "dsh-launcher";
  launcher.setAttribute("aria-label", "Open Platform Help Assistant");
  launcher.innerHTML = "<span class='dsh-dot'></span><span>Platform Help</span>";

  wrap.appendChild(panel);
  wrap.appendChild(launcher);
  shadow.appendChild(styles);
  shadow.appendChild(wrap);

  var msgContainer = panel.querySelector("[data-role='messages']");
  var quickContainer = panel.querySelector("[data-role='quick']");
  var formEl = panel.querySelector("[data-role='form']");
  var inputEl = panel.querySelector("[data-role='input']");
  var sendBtn = panel.querySelector("[data-role='send']");

  function renderWelcome() {
    msgContainer.innerHTML = "";
    appendMessage(
      "bot",
      "Welcome! I'm your **Platform Navigation Assistant**.\n\nAsk me how to sign in, reset your password, find your course dashboard or workbooks, manage billing, or reach support."
    );
    quickContainer.style.display = "flex";
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatSafeText(text) {
    var html = escapeHtml(text || "");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(
      /(https?:\/\/[^\s<]+)/g,
      "<a href='$1' target='_blank' rel='noopener noreferrer'>$1</a>"
    );
    return html.replace(/\n\n/g, "<br><br>").replace(/\n/g, "<br>");
  }

  function appendMessage(role, content, isHtml) {
    var el = document.createElement("div");
    el.className = "dsh-msg " + role;
    if (role === "bot" && isHtml && typeof content === "string") {
      el.innerHTML = content;
    } else if (role === "bot") {
      el.innerHTML = formatSafeText(content);
    } else {
      el.textContent = content;
    }
    msgContainer.appendChild(el);
    msgContainer.scrollTop = msgContainer.scrollHeight;
    return el;
  }

  function setOpen(nextOpen) {
    isOpen = nextOpen;
    if (isOpen) {
      panel.classList.add("open");
      setTimeout(function () {
        inputEl.focus();
      }, 40);
    } else {
      panel.classList.remove("open");
    }
  }

  async function sendQuestion(text) {
    var clean = (text || "").trim();
    if (!clean || isSending) return;

    isSending = true;
    sendBtn.disabled = true;
    quickContainer.style.display = "none";
    appendMessage("user", clean, false);
    inputEl.value = "";

    var typingEl = appendMessage("bot", "Looking up platform guide...", false);

    try {
      var headers = { "Content-Type": "application/json" };
      var activeToken = userCfg.sessionToken || (scriptEl && scriptEl.getAttribute("data-token"));
      if (activeToken) {
        headers["Authorization"] = "Bearer " + activeToken;
      }

      var res = await fetch(apiBase + "/api/platform-widget/chat", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          session_id: sessionId,
          message: clean
        })
      });

      var data = await res.json().catch(function () { return {}; });
      if (!res.ok || data.success === false) {
        throw new Error(data.error || data.detail || ("Request failed (" + res.status + ")"));
      }

      if (data.session_id) {
        sessionId = data.session_id;
        try { sessionStorage.setItem(SID_KEY, sessionId); } catch (_) {}
      }

      typingEl.remove();
      if (data.answer_html) {
        appendMessage("bot", data.answer_html, true);
      } else {
        appendMessage("bot", data.answer || "No guidance returned.", false);
      }
    } catch (err) {
      typingEl.remove();
      appendMessage("bot", "Unable to reach the platform assistant right now: " + (err && err.message ? err.message : "Unknown error"), false);
    } finally {
      isSending = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  launcher.addEventListener("click", function () {
    setOpen(!isOpen);
  });

  panel.addEventListener("click", function (ev) {
    var target = ev.target;
    if (!target || !target.getAttribute) return;
    var action = target.getAttribute("data-action");
    if (action === "close") {
      setOpen(false);
    } else if (action === "reset") {
      sessionId = resetSessionId();
      renderWelcome();
    } else if (target.getAttribute("data-q")) {
      void sendQuestion(target.getAttribute("data-q"));
    }
  });

  formEl.addEventListener("submit", function (ev) {
    ev.preventDefault();
    void sendQuestion(inputEl.value);
  });

  renderWelcome();
})();

