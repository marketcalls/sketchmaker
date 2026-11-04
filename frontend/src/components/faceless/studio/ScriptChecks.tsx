import { useState } from 'react';
import { Fingerprint, Loader2, RefreshCw, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { facelessApi, type FacelessProject } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { FlagList, Kicker } from '../shared';

const VERDICT: Record<string, { label: string; cls: string }> = {
  original: { label: 'Original', cls: 'text-success' },
  similar: { label: 'Similar to earlier work', cls: 'text-warning' },
  repetitive: { label: 'Repetitive', cls: 'text-destructive' },
};

// Originality and compliance, both computed by the backend on every saved
// version. Re-check forces a fresh run.
export function ScriptChecks({ project }: { project: FacelessProject }) {
  const refreshProject = useFacelessStore((s) => s.refreshProject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const o = project.originality;
  const c = project.compliance;
  const stale =
    (o?.script_version != null && o.script_version !== project.script_version) ||
    (c?.script_version != null && c.script_version !== project.script_version);

  const recheck = async () => {
    setBusy(true);
    setError(null);
    try {
      await Promise.all([facelessApi.originality(project.id, true), facelessApi.compliance(project.id, true)]);
      await refreshProject();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not run the checks'));
    } finally {
      setBusy(false);
    }
  };

  const verdict = o && !o.unavailable ? VERDICT[o.verdict] ?? { label: o.verdict, cls: '' } : null;
  const counts = {
    block: c?.flags.filter((f) => f.severity === 'block').length ?? 0,
    warn: c?.flags.filter((f) => f.severity === 'warn').length ?? 0,
  };

  return (
    <div className="space-y-4">
      <section className="panel rounded-xl p-4" aria-labelledby="orig-title">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 id="orig-title" className="flex items-center gap-2 text-base font-semibold">
            <Fingerprint className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> Originality
          </h3>
          <Button variant="ghost" size="sm" onClick={recheck} disabled={busy || !project.script}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {busy ? 'Checking' : 'Re-check'}
          </Button>
        </div>
        {!o || o.unavailable ? (
          <p className="text-sm text-muted-foreground">{o?.unavailable ? 'The originality check is not available yet.' : 'Runs when the script is saved.'}</p>
        ) : (
          <>
            <div className="flex items-end gap-3">
              <span className="font-mono text-3xl font-medium tabular text-foreground">{o.score}</span>
              <div className="pb-1">
                <p className={cn('text-sm', verdict?.cls)}>{verdict?.label}</p>
                <p className="text-[11px] text-muted-foreground">vs {o.compared} earlier script{o.compared === 1 ? '' : 's'}</p>
              </div>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary" aria-hidden="true">
              <div className="h-full rounded-full bg-foreground/60" style={{ width: `${Math.max(2, Math.min(100, o.score))}%` }} />
            </div>
            {o.same_situation_same_outcome && (
              <p className="mt-3 rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
                Same situation and same outcome as an earlier episode. Platforms treat this as repetitive content.
              </p>
            )}
            {o.findings.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {o.findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            )}
            {o.closest.length > 0 && (
              <div className="mt-3">
                <Kicker className="mb-1">Closest</Kicker>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {o.closest.slice(0, 3).map((m) => (
                    <li key={`${m.index}-${m.title}`} className="flex justify-between gap-2">
                      <span className="truncate">{m.title || `Script ${m.index + 1}`}</span>
                      <span className="font-mono tabular">{Math.round(m.similarity * 100)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {o.suggestions.length > 0 && (
              <div className="mt-3">
                <Kicker className="mb-1">Ideas to vary it</Kicker>
                <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
                  {o.suggestions.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </section>

      <section className="panel rounded-xl p-4" aria-labelledby="comp-title">
        <h3 id="comp-title" className="mb-1 flex items-center gap-2 text-base font-semibold">
          <ShieldCheck className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> Compliance
        </h3>
        {c && !c.unavailable && (
          <p className="mb-3 text-xs text-muted-foreground">
            {counts.block} blocking, {counts.warn} warnings
          </p>
        )}
        {!c || c.unavailable ? (
          <p className="text-sm text-muted-foreground">{c?.unavailable ? 'The compliance check is not available yet.' : 'Runs when the script is saved.'}</p>
        ) : (
          <FlagList flags={c.flags} empty="No issues found." />
        )}
      </section>
      {stale && <p className="text-xs text-warning">The checks are from an older version. Re-check to update them.</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
