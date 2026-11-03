import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { Check, ChevronLeft, ChevronRight, Download, Loader2, Plus, RotateCcw, Users, Video, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { MentionTextarea, type MentionTrigger } from '@/components/common/MentionTextarea';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { videoApi, type RecastResolution } from '@/api/video';
import { cn } from '@/lib/utils';
import {
  RECAST_KEYS,
  RECAST_MAX_PEOPLE,
  RECAST_MAX_SECONDS,
  RECAST_MIN_SECONDS,
  formatUsd,
  usePricingStore,
} from '@/stores/pricingStore';
import { RECAST_PHOTO_MAX_MB, recastPhotoProblem, recastVideoProblem, useRecastStore } from '@/stores/recastStore';

const RESOLUTIONS: { id: RecastResolution; label: string }[] = [
  { id: '768p', label: '768p' },
  { id: '1080p', label: '1080p' },
];

// People in the video, as the model understands them (inserted with @).
const ENTITIES = [
  { insert: 'the left character', label: 'Person on the left' },
  { insert: 'the center character', label: 'Person in the middle' },
  { insert: 'the right character', label: 'Person on the right' },
  { insert: 'the character in front', label: 'Person nearest the camera' },
  { insert: 'the character in the background', label: 'Person further back' },
  { insert: 'everyone else', label: 'All other people' },
];
const ENTITY_PATTERN = /\b(the (left|center|centre|middle|right) character|the character in (front|the background)|everyone else)\b/gi;

// "Replace the left character with #Image1 and the right character with
// #Image2." plus a keep list: Recast holds what the prompt names, and
// unnamed fragile details (hair length, accessories) drift between frames.
function examplePrompt(count: number): string {
  const places: Record<number, string[]> = {
    1: ['the main character'],
    2: ['the left character', 'the right character'],
    3: ['the left character', 'the center character', 'the right character'],
    4: ['the far left character', 'the center left character', 'the center right character', 'the far right character'],
  };
  const parts = (places[count] ?? places[1]).map((place, i) => `${place} with #Image${i + 1}`);
  const list = parts.length > 2 ? `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}` : parts.join(' and ');
  const who = count > 1 ? 'each new person' : 'the new person';
  return (
    `Replace ${list}. Keep camera, framing, light, choreography and timing exactly as in the video. ` +
    `Keep ${who}'s hair length and style and accessories (glasses, earrings, a watch) as in the photo, unchanged from the first frame to the last.`
  );
}

function missingMentions(prompt: string, count: number): string[] {
  const found = new Set<string>();
  for (const m of prompt.matchAll(/#image(\d+)\b/gi)) {
    const n = Number(m[1]);
    if (n < 1 || n > count) found.add(`#Image${n}`);
  }
  return [...found];
}

// Numbered step: the current one in the foreground, done ones muted with a check.
function StepTitle({ index, title, done, current }: { index: number; title: string; done: boolean; current: boolean }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span
        aria-hidden="true"
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-full border text-xs tabular',
          current ? 'border-primary text-foreground' : 'border-border text-muted-foreground',
        )}
      >
        {done ? <Check className="h-3.5 w-3.5" /> : index}
      </span>
      <h2 className={cn('text-base font-semibold tracking-tight', !current && 'text-muted-foreground')}>
        {title}
        {done && <span className="sr-only"> (done)</span>}
      </h2>
    </div>
  );
}

const formatElapsed = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

