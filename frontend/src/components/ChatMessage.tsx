import React, { useMemo, useState } from 'react';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';
import katex from 'katex';
import { marked } from 'marked';
import {
  AlertCircle,
  Bot,
  Briefcase,
  Check,
  ChevronDown,
  ChevronUp,
  Compass,
  Copy,
  Crown,
  Database,
  RotateCcw,
  Sparkles,
  User,
} from 'lucide-react';
import type { ChatMessage as ChatMessageType } from '../types/chat';
import { AudioPlayerBar } from './AudioPlayerBar';
import { SourceAccordion } from './SourceAccordion';

export interface ChatMessageProps {
  message: ChatMessageType;
  userInitials?: string;
  onRetry?: (message: ChatMessageType) => void;
  buildAuthHeaders?: (tokenOverride?: string, extra?: Record<string, string>) => Record<string, string>;
  autoPlayAudio?: boolean;
  onAudioError?: (detail: string) => void;
}

interface ContentSegment {
  type: 'markdown' | 'code';
  content: string;
  language?: string;
}

const USER_LONG_MESSAGE_THRESHOLD = 1800;

/**
 * Splits markdown prose and fenced code blocks while respecting nested fence lengths
 * (e.g., ``` blocks nested inside ```` fences), CRLF line endings, and unclosed streaming fences.
 */
