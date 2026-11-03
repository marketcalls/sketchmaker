import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { formatUsd } from '@/stores/pricingStore';
import { qualityApi, type Quality, type QualityConfig, type QualityFixTarget } from '@/api/quality';

// One small badge for every quality check (Faceless stills and clips,
// /generate, explainers). Pass is subtle, warn amber, fail destructive,
// unverified muted. The reasons open under it, with the fix the user starts
// and pays for: nothing is ever regenerated on its own.

const TONE: Record<string, string> = {
  pass: 'border-success/30 bg-success/5 text-success',
  warn: 'border-warning/40 bg-warning/10 text-warning',
  fail: 'border-destructive/40 bg-destructive/10 text-destructive',
  unverified: 'border-border bg-secondary/40 text-muted-foreground',
  pending: 'border-border bg-secondary/40 text-muted-foreground',
};

const LABEL: Record<string, string> = {
  pass: 'Checked',
  warn: 'Check: warning',
  fail: 'Check: failed',
  unverified: 'Not verified',
  pending: 'Checking',
};

const FIX_LABEL: Record<QualityFixTarget, string> = {
  spelling: 'Fix spelling',
  defects: 'Fix this',
};

export interface QualityFix {
  target: QualityFixTarget;
  label?: string;
  usd?: number;
}

export function QualityBadge({
  quality,
  fixes,
  onFix,
  busy = false,
  defaultOpen = false,
  className,
}: {
  quality?: Quality | null;
  // The fixes to offer; without it, the ones the server says fit.
  fixes?: QualityFix[];
  onFix?: (target: QualityFixTarget) => void;
  busy?: boolean;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!quality) return null;
  const state = quality.status === 'pending' ? 'pending' : quality.verdict ?? 'unverified';
  const reasons = quality.reasons ?? [];
  const offered: QualityFix[] =
    state === 'fail' || state === 'warn'
      ? fixes ?? (quality.fixable ?? []).map((target) => ({ target }))
      : [];
  const expandable = state !== 'pending' && state !== 'pass' && (reasons.length > 0 || offered.length > 0);

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <button
        type="button"
        onClick={() => expandable && setOpen((o) => !o)}
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
        title={state === 'pass' ? 'The quality check found nothing to fix' : undefined}
        className={cn(
          'w-fit rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default',
          TONE[state],
        )}
      >
        {LABEL[state]}
        {expandable && reasons.length > 0 && <span className="tabular">{` (${reasons.length})`}</span>}
      </button>
      {expandable && open && (
        <div className="rounded-lg border border-border bg-background/80 p-2.5">
          {reasons.length > 0 && (
            <ul className="space-y-1 text-xs text-muted-foreground">
              {reasons.map((reason, i) => (
                <li key={i} className="leading-snug">
                  {reason}
                </li>
              ))}
            </ul>
          )}
          {onFix && offered.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {offered.map((fix) => (
                <Button key={fix.target} variant="outline" size="sm" disabled={busy} onClick={() => onFix(fix.target)}>
                  {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {fix.label ?? FIX_LABEL[fix.target]}
                  {fix.usd !== undefined && (
                    <span className="font-mono tabular text-[11px] text-muted-foreground">{formatUsd(fix.usd)}</span>
                  )}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// The check's availability and price, loaded once per page view.
let configCache: Promise<QualityConfig | null> | null = null;

export function useQualityConfig(): QualityConfig | null {
  const [config, setConfig] = useState<QualityConfig | null>(null);
  useEffect(() => {
    let live = true;
    if (!configCache) configCache = qualityApi.config().catch(() => null);
    configCache.then((c) => {
      if (live) setConfig(c);
      if (!c) configCache = null;
    });
    return () => {
      live = false;
    };
  }, []);
  return config;
}

// Polls a stored image's check while it is pending.
export function useImageQuality(imageId: number | undefined, initial: Quality | null | undefined): Quality | null {
  const [quality, setQuality] = useState<Quality | null>(initial ?? null);
  useEffect(() => setQuality(initial ?? null), [imageId, initial]);
  useEffect(() => {
    if (!imageId || quality?.status !== 'pending') return;
    let live = true;
    const timer = window.setInterval(async () => {
      try {
        const next = await qualityApi.image(imageId);
        if (live && next && next.status !== 'pending') setQuality(next);
      } catch {
        // Keep polling; a stored verdict is still there next time.
      }
    }, 4000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [imageId, quality?.status]);
  return quality;
}
