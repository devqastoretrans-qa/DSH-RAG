export type BotMode = 'generic' | 'sales';

export type MessageRole = 'user' | 'assistant' | 'system';

export type MessageFilterMode = 'all' | 'user' | 'context';

export type ChronologicalGroup =
  | 'Today'
  | 'Yesterday'
  | 'Previous 7 Days'
  | 'Older';

export interface SourceCitation {
  document: string;
  page?: number | string | null;
  chunk_id?: number | string | null;
  relevance_score?: number | null;
  snippet?: string | null;
  text?: string | null;
  url?: string | null;
}

export interface RecommendedProduct {
  name?: string;
  title?: string;
  price?: string | number;
  description?: string;
  url?: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  mode: BotMode;
  createdAt: number;
  isStreaming?: boolean;
  isStopped?: boolean;
  isError?: boolean;
  errorDetail?: string;
  retryPrompt?: string;
  cached?: boolean;
  latencySec?: string;
  sources?: SourceCitation[];
  recommendedProducts?: RecommendedProduct[];
  retrievalContextSummary?: string;
}

export interface ToastNotification {
  id: string;
  type: 'error' | 'warning' | 'info' | 'success';
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export interface ChatThread {
  session_id: string;
  user_id: string;
  mode: BotMode;
  chat_number?: number;
  title: string;
  message_count: number;
  created_at: number;
  updated_at: number;
}

export interface ChatFilter {
  searchQuery: string;
  messageFilter: MessageFilterMode;
  mode: BotMode;
}

export interface PersonaUser {
  user_id: string;
  name?: string;
  email?: string;
  attachment_style?: string;
  all_purchases?: Array<string | { name?: string; title?: string }>;
}

export interface QuickPromptPreset {
  id: string;
  label: string;
  category: string;
  prompt: string;
  mode: BotMode;
}

