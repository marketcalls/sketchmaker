import { useRef, useState } from 'react';
import { Captions } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import {
  SAFE_ZONE_FOR_ASPECT,
  facelessApi,
  type CaptionPosition,
  type FacelessProject,
  type ProjectSettings,
  type SafeZone,
  type StepRun,
} from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { ASPECT_CLASS, EmptyState, ErrorNote, Kicker, PillGroup } from '../shared';
import { useRenderPrefs } from './renderPrefs';
import { useDebouncedCallback } from './useDebouncedCallback';

// Approximate platform UI zones as a share of the frame (bottom, right), for
// the preview overlay. The render engine applies its own exact zone.
const ZONES: Record<SafeZone, { label: string; bottom: number; right: number; top: number }> = {
  shorts: { label: 'YouTube Shorts', bottom: 0.135, right: 0.11, top: 0.06 },
  tiktok: { label: 'TikTok', bottom: 0.2, right: 0.15, top: 0.08 },
  reels: { label: 'Instagram Reels', bottom: 0.18, right: 0.12, top: 0.07 },
  youtube: { label: 'YouTube', bottom: 0.12, right: 0, top: 0 },
};

// The render's default highlight (render_job.ACCENT) and position
// (CaptionTrack.position). The swatches are caption colors the viewer sees in
// the video, so they are content values, not interface tokens.
const DEFAULT_HIGHLIGHT = '#FFD166';
const DEFAULT_POSITION: CaptionPosition = 'lower';
const HIGHLIGHTS: { value: string; label: string }[] = [
  { value: '#FFD166', label: 'Gold' },
  { value: '#C8F560', label: 'Lime' },
  { value: '#FFFFFF', label: 'White' },
  { value: '#5CE1E6', label: 'Cyan' },
  { value: '#FF5C8A', label: 'Pink' },
  { value: '#FF8A3D', label: 'Orange' },
];
const POSITION_CLASS: Record<CaptionPosition, string> = {
  lower: 'bottom-[16%]',
  middle: 'top-1/2 -translate-y-1/2',
  upper: 'top-[14%]',
};

function sampleWords(project: FacelessProject): string[] {
  const text = project.script?.scenes[0]?.narration || 'Nobody expected what happened next in the night market';
  return text.replace(/\[[^\]]*\]/g, '').split(/\s+/).filter(Boolean).slice(0, 6);
}