export function splitMarkdownAndCode(raw: string): ContentSegment[] {
  if (!raw) return [{ type: 'markdown', content: '' }];

  const normalized = raw.replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');
  const segments: ContentSegment[] = [];
  let proseLines: string[] = [];
  let codeLines: string[] = [];
  let inCode = false;
  let fenceLen = 3;
  let fenceLang = 'text';

  const flushProse = () => {
    if (proseLines.length > 0) {
      segments.push({ type: 'markdown', content: proseLines.join('\n') });
      proseLines = [];
    }
  };

  for (const line of lines) {
    const trimmedStart = line.trimStart();
    if (!inCode) {
      const openMatch = trimmedStart.match(/^(`{3,})([a-zA-Z0-9_+-]*)\s*$/);
      if (openMatch) {
        flushProse();
        inCode = true;
        fenceLen = openMatch[1].length;
        fenceLang = (openMatch[2] || 'text').toLowerCase();
        codeLines = [];
        continue;
      }
      proseLines.push(line);
    } else {
      const closeMatch = trimmedStart.match(/^(`{3,})\s*$/);
      if (closeMatch && closeMatch[1].length >= fenceLen) {
        segments.push({
          type: 'code',
          language: fenceLang,
          content: codeLines.join('\n'),
        });
        inCode = false;
        codeLines = [];
        continue;
      }
      codeLines.push(line);
    }
  }

  if (inCode) {
    segments.push({
      type: 'code',
      language: fenceLang,
      content: codeLines.join('\n'),
    });
  } else {
    flushProse();
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
    <div className="code-block-wrapper max-w-full">
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

function renderLatexExpressions(markdown: string): {
  processed: string;
  placeholders: Map<string, string>;
} {
  const placeholders = new Map<string, string>();
  let counter = 0;

  const stashMath = (expr: string, displayMode: boolean): string => {
    const key = `KATEXPLACEHOLDER${counter++}ENDKATEX`;
    let rendered = '';
    try {
      rendered = katex.renderToString(expr.trim(), {
        displayMode,
        throwOnError: false,
        strict: false,
        trust: false,
      });
    } catch {
      rendered = expr
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }
    placeholders.set(key, rendered);
    return displayMode ? `\n\n${key}\n\n` : key;
  };

  // Display math: $$...$$ and \[...\]
  let out = markdown.replace(/\$\$([\s\S]+?)\$\$/g, (_, inner: string) =>
    stashMath(inner, true)
  );
  out = out.replace(/\\\[([\s\S]+?)\\\]/g, (_, inner: string) =>
    stashMath(inner, true)
  );

  // Explicit inline math: \(...\)
  out = out.replace(/\\\(([\s\S]+?)\\\)/g, (_, inner: string) =>
    stashMath(inner, false)
  );

  // Pandoc-style inline $...$ while preserving prices like "$97" and "$197"
  out = out.replace(
    /(^|[^\\$])\$(?!\s)([^$\n]+?[^\s$\\]|\S)\$(?!\d)/g,
    (full: string, prefix: string, inner: string) => {
      // Skip currency expressions like "$97 and $197" where inner starts with digits & lacks math ops
      if (/^\d/.test(inner) && !/[\\^_=+\-*/()]/.test(inner)) {
        return full;
      }
      return `${prefix}${stashMath(inner, false)}`;
    }
  );

  return { processed: out, placeholders };
}

export function renderSafeMarkdownHtml(markdown: string): string {
  const { processed, placeholders } = renderLatexExpressions(markdown || '');
  let rawHtml = marked.parse(processed, {
    async: false,
    gfm: true,
    breaks: true,
  }) as string;

  // Restore KaTeX HTML placeholders
  placeholders.forEach((renderedHtml, key) => {
    rawHtml = rawHtml.split(key).join(renderedHtml);
  });

  // Wrap tables inside horizontal scroll containers to protect mobile/card layout
  rawHtml = rawHtml
    .replace(/<table([\s\S]*?)>/gi, '<div class="table-scroll-wrapper"><table$1>')
    .replace(/<\/table>/gi, '</table></div>');

  const sanitized = DOMPurify.sanitize(rawHtml, {
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
      'pre',
      'hr',
      'div',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
      'span',
      'a',
      // Safe KaTeX MathML/HTML output tags
      'math',
      'semantics',
      'mrow',
      'mi',
      'mn',
      'mo',
      'msup',
      'msub',
      'mfrac',
      'msqrt',
      'mroot',
      'annotation',
    ],
    ALLOWED_ATTR: [
      'href',
      'target',
      'rel',
      'class',
      'title',
      'aria-hidden',
      'encoding',
      'xmlns',
      'style',
    ],
    FORBID_TAGS: [
      'script',
      'iframe',
      'object',
      'embed',
      'form',
      'input',
      'textarea',
      'button',
      'svg',
      'img',
      'style',
      'link',
      'meta',
    ],
    FORBID_ATTR: [
      'onerror',
      'onload',
      'onclick',
      'onmouseover',
      'onfocus',
      'onblur',
    ],
    ALLOW_DATA_ATTR: false,
  });

  // Enforce safe link attributes
  return sanitized.replace(
    /<a\b([^>]*?)>/gi,
    (_m, attrs: string) =>
      `<a${attrs.replace(/\s*(target|rel)="[^"]*"/gi, '')} target="_blank" rel="noopener noreferrer">`
  );
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  userInitials = 'U',
  onRetry,
  buildAuthHeaders,
  autoPlayAudio = false,
  onAudioError,
}) => {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isSales = message.mode === 'sales';
  const isPlatform = message.mode === 'platform';
  const isOwner = message.mode === 'owner';
  const [expandLongPrompt, setExpandLongPrompt] = useState(false);

  const segments = useMemo(
    () => (isUser ? [] : splitMarkdownAndCode(message.content || '')),
    [isUser, message.content]
  );

  const timeLabel = useMemo(() => {
    const rawTs = Number(message.createdAt) || Date.now();
    const ms = rawTs > 1e12 ? rawTs : rawTs * 1000;
    const d = new Date(ms);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], {
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
          <p className="mt-1 break-words [overflow-wrap:anywhere] leading-relaxed">
            {message.content}
          </p>
        </div>
      </div>
    );
  }

  if (isUser) {
    const rawContent = message.content || '';
    const isUltraLong = rawContent.length > USER_LONG_MESSAGE_THRESHOLD;
    const displayedUserText =
      isUltraLong && !expandLongPrompt
        ? `${rawContent.slice(0, 1200)}...`
        : rawContent;

    return (
      <div className="mx-auto flex w-full max-w-3xl justify-end gap-3">
        <div className="flex min-w-0 max-w-[85%] flex-col items-end sm:max-w-[75%]">
          <div className="max-w-full overflow-hidden rounded-2xl rounded-tr-sm border border-amber-500/25 bg-gradient-to-br from-amber-500/15 to-amber-600/10 px-4 py-3 text-sm leading-relaxed text-slate-900 shadow-sm dark:border-amber-400/25 dark:from-amber-400/15 dark:to-amber-500/10 dark:text-slate-100">
            <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {displayedUserText}
            </p>
            {isUltraLong && (
              <button
                type="button"
                onClick={() => setExpandLongPrompt((prev) => !prev)}
                className="mt-2 inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-800 hover:bg-amber-500/25 dark:text-amber-200"
              >
                {expandLongPrompt ? (
                  <>
                    <ChevronUp className="h-3 w-3" />
                    <span>Collapse prompt</span>
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3 w-3" />
                    <span>
                      Show full message ({rawContent.length.toLocaleString()}{' '}
                      chars)
                    </span>
                  </>
                )}
              </button>
            )}
          </div>
          <span className="mt-1 px-1 font-mono text-[11px] text-slate-400 dark:text-slate-500">
            You{timeLabel ? ` • ${timeLabel}` : ''}
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
            : isPlatform
            ? 'border-sky-500/30 bg-sky-500/15 text-sky-600 dark:text-sky-300'
            : isOwner
            ? 'border-violet-500/30 bg-violet-500/15 text-violet-600 dark:text-violet-300'
            : 'border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
        }`}
        title={
          isSales
            ? 'Program Advisor Assistant'
            : isPlatform
            ? 'Platform Navigation Assistant'
            : isOwner
            ? 'Owner Agent (Founder Voice)'
            : 'Clinical Educator Assistant'
        }
      >
        {isSales ? (
          <Briefcase className="h-4 w-4" />
        ) : isPlatform ? (
          <Compass className="h-4 w-4" />
        ) : isOwner ? (
          <Crown className="h-4 w-4" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div
          className={`max-w-full overflow-hidden rounded-2xl rounded-tl-sm border px-4 py-3.5 shadow-sm ${
            message.isError
              ? 'border-rose-500/35 bg-rose-500/10 text-rose-800 dark:text-rose-200'
              : 'border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-[#131E32] dark:text-slate-100'
          }`}
        >
          {message.isError && (
            <div className="mb-2 flex items-center justify-between gap-2 text-xs font-semibold text-rose-600 dark:text-rose-400">
              <div className="flex items-center gap-1.5">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>Generation Error</span>
              </div>
              {onRetry && message.retryPrompt && (
                <button
                  type="button"
                  onClick={() => onRetry(message)}
                  className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 bg-rose-500/15 px-2.5 py-1 text-[11px] font-semibold text-rose-700 transition-colors hover:bg-rose-500/25 dark:text-rose-200"
                >
                  <RotateCcw className="h-3 w-3" />
                  <span>Retry</span>
                </button>
              )}
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

          {Array.isArray(message.recommendedProducts) &&
            message.recommendedProducts.length > 0 && (
              <div className="mt-3 grid gap-2">
                {message.recommendedProducts.map((prod, idx) => (
                  <div
                    key={`prod-${idx}`}
                    className="min-w-0 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-amber-800 dark:text-amber-300">
                        <Sparkles className="h-4 w-4 shrink-0" />
                        <span className="truncate">
                          {prod.name || prod.title || 'Recommended Program'}
                        </span>
                      </span>
                      {prod.price && (
                        <span className="shrink-0 rounded-md bg-emerald-500/15 px-2 py-0.5 font-mono text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                          {prod.price}
                        </span>
                      )}
                    </div>
                    {prod.description && (
                      <p className="mt-1 break-words text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                        {prod.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

          {message.retrievalContextSummary && (
            <div className="mt-2.5 break-words rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-600 dark:border-slate-700/60 dark:bg-slate-900/60 dark:text-slate-300">
              Context Retrieved: {message.retrievalContextSummary}
            </div>
          )}

          {Array.isArray(message.sources) && message.sources.length > 0 && (
            <SourceAccordion sources={message.sources} mode={message.mode} />
          )}

          {!message.isStreaming &&
            !message.isError &&
            message.content.trim().length > 0 && (
              <AudioPlayerBar
                messageId={message.id}
                text={message.content}
                mode={message.mode}
                buildAuthHeaders={buildAuthHeaders}
                autoPlay={autoPlayAudio}
                onError={onAudioError}
              />
            )}
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-2 px-1 font-mono text-[11px] text-slate-400 dark:text-slate-500">
          <span
            className={
              isSales
                ? 'text-amber-600 dark:text-amber-400'
                : isPlatform
                ? 'text-sky-600 dark:text-sky-400'
                : isOwner
                ? 'text-violet-600 dark:text-violet-400'
                : 'text-emerald-600 dark:text-emerald-400'
            }
          >
            {isSales
              ? 'Program Advisor'
              : isPlatform
              ? 'Platform Help'
              : isOwner
              ? 'Owner Agent'
              : 'Clinical Educator'}
          </span>
          {timeLabel && (
            <>
              <span>•</span>
              <span>{timeLabel}</span>
            </>
          )}
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
