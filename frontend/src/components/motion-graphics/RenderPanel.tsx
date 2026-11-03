import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Download, Info, Loader2, ShieldAlert, ShieldCheck, Square, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { formatUsd } from '@/stores/pricingStore';
import { useMotionGraphicsStore } from '@/stores/motionGraphicsStore';
import { friendlyError, getErrorMessage } from '@/utils/errors';
import {
  ACTIVE_JOB,
  ASPECT_LABEL,
  motionGraphicsApi,
  newIdempotencyKey,
  SAFE_ZONE_LABEL,
  type JobKind,
  type MGAspect,
  type MGCatalog,
  type MGProject,
  type MGSpec,
  type MGTemplate,
  type Quote,
  type SafeZonePreset,
} from '@/api/motionGraphics';
import { ASPECT_RATIO_CLASS, AspectGlyph, ErrorNote, FieldLabel, MutedChip, PillGroup, SectionTitle, formatSeconds } from './shared';

// Server times are naive UTC; read them as UTC so the elapsed clock is right.
function parseServerTime(s: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}

/** Minutes and seconds since the job started, ticking once a second. */
function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const start = parseServerTime(since);
  if (!Number.isFinite(start)) return null;
  return <span className="font-mono tabular">{formatSeconds(Math.max(0, (now - start) / 1000))}</span>;
}

const ITEM_STATUS: Record<string, string> = {
  queued: 'Queued',
  pending: 'Queued',
  running: 'Working',
  submitted: 'Working',
  done: 'Done',
  completed: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
  skipped: 'Skipped',
};

