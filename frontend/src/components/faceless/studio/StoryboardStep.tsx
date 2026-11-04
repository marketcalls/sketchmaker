import { useState } from 'react';
import { ImagePlus, LayoutGrid, RefreshCcw, Type, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { QualityBadge, useQualityConfig } from '@/components/quality/QualityBadge';
import { cn } from '@/lib/utils';
import { errorSuffix, getErrorMessage } from '@/utils/errors';
import { getModelDisplayName } from '@/utils/models';
import { editKey, formatUsd, imageKey, usePricingStore } from '@/stores/pricingStore';
import {
  SHOT_KINDS,
  facelessApi,
  type FacelessProject,
  type Scene,
  type ShotKind,
  type StepRun,
  type StillResolution,
} from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import type { Quality } from '@/api/quality';
import { ASPECT_CLASS, AssetStateIcon, EmptyState, ErrorNote, Kicker, MutedChip } from '../shared';
import { usePaidStep } from './usePaidStep';
import { usePaidGate } from './gate';
import { assetsOf, hasStill, sceneAssetState, sceneRunState, storyboardScenes } from './stepState';

// Saves one scene's shot kind as a new script version.
export async function saveShotKind(project: FacelessProject, sceneId: string, kind: ShotKind): Promise<FacelessProject> {
  if (!project.script) throw new Error('No script');
  const scenes = project.script.scenes.map((s) => (s.id === sceneId ? { ...s, shot: { ...s.shot, kind } } : s));
  return facelessApi.saveScript(project.id, { ...project.script, scenes });
}

// The check to show for a scene's stills or clips: the worst verdict first,
// so a failed still is never hidden behind a passing one.
const VERDICT_ORDER = ['fail', 'warn', 'unverified', 'pass'];
export function worstQuality(entries: ({ quality?: Quality | null } | null)[] | undefined): Quality | null {
  const checks = (entries ?? []).map((e) => e?.quality).filter((q): q is Quality => !!q);
  if (checks.some((q) => q.status === 'pending')) return checks.find((q) => q.status === 'pending') ?? null;
  return [...checks].sort((a, b) => VERDICT_ORDER.indexOf(a.verdict ?? 'unverified') - VERDICT_ORDER.indexOf(b.verdict ?? 'unverified'))[0] ?? null;
}

function SceneCard({
  project,
  scene,
  position,
  runs,
  gate,
  onRegenerate,
}: {
  project: FacelessProject;
  scene: Scene;
  position: number;
  runs: StepRun[];
  gate: string | null;
  onRegenerate: (s: Scene) => void;
}) {
  const setProject = useFacelessStore((s) => s.setProject);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const a = assetsOf(project, scene.id);
  const still = a?.stills.find((s) => s?.url) ?? null;
  const stillCount = a?.stills.filter((s) => s?.url).length ?? 0;
  const own = a?.user_media;
  const { running, failed } = sceneRunState(project, runs, 'storyboard', scene.id);
  const kind = scene.shot.kind;
  const quality = kind === 'user_media' || kind === 'card' ? null : worstQuality(a?.stills);

  const changeKind = async (k: ShotKind) => {
    if (k === kind) return;
    if (k === 'user_media' && !own) {
      media.open();
      return;
    }
    setBusy('Saving');
    setError(null);
    try {
      setProject(await saveShotKind(project, scene.id, k));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not change the shot'));
    } finally {
      setBusy(null);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy('Uploading');
    setError(null);
    try {
      const p = await facelessApi.uploadSceneMedia(project.id, scene.id, file);
      setProject(kind === 'user_media' ? p : await saveShotKind(p, scene.id, 'user_media'));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not upload'));
    } finally {
      setBusy(null);
    }
  };

  const media = useMediaPicker({
    kinds: ['image', 'video'],
    accept: 'image/png,image/jpeg,image/webp,image/avif,video/mp4,video/quicktime,video/webm',
    title: 'Use your own image or video',
    disabled: !!busy,
    onFiles: (files) => upload(files[0]),
  });

  const removeOwn = async () => {
    setBusy('Removing');
    try {
      const p = await facelessApi.deleteSceneMedia(project.id, scene.id);
      setProject(kind === 'user_media' ? await saveShotKind(p, scene.id, 'still') : p);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not remove'));
    } finally {
      setBusy(null);
    }
  };

  const showOwn = kind === 'user_media' && own?.url;

  return (
    <article className={cn('flex flex-col overflow-hidden rounded-xl border bg-card shadow-card', running || busy ? 'beam-border' : failed && !hasStill(a) ? 'border-destructive/40' : 'border-border')}>
      <div
        {...media.dropProps}
        className={cn(
          'relative w-full overflow-hidden bg-secondary/40',
          ASPECT_CLASS[project.aspect],
          project.aspect === '9:16' && 'max-h-[420px]',
          media.dragOver && 'ring-2 ring-inset ring-primary',
        )}
      >
        {showOwn ? (
          own?.kind === 'video' ? (
            <video src={own.url ?? undefined} className="h-full w-full object-cover" muted loop playsInline controls aria-label={`Scene ${position + 1} video`} />
          ) : (
            <img src={own?.url ?? undefined} alt={`Scene ${position + 1}, your image`} className="h-full w-full object-cover" />
          )
        ) : kind === 'card' ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-background p-4 text-center">
            <Type className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            <p className="text-lg font-semibold">{scene.on_screen_text || scene.stat?.value || scene.beat_name}</p>
            {scene.stat?.label && <p className="text-[11px] text-muted-foreground">{scene.stat.label}</p>}
          </div>
        ) : still?.url ? (
          <img src={still.url} alt={`Scene ${position + 1} storyboard`} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <LayoutGrid className="h-6 w-6 text-muted-foreground/40" aria-hidden="true" />
          </div>
        )}
        {(running || busy) && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/60" role="status">
            <span className="rounded-md bg-background/80 px-2 py-1 text-xs text-foreground">{busy ?? 'Generating'}</span>
          </div>
        )}
        <span className="absolute left-2 top-2 rounded-md bg-background/80 px-2 py-0.5 font-mono text-[11px] tabular">
          {String(position + 1).padStart(2, '0')}
        </span>
        {stillCount > 1 && kind !== 'user_media' && (
          <span className="absolute right-2 top-2 rounded-md bg-background/80 px-2 py-0.5 text-[11px]">{stillCount} stills</span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <AssetStateIcon state={sceneAssetState(running, kind === 'card' || hasStill(a) || !!own, !!failed)} label="Picture" />
          <p className="truncate text-sm">{scene.beat_name || scene.beat}</p>
          {scene.shot.characters.length > 0 && <MutedChip className="ml-auto">{scene.shot.characters.length} cast</MutedChip>}
        </div>
        <p className="line-clamp-2 text-xs text-muted-foreground">{scene.narration}</p>
        <div role="radiogroup" aria-label={`Scene ${position + 1} shot`} className="flex flex-wrap gap-1">
          {SHOT_KINDS.map((k) => (
            <button
              key={k.value}
              type="button"
              role="radio"
              aria-checked={kind === k.value}
              title={k.hint}
              disabled={!!busy}
              onClick={() => changeKind(k.value)}
              className={cn(
                'min-h-8 rounded-md border px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40',
                kind === k.value ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {k.label}
            </button>
          ))}
        </div>
        {failed && !running && (
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-destructive">
            Failed{errorSuffix(failed.error)}
          </p>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
        {quality && !running && (
          <QualityBadge
            quality={quality}
            fixes={[{ target: 'defects', label: 'Regenerate still' }]}
            onFix={() => onRegenerate(scene)}
            busy={!!gate || !!busy}
          />
        )}
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {(kind === 'still' || kind === 'clip') && (
            <Button variant="outline" size="sm" onClick={() => onRegenerate(scene)} disabled={!!gate || running || !!busy} title={gate ?? undefined}>
              {hasStill(a) ? <RefreshCcw className="h-3.5 w-3.5" /> : <ImagePlus className="h-3.5 w-3.5" />}
              {hasStill(a) ? 'Regenerate' : 'Generate'}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={media.open} disabled={!!busy} title="Use your own image or video">
            <Upload className="h-3.5 w-3.5" /> {own ? 'Replace mine' : 'Use mine'}
          </Button>
          {own && (
            <Button variant="ghost" size="sm" onClick={removeOwn} disabled={!!busy} aria-label="Remove your media">
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
        {media.dialog}
      </div>
    </article>
  );
}

export function StoryboardStep({ project, runs }: { project: FacelessProject; runs: StepRun[] }) {
  const { config, setProject } = useFacelessStore();
  const { getModelCost } = usePricingStore();
  const gate = usePaidGate(project, 'storyboard');
  const { request, dialog } = usePaidStep(project.id);
  const [error, setError] = useState<string | null>(null);
  const models = config?.models;
  const t2i = project.settings.t2i_model ?? models?.default_t2i ?? '';
  const edit = project.settings.edit_model ?? models?.default_edit ?? '';
  const res: StillResolution = project.settings.still_resolution ?? '1k';
  const scenes = project.script?.scenes ?? [];
  const needing = storyboardScenes(scenes).filter((s) => !hasStill(assetsOf(project, s.id)));

  const saveSetting = async (patch: Partial<FacelessProject['settings']>) => {
    setError(null);
    try {
      setProject(await facelessApi.updateProject(project.id, { settings: { ...patch } }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the model choice'));
    }
  };

  const qa = useQualityConfig();
  const [checkStills, setCheckStills] = useState(true);
  const options = { t2i_model: t2i, edit_model: edit, resolution: res, quality_check: checkStills };
  const t2iPrice = getModelCost(imageKey(t2i, res));
  const editPrice = getModelCost(editKey(edit, res));

  if (scenes.length === 0) {
    return <EmptyState icon={LayoutGrid} title="Script first">Draft and save a script, then the storyboard lays out one picture per scene.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <div className="panel flex flex-col gap-4 rounded-xl p-4 lg:flex-row lg:items-end">
        <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <Kicker className="mb-1.5">Scenes with cast</Kicker>
            <Select value={edit} onValueChange={(v) => saveSetting({ edit_model: v })} disabled={!models}>
              <SelectTrigger aria-label="Model for scenes with characters">
                <SelectValue placeholder="Edit model" />
              </SelectTrigger>
              <SelectContent>
                {(models?.edit ?? []).map((m) => (
                  <SelectItem key={m} value={m}>
                    {getModelDisplayName(m)}
                    <span className="ml-2 font-mono text-[11px] tabular text-muted-foreground">
                      {getModelCost(editKey(m, res)) !== undefined ? formatUsd(getModelCost(editKey(m, res))!) : ''}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Kicker className="mb-1.5">Scenes without cast</Kicker>
            <Select value={t2i} onValueChange={(v) => saveSetting({ t2i_model: v })} disabled={!models}>
              <SelectTrigger aria-label="Model for scenes without characters">
                <SelectValue placeholder="Text to image model" />
              </SelectTrigger>
              <SelectContent>
                {(models?.t2i ?? []).map((m) => (
                  <SelectItem key={m} value={m}>
                    {getModelDisplayName(m)}
                    <span className="ml-2 font-mono text-[11px] tabular text-muted-foreground">
                      {getModelCost(imageKey(m, res)) !== undefined ? formatUsd(getModelCost(imageKey(m, res))!) : ''}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Kicker className="mb-1.5">Resolution</Kicker>
            <Select value={res} onValueChange={(v) => saveSetting({ still_resolution: v as StillResolution })}>
              <SelectTrigger aria-label="Still resolution">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(models?.still_resolutions ?? ['1k', '2k']).map((r) => (
                  <SelectItem key={r} value={r}>
                    {r.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex flex-col items-start gap-1 lg:items-end">
          <p className="font-mono text-[11px] tabular text-muted-foreground">
            {editPrice !== undefined && `${formatUsd(editPrice)} with cast`}
            {editPrice !== undefined && t2iPrice !== undefined && ', '}
            {t2iPrice !== undefined && `${formatUsd(t2iPrice)} without`}
            {' per still'}
          </p>
          {qa?.available && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch checked={checkStills} onCheckedChange={setCheckStills} aria-label="Check each still" />
              Check each still
              <span className="font-mono text-[11px] tabular">+{formatUsd(qa.estimated_usd)}</span>
            </label>
          )}
          <Button
            disabled={!!gate || needing.length === 0}
            title={gate ?? undefined}
            onClick={() =>
              request({
                step: 'storyboard',
                options,
                title: 'Generate the storyboard',
                description: `Stills for ${needing.length} scene${needing.length === 1 ? '' : 's'} that have none yet.`,
              })
            }
          >
            <ImagePlus className="h-4 w-4" />
            {needing.length === 0 ? 'Storyboard complete' : `Generate ${needing.length} missing`}
          </Button>
        </div>
      </div>
      {gate && gate !== 'Already running' && <p className="text-xs text-muted-foreground">{gate}.</p>}
      <ErrorNote>{error}</ErrorNote>

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Storyboard">
        {scenes.map((scene, i) => (
          <li key={scene.id}>
            <SceneCard
              project={project}
              scene={scene}
              position={i}
              runs={runs}
              gate={gate}
              onRegenerate={(s) =>
                request({
                  step: 'storyboard',
                  sceneIds: [s.id],
                  options,
                  title: `${hasStill(assetsOf(project, s.id)) ? 'Regenerate' : 'Generate'} scene ${i + 1}`,
                  description: `New still${s.shot.images > 1 ? 's' : ''} for "${s.beat_name || s.beat}".`,
                })
              }
            />
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Still scenes get a slow Ken Burns move in the render. Animate scenes become H3 Max clips in the next step. Cards need no picture.
      </p>
      {dialog}
    </div>
  );
}
