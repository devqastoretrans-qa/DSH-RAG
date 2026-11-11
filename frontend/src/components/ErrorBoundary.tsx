import React from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface ErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error?.message || 'Unexpected rendering error occurred.',
    };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('[UI ErrorBoundary]', error, info);
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-dvh w-screen items-center justify-center bg-slate-50 p-6 text-slate-900 dark:bg-[#0B1120] dark:text-slate-100">
          <div className="w-full max-w-md rounded-2xl border border-rose-500/30 bg-white p-6 text-center shadow-xl dark:bg-[#131E32]">
            <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-rose-500" />
            <h1 className="text-lg font-semibold">Something went wrong</h1>
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
              {this.state.errorMessage}
            </p>
            <div className="mt-5 flex justify-center gap-2">
              <button
                type="button"
                onClick={() => this.setState({ hasError: false, errorMessage: '' })}
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Recover View</span>
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="rounded-xl border border-slate-300 px-4 py-2 text-xs font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
              >
                Reload Tab
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

