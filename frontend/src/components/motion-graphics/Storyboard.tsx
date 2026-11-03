import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Loader2, Mic, Play, Plus, ShieldCheck, Square, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { motionGraphicsApi } from '@/api/motionGraphics';
import type { MGAspect, MGSpec, MGTemplate, PlanScene, SceneTypeDef, SpecScene, ValidationIssue } from '@/api/motionGraphics';
import { friendlyError, getErrorMessage } from '@/utils/errors';
import { ASPECT_RATIO_CLASS, AspectGlyph, ErrorNote, PillGroup, formatSeconds, usePreview } from './shared';

export function sceneDef(tpl: MGTemplate, type: string): SceneTypeDef | undefined {
  return tpl.scene_types.find((s) => s.type === type) ?? tpl.shared_scene_types.find((s) => s.type === type);
}

// A silent animated preview of the selected scene or the video's opening,
// dropped as soon as the spec, scene or aspect changes (never shown stale).
function useMotionPreview(projectId: number, spec: MGSpec, sceneId: string | null, aspect: MGAspect) {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const key = JSON.stringify([spec, sceneId, aspect]);

  const stop = () => {
    seq.current += 1;
    setBusy(false);
    setUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
  };

  useEffect(() => {
    stop();
    setError(null);
  }, [key]);

  useEffect(() => () => stop(), []);

  const play = async (what: 'scene' | 'video') => {
    stop();
    const mine = seq.current;
    setBusy(true);
    setError(null);
    try {
      const blob = await motionGraphicsApi.motionPreview(projectId, {
        scene_id: what === 'scene' ? sceneId : null,
        aspect,
        spec,
      });
      if (mine !== seq.current) return;
      setUrl(URL.createObjectURL(blob));
    } catch (err) {
      if (mine === seq.current) setError(getErrorMessage(err, 'Motion preview failed'));
    } finally {
      if (mine === seq.current) setBusy(false);
    }
  };

  return { url, busy, error, play, stop };
}

// One small still per scene, refreshed when that scene (or the look) changes.
function SceneThumb({
  projectId,
  spec,
  scene,
  aspect,
  look,
}: {
  projectId: number;
  spec: MGSpec;
  scene: SpecScene;
  aspect: MGAspect;
  look: string;
}) {
  const key = JSON.stringify(scene) + look;
  const { url, loading } = usePreview(projectId, { scene_id: scene.id, aspect, scale: 0.25, spec }, [key, aspect], 600);
  return (
    <div className={cn('relative w-14 shrink-0 overflow-hidden rounded-md border border-border bg-secondary/40', ASPECT_RATIO_CLASS[aspect])}>
      {url && <img src={url} alt="" className="h-full w-full object-cover" draggable={false} />}
      {loading && !url && <div className="shimmer absolute inset-0" />}
    </div>
  );
}

