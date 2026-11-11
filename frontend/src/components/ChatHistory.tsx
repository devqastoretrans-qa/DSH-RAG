import React, { useMemo, useState } from 'react';
import {
  Briefcase,
  Check,
  Compass,
  MessageSquare,
  Pencil,
  Stethoscope,
  Trash2,
  X,
} from 'lucide-react';
import type { BotMode, ChatThread, ChronologicalGroup } from '../types/chat';

export interface ChatHistoryProps {
  threads: ChatThread[];
  activeSessionId: string;
  searchQuery: string;
  activeMode: BotMode;
  isLoading?: boolean;
  onSelectThread: (thread: ChatThread) => void;
  onRenameThread: (sessionId: string, newTitle: string) => Promise<void>;
  onDeleteThread: (sessionId: string) => Promise<void>;
}

const GROUP_ORDER: ChronologicalGroup[] = [
  'Today',
  'Yesterday',
  'Previous 7 Days',
  'Older',
];

function normalizeTimestampMs(tsValue?: number | null): number {
  const num = Number(tsValue);
  if (!Number.isFinite(num) || num <= 0) {
    return Date.now();
  }
  return num > 1e12 ? num : num * 1000;
}

function getChronologicalGroup(tsValue?: number | null): ChronologicalGroup {
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  ).getTime();
  const ms = normalizeTimestampMs(tsValue);
  const diffDays = (startOfToday - ms) / (1000 * 60 * 60 * 24);

  if (ms >= startOfToday) return 'Today';
  if (diffDays <= 1) return 'Yesterday';
  if (diffDays <= 7) return 'Previous 7 Days';
  return 'Older';
}

