import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  AudioLines,
  Check,
  Download,
  ImageIcon,
  Mic,
  Upload,
  Loader2,
  Play,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { VoiceGenerator } from '@/components/assets/VoiceGenerator';
import type { Asset } from '@/api/assets';
import { SEO } from '@/components/SEO';
import { cn } from '@/lib/utils';
import { formatLocalDate } from '@/lib/dateUtils';
import { videoApi } from '@/api/video';
import type { LipSyncResolution } from '@/api/lipsync';
import type { GeneratedVideo } from '@/types';
import { useQualityConfig } from '@/components/quality/QualityBadge';
import {
  LIPSYNC_LONG_AFTER_SECONDS,
  LIPSYNC_LONG_MULTIPLIER,
  LIPSYNC_MAX_SECONDS,
  LIPSYNC_MIN_SECONDS,
  formatUsd,
  lipsyncKey,
  lipsyncUsd,
  usePricingStore,
} from '@/stores/pricingStore';
import {
  LIPSYNC_ASPECT_MAX,
  LIPSYNC_ASPECT_MIN,
  LIPSYNC_AUDIO_MAX_MB,
  LIPSYNC_IMAGE_MAX_MB,
  lipsyncAudioProblem,
  lipsyncImageProblem,
  useLipSyncStore,
} from '@/stores/lipsyncStore';

type AudioSource = 'upload' | 'voice';

const AUDIO_SOURCES: { id: AudioSource; label: string; icon: typeof Upload }[] = [
  { id: 'upload', label: 'Audio file', icon: Upload },
  { id: 'voice', label: 'Generate voice', icon: Mic },
];

const RESOLUTIONS: { id: LipSyncResolution; label: string }[] = [
  { id: '480p', label: '480p' },
  { id: '768p', label: '768p' },
  { id: '1080p', label: '1080p' },
  { id: '2k', label: '2K' },
];

function formatSeconds(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return m > 0 ? `${m}:${s.toFixed(1).padStart(4, '0')}` : `${s.toFixed(1)}s`;
}

// Seconds since `active` turned on, for the plain status line while working.
function useElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [active]);
  return elapsed;
}

function formatElapsed(total: number): string {
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

// Numbered step heading: done steps show a muted check, the rest their number.
function StepTitle({ index, title, done }: { index: number; title: string; done: boolean }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span
        aria-hidden="true"
        className="flex h-6 w-6 items-center justify-center rounded-full border border-border text-[11px] tabular text-muted-foreground"
      >
        {done ? <Check className="h-3.5 w-3.5" /> : index}
      </span>
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      {done && <span className="sr-only">(done)</span>}
    </div>
  );
}

