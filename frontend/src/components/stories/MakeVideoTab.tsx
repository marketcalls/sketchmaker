import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Clapperboard, Film, Loader2, Scissors } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import { useFacelessStore } from '@/stores/facelessStore';
import {
  storyRoomApi, enumLabel, formatRuntime, imageProgress, storyRuntime, ONE_TAKE_MAX_SECONDS,
  type StoryDoc, type StoryThread,
} from '@/api/storyRoom';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { Chip } from './fields';

export type ClipSource = { kind: 'treatment' } | { kind: 'shot'; shotId: string };

// Numbered step: the current one in the foreground, done ones muted with a check.
function Step({
  n, title, done, current, children,
}: { n: number; title: string; done: boolean; current: boolean; children: React.ReactNode }) {
  return (
    <section className="relative pl-10">
      <span
        className={cn(
          'absolute left-0 top-0.5 flex h-6 w-6 items-center justify-center rounded-full border text-xs tabular',
          current ? 'border-primary text-foreground' : 'border-border text-muted-foreground',
        )}
      >
        {done ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : n}
      </span>
      <h3 className={cn('text-base font-semibold leading-7', !current && 'text-muted-foreground')}>
        {title}
        {done && <span className="sr-only"> (done)</span>}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

/** Make video: treatment, approved images, then one take, scene clips or the full video. */
export function MakeVideoTab({
  thread, story, disabled, onOpenClip, onOpenCast,
}: {
  thread: StoryThread;
  story: StoryDoc;
  disabled: boolean;
  onOpenClip: (source: ClipSource) => void;
  onOpenCast: () => void;
}) {
  const navigate = useNavigate();
  const flushSave = useStoryRoomStore((s) => s.flushSave);
  const { templates, catalogLoaded, loadCatalog } = useFacelessStore();
  const [templateId, setTemplateId] = useState<string>('default');
  const [handing, setHanding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ label: string; run: () => void | Promise<void> } | null>(null);

  const treatmentReady = !!(story.treatment ?? '').trim();
  const progress = imageProgress(story);
  const imagesReady = progress.total > 0 && progress.approved === progress.total;
  const runtime = storyRuntime(story);
  const length = runtime > 0 ? runtime : story.target_seconds;
  const oneTakeFits = length <= ONE_TAKE_MAX_SECONDS;
  const hasShots = story.scenes.some((s) => s.shots.length > 0);

  useEffect(() => {
    if (!catalogLoaded) loadCatalog();
  }, [catalogLoaded, loadCatalog]);

  // Video made before every image is approved loses its references: ask first.
  const guarded = (label: string, run: () => void | Promise<void>) => {
    if (imagesReady || progress.total === 0) run();
    else setConfirm({ label, run });
  };

  const toFaceless = async () => {
    setHanding(true);
    setError(null);
    try {
      await flushSave();
      const { projectId } = await storyRoomApi.toFaceless(thread.id, templateId === 'default' ? undefined : templateId);
      navigate(`/faceless/projects/${projectId}`);
    } catch (err) {
      setError(getErrorMessage(err, 'The story could not be sent to Faceless Studio. Please try again.'));
    } finally {
      setHanding(false);
    }
  };

  return (
    <div className="space-y-6">
      <Step n={1} title="Treatment" done={treatmentReady} current={!treatmentReady}>
        <p className="text-sm text-muted-foreground">
          {treatmentReady
            ? `Ready: ${story.scenes.length} scenes, ${formatRuntime(runtime)} cut for a ${formatRuntime(story.target_seconds)} target.`
            : 'Send a brief in the chat. The director writes the treatment in its first reply.'}
        </p>
      </Step>

      <Step n={2} title="Reference images" done={imagesReady} current={treatmentReady && !imagesReady}>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs">
            <span className={cn('font-mono tabular', imagesReady ? 'text-success' : 'text-foreground')}>{progress.approved} of {progress.total}</span>{' '}
            <span className="text-muted-foreground">approved</span>
          </p>
          <Button size="sm" variant="outline" onClick={onOpenCast}>Open Cast</Button>
        </div>
        {!imagesReady && progress.total > 0 && (
          <p className="mt-1.5 text-xs text-muted-foreground">
            Approved images keep faces, wardrobe, places and products the same from shot to shot.
          </p>
        )}
      </Step>

      <Step n={3} title="Video" done={false} current={treatmentReady && (imagesReady || progress.total === 0)}>
        {error && <p className="mb-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
        <div className="space-y-3">
          {/* One take */}
          <div className="rounded-xl border border-border p-3">
            <div className="flex items-start gap-3">
              <Clapperboard className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">One take</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  The whole piece as a single clip from the treatment, with the approved images as references. For pieces up to {ONE_TAKE_MAX_SECONDS} seconds.
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={disabled || !treatmentReady || !oneTakeFits}
                onClick={() => guarded('one take', () => onOpenClip({ kind: 'treatment' }))}
                title={!oneTakeFits ? `This cut runs ${formatRuntime(length)}. Use scene clips or the full video.` : undefined}
              >
                Open in Quick clip
              </Button>
            </div>
            {!oneTakeFits && treatmentReady && (
              <p className="mt-2 pl-7 text-[11px] text-muted-foreground">This cut runs {formatRuntime(length)}, longer than one take allows.</p>
            )}
          </div>

          {/* Scene clips */}
          <div className="rounded-xl border border-border p-3">
            <div className="flex items-start gap-3">
              <Scissors className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div>
                <p className="text-sm font-semibold">Scene clips</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Each shot as its own clip with the director's prompt and the references of who, what and where is in frame. A shot with a keyframe, or a hero shot of a product with its photo, opens on that image. The clip is priced in Quick clip before you generate.
                </p>
              </div>
            </div>
            {hasShots ? (
              <div className="mt-3 space-y-3">
                {story.scenes.map((scene) => (
                  <div key={scene.id}>
                    <p className="mb-1 text-xs font-medium text-foreground/90">{scene.heading || scene.id}</p>
                    <div className="divide-y divide-border rounded-lg border border-border">
                      {scene.shots.map((shot) => (
                        <div key={shot.id} className="flex items-center gap-2 px-2.5 py-1.5">
                          <span className="w-10 shrink-0 font-mono text-[11px] tabular text-muted-foreground">{shot.id}</span>
                          <Chip className="shrink-0">{enumLabel(shot.type)}</Chip>
                          <span className="min-w-0 flex-1 truncate text-xs text-foreground/90">{shot.action || 'No action written'}</span>
                          {shot.keyframe_approved && shot.keyframe_url && <Chip accent className="shrink-0">Keyframe</Chip>}
                          <span className="shrink-0 font-mono text-[10px] tabular text-muted-foreground">{formatRuntime(shot.duration_seconds)}</span>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 shrink-0 px-2.5"
                            disabled={disabled}
                            onClick={() => guarded(`a clip of shot ${shot.id}`, () => onOpenClip({ kind: 'shot', shotId: shot.id }))}
                          >
                            Make clip
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 pl-7 text-xs text-muted-foreground">No shots yet.</p>
            )}
          </div>

          {/* Full video */}
          <div className="rounded-xl border border-border p-3">
            <div className="flex items-start gap-3">
              <Film className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">Full video</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Faceless Studio turns the story into a finished video with narration, voices, music and captions. Unsaved characters are saved to your library first. Sending is free; each production step is priced in the studio.
                </p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 pl-7">
              {templates.length > 0 && (
                <Select value={templateId} onValueChange={setTemplateId}>
                  <SelectTrigger className="h-8 w-[200px] text-xs" aria-label="Faceless template">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Default template</SelectItem>
                    {templates.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
              <Button size="sm" disabled={disabled || handing || !hasShots} onClick={() => guarded('the full video', toFaceless)}>
                {handing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {handing ? 'Opening Faceless Studio' : 'Open in Faceless Studio'}
              </Button>
            </div>
          </div>
        </div>
      </Step>

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Some reference images are not approved"
        description={`${progress.total - progress.approved} of ${progress.total} characters, places and products have no approved image, so ${confirm?.label ?? 'this video'} may not keep faces, wardrobe, places and products consistent. Continue anyway?`}
        confirmText="Continue"
        onConfirm={async () => {
          const run = confirm?.run;
          setConfirm(null);
          await run?.();
        }}
      />
    </div>
  );
}
