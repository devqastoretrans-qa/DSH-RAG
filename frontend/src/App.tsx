import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown,
  Briefcase,
  Compass,
  Crown,
  Moon,
  PanelLeft,
  SlidersHorizontal,
  Stethoscope,
  Sun,
  Volume2,
  VolumeX,
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
  SuggestedAction,
  ToastNotification,
} from './types/chat';
import { Sidebar } from './components/Sidebar';
import { ChatMessage } from './components/ChatMessage';
import { stopActiveAudioPlayback } from './components/AudioPlayerBar';
import { ChatInput } from './components/ChatInput';
import { ProfileSettingsModal } from './components/ProfileSettingsModal';
import { ToastContainer } from './components/ToastContainer';

const STORAGE_KEYS = {
  token: 'studio_chat_token',
  user: 'studio_active_user',
  mode: 'studio_active_mode',
  sessionGeneric: 'studio_active_session_generic',
  sessionSales: 'studio_active_session_sales',
  sessionPlatform: 'studio_active_session_platform',
  sessionOwner: 'studio_active_session_owner',
} as const;

const REQUEST_TIMEOUT_MS = 15000;
const STREAM_TIMEOUT_MS = 90000;

function createSessionId(mode: BotMode): string {
  const prefix =
    mode === 'sales'
      ? 'sess_sales_'
      : mode === 'platform'
      ? 'sess_platform_'
      : mode === 'owner'
      ? 'sess_owner_'
      : 'sess_clinical_';
  const rand =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 10)
      : Math.random().toString(36).substring(2, 12);
  return `${prefix}${rand}`;
}

function getDefaultTitle(mode: BotMode): string {
  if (mode === 'sales') return 'New Program Advisor Chat';
  if (mode === 'platform') return 'New Platform Help Chat';
  if (mode === 'owner') return 'New Owner Agent Chat';
  return 'New Clinical Chat';
}

function getStoredSessionId(mode: BotMode): string | null {
  try {
    const key =
      mode === 'sales'
        ? STORAGE_KEYS.sessionSales
        : mode === 'platform'
        ? STORAGE_KEYS.sessionPlatform
        : mode === 'owner'
        ? STORAGE_KEYS.sessionOwner
        : STORAGE_KEYS.sessionGeneric;
    const saved = sessionStorage.getItem(key);
    return saved && saved.trim() ? saved.trim() : null;
  } catch {
    return null;
  }
}

function persistSessionId(mode: BotMode, sessionId: string): void {
  try {
    const key =
      mode === 'sales'
        ? STORAGE_KEYS.sessionSales
        : mode === 'platform'
        ? STORAGE_KEYS.sessionPlatform
        : mode === 'owner'
        ? STORAGE_KEYS.sessionOwner
        : STORAGE_KEYS.sessionGeneric;
    sessionStorage.setItem(key, sessionId);
  } catch {
    // Ignore storage quota errors
  }
}

async function parseHttpErrorMessage(res: Response): Promise<string> {
  const fallback = `Request failed with HTTP ${res.status}`;
  try {
    const text = await res.text();
    if (!text) return fallback;
    try {
      const parsed = JSON.parse(text) as {
        error?: string;
        detail?: unknown;
        message?: string;
      };
      if (typeof parsed.error === 'string' && parsed.error.trim()) {
        return parsed.error.trim();
      }
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
        return parsed.detail.trim();
      }
      if (Array.isArray(parsed.detail) && parsed.detail.length > 0) {
        const first = parsed.detail[0] as { msg?: string };
        if (first?.msg) return first.msg;
      }
      if (typeof parsed.message === 'string' && parsed.message.trim()) {
        return parsed.message.trim();
      }
    } catch {
      return text.slice(0, 200);
    }
  } catch {
    return fallback;
  }
  return fallback;
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
  {
    id: 'platform_login',
    category: 'Platform',
    label: 'How do I log into my account?',
    prompt: 'How do I log into my account?',
    mode: 'platform',
  },
  {
    id: 'platform_password',
    category: 'Platform',
    label: 'Reset forgotten password',
    prompt: 'How do I reset a forgotten password?',
    mode: 'platform',
  },
  {
    id: 'platform_workbooks',
    category: 'Platform',
    label: 'Find courses & workbooks',
    prompt: 'Where do I find my course dashboard and download workbooks?',
    mode: 'platform',
  },
  {
    id: 'platform_billing',
    category: 'Platform',
    label: 'Billing & support',
    prompt: 'How do I check my billing receipts or contact support?',
    mode: 'platform',
  },
  {
    id: 'owner_trap',
    category: 'Dr. Sarah Voice',
    label: 'Anxious-avoidant trap',
    prompt: 'In your clinical experience, why do anxious and avoidant partners keep triggering each other?',
    mode: 'owner',
  },
  {
    id: 'owner_wounds',
    category: 'Core Wounds',
    label: 'Heal abandonment core wounds',
    prompt: 'How do you help clients reprogram deep subconscious abandonment wounds so they feel safe in love?',
    mode: 'owner',
  },
  {
    id: 'owner_conflict',
    category: 'Relationship Repair',
    label: 'When a partner shuts down',
    prompt: 'When my partner shuts down during conflict, what is the healthiest way for me to respond?',
    mode: 'owner',
  },
  {
    id: 'owner_security',
    category: 'Earned Security',
    label: 'What earned security feels like',
    prompt: 'What does earning secure attachment actually look and feel like in everyday relationships?',
    mode: 'owner',
  },
];

