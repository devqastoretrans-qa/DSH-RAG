import React from 'react';
import {
  CheckCircle2,
  Moon,
  ShieldCheck,
  Sun,
  UserCheck,
  X,
} from 'lucide-react';
import type { PersonaUser } from '../types/chat';

export interface ProfileSettingsModalProps {
  isOpen: boolean;
  isDark: boolean;
  users: PersonaUser[];
  activeUserId: string;
  systemStats?: {
    documents?: number;
    conversationTurns?: number;
    users?: number;
  };
  onClose: () => void;
  onToggleTheme: () => void;
  onSelectUser: (userId: string) => void;
}

export const ProfileSettingsModal: React.FC<ProfileSettingsModalProps> = ({
  isOpen,
  isDark,
  users,
  activeUserId,
  systemStats,
  onClose,
  onToggleTheme,
  onSelectUser,
}) => {
  if (!isOpen) return null;

  const activeUser = users.find(
    (u) => String(u.user_id) === String(activeUserId)
  );
  const purchases = activeUser?.all_purchases || [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-[#131E32]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 pb-3 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <UserCheck className="h-5 w-5 text-emerald-500" />
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Profile, Theme & Session Isolation
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-4">
          {/* Theme Switcher */}
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-slate-800 dark:bg-slate-900/70">
            <div>
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-100">
                Interface Appearance
              </div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400">
                Switch between Dark Studio and Clean Light theme
              </div>
            </div>
            <button
              type="button"
              onClick={onToggleTheme}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              {isDark ? (
                <>
                  <Sun className="h-3.5 w-3.5 text-amber-400" />
                  <span>Light Mode</span>
                </>
              ) : (
                <>
                  <Moon className="h-3.5 w-3.5 text-indigo-500" />
                  <span>Dark Mode</span>
                </>
              )}
            </button>
          </div>

          {/* Authenticated User Selector */}
          <div>
            <label className="mb-1.5 block font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Authenticated Student / Persona
            </label>
            <select
              value={activeUserId}
              onChange={(e) => {
                onSelectUser(e.target.value);
                onClose();
              }}
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              {users.length > 0 ? (
                users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.name || u.email || u.user_id} (ID: {u.user_id}) —{' '}
                    {(u.all_purchases || []).length} owned
                  </option>
                ))
              ) : (
                <option value="1836">Test2011 User1022 (ID: 1836)</option>
              )}
              <option value="guest">Guest User (Unauthenticated)</option>
            </select>
            <p className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              <span>
                Switching users clears local state and rotates server-signed HMAC tokens.
              </span>
            </p>
          </div>

          {/* Owned Masterclasses */}
          {purchases.length > 0 && (
            <div>
              <div className="mb-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Owned Masterclasses ({purchases.length})
              </div>
              <div className="max-h-32 space-y-1.5 overflow-y-auto pr-1">
                {purchases.map((item, idx) => {
                  const title =
                    typeof item === 'string'
                      ? item
                      : item.name || item.title || 'Course';
                  return (
                    <div
                      key={`${title}-${idx}`}
                      className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-200"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                      <span className="truncate">{title}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* System Counters */}
          {systemStats && (
            <div className="grid grid-cols-3 gap-2 pt-1 text-center">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900/60">
                <div className="font-mono text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                  {systemStats.documents ?? '—'}
                </div>
                <div className="text-[10px] text-slate-500">Knowledge Docs</div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900/60">
                <div className="font-mono text-sm font-semibold text-amber-600 dark:text-amber-400">
                  {systemStats.users ?? users.length}
                </div>
                <div className="text-[10px] text-slate-500">Registered Users</div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900/60">
                <div className="font-mono text-sm font-semibold text-sky-600 dark:text-sky-400">
                  {systemStats.conversationTurns ?? '—'}
                </div>
                <div className="text-[10px] text-slate-500">Saved Turns</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