// A mock frame with sample words styled like the preset.
function CaptionPreview({
  preset,
  project,
  zone,
  large,
  highlight = DEFAULT_HIGHLIGHT,
  placement = DEFAULT_POSITION,
}: {
  preset: string;
  project: FacelessProject;
  zone: SafeZone | null;
  large?: boolean;
  highlight?: string;
  placement?: CaptionPosition;
}) {
  const words = sampleWords(project);
  const group = preset === 'minimal_lower' || preset === 'serif_story' ? words.slice(0, 6) : words.slice(0, 3);
  const hot = Math.min(1, group.length - 1);
  const still = project.scenes.flatMap((s) => s.stills).find((s) => s?.url)?.url;
  const z = zone ? ZONES[zone] : null;
  const position = POSITION_CLASS[placement];

  return (
    <div
      className={cn(
        'relative mx-auto overflow-hidden rounded-lg border border-border bg-secondary/60',
        ASPECT_CLASS[project.aspect],
        large ? (project.aspect === '16:9' ? 'w-full' : 'w-full max-w-[300px]') : 'w-full',
      )}
      aria-hidden="true"
    >
      {still && <img src={still} alt="" className="absolute inset-0 h-full w-full object-cover opacity-60" />}
      <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent" />
      {preset !== 'none' && (
        <div className={cn('absolute inset-x-[8%] text-center', position)}>
          {preset === 'bold_pop' && (
            <p className={cn('font-sans font-black uppercase leading-tight tracking-tight', large ? 'text-2xl' : 'text-sm')} style={{ WebkitTextStroke: '1px var(--color-background)' }}>
              {group.map((w, i) => (
                <span
                  key={i}
                  className={cn(i === hot ? '' : 'text-foreground', 'mx-0.5 inline-block', i === hot && 'scale-110')}
                  style={i === hot ? { color: highlight } : undefined}
                >
                  {w}
                </span>
              ))}
            </p>
          )}
          {preset === 'karaoke_box' && (
            <p className={cn('font-sans font-bold leading-tight', large ? 'text-xl' : 'text-xs')}>
              {group.map((w, i) => (
                <span
                  key={i}
                  className={cn('mx-0.5 inline-block rounded px-1', i === hot ? 'text-background' : 'text-foreground')}
                  style={i === hot ? { backgroundColor: highlight } : undefined}
                >
                  {w}
                </span>
              ))}
            </p>
          )}
          {preset === 'minimal_lower' && (
            <p className={cn('rounded bg-background/60 px-2 py-1 font-sans font-medium text-foreground', large ? 'text-sm' : 'text-[9px]')}>
              {group.join(' ')}
            </p>
          )}
          {preset === 'serif_story' && (
            <p className={cn('font-serif italic leading-snug text-foreground', large ? 'text-2xl' : 'text-sm')}>
              {group.map((w, i) => (
                <span key={i} className="mx-0.5 inline-block" style={i === hot ? { color: highlight } : undefined}>
                  {w}
                </span>
              ))}
            </p>
          )}
        </div>
      )}
      {z && (
        <>
          {z.bottom > 0 && (
            <div className="absolute inset-x-0 bottom-0 border-t border-dashed border-destructive/70 bg-destructive/15" style={{ height: `${z.bottom * 100}%` }} />
          )}
          {z.right > 0 && (
            <div className="absolute right-0 top-0 border-l border-dashed border-destructive/70 bg-destructive/15" style={{ width: `${z.right * 100}%`, bottom: `${z.bottom * 100}%` }} />
          )}
          {z.top > 0 && <div className="absolute inset-x-0 top-0 border-b border-dashed border-destructive/50 bg-destructive/10" style={{ height: `${z.top * 100}%` }} />}
        </>
      )}
    </div>
  );
}

