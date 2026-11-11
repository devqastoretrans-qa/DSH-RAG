import React, { useMemo, useState } from 'react';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';
import { marked } from 'marked';
import {
  AlertCircle,
  Bot,
  Briefcase,
  Check,
  Copy,
  Database,
  Sparkles,
  User,
} from 'lucide-react';
import type { ChatMessage as ChatMessageType } from '../types/chat';
import { SourceAccordion } from './SourceAccordion';

export interface ChatMessageProps {
  message: ChatMessageType;
  userInitials?: string;
}

interface ContentSegment {
  type: 'markdown' | 'code';
  content: string;
  language?: string;
}

function splitMarkdownAndCode(raw: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  const fenceRegex = /```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null = null;

  while ((match = fenceRegex.exec(raw)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: 'markdown',
        content: raw.slice(lastIndex, match.index),
      });
    }
    segments.push({
      type: 'code',
      language: (match[1] || 'text').toLowerCase(),
      content: match[2].replace(/\n$/, ''),
    });
    lastIndex = fenceRegex.lastIndex;
  }

  if (lastIndex < raw.length) {
    segments.push({
      type: 'markdown',
      content: raw.slice(lastIndex),
    });
  }

  return segments.length > 0 ? segments : [{ type: 'markdown', content: raw }];
}

const CodeBlock: React.FC<{ code: string; language: string }> = ({
  code,
  language,
}) => {
  const [copied, setCopied] = useState(false);

  const highlightedHtml = useMemo(() => {
    try {
      if (language && hljs.getLanguage(language)) {
        return hljs.highlight(code, { language }).value;
      }
      return hljs.highlightAuto(code).value;
    } catch {
      return code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }
  }, [code, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="uppercase tracking-wider">{language || 'code'}</span>
        <button type="button" onClick={handleCopy} className="code-copy-btn">
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy Code</span>
            </>
          )}
        </button>
      </div>
      <pre className="code-block-pre">
        <code
          className={`hljs language-${language}`}
          dangerouslySetInnerHTML={{
            __html: DOMPurify.sanitize(highlightedHtml, {
              ALLOWED_TAGS: ['span'],
              ALLOWED_ATTR: ['class'],
            }),
          }}
        />
      </pre>
    </div>
  );
};

function renderSafeMarkdownHtml(markdown: string): string {
  const rawHtml = marked.parse(markdown || '', { async: false }) as string;
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: [
      'p',
      'br',
      'strong',
      'em',
      'u',
      's',
      'b',
      'i',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'ul',
      'ol',
      'li',
      'blockquote',
      'code',
      'hr',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
      'span',
      'a',
    ],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'title'],
  });
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  userInitials = 'U',
}) => {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isSales = message.mode === 'sales';

  const segments = useMemo(
    () => (isUser ? [] : splitMarkdownAndCode(message.content || '')),
    [isUser, message.content]
  );

  const timeLabel = useMemo(() => {
    const ms =
      message.createdAt > 1e12 ? message.createdAt : message.createdAt * 1000;
    return new Date(ms).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
  }, [message.createdAt]);

  if (isSystem) {
    return (
      <div className="mx-auto flex w-full max-w-3xl items-start gap-3 rounded-xl border border-sky-500/25 bg-sky-500/10 px-4 py-3 text-xs text-sky-800 dark:text-sky-200">
        <Database className="mt-0.5 h-4 w-4 shrink-0 text-sky-500" />
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[11px] font-semibold uppercase tracking-wide text-sky-600 dark:text-sky-300">
            System / Retrieval Context
          </div>
          <p className="mt-1 leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="mx-auto flex w-full max-w-3xl justify-end gap-3">
        <div className="flex max-w-[85%] flex-col items-end sm:max-w-[75%]">
          <div className="rounded-2xl rounded-tr-sm border border-amber-500/25 bg-gradient-to-br from-amber-500/15 to-amber-600/10 px-4 py-3 text-sm leading-relaxed text-slate-900 shadow-sm dark:border-amber-400/25 dark:from-amber-400/15 dark:to-amber-500/10 dark:text-slate-100">
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </div>
          <span className="mt-1 px-1 font-mono text-[11px] text-slate-400 dark:text-slate-500">
            You • {timeLabel}
          </span>
        </div>
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/15 text-xs font-semibold text-amber-700 dark:text-amber-300"
          title="User"
        >
          {userInitials || <User className="h-4 w-4" />}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl items-start gap-3">
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border shadow-sm ${
          isSales
            ? 'border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-300'
            : 'border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
        }`}
        title={isSales ? 'Program Advisor Assistant' : 'Clinical Educator Assistant'}
      >
        {isSales ? (
          <Briefcase className="h-4 w-4" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div
          className={`rounded-2xl rounded-tl-sm border px-4 py-3.5 shadow-sm ${
            message.isError
              ? 'border-rose-500/35 bg-rose-500/10 text-rose-800 dark:text-rose-200'
              : 'border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-[#131E32] dark:text-slate-100'
          }`}
        >
          {message.isError && (
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400">
              <AlertCircle className="h-4 w-4" />
              <span>Generation Notice</span>
            </div>
          )}

          <div className="markdown-body">
            {segments.map((seg, idx) =>
              seg.type === 'code' ? (
                <CodeBlock
                  key={`code-${idx}`}
                  code={seg.content}
                  language={seg.language || 'text'}
                />
              ) : (
                <div
                  key={`md-${idx}`}
                  dangerouslySetInnerHTML={{
                    __html: renderSafeMarkdownHtml(seg.content),
                  }}
                />
              )
            )}

            {message.isStreaming && (
              <span className="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-emerald-500 align-middle" />
            )}
          </div>

          {message.recommendedProducts &&
            message.recommendedProducts.length > 0 && (
              <div className="mt-3 grid gap-2">
                {message.recommendedProducts.map((prod, idx) => (
                  <div
                    key={`prod-${idx}`}
                    className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-sm font-semibold text-amber-800 dark:text-amber-300">
                        <Sparkles className="h-4 w-4" />
                        {prod.name || prod.title || 'Recommended Program'}
                      </span>
                      {prod.price && (
                        <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 font-mono text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                          {prod.price}
                        </span>
                      )}
                    </div>
                    {prod.description && (
                      <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                        {prod.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

          {message.retrievalContextSummary && (
            <div className="mt-2.5 rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-600 dark:border-slate-700/60 dark:bg-slate-900/60 dark:text-slate-300">
              Context Retrieved: {message.retrievalContextSummary}
            </div>
          )}

          {message.sources && message.sources.length > 0 && (
            <SourceAccordion sources={message.sources} mode={message.mode} />
          )}
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-2 px-1 font-mono text-[11px] text-slate-400 dark:text-slate-500">
          <span
            className={
              isSales
                ? 'text-amber-600 dark:text-amber-400'
                : 'text-emerald-600 dark:text-emerald-400'
            }
          >
            {isSales ? 'Program Advisor' : 'Clinical Educator'}
          </span>
          <span>•</span>
          <span>{timeLabel}</span>
          {message.cached && (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-600 dark:text-amber-300">
              Cached
            </span>
          )}
          {message.latencySec && <span>• {message.latencySec}s</span>}
          {message.isStopped && (
            <span className="rounded bg-slate-500/20 px-1.5 py-0.5 text-[10px]">
              Stopped
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

