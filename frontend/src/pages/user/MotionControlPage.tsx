import { useState, useCallback, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Download,
  RotateCcw,
  Check,
  ImageIcon,
  Video,
  ArrowLeft,
  ArrowRight,
  X,
  Play,
  ScanFace,
  Info,
  Loader2,
} from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  MOTION_CONTROL_KEYS,
  MOTION_CONTROL_MAX_SECONDS,
  formatUsd,
  motionControlSeconds,
  usePricingStore,
} from '@/stores/pricingStore';
import type { MotionControlTier } from '@/stores/pricingStore';
import { useVideoStore } from '@/stores/videoStore';
import { videoApi } from '@/api/video';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { VideoUploader } from '@/components/video/VideoUploader';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import type { Asset } from '@/api/assets';
import { RecastStudio } from '@/components/recast/RecastStudio';
import { SEO } from '@/components/SEO';
import { cn } from '@/lib/utils';

// Wizard steps
const STEPS = [
  { id: 1, label: 'Character image' },
  { id: 2, label: 'Motion reference' },
  { id: 3, label: 'Generate' },
] as const;

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

// The three Kling tiers (backend fal_client.MOTION_CONTROL_TIERS). Prices come
// from the live price table, never from here.
const MODEL_TIERS: { id: MotionControlTier; label: string; description: string; faceLock: boolean }[] = [
  {
    id: 'v3-standard',
    label: 'Kling V3 Standard',
    description: 'Latest Kling generation at a lower cost. The default, ideal for iterating.',
    faceLock: true,
  },
  {
    id: 'v3-pro',
    label: 'Kling V3 Pro',
    description: 'Highest quality motion and detail on Kling V3. Best for finished work.',
    faceLock: true,
  },
  {
    id: 'v2.6',
    label: 'Kling v2.6 Budget',
    description: 'Earlier generation, the most budget-friendly. No face lock.',
    faceLock: false,
  },
];

const ORIENTATIONS: { id: 'video' | 'image'; label: string; description: string }[] = [
  {
    id: 'video',
    label: 'Match the video',
    description: 'Follows the reference video. Better for complex, full-body motion.',
  },
  {
    id: 'image',
    label: 'Match the image',
    description: 'Keeps the framing of your character image. Better for camera-movement-led shots.',
  },
];

// Scene prompts in the spirit of fal's Kling Motion Control examples.
const PROMPT_EXAMPLES = [
  'A barista rapping to camera, sharp head nods and hand chops on the beat',
  'A fitness coach erupting in a celebration, wide eyes, a roar and fist pumps',
  'A presenter delivering a dramatic monologue, a hand to the temple and a resolute chin lift',
  'A podcaster beatboxing to camera, rapid mouth movements and rhythmic head bobs',
];

// Backend limits (app/routers/video.py and the fal schemas).
const PROMPT_MAX_CHARS = 2000;
const REFERENCE_MIN_SECONDS = 3;
// Applied inward, as the server does: a length must sit inside the range by
// this margin, never on its edge.
const DURATION_SLACK_SECONDS = 0.05;
const secondsText = (s: number) => s.toFixed(2).replace(/\.?0+$/, '');
const FACE_MAX_MB = 20;
const STILL_ACCEPT = 'image/jpeg,image/png,image/webp,image/avif,.jpg,.jpeg,.png,.webp,.avif';
const STILL_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/avif'];
const STILL_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.avif'];

// A still the page accepts: by type, or by extension when the browser reports none.
function stillImageError(file: File): string | null {
  const name = file.name.toLowerCase();
  if (file.type === 'image/gif' || name.endsWith('.gif')) {
    return 'GIF is not supported. Save the frame you want as PNG or JPG and upload that.';
  }
  if (STILL_TYPES.includes(file.type) || STILL_EXTENSIONS.some((ext) => name.endsWith(ext))) return null;
  return 'Please select a JPG, PNG, WebP or AVIF image';
}

// Why a measured reference cannot be used with an orientation, or null. Mirrors
// check_orientation_duration in app/routers/video.py.
const KLING_STILL_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/avif'];

function stillAssetProblem(asset: Asset, minSide: number, maxMb?: number): string | null {
  if (!KLING_STILL_TYPES.includes(asset.contentType ?? '')) return 'Needs a JPG, PNG or WebP image';
  const w = asset.width ?? 0;
  const h = asset.height ?? 0;
  if (!w || !h) return 'Size unknown';
  if (Math.min(w, h) < minSide) return `${w}x${h}, needs at least ${minSide} px a side`;
  const ratio = w / h;
  if (ratio < 0.4 || ratio > 2.5) return `Aspect ratio ${ratio.toFixed(2)}, needs 0.4 to 2.5`;
  if (maxMb && asset.fileSizeBytes > maxMb * 1024 * 1024) return `Larger than ${maxMb} MB`;
  return null;
}

