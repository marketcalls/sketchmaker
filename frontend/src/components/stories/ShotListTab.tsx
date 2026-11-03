import { useState } from 'react';
import { Check, ChevronDown, ImagePlus, Loader2, Plus, RefreshCw, Trash2, Wand2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { assetsApi } from '@/api/assets';
import { keyframeJobKey, useStoryRoomStore, type KeyframeJob } from '@/stores/storyRoomStore';
import { formatUsd, usePricingStore } from '@/stores/pricingStore';
import {
  SHOT_CAMERAS, SHOT_SECONDS_MAX, SHOT_SECONDS_MIN, SHOT_TRANSITIONS, SHOT_TYPES,
  enumLabel, formatRuntime, keyframeBlock, newShot, storyRuntime,
  type DocScene, type Shot, type StoryDoc,
} from '@/api/storyRoom';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { Chip, EditableText, FieldLabel, InlineSelect } from './fields';

const NO_JOB: KeyframeJob = { generating: false, error: null, notice: null };

const ASPECT_CLASS: Record<string, string> = { '9:16': 'aspect-[9/16] w-24', '16:9': 'aspect-video w-44', '1:1': 'aspect-square w-32' };

/** The "Make keyframe" request of one shot in the open thread. */
function useKeyframeJob(shotId: string): KeyframeJob {
  return useStoryRoomStore((s) => (s.thread ? s.keyframeJobs[keyframeJobKey(s.thread.id, shotId)] : undefined)) ?? NO_JOB;
}

/** USD for one keyframe. */
function useKeyframePrice(): number | undefined {
  const keyframePrice = useStoryRoomStore((s) => s.keyframePrice);
  useStoryRoomStore((s) => s.config);
  usePricingStore((s) => s.costs);
  return keyframePrice();
}

/**
 * The shot's optional first frame: made from the approved cast, place and
 * product images ("Make keyframe", then approved by the user), or an
 * uploaded still or a My Assets image. Clips of the shot open on an approved
 * keyframe (image-to-video).
 */
function ShotKeyframe({ shot, scene, story, disabled }: { shot: Shot; scene: DocScene; story: StoryDoc; disabled: boolean }) {
  const { approveKeyframe, clearKeyframe, generateKeyframe } = useStoryRoomStore();
  const job = useKeyframeJob(shot.id);
  const price = useKeyframePrice();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const approved = shot.keyframe_approved && !!shot.keyframe_url;
  // Made by "Make keyframe" and waiting for the user's approval.
  const made = !approved && !!shot.keyframe_url;
  const blocked = keyframeBlock(story, scene, shot);
  const frame = ASPECT_CLASS[story.aspect] ?? ASPECT_CLASS['9:16'];
  const working = busy || job.generating;

  const run = async (fn: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(getErrorMessage(err, fallback));
      throw err;
    } finally {
      setBusy(false);
    }
  };

  const media = useMediaPicker({
    kinds: ['image'],
    title: `First frame of shot ${shot.id}`,
    description: 'A still at the shot\'s aspect with the cast and place as they should appear. The clip opens on it.',
    disabled: disabled || working,
    saveUploads: false,
    onAssets: (assets) => run(() => approveKeyframe(shot.id, { assetId: assets[0].id }), 'That image could not be used.'),
    onFiles: (files) =>
      run(async () => {
        const asset = await assetsApi.upload(files[0]);
        await approveKeyframe(shot.id, { assetId: asset.id });
      }, 'That image could not be used.'),
  });

  const makeButton = (label: string) => (
    <Button
      type="button"
      size="sm"
      variant={made ? 'outline' : 'default'}
      disabled={disabled || working || !!blocked}
      onClick={() => generateKeyframe(shot.id)}
      title={blocked ?? `One still at ${story.aspect} from the approved images`}
    >
      {job.generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : made ? <RefreshCw className="h-3.5 w-3.5" /> : <Wand2 className="h-3.5 w-3.5" />}
      {label}
      {price !== undefined && <span className="font-mono text-xs opacity-75">{formatUsd(price)}</span>}
    </Button>
  );

  return (
    <div className="px-2" {...media.dropProps}>
      <FieldLabel>Keyframe (optional first frame)</FieldLabel>
      {job.generating ? (
        <div className="flex items-center gap-3">
          <div className={cn('shimmer shrink-0 rounded-md border border-border bg-muted', frame)} />
          <p className="min-w-0 text-xs text-muted-foreground">
            Making the keyframe from the approved cast, place and product images. This takes up to a minute.
          </p>
        </div>
      ) : approved ? (
        <div className="flex items-center gap-2">
          <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-md border-2 border-primary/60 bg-muted">
            <img src={shot.keyframe_url} alt="" className="h-full w-full object-cover" />
            <Check className="absolute left-0.5 top-0.5 h-3.5 w-3.5 rounded-full bg-background/85 p-0.5 text-success" aria-label="Approved" />
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={disabled || working}
            onClick={() => run(() => clearKeyframe(shot.id), 'The keyframe could not be removed.').catch(() => {})}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />} Remove
          </Button>
          <p className="min-w-0 text-xs text-muted-foreground">The clip of this shot opens on this frame.</p>
        </div>
      ) : made ? (
        <div className="flex gap-3">
          <a href={shot.keyframe_url} target="_blank" rel="noreferrer" className={cn('block shrink-0 overflow-hidden rounded-md border border-border bg-muted', frame)}>
            <img src={shot.keyframe_url} alt={`Keyframe of shot ${shot.id}`} className="h-full w-full object-cover" />
          </a>
          <div className="flex min-w-0 flex-col justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              Check faces, wardrobe, place and product against the approved images, then approve it. The clip opens on an approved keyframe.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={disabled || working}
                onClick={() => run(() => approveKeyframe(shot.id, { made: true }), 'The keyframe could not be approved.').catch(() => {})}
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Approve
              </Button>
              {makeButton('Make another')}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={disabled || working}
                onClick={() => run(() => clearKeyframe(shot.id), 'The keyframe could not be removed.').catch(() => {})}
                className="text-muted-foreground hover:text-destructive"
              >
                <X className="h-3.5 w-3.5" /> Discard
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">Saved in My Assets.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            {makeButton('Make keyframe')}
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled || working}
              onClick={media.open}
              className={cn(media.dragOver && 'border-foreground/40 bg-accent/40')}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />} Add keyframe
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {blocked ?? 'Make a still from the approved images, or upload or pick one. The clip opens on it once approved.'}
          </p>
        </div>
      )}
      {job.notice && <p className="mt-1 text-xs text-warning">{job.notice}</p>}
      {(job.error || error) && <p className="mt-1 text-xs text-destructive">{job.error || error}</p>}
      {media.dialog}
    </div>
  );
}

