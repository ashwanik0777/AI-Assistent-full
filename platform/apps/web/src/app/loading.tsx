import { Spinner } from '@/components/ui/spinner';

export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center" id="loading-page">
      <div className="flex flex-col items-center gap-4 animate-fade-in">
        <Spinner size="lg" />
        <p className="text-sm font-medium text-text-muted">Loading AIRA…</p>
      </div>
    </div>
  );
}