function formatShortDate(tsValue?: number | null): string {
  const ms = normalizeTimestampMs(tsValue);
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatIsoDate(tsValue?: number | null): string {
  const ms = normalizeTimestampMs(tsValue);
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

export const ChatHistory: React.FC<ChatHistoryProps> = ({
  threads,
  activeSessionId,
  searchQuery,
  activeMode,
  isLoading = false,
  onSelectThread,
  onRenameThread,
  onDeleteThread,
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const groupedThreads = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = threads.filter((t) => {
      if (!q) return true;
      const rawTs = t.updated_at || t.created_at;
      const group = getChronologicalGroup(rawTs).toLowerCase();
      const dateStr = formatShortDate(rawTs).toLowerCase();
      const isoDate = formatIsoDate(rawTs).toLowerCase();
      return (
        (t.title || '').toLowerCase().includes(q) ||
        group.includes(q) ||
        dateStr.includes(q) ||
        isoDate.includes(q)
      );
    });

    const buckets: Record<ChronologicalGroup, ChatThread[]> = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      Older: [],
    };

    for (const thread of filtered) {
      const ts = thread.updated_at || thread.created_at;
      buckets[getChronologicalGroup(ts)].push(thread);
    }

    return buckets;
  }, [threads, searchQuery]);

  const hasAny = GROUP_ORDER.some((g) => groupedThreads[g].length > 0);

  const commitRename = async (sessionId: string) => {
    const clean = draftTitle.trim();
    setEditingId(null);
    if (!clean) return;
    await onRenameThread(sessionId, clean);
  };

  if (isLoading && threads.length === 0) {
    return (
      <div className="space-y-2 px-3 py-4">
        {[1, 2, 3].map((n) => (
          <div
            key={n}
            className="h-9 animate-pulse rounded-lg bg-slate-200/70 dark:bg-slate-800/70"
          />
        ))}
      </div>
    );
  }

  if (!hasAny) {
    return (
      <div className="px-4 py-8 text-center">
        <MessageSquare className="mx-auto mb-2 h-6 w-6 text-slate-400 dark:text-slate-600" />
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {searchQuery.trim()
            ? 'No matching chats found.'
            : `No ${
                activeMode === 'sales'
                  ? 'Program Advisor'
                  : activeMode === 'platform'
                  ? 'Platform Help'
                  : 'Clinical Educator'
              } conversations yet.`}
        </p>
        {!searchQuery.trim() && (
          <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
            Start chatting below and your conversation will appear here as #1.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4 px-2 py-2">
      {GROUP_ORDER.map((groupName) => {
        const items = groupedThreads[groupName];
        if (!items || items.length === 0) return null;

        return (
          <div key={groupName}>
            <div className="mb-1.5 px-2.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              {groupName}
            </div>
            <div className="space-y-0.5">
              {items.map((thread) => {
                const isActive = thread.session_id === activeSessionId;
                const isEditing = editingId === thread.session_id;
                const isConfirmingDelete = confirmDeleteId === thread.session_id;
                const displayNum = thread.chat_number ? `${thread.chat_number}.` : '';

                return (
                  <div
                    key={thread.session_id}
                    className={`group relative flex items-center justify-between gap-1.5 rounded-lg px-2.5 py-2 text-xs transition-colors ${
                      isActive
                        ? 'bg-emerald-500/15 font-medium text-emerald-800 dark:bg-amber-500/15 dark:text-amber-200'
                        : 'text-slate-700 hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800/80'
                    }`}
                  >
                    {isEditing ? (
                      <div className="flex flex-1 items-center gap-1">
                        <input
                          type="text"
                          value={draftTitle}
                          onChange={(e) => setDraftTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              void commitRename(thread.session_id);
                            } else if (e.key === 'Escape') {
                              setEditingId(null);
                            }
                          }}
                          autoFocus
                          maxLength={120}
                          className="w-full rounded border border-emerald-500/50 bg-white px-2 py-1 text-xs text-slate-900 outline-none dark:bg-slate-900 dark:text-slate-100"
                        />
                        <button
                          type="button"
                          onClick={() => void commitRename(thread.session_id)}
                          className="rounded p-1 text-emerald-600 hover:bg-emerald-500/15 dark:text-emerald-400"
                          title="Save title"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="rounded p-1 text-slate-400 hover:bg-slate-700/40"
                          title="Cancel"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : isConfirmingDelete ? (
                      <div className="flex flex-1 items-center justify-between gap-2 text-[11px]">
                        <span className="truncate font-medium text-rose-500 dark:text-rose-400">
                          Delete chat?
                        </span>
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(null);
                              void onDeleteThread(thread.session_id);
                            }}
                            className="rounded bg-rose-600 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-rose-500"
                            title="Confirm delete"
                          >
                            Confirm
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(null);
                            }}
                            className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] text-slate-600 hover:bg-slate-200 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                            title="Cancel delete"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setConfirmDeleteId(null);
                            onSelectThread(thread);
                          }}
                          title={`${displayNum ? displayNum + ' ' : ''}${thread.title}`}
                          className="flex min-w-0 flex-1 items-center gap-2 text-left"
                        >
                          {displayNum && (
                            <span className="shrink-0 font-mono text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                              {displayNum}
                            </span>
                          )}
                          {thread.mode === 'sales' ? (
                            <Briefcase className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                          ) : thread.mode === 'platform' ? (
                            <Compass className="h-3.5 w-3.5 shrink-0 text-sky-500" />
                          ) : (
                            <Stethoscope className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                          )}
                          <span className="block min-w-0 flex-1 truncate text-ellipsis">
                            {thread.title || 'New Conversation'}
                          </span>
                        </button>

                        <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(null);
                              setEditingId(thread.session_id);
                              setDraftTitle(thread.title || '');
                            }}
                            className="rounded p-1 text-slate-400 hover:bg-slate-300/60 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                            title="Rename conversation"
                          >
                            <Pencil className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteId(thread.session_id);
                            }}
                            className="rounded p-1 text-slate-400 hover:bg-rose-500/15 hover:text-rose-500"
                            title="Delete conversation"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};
