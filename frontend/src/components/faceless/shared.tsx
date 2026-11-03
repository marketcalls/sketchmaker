import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('text-xs font-medium text-muted-foreground', className)}>
      {children}
    </p>
  );
}

// Field label: small, sentence case, muted.
export function FieldLabel({ htmlFor, children, hint }: { htmlFor?: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-2">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
        {children}
      </label>
      {hint && <span className="text-[11px] text-muted-foreground/80">{hint}</span>}
    </div>
  );
}

// Pill toggle group (radio semantics) for compact option rows.
export function PillGroup<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: T;
  options: { value: T; label: ReactNode; hint?: string; disabled?: boolean }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            title={o.hint}
            disabled={disabled || o.disabled}
            onClick={() => onChange(o.value)}
            className={cn(
              'inline-flex min-h-10 items-center gap-2 rounded-md border px-3.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40',
              active
                ? 'border-primary/60 bg-primary/10 text-foreground'
                : 'border-border bg-secondary/40 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {children}
    </p>
  );
}
