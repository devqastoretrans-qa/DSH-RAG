import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown,
  Briefcase,
  Moon,
  PanelLeft,
  SlidersHorizontal,
  Stethoscope,
  Sun,
} from 'lucide-react';
import type {
  BotMode,
  ChatFilter,
  ChatMessage as ChatMessageType,
  ChatThread,
  MessageFilterMode,
  PersonaUser,
  QuickPromptPreset,
  RecommendedProduct,
  SourceCitation,
} from './types/chat';
import { Sidebar } from './components/Sidebar';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import { ProfileSettingsModal } from './components/ProfileSettingsModal';

function createSessionId(mode: BotMode): string {
  const prefix = mode === 'sales' ? 'sess_sales_' : 'sess_clinical_';
  return prefix + Math.random().toString(36).substring(2, 10);
}

const QUICK_PRESETS: QuickPromptPreset[] = [
  {
    id: 'journal',
    category: 'Clinical Tool',
    label: 'What is the 1:1:1 journal reflection method?',
    prompt: 'What is the 1:1:1 journal reflection method for emotional regulation?',
    mode: 'generic',
  },
  {
    id: 'solace',
    category: 'Communication',
    label: 'How does SOLACE resolve high-conflict fights?',
    prompt: 'How does the SOLACE communication tool resolve high-conflict fights?',
    mode: 'generic',
  },
  {
    id: 'hyperarousal',
    category: 'Somatic',
    label: 'Calm nervous system hyperarousal',
    prompt: 'How can I calm acute nervous system hyperarousal during relationship anxiety?',
    mode: 'generic',
  },
  {
    id: 'sales_masterclass',
    category: 'Advisor',
    label: 'Best $97 masterclass for attachment healing',
    prompt: 'I struggle with anxious attachment and want to break this pattern. Which $97 masterclass fits best?',
    mode: 'sales',
  },
  {
    id: 'sales_bundle',
    category: 'Bundle',
    label: 'What is included in the Secure Bundle?',
    prompt: 'What is included in the Secure Bundle and what is the investment?',
    mode: 'sales',
  },
];

interface ChannelBuffer {
  sessionId: string;
  messages: ChatMessageType[];
  title: string;
}