export function QuoteDialog({
  open,
  onOpenChange,
  project,
  kind,
  onStarted,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  project: MGProject;
  kind: JobKind;
  onStarted: () => void;
}) {
  const saveNow = useMotionGraphicsStore((s) => s.saveNow);
  const watchJob = useMotionGraphicsStore((s) => s.watchJob);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [key, setKey] = useState(() => newIdempotencyKey('mg'));
  // Synchronous guard: two clicks in one frame both see starting === false.
  const inFlight = useRef(false);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setQuote(null);
    setError(null);
    setKey(newIdempotencyKey('mg'));
    setLoading(true);
    (async () => {
      await saveNow();
      try {
        const q = await motionGraphicsApi.quote(project.id, kind);
        if (alive) setQuote(q);
      } catch (err) {
        if (alive) setError(getErrorMessage(err, 'Could not price this job'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [open, project.id, kind, saveNow]);

  const confirm = async () => {
    if (!quote || inFlight.current) return;
    inFlight.current = true;
    setStarting(true);
    setError(null);
    try {
      const job = await motionGraphicsApi.startJob(project.id, kind, key);
      watchJob(job);
      onStarted();
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not start the job'));
    } finally {
      inFlight.current = false;
      setStarting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{kind === 'render' ? 'Render' : 'Generate audio'}</DialogTitle>
          <DialogDescription>
            {kind === 'render'
              ? 'Everything the render needs, estimated line by line.'
              : 'The voiceover and music only, so you can listen before rendering.'}
          </DialogDescription>
        </DialogHeader>
        {loading && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <div className="shimmer h-4 w-3/4 rounded" />
            <div className="shimmer h-4 w-2/3 rounded" />
            <div className="shimmer h-4 w-1/2 rounded" />
            <div className="shimmer mt-3 h-6 w-1/3 rounded" />
          </div>
        )}
        {quote && (
          <div className="space-y-3">
            <div className="divide-y divide-border rounded-lg border border-border">
              {quote.breakdown.map((b, i) => (
                <div key={i} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate">{b.label}</p>
                    <p className="font-mono text-[11px] tabular text-muted-foreground">
                      {b.units} x {formatUsd(b.unit_usd)} per {b.unit}
                    </p>
                  </div>
                  <span className="font-mono text-sm tabular">{formatUsd(b.estimated_usd)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-sm font-medium">Estimated total</span>
                <span className="font-mono text-lg font-semibold tabular text-foreground">{formatUsd(quote.estimated_usd)}</span>
              </div>
            </div>
            <ul className="space-y-1">
              {quote.notes.map((n) => (
                <li key={n} className="flex gap-2 text-xs text-muted-foreground">
                  <Info className="mt-0.5 h-3 w-3 shrink-0" /> {n}
                </li>
              ))}
              {quote.warnings.map((n) => (
                <li key={n} className="flex gap-2 text-xs text-warning">
                  <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0" /> {n}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Estimated from a built-in price table, not fal's invoice.
              {kind === 'render' && ' Rendering runs on this machine, so it has no provider cost.'}
            </p>
          </div>
        )}
        {error && <ErrorNote>{error}</ErrorNote>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={!quote || starting}>
            {starting && <Loader2 className="h-4 w-4 animate-spin" />}
            {starting ? 'Starting' : quote ? `Confirm, ${formatUsd(quote.estimated_usd)}` : 'Confirm'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RenderPanel({
  catalog,
  tpl,
  project,
  spec,
  onSpec,
  onRender,
}: {
  catalog: MGCatalog;
  tpl: MGTemplate;
  project: MGProject;
  spec: MGSpec;
  onSpec: (fn: (s: MGSpec) => MGSpec) => void;
  onRender: () => void;
}) {
  const setProject = useMotionGraphicsStore((s) => s.setProject);
  const watchJob = useMotionGraphicsStore((s) => s.watchJob);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState<MGAspect>(project.aspect);
  const job = project.active_job;
  const lastJob = project.jobs[0];
  const outputs = project.outputs;
  const variants = project.variants ?? [];

  const update = async (body: Parameters<typeof motionGraphicsApi.updateProject>[1]) => {
    setBusy(true);
    setError(null);
    try {
      setProject(await motionGraphicsApi.updateProject(project.id, body));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not update the project'));
    } finally {
      setBusy(false);
    }
  };

  const toggleVariant = (a: MGAspect) =>
    update({ variants: variants.includes(a) ? variants.filter((x) => x !== a) : [...variants, a] });

  const out = outputs[shown] ?? Object.values(outputs)[0];
  const blocking = project.validation.errors;
  const opt = spec.options;
  const setOpt = (patch: Partial<MGSpec['options']>) => onSpec((s) => ({ ...s, options: { ...s.options, ...patch } }));

  return (
    <div className="space-y-5">
      <div>
        <SectionTitle>Outputs</SectionTitle>
        <FieldLabel hint="layout reflows for each, nothing is cropped">Primary aspect</FieldLabel>
        <PillGroup
          value={project.aspect}
          disabled={busy || !!job}
          onChange={(a) => update({ aspect: a, variants: variants.filter((x) => x !== a) })}
          options={tpl.aspects.map((a) => ({
            id: a,
            label: (
              <span className="flex items-center gap-1.5">
                <AspectGlyph aspect={a} /> {a}
              </span>
            ),
            title: ASPECT_LABEL[a],
          }))}
        />
        <div className="mt-3">
          <FieldLabel hint="rendered in the same job">Also render</FieldLabel>
          <div className="flex flex-wrap gap-2">
            {tpl.aspects
              .filter((a) => a !== project.aspect)
              .map((a) => (
                <label key={a} className="flex min-h-8 items-center gap-2 rounded-md border border-border px-3 text-xs">
                  <Switch checked={variants.includes(a)} disabled={busy || !!job} onCheckedChange={() => toggleVariant(a)} />
                  <span className="font-mono">{a}</span>
                </label>
              ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <FieldLabel hint="where text and logos may go">Safe zones</FieldLabel>
          <Select value={opt.safe_zone} onValueChange={(v) => setOpt({ safe_zone: v as SafeZonePreset })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {catalog.safe_zone_presets.map((z) => (
                <SelectItem key={z} value={z}>
                  {SAFE_ZONE_LABEL[z]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={opt.loop} onCheckedChange={(v) => setOpt({ loop: v })} /> Seamless loop
        </label>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch
            checked={opt.captions ?? tpl.id !== 'kinetic_quote'}
            onCheckedChange={(v) => setOpt({ captions: v })}
          />
          Captions
        </label>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={opt.logo_bug} onCheckedChange={(v) => setOpt({ logo_bug: v })} /> Logo corner bug
        </label>
      </div>

      <ReelSeries opt={opt} setOpt={setOpt} />

      <div className="space-y-3 rounded-lg border border-border p-3">
        <SectionTitle>Sources and disclosure</SectionTitle>
        <div>
          <FieldLabel hint={tpl.requires_source ? 'required' : 'optional'} count={(spec.source ?? '').length} max={160}>
            Source
          </FieldLabel>
          <Input
            value={spec.source ?? ''}
            onChange={(e) => onSpec((s) => ({ ...s, source: e.target.value || null }))}
            placeholder="Publisher or dataset, year"
          />
        </div>
        {tpl.requires_disclaimer && (
          <div>
            <FieldLabel hint="required, shown for at least 2 s" count={(spec.disclaimer ?? '').length} max={400}>
              Finance disclaimer
            </FieldLabel>
            <Textarea
              rows={3}
              value={spec.disclaimer ?? ''}
              onChange={(e) => onSpec((s) => ({ ...s, disclaimer: e.target.value || null }))}
              className="text-sm"
            />
          </div>
        )}
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch
            checked={opt.paid_partnership.enabled}
            onCheckedChange={(v) => setOpt({ paid_partnership: { ...opt.paid_partnership, enabled: v } })}
          />
          Paid partnership label
        </label>
        {opt.paid_partnership.enabled && (
          <Input
            value={opt.paid_partnership.brand ?? ''}
            maxLength={60}
            placeholder="Brand that paid for this video"
            onChange={(e) => setOpt({ paid_partnership: { ...opt.paid_partnership, brand: e.target.value || null } })}
          />
        )}
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={opt.ai_label} onCheckedChange={(v) => setOpt({ ai_label: v })} /> On-screen AI voice label
        </label>
        <ul className="space-y-2 pt-1">
          {project.compliance.map((c) => (
            <li key={c.id} className="flex gap-2 text-xs">
              {c.level === 'ok' ? (
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
              ) : c.level === 'error' ? (
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
              ) : (
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              )}
              <span>
                <span className="font-medium text-foreground">{c.title}.</span>{' '}
                <span className="text-muted-foreground">{c.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {blocking.length > 0 && (
        <ErrorNote>
          Fix before rendering: {blocking[0].message}
          {blocking.length > 1 ? ` (and ${blocking.length - 1} more)` : ''}
        </ErrorNote>
      )}

      {job && ACTIVE_JOB.includes(job.status) ? (
        <div className="beam-border space-y-3 rounded-lg border border-border p-3" aria-live="polite">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">
              {job.status === 'render_queued'
                ? 'Waiting for a render slot'
                : job.status === 'rendering'
                  ? 'Rendering'
                  : 'Generating audio and images'}
              {job.items.length > 1 &&
                `, ${job.items.filter((i) => i.status === 'done' || i.status === 'completed').length} of ${job.items.length} done`}
            </span>
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              <Elapsed since={job.created_at} />
              <span className="font-mono tabular">{job.progress}%</span>
            </span>
          </div>
          <Progress value={job.progress} />
          <ul className="space-y-1">
            {job.items.map((i) => (
              <li key={i.id} className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{i.label}</span>
                <span className={cn(i.status === 'done' && 'text-success', i.status === 'failed' && 'text-destructive')}>
                  {ITEM_STATUS[i.status] ?? i.status}
                </span>
              </li>
            ))}
          </ul>
          <Button
            variant="outline"
            size="sm"
            disabled={job.cancel_requested}
            onClick={async () => watchJob(await motionGraphicsApi.cancelJob(job.id))}
          >
            <Square className="h-3.5 w-3.5" /> {job.cancel_requested ? 'Cancelling' : 'Cancel'}
          </Button>
        </div>
      ) : (
        <Button size="lg" className="w-full" onClick={onRender} disabled={blocking.length > 0}>
          Render {1 + variants.length > 1 ? `${1 + variants.length} versions` : ''}
        </Button>
      )}

      {lastJob && !ACTIVE_JOB.includes(lastJob.status) && lastJob.status !== 'completed' && (
        <div className="flex gap-2 rounded-lg border border-border p-3 text-xs">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div>
            <p className="text-foreground">Last job {lastJob.status}.</p>
            <p className="text-muted-foreground">{friendlyError(lastJob.error, 'Please try again.')}</p>
          </div>
        </div>
      )}

      {job && ACTIVE_JOB.includes(job.status) && job.kind === 'render' && Object.keys(outputs).length === 0 && (
        <div
          className={cn(
            'flex w-full items-center justify-center rounded-lg border border-dashed border-border bg-secondary/20 text-xs text-muted-foreground',
            ASPECT_RATIO_CLASS[project.aspect],
          )}
        >
          The video appears here when it is ready
        </div>
      )}

      {Object.keys(outputs).length > 0 && out && (
        <div className="space-y-3">
          <SectionTitle
            aside={
              <PillGroup
                size="xs"
                value={shown}
                onChange={setShown}
                options={(Object.keys(outputs) as MGAspect[]).map((a) => ({ id: a, label: a }))}
              />
            }
          >
            Result
          </SectionTitle>
          <video
            key={out.url}
            src={out.url}
            controls
            playsInline
            className="w-full rounded-lg border border-border bg-background"
            style={out.width && out.height ? { aspectRatio: `${out.width} / ${out.height}` } : undefined}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 font-mono text-xs tabular text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-success" /> {out.width}x{out.height}, {formatSeconds(out.duration)}
            </span>
            {out.stale && <MutedChip>Storyboard edited since</MutedChip>}
          </div>
          <div className="flex flex-wrap gap-2">
            {(Object.entries(outputs) as [MGAspect, NonNullable<MGProject['outputs'][MGAspect]>][]).map(([a, o]) => (
              <Button key={a} asChild variant="outline" size="sm">
                <a href={o.download_url} download target="_blank" rel="noreferrer">
                  <Download className="h-3.5 w-3.5" /> {a}
                </a>
              </Button>
            ))}
            <Button asChild variant="ghost" size="sm">
              <Link to="/gallery">Open gallery</Link>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// Reel series: a header on every frame with the part number and pips, an
// optional progress bar, and the next part number on the Next part card.
function ReelSeries({ opt, setOpt }: { opt: MGSpec['options']; setOpt: (o: Partial<MGSpec['options']>) => void }) {
  const ser = opt.series ?? { enabled: false, name: '', part: 1, total: 3 };
  const setSer = (patch: Partial<typeof ser>) => setOpt({ series: { ...ser, ...patch } });
  const num = (v: string, lo: number) => Math.max(lo, Math.min(30, Math.round(Number(v) || lo)));
  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <SectionTitle>Reel series</SectionTitle>
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Switch checked={ser.enabled} onCheckedChange={(v) => setSer({ enabled: v })} /> Part header on every frame
      </label>
      {ser.enabled && (
        <div className="grid grid-cols-[1fr_4.5rem_4.5rem] gap-2">
          <div>
            <FieldLabel count={ser.name.length} max={40}>
              Series name
            </FieldLabel>
            <Input value={ser.name} maxLength={40} placeholder="Relay 101" onChange={(e) => setSer({ name: e.target.value })} />
          </div>
          <div>
            <FieldLabel>Part</FieldLabel>
            <Input type="number" min={1} max={30} value={ser.part} onChange={(e) => setSer({ part: num(e.target.value, 1) })} />
          </div>
          <div>
            <FieldLabel>Of</FieldLabel>
            <Input type="number" min={1} max={30} value={ser.total} onChange={(e) => setSer({ total: num(e.target.value, 1) })} />
          </div>
        </div>
      )}
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Switch checked={!!opt.progress_bar} onCheckedChange={(v) => setOpt({ progress_bar: v })} /> Progress bar
      </label>
      <p className="text-xs text-muted-foreground">
        Add a Poll or Next part scene from the storyboard to ask for comments and tease the next part.
      </p>
    </div>
  );
}
