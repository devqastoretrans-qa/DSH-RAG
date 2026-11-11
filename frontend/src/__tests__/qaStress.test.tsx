import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import App from '../App';
import {
  ChatMessage,
  renderSafeMarkdownHtml,
  splitMarkdownAndCode,
} from '../components/ChatMessage';
import { SourceAccordion } from '../components/SourceAccordion';
import { ChatHistory } from '../components/ChatHistory';
import { ErrorBoundary } from '../components/ErrorBoundary';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeControlledStream() {
  let ctrl!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      ctrl = controller;
    },
  });
  const enc = new TextEncoder();
  return {
    stream,
    push(sseChunk: string) {
      ctrl.enqueue(enc.encode(sseChunk));
    },
    close() {
      ctrl.close();
    },
  };
}

describe('QA Vector 1: Rapid Interaction & Stream Abort Isolation', () => {
  beforeEach(() => {
    sessionStorage.clear();
    Element.prototype.scrollTo = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('aborts active stream cleanly on New Chat / Switch Thread without buffer bleed', async () => {
    const controlled = makeControlledStream();
    let abortedSignal: AbortSignal | undefined;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/users')) return jsonResponse({ users: [{ user_id: '1836', name: 'Test User' }] });
      if (url.includes('/api/system/stats')) return jsonResponse({ documents_count: 10 });
      if (url.includes('/api/auth/token')) return jsonResponse({ token: 'tok_123' });
      if (url.includes('/api/chat/sessions')) {
        return jsonResponse({
          sessions: [
            {
              session_id: 'sess_past_1',
              user_id: '1836',
              mode: 'generic',
              chat_number: 1,
              title: 'Past Clinical Thread',
              message_count: 2,
              created_at: Math.floor(Date.now() / 1000),
              updated_at: Math.floor(Date.now() / 1000),
            },
          ],
        });
      }
      if (url.includes('/api/chats/sess_past_1/messages')) {
        return jsonResponse({
          messages: [
            { role: 'user', content: 'Old Q', mode: 'generic', created_at: 1700000000 },
            { role: 'assistant', content: 'Old A', mode: 'generic', created_at: 1700000001 },
          ],
        });
      }
      if (url.includes('/chat/stream')) {
        abortedSignal = init?.signal as AbortSignal | undefined;
        // Emit 1 chunk immediately, keep stream open
        controlled.push(`data: ${JSON.stringify({ token: 'BLEED_SHOULD_NOT_APPEAR ' })}\n\n`);
        return new Response(controlled.stream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }
      return jsonResponse({});
    });

    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const textarea = await screen.findByPlaceholderText(/Clinical Educator AI/i);
    fireEvent.change(textarea, { target: { value: 'Rapid question 1' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // Even if user fires Enter again immediately before state settles, only 1 /chat/stream runs
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(/BLEED_SHOULD_NOT_APPEAR/)).toBeInTheDocument();
    });

    const streamCalls = fetchMock.mock.calls.filter(([u]) => String(u).includes('/chat/stream'));
    expect(streamCalls.length).toBe(1);

    // Click Past Thread WHILE still streaming -> must abort stream and load Old Q / Old A cleanly
    const pastBtn = await screen.findByText('Past Clinical Thread');
    fireEvent.click(pastBtn);

    expect(abortedSignal?.aborted).toBe(true);
    await waitFor(() => {
      expect(screen.getByText('Old Q')).toBeInTheDocument();
      expect(screen.getByText('Old A')).toBeInTheDocument();
    });

    // Late token arriving on old closed stream cannot bleed into switched thread
    act(() => {
      try {
        controlled.push(`data: ${JSON.stringify({ token: 'LATE_LEAK_TOKEN' })}\n\n`);
        controlled.close();
      } catch {
        // stream already cancelled
      }
    });
    expect(screen.queryByText(/BLEED_SHOULD_NOT_APPEAR/)).not.toBeInTheDocument();
    expect(screen.queryByText(/LATE_LEAK_TOKEN/)).not.toBeInTheDocument();

    // Clicking New Chat resets cleanly
    const newChatBtn = screen.getByRole('button', { name: /New Chat/i });
    fireEvent.click(newChatBtn);
    await waitFor(() => {
      expect(screen.queryByText('Old Q')).not.toBeInTheDocument();
    });
  });
});

describe('QA Vector 2: Ultra-Long Prompts, Nested Code Blocks, LaTeX, Tables & XSS', () => {
  it('handles nested 4-backtick / 3-backtick code fences, CRLF, and unclosed streaming code fences', () => {
    const nestedMd = [
      'Here is nested markdown:\r\n',
      '````markdown',
      '```python',
      'print("hello <script>alert(1)</script>")',
      '```',
      '````',
      '```typescript',
      'const x: string = "<div>";',
      '```',
      '```sql',
      'SELECT * FROM users WHERE name LIKE \'%_%\';',
      '```',
      '```bash',
      'echo "hello" | grep hello',
    ].join('\n');

    const segments = splitMarkdownAndCode(nestedMd);
    const codeSegs = segments.filter((s) => s.type === 'code');
    expect(codeSegs.map((s) => s.language)).toEqual([
      'markdown',
      'typescript',
      'sql',
      'bash',
    ]);
    expect(codeSegs[0].content).toContain('```python');
    expect(codeSegs[3].content).toContain('echo "hello"');
  });

  it('sanitizes XSS injections, wraps tables for horizontal scroll, and renders KaTeX while preserving $97 currency', () => {
    const dangerousMd = [
      '# Safe Header',
      '',
      '<script>window.__xss=1</script>',
      '<img src="x" onerror="alert(1)" />',
      '[Click me](javascript:alert(2))',
      '',
      '| Col A | Col B | Col C |',
      '| --- | --- | --- |',
      '| val1 | val2 | val3 |',
      '',
      'Formula: $$E = mc^2$$ and course price $97 vs $197.',
    ].join('\n');

    const html = renderSafeMarkdownHtml(dangerousMd);
    expect(html).not.toContain('<script');
    expect(html).not.toContain('onerror');
    expect(html).not.toMatch(/href\s*=\s*["']?\s*javascript:/i);
    expect(html).not.toContain('<a ');
    expect(html).toContain('table-scroll-wrapper');
    expect(html).toContain('katex');
    expect(html).toContain('$97');
    expect(html).toContain('$197');
  });

  it('renders and toggles ultra-long 12,000+ character user prompts cleanly', () => {
    const ultraLong = 'Clinical narrative section. '.repeat(500);
    render(
      <ChatMessage
        message={{
          id: 'u_long',
          role: 'user',
          content: ultraLong,
          mode: 'generic',
          createdAt: Date.now(),
        }}
      />
    );
    const expandBtn = screen.getByRole('button', { name: /Show full message/i });
    expect(expandBtn).toBeInTheDocument();
    fireEvent.click(expandBtn);
    expect(screen.getByRole('button', { name: /Collapse prompt/i })).toBeInTheDocument();
  });
});

describe('QA Vector 3: RAG Retrieval & Source Metadata Handling', () => {
  it('returns null gracefully for empty or null source arrays', () => {
    const { container: c1 } = render(<SourceAccordion sources={[]} />);
    expect(c1.firstChild).toBeNull();
    const { container: c2 } = render(<SourceAccordion sources={null} />);
    expect(c2.firstChild).toBeNull();
  });

  it('renders 25 dense citation chunks & long URLs with constrained scrollable container', () => {
    const denseSources = Array.from({ length: 25 }, (_, i) => ({
      document: `Long_Clinical_Reference_Document_${i}_With_Unbroken_Filename_And_Protocol.pdf`,
      page: i + 1,
      chunk_id: `chunk_${i}`,
      relevance_score: 0.92,
      url: `https://doctorsarahhensley.com/very/long/path/without/spaces/${'segment/'.repeat(10)}${i}`,
      snippet: 'Detailed clinical excerpt. '.repeat(25),
    }));

    render(<SourceAccordion sources={denseSources} defaultOpen={true} />);
    expect(
      screen.getByText(/Sources \(25 Context Chunks Retrieved\)/i)
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Show full excerpt/i }).length).toBe(25);
  });
});

describe('QA Vector 4: Sidebar Search Special Chars & Delete/Reload Synchronization', () => {
  it('handles special characters (%, _, quotes, emoji) and ms/0 timestamps in search without crashing', () => {
    const threads = [
      {
        session_id: 's1',
        user_id: '1836',
        mode: 'generic' as const,
        chat_number: 1,
        title: '100% _test_ "quote" 🔥',
        message_count: 2,
        created_at: 0,
        updated_at: 0,
      },
      {
        session_id: 's2',
        user_id: '1836',
        mode: 'generic' as const,
        chat_number: 2,
        title: "Partner's 'avoidant' shutdown",
        message_count: 4,
        created_at: Date.now(), // milliseconds instead of seconds
        updated_at: Date.now(),
      },
    ];

    render(
      <ChatHistory
        threads={threads}
        activeSessionId="s1"
        searchQuery="% _ 🔥"
        activeMode="generic"
        onSelectThread={vi.fn()}
        onRenameThread={vi.fn(async () => {})}
        onDeleteThread={vi.fn(async () => {})}
      />
    );
    expect(screen.getByText(/No matching chats found/i)).toBeInTheDocument();

    const { rerender } = render(
      <ChatHistory
        threads={threads}
        activeSessionId="s1"
        searchQuery="100%"
        activeMode="generic"
        onSelectThread={vi.fn()}
        onRenameThread={vi.fn(async () => {})}
        onDeleteThread={vi.fn(async () => {})}
      />
    );
    expect(screen.getByText('100% _test_ "quote" 🔥')).toBeInTheDocument();
    rerender(
      <ChatHistory
        threads={threads}
        activeSessionId="s2"
        searchQuery="'avoidant'"
        activeMode="generic"
        onSelectThread={vi.fn()}
        onRenameThread={vi.fn(async () => {})}
        onDeleteThread={vi.fn(async () => {})}
      />
    );
    expect(screen.getByText("Partner's 'avoidant' shutdown")).toBeInTheDocument();
  });

  it('re-hydrates open thread on reload from GET /api/chats/{id}/messages and resets cleanly on delete', async () => {
    sessionStorage.setItem('studio_active_user', '1836');
    sessionStorage.setItem('studio_active_mode', 'generic');
    sessionStorage.setItem('studio_active_session_generic', 'sess_reload_1');
    Element.prototype.scrollTo = vi.fn();

    let deleted = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/users')) return jsonResponse({ users: [{ user_id: '1836', name: 'Test User' }] });
      if (url.includes('/api/system/stats')) return jsonResponse({ documents_count: 5 });
      if (url.includes('/api/auth/token')) return jsonResponse({ token: 'tok_reload' });
      if (url.includes('/api/chat/sessions/sess_reload_1') && init?.method === 'DELETE') {
        deleted = true;
        return jsonResponse({ success: true });
      }
      if (url.includes('/api/chat/sessions')) {
        return jsonResponse({
          sessions: deleted
            ? []
            : [
                {
                  session_id: 'sess_reload_1',
                  user_id: '1836',
                  mode: 'generic',
                  chat_number: 1,
                  title: 'Persisted Thread',
                  message_count: 2,
                  created_at: Math.floor(Date.now() / 1000),
                  updated_at: Math.floor(Date.now() / 1000),
                },
              ],
        });
      }
      if (url.includes('/api/chats/sess_reload_1/messages')) {
        return jsonResponse({
          messages: [
            { role: 'user', content: 'Reloaded Question', mode: 'generic', created_at: 1700000000 },
            { role: 'assistant', content: 'Reloaded Answer', mode: 'generic', created_at: 1700000001 },
          ],
        });
      }
      return jsonResponse({});
    });

    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('Reloaded Question').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Reloaded Answer')).toBeInTheDocument();
    });

    // Inline 2-step delete while viewing thread -> resets to New Clinical Chat
    const delTrigger = screen.getByTitle('Delete conversation');
    fireEvent.click(delTrigger);
    const confirmBtn = screen.getByRole('button', { name: /Confirm/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.queryAllByText('Reloaded Question')).toHaveLength(0);
      expect(screen.getByRole('heading', { name: 'New Clinical Chat' })).toBeInTheDocument();
    });
  });
});

