'use client';

import Link from 'next/link';
import { ArrowLeft, Search } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4" id="not-found-page">
      <div className="text-center animate-fade-in max-w-md">
        {/* Large 404 with gradient */}
        <div className="relative mb-6">
          <h1 className="text-[120px] font-black leading-none tracking-tighter gradient-text opacity-80 sm:text-[160px]">
            404
          </h1>
          <div className="absolute inset-0 flex items-center justify-center">
            <Search className="h-16 w-16 text-text-muted/30 sm:h-20 sm:w-20" />
          </div>
        </div>

        <h2 className="mb-3 text-2xl font-bold text-text">Page Not Found</h2>
        <p className="mb-8 text-text-secondary leading-relaxed">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
          Let&apos;s get you back on track.
        </p>

        <Link
          href="/"
          className="focus-ring transition-base inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-dark px-6 py-3 text-sm font-medium text-white shadow-md hover:shadow-glow"
          id="back-home-link"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>

        <div className="mt-10 mx-auto h-1 w-24 rounded-full bg-gradient-to-r from-primary to-accent opacity-50" />
      </div>
    </div>
  );
}
