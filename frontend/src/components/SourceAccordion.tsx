import React, { useState } from 'react';
import { BookOpen, ChevronDown, ChevronUp, FileText } from 'lucide-react';
import type { BotMode, SourceCitation } from '../types/chat';

export interface SourceAccordionProps {
  sources: SourceCitation[];
  mode?: BotMode;
  defaultOpen?: boolean;
  label?: string;
}

export const SourceAccordion: React.FC<SourceAccordionProps> = ({
  sources,
  mode = 'generic',
  defaultOpen = false,
  label,
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (!sources || sources.length === 0) {
    return null;
  }

  const accentClasses =
    mode === 'sales'
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/15'
      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/15';

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${accentClasses}`}
        aria-expanded={isOpen}
      >
        <BookOpen className="h-3.5 w-3.5 shrink-0" />
        <span>
          {label || `Sources (${sources.length} Context Chunks Retrieved)`}
        </span>
        {isOpen ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
      </button>

      {isOpen && (
        <div className="mt-2.5 grid gap-2 rounded-xl border border-slate-200 bg-slate-50/90 p-3 dark:border-slate-700/70 dark:bg-slate-900/70">
          {sources.map((src, index) => {
            const scorePct =
              typeof src.relevance_score === 'number'
                ? `${Math.round(
                    src.relevance_score <= 1
                      ? src.relevance_score * 100
                      : src.relevance_score
                  )}% match`
                : null;

            const snippet = src.snippet || src.text;

            return (
              <div
                key={`${src.document}-${index}`}
                className="rounded-lg border border-slate-200/80 bg-white px-3 py-2 text-xs shadow-sm dark:border-slate-800 dark:bg-slate-950/60"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5 font-medium text-slate-800 dark:text-slate-200">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    <span className="truncate">{src.document || 'Knowledge Document'}</span>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                    {src.page !== undefined && src.page !== null && (
                      <span>p. {src.page}</span>
                    )}
                    {src.chunk_id !== undefined && src.chunk_id !== null && (
                      <span>chunk #{src.chunk_id}</span>
                    )}
                    {scorePct && (
                      <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-600 dark:text-emerald-400">
                        {scorePct}
                      </span>
                    )}
                  </div>
                </div>
                {snippet && (
                  <p className="mt-1.5 line-clamp-3 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                    {snippet}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

