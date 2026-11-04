import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { getErrorMessage } from '@/utils/errors';
import { STUDIO_STEPS, PAID_TO_STUDIO, facelessApi, isRunActive, type FacelessProject, type PaidStep } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { formatUsd } from '@/stores/pricingStore';
import { formatDuration } from '../shared';

export function stepLabel(step: string): string {
  if (step === 'script') return 'Script draft';
  const studio = PAID_TO_STUDIO[step as PaidStep];
  return STUDIO_STEPS.find((s) => s.id === studio)?.label ?? step;
}

// Time since a run started, ticking once a second. Renders nothing without a start time.
export function Elapsed({ since, className }: { since: string | null | undefined; className?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!since) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [since]);
  if (!since) return null;
  const start = Date.parse(since);
  if (!Number.isFinite(start)) return null;
  return <span className={className}>{formatDuration(Math.max(0, (now - start) / 1000))} elapsed</span>;
}

// Live runs across the project, with progress and cancel.
export function RunsStrip({ project }: { project: FacelessProject }) {
  const refreshProject = useFacelessStore((s) => s.refreshProject);
  const [cancelling, setCancelling] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const live = project.active_runs.filter(isRunActive);
  if (live.length === 0 && !error) return null;

  const cancel = async (runId: number) => {
    setCancelling(runId);
    setError(null);
    try {
      await facelessApi.cancelRun(runId);
      await refreshProject();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not cancel'));
    } finally {
      setCancelling(null);
    }
  };

  return (
    <div className="mb-6 space-y-2" aria-live="polite">
      {live.map((run) => {
        const done = run.items.filter((i) => i.status === 'done').length;
        return (
          <div key={run.id} className="beam-border panel flex flex-wrap items-center gap-3 rounded-xl px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm">
                {stepLabel(run.step)}, {run.status === 'queued' ? 'queued' : `${done} of ${run.items.length} done`}
                <span className="ml-2 text-xs text-muted-foreground">
                  <span className="font-mono tabular">{formatUsd(run.usd_spent)}</span> of <span className="font-mono tabular">{formatUsd(run.estimated_usd)}</span> estimated
                  <Elapsed since={run.started_at ?? run.created_at} className="ml-2 font-mono tabular" />
                </span>
              </p>
              <Progress value={run.progress} className="mt-2 h-1.5" aria-label={`${stepLabel(run.step)} progress`} />
            </div>
            <span className="w-10 text-right font-mono text-xs tabular text-muted-foreground">{run.progress}%</span>
            {!run.cancel_requested ? (
              <Button variant="outline" size="sm" onClick={() => cancel(run.id)} disabled={cancelling === run.id}>
                <X className="h-3.5 w-3.5" /> {cancelling === run.id ? 'Cancelling' : 'Cancel'}
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">Cancelling</span>
            )}
          </div>
        );
      })}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
