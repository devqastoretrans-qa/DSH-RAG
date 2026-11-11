import React, { useState } from 'react';
import {
  Eraser,
  Plus,
  Search,
  Settings,
  User as UserIcon,
  X,
} from 'lucide-react';
import type { BotMode, ChatThread, PersonaUser } from '../types/chat';
import { ChatHistory } from './ChatHistory';

export interface SidebarProps {
  isOpen: boolean;
  activeMode: BotMode;
  threads: ChatThread[];
  activeSessionId: string;
  searchQuery: string;
  isLoadingThreads?: boolean;
  currentUser?: PersonaUser;
  userId: string;
  onCloseMobile: () => void;
  onNewChat: () => void;
  onSearchChange: (q: string) => void;
  onSelectThread: (thread: ChatThread) => void;
  onRenameThread: (sessionId: string, newTitle: string) => Promise<void>;
  onDeleteThread: (sessionId: string) => Promise<void>;
  onClearHistory: () => Promise<void>;
  onOpenProfileModal: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  activeMode,
  threads,
  activeSessionId,
  searchQuery,
  isLoadingThreads = false,
  currentUser,
  userId,
  onCloseMobile,
  onNewChat,
  onSearchChange,
  onSelectThread,
  onRenameThread,
  onDeleteThread,
  onClearHistory,
  onOpenProfileModal,
}) => {
  const [confirmClear, setConfirmClear] = useState(false);

  const displayName =
    currentUser?.name ||
    (userId === 'guest' ? 'Guest Visitor' : `User ${userId}`);
  const displaySub =
    currentUser?.email ||
    (userId === 'guest' ? 'Unauthenticated' : `ID: ${userId}`);

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-950/60 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-slate-200 bg-slate-100/95 backdrop-blur-xl transition-all duration-200 dark:border-slate-800 dark:bg-[#0D1526]/95 lg:static lg:z-auto ${
          isOpen
            ? 'w-72 translate-x-0'
            : 'w-72 -translate-x-full lg:w-0 lg:overflow-hidden lg:border-r-0 lg:translate-x-0'
        }`}
      >
        {/* Header: New Chat Button */}
        <div className="flex items-center gap-2 border-b border-slate-200/80 p-3 dark:border-slate-800/80">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              onCloseMobile();
            }}
            className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all active:scale-[0.98] ${
              activeMode === 'sales'
                ? 'bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400'
                : activeMode === 'platform'
                ? 'bg-gradient-to-r from-sky-600 to-sky-500 hover:from-sky-500 hover:to-sky-400'
                : 'bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400'
            }`}
          >
            <Plus className="h-4 w-4" />
            <span>New Chat</span>
          </button>

          <button
            type="button"
            onClick={onCloseMobile}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-800 lg:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Search / Filter Bar */}
        <div className="border-b border-slate-200/60 px-3 py-2.5 dark:border-slate-800/60">
          <div className="relative flex items-center">
            <Search className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search chats or date (Today, 2026...)"
              className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pl-8 pr-7 text-xs text-slate-800 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-700/80 dark:bg-slate-900/90 dark:text-slate-200 dark:placeholder:text-slate-500"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange('')}
                className="absolute right-2 rounded p-0.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                aria-label="Clear search"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
          <div className="mt-2 flex items-center justify-between px-0.5">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {activeMode === 'sales'
                ? 'Program Advisor History'
                : activeMode === 'platform'
                ? 'Platform Help History'
                : 'Clinical Educator History'}
            </span>
            <span className="font-mono text-[10px] text-slate-400">
              {threads.length}
            </span>
          </div>
        </div>

        {/* Chronological History Feed */}
        <div className="flex-1 overflow-y-auto">
          <ChatHistory
            threads={threads}
            activeSessionId={activeSessionId}
            searchQuery={searchQuery}
            activeMode={activeMode}
            isLoading={isLoadingThreads}
            onSelectThread={(thread) => {
              onSelectThread(thread);
              onCloseMobile();
            }}
            onRenameThread={onRenameThread}
            onDeleteThread={onDeleteThread}
          />
        </div>

        {/* Footer: User Profile Trigger & Clear History */}
        <div className="border-t border-slate-200/80 p-2.5 dark:border-slate-800/80">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onOpenProfileModal}
              className="flex min-w-0 flex-1 items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-slate-200/70 dark:hover:bg-slate-800/80"
              title="Profile, Persona Switcher & Settings"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/15 text-xs font-semibold text-amber-700 dark:text-amber-300">
                <UserIcon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-100">
                  {displayName}
                </div>
                <div className="truncate text-[11px] text-slate-500 dark:text-slate-400">
                  {displaySub}
                </div>
              </div>
              <Settings className="h-4 w-4 shrink-0 text-slate-400" />
            </button>

            {threads.length > 0 &&
              (confirmClear ? (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmClear(false);
                      void onClearHistory();
                    }}
                    className="rounded-lg bg-rose-600 px-2 py-1.5 text-[11px] font-semibold text-white hover:bg-rose-500"
                    title="Confirm clear all"
                  >
                    Clear All
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmClear(false)}
                    className="rounded-lg border border-slate-300 px-2 py-1.5 text-[11px] text-slate-600 hover:bg-slate-200 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                    title="Cancel"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmClear(true)}
                  className="flex shrink-0 items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-2 text-[11px] font-medium text-slate-600 transition-colors hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-600 dark:border-slate-700/80 dark:text-slate-300 dark:hover:text-rose-400"
                  title="Clear all chats in active mode"
                >
                  <Eraser className="h-3.5 w-3.5" />
                  <span>Clear</span>
                </button>
              ))}
          </div>
        </div>
      </aside>
    </>
  );
};