// Multi-character motion transfer: up to four people in a short video are
// replaced by one photo each (MiniMax H3 Max Recast), keeping the motion and
// the original sound.
export function RecastStudio() {
  const {
    video, videoError, isUploadingVideo, people, peopleError, isUploadingPhoto,
    resolution, enhanceRealism, prompt,
    isGenerating, progress, statusText, generatedVideo, error,
    selectVideo, selectVideoAsset, clearVideo, addPhoto, addPhotoAsset, removePerson, movePerson,
    setResolution, setEnhanceRealism, setPrompt, generate, clearError, startOver,
  } = useRecastStore();
  const { getModelCost } = usePricingStore();
  // The source video's shape, so the space for the result does not jump.
  const [srcRatio, setSrcRatio] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!isGenerating) {
      setElapsed(0);
      return;
    }
    const startedAt = Date.now();
    const t = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, [isGenerating]);

  const perSecond = getModelCost(RECAST_KEYS[resolution]);
  const seconds = video ? Math.min(RECAST_MAX_SECONDS, Math.max(1, Math.ceil(Math.round(video.seconds * 10) / 10))) : 0;
  const total = perSecond !== undefined && seconds > 0 ? perSecond * seconds : undefined;
  const busy = isGenerating || isUploadingVideo || isUploadingPhoto;
  const missing = missingMentions(prompt, people.length);
  const canGenerate = !!video && people.length > 0 && !busy && missing.length === 0;
  const triggers: MentionTrigger[] = [
    {
      char: '#',
      title: 'Inputs',
      items: people.map((p, i) => ({ insert: `#Image${i + 1}`, label: `Photo ${i + 1}`, thumbnail: p.preview })),
    },
    { char: '@', title: 'People in the video', items: ENTITIES },
  ];
  const highlights = [
    // Valid mentions first (#Image1 up to the number of photos), then any
    // other #ImageN in red; spans already highlighted are not repeated.
    ...(people.length > 0
      ? [{ pattern: new RegExp(`#Image[1-${people.length}]\\b`, 'gi'), className: 'bg-primary/15 text-foreground' }]
      : []),
    { pattern: /#image\d+\b/gi, className: 'bg-destructive/20 text-destructive' },
    { pattern: ENTITY_PATTERN, className: 'bg-accent text-accent-foreground' },
  ];
  // One photo per person, added in order, up to the free places left.
  const photos = useMediaPicker({
    kinds: ['image'],
    multiple: true,
    maxFiles: Math.max(1, RECAST_MAX_PEOPLE - people.length),
    title: 'Add photos of the new people',
    description: 'A clear, front-facing photo per person, at least 300 px a side.',
    disabled: isGenerating || isUploadingPhoto,
    unusableReason: recastPhotoProblem,
    onFiles: async (files) => {
      for (const f of files) await addPhoto(f);
    },
    onAssets: (assets) => assets.forEach(addPhotoAsset),
  });

  const download = async () => {
    if (!generatedVideo) return;
    try {
      await videoApi.downloadVideo(generatedVideo.id, `recast-${generatedVideo.id}.mp4`);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 pt-4">
            <StepTitle index={1} title="Source video" done={!!video} current={!video} />
            {video ? (
              <div className="space-y-2">
                <div className="relative overflow-hidden rounded-lg border border-border bg-background">
                  <video
                    src={video.preview}
                    controls
                    playsInline
                    className="max-h-[320px] w-full"
                    onLoadedMetadata={(e) => {
                      const v = e.currentTarget;
                      if (v.videoWidth && v.videoHeight) setSrcRatio(v.videoWidth / v.videoHeight);
                    }}
                  />
                  <Button size="icon" variant="glass" className="absolute right-2 top-2" onClick={clearVideo} disabled={isGenerating} aria-label="Remove video">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {video.name}, <span className="font-mono tabular">{video.seconds.toFixed(1)}s</span>{video.assetId ? ', from My Assets' : ''}
                </p>
              </div>
            ) : (
              <MediaDropzone
                kinds={['video']}
                icon={Video}
                label="Video with the people to replace"
                hint={`MP4, MOV or WebM, ${RECAST_MIN_SECONDS} to ${RECAST_MAX_SECONDS} seconds, max 100 MB`}
                title="Add the source video"
                description={`A video with the people to replace, ${RECAST_MIN_SECONDS} to ${RECAST_MAX_SECONDS} seconds.`}
                disabled={isGenerating || isUploadingVideo}
                unusableReason={recastVideoProblem}
                onFiles={(files) => selectVideo(files[0])}
                onAssets={(assets) => selectVideoAsset(assets[0])}
              >
                {isUploadingVideo ? (
                  <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" /> Uploading and measuring
                  </span>
                ) : undefined}
              </MediaDropzone>
            )}
            {videoError && (
              <p className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{videoError}</p>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              Up to {RECAST_MAX_PEOPLE} people, each clearly visible. The new video keeps the motion and the original sound.
              Works best with a static camera, one continuous shot (no cuts), bodies and feet in frame, and no one crossing in front.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 pt-4">
            <StepTitle index={2} title="New people" done={people.length > 0} current={!!video && people.length === 0} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {people.map((p, i) => (
                <div key={p.key} className="space-y-1">
                  <div className="relative aspect-[3/4] overflow-hidden rounded-lg border border-border bg-muted">
                    <img src={p.preview} alt={`Person ${i + 1}`} className="h-full w-full object-cover" />
                    <span className="absolute left-1.5 top-1.5 rounded-md bg-background/85 px-1.5 py-0.5 font-mono text-[10px] text-foreground">
                      #Image{i + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => removePerson(p.key)}
                      disabled={isGenerating}
                      className="absolute right-1.5 top-1.5 rounded-full bg-background/85 p-1 text-foreground hover:bg-background"
                      aria-label={`Remove photo ${i + 1}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                  <div className="flex justify-between">
                    <button type="button" onClick={() => movePerson(p.key, -1)} disabled={isGenerating || i === 0}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" aria-label="Move left">
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <button type="button" onClick={() => movePerson(p.key, 1)} disabled={isGenerating || i === people.length - 1}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" aria-label="Move right">
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
              {people.length < RECAST_MAX_PEOPLE && (
                <button
                  type="button"
                  onClick={photos.open}
                  {...photos.dropProps}
                  disabled={isGenerating || isUploadingPhoto}
                  className={cn(
                    'flex aspect-[3/4] flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-secondary/20 p-2 text-sm text-muted-foreground transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                    photos.dragOver ? 'border-foreground/40 bg-accent/40' : 'border-border hover:border-foreground/30 hover:text-foreground',
                  )}
                >
                  {isUploadingPhoto ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  {isUploadingPhoto ? 'Adding' : 'Add photo'}
                </button>
              )}
            </div>
            {peopleError && (
              <p className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{peopleError}</p>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              One clear, front-facing photo per person (JPG, PNG or WebP, at least 300 px, up to {RECAST_PHOTO_MAX_MB} MB). By
              default the photos replace the people in the video from left to right. Use the arrows to reorder, or say who
              becomes whom in the prompt.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-5 p-4 pt-4">
            <StepTitle index={3} title="Options" done={false} current={!!video && people.length > 0} />
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Resolution</p>
              <div className="grid grid-cols-2 gap-2">
                {RESOLUTIONS.map((r) => {
                  const price = getModelCost(RECAST_KEYS[r.id]);
                  const active = resolution === r.id;
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setResolution(r.id)}
                      disabled={isGenerating}
                      aria-pressed={active}
                      className={cn(
                        'min-h-[52px] rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-60',
                        active
                          ? 'border-primary/60 bg-primary/10 text-foreground'
                          : 'border-border bg-secondary/20 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                      )}
                    >
                      <span className="block text-sm font-medium">{r.label}</span>
                      <span className="block font-mono text-[10px] tabular text-muted-foreground">
                        {price !== undefined ? `${formatUsd(price)}/s` : ' '}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <label htmlFor="recast-prompt" className="text-xs font-medium text-muted-foreground">
                  Prompt
                </label>
                {people.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setPrompt(examplePrompt(people.length))}
                    disabled={isGenerating}
                    className="text-xs text-foreground underline-offset-4 hover:underline disabled:opacity-50"
                  >
                    Use example
                  </button>
                )}
              </div>
              <MentionTextarea
                id="recast-prompt"
                aria-label="Prompt"
                value={prompt}
                onChange={setPrompt}
                triggers={triggers}
                highlights={highlights}
                rows={3}
                maxLength={2000}
                placeholder="Optional: who becomes whom, or what else to keep or change."
                disabled={isGenerating}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Type <span className="rounded-sm bg-primary/15 px-1 font-mono text-foreground">#</span> to reference inputs.{' '}
                <span className="rounded-sm bg-accent px-1 font-mono text-accent-foreground">@</span> to reference entities.
              </p>
              {missing.length > 0 && (
                <p className="mt-1 text-xs text-destructive">
                  {missing.join(', ')} {missing.length === 1 ? 'is' : 'are'} not added yet.{' '}
                  {people.length > 0 ? `Use #Image1 to #Image${people.length}, or add more photos.` : 'Add the photos first.'}
                </p>
              )}
            </div>

            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium">Enhance realism</p>
                <p className="text-xs text-muted-foreground">More natural skin and better blending of the new people into the scene.</p>
              </div>
              <Switch checked={enhanceRealism} onCheckedChange={setEnhanceRealism} disabled={isGenerating} aria-label="Enhance realism" />
            </div>

            <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs tabular text-muted-foreground">
              {perSecond === undefined ? (
                <p>Loading prices</p>
              ) : total !== undefined ? (
                <>
                  <p className="text-foreground">{formatUsd(total)} for this {seconds}-second video</p>
                  <p className="mt-1">{formatUsd(perSecond)}/s x {seconds}s at {resolution}</p>
                </>
              ) : (
                <p>{formatUsd(perSecond)} per second of video at {resolution}</p>
              )}
            </div>

            <div className="flex flex-col items-stretch gap-3">
              <Button size="xl" onClick={() => generate()} disabled={!canGenerate}>
                {isGenerating ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Recasting
                  </>
                ) : (
                  <>
                    Recast {people.length > 1 ? `${people.length} people` : 'the video'}
                    {total !== undefined && <span className="font-mono text-xs tabular opacity-80">{formatUsd(total)}</span>}
                  </>
                )}
              </Button>
              <p className="text-center text-xs text-muted-foreground">Estimated. fal bills for the real video length.</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        {error && (
          <div className="flex items-start justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <span>{error}</span>
            <button onClick={clearError} className="hover:text-destructive/80" aria-label="Dismiss error">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        {isGenerating ? (
          <div className="beam-border rounded-xl">
            <Card>
              <CardContent className="space-y-3 p-4 pt-4">
                <div className="flex items-center justify-between gap-3 text-sm" aria-live="polite">
                  <span className="text-foreground">{statusText || 'Processing'}</span>
                  <span className="shrink-0 font-mono text-xs tabular text-muted-foreground">
                    {formatElapsed(elapsed)} elapsed, {Math.round(progress)}%
                  </span>
                </div>
                <div
                  className="mx-auto w-full rounded-lg border border-border bg-secondary/30"
                  style={{ aspectRatio: srcRatio ?? 16 / 9, maxWidth: srcRatio !== null && srcRatio < 1 ? 300 : undefined }}
                />
                <Progress value={progress} className="h-2" />
                <p className="text-center text-xs text-muted-foreground">
                  Recasting takes a few minutes. You can leave this page and track progress in{' '}
                  <Link to="/my-jobs" className="text-foreground underline underline-offset-4">My Jobs</Link>.
                </p>
              </CardContent>
            </Card>
          </div>
        ) : generatedVideo ? (
          <motion.div key={generatedVideo.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
            <Card>
              <CardContent className="space-y-4 p-4 pt-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
                    <Check className="h-4 w-4 text-success" aria-hidden="true" />
                    Your recast video
                  </h2>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={download}>
                      <Download className="h-4 w-4" />
                      Download
                    </Button>
                    <Button size="sm" variant="outline" onClick={startOver}>
                      <RotateCcw className="h-4 w-4" />
                      Start over
                    </Button>
                  </div>
                </div>
                <div className="flex items-center justify-center">
                  <VideoPlayer src={generatedVideo.url} poster={generatedVideo.thumbnailUrl} showDownload={false} className="border border-border" />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : (
          <Card>
            <CardContent className="flex min-h-[320px] flex-col items-center justify-center p-6 text-center">
              <Users className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
              <p className="mt-3 text-base font-semibold">Your recast appears here</p>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">
                Add a video with up to {RECAST_MAX_PEOPLE} people and one photo for each person to put in their place.
              </p>
            </CardContent>
          </Card>
        )}
      </div>

      {photos.dialog}
    </div>
  );
}
