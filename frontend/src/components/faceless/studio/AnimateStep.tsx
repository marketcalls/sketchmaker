import { useEffect, useMemo, useState } from 'react';
import { Film, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { QualityBadge, useQualityConfig } from '@/components/quality/QualityBadge';
import { cn } from '@/lib/utils';
import { errorSuffix, friendlyError, getErrorMessage } from '@/utils/errors';
import { formatUsd, usePricingStore, videoKey } from '@/stores/pricingStore';
import { facelessApi, type ClipMode, type ClipResolution, type FacelessProject, type StepRun } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { ASPECT_CLASS, AssetStateIcon, EmptyState, ErrorNote, FieldLabel, Kicker, PillGroup } from '../shared';
import { usePaidStep } from './usePaidStep';
import { usePaidGate } from './gate';
import { useLiveQuote } from './useLiveQuote';
import { saveShotKind, worstQuality } from './StoryboardStep';
import { assetsOf, clipScenes, hasClip, hasStill, sceneAssetState, sceneRunState } from './stepState';

export function AnimateStep({ project, runs }: { project: FacelessProject; runs: StepRun[] }) {
  const { config, setProject } = useFacelessStore();
  const { getModelCost } = usePricingStore();
  const gate = usePaidGate(project, 'clips');
  const { request, dialog } = usePaidStep(project.id);
  const scenes = project.script?.scenes ?? [];
  const clipList = clipScenes(scenes);
  const stillList = scenes.filter((s) => s.shot.kind === 'still');
  const resolutions = config?.models.clip_resolutions ?? ['480p', '768p', '1080p'];
  const [resolution, setResolution] = useState<ClipResolution>(
    project.settings.clip_resolution ?? config?.models.default_clip_resolution ?? '768p',
  );
  const [mode, setMode] = useState<ClipMode>(project.settings.clip_mode ?? 'image');
  const [maxParts, setMaxParts] = useState(2);
  const qa = useQualityConfig();
  const [checkClips, setCheckClips] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Default selection: clip scenes without a clip yet.
  const missingKey = clipList.filter((s) => !hasClip(assetsOf(project, s.id))).map((s) => s.id).join(',');
  useEffect(() => {
    setSelected(missingKey ? missingKey.split(',') : []);
  }, [missingKey]);

  const options = useMemo(
    () => ({ resolution, mode, max_clips_per_scene: maxParts, quality_check: checkClips }),
    [resolution, mode, maxParts, checkClips],
  );
  const live = useLiveQuote(project.id, 'clips', selected, options, selected.length > 0 && !gate, `${project.updated_at}`);
  const perSecond = getModelCost(videoKey('h3-max', resolution));

  const persist = async (patch: { clip_resolution?: ClipResolution; clip_mode?: ClipMode }) => {
    try {
      setProject(await facelessApi.updateProject(project.id, { settings: patch }));
    } catch {
      // the choice still applies to this run
    }
  };

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const markAnimated = async (sceneId: string) => {
    setBusy(sceneId);
    setError(null);
    try {
      setProject(await saveShotKind(project, sceneId, 'clip'));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not change the shot'));
    } finally {
      setBusy(null);
    }
  };

  if (scenes.length === 0) {
    return <EmptyState icon={Film} title="Script first">Animated scenes come from the script and the storyboard.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <div className="panel space-y-4 rounded-xl p-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <FieldLabel hint={perSecond !== undefined ? `${formatUsd(perSecond)} per second` : undefined}>Resolution</FieldLabel>
            <PillGroup<ClipResolution>
              label="Clip resolution"
              value={resolution}
              onChange={(r) => {
                setResolution(r);
                persist({ clip_resolution: r });
              }}
              options={resolutions.map((r) => ({ value: r, label: r }))}
            />
          </div>
          <div>
            <FieldLabel>Made from</FieldLabel>
            <PillGroup<ClipMode>
              label="Clip mode"
              value={mode}
              onChange={(m) => {
                setMode(m);
                persist({ clip_mode: m });
              }}
              options={[
                { value: 'image', label: 'The still', hint: 'Image to video from the storyboard still' },
                { value: 'reference', label: 'Cast references', hint: 'Reference to video from the character photos, for stronger likeness' },
              ]}
            />
          </div>
          <div>
            <FieldLabel hint="2 to 15 s each">Clips per scene, up to</FieldLabel>
            <PillGroup<string>
              label="Clips per scene"
              value={String(maxParts)}
              onChange={(v) => setMaxParts(Number(v))}
              options={['1', '2', '3', '4'].map((v) => ({ value: v, label: v }))}
            />
          </div>
        </div>
        <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-h-10 text-sm" aria-live="polite">
            {selected.length === 0 ? (
              <span className="text-muted-foreground">Choose scenes to animate.</span>
            ) : live.loading ? (
              <div className="flex items-center gap-2 text-muted-foreground"><Skeleton className="h-7 w-24" /> <span className="sr-only">Pricing</span></div>
            ) : live.quote ? (
              <>
                <span className="font-mono text-xl font-medium tabular text-foreground">{formatUsd(live.quote.usd)}</span>
                <span className="ml-1 text-muted-foreground">estimated for {selected.length} scene{selected.length === 1 ? '' : 's'}</span>
                {live.quote.assumptions[0] && <p className="text-[11px] text-muted-foreground">{live.quote.assumptions[0]}</p>}
              </>

            ) : live.error ? (
              <span className="text-warning">{friendlyError(live.error)}</span>
            ) : gate ? (
              <span className="text-muted-foreground">{gate}.</span>
            ) : null}
          </div>
          {qa?.available && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch checked={checkClips} onCheckedChange={setCheckClips} aria-label="Check each clip" />
              Check each clip
              <span className="font-mono text-[11px] tabular">+{formatUsd(qa.estimated_usd)}</span>
            </label>
          )}
          <Button
            disabled={!!gate || selected.length === 0 || !!live.error}
            title={gate ?? undefined}
            onClick={() =>
              request({
                step: 'clips',
                sceneIds: selected,
                options,
                title: 'Animate scenes',
                description: `H3 Max clips at ${resolution} for ${selected.length} scene${selected.length === 1 ? '' : 's'}, from ${mode === 'image' ? 'the storyboard stills' : 'the cast references'}.`,
              })
            }
          >
            <Film className="h-4 w-4" /> Animate {selected.length || ''}
          </Button>
        </div>
      </div>

      {clipList.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No scene is marked Animate yet. Pick scenes below, or set the shot to Animate in the storyboard.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Scenes to animate">
          {clipList.map((scene) => {
            const a = assetsOf(project, scene.id);
            const clips = (a?.clips ?? []).filter((c) => c?.url);
            const still = a?.stills.find((s) => s?.url);
            const { running, failed } = sceneRunState(project, runs, 'clips', scene.id);
            const position = scenes.findIndex((s) => s.id === scene.id);
            const on = selected.includes(scene.id);
            return (
              <li key={scene.id} className={cn('overflow-hidden rounded-xl border bg-card shadow-card', running ? 'beam-border' : on ? 'border-primary/60' : 'border-border')}>
                <div className={cn('relative bg-secondary/40', ASPECT_CLASS[project.aspect], project.aspect === '9:16' && 'max-h-[420px] w-full')}>
                  {clips[0]?.url ? (
                    <video src={clips[0].url} poster={still?.url ?? undefined} className="h-full w-full object-cover" controls muted loop playsInline aria-label={`Scene ${position + 1} clip`} />
                  ) : still?.url ? (
                    <img src={still.url} alt={`Scene ${position + 1} still`} className="h-full w-full object-cover opacity-70" />
                  ) : (
                    <div className="flex h-full items-center justify-center p-4 text-center text-xs text-muted-foreground">
                      {mode === 'image' ? 'Needs a storyboard still first' : 'Will use the cast references'}
                    </div>
                  )}
                  {running && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/60" role="status">
                      <span className="rounded-md bg-background/80 px-2 py-1 text-xs text-foreground">Animating</span>
                    </div>
                  )}
                </div>
                <div className="space-y-2 p-3">
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-[var(--color-primary)]"
                      checked={on}
                      onChange={() => toggle(scene.id)}
                      disabled={running}
                    />
                    <span className="font-mono text-[11px] tabular text-muted-foreground">{String(position + 1).padStart(2, '0')}</span>
                    <span className="truncate">{scene.beat_name || scene.beat}</span>
                    <span className="ml-auto">
                      <AssetStateIcon state={sceneAssetState(running, clips.length > 0, !!failed)} label="Clip" />
                    </span>
                  </label>
                  <p className="text-[11px] text-muted-foreground">
                    {clips.length > 0
                      ? `${clips.length} clip${clips.length === 1 ? '' : 's'}, ${clips.map((c) => `${c?.duration ?? '?'}s ${c?.resolution ?? ''}`).join(', ')}`
                      : !hasStill(a) && mode === 'image'
                        ? 'No still yet'
                        : `about ${Math.round(a?.duration ?? 0)}s of scene`}
                  </p>
                  {clips.length > 1 && (
                    <div className="flex gap-1.5 overflow-x-auto">
                      {clips.slice(1).map((c, i) => (
                        <video key={i} src={c?.url ?? undefined} className="h-16 shrink-0 rounded border border-border" muted controls aria-label={`Scene ${position + 1} clip ${i + 2}`} />
                      ))}
                    </div>
                  )}
                  {failed && !running && (
                    <p className="flex flex-wrap items-center gap-1.5 text-xs text-destructive">
                      Failed{errorSuffix(failed.error)}
                    </p>
                  )}
                  {!running && worstQuality(a?.clips) && (
                    <QualityBadge
                      quality={worstQuality(a?.clips)}
                      fixes={[{ target: 'defects', label: 'Regenerate clip' }]}
                      onFix={() =>
                        request({
                          step: 'clips',
                          sceneIds: [scene.id],
                          options,
                          title: `Regenerate scene ${position + 1}`,
                          description: `New H3 Max clips at ${resolution} for "${scene.beat_name || scene.beat}".`,
                        })
                      }
                      busy={!!gate}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {stillList.length > 0 && (
        <section aria-labelledby="animate-more">
          <Kicker className="mb-2">
            <span id="animate-more">Still scenes you could animate</span>
          </Kicker>
          <ul className="flex flex-wrap gap-2">
            {stillList.map((s) => (
              <li key={s.id}>
                <Button variant="outline" size="sm" onClick={() => markAnimated(s.id)} disabled={busy === s.id}>
                  {busy === s.id && <Loader2 className="h-3 w-3 animate-spin" />}
                  {String(scenes.findIndex((x) => x.id === s.id) + 1).padStart(2, '0')} {s.beat_name || s.beat}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <ErrorNote>{error}</ErrorNote>
      {dialog}
    </div>
  );
}
