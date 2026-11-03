import { X } from 'lucide-react';
import { useMediaNoticeStore } from './library';

// Short notices from the background copy into My Assets (only failures).
export function MediaNotice() {
  const { notices, dismiss } = useMediaNoticeStore();
  if (notices.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
      {notices.map((n) => (
        <div
          key={n.id}
          className="pointer-events-auto flex items-start gap-3 rounded-xl border border-border bg-card p-3 text-sm shadow-card"
        >
          <p className="flex-1 text-muted-foreground">{n.text}</p>
          <button
            type="button"
            onClick={() => dismiss(n.id)}
            className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
