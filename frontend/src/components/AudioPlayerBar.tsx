import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Pause, Play } from 'lucide-react';
import type { BotMode } from '../types/chat';

export type PlaybackSpeed = 1 | 1.25 | 1.5;

const SPEED_OPTIONS: PlaybackSpeed[] = [1, 1.25, 1.5];

/**
 * Global single-playback coordinator so only one AudioPlayerBar can play at a time
 * across the entire chat UI (covers both ElevenLabs <audio> and window.speechSynthesis).
 */
type StopCallback = () => void;
let activePlaybackId: string | null = null;
let activeStopCallback: StopCallback | null = null;

export function stopActiveAudioPlayback(): void {
  if (activeStopCallback) {
    const fn = activeStopCallback;
    activeStopCallback = null;
    activePlaybackId = null;
    fn();
  } else if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

export function stripMarkdownForSpeech(raw: string): string {
  if (!raw || !raw.trim()) return '';
  let text = raw.replace(/\r\n/g, '\n');

  // Remove fenced code blocks and unwrap Markdown links [label](url) -> label
  text = text.replace(/```[\s\S]*?```/g, ' ');
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '$1');
  text = text.replace(/https?:\/\/\S+/g, '');

  // Strip citation brackets like [1], [1, 2], [Source 1]
  text = text.replace(/\[(?:\d+(?:\s*,\s*\d+)*|source\s*\d+)\]/gi, '');

  // Strip markdown headings, blockquotes, list bullets, backticks, emphasis
  text = text.replace(/`([^`]+)`/g, '$1');
  text = text.replace(/^\s{0,3}#{1,6}\s*/gm, '');
  text = text.replace(/^\s*>\s?/gm, '');
  text = text.replace(/^\s*(?:[-*•]+|\d+[.)])\s+/gm, '');
  text = text.replace(/(\*\*|__|\*|_|~~)/g, '');

  // Natural pronunciation helpers
  text = text.replace(/\bDr\./g, 'Doctor');
  text = text.replace(/\bPh\.?D\.?/g, 'PhD');
  text = text.replace(/\b1[-:\s]*1[-:\s]*1\b/g, 'one-one-one');
  text = text.replace(/[→—–]/g, ', ');

  text = text.replace(/\n{2,}/g, '. ').replace(/\n/g, ' ');
  text = text.replace(/\s+([.,!?;:])/g, '$1');
  text = text.replace(/\.{2,}/g, '.').replace(/\s{2,}/g, ' ').trim();
  return text;
}

export function formatCountdownMMSS(remainingSeconds: number): string {
  const safeSec = Math.max(0, Math.ceil(remainingSeconds));
  const mins = Math.floor(safeSec / 60);
  const secs = safeSec % 60;
  return `-${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export interface AudioPlayerBarProps {
  messageId: string;
  text: string;
  mode?: BotMode;
  buildAuthHeaders?: (tokenOverride?: string, extra?: Record<string, string>) => Record<string, string>;
  autoPlay?: boolean;
  onError?: (message: string) => void;
}

export const AudioPlayerBar: React.FC<AudioPlayerBarProps> = ({
  messageId,
  text,
  mode = 'generic',
  buildAuthHeaders,
  autoPlay = false,
  onError,
}) => {
  const cleanedText = useMemo(() => stripMarkdownForSpeech(text), [text]);
  const wordCount = useMemo(
    () => (cleanedText ? cleanedText.split(/\s+/).filter(Boolean).length : 0),
    [cleanedText]
  );
  // Estimated base duration at 1x speed (~150 WPM)
  const estimatedBaseSec = useMemo(
    () => Math.max(1, Math.round((wordCount / 150) * 60)),
    [wordCount]
  );

  const [status, setStatus] = useState<'idle' | 'loading' | 'playing' | 'paused'>('idle');
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [progress, setProgress] = useState(0); // 0..1
  const [actualBaseDuration, setActualBaseDuration] = useState<number | null>(null);

  const speedRef = useRef<PlaybackSpeed>(speed);
  speedRef.current = speed;

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const fetchAbortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const elapsedSpeechSecRef = useRef(0);
  const lastTickRef = useRef<number>(0);
  const charProgressRef = useRef(0);
  const autoPlayedRef = useRef(false);

  const useBackendElevenLabs = mode === 'owner' && Boolean(buildAuthHeaders);

  const totalBaseSec = actualBaseDuration ?? estimatedBaseSec;
  const remainingSec = Math.max(0, (totalBaseSec * (1 - progress)) / speed);

  const clearSpeechInterval = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const resetToIdle = useCallback(
    (keepCachedAudio = true) => {
      clearSpeechInterval();
      if (fetchAbortRef.current) {
        fetchAbortRef.current.abort();
        fetchAbortRef.current = null;
      }
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
        if (!keepCachedAudio) {
          audioRef.current.src = '';
          audioRef.current = null;
        }
      }
      if (!keepCachedAudio && blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
      if (
        typeof window !== 'undefined' &&
        'speechSynthesis' in window &&
        activePlaybackId === messageId
      ) {
        window.speechSynthesis.cancel();
      }
      elapsedSpeechSecRef.current = 0;
      charProgressRef.current = 0;
      setProgress(0);
      setStatus('idle');
      if (activePlaybackId === messageId) {
        activePlaybackId = null;
        activeStopCallback = null;
      }
    },
    [clearSpeechInterval, messageId]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearSpeechInterval();
      if (fetchAbortRef.current) fetchAbortRef.current.abort();
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
      }
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
      if (activePlaybackId === messageId) {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
          window.speechSynthesis.cancel();
        }
        activePlaybackId = null;
        activeStopCallback = null;
      }
    };
  }, [clearSpeechInterval, messageId]);

  const startWebSpeech = useCallback(
    (startCharIndex = 0) => {
      if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
        onError?.('Text-to-speech is not supported in this browser.');
        resetToIdle();
        return;
      }

      window.speechSynthesis.cancel();
      const sliceText = startCharIndex > 0 ? cleanedText.slice(startCharIndex) : cleanedText;
      const utterance = new SpeechSynthesisUtterance(sliceText);
      utterance.rate = speedRef.current;

      const voices = window.speechSynthesis.getVoices();
      const preferredVoice =
        voices.find((v) => v.lang.startsWith('en') && /natural|neural|aria|jenny|samantha|google/i.test(v.name)) ||
        voices.find((v) => v.lang.startsWith('en'));
      if (preferredVoice) {
        utterance.voice = preferredVoice;
      }

      lastTickRef.current = performance.now();
      clearSpeechInterval();
      timerRef.current = window.setInterval(() => {
        const now = performance.now();
        const dt = (now - lastTickRef.current) / 1000;
        lastTickRef.current = now;
        elapsedSpeechSecRef.current += dt * speedRef.current;
        const timeRatio = Math.min(0.99, elapsedSpeechSecRef.current / estimatedBaseSec);
        const blended = Math.max(charProgressRef.current, timeRatio);
        setProgress(blended);
      }, 250);

      utterance.onboundary = (ev: SpeechSynthesisEvent) => {
        if (typeof ev.charIndex === 'number' && cleanedText.length > 0) {
          const absIndex = startCharIndex + ev.charIndex;
          const ratio = Math.min(0.99, absIndex / cleanedText.length);
          charProgressRef.current = ratio;
          elapsedSpeechSecRef.current = ratio * estimatedBaseSec;
          setProgress(ratio);
        }
      };

      utterance.onend = () => {
        resetToIdle();
      };

      utterance.onerror = (ev) => {
        if (ev.error === 'interrupted' || ev.error === 'canceled') return;
        resetToIdle();
        onError?.('Browser speech playback failed.');
      };

      activePlaybackId = messageId;
      activeStopCallback = () => resetToIdle();
      setStatus('playing');
      window.speechSynthesis.speak(utterance);
    },
    [cleanedText, clearSpeechInterval, estimatedBaseSec, messageId, onError, resetToIdle]
  );

  const playBackendElevenLabs = useCallback(async () => {
    // Reuse already-fetched audio blob for instant play/resume at 0 credits
    if (audioRef.current && blobUrlRef.current) {
      activePlaybackId = messageId;
      activeStopCallback = () => resetToIdle();
      audioRef.current.playbackRate = speedRef.current;
      setStatus('playing');
      await audioRef.current.play();
      return;
    }

    const controller = new AbortController();
    fetchAbortRef.current = controller;
    activePlaybackId = messageId;
    activeStopCallback = () => resetToIdle();
    setStatus('loading');

    try {
      const headers = buildAuthHeaders
        ? buildAuthHeaders(undefined, { 'Content-Type': 'application/json' })
        : { 'Content-Type': 'application/json' };
      const res = await fetch('/api/v1/tts/stream', {
        method: 'POST',
        headers,
        body: JSON.stringify({ text, mode: 'owner', message_id: messageId }),
        signal: controller.signal,
      });

      if (!res.ok) {
        // Fallback to browser Web Speech if backend TTS is unavailable/unconfigured
        if (res.status === 400 || res.status === 503) {
          startWebSpeech(0);
          return;
        }
        let errMsg = `Voice synthesis failed (${res.status})`;
        try {
          const j = (await res.json()) as { detail?: string; error?: string };
          errMsg = j.detail || j.error || errMsg;
        } catch {
          // ignore
        }
        throw new Error(errMsg);
      }

      const blob = await res.blob();
      if (controller.signal.aborted) return;

      const url = URL.createObjectURL(blob);
      blobUrlRef.current = url;
      const audio = new Audio(url);
      audio.playbackRate = speedRef.current;
      audioRef.current = audio;

      audio.onloadedmetadata = () => {
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          setActualBaseDuration(audio.duration);
        }
      };
      audio.ontimeupdate = () => {
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          setProgress(Math.min(1, audio.currentTime / audio.duration));
        }
      };
      audio.onended = () => resetToIdle();
      audio.onerror = () => {
        resetToIdle(false);
        onError?.('Could not play generated voice audio.');
      };

      setStatus('playing');
      await audio.play();
    } catch (err) {
      const e = err as Error;
      if (e.name === 'AbortError') return;
      resetToIdle(false);
      onError?.(e.message || 'Unable to generate voice audio.');
    }
  }, [buildAuthHeaders, messageId, onError, resetToIdle, startWebSpeech, text]);

  const handleTogglePlayPause = useCallback(async () => {
    if (!cleanedText) return;

    if (status === 'loading') {
      resetToIdle();
      return;
    }

    if (status === 'playing') {
      if (audioRef.current) {
        audioRef.current.pause();
        setStatus('paused');
      } else if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        clearSpeechInterval();
        window.speechSynthesis.pause();
        setStatus('paused');
      }
      return;
    }

    if (status === 'paused') {
      // Ensure no other message took over while paused
      if (activePlaybackId && activePlaybackId !== messageId) {
        stopActiveAudioPlayback();
      }
      activePlaybackId = messageId;
      activeStopCallback = () => resetToIdle();

      if (audioRef.current) {
        audioRef.current.playbackRate = speedRef.current;
        setStatus('playing');
        await audioRef.current.play();
      } else if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        lastTickRef.current = performance.now();
        clearSpeechInterval();
        timerRef.current = window.setInterval(() => {
          const now = performance.now();
          const dt = (now - lastTickRef.current) / 1000;
          lastTickRef.current = now;
          elapsedSpeechSecRef.current += dt * speedRef.current;
          const timeRatio = Math.min(0.99, elapsedSpeechSecRef.current / estimatedBaseSec);
          setProgress(Math.max(charProgressRef.current, timeRatio));
        }, 250);
        setStatus('playing');
        window.speechSynthesis.resume();
      }
      return;
    }

    // Starting fresh playback: stop any other currently playing message first
    if (activePlaybackId && activePlaybackId !== messageId) {
      stopActiveAudioPlayback();
    }

    if (useBackendElevenLabs) {
      await playBackendElevenLabs();
    } else {
      startWebSpeech(0);
    }
  }, [
    cleanedText,
    clearSpeechInterval,
    estimatedBaseSec,
    messageId,
    playBackendElevenLabs,
    resetToIdle,
    startWebSpeech,
    status,
    useBackendElevenLabs,
  ]);

  const handleCycleSpeed = useCallback(() => {
    const idx = SPEED_OPTIONS.indexOf(speed);
    const nextSpeed = SPEED_OPTIONS[(idx + 1) % SPEED_OPTIONS.length];
    speedRef.current = nextSpeed;
    setSpeed(nextSpeed);

    if (audioRef.current) {
      audioRef.current.playbackRate = nextSpeed;
    } else if (status === 'playing' && typeof window !== 'undefined' && 'speechSynthesis' in window) {
      // Restart Web Speech from current estimated character offset with updated rate
      const resumeOffset = Math.floor(progress * cleanedText.length);
      startWebSpeech(resumeOffset);
    }
  }, [cleanedText.length, progress, speed, startWebSpeech, status]);

  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));

      if (audioRef.current && Number.isFinite(audioRef.current.duration) && audioRef.current.duration > 0) {
        audioRef.current.currentTime = ratio * audioRef.current.duration;
        setProgress(ratio);
      } else if (status === 'playing' || status === 'paused') {
        const offset = Math.floor(ratio * cleanedText.length);
        charProgressRef.current = ratio;
        elapsedSpeechSecRef.current = ratio * estimatedBaseSec;
        setProgress(ratio);
        if (status === 'playing') {
          startWebSpeech(offset);
        }
      }
    },
    [cleanedText.length, estimatedBaseSec, startWebSpeech, status]
  );

  // Trigger optional Auto-Read once per new message when enabled
  useEffect(() => {
    if (autoPlay && !autoPlayedRef.current && cleanedText) {
      autoPlayedRef.current = true;
      void handleTogglePlayPause();
    }
  }, [autoPlay, cleanedText, handleTogglePlayPause]);

  if (!cleanedText) return null;

  const accentClasses =
    mode === 'owner'
      ? {
          btn: 'bg-violet-600 text-white hover:bg-violet-500',
          fill: 'bg-violet-500',
          ring: 'border-violet-500/25 bg-violet-500/5 dark:border-violet-500/30 dark:bg-violet-500/10',
        }
      : mode === 'sales'
      ? {
          btn: 'bg-amber-600 text-white hover:bg-amber-500',
          fill: 'bg-amber-500',
          ring: 'border-amber-500/25 bg-amber-500/5 dark:border-amber-500/30 dark:bg-amber-500/10',
        }
      : mode === 'platform'
      ? {
          btn: 'bg-sky-600 text-white hover:bg-sky-500',
          fill: 'bg-sky-500',
          ring: 'border-sky-500/25 bg-sky-500/5 dark:border-sky-500/30 dark:bg-sky-500/10',
        }
      : {
          btn: 'bg-emerald-600 text-white hover:bg-emerald-500',
          fill: 'bg-emerald-500',
          ring: 'border-emerald-500/25 bg-emerald-500/5 dark:border-emerald-500/30 dark:bg-emerald-500/10',
        };

  return (
    <div
      className={`mt-2.5 flex items-center gap-2.5 rounded-xl border px-2.5 py-1.5 shadow-sm transition-colors ${accentClasses.ring}`}
      role="region"
      aria-label="Response audio player"
    >
      <button
        type="button"
        onClick={() => void handleTogglePlayPause()}
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full shadow-sm transition-transform active:scale-95 ${accentClasses.btn}`}
        aria-label={
          status === 'loading'
            ? 'Cancel audio loading'
            : status === 'playing'
            ? 'Pause audio'
            : 'Play audio'
        }
        title={
          status === 'loading'
            ? 'Loading audio...'
            : status === 'playing'
            ? 'Pause'
            : 'Play'
        }
      >
        {status === 'loading' ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : status === 'playing' ? (
          <Pause className="h-3.5 w-3.5 fill-current" />
        ) : (
          <Play className="ml-0.5 h-3.5 w-3.5 fill-current" />
        )}
      </button>

      <div
        onClick={handleSeek}
        className="group relative flex h-5 flex-1 cursor-pointer items-center"
        role="slider"
        aria-label="Audio progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        tabIndex={0}
      >
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700/80">
          <div
            className={`h-full rounded-full transition-[width] duration-150 ${accentClasses.fill}`}
            style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
          />
        </div>
      </div>

      <span className="shrink-0 font-mono text-[11px] tabular-nums text-slate-600 dark:text-slate-300">
        {formatCountdownMMSS(remainingSec)}
      </span>

      <button
        type="button"
        onClick={handleCycleSpeed}
        className="shrink-0 rounded-md border border-slate-200 bg-white/80 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-700 transition-colors hover:bg-white dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200 dark:hover:bg-slate-700"
        title="Cycle playback speed"
      >
        {speed}x
      </button>
    </div>
  );
};