export function SceneRail({
  projectId,
  spec,
  tpl,
  plan,
  aspect,
  selected,
  onSelect,
  onSpec,
  issues,
}: {
  projectId: number;
  spec: MGSpec;
  tpl: MGTemplate;
  plan: PlanScene[];
  aspect: MGAspect;
  selected: string | null;
  onSelect: (id: string) => void;
  onSpec: (fn: (s: MGSpec) => MGSpec) => void;
  issues: ValidationIssue[];
}) {
  const look = useMemo(
    () => JSON.stringify([spec.style_id, spec.options, spec.data, spec.source, spec.disclaimer, spec.data_options]),
    [spec.style_id, spec.options, spec.data, spec.source, spec.disclaimer, spec.data_options],
  );
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    spec.scenes.forEach((s) => m.set(s.type, (m.get(s.type) ?? 0) + 1));
    return m;
  }, [spec.scenes]);
  const addable = [...tpl.scene_types, ...tpl.shared_scene_types.filter((s) => s.type === 'end_card' || s.type === 'logo_sting')]
    .filter((d) => (counts.get(d.type) ?? 0) < d.max_count);

  const move = (i: number, d: -1 | 1) =>
    onSpec((s) => {
      const j = i + d;
      if (j < 0 || j >= s.scenes.length) return s;
      const scenes = [...s.scenes];
      [scenes[i], scenes[j]] = [scenes[j], scenes[i]];
      return { ...s, scenes };
    });

  const add = (def: SceneTypeDef) => {
    const id = Math.random().toString(36).slice(2, 10);
    onSpec((s) => {
      const scenes = [...s.scenes];
      // keep compliance and end cards last
      const tail = scenes.findIndex((x) => ['source_card', 'disclaimer', 'end_card'].includes(x.type));
      const at = def.type === 'end_card' || tail < 0 ? scenes.length : tail;
      scenes.splice(def.type === 'end_card' ? scenes.length : at, 0, {
        id,
        type: def.type,
        slots: {},
        duration: null,
        voiceover: null,
      });
      return { ...s, scenes };
    });
    onSelect(id);
  };

  return (
    <div className="space-y-2">
      {spec.scenes.map((sc, i) => {
        const def = sceneDef(tpl, sc.type);
        const p = plan.find((x) => x.id === sc.id);
        const bad = issues.some((x) => x.scene_id === sc.id);
        const removable =
          !!def && def.removable && !['source_card', 'disclaimer'].includes(sc.type) && (counts.get(sc.type) ?? 0) > def.min_count;
        return (
          <div
            key={sc.id}
            className={cn(
              'group flex items-center gap-2 rounded-lg border p-1.5 transition-colors',
              selected === sc.id ? 'border-primary/60 bg-primary/10' : 'border-border bg-card hover:border-foreground/20',
            )}
          >
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => onSelect(sc.id)}>
              <SceneThumb projectId={projectId} spec={spec} scene={sc} aspect={aspect} look={look} />
              <div className="min-w-0 space-y-0.5">
                <p className="truncate text-xs font-medium">
                  <span className="mr-1 font-mono text-[10px] text-muted-foreground">{i + 1}</span>
                  {def?.label ?? sc.type}
                </p>
                <p className="truncate text-[11px] text-muted-foreground">
                  {String(sc.slots.text ?? sc.slots.title ?? sc.slots.headline ?? sc.slots.label ?? sc.slots.date ?? '') ||
                    (sc.type === 'source_card' ? spec.source ?? '' : '')}
                </p>
                <div className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
                  {p && <span>{p.duration.toFixed(1)} s</span>}
                  {p?.voiced && <Mic className="h-3 w-3" aria-label="Voiced" />}
                  {['source_card', 'disclaimer'].includes(sc.type) && <ShieldCheck className="h-3 w-3 text-success" />}
                  {bad && <span className="h-1.5 w-1.5 rounded-full bg-destructive" />}
                </div>
              </div>
            </button>
            <div className="flex flex-col opacity-60 transition-opacity group-hover:opacity-100">
              <button type="button" className="p-0.5 hover:text-foreground" onClick={() => move(i, -1)} aria-label="Move up">
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button type="button" className="p-0.5 hover:text-foreground" onClick={() => move(i, 1)} aria-label="Move down">
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              {removable && (
                <button
                  type="button"
                  className="p-0.5 hover:text-destructive"
                  onClick={() => onSpec((s) => ({ ...s, scenes: s.scenes.filter((x) => x.id !== sc.id) }))}
                  aria-label="Delete scene"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        );
      })}
      {addable.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="w-full">
              <Plus className="h-4 w-4" /> Add scene
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {addable.map((d) => (
              <DropdownMenuItem key={d.type} onClick={() => add(d)}>
                {d.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

export function PreviewStage({
  projectId,
  spec,
  scene,
  planScene,
  aspects,
  aspect,
  onAspect,
}: {
  projectId: number;
  spec: MGSpec;
  scene: SpecScene | null;
  planScene?: PlanScene;
  aspects: MGAspect[];
  aspect: MGAspect;
  onAspect: (a: MGAspect) => void;
}) {
  const [safe, setSafe] = useState(false);
  const [at, setAt] = useState<number | null>(null);
  const dur = planScene?.duration ?? 3;
  const key = JSON.stringify([spec, scene?.id, aspect, safe, at]);
  const { url, loading, error } = usePreview(
    projectId,
    scene ? { scene_id: scene.id, aspect, scale: 0.5, safe_zone_overlay: safe, spec, at } : null,
    [key],
    300,
  );
  const motion = useMotionPreview(projectId, spec, scene?.id ?? null, aspect);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PillGroup
          size="xs"
          value={aspect}
          onChange={onAspect}
          options={aspects.map((a) => ({
            id: a,
            label: (
              <span className="flex items-center gap-1.5">
                <AspectGlyph aspect={a} /> {a}
              </span>
            ),
          }))}
        />
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={safe} onCheckedChange={setSafe} /> Safe zones
        </label>
      </div>
      <div className="flex justify-center rounded-xl border border-border bg-secondary/20 p-3">
        <div
          className={cn(
            'relative overflow-hidden rounded-lg border border-border bg-background shadow-card',
            ASPECT_RATIO_CLASS[aspect],
            aspect === '16:9' ? 'w-full' : aspect === '1:1' ? 'w-full max-w-[520px]' : 'w-full max-w-[380px]',
          )}
        >
          {motion.url ? (
            <img src={motion.url} alt="Motion preview" className="h-full w-full object-contain" draggable={false} />
          ) : (
            url && <img src={url} alt="Scene preview" className="h-full w-full object-contain" draggable={false} />
          )}
          {!url && !motion.url && <div className="shimmer absolute inset-0" />}
          {(loading || motion.busy) && (
            <div className="absolute right-2 top-2 rounded-full bg-background/70 p-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-label="Updating preview" />
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="w-12 font-mono text-[10px] text-muted-foreground">{at === null ? 'settled' : `${at.toFixed(1)} s`}</span>
        <Slider
          value={[at ?? dur * 0.78]}
          min={0}
          max={Math.max(0.5, dur)}
          step={0.05}
          onValueChange={(v) => setAt(v[0])}
          className="flex-1"
          aria-label="Time in scene"
        />
        <Button variant="ghost" size="sm" onClick={() => setAt(null)} disabled={at === null}>
          Reset
        </Button>
        <span className="font-mono text-[10px] text-muted-foreground">{formatSeconds(dur)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {motion.url ? (
          <Button variant="outline" size="sm" onClick={motion.stop}>
            <Square className="mr-1.5 h-3.5 w-3.5" /> Back to still
          </Button>
        ) : (
          <>
            <Button variant="outline" size="sm" onClick={() => motion.play('scene')} disabled={!scene || motion.busy}>
              <Play className="mr-1.5 h-3.5 w-3.5" /> Play scene
            </Button>
            <Button variant="ghost" size="sm" onClick={() => motion.play('video')} disabled={motion.busy}>
              <Play className="mr-1.5 h-3.5 w-3.5" /> Play video
            </Button>
          </>
        )}
        <span className="text-xs text-muted-foreground">
          Silent, low resolution, no provider cost. The render adds voice, music and full quality.
        </span>
      </div>
      {(error || motion.error) && <ErrorNote>{friendlyError(error || motion.error)}</ErrorNote>}
    </div>
  );
}