/**
 * "Make keyframes" for a scene: every shot without a keyframe that can have
 * one, one request after another, after the total is confirmed.
 */
function SceneKeyframes({ scene, story, disabled }: { scene: DocScene; story: StoryDoc; disabled: boolean }) {
  const generateKeyframe = useStoryRoomStore((s) => s.generateKeyframe);
  const jobs = useStoryRoomStore((s) => s.keyframeJobs);
  const threadId = useStoryRoomStore((s) => s.thread?.id);
  const [confirming, setConfirming] = useState(false);
  const [running, setRunning] = useState(false);
  const ready = scene.shots.filter((sh) => !sh.keyframe_url && !keyframeBlock(story, scene, sh));
  const price = useKeyframePrice();
  const anyRunning = threadId !== undefined && scene.shots.some((sh) => jobs[keyframeJobKey(threadId, sh.id)]?.generating);
  if (ready.length < 2 || price === undefined) return null;
  const total = price * ready.length;

  const runAll = async () => {
    setRunning(true);
    try {
      for (const sh of ready) {
        if (!(await generateKeyframe(sh.id))) break;
      }
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <button
        type="button"
        disabled={disabled || running || anyRunning}
        onClick={() => setConfirming(true)}
        className="flex shrink-0 items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground disabled:opacity-50"
      >
        {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3" />}
        Keyframes <span className="tabular">{ready.length}</span> <span className="font-mono tabular opacity-75">{formatUsd(total)}</span>
      </button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Make ${ready.length} keyframes?`}
        description={`${ready.length} shots in this scene have no keyframe yet. Each is made from the approved images at ${formatUsd(price)}, ${formatUsd(total)} in all. They are made one after another, and you approve each one.`}
        confirmText={`Make ${ready.length} for ${formatUsd(total)}`}
        onConfirm={() => {
          setConfirming(false);
          void runAll();
        }}
      />
    </>
  );
}

// Next free shot id in a scene ("s2.4"); the server re-keys if it disagrees.
function nextShotId(scene: DocScene): string {
  const used = new Set(scene.shots.map((s) => s.id));
  let n = scene.shots.length + 1;
  while (used.has(`${scene.id}.${n}`)) n += 1;
  return `${scene.id}.${n}`;
}

function ShotSummary({ shot, story }: { shot: Shot; story: StoryDoc }) {
  const name = (key: string) => story.characters.find((c) => c.key === key)?.name || key;
  const productName = (key: string) => (story.products ?? []).find((p) => p.key === key)?.name || key;
  const props = shot.props ?? [];
  const job = useKeyframeJob(shot.id);
  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1 font-mono text-[11px] tabular text-muted-foreground">{shot.id}</span>
        <Chip>{enumLabel(shot.type)}</Chip>
        <Chip>{enumLabel(shot.camera)}</Chip>
        {shot.transition_in !== 'cut' && <Chip>{enumLabel(shot.transition_in)}</Chip>}
        {shot.b_roll && <Chip accent>B-roll</Chip>}
        {props.map((k) => <Chip key={k}>{productName(k)}</Chip>)}
        {shot.keyframe_approved && shot.keyframe_url && <Chip accent>Keyframe</Chip>}
        {job.generating ? <Chip>Making keyframe</Chip> : !shot.keyframe_approved && shot.keyframe_url && <Chip>Keyframe to approve</Chip>}
        <Chip className="ml-auto">{formatRuntime(shot.duration_seconds)}</Chip>
      </div>
      {shot.action && <p className="text-sm leading-relaxed text-foreground/90">{shot.action}</p>}
      {(shot.frame_position || shot.end_state) && (
        <p className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
          {shot.frame_position && <span>Frame: {shot.frame_position}</span>}
          {shot.end_state && <span>Ends: {shot.end_state}</span>}
        </p>
      )}
      {shot.dialogue.length > 0 && (
        <div className="space-y-0.5 border-l border-border pl-3">
          {shot.dialogue.map((d, i) => (
            <p key={i} className="text-sm">
              <span className="font-mono text-[11px] uppercase text-foreground">{name(d.character_key)}</span>
              {d.delivery && <span className="text-xs italic text-muted-foreground"> ({d.delivery})</span>}
              <span className="text-foreground/90">: {d.line}</span>
            </p>
          ))}
        </div>
      )}
      {shot.voiceover && (
        <p className="text-sm text-foreground/90">
          <span className="text-[11px] font-medium text-muted-foreground">Voiceover: </span>
          {shot.voiceover}
        </p>
      )}
      {(shot.on_screen_text || shot.sound) && (
        <p className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
          {shot.on_screen_text && <span>Text: {shot.on_screen_text}</span>}
          {shot.sound && <span>Sound: {shot.sound}</span>}
        </p>
      )}
    </div>
  );
}

function ShotEditor({
  shot, scene, story, disabled, onChange, onDelete,
}: {
  shot: Shot;
  scene: DocScene;
  story: StoryDoc;
  disabled: boolean;
  onChange: (patch: Partial<Shot>) => void;
  onDelete: () => void;
}) {
  const config = useStoryRoomStore((s) => s.config);
  const types = config?.enums.shotTypes ?? SHOT_TYPES;
  const cameras = config?.enums.cameras ?? SHOT_CAMERAS;
  const transitions = config?.enums.transitions ?? SHOT_TRANSITIONS;
  const [seconds, setSeconds] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const commitSeconds = () => {
    if (seconds === null) return;
    const n = Number(seconds);
    setSeconds(null);
    if (!Number.isFinite(n)) return;
    const v = Math.round(Math.min(SHOT_SECONDS_MAX, Math.max(SHOT_SECONDS_MIN, n)) * 10) / 10;
    if (v !== shot.duration_seconds) onChange({ duration_seconds: v });
  };

  return (
    <div className="space-y-2 pt-1">
      <div className="grid grid-cols-2 gap-2 px-2 sm:grid-cols-4">
        <InlineSelect label="Shot" value={shot.type} options={types} render={enumLabel} disabled={disabled} onChange={(type) => onChange({ type })} />
        <InlineSelect label="Camera" value={shot.camera} options={cameras} render={enumLabel} disabled={disabled} onChange={(camera) => onChange({ camera })} />
        <InlineSelect label="Transition in" value={shot.transition_in} options={transitions} render={enumLabel} disabled={disabled} onChange={(transition_in) => onChange({ transition_in })} />
        <label className="block min-w-0">
          <FieldLabel>Seconds</FieldLabel>
          <input
            type="number"
            inputMode="decimal"
            step={0.5}
            min={SHOT_SECONDS_MIN}
            max={SHOT_SECONDS_MAX}
            value={seconds ?? String(shot.duration_seconds)}
            disabled={disabled}
            onChange={(e) => setSeconds(e.target.value)}
            onBlur={commitSeconds}
            onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
            className="h-8 w-full rounded-md border border-input bg-secondary/40 px-2 font-mono text-xs tabular text-foreground focus-visible:border-ring focus-visible:outline-none disabled:opacity-60"
          />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-2">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={shot.b_roll} disabled={disabled} onCheckedChange={(b_roll) => onChange({ b_roll })} />
          B-roll
        </label>
        {story.characters.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs font-medium text-muted-foreground">In frame</span>
            {story.characters.map((c) => {
              const on = shot.characters.includes(c.key);
              return (
                <button
                  key={c.key}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange({ characters: on ? shot.characters.filter((k) => k !== c.key) : [...shot.characters, c.key] })}
                  className={cn(
                    'rounded border px-1.5 py-px text-[11px] transition-colors',
                    on ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-muted-foreground hover:text-foreground',
                  )}
                >
                  {c.name || c.key}
                </button>
              );
            })}
          </div>
        )}
        {(story.products ?? []).length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs font-medium text-muted-foreground">Products</span>
            {(story.products ?? []).map((p) => {
              const props = shot.props ?? [];
              const on = props.includes(p.key);
              return (
                <button
                  key={p.key}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange({ props: on ? props.filter((k) => k !== p.key) : [...props, p.key] })}
                  className={cn(
                    'rounded border px-1.5 py-px text-[11px] transition-colors',
                    on ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-muted-foreground hover:text-foreground',
                  )}
                >
                  {p.name || p.key}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <EditableText label="Action" multiline value={shot.action} disabled={disabled} onCommit={(action) => onChange({ action })} />
      <div className="grid grid-cols-1 gap-x-2 sm:grid-cols-2">
        <EditableText
          label="Frame position"
          multiline
          rows={1}
          value={shot.frame_position ?? ''}
          placeholder="Mira left facing right, Dev right"
          disabled={disabled}
          onCommit={(frame_position) => onChange({ frame_position })}
        />
        <EditableText
          label="Ends on"
          multiline
          rows={1}
          value={shot.end_state ?? ''}
          placeholder="The pose the next shot begins from"
          disabled={disabled}
          onCommit={(end_state) => onChange({ end_state })}
        />
      </div>

      <div className="px-2">
        <FieldLabel>Dialogue</FieldLabel>
        <div className="space-y-1.5">
          {shot.dialogue.map((d, i) => {
            const setLine = (patch: Partial<typeof d>) =>
              onChange({ dialogue: shot.dialogue.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
            return (
              <div key={i} className="rounded-md border border-border bg-secondary/20 p-1.5">
                <div className="flex items-center gap-1.5">
                  <select
                    value={d.character_key}
                    disabled={disabled}
                    onChange={(e) => setLine({ character_key: e.target.value })}
                    aria-label="Speaker"
                    className="h-7 min-w-0 flex-1 rounded border border-input bg-secondary/40 px-1.5 text-xs text-foreground focus-visible:border-ring focus-visible:outline-none"
                  >
                    {!story.characters.some((c) => c.key === d.character_key) && <option value={d.character_key}>{d.character_key || 'Speaker'}</option>}
                    {story.characters.map((c) => <option key={c.key} value={c.key} className="bg-popover">{c.name || c.key}</option>)}
                  </select>
                  <button
                    type="button"
                    disabled={disabled}
                    aria-label="Remove line"
                    onClick={() => onChange({ dialogue: shot.dialogue.filter((_, j) => j !== i) })}
                    className="rounded p-1 text-muted-foreground hover:text-destructive"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                <EditableText value={d.delivery} placeholder="Delivery, for example quietly, amused" disabled={disabled} onCommit={(delivery) => setLine({ delivery })} className="text-xs italic" />
                <EditableText value={d.line} placeholder="Line" multiline rows={1} disabled={disabled} onCommit={(line) => setLine({ line })} />
              </div>
            );
          })}
          <button
            type="button"
            disabled={disabled}
            onClick={() =>
              onChange({ dialogue: [...shot.dialogue, { character_key: shot.characters[0] ?? story.characters[0]?.key ?? '', line: '', delivery: '' }] })
            }
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <Plus className="h-3 w-3" /> Add line
          </button>
        </div>
      </div>

      <EditableText label="Voiceover" multiline rows={1} value={shot.voiceover} disabled={disabled} onCommit={(voiceover) => onChange({ voiceover })} />
      <div className="grid grid-cols-2 gap-x-2">
        <EditableText label="On-screen text" value={shot.on_screen_text} disabled={disabled} onCommit={(on_screen_text) => onChange({ on_screen_text })} />
        <EditableText label="Sound" value={shot.sound} disabled={disabled} onCommit={(sound) => onChange({ sound })} />
      </div>
      <ShotKeyframe shot={shot} scene={scene} story={story} disabled={disabled} />
      <div className="flex justify-end px-2">
        <Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => setConfirmDelete(true)} className="text-muted-foreground hover:text-destructive">
          <Trash2 className="h-3.5 w-3.5" /> Delete shot
        </Button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete shot ${shot.id}?`}
        description="The shot, its dialogue and its keyframe are removed from the shot list."
        confirmText="Delete"
        variant="destructive"
        onConfirm={onDelete}
      />
    </div>
  );
}

/** Shot list: scenes as screenplay headings, shots as dense rows that open for editing. */
export function ShotListTab({ story, disabled }: { story: StoryDoc; disabled: boolean }) {
  const editStory = useStoryRoomStore((s) => s.editStory);
  const maxShots = useStoryRoomStore((s) => s.config?.limits.maxShots ?? 12);
  const [open, setOpen] = useState<string | null>(null);
  const runtime = storyRuntime(story);
  const target = story.target_seconds;
  const off = target > 0 ? Math.abs(runtime - target) / target : 0;

  const editScene = (sceneId: string, mutate: (s: DocScene) => DocScene) =>
    editStory((d) => ({ ...d, scenes: d.scenes.map((s) => (s.id === sceneId ? mutate(s) : s)) }));
  const editShot = (sceneId: string, shotId: string, patch: Partial<Shot>) =>
    editScene(sceneId, (s) => ({ ...s, shots: s.shots.map((sh) => (sh.id === shotId ? { ...sh, ...patch } : sh)) }));

  if (story.scenes.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        The shot list appears after the director's first reply.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {/* Runtime against the target */}
      <div className="rounded-lg border border-border bg-secondary/20 p-3">
        <div className="flex items-baseline justify-between text-xs">
          <span className="text-muted-foreground">Runtime</span>
          <span className={cn('font-mono tabular', off > 0.1 ? 'text-warning' : 'text-foreground')}>
            {formatRuntime(runtime)} <span className="text-muted-foreground">of {formatRuntime(target)} target</span>
          </span>
        </div>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-secondary">
          <div
            className={cn('h-full rounded-full transition-[width] duration-300', off > 0.1 ? 'bg-warning' : 'bg-primary')}
            style={{ width: `${Math.min(100, target > 0 ? (runtime / target) * 100 : 0)}%` }}
          />
        </div>
      </div>

      {story.scenes.map((scene, si) => {
        const sceneSeconds = scene.shots.reduce((s, sh) => s + (Number(sh.duration_seconds) || 0), 0);
        return (
          <section key={scene.id}>
            <div className="mb-2 flex items-baseline gap-2">
              <span className="font-mono text-[11px] tabular text-muted-foreground">{si + 1}</span>
              <EditableText
                value={scene.heading}
                placeholder="INT. LOCATION - DAY"
                disabled={disabled}
                onCommit={(heading) => editScene(scene.id, (s) => ({ ...s, heading: heading.toUpperCase() }))}
                className="font-mono text-sm font-semibold uppercase"
              />
              <SceneKeyframes scene={scene} story={story} disabled={disabled} />
              <span className="shrink-0 font-mono text-[11px] tabular text-muted-foreground">{formatRuntime(sceneSeconds)}</span>
            </div>
            <div className="mb-2 grid grid-cols-[1fr_auto] items-start gap-2">
              <EditableText
                value={scene.summary}
                placeholder="What happens in this scene"
                multiline
                rows={1}
                disabled={disabled}
                onCommit={(summary) => editScene(scene.id, (s) => ({ ...s, summary }))}
                className="text-sm text-muted-foreground"
              />
              <div className="flex items-center gap-1.5 pt-1">
                {scene.purpose && <Chip accent>{scene.purpose}</Chip>}
                {story.environments.length > 0 && (
                  <select
                    value={scene.environment_key ?? ''}
                    disabled={disabled}
                    aria-label="Environment"
                    onChange={(e) => editScene(scene.id, (s) => ({ ...s, environment_key: e.target.value || null }))}
                    className="h-6 max-w-[120px] rounded border border-input bg-secondary/40 px-1 text-[11px] text-muted-foreground focus-visible:border-ring focus-visible:outline-none"
                  >
                    <option value="">No environment</option>
                    {story.environments.map((e) => <option key={e.key} value={e.key} className="bg-popover">{e.name || e.key}</option>)}
                  </select>
                )}
              </div>
            </div>

            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
              {scene.shots.map((shot) => {
                const isOpen = open === shot.id;
                return (
                  <div key={shot.id} className={cn('p-2.5 transition-colors', isOpen ? 'bg-secondary/30' : 'hover:bg-accent/30')}>
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <ShotSummary shot={shot} story={story} />
                      </div>
                      <button
                        type="button"
                        aria-label={isOpen ? 'Close shot' : 'Edit shot'}
                        aria-expanded={isOpen}
                        onClick={() => setOpen(isOpen ? null : shot.id)}
                        className="mt-0.5 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <ChevronDown className={cn('h-4 w-4 transition-transform duration-200', isOpen && 'rotate-180')} />
                      </button>
                    </div>
                    {isOpen && (
                      <ShotEditor
                        shot={shot}
                        scene={scene}
                        story={story}
                        disabled={disabled}
                        onChange={(patch) => editShot(scene.id, shot.id, patch)}
                        onDelete={() => {
                          setOpen(null);
                          editScene(scene.id, (s) => ({ ...s, shots: s.shots.filter((x) => x.id !== shot.id) }));
                        }}
                      />
                    )}
                  </div>
                );
              })}
              {scene.shots.length < maxShots && (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    const shot = newShot(nextShotId(scene));
                    editScene(scene.id, (s) => ({ ...s, shots: [...s.shots, shot] }));
                    setOpen(shot.id);
                  }}
                  className="flex w-full items-center gap-1 px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent/30 hover:text-foreground disabled:opacity-50"
                >
                  <Plus className="h-3 w-3" /> Add shot
                </button>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