export function CaptionsStep({ project }: { project: FacelessProject; runs: StepRun[] }) {
  const { captionStyles, setProject } = useFacelessStore();
  const [prefs, setPrefs] = useRenderPrefs(project.id);
  const [error, setError] = useState<string | null>(null);
  const preset = project.caption_preset ?? 'bold_pop';
  const renderZone = SAFE_ZONE_FOR_ASPECT[project.aspect];
  const previewZone = prefs.previewZone ?? renderZone;
  const hasTimings = project.scenes.some((s) => s.voice.some((v) => v.words && v.words.length > 0));

  // The custom colour shows at once and is saved when the picker goes quiet.
  const [customColor, setCustomColor] = useState<string | null>(null);
  const highlight = customColor ?? project.settings?.caption_highlight ?? DEFAULT_HIGHLIGHT;
  const placement = project.settings?.caption_position ?? DEFAULT_POSITION;

  const pick = async (id: string) => {
    setError(null);
    try {
      setProject(await facelessApi.updateProject(project.id, { caption_preset: id }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the caption style'));
    }
  };

  // Replies can land out of order: only the newest save may change the page.
  const lastSave = useRef(0);
  const saveSettings = async (settings: ProjectSettings) => {
    const seq = ++lastSave.current;
    setError(null);
    try {
      const saved = await facelessApi.updateProject(project.id, { settings });
      if (seq === lastSave.current) setProject(saved);
    } catch (err) {
      if (seq !== lastSave.current) return;
      setCustomColor(null);
      setError(getErrorMessage(err, 'Could not save the caption settings'));
    }
  };
  const saveColor = useDebouncedCallback((color: string) => saveSettings({ caption_highlight: color }));
  const pickSwatch = (color: string) => {
    saveColor.cancel();
    setCustomColor(null);
    saveSettings({ caption_highlight: color });
  };

  if (!project.script) {
    return <EmptyState icon={Captions} title="Script first">Captions follow the recorded voice word by word.</EmptyState>;
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        <section aria-labelledby="cap-styles">
          <Kicker className="mb-2">
            <span id="cap-styles">Caption style</span>
          </Kicker>
          <div role="radiogroup" aria-label="Caption style" className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {captionStyles.map((s) => {
              const active = s.id === preset;
              return (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => pick(s.id)}
                  className={cn(
                    'rounded-xl border p-2 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    active ? 'border-primary/60 bg-primary/10' : 'border-border hover:border-foreground/20',
                  )}
                >
                  <div className={cn(project.aspect === '9:16' && 'mx-auto max-w-[120px]')}>
                    <CaptionPreview preset={s.id} project={project} zone={null} highlight={highlight} placement={placement} />
                  </div>
                  <p className="mt-2 text-sm font-medium text-foreground">{s.label}</p>
                  <p className="text-xs text-muted-foreground">{s.description}</p>
                </button>
              );
            })}
          </div>
        </section>

        <div className="panel space-y-4 rounded-xl p-4">
          <div className="space-y-2">
            <Kicker>Highlight color</Kicker>
            <div role="radiogroup" aria-label="Caption highlight color" className="flex flex-wrap items-center gap-2">
              {HIGHLIGHTS.map((h) => {
                const active = h.value.toLowerCase() === highlight.toLowerCase();
                return (
                  <button
                    key={h.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    aria-label={h.label}
                    title={h.label}
                    onClick={() => pickSwatch(h.value)}
                    className={cn(
                      'h-9 w-9 rounded-full border-2 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      active ? 'border-foreground ring-2 ring-foreground/20 ring-offset-2 ring-offset-background' : 'border-border hover:border-foreground/40',
                    )}
                    style={{ backgroundColor: h.value }}
                  />
                );
              })}
              <label className="flex items-center gap-2 font-mono text-[11px] tabular text-muted-foreground">
                <input
                  type="color"
                  aria-label="Custom highlight color"
                  value={highlight}
                  onChange={(e) => {
                    const color = e.target.value.toUpperCase();
                    setCustomColor(color);
                    saveColor.call(color);
                  }}
                  onBlur={saveColor.flush}
                  className="h-9 w-12 cursor-pointer rounded border border-border bg-transparent"
                />
                {highlight.toUpperCase()}
              </label>
            </div>
            <p className="text-xs text-muted-foreground">The color of the word being spoken (the box behind it in Karaoke).</p>
          </div>
          <div className="space-y-2">
            <Kicker>Position</Kicker>
            <PillGroup<CaptionPosition>
              label="Caption position"
              value={placement}
              onChange={(v) => saveSettings({ caption_position: v })}
              options={[
                { value: 'upper', label: 'Upper' },
                { value: 'middle', label: 'Middle' },
                { value: 'lower', label: 'Lower' },
              ]}
            />
          </div>
        </div>

        <div className="panel space-y-3 rounded-xl p-4">
          <Kicker>Platform safe zone</Kicker>
          <PillGroup<SafeZone>
            label="Preview platform safe zone"
            value={previewZone}
            onChange={(z) => setPrefs({ previewZone: z })}
            options={(Object.keys(ZONES) as SafeZone[]).map((z) => ({ value: z, label: ZONES[z].label }))}
          />
          <p className="text-xs text-muted-foreground">
            The render keeps captions clear of the {ZONES[renderZone].label} interface for {project.aspect} video. Switch the preview to
            check how the same frame sits under other platforms. Shaded areas are covered by buttons and titles there.
          </p>
          <p className="text-xs text-muted-foreground">
            The render uses the highlight and position saved here and keeps captions clear of the platform interface; groups are three words on vertical video and six on landscape.
          </p>
          {!hasTimings && <p className="text-xs text-warning">Captions need the voices: they are timed from the recorded words.</p>}
        </div>
        <ErrorNote>{error}</ErrorNote>
      </div>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        <Kicker className="mb-2">Preview, {ZONES[previewZone].label}</Kicker>
        <CaptionPreview preset={preset} project={project} zone={previewZone} large highlight={highlight} placement={placement} />
      </aside>
    </div>
  );
}
