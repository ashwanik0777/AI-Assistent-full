'use client';

import { useEffect } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error('[AIRA Error Boundary]', error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center px-4" id="error-page">
      <div className="text-center animate-fade-in max-w-md">
        <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-error/10 animate-pulse-glow">
          <AlertTriangle className="h-10 w-10 text-error" />
        </div>

        <h1 className="mb-3 text-2xl font-bold text-text">Something went wrong</h1>
        <p className="mb-2 text-text-secondary leading-relaxed">
          An unexpected error occurred. Our team has been notified.
        </p>
        {error.digest && (
          <p className="mb-6 text-xs text-text-muted font-mono">
            Error ID: {error.digest}
          </p>
        )}

        <button
          onClick={reset}
          className="focus-ring transition-base inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-dark px-6 py-3 text-sm font-medium text-white shadow-md hover:shadow-glow"
          id="error-reset-btn"
        >
          <RefreshCw className="h-4 w-4" />
          Try Again
        </button>
      </div>
    </div>
  );
}
