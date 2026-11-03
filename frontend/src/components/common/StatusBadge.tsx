import { Badge } from '@/components/ui/badge';

type BadgeVariant = 'success' | 'warning' | 'destructive' | 'outline';

const SUCCESS = new Set([
  'completed', 'complete', 'success', 'succeeded', 'active', 'done', 'ok', 'enabled',
  'rendered',
]);
const WARNING = new Set([
  'pending', 'processing', 'queued', 'running', 'in_progress', 'submitted',
  'rendering', 'generating', 'scheduled', 'created', 'waiting', 'retrying', 'partial',
]);
const DESTRUCTIVE = new Set([
  'failed', 'failure', 'error',
]);

/** Map a status string to the shared badge variant. Unknown values are neutral. */
export function statusVariant(status: string | null | undefined): BadgeVariant {
  const key = (status ?? '').toLowerCase().trim().replace(/[\s-]+/g, '_');
  if (SUCCESS.has(key)) return 'success';
  if (WARNING.has(key)) return 'warning';
  if (DESTRUCTIVE.has(key)) return 'destructive';
  return 'outline';
}

function humanize(status: string): string {
  const s = status.replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

interface StatusBadgeProps {
  status: string | null | undefined;
  /** Text to show instead of the humanized status. */
  label?: string;
  className?: string;
}

/** Consistent status badge: success, warning (in progress), destructive (failed), outline. */
export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  const text = label ?? (status ? humanize(status) : 'Unknown');
  return (
    <Badge variant={statusVariant(status)} className={className}>
      {text}
    </Badge>
  );
}
