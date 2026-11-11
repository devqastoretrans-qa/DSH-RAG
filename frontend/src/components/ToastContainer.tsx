import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import type { ToastNotification } from '../types/chat';

export interface ToastContainerProps {
  toasts: ToastNotification[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastContainerProps> = ({
  toasts,
  onDismiss,
}) => {
  if (!toasts || toasts.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed right-4 top-16 z-50 flex w-full max-w-sm flex-col gap-2"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((t) => {
        const tone =
          t.type === 'error'
            ? 'border-rose-500/40 bg-rose-950/90 text-rose-100'
            : t.type === 'warning'
            ? 'border-amber-500/40 bg-amber-950/90 text-amber-100'
            : t.type === 'success'
            ? 'border-emerald-500/40 bg-emerald-950/90 text-emerald-100'
            : 'border-sky-500/40 bg-slate-900/95 text-slate-100';

        const Icon =
          t.type === 'error'
            ? AlertCircle
            : t.type === 'warning'
            ? AlertTriangle
            : t.type === 'success'
            ? CheckCircle2
            : Info;

        return (
          <div
            key={t.id}
            role="alert"
            className={`pointer-events-auto flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-xs shadow-xl backdrop-blur-md ${tone}`}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              {t.title && <div className="font-semibold">{t.title}</div>}
              <p className="mt-0.5 break-words text-[11px] opacity-90">
                {t.message}
              </p>
              {t.actionLabel && t.onAction && (
                <button
                  type="button"
                  onClick={() => {
                    t.onAction?.();
                    onDismiss(t.id);
                  }}
                  className="mt-1.5 rounded-md bg-white/15 px-2.5 py-1 text-[11px] font-semibold hover:bg-white/25"
                >
                  {t.actionLabel}
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(t.id)}
              className="rounded p-0.5 opacity-70 hover:bg-white/10 hover:opacity-100"
              aria-label="Dismiss notification"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};