function referenceAssetProblem(asset: Asset): string | null {
  const seconds = asset.durationSeconds ?? 0;
  if (seconds < REFERENCE_MIN_SECONDS + DURATION_SLACK_SECONDS) return `${secondsText(seconds)}s, needs more than ${REFERENCE_MIN_SECONDS}s`;
  if (seconds > MOTION_CONTROL_MAX_SECONDS.video - DURATION_SLACK_SECONDS) return `${secondsText(seconds)}s, needs under ${MOTION_CONTROL_MAX_SECONDS.video}s`;
  const w = asset.width ?? 0;
  const h = asset.height ?? 0;
  if (w && h && (Math.min(w, h) < 340 || Math.max(w, h) > 3850)) return `${w}x${h}, each side must be 340 to 3850 px`;
  return null;
}

function referenceDurationProblem(orientation: 'video' | 'image', seconds: number | null): string | null {
  if (seconds === null) return null;
  const cap = MOTION_CONTROL_MAX_SECONDS[orientation];
  const longest = MOTION_CONTROL_MAX_SECONDS.video;
  const shown = secondsText(seconds);
  if (seconds > cap - DURATION_SLACK_SECONDS) {
    if (orientation === 'image' && seconds <= longest - DURATION_SLACK_SECONDS) {
      return `This reference is ${shown} seconds. Match the image accepts clips shorter than ${cap} seconds: switch to Match the video (under ${longest} seconds) or trim the clip.`;
    }
    return `This reference is ${shown} seconds. Motion Control accepts clips shorter than ${cap} seconds here. Trim the clip.`;
  }
  if (seconds < REFERENCE_MIN_SECONDS + DURATION_SLACK_SECONDS) {
    return `This reference is ${shown} seconds. It needs to be longer than ${REFERENCE_MIN_SECONDS} seconds.`;
  }
  return null;
}

// Step indicator: a calm numbered row. Done steps are muted with a check and
// can be revisited; the current step is in the foreground.
function StepIndicator({
  currentStep,
  onSelect,
  locked,
}: {
  currentStep: number;
  onSelect: (step: 1 | 2 | 3) => void;
  locked: boolean;
}) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2" aria-label="Steps">
      {STEPS.map((step, index) => {
        const isCompleted = currentStep > step.id;
        const isCurrent = currentStep === step.id;
        const canGoBack = isCompleted && !locked;

        return (
          <li key={step.id} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => canGoBack && onSelect(step.id)}
              disabled={!canGoBack}
              aria-current={isCurrent ? 'step' : undefined}
              className={cn(
                'flex items-center gap-2 rounded-md px-1.5 py-1 text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default',
                isCurrent ? 'font-medium text-foreground' : 'text-muted-foreground',
                canGoBack && 'hover:text-foreground',
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-full border text-[11px] tabular',
                  isCurrent ? 'border-primary text-foreground' : 'border-border text-muted-foreground',
                )}
              >
                {isCompleted ? <Check className="h-3.5 w-3.5" /> : step.id}
              </span>
              <span className={cn(!isCurrent && 'hidden sm:inline')}>{step.label}</span>
              {isCompleted && <span className="sr-only">(done)</span>}
            </button>
            {index < STEPS.length - 1 && <span aria-hidden="true" className="h-px w-6 bg-border sm:w-10" />}
          </li>
        );
      })}
    </ol>
  );
}

