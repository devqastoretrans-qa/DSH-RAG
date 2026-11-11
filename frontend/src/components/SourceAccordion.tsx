import React, { useMemo, useState } from 'react';
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
} from 'lucide-react';
import type { BotMode, SourceCitation } from '../types/chat';

export interface SourceAccordionProps {
  sources?: SourceCitation[] | null;
  mode?: BotMode;
  defaultOpen?: boolean;
  label?: string;
}

function isSafeHttpUrl(url?: string | null): url is string {
  if (!url || typeof url !== 'string') return false;
  return /^https?:\/\//i.test(url.trim());
}

export const SourceAccordion: React.FC<SourceAccordionProps> = ({
  sources,
  mode = 'generic',
  defaultOpen = false,
  label,
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [expandedItems, setExpandedItems] = useState<Record<number, boolean>>({});

  const validSources = useMemo(() => {
    if (!Array.isArray(sources)) return [];
    return sources.filter(
      (s): s is SourceCitation => Boolean(s && typeof s === 'object')
    );
  }, [sources]);

  if (validSources.length === 0) {
    return null;
  }

  const accentClasses =
    mode === 'sales'
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/15'
      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/15';

  return (
    <div className="mt-3 min-w-0 max-w-full">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${accentClasses}`}
        aria-expanded={isOpen}
      >
        <BookOpen className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">
          {label ||
            `Sources (${validSources.length} Context Chunk${
              validSources.length === 1 ? '' : 's'
            } Retrieved)`}
        </span>
        {isOpen ? (
          <ChevronUp className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        )}
      </button>

      {isOpen && (
        <div className="mt-2.5 grid max-h-72 grid-cols-1 gap-2 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50/90 p-3 dark:border-slate-700/70 dark:bg-slate-900/70">
          {validSources.map((src, index) => {
            const rawScore = src.relevance_score;
            const scorePct =
              typeof rawScore === 'number' && Number.isFinite(rawScore)
                ? `${Math.round(rawScore <= 1 ? rawScore * 100 : rawScore)}% match`
                : null;

            const snippet = (src.snippet || src.text || '').trim();
            const isLongSnippet = snippet.length > 220;
            const isItemExpanded = Boolean(expandedItems[index]);
            const safeUrl = isSafeHttpUrl(src.url) ? src.url.trim() : null;

            return (
              <div
                key={`${src.document || 'doc'}-${index}`}
                className="min-w-0 max-w-full overflow-hidden rounded-lg border border-slate-200/80 bg-white px-3 py-2 text-xs shadow-sm dark:border-slate-800 dark:bg-slate-950/60"
              >
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-1 items-center gap-1.5 font-medium text-slate-800 dark:text-slate-200">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    <span
                      className="min-w-0 break-all font-medium"
                      title={src.document || 'Knowledge Document'}
                    >
                      {src.document || 'Knowledge Document'}
                    </span>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                    {src.page !== undefined &&
                      src.page !== null &&
                      String(src.page).trim() !== '' && (
                        <span>p. {src.page}</span>
                      )}
                    {src.chunk_id !== undefined &&
                      src.chunk_id !== null &&
                      String(src.chunk_id).trim() !== '' && (
                        <span>chunk #{src.chunk_id}</span>
                      )}
                    {scorePct && (
                      <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-600 dark:text-emerald-400">
                        {scorePct}
                      </span>
                    )}
                  </div>
                </div>

                {safeUrl && (
                  <a
                    href={safeUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-flex max-w-full items-center gap-1 break-all text-[11px] text-sky-600 underline hover:text-sky-500 dark:text-sky-400"
                  >
                    <span className="break-all">{safeUrl}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                )}

                {snippet && (
                  <div className="mt-1.5 min-w-0">
                    <p
                      className={`break-words [overflow-wrap:anywhere] text-[11px] leading-relaxed text-slate-600 dark:text-slate-400 ${
                        isItemExpanded ? '' : 'line-clamp-3'
                      }`}
                    >
                      {snippet}
                    </p>
                    {isLongSnippet && (
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedItems((prev) => ({
                            ...prev,
                            [index]: !prev[index],
                          }))
                        }
                        className="mt-1 text-[10px] font-semibold text-emerald-600 hover:underline dark:text-emerald-400"
                      >
                        {isItemExpanded ? 'Show less' : 'Show full excerpt'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