export const App: React.FC = () => {
  const [isDark, setIsDark] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [profileModalOpen, setProfileModalOpen] = useState(false);

  const [filter, setFilter] = useState<ChatFilter>({
    searchQuery: '',
    messageFilter: 'all',
    mode: 'generic',
  });

  const [userId, setUserId] = useState('1836');
  const [authToken, setAuthToken] = useState('');
  const [usersCatalog, setUsersCatalog] = useState<PersonaUser[]>([]);
  const [systemStats, setSystemStats] = useState<{
    documents?: number;
    conversationTurns?: number;
    users?: number;
  }>({});

  const [channels, setChannels] = useState<Record<BotMode, ChannelBuffer>>({
    generic: {
      sessionId: createSessionId('generic'),
      messages: [],
      title: 'New Clinical Chat',
    },
    sales: {
      sessionId: createSessionId('sales'),
      messages: [],
      title: 'New Program Advisor Chat',
    },
  });

  const [threadsByMode, setThreadsByMode] = useState<
    Record<BotMode, ChatThread[]>
  >({
    generic: [],
    sales: [],
  });
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [showScrollBottomBtn, setShowScrollBottomBtn] = useState(false);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const activeMode = filter.mode;
  const activeChannel = channels[activeMode];
  const activeThreads = threadsByMode[activeMode];

  // Sync Tailwind dark class on <html>
  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [isDark]);

  const buildAuthHeaders = useCallback(
    (tokenOverride?: string, extra: Record<string, string> = {}) => {
      const tok = tokenOverride ?? authToken;
      return tok
        ? { ...extra, Authorization: `Bearer ${tok}` }
        : { ...extra };
    },
    [authToken]
  );

  const fetchThreads = useCallback(
    async (mode: BotMode, tokenOverride?: string) => {
      const tok = tokenOverride ?? authToken;
      if (!tok) return;
      setIsLoadingThreads(true);
      try {
        const res = await fetch(
          `/api/chat/sessions?mode=${encodeURIComponent(mode)}&limit=50`,
          { headers: buildAuthHeaders(tok) }
        );
        if (!res.ok) return;
        const data = (await res.json()) as { sessions?: ChatThread[] };
        const clean = (data.sessions || []).filter(
          (s) => (s.mode || 'generic') === mode
        );
        setThreadsByMode((prev) => ({ ...prev, [mode]: clean }));
      } catch (err) {
        console.warn('Failed to fetch sessions:', err);
      } finally {
        setIsLoadingThreads(false);
      }
    },
    [authToken, buildAuthHeaders]
  );

  const authenticateUser = useCallback(
    async (targetUserId: string) => {
      try {
        const res = await fetch('/api/auth/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: targetUserId }),
        });
        if (!res.ok) return '';
        const data = (await res.json()) as { token?: string };
        const tok = data.token || '';
        setAuthToken(tok);
        sessionStorage.setItem('studio_chat_token', tok);
        sessionStorage.setItem('studio_active_user', targetUserId);
        return tok;
      } catch (err) {
        console.warn('Failed to authenticate user:', err);
        return '';
      }
    },
    []
  );

  const handleSelectUser = useCallback(
    async (nextUserId: string) => {
      abortControllerRef.current?.abort();
      setIsStreaming(false);
      sessionStorage.clear();
      setUserId(nextUserId);
      setThreadsByMode({ generic: [], sales: [] });
      setChannels({
        generic: {
          sessionId: createSessionId('generic'),
          messages: [],
          title: 'New Clinical Chat',
        },
        sales: {
          sessionId: createSessionId('sales'),
          messages: [],
          title: 'New Program Advisor Chat',
        },
      });
      const tok = await authenticateUser(nextUserId);
      if (tok) {
        await fetchThreads(filter.mode, tok);
      }
    },
    [authenticateUser, fetchThreads, filter.mode]
  );

  // Initial startup load
  useEffect(() => {
    const boot = async () => {
      try {
        const [usersRes, statsRes] = await Promise.all([
          fetch('/api/users').catch(() => null),
          fetch('/api/system/stats').catch(() => null),
        ]);
        if (usersRes && usersRes.ok) {
          const uData = (await usersRes.json()) as { users?: PersonaUser[] };
          setUsersCatalog(uData.users || []);
        }
        if (statsRes && statsRes.ok) {
          const sData = (await statsRes.json()) as {
            documents_count?: number;
            mysql_counts?: { users?: number; conversation_turns?: number };
          };
          setSystemStats({
            documents: sData.documents_count,
            users: sData.mysql_counts?.users,
            conversationTurns: sData.mysql_counts?.conversation_turns,
          });
        }
      } catch {
        // Non-blocking startup stats
      }
      const tok = await authenticateUser('1836');
      if (tok) {
        await fetchThreads('generic', tok);
      }
    };
    void boot();
  }, [authenticateUser, fetchThreads]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBottomBtn(distanceFromBottom > 120);
  }, []);

  // Auto-scroll smoothly while new messages arrive unless scrolled far away
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 260) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [activeChannel.messages]);

  const handleModeSwitch = useCallback(
    (nextMode: BotMode) => {
      if (isStreaming || nextMode === activeMode) return;
      setFilter((prev) => ({ ...prev, mode: nextMode }));
      void fetchThreads(nextMode);
    },
    [activeMode, fetchThreads, isStreaming]
  );

  const handleNewChat = useCallback(() => {
    if (isStreaming) {
      abortControllerRef.current?.abort();
      setIsStreaming(false);
    }
    setChannels((prev) => ({
      ...prev,
      [activeMode]: {
        sessionId: createSessionId(activeMode),
        messages: [],
        title:
          activeMode === 'sales'
            ? 'New Program Advisor Chat'
            : 'New Clinical Chat',
      },
    }));
  }, [activeMode, isStreaming]);

  const handleSelectThread = useCallback(
    async (thread: ChatThread) => {
      if (isStreaming) return;
      const targetMode = thread.mode || activeMode;
      setFilter((prev) => ({ ...prev, mode: targetMode }));
      setIsLoadingHistory(true);

      try {
        const res = await fetch(
          `/api/chat/history?session_id=${encodeURIComponent(
            thread.session_id
          )}&mode=${encodeURIComponent(targetMode)}`,
          { headers: buildAuthHeaders() }
        );
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = (await res.json()) as {
          turns?: Array<{
            role: 'user' | 'assistant' | 'system';
            content: string;
            mode?: BotMode;
            created_at?: number;
          }>;
        };
        const mapped: ChatMessageType[] = (data.turns || []).map((t, idx) => ({
          id: `${thread.session_id}_turn_${idx}`,
          role: t.role === 'user' ? 'user' : t.role === 'system' ? 'system' : 'assistant',
          content: t.content,
          mode: (t.mode as BotMode) || targetMode,
          createdAt: t.created_at || Date.now() / 1000,
        }));

        setChannels((prev) => ({
          ...prev,
          [targetMode]: {
            sessionId: thread.session_id,
            messages: mapped,
            title: thread.title || 'Conversation',
          },
        }));
        window.setTimeout(() => scrollToBottom('auto'), 40);
      } catch (err) {
        console.error('Failed to load thread:', err);
      } finally {
        setIsLoadingHistory(false);
      }
    },
    [activeMode, buildAuthHeaders, isStreaming, scrollToBottom]
  );

  const handleRenameThread = useCallback(
    async (sessionId: string, newTitle: string) => {
      try {
        const res = await fetch(
          `/api/chat/sessions/${encodeURIComponent(sessionId)}`,
          {
            method: 'PATCH',
            headers: buildAuthHeaders(undefined, {
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ title: newTitle }),
          }
        );
        if (!res.ok) return;
        const data = (await res.json()) as { title?: string };
        const finalTitle = data.title || newTitle;
        setThreadsByMode((prev) => ({
          ...prev,
          [activeMode]: prev[activeMode].map((t) =>
            t.session_id === sessionId ? { ...t, title: finalTitle } : t
          ),
        }));
        setChannels((prev) =>
          prev[activeMode].sessionId === sessionId
            ? { ...prev, [activeMode]: { ...prev[activeMode], title: finalTitle } }
            : prev
        );
      } catch (err) {
        console.error('Failed to rename thread:', err);
      }
    },
    [activeMode, buildAuthHeaders]
  );

  const handleDeleteThread = useCallback(
    async (sessionId: string) => {
      if (!window.confirm('Delete this conversation permanently?')) return;
      try {
        const res = await fetch(
          `/api/chat/sessions/${encodeURIComponent(sessionId)}`,
          {
            method: 'DELETE',
            headers: buildAuthHeaders(),
          }
        );
        if (!res.ok) return;
        setThreadsByMode((prev) => ({
          ...prev,
          [activeMode]: prev[activeMode].filter((t) => t.session_id !== sessionId),
        }));
        if (activeChannel.sessionId === sessionId) {
          handleNewChat();
        } else {
          void fetchThreads(activeMode);
        }
      } catch (err) {
        console.error('Failed to delete thread:', err);
      }
    },
    [activeChannel.sessionId, activeMode, buildAuthHeaders, fetchThreads, handleNewChat]
  );

  const handleClearHistory = useCallback(async () => {
    const label =
      activeMode === 'sales' ? 'Program Advisor' : 'Clinical Educator';
    if (
      !window.confirm(
        `Remove all past ${label} conversations? Your next chat will start as #1.`
      )
    ) {
      return;
    }
    try {
      const res = await fetch(
        `/api/chat/sessions?mode=${encodeURIComponent(activeMode)}`,
        {
          method: 'DELETE',
          headers: buildAuthHeaders(),
        }
      );
      if (!res.ok) return;
      setThreadsByMode((prev) => ({ ...prev, [activeMode]: [] }));
      handleNewChat();
    } catch (err) {
      console.error('Failed to clear sessions:', err);
    }
  }, [activeMode, buildAuthHeaders, handleNewChat]);

  const handleStopGeneration = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const handleSubmitMessage = useCallback(
    async (overridePrompt?: string, overrideMode?: BotMode) => {
      const targetMode = overrideMode || activeMode;
      const text = (overridePrompt ?? inputValue).trim();
      if (!text || isStreaming) return;

      if (overrideMode && overrideMode !== activeMode) {
        setFilter((prev) => ({ ...prev, mode: overrideMode }));
      }

      const channelSnapshot = channels[targetMode];
      const sessionId = channelSnapshot.sessionId;
      const isFirstMessage = channelSnapshot.messages.length === 0;
      const nextTitle = isFirstMessage
        ? text.slice(0, 60)
        : channelSnapshot.title;

      const userMsg: ChatMessageType = {
        id: `user_${Date.now()}`,
        role: 'user',
        content: text,
        mode: targetMode,
        createdAt: Date.now(),
      };

      const assistantMsgId = `bot_${Date.now()}`;
      const placeholderBotMsg: ChatMessageType = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        mode: targetMode,
        createdAt: Date.now(),
        isStreaming: true,
      };

      if (!overridePrompt) {
        setInputValue('');
      }
      setIsStreaming(true);

      setChannels((prev) => ({
        ...prev,
        [targetMode]: {
          ...prev[targetMode],
          title: nextTitle,
          messages: [...prev[targetMode].messages, userMsg, placeholderBotMsg],
        },
      }));

      const controller = new AbortController();
      abortControllerRef.current = controller;
      const startTime = performance.now();

      const updateAssistantMsg = (
        updater: (prevMsg: ChatMessageType) => ChatMessageType
      ) => {
        setChannels((prev) => ({
          ...prev,
          [targetMode]: {
            ...prev[targetMode],
            messages: prev[targetMode].messages.map((m) =>
              m.id === assistantMsgId ? updater(m) : m
            ),
          },
        }));
      };

      try {
        const res = await fetch('/chat/stream', {
          method: 'POST',
          headers: buildAuthHeaders(undefined, {
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify({
            session_id: sessionId,
            message: text,
            mode: targetMode,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let accumulated = '';
        let receivedDonePayload = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const payload = JSON.parse(line.slice(6)) as {
                token?: string;
                done?: boolean;
                answer?: string;
                full_answer?: string;
                sources?: SourceCitation[];
                recommended_products?: RecommendedProduct[];
                cached?: boolean;
              };

              if (payload.token) {
                accumulated += payload.token;
                updateAssistantMsg((m) => ({
                  ...m,
                  content: accumulated,
                  isStreaming: true,
                }));
              } else if (payload.done || payload.answer) {
                receivedDonePayload = true;
                const finalAns =
                  payload.answer || payload.full_answer || accumulated;
                const latencySec = (
                  (performance.now() - startTime) /
                  1000
                ).toFixed(2);
                const sources = payload.sources || [];
                const docNames = sources
                  .map((s) => s.document)
                  .filter(Boolean)
                  .slice(0, 3)
                  .join(', ');

                updateAssistantMsg((m) => ({
                  ...m,
                  content: finalAns,
                  isStreaming: false,
                  cached: Boolean(payload.cached),
                  latencySec,
                  sources,
                  recommendedProducts: payload.recommended_products || [],
                  retrievalContextSummary:
                    sources.length > 0
                      ? `${sources.length} vector chunks (${docNames})`
                      : undefined,
                }));
              }
            } catch {
              // Ignore partial SSE lines
            }
          }
        }

        if (!receivedDonePayload && accumulated.length === 0) {
          // Fallback to non-streaming /chat endpoint
          const fallbackRes = await fetch('/chat', {
            method: 'POST',
            headers: buildAuthHeaders(undefined, {
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({
              session_id: sessionId,
              message: text,
              mode: targetMode,
            }),
            signal: controller.signal,
          });
          const data = (await fallbackRes.json()) as {
            answer?: string;
            sources?: SourceCitation[];
            recommended_products?: RecommendedProduct[];
            cached?: boolean;
          };
          const latencySec = ((performance.now() - startTime) / 1000).toFixed(2);
          updateAssistantMsg((m) => ({
            ...m,
            content: data.answer || 'No response generated.',
            isStreaming: false,
            cached: Boolean(data.cached),
            latencySec,
            sources: data.sources || [],
            recommendedProducts: data.recommended_products || [],
          }));
        } else if (!receivedDonePayload) {
          updateAssistantMsg((m) => ({ ...m, isStreaming: false }));
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          updateAssistantMsg((m) => ({
            ...m,
            content: m.content || 'Generation stopped by user.',
            isStreaming: false,
            isStopped: true,
          }));
        } else {
          updateAssistantMsg((m) => ({
            ...m,
            content: 'Connection error while generating response. Please try again.',
            isStreaming: false,
            isError: true,
          }));
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
        void fetchThreads(targetMode);
      }
    },
    [activeMode, buildAuthHeaders, channels, fetchThreads, inputValue, isStreaming]
  );

  const visibleMessages = useMemo(() => {
    const modeFilter: MessageFilterMode = filter.messageFilter;
    if (modeFilter === 'all') return activeChannel.messages;
    if (modeFilter === 'user') {
      return activeChannel.messages.filter((m) => m.role === 'user');
    }
    return activeChannel.messages.filter(
      (m) =>
        m.role === 'system' ||
        (m.sources && m.sources.length > 0) ||
        Boolean(m.retrievalContextSummary)
    );
  }, [activeChannel.messages, filter.messageFilter]);

  const currentUser = useMemo(
    () => usersCatalog.find((u) => String(u.user_id) === String(userId)),
    [userId, usersCatalog]
  );

  const userInitials = useMemo(() => {
    const name = currentUser?.name || (userId === 'guest' ? 'G' : 'U');
    return name
      .split(' ')
      .map((p) => p[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
  }, [currentUser, userId]);

  const modeFilteredPresets = useMemo(
    () => QUICK_PRESETS.filter((p) => p.mode === activeMode || p.mode === 'generic'),
    [activeMode]
  );

  return (
    <div className="flex h-dvh w-screen overflow-hidden bg-slate-50 text-slate-900 dark:bg-[#0B1120] dark:text-slate-100">
      {/* Left Collapsible Sidebar */}
      <Sidebar
        isOpen={sidebarOpen}
        activeMode={activeMode}
        threads={activeThreads}
        activeSessionId={activeChannel.sessionId}
        searchQuery={filter.searchQuery}
        isLoadingThreads={isLoadingThreads}
        currentUser={currentUser}
        userId={userId}
        onCloseMobile={() => {
          if (window.innerWidth < 1024) setSidebarOpen(false);
        }}
        onNewChat={handleNewChat}
        onSearchChange={(searchQuery) =>
          setFilter((prev) => ({ ...prev, searchQuery }))
        }
        onSelectThread={(thread) => void handleSelectThread(thread)}
        onRenameThread={handleRenameThread}
        onDeleteThread={handleDeleteThread}
        onClearHistory={handleClearHistory}
        onOpenProfileModal={() => setProfileModalOpen(true)}
      />

      {/* Right Main Chat Column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Sticky Top Bar */}
        <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 bg-white/85 px-3 py-2.5 backdrop-blur-md dark:border-slate-800/80 dark:bg-[#0B1120]/90 sm:px-5">
          <div className="flex min-w-0 items-center gap-2.5">
            <button
              type="button"
              onClick={() => setSidebarOpen((prev) => !prev)}
              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              title="Toggle Sidebar"
              aria-label="Toggle Sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </button>

            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate font-serif text-sm font-semibold text-slate-900 dark:text-slate-100 sm:text-base">
                  {activeChannel.title}
                </h1>
              </div>
              <p className="truncate font-mono text-[10px] text-slate-400 dark:text-slate-500">
                Session: {activeChannel.sessionId}
              </p>
            </div>
          </div>

          {/* Bot Mode Pills + Message Role/Context Filter + Theme Toggle */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Dual Bot Switcher */}
            <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-800 dark:bg-slate-900">
              <button
                type="button"
                onClick={() => handleModeSwitch('generic')}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  activeMode === 'generic'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Stethoscope className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Clinical Educator</span>
                <span className="sm:hidden">Clinical</span>
              </button>
              <button
                type="button"
                onClick={() => handleModeSwitch('sales')}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  activeMode === 'sales'
                    ? 'bg-amber-500 text-slate-950 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Briefcase className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Program Advisor</span>
                <span className="sm:hidden">Advisor</span>
              </button>
            </div>

            {/* Quick Message Filter Toggle */}
            <div
              className="hidden items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5 md:inline-flex dark:border-slate-800 dark:bg-slate-900"
              title="Filter displayed messages"
            >
              <SlidersHorizontal className="mx-1.5 h-3 w-3 text-slate-400" />
              {(
                [
                  { id: 'all', label: 'All' },
                  { id: 'user', label: 'User Query' },
                  { id: 'context', label: 'Retrieval Context' },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() =>
                    setFilter((prev) => ({ ...prev, messageFilter: opt.id }))
                  }
                  className={`rounded-lg px-2 py-1 text-[11px] font-medium transition-colors ${
                    filter.messageFilter === opt.id
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-slate-100'
                      : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Theme Toggle */}
            <button
              type="button"
              onClick={() => setIsDark((prev) => !prev)}
              className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {isDark ? (
                <Sun className="h-4 w-4 text-amber-400" />
              ) : (
                <Moon className="h-4 w-4 text-indigo-500" />
              )}
            </button>
          </div>
        </header>

        {/* Scrollable Message Canvas */}
        <div className="relative flex-1 overflow-hidden">
          <div
            ref={scrollContainerRef}
            onScroll={handleScroll}
            className="h-full overflow-y-auto px-3 py-6 sm:px-6"
          >
            {isLoadingHistory ? (
              <div className="mx-auto max-w-3xl space-y-4">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-20 animate-pulse rounded-2xl bg-slate-200/70 dark:bg-slate-800/60"
                  />
                ))}
              </div>
            ) : activeChannel.messages.length === 0 ? (
              /* Welcome Hero Empty State */
              <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center py-8 text-center">
                <div
                  className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border shadow-sm ${
                    activeMode === 'sales'
                      ? 'border-amber-500/30 bg-amber-500/15 text-amber-500'
                      : 'border-emerald-500/30 bg-emerald-500/15 text-emerald-500'
                  }`}
                >
                  {activeMode === 'sales' ? (
                    <Briefcase className="h-7 w-7" />
                  ) : (
                    <Stethoscope className="h-7 w-7" />
                  )}
                </div>

                <h2 className="font-serif text-2xl font-semibold text-slate-900 dark:text-slate-100">
                  {activeMode === 'sales'
                    ? 'Dr. Sarah Hensley Program Advisor'
                    : 'Dr. Sarah Hensley Clinical Educator'}
                </h2>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                  {activeMode === 'sales'
                    ? 'Personalized guidance for $97 masterclasses, curriculum roadmaps, and coaching bundles tailored to your attachment profile.'
                    : 'Evidence-based clinical guidance on attachment styles, subconscious core wounds, and nervous system regulation with zero sales pitches.'}
                </p>

                <div className="mt-6 grid w-full gap-2.5 sm:grid-cols-2">
                  {modeFilteredPresets.slice(0, 4).map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() =>
                        void handleSubmitMessage(preset.prompt, preset.mode)
                      }
                      className="rounded-xl border border-slate-200 bg-white p-3.5 text-left transition-all hover:-translate-y-0.5 hover:border-emerald-500/40 hover:shadow-md dark:border-slate-800 dark:bg-[#131E32] dark:hover:border-amber-500/40"
                    >
                      <div className="font-mono text-[10px] font-semibold uppercase tracking-wider text-emerald-600 dark:text-amber-400">
                        {preset.category}
                      </div>
                      <div className="mt-1 text-xs font-medium leading-snug text-slate-700 dark:text-slate-200">
                        {preset.prompt}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ) : visibleMessages.length === 0 ? (
              <div className="mx-auto max-w-md py-16 text-center text-sm text-slate-500 dark:text-slate-400">
                No messages match the selected filter (
                <span className="font-semibold">{filter.messageFilter}</span>).
              </div>
            ) : (
              <div className="space-y-5 pb-6">
                {visibleMessages.map((msg) => (
                  <ChatMessage
                    key={msg.id}
                    message={msg}
                    userInitials={userInitials}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Floating Scroll-to-Bottom Button */}
          {showScrollBottomBtn && (
            <button
              type="button"
              onClick={() => scrollToBottom('smooth')}
              className="absolute bottom-4 right-6 z-20 flex h-10 w-10 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-700 shadow-lg transition-transform hover:scale-105 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              title="Scroll to bottom"
              aria-label="Scroll to bottom"
            >
              <ArrowDown className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Sticky Bottom Input Dock */}
        <ChatInput
          value={inputValue}
          isStreaming={isStreaming}
          activeMode={activeMode}
          presets={modeFilteredPresets}
          onChange={setInputValue}
          onSubmit={(prompt) => void handleSubmitMessage(prompt)}
          onStopGeneration={handleStopGeneration}
          onSelectPreset={(preset) =>
            void handleSubmitMessage(preset.prompt, preset.mode)
          }
        />
      </div>

      {/* User Profile, Persona & Theme Modal */}
      <ProfileSettingsModal
        isOpen={profileModalOpen}
        isDark={isDark}
        users={usersCatalog}
        activeUserId={userId}
        systemStats={systemStats}
        onClose={() => setProfileModalOpen(false)}
        onToggleTheme={() => setIsDark((prev) => !prev)}
        onSelectUser={(uid) => void handleSelectUser(uid)}
      />
    </div>
  );
};

export default App;

