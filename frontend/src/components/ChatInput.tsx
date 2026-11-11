import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, Sparkles, Square } from 'lucide-react';
import type { BotMode, QuickPromptPreset } from '../types/chat';

export interface ChatInputProps {
  value: string;
  isStreaming: boolean;
  activeMode: BotMode;
  presets: QuickPromptPreset[];
  onChange: (val: string) => void;
  onSubmit: (prompt?: string) => void;
  onStopGeneration: () => void;
  onSelectPreset: (preset: QuickPromptPreset) => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  value,
  isStreaming,
  activeMode,
  presets,
  onChange,
  onSubmit,
  onStopGeneration,
  onSelectPreset,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [showPresets, setShowPresets] = useState(false);

  const MAX_CHARS = 50000;
  const isOverLimit = value.length > MAX_CHARS;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!e.repeat && !isStreaming && value.trim() && !isOverLimit) {
        onSubmit();
      }
    }
  };

  const placeholder =
    activeMode === 'sales'
      ? 'Describe your relationship struggle or ask which course or masterclass fits...'
      : activeMode === 'platform'
      ? 'Ask about login, password reset, course dashboard, PDF workbooks, or billing...'
      : activeMode === 'owner'
      ? 'Ask Dr. Sarah Hensley (Founder Voice) about attachment styles, emotional healing, or relationships...'
      : "Ask Dr. Sarah's Clinical Educator AI about attachment styles, somatic tools, or reflection...";

  return (
    <div className="border-t border-slate-200/80 bg-white/85 px-3 py-3 backdrop-blur-md dark:border-slate-800/80 dark:bg-[#0B1120]/90 sm:px-6">
      <div className="mx-auto max-w-3xl">
        {showPresets && (
          <div className="mb-2.5 flex flex-wrap gap-1.5 rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900/90">
            {presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                disabled={isStreaming}
                onClick={() => {
                  setShowPresets(false);
                  onSelectPreset(preset);
                }}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left text-xs font-medium text-slate-700 transition-colors hover:border-emerald-500/50 hover:text-emerald-700 disabled:opacity-50 dark:border-slate-700/80 dark:bg-slate-800/80 dark:text-slate-200 dark:hover:border-amber-400/50 dark:hover:text-amber-300"
              >
                <span className="mr-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-amber-400">
                  {preset.category}
                </span>
                <span>{preset.label}</span>
              </button>
            ))}
          </div>
        )}

        <div
          className={`flex items-end gap-2 rounded-2xl border bg-slate-50 px-3 py-2 shadow-sm transition-colors focus-within:ring-2 dark:bg-[#131E32] ${
            activeMode === 'sales'
              ? 'border-amber-500/30 focus-within:border-amber-500 focus-within:ring-amber-500/20'
              : activeMode === 'platform'
              ? 'border-sky-500/30 focus-within:border-sky-500 focus-within:ring-sky-500/20'
              : activeMode === 'owner'
              ? 'border-violet-500/30 focus-within:border-violet-500 focus-within:ring-violet-500/20'
              : 'border-slate-300 focus-within:border-emerald-500 focus-within:ring-emerald-500/20 dark:border-slate-700/80'
          }`}
        >
          <button
            type="button"
            onClick={() => setShowPresets((prev) => !prev)}
            disabled={isStreaming}
            title="Quick action prompts & clinical test presets"
            className={`mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors disabled:opacity-40 ${
              showPresets
                ? 'bg-emerald-500/20 text-emerald-600 dark:bg-amber-500/20 dark:text-amber-300'
                : 'text-slate-500 hover:bg-slate-200/70 dark:text-slate-400 dark:hover:bg-slate-800'
            }`}
          >
            <Sparkles className="h-4 w-4" />
          </button>

          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            disabled={isStreaming}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            className="max-h-[180px] min-h-[38px] flex-1 resize-none bg-transparent py-2 text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-100 dark:placeholder:text-slate-500"
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={onStopGeneration}
              className="mb-0.5 inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-rose-600 px-3 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-rose-500"
              title="Stop generation"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              <span>Stop</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => onSubmit()}
              disabled={!value.trim() || isOverLimit}
              className={`mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-35 ${
                activeMode === 'sales'
                  ? 'bg-amber-500 hover:bg-amber-400'
                  : activeMode === 'platform'
                  ? 'bg-sky-600 hover:bg-sky-500'
                  : activeMode === 'owner'
                  ? 'bg-violet-600 hover:bg-violet-500'
                  : 'bg-emerald-600 hover:bg-emerald-500'
              }`}
              title={isOverLimit ? 'Message exceeds 50,000 characters' : 'Send message'}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="mt-1.5 flex items-center justify-between gap-2 px-1 text-[11px] text-slate-400 dark:text-slate-500">
          <span>
            Press <kbd className="font-mono font-semibold">Enter</kbd> to send •{' '}
            <kbd className="font-mono font-semibold">Shift+Enter</kbd> for new line
            {value.length > 2000 && (
              <span
                className={`ml-2 font-mono ${
                  isOverLimit ? 'font-semibold text-rose-500' : 'text-slate-400'
                }`}
              >
                ({value.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} chars)
              </span>
            )}
          </span>
          <span
            className={
              activeMode === 'sales'
                ? 'font-medium text-amber-600 dark:text-amber-400'
                : activeMode === 'platform'
                ? 'font-medium text-sky-600 dark:text-sky-400'
                : activeMode === 'owner'
                ? 'font-medium text-violet-600 dark:text-violet-400'
                : 'font-medium text-emerald-600 dark:text-emerald-400'
            }
          >
            {activeMode === 'sales'
              ? 'Program Advisor Mode'
              : activeMode === 'platform'
              ? 'Platform Navigation Mode'
              : activeMode === 'owner'
              ? 'Owner Agent Mode (Founder Voice)'
              : 'Clinical Educator Mode (0 Pitches)'}
          </span>
        </div>
      </div>
    </div>
  );
};

