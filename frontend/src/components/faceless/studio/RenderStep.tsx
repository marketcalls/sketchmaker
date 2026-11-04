import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { CheckCircle2, Circle, Clapperboard, Download, ExternalLink, Loader2, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { cn } from '@/lib/utils';
import { formatLocalDateTime } from '@/lib/dateUtils';
import { videoApi } from '@/api/video';
import { formatUsd } from '@/stores/pricingStore';
import { facelessApi, type FacelessProject, type RenderResolution, type StepRun, type StudioStep } from '@/api/faceless';
import { assetsApi } from '@/api/assets';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { useFacelessStore } from '@/stores/facelessStore';
import { ASPECT_CLASS, EmptyState, ErrorNote, FieldLabel, Kicker, PillGroup, formatDuration } from '../shared';
import { Elapsed } from './RunsStrip';
import { usePaidStep } from './usePaidStep';
import { usePaidGate } from './gate';
import { useLiveQuote } from './useLiveQuote';
import { useDebouncedCallback } from './useDebouncedCallback';
import { useRenderPrefs } from './renderPrefs';
import { activeRun, assetsOf, clipScenes, hasClip, hasStill, lastRun, voiceReady } from './stepState';
import { errorSuffix, friendlyError, getErrorMessage } from '@/utils/errors';

interface CheckRow {
  label: string;
  detail: string;
  ok: boolean;
  required: boolean;
  step: StudioStep;
}

export function RenderStep({
  project,
  runs,
  onGoto,
}: {
  project: FacelessProject;
  runs: StepRun[];
  onGoto: (s: StudioStep) => void;
}) {
  const { config, captionStyles, musicMoods, setProject } = useFacelessStore();
  const gate = usePaidGate(project, 'render');
  const { request, dialog } = usePaidStep(project.id);
  const [prefs, setPrefs] = useRenderPrefs(project.id);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scenes = project.script?.scenes ?? [];
  // Ads (Story Room hand-off) end on a brand beat that can carry a logo.
  const isAd = project.script?.format === 'ad';
  const exactSeconds = typeof project.script?.exact_seconds === 'number' ? project.script.exact_seconds : null;
  const logoId = project.settings.ad_logo_asset_id || null;
  const [savingLogo, setSavingLogo] = useState(false);
  const saveLogo = async (assetId: number) => {
    setSavingLogo(true);
    setError(null);
    try {
      setProject(await facelessApi.updateProject(project.id, { settings: { ad_logo_asset_id: assetId } }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the logo'));
    } finally {
      setSavingLogo(false);
    }
  };
  // Colour grade (backend services/faceless/grade.py): saved on the project,
  // read by the render. Strength is shown in per cent.
  const looks = config?.grade_looks ?? [];
  const look = project.settings.grade_look ?? 'neutral';
  const savedStrength = Math.round((project.settings.grade_strength ?? 0.8) * 100);
  const [strength, setStrength] = useState<number | null>(null);
  const plateCount = Object.keys(project.settings.grade_plates ?? {}).length;
  const [savingGrade, setSavingGrade] = useState(false);
  const saveGrade = async (settings: { grade_look?: string; grade_strength?: number; grade_match?: boolean }) => {
    setSavingGrade(true);
    setError(null);
    try {
      setProject(await facelessApi.updateProject(project.id, { settings }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the look'));
    } finally {
      setSavingGrade(false);
      setStrength(null);
    }
  };
  const saveStrength = useDebouncedCallback((percent: number) => saveGrade({ grade_strength: percent / 100 }));
  const logoPicker = useMediaPicker({
    kinds: ['logo', 'image'],
    accept: 'image/png,image/jpeg,image/webp',
    title: 'End card logo',
    unusableReason: (a) => (a.contentType?.includes('svg') ? 'SVG logos cannot be drawn on video. Use a PNG.' : null),
    saveUploads: false,
    onFiles: async (files) => {
      const asset = await assetsApi.upload(files[0], { asLogo: true });
      await saveLogo(asset.id);
    },
    onAssets: async (assets) => saveLogo(assets[0].id),
  });
  const resolutions = config?.models.render_resolutions ?? ['1080p', '720p'];
  const resolution: RenderResolution = prefs.resolution ?? project.settings.render_resolution ?? '1080p';
  const live = activeRun(project, 'render');
  const last = lastRun(runs, 'render');
  const render = project.render;

  const options = useMemo(() => {
    const o: { resolution: RenderResolution; music: boolean; music_gain_db?: number } = { resolution, music: prefs.music };
    if (prefs.musicGainDb !== null) o.music_gain_db = prefs.musicGainDb;
    return o;
  }, [resolution, prefs.music, prefs.musicGainDb]);
  const quote = useLiveQuote(project.id, 'render', undefined, options, scenes.length > 0 && !live, `${project.updated_at}`);

  const rows: CheckRow[] = useMemo(() => {
    const visual = scenes.filter((s) => s.shot.kind !== 'card');
    const pictured = visual.filter((s) => {
      const a = assetsOf(project, s.id);
      return hasStill(a) || hasClip(a) || !!a?.user_media;
    });
    const clips = clipScenes(scenes);
    const animated = clips.filter((s) => hasClip(assetsOf(project, s.id)));
    const voiced = project.scenes.filter((a) => a.voice.length > 0);
    const voicedOk = voiced.filter(voiceReady);
    const moodLabel = musicMoods.find((m) => m.id === project.music_mood)?.label ?? project.music_mood ?? 'none';
    const hasMusic = (project.music?.tracks ?? []).some((t) => t.url);
    const captions = captionStyles.find((c) => c.id === project.caption_preset)?.label ?? project.caption_preset ?? 'none';
    return [
      { label: 'Script', detail: `version ${project.script_version}, ${scenes.length} scenes`, ok: scenes.length > 0, required: true, step: 'script' },
      { label: 'Pictures', detail: `${pictured.length} of ${visual.length} scenes`, ok: pictured.length === visual.length && visual.length > 0, required: true, step: 'storyboard' },
      { label: 'Clips', detail: clips.length ? `${animated.length} of ${clips.length} animated scenes` : 'none planned, stills move', ok: animated.length === clips.length, required: false, step: 'animate' },
      { label: 'Voice', detail: `${voicedOk.length} of ${voiced.length} scenes`, ok: voiced.length > 0 && voicedOk.length === voiced.length, required: false, step: 'voice' },
      { label: 'Music', detail: project.music_mood === 'none' ? 'off' : hasMusic ? moodLabel : 'no track', ok: hasMusic || project.music_mood === 'none', required: false, step: 'music' },
      { label: 'Captions', detail: captions, ok: true, required: false, step: 'captions' },
      { label: 'Compliance', detail: project.compliance?.blocked ? 'blocked' : `${project.compliance?.flags.length ?? 0} notes`, ok: !project.compliance?.blocked, required: true, step: 'script' },
    ];
  }, [project, scenes, captionStyles, musicMoods]);

  const ready = rows.every((r) => !r.required || r.ok);

  const download = async () => {
    if (!render?.video_id) return;
    setDownloading(true);
    setError(null);
    try {
      await videoApi.downloadVideo(render.video_id, `${(project.title || 'faceless').replace(/[^\w-]+/g, '-').slice(0, 60)}.mp4`);
    } catch {
      setError('Download failed. Try again, or open it in My Gallery.');
    } finally {
      setDownloading(false);
    }
  };

  if (scenes.length === 0) {
    return <EmptyState icon={Clapperboard} title="Nothing to render yet">Write the script and make the pictures first.</EmptyState>;
  }

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_340px]">
      <div className="space-y-5">
        {live ? (
          <div className={cn('space-y-3', project.aspect === '9:16' && 'mx-auto max-w-sm')} aria-live="polite">
            <div
              className={cn(
                'beam-border panel flex flex-col items-center justify-center rounded-xl p-6 text-center',
                ASPECT_CLASS[project.aspect],
              )}
            >
              <Clapperboard className="mb-3 h-6 w-6 text-muted-foreground" aria-hidden="true" />
              <p className="text-sm font-medium">
                {live.status === 'queued' ? 'Queued for rendering' : `Rendering, ${live.progress}%`}
              </p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                {live.status === 'queued' ? 'Waiting for the render queue. One video renders at a time.' : 'Compositing clips, voice, music and captions.'}
              </p>
              <Elapsed since={live.started_at ?? live.created_at} className="mt-2 font-mono text-xs tabular text-muted-foreground" />
            </div>
            <Progress value={live.progress} aria-label="Render progress" />
          </div>
        ) : render?.url && !render.deleted ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} className="space-y-3">
            <div className={cn('overflow-hidden rounded-xl border border-border bg-background', project.aspect === '9:16' && 'mx-auto max-w-sm')}>
              <VideoPlayer src={render.url} poster={render.thumbnail_url ?? undefined} showDownload={false} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={download} disabled={downloading || !render.video_id}>
                {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Download MP4
              </Button>
              <Button asChild variant="outline">
                <Link to="/gallery">
                  <ExternalLink className="h-4 w-4" /> Open in My Gallery
                </Link>
              </Button>
              <span className="font-mono text-[11px] tabular text-muted-foreground">
                {render.width}x{render.height}, {formatDuration(render.duration)}
                {render.rendered_at && `, ${formatLocalDateTime(render.rendered_at)}`}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              The video is in My Gallery. Re-render any time after changing scenes; each render is quoted.
            </p>
          </motion.div>
        ) : (
          <div className="panel flex flex-col items-center rounded-xl px-6 py-12 text-center">
            <Clapperboard className="mb-3 h-6 w-6 text-muted-foreground" aria-hidden="true" />
            <p className="text-base font-semibold">{render?.deleted ? 'The last render was deleted from the gallery' : 'Not rendered yet'}</p>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              The render follows the voice timing, cuts where the script cuts and dissolves only where it asks, keeps every
              picture moving, and lays leveled voice, music and captions on top.
            </p>
          </div>
        )}

        {last && (last.status === 'failed' || last.status === 'cancelled') && !live && (
          <p className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            The last render {last.status === 'cancelled' ? 'was cancelled' : 'failed'}
            {errorSuffix(last.error, '.')}
          </p>
        )}
        <ErrorNote>{error}</ErrorNote>
      </div>

      <aside className="space-y-4">
        <section className="panel rounded-xl p-4" aria-labelledby="render-check">
          <h3 id="render-check" className="mb-3 text-base font-semibold">Pre-flight</h3>
          <ul className="space-y-1">
            {rows.map((r) => (
              <li key={r.label}>
                <button
                  type="button"
                  onClick={() => onGoto(r.step)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {r.ok ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                  ) : r.required ? (
                    <TriangleAlert className="h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
                  ) : (
                    <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  )}
                  <span>{r.label}</span>
                  <span className="ml-auto truncate text-[11px] text-muted-foreground">{r.detail}</span>
                  <span className="sr-only">{r.ok ? 'ready' : r.required ? 'required' : 'optional'}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel space-y-4 rounded-xl p-4" aria-labelledby="render-opts">
          <h3 id="render-opts" className="text-base font-semibold">Output</h3>
          <div>
            <FieldLabel>Resolution</FieldLabel>
            <PillGroup<RenderResolution>
              label="Render resolution"
              value={resolution}
              onChange={(r) => setPrefs({ resolution: r })}
              options={resolutions.map((r) => ({ value: r, label: r }))}
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <label htmlFor="rd-music" className="text-sm">Include music</label>
            <Switch id="rd-music" checked={prefs.music} onCheckedChange={(v) => setPrefs({ music: v })} />
          </div>
          {looks.length > 0 && (
            <div>
              <FieldLabel hint={looks.find((l) => l.id === look)?.description}>Look</FieldLabel>
              <PillGroup<string>
                label="Colour look"
                value={look}
                disabled={savingGrade}
                onChange={(id) => saveGrade({ grade_look: id })}
                options={looks.map((l) => ({ value: l.id, label: l.label, hint: l.description }))}
              />
              {look !== 'neutral' && (
                <div className="mt-3">
                  <FieldLabel htmlFor="rd-grade-strength" hint={`${strength ?? savedStrength}%`}>Strength</FieldLabel>
                  <Slider
                    id="rd-grade-strength"
                    aria-label="Look strength"
                    min={0}
                    max={100}
                    step={5}
                    value={[strength ?? savedStrength]}
                    disabled={savingGrade}
                    onValueChange={(v) => setStrength(v[0])}
                    onValueCommit={(v) => saveStrength.call(v[0])}
                  />
                </div>
              )}
              {plateCount > 0 && (
                <div className="mt-3 flex items-center justify-between gap-3">
                  <label htmlFor="rd-grade-match" className="text-sm">
                    Match clips to approved places
                  </label>
                  <Switch
                    id="rd-grade-match"
                    checked={!!project.settings.grade_match}
                    disabled={savingGrade}
                    onCheckedChange={(v) => saveGrade({ grade_match: v })}
                  />
                </div>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                The look grades the pictures only; titles, captions and the end card keep their colours.
                {plateCount > 0 && ' Matching evens out colour between clips of the same place from the Story Room.'}
              </p>
            </div>
          )}
          {isAd && (
            <div>
              <FieldLabel hint={`${exactSeconds ?? ''} s ad, ends on the call to action`}>End card logo</FieldLabel>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={logoPicker.open} disabled={savingLogo}>
                  {logoId ? 'Change logo' : 'Choose a logo'}
                </Button>
                {logoId ? (
                  <Button variant="ghost" size="sm" onClick={() => saveLogo(0)} disabled={savingLogo}>
                    Remove
                  </Button>
                ) : null}
                <span className="text-xs text-muted-foreground">
                  {logoId ? 'Logo on the end card' : 'No logo'}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">PNG, JPEG or WebP from My Assets or a new upload.</p>
              {logoPicker.dialog}
            </div>
          )}
          <div className="border-t border-border pt-3" aria-live="polite">
            <Kicker className="mb-1">Final quote</Kicker>
            {quote.loading ? (
              <Skeleton className="h-8 w-28"><span className="sr-only">Pricing</span></Skeleton>
            ) : quote.quote ? (
              <>
                <p className="font-mono text-2xl font-medium tabular text-foreground">
                  {formatUsd(quote.quote.usd)} <span className="font-sans text-sm font-normal text-muted-foreground">estimated</span>
                </p>
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {quote.quote.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </>
            ) : quote.error ? (
              <p className="text-sm text-warning">{friendlyError(quote.error)}</p>
            ) : null}
          </div>
          <Button
            size="lg"
            className="w-full"
            disabled={!!gate || !ready || !!quote.error}
            title={gate ?? (!ready ? 'Finish the required steps first' : undefined)}
            onClick={() =>
              request({
                step: 'render',
                options,
                title: render?.url ? 'Render again' : 'Render the video',
                description: `${project.aspect} at ${resolution}, about ${formatDuration(project.total_seconds)}.`,
                confirmLabel: 'Confirm and render',
              })
            }
          >
            <Clapperboard className="h-4 w-4" /> {render?.url ? 'Render again' : 'Render'}
          </Button>
          {gate && gate !== 'Already running' && <p className="text-xs text-muted-foreground">{gate}.</p>}
        </section>
      </aside>
      {dialog}
    </div>
  );
}