// Input guidance from fal's Kling Motion Control docs.
function InputTips({ title, tips }: { title: string; tips: string[] }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-3">
      <p className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Info className="h-3.5 w-3.5" />
        {title}
      </p>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {tips.map((tip) => (
          <li key={tip} className="flex gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/60" />
            <span>{tip}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Section label used in the settings card.
function SettingLabel({ children, hint }: { children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <p className="text-xs font-medium text-muted-foreground">{children}</p>
      {hint && <p className="text-[11px] tabular text-muted-foreground">{hint}</p>}
    </div>
  );
}

// Step 1: Source Image Upload
function SourceImageStep({
  sourceImage,
  sourceImagePreview,
  onImageChange,
  onPickAsset,
  isPreparing,
  onNext,
}: {
  sourceImage: string | null;
  sourceImagePreview: string | null;
  onImageChange: (image: string | null, preview?: string | null, file?: File | null) => void;
  // A character image picked from My Assets (read by id on the server).
  onPickAsset: (asset: Asset) => void | Promise<void>;
  isPreparing: boolean;
  onNext: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const processFile = useCallback((file: File): Promise<string | null> => {
    return new Promise((resolve) => {
      if (file.size > 25 * 1024 * 1024) {
        setError('File size must be less than 25MB');
        resolve(null);
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        const result = e.target?.result;
        if (typeof result !== 'string') {
          setError('Failed to read file');
          resolve(null);
          return;
        }
        resolve(result);
      };
      reader.onerror = () => {
        setError('Failed to read file');
        resolve(null);
      };
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFileSelect = useCallback(async (file: File) => {
    const typeError = stillImageError(file);
    if (typeError) {
      setError(typeError);
      return;
    }

    const dataUrl = await processFile(file);
    if (dataUrl) {
      // Pass the file so it can be uploaded later to get a hosted URL
      // FAL's Kling Video API requires hosted URLs, not base64 data URLs
      onImageChange(dataUrl, dataUrl, file);
      setError(null);
    }
  }, [processFile, onImageChange]);

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">Character image</h2>
        <p className="text-sm text-muted-foreground">
          The character, outfit and background in your video come from this image.
        </p>
      </div>

      {/* Upload Area */}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <MediaDropzone
            kinds={['image']}
            accept={STILL_ACCEPT}
            icon={ImageIcon}
            label="Character image"
            hint="JPG, PNG, WebP or AVIF, max 25 MB"
            title="Add a character image"
            description="One clear character, at least 340 px a side. Large photos are scaled to fit."
            disabled={isPreparing}
            unusableReason={(asset) => stillAssetProblem(asset, 340)}
            onFiles={(files) => handleFileSelect(files[0])}
            onAssets={(assets) => onPickAsset(assets[0])}
            className="min-h-[300px] p-6"
          >
            {sourceImagePreview ? (
              <div className="relative w-full h-full">
                <img
                  src={sourceImagePreview}
                  alt="Source"
                  className="w-full h-full object-contain rounded-lg max-h-[350px]"
                />
                <Button
                  type="button"
                  variant="glass"
                  size="icon"
                  onClick={(e) => {
                    e.stopPropagation();
                    onImageChange(null, null, null);
                  }}
                  onKeyDown={(e) => e.stopPropagation()}
                  className="absolute right-2 top-2 h-8 w-8"
                  aria-label="Remove image"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : undefined}
          </MediaDropzone>
        </CardContent>
      </Card>

      <InputTips
        title="For the best result"
        tips={[
          'One clear character with visible body proportions, not cut off or covered by objects.',
          'The character should fill more than 5 percent of the image; a person far in the background will not work.',
          'At least 340 px on each side, aspect ratio between 2:5 and 5:2. Larger photos are scaled to fit.',
        ]}
      />

      {/* Error Display */}
      {error && (
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Next Button */}
      <div className="flex justify-end">
        <Button
          size="lg"
          onClick={onNext}
          disabled={!sourceImage}
          className="w-full sm:w-auto sm:min-w-[200px]"
        >
          {sourceImage ? (
            <>
              Next: motion reference
              <ArrowRight className="h-4 w-4" />
            </>
          ) : (
            'Add an image to continue'
          )}
        </Button>
      </div>
    </div>
  );
}

// Step 2: Motion Reference
function MotionReferenceStep({
  motionReferenceFile,
  motionReferencePreview,
  motionReferenceUrl,
  onFileChange,
  onUrlChange,
  onPickAsset,
  fromAssets,
  onNext,
  onBack,
}: {
  motionReferenceFile: File | null;
  motionReferencePreview: string | null;
  motionReferenceUrl: string | null;
  onFileChange: (file: File | null) => void;
  onUrlChange: (url: string | null) => void;
  // A motion reference picked from My Assets (read by id on the server).
  onPickAsset: (asset: Asset) => void;
  fromAssets: boolean;
  onNext: () => void;
  onBack: () => void;
}) {
  const hasMotionReference = motionReferenceFile !== null || motionReferenceUrl !== null;

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">Motion reference</h2>
        <p className="text-sm text-muted-foreground">
          Your character performs the movement, timing and expression of this video.
        </p>
      </div>

      {/* Video Uploader */}
      <VideoUploader
        videoFile={motionReferenceFile}
        videoPreview={motionReferencePreview}
        videoUrl={motionReferenceUrl}
        onFileChange={onFileChange}
        onUrlChange={onUrlChange}
        maxSizeMB={100}
        sourceLabel={fromAssets ? 'Video from My Assets' : undefined}
        pickerTitle="Add a motion reference"
        pickerDescription={`A person moving, ${REFERENCE_MIN_SECONDS} to ${MOTION_CONTROL_MAX_SECONDS.video} seconds.`}
        unusableReason={referenceAssetProblem}
        onAssets={(assets) => onPickAsset(assets[0])}
      />

      <InputTips
        title="A good reference"
        tips={[
          'One realistic person, head and body in frame for the whole clip, feet visible when the legs move.',
          'A static camera and one continuous shot: no cuts, and no one crossing in front of the person.',
          'Fitted clothing reads best; loose clothing and props hide the joints the motion is read from.',
          `${REFERENCE_MIN_SECONDS} to ${MOTION_CONTROL_MAX_SECONDS.video} seconds long (up to ${MOTION_CONTROL_MAX_SECONDS.image} seconds if you keep the framing of your image).`,
          'Its speech, singing or ambient sound can be carried into your video.',
        ]}
      />

      {/* Status */}
      <div className="flex items-center gap-2 text-xs">
        <span className={cn('h-2 w-2 rounded-full', hasMotionReference ? 'bg-success' : 'bg-muted-foreground/40')} />
        <span className={hasMotionReference ? 'text-foreground' : 'text-muted-foreground'}>
          Motion reference {hasMotionReference ? 'ready' : 'required'}
        </span>
      </div>

      {/* Navigation Buttons */}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <Button variant="outline" size="lg" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button
          size="lg"
          onClick={onNext}
          disabled={!hasMotionReference}
          className="sm:min-w-[200px]"
        >
          {hasMotionReference ? (
            <>
              Next: settings
              <ArrowRight className="h-4 w-4" />
            </>
          ) : (
            'Add a reference to continue'
          )}
        </Button>
      </div>
    </div>
  );
}

export function MotionControlPage() {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [faceLocalError, setFaceLocalError] = useState<string | null>(null);
  // One character (Kling motion control) or several (MiniMax H3 Max Recast).
  const [mode, setMode] = useState<'single' | 'multi'>('single');
  const location = useLocation();
  const navigate = useNavigate();

  // Get store state and actions
  const {
    sourceImage,
    sourceImagePreview,
    motionReferenceUrl,
    motionReferenceFile,
    motionReferencePreview,
    motionReferenceAssetId,
    characterOrientation,
    modelTier,
    prompt,
    keepOriginalSound,
    faceImage,
    isUploadingFace,
    faceError,
    generatedVideo,
    error,
    isGenerating,
    generationProgress,
    generationStatus,
    isUploading,
    setSourceImage,
    setMotionReferenceUrl,
    setMotionReferenceFile,
    setCharacterOrientation,
    setModelTier,
    setPrompt,
    setKeepOriginalSound,
    uploadFaceImage,
    clearFaceImage,
    pickSourceImageAsset,
    selectMotionReferenceAsset,
    selectFaceAsset,
    generateVideo,
    clearError,
    reset,
  } = useVideoStore();

  // "Use in Motion Control" from My Assets passes the asset in the route state.
  useEffect(() => {
    const asset = (location.state as { asset?: Asset } | null)?.asset;
    if (!asset) return;
    if (asset.kind === 'video') {
      if (!referenceAssetProblem(asset)) {
        selectMotionReferenceAsset(asset);
      }
      setCurrentStep(sourceImage ? 2 : 1);
    } else if (asset.kind === 'image' && !stillAssetProblem(asset, 340)) {
      pickSourceImageAsset(asset);
    }
    navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const { getModelCost } = usePricingStore();

  // Length of the motion reference, read from its metadata in the browser.
  // Kept with the source it was measured from so a new reference starts unknown.
  const referenceSrc = motionReferencePreview || motionReferenceUrl;
  const [measured, setMeasured] = useState<{ src: string; seconds: number } | null>(null);
  useEffect(() => {
    if (!referenceSrc) return;
    const probe = document.createElement('video');
    probe.preload = 'metadata';
    probe.muted = true;
    const onLoaded = () => {
      if (Number.isFinite(probe.duration) && probe.duration > 0) {
        setMeasured({ src: referenceSrc, seconds: probe.duration });
      }
    };
    probe.addEventListener('loadedmetadata', onLoaded);
    probe.src = referenceSrc;
    return () => {
      probe.removeEventListener('loadedmetadata', onLoaded);
      probe.removeAttribute('src');
      probe.load();
    };
  }, [referenceSrc]);
  const referenceSeconds = measured && measured.src === referenceSrc ? measured.seconds : null;

  const tier = MODEL_TIERS.find((t) => t.id === modelTier) ?? MODEL_TIERS[0];
  const faceLockAvailable = tier.faceLock;
  const faceLockEnabled = faceLockAvailable && characterOrientation === 'video';
  const faceWillBeSent = faceLockEnabled && faceImage !== null;

  // The orientation caps the length (10 s matching the image, 30 s the video);
  // the server refuses a measured reference outside the limits, so does the page.
  const maxSeconds = MOTION_CONTROL_MAX_SECONDS[characterOrientation];
  const durationProblem = referenceDurationProblem(characterOrientation, referenceSeconds);

  // Priced per second of output on the chosen tier, which follows the
  // reference video. The server measures an uploaded file; a pasted link is
  // estimated at the orientation's maximum. fal bills the real output length.
  const perSecond = getModelCost(MOTION_CONTROL_KEYS[modelTier]);
  const isPastedLink = motionReferenceFile === null && motionReferenceUrl !== null && motionReferenceAssetId === null;
  const estimateSeconds = motionControlSeconds(characterOrientation, referenceSeconds);
  const upperSeconds = isPastedLink ? maxSeconds : estimateSeconds;
  const estimateUsd = perSecond !== undefined ? perSecond * estimateSeconds : undefined;
  const upperUsd = perSecond !== undefined ? perSecond * upperSeconds : undefined;

  const handleFacePick = async (file: File) => {
    const typeError = stillImageError(file);
    if (typeError) {
      setFaceLocalError(typeError);
      return;
    }
    if (file.size > FACE_MAX_MB * 1024 * 1024) {
      setFaceLocalError(`The face image must be under ${FACE_MAX_MB}MB`);
      return;
    }
    setFaceLocalError(null);
    await uploadFaceImage(file);
  };

  // Handle generate
  const handleGenerate = async () => {
    clearError();
    try {
      await generateVideo();
    } catch {
      // Error is handled in the store
    }
  };

  // Handle start over
  const handleStartOver = () => {
    reset();
    setFaceLocalError(null);
    setCurrentStep(1);
  };

  // Handle download
  const handleDownload = async () => {
    if (!generatedVideo) return;
    try {
      await videoApi.downloadVideo(generatedVideo.id, generatedVideo.filename);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const canGenerate =
    sourceImage !== null &&
    (motionReferenceUrl !== null || motionReferenceFile !== null) &&
    !isGenerating &&
    !isUploading &&
    !isUploadingFace &&
    durationProblem === null;

  const settingsLocked = isGenerating || isUploading || generatedVideo !== null;
  const elapsed = useElapsed(isGenerating || isUploading);

  // Each step starts at its top; the inputs of earlier steps stay in the store.
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
  }, [currentStep, mode]);
  const facePicker = useMediaPicker({
    kinds: ['image'],
    accept: STILL_ACCEPT,
    title: 'Add a face',
    description: `A clear, front-facing face, at least 300x300 px, up to ${FACE_MAX_MB} MB.`,
    disabled: !faceLockEnabled || isUploadingFace || settingsLocked,
    unusableReason: (asset) => stillAssetProblem(asset, 300, FACE_MAX_MB),
    onFiles: (files) => handleFacePick(files[0]),
    onAssets: (assets) => {
      setFaceLocalError(null);
      selectFaceAsset(assets[0]);
    },
  });
  const promptPlaceholder = faceLockEnabled && faceImage
    ? `${PROMPT_EXAMPLES[0]}. Mention @Element1 where the locked face belongs, or we add it for you.`
    : `For example: ${PROMPT_EXAMPLES[0]}`;

  return (
    <>
      <SEO
        title="Motion Control Video"
        description="Transfer the motion of any reference video onto your character with Kling V3 motion control. Upload a character image and a motion reference to create animated AI video, with the original audio carried through."
        keywords="AI video generator, motion control, motion transfer, Kling V3, Kling Video, image to video, AI animation, video generation"
        url="/motion-control"
      />
      <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="border-b border-border pb-5">
        <div className="flex flex-col gap-4">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-balance text-2xl font-semibold tracking-tight">Motion control</h1>
              <p className="mt-1 max-w-prose text-pretty text-sm text-muted-foreground">
                {mode === 'single'
                  ? 'Make your character perform the movement of any reference video, with Kling V3.'
                  : 'Replace up to four people in a video with your own photos, keeping every move and the original sound, with MiniMax H3 Max.'}
              </p>
            </div>
          <div role="tablist" aria-label="Number of characters" className="inline-flex gap-1 rounded-md border border-border bg-muted/60 p-1">
            {([
              { id: 'single', label: 'One character' },
              { id: 'multi', label: 'Several characters' },
            ] as const).map((m) => (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={mode === m.id}
                onClick={() => setMode(m.id)}
                disabled={isGenerating}
                className={cn(
                  'rounded px-3 py-1.5 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60',
                  mode === m.id ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
          </header>

          {/* Step Indicator */}
          {mode === 'single' && (
            <StepIndicator currentStep={currentStep} onSelect={setCurrentStep} locked={isGenerating || isUploading} />
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="py-6">
          {mode === 'multi' && (
            <div className="pb-8">
              <RecastStudio />
            </div>
          )}

          {/* Step 1: Source Image */}
          {mode === 'single' && currentStep === 1 && (
            <SourceImageStep
              sourceImage={sourceImage}
              sourceImagePreview={sourceImagePreview}
              onImageChange={setSourceImage}
              onPickAsset={pickSourceImageAsset}
              isPreparing={isUploading}
              onNext={() => setCurrentStep(2)}
            />
          )}

          {/* Step 2: Motion Reference */}
          {mode === 'single' && currentStep === 2 && (
            <MotionReferenceStep
              motionReferenceFile={motionReferenceFile}
              motionReferencePreview={motionReferencePreview}
              motionReferenceUrl={motionReferenceUrl}
              onFileChange={setMotionReferenceFile}
              onUrlChange={setMotionReferenceUrl}
              onPickAsset={selectMotionReferenceAsset}
              fromAssets={motionReferenceAssetId !== null}
              onNext={() => setCurrentStep(3)}
              onBack={() => setCurrentStep(1)}
            />
          )}

          {/* Step 3: Generate */}
          {mode === 'single' && currentStep === 3 && (
            <div className="max-w-4xl space-y-6 pb-8">
              {/* Back Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCurrentStep(2)}
                className="mb-4"
                disabled={isGenerating}
              >
                <ArrowLeft className="h-4 w-4" />
                Change motion reference
              </Button>

              {/* Preview Section */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Source Image Preview */}
                <Card>
                  <CardContent className="p-4">
                    <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-tight">
                      <ImageIcon className="h-4 w-4 text-muted-foreground" />
                      Character image
                    </h3>
                    <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg border border-border bg-muted">
                      {sourceImagePreview && (
                        <img
                          src={sourceImagePreview}
                          alt="Source"
                          className="w-full h-full object-contain"
                        />
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* Motion Reference Preview */}
                <Card>
                  <CardContent className="p-4">
                    <h3 className="mb-3 flex items-center justify-between gap-2 text-sm font-semibold tracking-tight">
                      <span className="flex items-center gap-2">
                        <Video className="h-4 w-4 text-muted-foreground" />
                        Motion reference
                      </span>
                      {referenceSeconds !== null && (
                        <span className="font-mono text-[11px] font-normal tabular text-muted-foreground">
                          {referenceSeconds.toFixed(1)}s
                        </span>
                      )}
                    </h3>
                    <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg border border-border bg-background">
                      {(motionReferencePreview || motionReferenceUrl) ? (
                        <video
                          key={motionReferencePreview || motionReferenceUrl || undefined}
                          src={motionReferencePreview || motionReferenceUrl || undefined}
                          className="w-full h-full object-contain"
                          controls
                          muted
                          loop
                          autoPlay
                          playsInline
                          onError={(e) => console.error('[Video] Load error:', e)}
                        />
                      ) : (
                        <p className="text-muted-foreground text-sm">No video selected</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Settings */}
              {!generatedVideo && (
                <Card>
                  <CardContent className="space-y-6 p-4 pt-4 sm:p-5 sm:pt-5">
                    {/* Model tier */}
                    <div>
                      <SettingLabel hint="estimated USD per second of video">Model</SettingLabel>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                        {MODEL_TIERS.map((t) => {
                          const price = getModelCost(MOTION_CONTROL_KEYS[t.id]);
                          const active = modelTier === t.id;
                          return (
                            <button
                              key={t.id}
                              type="button"
                              onClick={() => setModelTier(t.id)}
                              disabled={settingsLocked}
                              aria-pressed={active}
                              className={cn(
                                'rounded-md border px-3 py-2.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60',
                                active
                                  ? 'border-primary/60 bg-primary/10 text-foreground'
                                  : 'border-border bg-secondary/20 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                              )}
                            >
                              <span className="flex items-center justify-between gap-2">
                                <span className="text-sm font-medium text-foreground">{t.label}</span>
                                <span className="font-mono text-[10px] tabular text-muted-foreground">
                                  {price !== undefined ? `${formatUsd(price)}/s` : '\u00a0'}
                                </span>
                              </span>
                              <span className="mt-1 block text-xs text-muted-foreground">{t.description}</span>
                              {t.id === 'v3-standard' && (
                                <span className="mt-1.5 inline-block text-[11px] text-muted-foreground">
                                  Default
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Orientation */}
                    <div>
                      <SettingLabel>Character orientation</SettingLabel>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {ORIENTATIONS.map((o) => {
                          const active = characterOrientation === o.id;
                          return (
                            <button
                              key={o.id}
                              type="button"
                              onClick={() => setCharacterOrientation(o.id)}
                              disabled={settingsLocked}
                              aria-pressed={active}
                              className={cn(
                                'rounded-md border px-3 py-2.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60',
                                active
                                  ? 'border-primary/60 bg-primary/10 text-foreground'
                                  : 'border-border bg-secondary/20 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                              )}
                            >
                              <span className="flex items-center justify-between gap-2">
                                <span className="text-sm font-medium text-foreground">{o.label}</span>
                                <span className="font-mono text-[10px] tabular text-muted-foreground">
                                  up to {MOTION_CONTROL_MAX_SECONDS[o.id]}s
                                </span>
                              </span>
                              <span className="mt-1 block text-xs text-muted-foreground">{o.description}</span>
                            </button>
                          );
                        })}
                      </div>
                      {durationProblem && (
                        <p className="mt-2 rounded-lg border border-warning/30 bg-warning/10 p-2.5 text-xs text-warning">
                          {durationProblem}
                        </p>
                      )}
                    </div>

                    {/* Prompt */}
                    <div>
                      <SettingLabel hint={`${prompt.length}/${PROMPT_MAX_CHARS}`}>Scene prompt (optional)</SettingLabel>
                      <Textarea
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value.slice(0, PROMPT_MAX_CHARS))}
                        maxLength={PROMPT_MAX_CHARS}
                        placeholder={promptPlaceholder}
                        disabled={settingsLocked}
                        rows={3}
                        aria-label="Scene prompt"
                      />
                      <p className="mt-1.5 text-xs text-muted-foreground">
                        Describe who is performing and the key moves. It is optional, but it helps the model read the motion.
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {PROMPT_EXAMPLES.map((example) => (
                          <button
                            key={example}
                            type="button"
                            onClick={() => setPrompt(example)}
                            disabled={settingsLocked}
                            className="max-w-full truncate rounded-md border border-border bg-secondary/20 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors duration-150 hover:border-foreground/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                            title={example}
                          >
                            {example}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Original audio */}
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium">Keep original audio</p>
                        <p className="text-xs text-muted-foreground">
                          Carries the reference video's speech, singing or ambient sound into your video, in sync with the motion. Turn it off for a silent video.
                        </p>
                      </div>
                      <Switch
                        checked={keepOriginalSound}
                        onCheckedChange={setKeepOriginalSound}
                        disabled={settingsLocked}
                        aria-label="Keep original audio"
                      />
                    </div>

                    {/* Face lock (Kling V3 only) */}
                    {faceLockAvailable && (
                      <div className="rounded-lg border border-border bg-secondary/20 p-3">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                          <div
                            {...facePicker.dropProps}
                            className={cn(
                              'flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted',
                              facePicker.dragOver ? 'border-foreground/40' : 'border-border',
                            )}
                          >
                            {faceImage ? (
                              <img src={faceImage.preview} alt="Locked face" className="h-full w-full object-cover" />
                            ) : (
                              <ScanFace className="h-7 w-7 text-muted-foreground" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1 space-y-1.5">
                            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                              Face lock
                              <span className="text-[11px] font-normal text-muted-foreground">
                                Optional, Kling V3
                              </span>
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Upload a clear, front-facing photo of the face to keep the identity consistent in every frame.
                              At least 300x300 px, JPG, PNG, WebP or AVIF.
                            </p>
                            {!faceLockEnabled && (
                              <p className="text-xs text-warning">
                                Face lock only works with Match the video: Kling binds the face to the character as it follows the
                                reference video, and does not support it when the framing comes from your image.
                                {faceImage ? ' The uploaded face is not used unless you switch.' : ''}
                              </p>
                            )}
                            {faceWillBeSent && (
                              <p className="text-xs text-muted-foreground">
                                The face is referenced as <span className="font-mono text-foreground">@Element1</span>. If your
                                prompt does not mention it, we add it for you.
                              </p>
                            )}
                            {(faceLocalError || faceError) && (
                              <p className="text-xs text-destructive">{faceLocalError || faceError}</p>
                            )}
                            <div className="flex flex-wrap gap-2 pt-1">
                              {facePicker.dialog}
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={facePicker.open}
                                {...facePicker.dropProps}
                                disabled={!faceLockEnabled || isUploadingFace || settingsLocked}
                              >
                                {isUploadingFace ? (
                                  <>
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    Uploading
                                  </>
                                ) : (
                                  <>
                                    <ScanFace className="h-4 w-4 mr-1.5" />
                                    {faceImage ? 'Replace face' : 'Add face'}
                                  </>
                                )}
                              </Button>
                              {faceImage && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    clearFaceImage();
                                    setFaceLocalError(null);
                                  }}
                                  disabled={isUploadingFace || settingsLocked}
                                >
                                  <X className="h-4 w-4 mr-1" />
                                  Remove
                                </Button>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Generation Progress */}
              {(isGenerating || isUploading) && (
                <Card className="beam-border rounded-xl">
                  <CardContent className="p-4 space-y-3 pt-4">
                    <div className="flex items-center justify-between gap-3 text-sm" role="status">
                      <span className="text-foreground">
                        {isUploading ? 'Uploading your files' : generationStatus || 'Generating your video'}
                      </span>
                      <span className="font-mono text-xs tabular text-muted-foreground">{formatElapsed(elapsed)}</span>
                    </div>
                    <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg border border-border bg-muted/40">
                      {sourceImagePreview && (
                        <img src={sourceImagePreview} alt="" className="h-full w-full object-contain opacity-40" />
                      )}
                    </div>
                    <Progress value={generationProgress} className="h-1.5" />
                    <p className="text-xs text-muted-foreground">
                      Video generation usually takes 2 to 5 minutes. You can leave this page and follow it in{' '}
                      <Link to="/my-jobs" className="font-medium text-foreground underline-offset-4 hover:underline">
                        My jobs
                      </Link>
                      . The video goes to your gallery when it is ready.
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Generated Video Result */}
              {generatedVideo && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
                  <Card className="border-success/40">
                    <CardContent className="p-4 space-y-4 pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="flex items-center gap-2 text-base font-semibold tracking-tight">
                          <Play className="h-4 w-4 text-success" />
                          Generated video
                        </h3>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" onClick={handleDownload}>
                            <Download className="h-4 w-4" />
                            Download
                          </Button>
                          <Button variant="outline" size="sm" onClick={handleStartOver}>
                            <RotateCcw className="h-4 w-4" />
                            Start over
                          </Button>
                        </div>
                      </div>

                      <div className="flex items-center justify-center">
                        <VideoPlayer
                          src={generatedVideo.url}
                          poster={generatedVideo.thumbnailUrl}
                          showDownload={false}
                          className="border border-border"
                        />
                      </div>

                      {/* Video Info */}
                      <div className="flex flex-wrap gap-4 font-mono text-xs tabular text-muted-foreground">
                        <span>Model: {tier.label}</span>
                        {generatedVideo.durationSeconds && (
                          <span>Duration: {generatedVideo.durationSeconds.toFixed(1)}s</span>
                        )}
                        {generatedVideo.width && generatedVideo.height && (
                          <span>Resolution: {generatedVideo.width}x{generatedVideo.height}</span>
                        )}
                        {generatedVideo.fps && <span>FPS: {generatedVideo.fps}</span>}
                        {generatedVideo.fileSizeBytes && (
                          <span>Size: {(generatedVideo.fileSizeBytes / 1024 / 1024).toFixed(2)} MB</span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Error Display */}
              {error && (
                <div role="alert" className="flex items-start justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  <span>{error}</span>
                  <button type="button" onClick={clearError} className="rounded text-destructive hover:text-destructive/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Dismiss error">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}

              {/* Generate Button */}
              {!generatedVideo && (
                <div className="flex flex-col items-center gap-4">
                  <Button
                    size="xl"
                    onClick={handleGenerate}
                    disabled={!canGenerate}
                    className="w-full sm:w-auto sm:min-w-[250px]"
                  >
                    {isGenerating || isUploading ? (
                      <>
                        <Loader2 className="h-5 w-5 animate-spin" />
                        {isUploading ? 'Uploading' : 'Generating'}
                      </>
                    ) : (
                      'Generate video'
                    )}
                  </Button>

                  {/* Price */}
                  {perSecond !== undefined && estimateUsd !== undefined && upperUsd !== undefined && (
                    <div className="space-y-1 text-center font-mono text-xs tabular text-muted-foreground">
                      <p>
                        {tier.label}: {formatUsd(perSecond)} per second of video, up to{' '}
                        {maxSeconds} seconds
                      </p>
                      {isPastedLink ? (
                        <p>
                          Up to {formatUsd(upperUsd)}: a pasted link is estimated at {maxSeconds}{' '}
                          seconds and billed for the real length
                        </p>
                      ) : referenceSeconds !== null ? (
                        <p className="text-foreground">
                          {formatUsd(estimateUsd)} for this {estimateSeconds}-second reference
                          {' '}({formatUsd(perSecond)} x {estimateSeconds}s)
                        </p>
                      ) : (
                        <p>Up to {formatUsd(upperUsd)}, billed for the real length</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      </div>
    </>
  );
}

export default MotionControlPage;
