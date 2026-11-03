import { useEffect, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { motionGraphicsApi, type MGAspect, type PreviewRequest } from '@/api/motionGraphics';
import { getErrorMessage } from '@/utils/errors';

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-balance text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-prose text-pretty text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-xs font-medium text-muted-foreground">{children}</h2>
      {aside}
    </div>
  );
}

export function TechChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[11px] font-medium text-foreground',
        className,
      )}
    >
      {children}
    </span>
  );
}

export function MutedChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground',
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function FieldLabel({
  htmlFor,
  children,
  hint,
  count,
  max,
}: {
  htmlFor?: string;
  children: ReactNode;
  hint?: ReactNode;
  count?: number;
  max?: number;
}) {
  const over = max !== undefined && count !== undefined && count > max;
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-2">
      <label htmlFor={htmlFor} className="text-xs font-medium text-foreground">
        {children}
        {hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}
      </label>
      {max !== undefined && count !== undefined && (
        <span className={cn('font-mono text-[10px]', over ? 'text-destructive' : 'text-muted-foreground')}>
          {count}/{max}
        </span>
      )}
    </div>
  );
}

export function PillGroup<T extends string>({
  value,
  options,
  onChange,
  disabled,
  size = 'sm',
}: {
  value: T | null | undefined;
  options: { id: T; label: ReactNode; title?: string; disabled?: boolean }[];
  onChange: (v: T) => void;
  disabled?: boolean;
  size?: 'sm' | 'xs';
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="radiogroup">
      {options.map((o) => {
        const active = o.id === value;
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={active}
            title={o.title}
            disabled={disabled || o.disabled}
            onClick={() => onChange(o.id)}
            className={cn(
              'rounded-md border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40',
              size === 'sm' ? 'min-h-8 px-3 text-xs' : 'min-h-7 px-2.5 text-[11px]',
              active
                ? 'border-primary/60 bg-primary/10 text-foreground'
                : 'border-border bg-secondary/30 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function AspectGlyph({ aspect, className }: { aspect: MGAspect; className?: string }) {
  const box: Record<MGAspect, string> = {
    '9:16': 'h-4 w-[9px]',
    '4:5': 'h-4 w-[13px]',
    '1:1': 'h-[13px] w-[13px]',
    '16:9': 'h-[9px] w-4',
  };
  return <span className={cn('inline-block rounded-[2px] border border-current', box[aspect], className)} aria-hidden />;
}

export const ASPECT_RATIO_CLASS: Record<MGAspect, string> = {
  '9:16': 'aspect-[9/16]',
  '4:5': 'aspect-[4/5]',
  '1:1': 'aspect-square',
  '16:9': 'aspect-video',
};

export function formatSeconds(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return '0:00';
  const total = Math.round(s);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** A preview still as an object URL, fetched after the inputs settle. */
export function usePreview(
  projectId: number | null,
  request: PreviewRequest | null,
  deps: unknown[],
  delayMs = 350,
): { url: string | null; loading: boolean; error: string | null } {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const current = useRef<string | null>(null);

  useEffect(() => {
    if (!projectId || !request) return;
    const mine = ++seq.current;
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const blob = await motionGraphicsApi.preview(projectId, request);
        if (mine !== seq.current) return;
        const next = URL.createObjectURL(blob);
        if (current.current) URL.revokeObjectURL(current.current);
        current.current = next;
        setUrl(next);
        setError(null);
      } catch (err) {
        if (mine === seq.current) setError(getErrorMessage(err, 'Preview failed'));
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, delayMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, ...deps]);

  useEffect(
    () => () => {
      if (current.current) URL.revokeObjectURL(current.current);
    },
    [],
  );
  return { url, loading, error };
}