interface ChannelBuffer {
  sessionId: string;
  messages: ChatMessageType[];
  title: string;
}

export const App: React.FC = () => {
  const initialMode: BotMode = (() => {
    try {
      const m = sessionStorage.getItem(STORAGE_KEYS.mode);
      if (m === 'sales' || m === 'platform' || m === 'owner') return m;
      return 'generic';
    } catch {
      return 'generic';
    }
  })();

  const initialUserId: string = (() => {
    try {
      const u = sessionStorage.getItem(STORAGE_KEYS.user);
      return u && u.trim() ? u.trim() : '1836';
    } catch {
      return '1836';
    }
  })();

  const [isDark, setIsDark] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [profileModalOpen, setProfileModalOpen] = useState(false);

  const [filter, setFilter] = useState<ChatFilter>({
    searchQuery: '',
    messageFilter: 'all',
    mode: initialMode,
  });

  const [userId, setUserId] = useState(initialUserId);
  const [authToken, setAuthToken] = useState('');
  const [usersCatalog, setUsersCatalog] = useState<PersonaUser[]>([]);
  const [systemStats, setSystemStats] = useState<{
    documents?: number;
    conversationTurns?: number;
    users?: number;
  }>({});

  const [channels, setChannels] = useState<Record<BotMode, ChannelBuffer>>(() => {
    const genSid = getStoredSessionId('generic') || createSessionId('generic');
    const salesSid = getStoredSessionId('sales') || createSessionId('sales');
    const platSid = getStoredSessionId('platform') || createSessionId('platform');
    const ownerSid = getStoredSessionId('owner') || createSessionId('owner');
    persistSessionId('generic', genSid);
    persistSessionId('sales', salesSid);
    persistSessionId('platform', platSid);
    persistSessionId('owner', ownerSid);
    return {
      generic: {
        sessionId: genSid,
        messages: [],
        title: getDefaultTitle('generic'),
      },
      sales: {
        sessionId: salesSid,
        messages: [],
        title: getDefaultTitle('sales'),
      },
      platform: {
        sessionId: platSid,
        messages: [],
        title: getDefaultTitle('platform'),
      },
      owner: {
        sessionId: ownerSid,
        messages: [],
        title: getDefaultTitle('owner'),
      },
    };
  });

  const [threadsByMode, setThreadsByMode] = useState<
    Record<BotMode, ChatThread[]>
  >({
    generic: [],
    sales: [],
    platform: [],
    owner: [],
  });
  const [platformGreeting, setPlatformGreeting] = useState('Hi there!');
  const [platformActions, setPlatformActions] = useState<SuggestedAction[]>([]);
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [showScrollBottomBtn, setShowScrollBottomBtn] = useState(false);
  const [toasts, setToasts] = useState<ToastNotification[]>([]);
  const [autoReadOwner, setAutoReadOwner] = useState(false);
  const [autoPlayMsgId, setAutoPlayMsgId] = useState<string | null>(null);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const autoReadOwnerRef = useRef(autoReadOwner);
  autoReadOwnerRef.current = autoReadOwner;
  const activeRequestSeqRef = useRef(0);
  const selectThreadSeqRef = useRef(0);
  const isSubmittingRef = useRef(false);
  const msgCounterRef = useRef(0);
  const channelsRef = useRef(channels);
  channelsRef.current = channels;

  const activeMode = filter.mode;
  const activeChannel = channels[activeMode];
  const activeThreads = threadsByMode[activeMode];

  const nextMsgId = useCallback((prefix: string) => {
    msgCounterRef.current += 1;
    return `${prefix}_${Date.now()}_${msgCounterRef.current}`;
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const pushToast = useCallback(
    (toast: Omit<ToastNotification, 'id'>) => {
      const id = nextMsgId('toast');
      setToasts((prev) => [...prev.slice(-3), { ...toast, id }]);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 6500);
    },
    [nextMsgId]
  );

  // Persist active mode for tab reload recovery
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEYS.mode, activeMode);
    } catch {
      // ignore
    }
  }, [activeMode]);

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

  const abortActiveStream = useCallback(() => {
    activeRequestSeqRef.current += 1;
    isSubmittingRef.current = false;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  useEffect(() => {
    stopActiveAudioPlayback();
    setAutoPlayMsgId(null);
  }, [activeMode]);

  useEffect(() => {
    return () => stopActiveAudioPlayback();
  }, []);

  const fetchWithTimeout = useCallback(
    async (
      input: RequestInfo | URL,
      init: RequestInit = {},
      timeoutMs: number = REQUEST_TIMEOUT_MS
    ): Promise<Response> => {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(
        () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
        timeoutMs
      );
      try {
        return await fetch(input, {
          ...init,
          signal: init.signal || controller.signal,
        });
      } finally {
        window.clearTimeout(timeoutId);
      }
    },
    []
  );

  const fetchThreads = useCallback(
    async (mode: BotMode, tokenOverride?: string) => {
      const tok = tokenOverride ?? authToken;
      if (!tok) return;
      setIsLoadingThreads(true);
      try {
        const res = await fetchWithTimeout(
          `/api/chat/sessions?mode=${encodeURIComponent(mode)}&limit=50`,
          { headers: buildAuthHeaders(tok) }
        );
        if (!res.ok) {
          const msg = await parseHttpErrorMessage(res);
          pushToast({
            type: 'warning',
            title: 'Session Sync Warning',
            message: msg,
          });
          return;
        }
        const data = (await res.json()) as { sessions?: ChatThread[] };
        const clean = (data.sessions || []).filter(
          (s) => (s.mode || 'generic') === mode
        );
        setThreadsByMode((prev) => ({ ...prev, [mode]: clean }));
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          pushToast({
            type: 'error',
            title: 'Failed to Load Chat History',
            message: 'Network error while fetching past conversations.',
          });
        }
      } finally {
        setIsLoadingThreads(false);
      }
    },
    [authToken, buildAuthHeaders, fetchWithTimeout, pushToast]
  );

  const authenticateUser = useCallback(
    async (targetUserId: string) => {
      try {
        const res = await fetchWithTimeout('/api/auth/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: targetUserId }),
        });
        if (!res.ok) {
          const msg = await parseHttpErrorMessage(res);
          pushToast({
            type: 'error',
            title: 'Authentication Error',
            message: msg,
          });
          return '';
        }
        const data = (await res.json()) as { token?: string };
        const tok = data.token || '';
        setAuthToken(tok);
        try {
          sessionStorage.setItem(STORAGE_KEYS.token, tok);
          sessionStorage.setItem(STORAGE_KEYS.user, targetUserId);
        } catch {
          // ignore
        }
        return tok;
      } catch {
        pushToast({
          type: 'error',
          title: 'Connection Error',
          message: 'Unable to authenticate session with backend.',
        });
        return '';
      }
    },
    [fetchWithTimeout, pushToast]
  );

  const hydrateThreadMessages = useCallback(
    async (
      sessionId: string,
      targetMode: BotMode,
      titleFallback?: string,
      tokenOverride?: string,
      silentIfNotFound: boolean = false
    ) => {
      const seq = ++selectThreadSeqRef.current;
      setIsLoadingHistory(true);
      try {
        const res = await fetchWithTimeout(
          `/api/chats/${encodeURIComponent(
            sessionId
          )}/messages?mode=${encodeURIComponent(targetMode)}`,
          { headers: buildAuthHeaders(tokenOverride) }
        );
        if (seq !== selectThreadSeqRef.current) return;

        if (res.status === 404 && silentIfNotFound) {
          return;
        }
        if (!res.ok) {
          const errMsg = await parseHttpErrorMessage(res);
          pushToast({
            type: 'error',
            title: `Could Not Load Thread (${res.status})`,
            message: errMsg,
          });
          return;
        }

        const data = (await res.json()) as {
          turns?: Array<{
            role: 'user' | 'assistant' | 'system';
            content: string;
            mode?: BotMode;
            created_at?: number;
          }>;
          messages?: Array<{
            role: 'user' | 'assistant' | 'system';
            content: string;
            mode?: BotMode;
            created_at?: number;
          }>;
        };

        const rawList = data.messages || data.turns || [];
        const mapped: ChatMessageType[] = rawList.map((t, idx) => ({
          id: `${sessionId}_turn_${idx}`,
          role:
            t.role === 'user'
              ? 'user'
              : t.role === 'system'
              ? 'system'
              : 'assistant',
          content: t.content,
          mode: (t.mode as BotMode) || targetMode,
          createdAt: t.created_at || Date.now() / 1000,
        }));

        const firstUserTurn = mapped.find((m) => m.role === 'user');
        const derivedTitle =
          titleFallback ||
          (firstUserTurn ? firstUserTurn.content.slice(0, 60) : getDefaultTitle(targetMode));

        persistSessionId(targetMode, sessionId);
        setChannels((prev) => ({
          ...prev,
          [targetMode]: {
            sessionId,
            messages: mapped,
            title: derivedTitle,
          },
        }));
      } catch (err) {
        if ((err as Error).name !== 'AbortError' && !silentIfNotFound) {
          pushToast({
            type: 'error',
            title: 'Network Error',
            message: 'Failed to load conversation messages. Please try again.',
          });
        }
      } finally {
        if (seq === selectThreadSeqRef.current) {
          setIsLoadingHistory(false);
        }
      }
    },
    [buildAuthHeaders, fetchWithTimeout, pushToast]
  );

  const handleSelectUser = useCallback(
    async (nextUserId: string) => {
      abortActiveStream();
      try {
        sessionStorage.removeItem(STORAGE_KEYS.sessionGeneric);
        sessionStorage.removeItem(STORAGE_KEYS.sessionSales);
        sessionStorage.removeItem(STORAGE_KEYS.sessionPlatform);
        sessionStorage.removeItem(STORAGE_KEYS.sessionOwner);
        sessionStorage.removeItem(STORAGE_KEYS.token);
      } catch {
        // ignore
      }
      setUserId(nextUserId);
      setThreadsByMode({ generic: [], sales: [], platform: [], owner: [] });
      const genSid = createSessionId('generic');
      const salesSid = createSessionId('sales');
      const platSid = createSessionId('platform');
      const ownerSid = createSessionId('owner');
      persistSessionId('generic', genSid);
      persistSessionId('sales', salesSid);
      persistSessionId('platform', platSid);
      persistSessionId('owner', ownerSid);
      setChannels({
        generic: {
          sessionId: genSid,
          messages: [],
          title: getDefaultTitle('generic'),
        },
        sales: {
          sessionId: salesSid,
          messages: [],
          title: getDefaultTitle('sales'),
        },
        platform: {
          sessionId: platSid,
          messages: [],
          title: getDefaultTitle('platform'),
        },
        owner: {
          sessionId: ownerSid,
          messages: [],
          title: getDefaultTitle('owner'),
        },
      });
      const tok = await authenticateUser(nextUserId);
      if (tok) {
        await fetchThreads(filter.mode, tok);
      }
    },
    [abortActiveStream, authenticateUser, fetchThreads, filter.mode]
  );

  // Initial startup load + mid-conversation reload re-hydration
  useEffect(() => {
    let mounted = true;
    const boot = async () => {
      try {
        const [usersRes, statsRes] = await Promise.all([
          fetchWithTimeout('/api/users').catch(() => null),
          fetchWithTimeout('/api/system/stats').catch(() => null),
        ]);
        if (!mounted) return;
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

      const tok = await authenticateUser(initialUserId);
      if (!mounted || !tok) return;

      await fetchThreads(initialMode, tok);
      const savedSid = getStoredSessionId(initialMode);
      if (savedSid) {
        await hydrateThreadMessages(savedSid, initialMode, undefined, tok, true);
      }
    };
    void boot();
    return () => {
      mounted = false;
      abortControllerRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch personalized Platform Help greeting & page-aware quick-reply chips
  useEffect(() => {
    let active = true;
    const currentPage = `${window.location.pathname || '/'}${window.location.search || ''}`;
    const loadPlatformContext = async () => {
      try {
        const res = await fetchWithTimeout(
          `/api/platform-widget/context?current_page=${encodeURIComponent(currentPage)}`,
          { headers: buildAuthHeaders() }
        );
        if (!res.ok || !active) return;
        const data = (await res.json()) as {
          greeting_line?: string;
          suggested_actions?: SuggestedAction[];
        };
        if (!active) return;
        if (data.greeting_line) setPlatformGreeting(data.greeting_line);
        if (Array.isArray(data.suggested_actions) && data.suggested_actions.length > 0) {
          setPlatformActions(data.suggested_actions);
        }
      } catch {
        // Non-blocking context lookup
      }
    };
    void loadPlatformContext();
    return () => {
      active = false;
    };
  }, [authToken, userId, buildAuthHeaders, fetchWithTimeout]);

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
      if (nextMode === activeMode) return;
      abortActiveStream();
      setFilter((prev) => ({ ...prev, mode: nextMode }));
      void fetchThreads(nextMode);
    },
    [abortActiveStream, activeMode, fetchThreads]
  );

  const handleNewChat = useCallback(() => {
    abortActiveStream();
    selectThreadSeqRef.current += 1;
    setIsLoadingHistory(false);
    const freshSessionId = createSessionId(activeMode);
    persistSessionId(activeMode, freshSessionId);
    setChannels((prev) => ({
      ...prev,
      [activeMode]: {
        sessionId: freshSessionId,
        messages: [],
        title: getDefaultTitle(activeMode),
      },
    }));
  }, [abortActiveStream, activeMode]);

  const handleSelectThread = useCallback(
    async (thread: ChatThread) => {
      abortActiveStream();
      const targetMode = thread.mode || activeMode;
      setFilter((prev) => ({ ...prev, mode: targetMode }));
      persistSessionId(targetMode, thread.session_id);
      setChannels((prev) => ({
        ...prev,
        [targetMode]: {
          ...prev[targetMode],
          sessionId: thread.session_id,
          title: thread.title || 'Conversation',
        },
      }));
      await hydrateThreadMessages(
        thread.session_id,
        targetMode,
        thread.title || 'Conversation'
      );
      window.setTimeout(() => scrollToBottom('auto'), 40);
    },
    [abortActiveStream, activeMode, hydrateThreadMessages, scrollToBottom]
  );

  const handleRenameThread = useCallback(
    async (sessionId: string, newTitle: string) => {
      try {
        const res = await fetchWithTimeout(
          `/api/chat/sessions/${encodeURIComponent(sessionId)}`,
          {
            method: 'PATCH',
            headers: buildAuthHeaders(undefined, {
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ title: newTitle }),
          }
        );
        if (!res.ok) {
          const msg = await parseHttpErrorMessage(res);
          pushToast({
            type: 'error',
            title: 'Rename Failed',
            message: msg,
          });
          return;
        }
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
      } catch {
        pushToast({
          type: 'error',
          title: 'Network Error',
          message: 'Unable to rename conversation.',
        });
      }
    },
    [activeMode, buildAuthHeaders, fetchWithTimeout, pushToast]
  );

  const handleDeleteThread = useCallback(
    async (sessionId: string) => {
      const isViewingDeleted = channelsRef.current[activeMode].sessionId === sessionId;
      if (isViewingDeleted) {
        abortActiveStream();
      }
      try {
        const res = await fetchWithTimeout(
          `/api/chat/sessions/${encodeURIComponent(sessionId)}`,
          {
            method: 'DELETE',
            headers: buildAuthHeaders(),
          }
        );
        if (!res.ok && res.status !== 404) {
          const msg = await parseHttpErrorMessage(res);
          pushToast({
            type: 'error',
            title: 'Delete Failed',
            message: msg,
          });
          return;
        }
        setThreadsByMode((prev) => ({
          ...prev,
          [activeMode]: prev[activeMode].filter((t) => t.session_id !== sessionId),
        }));
        if (isViewingDeleted) {
          handleNewChat();
        } else {
          void fetchThreads(activeMode);
        }
      } catch {
        pushToast({
          type: 'error',
          title: 'Network Error',
          message: 'Failed to delete conversation.',
        });
      }
    },
    [abortActiveStream, activeMode, buildAuthHeaders, fetchThreads, fetchWithTimeout, handleNewChat, pushToast]
  );

  const handleClearHistory = useCallback(async () => {
    abortActiveStream();
    try {
      const res = await fetchWithTimeout(
        `/api/chat/sessions?mode=${encodeURIComponent(activeMode)}`,
        {
          method: 'DELETE',
          headers: buildAuthHeaders(),
        }
      );
      if (!res.ok) {
        const msg = await parseHttpErrorMessage(res);
        pushToast({
          type: 'error',
          title: 'Clear History Failed',
          message: msg,
        });
        return;
      }
      setThreadsByMode((prev) => ({ ...prev, [activeMode]: [] }));
      handleNewChat();
    } catch {
      pushToast({
        type: 'error',
        title: 'Network Error',
        message: 'Unable to clear conversation history.',
      });
    }
  }, [abortActiveStream, activeMode, buildAuthHeaders, fetchWithTimeout, handleNewChat, pushToast]);

  const handleStopGeneration = useCallback(() => {
    abortActiveStream();
  }, [abortActiveStream]);

  const handleSubmitMessage = useCallback(
    async (
      overridePrompt?: string,
      overrideMode?: BotMode,
      options?: { replaceErrorMsgId?: string; skipUserEcho?: boolean }
    ) => {
      const targetMode = overrideMode || activeMode;
      const text = (overridePrompt ?? inputValue).trim();
      if (!text || isSubmittingRef.current) return;

      if (text.length > 50000) {
        pushToast({
          type: 'warning',
          title: 'Prompt Too Long',
          message: 'Please keep messages under 50,000 characters.',
        });
        return;
      }

      // Synchronous re-entrancy lock prevents rapid-fire race conditions
      isSubmittingRef.current = true;
      const reqSeq = ++activeRequestSeqRef.current;

      if (overrideMode && overrideMode !== activeMode) {
        setFilter((prev) => ({ ...prev, mode: overrideMode }));
      }

      const channelSnapshot = channelsRef.current[targetMode];
      const sessionId = channelSnapshot.sessionId;
      persistSessionId(targetMode, sessionId);

      const isFirstMessage = channelSnapshot.messages.length === 0;
      const nextTitle = isFirstMessage
        ? text.slice(0, 60)
        : channelSnapshot.title;

      const userMsg: ChatMessageType | null = options?.skipUserEcho
        ? null
        : {
            id: nextMsgId('user'),
            role: 'user',
            content: text,
            mode: targetMode,
            createdAt: Date.now(),
          };

      const assistantMsgId = nextMsgId('bot');
      const placeholderBotMsg: ChatMessageType = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        mode: targetMode,
        createdAt: Date.now(),
        isStreaming: true,
        retryPrompt: text,
      };

      if (!overridePrompt) {
        setInputValue('');
      }
      setIsStreaming(true);

      setChannels((prev) => {
        const baseMessages = options?.replaceErrorMsgId
          ? prev[targetMode].messages.filter(
              (m) => m.id !== options.replaceErrorMsgId
            )
          : prev[targetMode].messages;
        return {
          ...prev,
          [targetMode]: {
            ...prev[targetMode],
            title: nextTitle,
            messages: [
              ...baseMessages,
              ...(userMsg ? [userMsg] : []),
              placeholderBotMsg,
            ],
          },
        };
      });

      const controller = new AbortController();
      abortControllerRef.current = controller;
      const timeoutId = window.setTimeout(
        () =>
          controller.abort(
            new DOMException('Response timed out after 90s', 'TimeoutError')
          ),
        STREAM_TIMEOUT_MS
      );
      const startTime = performance.now();

      const updateAssistantMsg = (
        updater: (prevMsg: ChatMessageType) => ChatMessageType
      ) => {
        setChannels((prev) => {
          // Strict guard: never mutate a switched/new session or stale superseded request
          if (
            activeRequestSeqRef.current !== reqSeq ||
            prev[targetMode].sessionId !== sessionId
          ) {
            return prev;
          }
          return {
            ...prev,
            [targetMode]: {
              ...prev[targetMode],
              messages: prev[targetMode].messages.map((m) =>
                m.id === assistantMsgId ? updater(m) : m
              ),
            },
          };
        });
      };

      try {
        const currentPage = `${window.location.pathname || '/'}${window.location.search || ''}`;
        const res = await fetch('/chat/stream', {
          method: 'POST',
          headers: buildAuthHeaders(undefined, {
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify({
            session_id: sessionId,
            message: text,
            mode: targetMode,
            ...(targetMode === 'platform' ? { current_page: currentPage } : {}),
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const errMsg = await parseHttpErrorMessage(res);
          const apiErr = new Error(errMsg) as Error & { status?: number };
          apiErr.status = res.status;
          throw apiErr;
        }

        if (!res.body) {
          throw new Error('Streaming response body unavailable.');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let sseBuffer = '';
        let accumulated = '';
        let receivedDonePayload = false;

        const processLine = (rawLine: string) => {
          const line = rawLine.trim();
          if (!line.startsWith('data:')) return;
          const jsonStr = line.slice(5).trim();
          if (!jsonStr || jsonStr === '[DONE]') return;

          const payload = JSON.parse(jsonStr) as {
            token?: string;
            done?: boolean;
            answer?: string;
            full_answer?: string;
            sources?: SourceCitation[] | null;
            recommended_products?: RecommendedProduct[] | null;
            suggested_actions?: SuggestedAction[] | null;
            cached?: boolean;
          };

          if (typeof payload.token === 'string' && payload.token.length > 0) {
            accumulated += payload.token;
            updateAssistantMsg((m) => ({
              ...m,
              content: accumulated,
              isStreaming: true,
            }));
          } else if (payload.done || payload.answer !== undefined) {
            receivedDonePayload = true;
            if (
              targetMode === 'platform' &&
              Array.isArray(payload.suggested_actions) &&
              payload.suggested_actions.length > 0
            ) {
              setPlatformActions(payload.suggested_actions);
            }
            const finalAns =
              payload.answer || payload.full_answer || accumulated || 'No response generated.';
            const latencySec = (
              (performance.now() - startTime) /
              1000
            ).toFixed(2);
            const sources = Array.isArray(payload.sources)
              ? payload.sources.filter(Boolean)
              : [];
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
              recommendedProducts: Array.isArray(payload.recommended_products)
                ? payload.recommended_products
                : [],
              retrievalContextSummary:
                sources.length > 0
                  ? `${sources.length} vector chunk${
                      sources.length === 1 ? '' : 's'
                    } (${docNames})`
                  : undefined,
            }));

            if (targetMode === 'owner' && autoReadOwnerRef.current && finalAns.trim()) {
              setAutoPlayMsgId(assistantMsgId);
            }
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (
            activeRequestSeqRef.current !== reqSeq ||
            controller.signal.aborted
          ) {
            await reader.cancel().catch(() => undefined);
            break;
          }

          sseBuffer += decoder.decode(value, { stream: true });
          const lines = sseBuffer.split(/\r?\n/);
          sseBuffer = lines.pop() ?? '';

          for (const line of lines) {
            try {
              processLine(line);
            } catch {
              // Malformed JSON line in stream; continue reading remaining chunks safely
            }
          }
        }

        if (sseBuffer.trim()) {
          try {
            processLine(sseBuffer);
          } catch {
            // Ignore trailing incomplete frame
          }
        }

        if (
          activeRequestSeqRef.current === reqSeq &&
          !controller.signal.aborted &&
          !receivedDonePayload &&
          accumulated.length === 0
        ) {
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
              ...(targetMode === 'platform' ? { current_page: currentPage } : {}),
            }),
            signal: controller.signal,
          });
          if (!fallbackRes.ok) {
            const errMsg = await parseHttpErrorMessage(fallbackRes);
            const apiErr = new Error(errMsg) as Error & { status?: number };
            apiErr.status = fallbackRes.status;
            throw apiErr;
          }
          const data = (await fallbackRes.json()) as {
            answer?: string;
            sources?: SourceCitation[] | null;
            recommended_products?: RecommendedProduct[] | null;
            cached?: boolean;
          };
          const latencySec = ((performance.now() - startTime) / 1000).toFixed(2);
          const sources = Array.isArray(data.sources)
            ? data.sources.filter(Boolean)
            : [];
          updateAssistantMsg((m) => ({
            ...m,
            content: data.answer || 'No response generated.',
            isStreaming: false,
            cached: Boolean(data.cached),
            latencySec,
            sources,
            recommendedProducts: Array.isArray(data.recommended_products)
              ? data.recommended_products
              : [],
          }));
          if (targetMode === 'owner' && autoReadOwnerRef.current && (data.answer || '').trim()) {
            setAutoPlayMsgId(assistantMsgId);
          }
        } else if (!receivedDonePayload) {
          updateAssistantMsg((m) => ({ ...m, isStreaming: false }));
        }
      } catch (err) {
        const errorObj = err as Error & { status?: number };
        const isTimeout =
          errorObj.name === 'TimeoutError' ||
          (controller.signal.reason &&
            (controller.signal.reason as Error).name === 'TimeoutError');

        if (errorObj.name === 'AbortError' && !isTimeout) {
          updateAssistantMsg((m) => ({
            ...m,
            content: m.content || 'Generation stopped by user.',
            isStreaming: false,
            isStopped: true,
          }));
        } else {
          const detail = isTimeout
            ? 'The server took too long to respond (request timed out).'
            : errorObj.message || 'Connection error while generating response.';
          updateAssistantMsg((m) => ({
            ...m,
            content: `${detail}`,
            isStreaming: false,
            isError: true,
            errorDetail: detail,
            retryPrompt: text,
          }));
          pushToast({
            type: 'error',
            title: isTimeout
              ? 'Request Timed Out'
              : errorObj.status
              ? `Server Error (${errorObj.status})`
              : 'Network Error',
            message: detail,
            actionLabel: 'Retry',
            onAction: () => {
              void handleSubmitMessage(text, targetMode, {
                replaceErrorMsgId: assistantMsgId,
                skipUserEcho: true,
              });
            },
          });
        }
      } finally {
        window.clearTimeout(timeoutId);
        // Only clear global streaming locks if this request is still the active one
        if (activeRequestSeqRef.current === reqSeq) {
          isSubmittingRef.current = false;
          setIsStreaming(false);
          if (abortControllerRef.current === controller) {
            abortControllerRef.current = null;
          }
          void fetchThreads(targetMode);
        }
      }
    },
    [
      activeMode,
      buildAuthHeaders,
      fetchThreads,
      inputValue,
      nextMsgId,
      pushToast,
    ]
  );

  const handleRetryMessage = useCallback(
    (failedMessage: ChatMessageType) => {
      if (!failedMessage.retryPrompt) return;
      void handleSubmitMessage(failedMessage.retryPrompt, failedMessage.mode, {
        replaceErrorMsgId: failedMessage.id,
        skipUserEcho: true,
      });
    },
    [handleSubmitMessage]
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

  const modeFilteredPresets = useMemo(() => {
    if (activeMode === 'platform') {
      if (platformActions.length > 0) {
        return platformActions.map((act, idx) => ({
          id: `platform_ctx_${idx}`,
          category: 'Platform',
          label: act.label,
          prompt: act.prompt,
          mode: 'platform' as const,
        }));
      }
      return QUICK_PRESETS.filter((p) => p.mode === 'platform');
    }
    if (activeMode === 'owner') {
      return QUICK_PRESETS.filter((p) => p.mode === 'owner');
    }
    return QUICK_PRESETS.filter(
      (p) => p.mode === activeMode || p.mode === 'generic'
    );
  }, [activeMode, platformActions]);

  return (
    <div className="flex h-dvh w-screen overflow-hidden bg-slate-50 text-slate-900 dark:bg-[#0B1120] dark:text-slate-100">
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

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
        <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 bg-white/85 px-3 py-2.5 backdrop-blur-md dark:border-slate-800/80 dark:bg-[#0B1120]/90 sm:px-5 xl:flex-nowrap">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
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
          <div className="flex shrink-0 flex-wrap items-center gap-2">
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
              <button
                type="button"
                onClick={() => handleModeSwitch('platform')}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  activeMode === 'platform'
                    ? 'bg-sky-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Compass className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Platform Help</span>
                <span className="sm:hidden">Platform</span>
              </button>
              <button
                type="button"
                onClick={() => handleModeSwitch('owner')}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  activeMode === 'owner'
                    ? 'bg-violet-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Crown className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Owner Agent</span>
                <span className="sm:hidden">Owner</span>
              </button>
            </div>

            {activeMode === 'owner' && (
              <button
                type="button"
                onClick={() => {
                  const next = !autoReadOwner;
                  setAutoReadOwner(next);
                  if (!next) {
                    setAutoPlayMsgId(null);
                    stopActiveAudioPlayback();
                  }
                }}
                className={`inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-medium transition-colors ${
                  autoReadOwner
                    ? 'border-violet-500/50 bg-violet-500/15 text-violet-700 dark:text-violet-300'
                    : 'border-slate-200 bg-slate-100 text-slate-600 hover:text-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
                title="Automatically read new Owner Agent replies aloud using ElevenLabs"
              >
                {autoReadOwner ? (
                  <Volume2 className="h-3.5 w-3.5" />
                ) : (
                  <VolumeX className="h-3.5 w-3.5" />
                )}
                <span className="hidden sm:inline">
                  {autoReadOwner ? 'Voice: Auto' : 'Voice: Manual'}
                </span>
              </button>
            )}

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
              <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center py-8 text-center">
                <div
                  className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border shadow-sm ${
                    activeMode === 'sales'
                      ? 'border-amber-500/30 bg-amber-500/15 text-amber-500'
                      : activeMode === 'platform'
                      ? 'border-sky-500/30 bg-sky-500/15 text-sky-500'
                      : activeMode === 'owner'
                      ? 'border-violet-500/30 bg-violet-500/15 text-violet-500'
                      : 'border-emerald-500/30 bg-emerald-500/15 text-emerald-500'
                  }`}
                >
                  {activeMode === 'sales' ? (
                    <Briefcase className="h-7 w-7" />
                  ) : activeMode === 'platform' ? (
                    <Compass className="h-7 w-7" />
                  ) : activeMode === 'owner' ? (
                    <Crown className="h-7 w-7" />
                  ) : (
                    <Stethoscope className="h-7 w-7" />
                  )}
                </div>

                <h2 className="font-serif text-2xl font-semibold text-slate-900 dark:text-slate-100">
                  {activeMode === 'sales'
                    ? 'Dr. Sarah Hensley Program Advisor'
                    : activeMode === 'platform'
                    ? 'Dr. Sarah Hensley Platform Navigation Assistant'
                    : activeMode === 'owner'
                    ? 'Dr. Sarah Hensley — Owner Agent'
                    : 'Dr. Sarah Hensley Clinical Educator'}
                </h2>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                  {activeMode === 'sales'
                    ? 'Personalized guidance for $97 masterclasses, curriculum roadmaps, and coaching bundles tailored to your attachment profile.'
                    : activeMode === 'platform'
                    ? `${platformGreeting} Step-by-step help with website login, password reset, course dashboards, PDF workbooks, billing, and account support.`
                    : activeMode === 'owner'
                    ? "Speak directly with Dr. Sarah Hensley's first-person founder voice grounded in her clinical attachment frameworks and subconscious relational reprogramming work."
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
                    onRetry={handleRetryMessage}
                    buildAuthHeaders={buildAuthHeaders}
                    autoPlayAudio={autoPlayMsgId === msg.id}
                    onAudioError={(detail) =>
                      pushToast({
                        type: 'error',
                        title: 'Voice Unavailable',
                        message: detail,
                      })
                    }
                  />
                ))}
              </div>
            )}
          </div>

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
