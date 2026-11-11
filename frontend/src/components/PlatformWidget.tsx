import React, { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { HelpCircle, RotateCcw, Send, X } from 'lucide-react';

interface WidgetMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  html?: string;
}

export interface PlatformWidgetProps {
  authToken?: string;
}

const STORAGE_SID_KEY = 'dsh_platform_widget_sid';

const QUICK_QUESTIONS = [
  'How do I log into my account?',
  'How do I reset a forgotten password?',
  'Where do I find my course dashboard and download workbooks?',
  'How do I view billing receipts or contact support?',
];

function createWidgetSessionId(): string {
  const rand =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
      : Math.random().toString(36).slice(2, 14);
  return `plat_${rand}`;
}

function getOrCreateWidgetSessionId(): string {
  try {
    const existing = sessionStorage.getItem(STORAGE_SID_KEY);
    if (existing && existing.trim()) return existing.trim();
    const fresh = createWidgetSessionId();
    sessionStorage.setItem(STORAGE_SID_KEY, fresh);
    return fresh;
  } catch {
    return createWidgetSessionId();
  }
}

export const PlatformWidget: React.FC<PlatformWidgetProps> = ({ authToken }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() =>
    getOrCreateWidgetSessionId()
  );
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: "Welcome! I'm the dedicated **Platform Help Assistant**.\n\nAsk me how to sign in, reset your password, find your course dashboard or workbooks, update billing, or contact support.",
    },
  ]);
  const [draft, setDraft] = useState('');
  const [isSending, setIsSending] = useState(false);

  const listRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, isOpen]);

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [isOpen]);

  const handleReset = () => {
    const fresh = createWidgetSessionId();
    try {
      sessionStorage.setItem(STORAGE_SID_KEY, fresh);
    } catch {
      // ignore
    }
    setSessionId(fresh);
    setMessages([
      {
        id: `welcome_${Date.now()}`,
        role: 'assistant',
        text: "Started a fresh Platform Help session. What can I help you find on the website or learning portal?",
      },
    ]);
  };

  const sendQuestion = async (rawText: string) => {
    const clean = rawText.trim();
    if (!clean || isSending) return;

    const userMsg: WidgetMessage = {
      id: `u_${Date.now()}`,
      role: 'user',
      text: clean,
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft('');
    setIsSending(true);

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (authToken) {
        headers.Authorization = `Bearer ${authToken}`;
      }

      const res = await fetch('/api/platform-widget/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          session_id: sessionId,
          message: clean,
        }),
      });

      const data = (await res.json().catch(() => ({}))) as {
        success?: boolean;
        session_id?: string;
        answer?: string;
        answer_html?: string;
        error?: string;
        detail?: string;
      };

      if (!res.ok || data.success === false) {
        throw new Error(
          data.error || data.detail || `Request failed (${res.status})`
        );
      }

      if (data.session_id) {
        setSessionId(data.session_id);
        try {
          sessionStorage.setItem(STORAGE_SID_KEY, data.session_id);
        } catch {
          // ignore
        }
      }

      const sanitizedHtml = data.answer_html
        ? DOMPurify.sanitize(data.answer_html, {
            ALLOWED_TAGS: [
              'p',
              'br',
              'strong',
              'em',
              'b',
              'i',
              'ul',
              'ol',
              'li',
              'a',
              'code',
              'pre',
              'h3',
              'h4',
              'blockquote',
            ],
            ALLOWED_ATTR: ['href', 'target', 'rel'],
          })
        : undefined;

      setMessages((prev) => [
        ...prev,
        {
          id: `b_${Date.now()}`,
          role: 'assistant',
          text: data.answer || 'No guidance returned.',
          html: sanitizedHtml,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unable to connect';
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: 'assistant',
          text: `Sorry, I couldn't reach the Platform Help service (${msg}).`,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void sendQuestion(draft);
  };

  return (
    <div className="fixed bottom-24 right-4 z-40 flex flex-col items-end gap-3 sm:bottom-5 sm:right-5">
      {isOpen && (
        <section
          aria-label="Platform Help Assistant"
          className="flex h-[510px] max-h-[calc(100vh-120px)] w-[370px] max-w-[calc(100vw-24px)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700/80 dark:bg-[#0B1120]"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-emerald-500/20 bg-gradient-to-r from-slate-900 to-emerald-950 px-4 py-3 text-white">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-emerald-400/35 bg-emerald-500/20 text-emerald-300">
                <HelpCircle className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-semibold leading-tight">
                  Platform Help Bot
                </div>
                <div className="text-[11px] text-emerald-200/80">
                  Website, Login, Portal & Billing
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleReset}
                title="New platform conversation"
                className="rounded-lg border border-white/15 bg-white/10 p-1.5 text-slate-200 transition-colors hover:bg-white/20"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                aria-label="Close Platform Help"
                className="rounded-lg border border-white/15 bg-white/10 p-1.5 text-slate-200 transition-colors hover:bg-white/20"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div
            ref={listRef}
            className="flex-1 space-y-3 overflow-y-auto bg-slate-50 px-3.5 py-3.5 dark:bg-[#0B1120]"
          >
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${
                  m.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                    m.role === 'user'
                      ? 'rounded-br-sm bg-emerald-600 text-white'
                      : 'rounded-bl-sm border border-slate-200 bg-white text-slate-800 shadow-sm dark:border-slate-800 dark:bg-[#131C31] dark:text-slate-100 [&_a]:text-emerald-600 [&_a]:underline dark:[&_a]:text-emerald-400 [&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-1.5 [&_p:last-child]:mb-0 [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5'
                  }`}
                >
                  {m.role === 'assistant' && m.html ? (
                    <div dangerouslySetInnerHTML={{ __html: m.html }} />
                  ) : (
                    <div className="whitespace-pre-wrap">{m.text}</div>
                  )}
                </div>
              </div>
            ))}

            {isSending && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-500 dark:border-slate-800 dark:bg-[#131C31] dark:text-slate-400">
                  Checking platform guide...
                </div>
              </div>
            )}
          </div>

          {/* Starter Quick Prompts */}
          {messages.length <= 1 && (
            <div className="flex flex-wrap gap-1.5 border-t border-slate-200/70 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-[#0B1120]">
              {QUICK_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  disabled={isSending}
                  onClick={() => void sendQuestion(q)}
                  className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-700 transition-colors hover:bg-emerald-500/20 disabled:opacity-50 dark:text-emerald-300"
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 border-t border-slate-200 bg-white px-3 py-2.5 dark:border-slate-800 dark:bg-slate-900"
          >
            <input
              ref={inputRef}
              type="text"
              maxLength={1000}
              value={draft}
              disabled={isSending}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask about login, courses, billing..."
              className="flex-1 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-[#131C31] dark:text-slate-100"
            />
            <button
              type="submit"
              disabled={!draft.trim() || isSending}
              aria-label="Send platform question"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </form>
        </section>
      )}

      {/* Floating Bottom-Right Launcher */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label={isOpen ? 'Minimize Platform Help' : 'Open Platform Help'}
        className="inline-flex items-center gap-2 rounded-full border border-emerald-400/40 bg-gradient-to-r from-slate-900 to-emerald-900 px-4 py-2.5 text-xs font-semibold text-white shadow-xl transition-transform hover:-translate-y-0.5 hover:shadow-2xl"
      >
        <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_0_3px_rgba(52,211,153,0.25)]" />
        <HelpCircle className="h-4 w-4 text-emerald-300" />
        <span>{isOpen ? 'Hide Platform Help' : 'Platform Help'}</span>
      </button>
    </div>
  );
};