export function LipSyncPage() {
  const {
    imagePreview, image, imageError, isUploadingImage,
    audioPreview, audioName, audio, audioError, isUploadingAudio,
    resolution, enableTranscription, faceCheck,
    isGenerating, progress, statusText, estimatedUsd, generatedVideo, error,
    videos, isLoadingGallery,
    selectImage, selectImageAsset, clearImage, selectAudio, selectAudioAsset, clearAudio,
    setResolution, setEnableTranscription, setFaceCheck,
    generate, clearError, startOver, loadGallery, deleteVideo,
  } = useLipSyncStore();

  const { getModelCost } = usePricingStore();

  const [shownVideo, setShownVideo] = useState<GeneratedVideo | null>(null);
  const [audioSource, setAudioSource] = useState<AudioSource>('upload');
  const location = useLocation();
  const navigate = useNavigate();

  // "Use in Lip Sync" from My Assets passes the asset in the route state.
  useEffect(() => {
    const asset = (location.state as { asset?: Asset } | null)?.asset;
    if (!asset) return;
    if (asset.kind === 'audio') {
      selectAudioAsset(asset);
      setAudioSource('upload');
    } else if (asset.kind === 'image' || asset.kind === 'logo') {
      selectImageAsset(asset);
    }
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, navigate, selectAudioAsset, selectImageAsset]);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const elapsed = useElapsed(isGenerating);

  useEffect(() => {
    loadGallery();
  }, [loadGallery]);

  // A new result replaces whatever recent video was being viewed.
  useEffect(() => {
    if (generatedVideo) setShownVideo(null);
  }, [generatedVideo]);

  const displayed = shownVideo ?? generatedVideo;

  // Price: USD per second at this resolution times the audio's whole seconds,
  // 1.2x over 15 seconds (backend lipsync_usd).
  const perSecond = getModelCost(lipsyncKey(resolution));
  const seconds = audio?.billableSeconds ?? 0;
  const isLong = seconds > LIPSYNC_LONG_AFTER_SECONDS;
  // The optional face check runs first, at the quality check price.
  const qa = useQualityConfig();
  const faceCheckOn = faceCheck && !!qa?.available;
  const checkUsd = faceCheckOn && qa ? qa.estimated_usd : 0;
  const videoUsd = perSecond !== undefined && seconds > 0 ? lipsyncUsd(perSecond, seconds) : undefined;
  const totalUsd = videoUsd !== undefined ? videoUsd + checkUsd : undefined;

  const busy = isGenerating || isUploadingImage || isUploadingAudio;
  const canGenerate = !!image && !!audio && !busy;

  const handleDownload = async (video: GeneratedVideo) => {
    try {
      await videoApi.downloadVideo(video.id, `lipsync-${video.id}.mp4`);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const showRecent = (video: GeneratedVideo) => {
    setShownVideo(video);
    resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <>
      <SEO
        title="Lip Sync Video"
        description="Turn a portrait and a voice recording into a talking video. Upload an image and audio, and AI lip sync animates the face to match every word."
        keywords="AI lip sync, talking photo, talking avatar, image to video, audio to video, MiniMax H3"
        url="/lip-sync"
      />
      <div className="w-full">
        <header className="mb-6">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Lip sync</h1>
          <p className="mt-1 max-w-prose text-pretty text-sm text-muted-foreground">
            Add a portrait and a voice track (upload one, generate a voice, or pick from My Assets). The face speaks every word, for as long as the audio runs.
          </p>
        </header>

        <div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Inputs */}
            <div className="space-y-6">
              <Card>
                <CardContent className="p-4 pt-4">
                  <StepTitle index={1} title="Portrait" done={!!image} />
                  {imagePreview ? (
                    <div className="space-y-2">
                      <div className="relative flex max-h-[360px] items-center justify-center overflow-hidden rounded-lg border border-border bg-muted">
                        <img src={imagePreview} alt="Portrait" className="max-h-[360px] w-full object-contain" />
                        {isUploadingImage && (
                          <div role="status" className="absolute inset-x-0 bottom-0 bg-background/80 px-3 py-2 text-xs text-muted-foreground">
                            Uploading portrait
                          </div>
                        )}
                        <Button
                          size="icon"
                          variant="glass"
                          className="absolute right-2 top-2"
                          onClick={clearImage}
                          disabled={isGenerating}
                          aria-label="Remove portrait"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                      {image && (
                        <p className="font-mono text-xs tabular text-muted-foreground">
                          {image.width}x{image.height}, aspect ratio {image.aspectRatio.toFixed(2)}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <MediaDropzone
                        kinds={['image']}
                        icon={ImageIcon}
                        label="Portrait image"
                        hint={`PNG, JPEG or WebP, max ${LIPSYNC_IMAGE_MAX_MB} MB, aspect ratio ${LIPSYNC_ASPECT_MIN} to ${LIPSYNC_ASPECT_MAX}`}
                        title="Add a portrait"
                        description="One large, front-facing face with the mouth unobstructed. PNG, JPEG or WebP up to 10 MB."
                        disabled={isGenerating}
                        unusableReason={lipsyncImageProblem}
                        onFiles={(files) => selectImage(files[0])}
                        onAssets={(assets) => selectImageAsset(assets[0])}
                      />
                    </div>
                  )}
                  {imageError && (
                    <p role="alert" className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                      {imageError}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-muted-foreground">
                    Use one large, front-facing face: a head-and-shoulders shot where the face fills a good part of the
                    picture, looking at the camera, with nothing covering the mouth (hands, a microphone, hair, a mask).
                    A small, turned or covered face still renders and is billed, but the mouth may not move. The video
                    uses the supported aspect ratio nearest the image.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4 pt-4">
                  <StepTitle index={2} title="Audio" done={!!audio} />
                  {audioPreview ? (
                    <div className="space-y-2 rounded-lg border border-border bg-secondary/40 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="min-w-0 truncate text-sm">{audioName}</p>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={clearAudio}
                          disabled={isGenerating}
                          aria-label="Remove audio"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                      <audio src={audioPreview} controls preload="metadata" className="w-full" />
                      <p className="text-xs tabular text-muted-foreground">
                        {isUploadingAudio ? (
                          <span className="inline-flex items-center gap-2" role="status">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Uploading and measuring
                          </span>
                        ) : audio ? (
                          `Measured length ${formatSeconds(audio.durationSeconds)}, video length ${audio.billableSeconds}s`
                        ) : null}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div role="tablist" aria-label="Audio source" className="grid grid-cols-2 gap-1 rounded-md border border-border bg-muted/60 p-1">
                        {AUDIO_SOURCES.map(({ id, label, icon: Icon }) => (
                          <button
                            key={id}
                            type="button"
                            role="tab"
                            aria-selected={audioSource === id}
                            onClick={() => setAudioSource(id)}
                            className={cn(
                              'inline-flex items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm',
                              audioSource === id ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground',
                            )}
                          >
                            <Icon className="h-3.5 w-3.5" />
                            {label}
                          </button>
                        ))}
                      </div>
                      {audioSource === 'upload' && (
                        <MediaDropzone
                          kinds={['audio']}
                          icon={AudioLines}
                          label="Voice audio"
                          hint={`MP3, WAV, M4A, AAC or OGG, max ${LIPSYNC_AUDIO_MAX_MB} MB, ${LIPSYNC_MIN_SECONDS} s to ${LIPSYNC_MAX_SECONDS / 60} min`}
                          title="Add audio"
                          description={`Speech from ${LIPSYNC_MIN_SECONDS} seconds to ${LIPSYNC_MAX_SECONDS / 60} minutes. Voices you generated are in My Assets.`}
                          disabled={isGenerating}
                          unusableReason={lipsyncAudioProblem}
                          onFiles={(files) => selectAudio(files[0])}
                          onAssets={(assets) => selectAudioAsset(assets[0])}
                        />
                      )}
                      {audioSource === 'voice' && (
                        <div className="rounded-xl border border-border bg-secondary/20 p-4">
                          <VoiceGenerator
                            onCreated={selectAudioAsset}
                            disabled={isGenerating}
                            minSeconds={LIPSYNC_MIN_SECONDS}
                            maxSeconds={LIPSYNC_MAX_SECONDS}
                            lengthHint={`Lip Sync needs ${LIPSYNC_MIN_SECONDS} seconds to ${LIPSYNC_MAX_SECONDS / 60} minutes`}
                          />
                        </div>
                      )}
                    </div>
                  )}
                  {audioError && (
                    <p role="alert" className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                      {audioError}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-muted-foreground">
                    The video is exactly as long as the audio. Audio is limited to {LIPSYNC_MAX_SECONDS / 60} minutes for now.
                    {audio?.assetId ? ' This audio is in My Assets.' : ''}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="space-y-5 p-4 pt-4">
                  <StepTitle index={3} title="Options" done={!!image && !!audio} />

                  <div>
                    <p className="mb-2 text-xs font-medium text-muted-foreground">Resolution</p>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {RESOLUTIONS.map((r) => {
                        const price = getModelCost(lipsyncKey(r.id));
                        const active = resolution === r.id;
                        return (
                          <button
                            key={r.id}
                            type="button"
                            onClick={() => setResolution(r.id)}
                            disabled={isGenerating}
                            aria-pressed={active}
                            className={cn(
                              'min-h-[52px] rounded-md border px-3 py-2 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60',
                              active
                                ? 'border-primary/60 bg-primary/10 text-foreground'
                                : 'border-border bg-secondary/20 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                            )}
                          >
                            <span className="block text-sm font-medium">{r.label}</span>
                            <span className="block font-mono text-[10px] tabular text-muted-foreground">
                              {price !== undefined ? `${formatUsd(price)}/s` : '\u00a0'}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-medium">Use transcription for better sync</p>
                      <p className="text-xs text-muted-foreground">
                        Transcribes the speech to guide the mouth shapes. Helps most with clear speech.
                      </p>
                    </div>
                    <Switch
                      checked={enableTranscription}
                      onCheckedChange={setEnableTranscription}
                      disabled={isGenerating}
                      aria-label="Use transcription for better sync"
                    />
                  </div>

                  {qa?.available && (
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium">
                          Check the face first <span className="font-mono text-xs text-muted-foreground">{formatUsd(qa.estimated_usd)}</span>
                        </p>
                        <p className="text-xs text-muted-foreground">
                          A quick look for one large, front-facing face with the mouth in view. If the photo will not sync
                          well, only the check is billed.
                        </p>
                      </div>
                      <Switch
                        checked={faceCheck}
                        onCheckedChange={setFaceCheck}
                        disabled={isGenerating}
                        aria-label="Check the face first"
                      />
                    </div>
                  )}

                  {/* Price */}
                  <div className="rounded-lg border border-border bg-secondary/40 p-3 font-mono text-xs tabular text-muted-foreground">
                    {perSecond === undefined ? (
                      <p>Loading prices</p>
                    ) : totalUsd !== undefined ? (
                      <>
                        <p className="text-foreground">
                          {formatUsd(totalUsd)} for this {seconds}-second video
                        </p>
                        <p className="mt-1">
                          {formatUsd(perSecond)}/s x {seconds}s
                          {isLong ? ` x ${LIPSYNC_LONG_MULTIPLIER} (over ${LIPSYNC_LONG_AFTER_SECONDS}s)` : ''}
                          {checkUsd > 0 ? ` + ${formatUsd(checkUsd)} face check` : ''}
                        </p>
                      </>
                    ) : (
                      <p>
                        {formatUsd(perSecond)} per second of video, {LIPSYNC_LONG_MULTIPLIER}x for videos over{' '}
                        {LIPSYNC_LONG_AFTER_SECONDS} seconds
                      </p>
                    )}
                  </div>

                  <div className="flex flex-col items-stretch gap-3">
                    <Button size="xl" onClick={() => generate()} disabled={!canGenerate}>
                      {isGenerating ? (
                        <>
                          <Loader2 className="h-5 w-5 animate-spin" />
                          Generating
                        </>
                      ) : (
                        <>
                          Generate lip sync
                          {totalUsd !== undefined && (
                            <span className="font-mono text-xs tabular opacity-80">{formatUsd(totalUsd)}</span>
                          )}
                        </>
                      )}
                    </Button>
                    <p className="text-center text-xs text-muted-foreground">
                      Estimated. fal bills for the real video length.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Result */}
            <div ref={resultRef} className="space-y-4 lg:sticky lg:top-4 lg:self-start">
              {error && (
                <div role="alert" className="flex items-start justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  <span>{error}</span>
                  <button type="button" onClick={clearError} className="rounded hover:text-destructive/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Dismiss error">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}

              {isGenerating ? (
                <Card className="beam-border rounded-xl">
                  <CardContent className="space-y-3 p-4 pt-4">
                    <div className="flex items-center justify-between gap-3 text-sm" role="status">
                      <span className="text-foreground">{statusText || 'Generating your lip sync video'}</span>
                      <span className="font-mono text-xs tabular text-muted-foreground">{formatElapsed(elapsed)}</span>
                    </div>
                    <div
                      className="flex max-h-[420px] items-center justify-center rounded-lg border border-border bg-muted/40"
                      style={{ aspectRatio: image?.aspectRatio ? String(image.aspectRatio) : '16 / 9' }}
                    >
                      {imagePreview && (
                        <img src={imagePreview} alt="" className="h-full w-full rounded-lg object-contain opacity-40" />
                      )}
                    </div>
                    <Progress value={progress} className="h-1.5" />
                    <p className="text-xs text-muted-foreground">
                      Lip sync takes a few minutes, longer for long audio and 2K.
                      {estimatedUsd !== null ? (
                        <> Estimated <span className="font-mono tabular">{formatUsd(estimatedUsd)}</span>.</>
                      ) : null}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      You can leave this page and follow it in{' '}
                      <Link to="/my-jobs" className="font-medium text-foreground underline-offset-4 hover:underline">My jobs</Link>.
                      The video goes to your gallery when it is ready.
                    </p>
                  </CardContent>
                </Card>
              ) : displayed ? (
                <motion.div
                  key={displayed.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2 }}
                >
                  <Card className={cn(!shownVideo && 'border-success/40')}>
                    <CardContent className="space-y-4 p-4 pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
                          <Play className={cn('h-4 w-4', shownVideo ? 'text-muted-foreground' : 'text-success')} />
                          {shownVideo ? 'Lip sync video' : 'Your lip sync video'}
                        </h2>
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" onClick={() => handleDownload(displayed)}>
                            <Download className="mr-1 h-4 w-4" />
                            Download
                          </Button>
                          {shownVideo ? (
                            <Button size="sm" variant="outline" onClick={() => setShownVideo(null)}>
                              <X className="mr-1 h-4 w-4" />
                              Close
                            </Button>
                          ) : (
                            <Button size="sm" variant="outline" onClick={startOver}>
                              <RotateCcw className="mr-1 h-4 w-4" />
                              Start over
                            </Button>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center justify-center">
                        <VideoPlayer
                          src={displayed.url}
                          poster={displayed.thumbnailUrl}
                          showDownload={false}
                          className="border border-border"
                        />
                      </div>
                      <div className="flex flex-wrap gap-4 font-mono text-xs tabular text-muted-foreground">
                        {displayed.durationSeconds ? <span>Duration {displayed.durationSeconds.toFixed(1)}s</span> : null}
                        {displayed.width && displayed.height ? <span>{displayed.width}x{displayed.height}</span> : null}
                        {displayed.fileSizeBytes ? (
                          <span>{(displayed.fileSizeBytes / 1024 / 1024).toFixed(2)} MB</span>
                        ) : null}
                        <span>{formatLocalDate(displayed.createdAt)}</span>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ) : (
                <Card>
                  <CardContent className="flex min-h-[320px] flex-col items-center justify-center p-6 text-center">
                    <AudioLines className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                    <p className="mt-3 text-base font-semibold">Your video appears here</p>
                    <p className="mt-1 max-w-sm text-sm text-muted-foreground">
                      Add a portrait and a voice track, pick a resolution and generate.
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>

        {/* Recent */}
        <div>
          <div className="mt-12">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
              <h2 className="text-base font-semibold tracking-tight">Recent lip sync videos</h2>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/gallery?tab=videos">All videos</Link>
              </Button>
            </div>
            {isLoadingGallery && videos.length === 0 ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4" aria-busy="true">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Card key={i} className="overflow-hidden">
                    <Skeleton className="aspect-video w-full rounded-none" />
                    <CardContent className="flex items-center justify-between gap-2 p-2">
                      <Skeleton className="h-3 w-16" />
                      <Skeleton className="h-8 w-16" />
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : videos.length === 0 ? (
              <div className="flex flex-col items-center rounded-xl border border-dashed border-border py-12 text-center">
                <AudioLines className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p className="mt-3 text-base font-semibold">No lip sync videos yet</p>
                <p className="mt-1 text-sm text-muted-foreground">Your first one will show up here.</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {videos.map((video) => (
                  <Card
                    key={video.id}
                    className="group overflow-hidden transition-colors duration-150 hover:border-foreground/20"
                  >
                    <button
                      type="button"
                      onClick={() => showRecent(video)}
                      className="relative block aspect-video w-full bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                      aria-label="Play video"
                    >
                      {video.thumbnailUrl ? (
                        <img src={video.thumbnailUrl} alt="" loading="lazy" className="h-full w-full object-cover" />
                      ) : (
                        <span className="flex h-full w-full items-center justify-center">
                          <Play className="h-8 w-8 text-muted-foreground" />
                        </span>
                      )}
                      {video.durationSeconds ? (
                        <span className="absolute bottom-2 right-2 rounded bg-background/80 px-1.5 py-0.5 font-mono text-[10px] tabular text-foreground">
                          {formatSeconds(video.durationSeconds)}
                        </span>
                      ) : null}
                    </button>
                    <CardContent className="flex items-center justify-between gap-2 p-2">
                      <p className="font-mono text-[10px] tabular text-muted-foreground">{formatLocalDate(video.createdAt)}</p>
                      <div className="flex gap-1">
                        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => handleDownload(video)} aria-label="Download">
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(video.id)} aria-label="Delete">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>


      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete this lip sync video?"
        description="The video is removed from your gallery. This cannot be undone."
        confirmText="Delete"
        variant="destructive"
        onConfirm={async () => {
          if (deleteId !== null) {
            if (shownVideo?.id === deleteId) setShownVideo(null);
            await deleteVideo(deleteId);
          }
          setDeleteId(null);
        }}
      />
    </>
  );
}

export default LipSyncPage;