describe('QA Vector 5: Server Error (500/422), Timeout, Retry & ErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('displays toast + inline retry button on 500 error and recovers on retry', async () => {
    sessionStorage.clear();
    Element.prototype.scrollTo = vi.fn();
    let attempt = 0;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/users')) return jsonResponse({ users: [{ user_id: '1836', name: 'Test User' }] });
      if (url.includes('/api/system/stats')) return jsonResponse({ documents_count: 5 });
      if (url.includes('/api/auth/token')) return jsonResponse({ token: 'tok_err' });
      if (url.includes('/api/chat/sessions')) return jsonResponse({ sessions: [] });
      if (url.includes('/chat/stream')) {
        attempt += 1;
        if (attempt === 1) {
          return jsonResponse({ success: false, error: 'Simulated 500 Outage' }, 500);
        }
        const enc = new TextEncoder();
        const stream = new ReadableStream({
          start(c) {
            c.enqueue(
              enc.encode(
                `data: ${JSON.stringify({ done: true, answer: 'Recovered after retry!', sources: [] })}\n\n`
              )
            );
            c.close();
          },
        });
        return new Response(stream, { status: 200 });
      }
      return jsonResponse({});
    });

    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const textarea = await screen.findByPlaceholderText(/Clinical Educator AI/i);
    fireEvent.change(textarea, { target: { value: 'Trigger 500 error' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getAllByText(/Simulated 500 Outage/i).length).toBeGreaterThanOrEqual(1);
    });

    const retryBtns = screen.getAllByRole('button', { name: /Retry/i });
    fireEvent.click(retryBtns[0]);

    await waitFor(() => {
      expect(screen.getByText('Recovered after retry!')).toBeInTheDocument();
    });
  });

  it('catches unhandled child render errors in ErrorBoundary instead of white-screening', () => {
    const Boom: React.FC = () => {
      throw new Error('Simulated UI Crash');
    };
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Simulated UI Crash')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Recover View/i })).toBeInTheDocument();
  });

  it('switches to Platform Help side-by-side in top bar on the same page without floating popup', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/users')) return jsonResponse({ users: [{ user_id: '1836', name: 'Maya Lin' }] });
      if (url.includes('/api/system/stats')) return jsonResponse({ documents_count: 10 });
      if (url.includes('/api/auth/token')) return jsonResponse({ token: 'tok_plat' });
      if (url.includes('/api/chat/sessions')) return jsonResponse({ sessions: [] });
      if (url.includes('/api/platform-widget/context')) {
        return jsonResponse({
          success: true,
          authenticated: true,
          user_id: '1836',
          user_first_name: 'Maya',
          greeting_line: 'Hello Maya!',
          current_page: '/',
          suggested_actions: [
            { label: 'How do I log in?', prompt: 'How do I log into my account?' },
          ],
        });
      }
      if (url.includes('/chat/stream')) {
        const enc = new TextEncoder();
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              enc.encode(`data: ${JSON.stringify({ done: true, answer: 'Hello Maya!\n\n1. Open Login.' })}\n\n`)
            );
            controller.close();
          },
        });
        return new Response(stream, { status: 200 });
      }
      return jsonResponse({});
    });

    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    // Floating corner launcher should NOT be rendered in Studio App
    expect(screen.queryByRole('button', { name: /Platform Help chat widget/i })).not.toBeInTheDocument();

    const platformBtn = await screen.findByRole('button', { name: /Platform Help/i });
    fireEvent.click(platformBtn);

    await waitFor(() => {
      expect(screen.getByText(/Dr\. Sarah Hensley Platform Navigation Assistant/i)).toBeInTheDocument();
      expect(screen.getByText(/Hello Maya!/i)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(/Ask about login, password reset/i);
    fireEvent.change(input, { target: { value: 'How do I log in?' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(/Open Login\./i)).toBeInTheDocument();
    });

    const streamCall = fetchMock.mock.calls.find(([u]) => String(u).includes('/chat/stream'));
    expect(streamCall).toBeDefined();
    const sentBody = JSON.parse(String(streamCall?.[1]?.body || '{}'));
    expect(sentBody.mode).toBe('platform');
  });

  it('switches to Owner Agent side-by-side in top bar and streams with mode owner', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/users')) return jsonResponse({ users: [{ user_id: '1836', name: 'Maya Lin' }] });
      if (url.includes('/api/system/stats')) return jsonResponse({ documents_count: 10 });
      if (url.includes('/api/auth/token')) return jsonResponse({ token: 'tok_owner' });
      if (url.includes('/api/chat/sessions')) return jsonResponse({ sessions: [] });
      if (url.includes('/api/platform-widget/context')) {
        return jsonResponse({ success: true, greeting_line: 'Hello Maya!', suggested_actions: [] });
      }
      if (url.includes('/chat/stream')) {
        const enc = new TextEncoder();
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              enc.encode(`data: ${JSON.stringify({ done: true, answer: "Hello Maya! In my clinical practice, core wounds shape our triggers." })}\n\n`)
            );
            controller.close();
          },
        });
        return new Response(stream, { status: 200 });
      }
      return jsonResponse({});
    });

    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const ownerBtn = await screen.findByRole('button', { name: /Owner Agent/i });
    fireEvent.click(ownerBtn);

    await waitFor(() => {
      expect(screen.getByText(/Dr\. Sarah Hensley — Owner Agent/i)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(/Ask Dr\. Sarah Hensley \(Founder Voice\)/i);
    fireEvent.change(input, { target: { value: 'Why do attachment wounds trigger?' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(/In my clinical practice, core wounds shape our triggers/i)).toBeInTheDocument();
    });

    const streamCall = fetchMock.mock.calls.find(([u]) => String(u).includes('/chat/stream'));
    expect(streamCall).toBeDefined();
    const sentBody = JSON.parse(String(streamCall?.[1]?.body || '{}'));
    expect(sentBody.mode).toBe('owner');
  });
});
