import { useState, type ReactNode } from 'react';
import { AlertOctagon, AlertTriangle, Check, CheckCircle2, Circle, Copy, Info, Loader2, XCircle, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ComplianceFlag, FacelessAspect, ProjectStatus, Severity } from '@/api/faceless';

// UI state of a studio step (derived from runs and assets).
export type StepState = 'idle' | 'queued' | 'running' | 'done' | 'partial' | 'failed';
// UI state of one scene asset.
export type AssetState = 'none' | 'running' | 'done' | 'failed';

// Page header per docs/DESIGN_SYSTEM.md.
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
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
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 className="text-base font-semibold tracking-tight">{children}</h2>
      {aside}
    </div>
  );
}

export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('text-xs font-medium text-muted-foreground', className)}>
      {children}
    </p>
  );
}

export function TechChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[11px] font-medium text-foreground',
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
        'inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground',
        className,
      )}
    >
      {children}
    </span>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-12 text-center">
      <Icon className="mb-3 h-6 w-6 text-muted-foreground" aria-hidden="true" />
      <h3 className="text-base font-semibold">{title}</h3>
      {children && <p className="mt-2 max-w-md text-sm text-muted-foreground">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

const STEP_LABEL: Record<StepState, string> = {
  idle: 'Not started',
  queued: 'Queued',
  running: 'Running',
  done: 'Done',
  partial: 'Partial',
  failed: 'Failed',
};

export function StepStateChip({ state, progress, compact }: { state: StepState; progress?: number; compact?: boolean }) {
  const variant =
    state === 'done' ? 'success' : state === 'failed' ? 'destructive' : state === 'partial' ? 'warning' : state === 'idle' ? 'outline' : 'warning';
  const label = state === 'running' && progress ? `${Math.round(progress)}%` : STEP_LABEL[state];
  return (
    <Badge variant={variant} className="tabular">
      {(state === 'running' || state === 'queued') && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
      {compact && state === 'idle' ? <Circle className="h-2.5 w-2.5" aria-hidden="true" /> : label}
      {compact && state === 'idle' && <span className="sr-only">{label}</span>}
    </Badge>
  );
}

export function AssetStateIcon({ state, label }: { state: AssetState; label: string }) {
  const map: Record<AssetState, { icon: LucideIcon; cls: string; text: string }> = {
    none: { icon: Circle, cls: 'text-muted-foreground/50', text: 'not made' },
    running: { icon: Loader2, cls: 'animate-spin text-muted-foreground', text: 'running' },
    done: { icon: CheckCircle2, cls: 'text-success', text: 'ready' },
    failed: { icon: XCircle, cls: 'text-destructive', text: 'failed' },
  };
  const { icon: Icon, cls, text } = map[state] ?? map.none;
  return (
    <span className="inline-flex items-center gap-1" title={`${label}: ${text}`}>
      <Icon className={cn('h-3.5 w-3.5', cls)} aria-hidden="true" />
      <span className="sr-only">{`${label}: ${text}`}</span>
    </span>
  );
}

const PROJECT_STATUS: Record<ProjectStatus, { label: string; variant: 'success' | 'warning' | 'destructive' | 'outline' }> = {
  draft: { label: 'Draft', variant: 'outline' },
  scripted: { label: 'Scripted', variant: 'outline' },
  producing: { label: 'In production', variant: 'warning' },
  rendered: { label: 'Rendered', variant: 'success' },
};

export function ProjectStatusBadge({ status, running }: { status: ProjectStatus; running?: boolean }) {
  const s = PROJECT_STATUS[status] ?? { label: status, variant: 'outline' as const };
  return (
    <Badge variant={s.variant}>
      {running && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
      {s.label}
    </Badge>
  );
}

// A rectangle in the output's proportions, for aspect pickers and cards.
export function AspectGlyph({ aspect, className }: { aspect: FacelessAspect; className?: string }) {
  const [w, h] = aspect.split(':').map(Number);
  const scale = 18 / Math.max(w, h);
  return (
    <span
      aria-hidden="true"
      className={cn('inline-block rounded-[3px] border-[1.5px] border-current', className)}
      style={{ width: Math.round(w * scale), height: Math.round(h * scale) }}
    />
  );
}

export const ASPECT_CLASS: Record<FacelessAspect, string> = {
  '9:16': 'aspect-[9/16]',
  '16:9': 'aspect-video',
  '1:1': 'aspect-square',
  '4:5': 'aspect-[4/5]',
};

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '--';
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m > 0 ? `${m}:${String(r).padStart(2, '0')}` : `${r}s`;
}

export function formatLengthRange(min: number, max: number): string {
  return `${formatDuration(min)} to ${formatDuration(max)}`;
}

const SEVERITY: Record<Severity, { icon: LucideIcon; cls: string; label: string }> = {
  block: { icon: AlertOctagon, cls: 'border-destructive/40 bg-destructive/10 text-destructive', label: 'Blocks render' },
  warn: { icon: AlertTriangle, cls: 'border-warning/40 bg-warning/10 text-warning', label: 'Warning' },
  info: { icon: Info, cls: 'border-border bg-secondary/40 text-muted-foreground', label: 'Note' },
};

export function FlagList({ flags, empty }: { flags: ComplianceFlag[]; empty?: string }) {
  if (flags.length === 0) {
    return empty ? (
      <p className="flex items-center gap-2 text-sm text-success">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        {empty}
      </p>
    ) : null;
  }
  const order: Severity[] = ['block', 'warn', 'info'];
  const sorted = [...flags].sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
  return (
    <ul className="space-y-2">
      {sorted.map((f, i) => {
        const s = SEVERITY[f.severity] ?? SEVERITY.info;
        return (
          <li key={`${f.code}-${i}`} className={cn('flex gap-2 rounded-lg border p-3 text-sm', s.cls)}>
            <s.icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-xs font-medium">
                {s.label}
                {f.scene_id && <span className="ml-2 opacity-80">scene {f.scene_id}</span>}
                {f.platform && f.platform !== 'all' && <span className="ml-2 opacity-80">{f.platform}</span>}
              </p>
              <p className="mt-0.5 text-foreground">{f.message}</p>
              {f.advice && <p className="mt-1 text-xs text-muted-foreground">{f.advice}</p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function hasBlockingFlag(flags: ComplianceFlag[] | undefined): boolean {
  return (flags ?? []).some((f) => f.severity === 'block');
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

// Copies text to the clipboard and confirms inline (announced to screen readers).
export function CopyButton({ text, label = 'Copy', className }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={className}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          setCopied(false);
        }
      }}
      aria-label={copied ? 'Copied' : label}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      <span aria-live="polite">{copied ? 'Copied' : label}</span>
    </Button>
  );
}
