import { useState, useEffect, Fragment } from 'react';
import { Download, Wand2, Loader2, Play, Trash2, RefreshCcw, Settings2, ChevronDown, Film, Volume2, VolumeX, ImageIcon, X, Upload, Monitor, ArrowLeftRight, Music, Video, Plus, Layers, Clock, Eye } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { studioEase } from '@/components/motion';
import { cn } from '@/lib/utils';
import { useStoryStore } from '@/stores/storyStore';
import { usePricingStore, STORY_ENHANCE_KEY, formatUsd } from '@/stores/pricingStore';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { SEO } from '@/components/SEO';
import { formatLocalDate } from '@/lib/dateUtils';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { otherProviderChoices, CONTENT_FILTER_CODE } from '@/utils/errors';
import type { AssetKind } from '@/api/assets';
import {
  STORY_VIDEO_MODELS,
  STORY_VIDEO_MODEL_ORDER,
  storyAspectRatios,
  storyBillableSeconds,
  storyKeyframeIssue,
  storyRefName,
  storyReferenceTokenBudget,
  storyReferenceTokensKey,
  storyVideoRefKey,
  storyVideoRefSeconds,
  storyPreviewSettings,
  STORY_FILTER_SWITCH_ORDER,
  STORY_LONG_CLIP_SECONDS,
  STORY_MODE_HINTS,
  STORY_PREVIEW_MAX_SECONDS,
  STORY_PROMPT_MAX_CHARS,
  type StoryMode,
  type StoryVideoModel,
} from '@/api/story';

// Mode tab icons; labels and order come from the chosen model.
const MODE_ICONS: Record<StoryMode, typeof Film> = {
  'text-to-video': Monitor,
  'reference-to-video': ImageIcon,
  'image-to-video': ArrowLeftRight,
  keyframes: Layers,
};

// Soundtrack and reference audio take MP3 or WAV only.
const STORY_AUDIO_ACCEPT = 'audio/mpeg,audio/wav,audio/mp3';


// Subtitle colors
const SUBTITLE_COLORS = [
  { value: 'white', label: 'White', hex: '#FFFFFF' },
  { value: 'black', label: 'Black', hex: '#000000' },
  { value: 'yellow', label: 'Yellow', hex: '#FFFF00' },
  { value: 'red', label: 'Red', hex: '#FF0000' },
  { value: 'green', label: 'Green', hex: '#00FF00' },
  { value: 'blue', label: 'Blue', hex: '#0000FF' },
  { value: 'orange', label: 'Orange', hex: '#FFA500' },
  { value: 'purple', label: 'Purple', hex: '#800080' },
  { value: 'pink', label: 'Pink', hex: '#FFC0CB' },
  { value: 'cyan', label: 'Cyan', hex: '#00FFFF' },
];

const SUBTITLE_POSITIONS = ['top', 'center', 'bottom'];
const FONT_FAMILIES = ['Montserrat', 'Arial', 'Roboto', 'Poppins'];

// Shared treatment for the composer control row
const pillTriggerClass =
  'h-8 w-auto gap-1 rounded-md border border-border bg-secondary/50 px-3 text-xs text-foreground transition-colors hover:border-foreground/30';

// Minutes and seconds for the elapsed time of a running clip.
const formatElapsed = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

// Color selector
function ColorSelect({ value, onChange, label, disabled, allowNone = false }: {
  value: string | null; onChange: (v: string | null) => void; label: string; disabled?: boolean; allowNone?: boolean;
}) {
  const selected = SUBTITLE_COLORS.find(c => c.value === value);
  return (
    <div className="space-y-2">
      <Label className="text-xs font-medium text-muted-foreground">{label}</Label>
      <Select value={value || 'none'} onValueChange={(v) => onChange(v === 'none' ? null : v)} disabled={disabled}>
        <SelectTrigger>
          <SelectValue>
            {value ? (
              <div className="flex items-center gap-2">
                <div className="h-4 w-4 rounded-full border border-border" style={{ backgroundColor: selected?.hex || '#FFF' }} />
                {selected?.label || value}
              </div>
            ) : <span className="text-muted-foreground">None</span>}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {allowNone && (
            <SelectItem value="none">
              <div className="flex items-center gap-2"><div className="h-4 w-4 rounded-full border border-dashed border-muted-foreground" />None</div>
            </SelectItem>
          )}
          {SUBTITLE_COLORS.map((c) => (
            <SelectItem key={c.value} value={c.value}>
              <div className="flex items-center gap-2">
                <div
                  className={cn('h-4 w-4 rounded-full border border-border', c.value === value && 'ring-2 ring-primary ring-offset-1 ring-offset-background')}
                  style={{ backgroundColor: c.hex }}
                />
                {c.label}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// Drag-drop upload zone: click opens the media window (upload or My Assets),
// and a dropped or picked file goes to onFile.
function UploadZone({ label, kinds, accept, title, onFile, disabled, children, className = '' }: {
  label: string; kinds: AssetKind[]; accept?: string; title?: string; onFile: (f: File) => void; disabled?: boolean; children?: React.ReactNode; className?: string;
}) {
  const media = useMediaPicker({ kinds, accept, title, disabled, onFiles: (files) => onFile(files[0]) });

  return (
    <div
      className={cn(
        'group relative cursor-pointer rounded-xl border border-dashed bg-secondary/20 p-4 text-center transition-colors hover:border-foreground/30',
        media.dragOver ? 'border-foreground/40 bg-accent/40' : 'border-border',
        className,
      )}
      onClick={media.open}
      {...media.dropProps}
    >
      {children || (
        <div className="flex flex-col items-center gap-2 py-4">
          <Upload className="h-6 w-6 text-muted-foreground transition-colors group-hover:text-foreground" />
          <p className="text-sm text-muted-foreground">{label}</p>
        </div>
      )}
      {media.dialog}
    </div>
  );
}

// Frame upload (start/end)
function FrameUpload({ label, preview, onFile, onClear, disabled }: {
  label: string; preview: string | null; onFile: (f: File) => void; onClear: () => void; disabled?: boolean;
}) {
  if (preview) {
    return (
      <div className="relative aspect-[4/3] overflow-hidden rounded-xl border border-border bg-muted">
        <img src={preview} alt={label} className="h-full w-full object-cover" />
        <button
          onClick={(e) => { e.stopPropagation(); onClear(); }}
          aria-label={`Remove the ${label.toLowerCase()}`}
          className="absolute right-2 top-2 rounded-full bg-background/80 p-1 text-foreground transition-colors hover:bg-background"
          disabled={disabled}
        >
          <X className="h-4 w-4" />
        </button>
        <span className="absolute bottom-2 left-2 rounded-md bg-background/85 px-1.5 py-0.5 text-[11px] text-foreground">{label}</span>
      </div>
    );
  }
  return (
    <UploadZone label={label} kinds={['image']} title={`Add the ${label.toLowerCase()}`} onFile={onFile} disabled={disabled} className="aspect-[4/3]">
      <div className="flex h-full flex-col items-center justify-center gap-2">
        <Upload className="h-6 w-6 text-muted-foreground transition-colors group-hover:text-foreground" />
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </UploadZone>
  );
}

// Keyframe tile: image plus the time it is pinned to
function KeyframeCard({ index, preview, timeSeconds, maxSeconds, fps, onTime, onRemove, disabled }: {
  index: number; preview: string; timeSeconds: number | null; maxSeconds: number; fps: number;
  onTime: (seconds: number | null) => void; onRemove: () => void; disabled?: boolean;
}) {
  const shown = timeSeconds ?? (index === 0 ? 0 : null);
  return (
    <div className="group relative h-32 w-32 overflow-hidden rounded-xl border border-border bg-muted">
      <img src={preview} alt={`Keyframe ${index + 1}`} className="h-full w-full object-cover" />
      <span className="absolute left-1.5 top-1.5 rounded-md bg-background/80 px-1.5 py-0.5 font-mono text-[10px] text-foreground">
        K{index + 1}
      </span>
      <button
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remove keyframe ${index + 1}`}
        className="absolute right-1.5 top-1.5 rounded-full bg-background/80 p-1 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
      >
        <X className="h-3.5 w-3.5 text-foreground" />
      </button>
      <label
        className="absolute inset-x-1.5 bottom-1.5 flex items-center gap-1 rounded-md border border-border bg-background/85 px-1.5 py-1"
        title={shown !== null ? `Frame ${Math.round(shown * fps)} at ${fps} fps` : undefined}
      >
        <Clock className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={maxSeconds}
          step={0.5}
          value={timeSeconds ?? ''}
          placeholder={index === 0 ? '0' : ''}
          onChange={(e) => onTime(e.target.value === '' ? null : Number(e.target.value))}
          disabled={disabled}
          aria-label={`Keyframe ${index + 1} time in seconds`}
          className="w-full min-w-0 bg-transparent font-mono text-[11px] text-foreground outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
        <span className="font-mono text-[10px] text-muted-foreground">s</span>
      </label>
    </div>
  );
}

// The single-clip maker: the "Quick clip" tab of /stories. Story Room shots
// open here prefilled through useStoryStore().prefillFromShot.
export function QuickClip() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSubtitleSettings, setShowSubtitleSettings] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [deleting, setDeleting] = useState<{ id: number; prompt: string } | null>(null);

  const {
    videoModel, setVideoModel,
    mode, setMode,
    currentPrompt, setPrompt,
    originalPrompt, isEnhancing, contentType, setContentType,
    duration, setDuration, resolution, setResolution, aspectRatio, setAspectRatio,
    generateAudio, setGenerateAudio,
    startFrame, setStartFrame, clearStartFrame,
    endFrame, setEndFrame, clearEndFrame,
    refImages, addRefImage, removeRefImage,
    refVideos, addRefVideo, removeRefVideo,
    refAudios, addRefAudio, removeRefAudio,
    soundtrack, setSoundtrack, clearSoundtrack,
    keyframes, addKeyframe, removeKeyframe, setKeyframeTime,
    addSubtitles, setAddSubtitles,
    subtitleFontColor, setSubtitleFontColor,
    subtitleStrokeColor, setSubtitleStrokeColor,
    subtitleHighlightColor, setSubtitleHighlightColor,
    subtitleBackgroundColor, setSubtitleBackgroundColor,
    subtitlePosition, setSubtitlePosition,
    subtitleFontSize, setSubtitleFontSize,
    subtitleFontName, setSubtitleFontName,
    subtitleFontWeight, setSubtitleFontWeight,
    subtitleStrokeWidth, setSubtitleStrokeWidth,
    subtitleYOffset, setSubtitleYOffset,
    subtitleWordsPerSubtitle, setSubtitleWordsPerSubtitle,
    subtitleEnableAnimation, setSubtitleEnableAnimation,
    isGenerating, isUploading, generatedVideo, error, errorCode, generationProgress, generationStatus,
    isPreviewing, lastPreview,
    enhancePrompt, generateStory, clearError, reset,
    videos, isLoadingGallery, loadGallery, deleteVideo,
  } = useStoryStore();

  const { getModelCost } = usePricingStore();

  const modelConfig = STORY_VIDEO_MODELS[videoModel];
  const modeAspects = storyAspectRatios(videoModel, mode);

  // Price: USD per second for this model and resolution, times the length
  // ("auto" assumes the model's longest auto clip; fal bills the real length).
  const perSecond = getModelCost(`video:${videoModel}:${resolution}`);
  const billableSeconds = storyBillableSeconds(videoModel, duration);
  const isAutoDuration = duration === 'auto';
  // H3 Max reference mode: reference tokens beyond the allowance, estimated at
  // the worst case of the uploads and billed on what fal reports.
  const extraTokens = storyReferenceTokenBudget(videoModel, mode, refImages.length, refVideos.length, refAudios.length, resolution);
  const per1kTokens = extraTokens > 0 ? getModelCost(storyReferenceTokensKey(videoModel)) : 0;
  const tokensUsd = extraTokens > 0 && per1kTokens !== undefined
    ? Math.round((extraTokens / 1000) * per1kTokens * 1e4) / 1e4
    : 0;
  // Kling v4 and Seedance with reference videos: a per-second rate on the
  // input plus the output length. The server measures the uploads; until
  // then the page shows the longest inputs fal accepts.
  const videoRefSeconds = storyVideoRefSeconds(videoModel, mode, refVideos.length, billableSeconds);
  const videoRefRate = videoRefSeconds !== null ? getModelCost(storyVideoRefKey(videoModel, resolution)) : undefined;
  const rate = videoRefSeconds !== null ? videoRefRate : perSecond;
  const rateSeconds = videoRefSeconds ?? billableSeconds;
  const storyUsd = rate !== undefined && per1kTokens !== undefined
    ? rate * rateSeconds + tokensUsd
    : undefined;
  const isUpperBound = isAutoDuration || tokensUsd > 0 || videoRefSeconds !== null;
  const priceLabel = storyUsd === undefined
    ? null
    : `${isUpperBound ? 'up to ' : ''}${formatUsd(storyUsd)}`;

  // Preview: the family's cheapest resolution and a short length, priced
  // like any clip (null when it would be the same render as the final).
  const preview = storyPreviewSettings(videoModel, duration, resolution);
  const previewSeconds = preview ? Number(preview.duration) : 0;
  const previewRefSeconds = preview ? storyVideoRefSeconds(videoModel, mode, refVideos.length, previewSeconds) : null;
  const previewRate = preview
    ? getModelCost(previewRefSeconds !== null ? storyVideoRefKey(videoModel, preview.resolution) : `video:${videoModel}:${preview.resolution}`)
    : undefined;
  const previewTokens = preview ? storyReferenceTokenBudget(videoModel, mode, refImages.length, refVideos.length, refAudios.length, preview.resolution) : 0;
  const previewTokensUsd = previewTokens > 0 && per1kTokens !== undefined
    ? Math.round((previewTokens / 1000) * per1kTokens * 1e4) / 1e4
    : 0;
  const previewUsd = preview && previewRate !== undefined
    ? previewRate * (previewRefSeconds ?? previewSeconds) + previewTokensUsd
    : undefined;

  // After a content filter block: models from other providers that offer
  // this mode (siblings share their provider's filter).
  const filterSwitches = errorCode === CONTENT_FILTER_CODE
    ? otherProviderChoices(
        videoModel,
        STORY_FILTER_SWITCH_ORDER.map((id) => ({ id, provider: STORY_VIDEO_MODELS[id].provider })),
      )
        .filter((o) => STORY_VIDEO_MODELS[o.id].modes.some((m) => m.value === mode))
        .slice(0, 2)
    : [];
  const switchModel = (id: StoryVideoModel) => {
    setVideoModel(id);
    clearError();
  };

  const isLongClip = Number(duration) > STORY_LONG_CLIP_SECONDS;
  const showingPreview = !!generatedVideo && !!lastPreview && lastPreview.videoId === generatedVideo.id;

  // Enhancing the prompt is priced per run (story:prompt-enhance).
  const enhanceUsd = getModelCost(STORY_ENHANCE_KEY);

  const clipSeconds = Number(duration) || Number(modelConfig.defaultDuration);
  const keyframeIssue = mode === 'keyframes'
    ? (keyframes.length === 0
      ? 'Add at least one keyframe image'
      : storyKeyframeIssue(keyframes.map((k) => k.timeSeconds), clipSeconds, modelConfig.keyframesFps))
    : null;
  const missingInput =
    (mode === 'image-to-video' && (modelConfig.startRequired === false ? !startFrame && !endFrame : !startFrame)) ||
    (mode === 'reference-to-video' && modelConfig.requiresReference && refImages.length + refVideos.length + refAudios.length === 0) ||
    keyframeIssue !== null;

  useEffect(() => { loadGallery(); }, [loadGallery]);

  // Elapsed time while a clip is generating (counted in this tab).
  useEffect(() => {
    if (!isGenerating) {
      setElapsed(0);
      return;
    }
    const startedAt = Date.now();
    const t = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, [isGenerating]);
  const ratioParts = /^(\d+):(\d+)$/.exec(modeAspects ? aspectRatio : '');
  const placeholderRatio = ratioParts ? Number(ratioParts[1]) / Number(ratioParts[2]) : 16 / 9;

  const handleEnhancePrompt = async () => {
    if (!currentPrompt.trim() || isEnhancing) return;
    try { await enhancePrompt(); } catch { /* handled by store */ }
  };

  const handleGenerate = async () => {
    if (!currentPrompt.trim() || isGenerating) return;
    clearError();
    try { await generateStory(); } catch { /* handled by store */ }
  };

  const handlePreview = async () => {
    if (!currentPrompt.trim() || isGenerating || !preview) return;
    clearError();
    try { await generateStory({ preview: true }); } catch { /* handled by store */ }
  };

  // The final render: same prompt and settings, the preview's seed where the
  // family takes one. It is still a new take.
  const handleRenderFinal = async () => {
    if (!currentPrompt.trim() || isGenerating) return;
    clearError();
    try { await generateStory({ seed: lastPreview?.seed ?? null }); } catch { /* handled by store */ }
  };

  const handleDownload = async (url: string, filename: string) => {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch (err) { console.error('Download failed:', err); }
  };

  const hasPrompt = currentPrompt.trim().length > 0;

  return (
    <>
      <SEO title="Stories - AI Video Generator" description="Generate Hollywood-quality video stories with cinematic scenes, reels, ads, vlogs and more" />
      <div className="flex min-h-[calc(100vh-4rem)] flex-col">
        {/* Composer */}
        <div className="flex-shrink-0 px-4 pb-6 pt-4">
          <div>
            {/* Video model picker */}
            <div>
              <div className="mb-4 max-w-3xl">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Video model</p>
                <div role="radiogroup" aria-label="Video model" className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
                  {STORY_VIDEO_MODEL_ORDER.map((id) => {
                    const cfg = STORY_VIDEO_MODELS[id];
                    const isActive = videoModel === id;
                    const rate = getModelCost(`video:${id}:${isActive ? resolution : cfg.defaultResolution}`);
                    return (
                      <button
                        key={id}
                        role="radio"
                        aria-checked={isActive}
                        onClick={() => setVideoModel(id)}
                        disabled={isGenerating}
                        className={cn(
                          'flex min-w-0 flex-col items-start gap-0.5 rounded-xl border px-3 py-2.5 text-left transition-colors duration-200 disabled:opacity-60',
                          isActive
                            ? 'border-primary/60 bg-primary/10'
                            : 'border-border bg-secondary/30 hover:border-foreground/30',
                        )}
                      >
                        <span className={cn('block w-full truncate text-sm font-medium', isActive ? 'text-foreground' : 'text-muted-foreground')}>{cfg.label}</span>
                        <span className="block w-full truncate text-[11px] text-muted-foreground">{cfg.tagline}</span>
                        <span className={cn('font-mono text-[11px] tabular', isActive ? 'text-foreground' : 'text-muted-foreground')}>
                          {rate !== undefined ? `${formatUsd(rate)}/s` : ' '}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Mode Tabs */}
            <div>
              <div className="mb-6 flex justify-center">
                <div role="tablist" aria-label="Mode" className="inline-flex max-w-full flex-wrap items-center justify-center rounded-md border border-border bg-secondary/50 p-1">
                  {modelConfig.modes.map((m) => {
                    const Icon = MODE_ICONS[m.value];
                    const isActive = mode === m.value;
                    return (
                      <button
                        key={m.value}
                        role="tab"
                        aria-selected={isActive}
                        onClick={() => setMode(m.value)}
                        disabled={isGenerating}
                        className={`flex items-center gap-2 rounded px-4 py-2 text-xs transition-colors duration-150 ${
                          isActive
                            ? 'bg-background text-foreground shadow-card'
                            : 'text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {m.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              {STORY_MODE_HINTS[mode] && (
                <p className="-mt-3 mb-5 text-center text-xs text-muted-foreground">{STORY_MODE_HINTS[mode]}</p>
              )}
            </div>

            <div>
              {/* Start & end frame uploads */}
              {mode === 'image-to-video' && (
                <div className="mb-4 max-w-3xl">
                  <div className="grid grid-cols-2 gap-4">
                    <FrameUpload label="Start frame" preview={startFrame?.preview || null} onFile={setStartFrame} onClear={clearStartFrame} disabled={isGenerating} />
                    <FrameUpload label="End frame" preview={endFrame?.preview || null} onFile={setEndFrame} onClear={clearEndFrame} disabled={isGenerating} />
                  </div>
                  <p className="mt-2 text-center text-xs text-muted-foreground">
                    {modelConfig.startRequired === false
                      ? 'The model makes the motion into, out of or between the frames. Use either frame, or both.'
                      : 'The model makes the transition between the two frames. The end frame is optional.'}
                  </p>
                </div>
              )}

              {/* Soundtrack pinned to the clip (H3 Max, text and image modes) */}
              {modelConfig.soundtrack && (mode === 'text-to-video' || mode === 'image-to-video') && (
                <div className="mb-4 flex max-w-3xl flex-wrap items-center gap-2">
                  {soundtrack ? (
                    <div className="flex items-center gap-1.5 rounded-md border border-border bg-secondary/50 py-1 pl-2 pr-1 text-xs">
                      <Music className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="max-w-[160px] truncate">{soundtrack.file.name}</span>
                      <button onClick={clearSoundtrack} disabled={isGenerating} aria-label="Remove soundtrack" className="rounded p-0.5 hover:bg-destructive/20"><X className="h-3 w-3" /></button>
                    </div>
                  ) : (
                    <UploadZone label="" kinds={['audio']} accept={STORY_AUDIO_ACCEPT} title="Add a soundtrack" onFile={setSoundtrack} disabled={isGenerating} className="!border-1 !rounded-md !p-0 px-3 py-1">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground transition-colors group-hover:text-foreground"><Plus className="h-3.5 w-3.5" />Soundtrack</div>
                    </UploadZone>
                  )}
                  <span className="text-xs text-muted-foreground">Optional MP3 or WAV, at least 2s, replaces the generated sound</span>
                </div>
              )}

              {/* Keyframes (FLUX 3 Max) */}
              {mode === 'keyframes' && (
                <div className="mb-4 max-w-3xl">
                  <div className="mb-3 flex flex-wrap gap-3">
                    {keyframes.map((kf, i) => (
                      <KeyframeCard
                        key={kf.id}
                        index={i}
                        preview={kf.preview}
                        timeSeconds={kf.timeSeconds}
                        maxSeconds={clipSeconds}
                        fps={modelConfig.keyframesFps}
                        onTime={(s) => setKeyframeTime(kf.id, s)}
                        onRemove={() => removeKeyframe(kf.id)}
                        disabled={isGenerating}
                      />
                    ))}
                    {keyframes.length < modelConfig.maxKeyframes && (
                      <UploadZone label="" kinds={['image']} title="Add a keyframe" onFile={addKeyframe} disabled={isGenerating} className="h-32 w-32 !rounded-xl !p-0">
                        <div className="flex h-full flex-col items-center justify-center gap-1">
                          <Plus className="h-6 w-6 text-muted-foreground transition-colors group-hover:text-foreground" />
                          <span className="text-[11px] text-muted-foreground">Keyframe</span>
                        </div>
                      </UploadZone>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Pin up to {modelConfig.maxKeyframes} images to times between 0 and {clipSeconds}s ({modelConfig.keyframesFps} fps). The first starts at 0s.
                  </p>
                  {keyframes.length > 0 && keyframeIssue && (
                    <p className="mt-1 text-xs text-destructive">{keyframeIssue}</p>
                  )}
                </div>
              )}

              {/* Reference uploads (Characters & references / reference-to-video) */}
              {mode === 'reference-to-video' && (
                <div className="mb-4 max-w-3xl">
                  {/* Image uploads: clean grid */}
                  <div className="mb-3 flex flex-wrap gap-3">
                    {refImages.map((ref) => (
                      <div key={ref.id} className="group relative h-32 w-32 overflow-hidden rounded-xl border border-border bg-muted">
                        <img src={ref.preview} alt="" className="h-full w-full object-cover" />
                        <button
                          onClick={() => removeRefImage(ref.id)}
                          aria-label="Remove reference image"
                          className="absolute right-1.5 top-1.5 rounded-full bg-background/80 p-1 text-foreground opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                        <span className="absolute bottom-1.5 left-1.5 rounded-md bg-background/85 px-1.5 py-0.5 font-mono text-[10px] text-foreground">{storyRefName(videoModel, 'Image', refImages.indexOf(ref) + 1)}</span>
                      </div>
                    ))}
                    {refImages.length < modelConfig.maxRefImages && (
                      <UploadZone label="" kinds={['image']} title="Add a reference image" onFile={addRefImage} disabled={isGenerating} className="w-32 h-32 !rounded-xl !p-0">
                        <div className="flex h-full flex-col items-center justify-center gap-1">
                          <Plus className="h-6 w-6 text-muted-foreground transition-colors group-hover:text-foreground" />
                        </div>
                      </UploadZone>
                    )}
                  </div>

                  {/* Video and audio: compact inline row */}
                  <div className="flex flex-wrap items-center gap-2">
                    {refVideos.map((ref) => (
                      <div key={ref.id} className="group flex items-center gap-1.5 rounded-md border border-border bg-secondary/50 py-1 pl-2 pr-1 text-xs">
                        <Video className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="max-w-[80px] truncate">{ref.file.name}</span>
                        <button onClick={() => removeRefVideo(ref.id)} aria-label="Remove reference video" className="rounded p-0.5 hover:bg-destructive/20"><X className="h-3 w-3" /></button>
                      </div>
                    ))}
                    {refAudios.map((ref) => (
                      <div key={ref.id} className="group flex items-center gap-1.5 rounded-md border border-border bg-secondary/50 py-1 pl-2 pr-1 text-xs">
                        <Music className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="max-w-[80px] truncate">{ref.file.name}</span>
                        <button onClick={() => removeRefAudio(ref.id)} aria-label="Remove reference audio" className="rounded p-0.5 hover:bg-destructive/20"><X className="h-3 w-3" /></button>
                      </div>
                    ))}
                    {refVideos.length < modelConfig.maxRefVideos && (
                      <UploadZone label="" kinds={['video']} accept="video/mp4,video/quicktime" title="Add a reference video" onFile={addRefVideo} disabled={isGenerating} className="!border-1 !rounded-md !p-0 px-3 py-1">
                        <div className="flex items-center gap-1 text-xs text-muted-foreground transition-colors group-hover:text-foreground"><Plus className="h-3.5 w-3.5" />Video</div>
                      </UploadZone>
                    )}
                    {refAudios.length < modelConfig.maxRefAudios && (
                      <UploadZone label="" kinds={['audio']} accept={STORY_AUDIO_ACCEPT} title="Add reference audio" onFile={addRefAudio} disabled={isGenerating} className="!border-1 !rounded-md !p-0 px-3 py-1">
                        <div className="flex items-center gap-1 text-xs text-muted-foreground transition-colors group-hover:text-foreground"><Plus className="h-3.5 w-3.5" />Audio</div>
                      </UploadZone>
                    )}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {videoModel === 'h3-max'
                      ? `Name uploads in your prompt as Image 1, Video 1, Audio 1. Up to ${modelConfig.maxRefImages} images, ${modelConfig.maxRefVideos} videos and ${modelConfig.maxRefAudios} audio clips; videos and audio 2 to 15s each, 15s combined per kind.`
                      : videoModel === 'omni-flash'
                      ? `Name uploads in your prompt as <IMAGE_REF_0>, <VIDEO_REF_0> (counting from 0, in upload order). Up to ${modelConfig.maxRefImages} images and ${modelConfig.maxRefVideos} videos of at most 10s each.`
                      : modelConfig.maxRefAudios > 0
                      ? 'Use @Image1, @Video1, @Audio1 in your prompt to reference uploads'
                      : `Use @Image1, @Video1 in your prompt to reference uploads. Up to ${modelConfig.maxRefImages} images and ${modelConfig.maxRefVideos} videos (3 to 30s each, 30s combined).`}
                    {modelConfig.requiresReference && (modelConfig.maxRefAudios > 0 ? ' Add at least one upload.' : ' Add at least one image or video.')}
                    {extraTokens > 0 && per1kTokens !== undefined && ` Reference tokens beyond the included 4,096 (about four square images) are billed on actual use; the estimate allows up to ${formatUsd(tokensUsd)} for them.`}
                  </p>
                </div>
              )}

              {/* Main Input Card */}
              <div className="max-w-3xl">
                <div className={cn('rounded-xl', isGenerating && 'beam-border')}>
                  <div className="overflow-hidden rounded-xl border border-border bg-card">
                    {/* Prompt */}
                    <div className="relative">
                      <Textarea
                        placeholder={
                          mode === 'image-to-video'
                            ? 'Describe the motion between the two frames...'
                            : mode === 'reference-to-video'
                            ? (modelConfig.maxRefAudios > 0
                              ? `Describe the video using ${storyRefName(videoModel, 'Image', 1)}, ${storyRefName(videoModel, 'Video', 1)}, ${storyRefName(videoModel, 'Audio', 1)} references...`
                              : `Describe the video using ${storyRefName(videoModel, 'Image', 1)}, ${storyRefName(videoModel, 'Video', 1)} references...`)
                            : mode === 'keyframes'
                            ? 'Describe the motion that carries the video through your keyframes...'
                            : 'Describe the video you want to create...'
                        }
                        value={currentPrompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        className="min-h-[120px] resize-none rounded-none border-0 bg-transparent pr-24 text-base placeholder:text-muted-foreground/70 focus-visible:ring-0"
                        disabled={isGenerating}
                        maxLength={STORY_PROMPT_MAX_CHARS}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-2 top-2 gap-1.5 px-2.5"
                        onClick={handleEnhancePrompt}
                        disabled={!hasPrompt || isEnhancing || isGenerating}
                        title="Rewrite the prompt as a director would"
                      >
                        {isEnhancing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                        <span className="hidden sm:inline">{isEnhancing ? 'Enhancing' : 'Enhance'}</span>
                        {enhanceUsd !== undefined && (
                          <span className="font-mono text-[11px] tabular">{formatUsd(enhanceUsd)}</span>
                        )}
                      </Button>
                    </div>

                    {/* Toolbar */}
                    <div className="flex flex-wrap items-center gap-2 border-t border-border bg-secondary/20 px-3 py-2.5">
                      {/* Content Type */}
                      <Select value={contentType} onValueChange={setContentType} disabled={isGenerating}>
                        <SelectTrigger className={pillTriggerClass}>
                          <Film className="h-3.5 w-3.5 text-muted-foreground" />
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[
                            { value: 'cinematic', label: 'Cinematic' },
                            { value: 'pixar', label: 'Pixar / 3D' },
                            { value: 'anime', label: 'Anime' },
                            { value: 'marvel', label: 'Marvel / Hero' },
                            { value: 'fantasy', label: 'Fantasy' },
                            { value: 'horror', label: 'Horror' },
                            { value: 'reel', label: 'Reel' },
                            { value: 'story', label: 'Story' },
                            { value: 'ad', label: 'Ad' },
                            { value: 'meme', label: 'Meme' },
                            { value: 'vlog', label: 'Vlog' },
                            { value: 'narration', label: 'Narration' },
                            { value: 'music', label: 'Music Video' },
                            { value: 'documentary', label: 'Documentary' },
                            { value: 'product', label: 'Product' },
                          ].map((t) => (
                            <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>

                      {/* Aspect Ratio (hidden when the model follows the start image) */}
                      {modeAspects && (
                        <Select value={aspectRatio} onValueChange={setAspectRatio} disabled={isGenerating}>
                          <SelectTrigger className={pillTriggerClass} aria-label="Aspect ratio">
                            <Monitor className="h-3.5 w-3.5 text-muted-foreground" />
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {modeAspects.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      )}

                      {/* Resolution */}
                      <Select value={resolution} onValueChange={setResolution} disabled={isGenerating}>
                        <SelectTrigger className={pillTriggerClass} aria-label="Resolution">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {modelConfig.resolutions.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                        </SelectContent>
                      </Select>

                      {/* Duration */}
                      <Select value={duration} onValueChange={setDuration} disabled={isGenerating}>
                        <SelectTrigger className={pillTriggerClass} aria-label="Duration">
                          <SelectValue>{duration === 'auto' ? 'Auto' : `${duration}s`}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {modelConfig.durations.map((d, i) => {
                            const firstLong = Number(d) > STORY_LONG_CLIP_SECONDS
                              && !(Number(modelConfig.durations[i - 1]) > STORY_LONG_CLIP_SECONDS);
                            return (
                              <Fragment key={d}>
                                {firstLong && (
                                  <p className="px-2 pb-1 pt-2 text-[11px] text-muted-foreground">
                                    Over {STORY_LONG_CLIP_SECONDS}s: keep it simple. Complex scenes hold best near 5s.
                                  </p>
                                )}
                                <SelectItem value={d}>{d === 'auto' ? 'Auto' : `${d}s`}</SelectItem>
                              </Fragment>
                            );
                          })}
                        </SelectContent>
                      </Select>

                      {/* Audio toggle (models that generate sound) */}
                      {modelConfig.audio && (
                        <button
                          onClick={() => setGenerateAudio(!generateAudio)}
                          disabled={isGenerating}
                          aria-pressed={generateAudio}
                          className={`flex h-8 items-center gap-1 rounded-md border border-border bg-secondary/50 px-3 text-xs transition-colors hover:border-foreground/30 ${generateAudio ? 'text-foreground' : 'text-muted-foreground'}`}
                          title={generateAudio ? 'Audio on' : 'Audio off'}
                        >
                          {generateAudio ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
                          <span className="hidden sm:inline">{generateAudio ? 'On' : 'Off'}</span>
                        </button>
                      )}
                      {!modelConfig.audio && modelConfig.alwaysAudio && (
                        <span
                          className="flex h-8 items-center gap-1 rounded-md border border-border bg-secondary/30 px-3 text-xs text-muted-foreground"
                          title="Clips always include synchronized audio"
                        >
                          <Volume2 className="h-3.5 w-3.5" />
                          <span className="hidden sm:inline">Audio included</span>
                        </span>
                      )}

                      <div className="flex-1" />

                      {/* Preview: cheapest resolution, short length */}
                      {preview && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handlePreview}
                          disabled={!hasPrompt || isGenerating || missingInput}
                          className="h-8 gap-1.5 px-3"
                          title={`Checks composition and motion at ${preview.resolution}, ${preview.duration}s. The final render is a new take.`}
                        >
                          <Eye className="h-3.5 w-3.5" />
                          Preview
                          {previewUsd !== undefined && (
                            <span className="font-mono text-xs tabular opacity-75">{`${previewTokensUsd > 0 || previewRefSeconds !== null ? 'up to ' : ''}${formatUsd(previewUsd)}`}</span>
                          )}
                        </Button>
                      )}

                      {/* Generate button */}
                      <Button
                        size="sm"
                        onClick={handleGenerate}
                        disabled={!hasPrompt || isGenerating || missingInput}
                        className="h-8 gap-1.5 px-4"
                      >
                        {isGenerating ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Wand2 className="h-3.5 w-3.5" />
                        )}
                        {isGenerating ? 'Generating' : 'Generate'}
                        {priceLabel && <span className="font-mono text-xs tabular opacity-75">{priceLabel}</span>}
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Enhanced badge, price breakdown, char count */}
                <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    {originalPrompt && (
                      <Badge variant="outline">Prompt enhanced</Badge>
                    )}
                    {rate !== undefined && storyUsd !== undefined && (
                      <span className="font-mono text-xs tabular text-muted-foreground">
                        {videoRefSeconds !== null
                          ? `${formatUsd(rate)}/s x up to ${videoRefSeconds}s (reference videos plus output)`
                          : `${formatUsd(rate)}/s x ${billableSeconds}s`}
                        {tokensUsd > 0 && ` + up to ${formatUsd(tokensUsd)} reference tokens`}
                        {isAutoDuration
                          ? ` = up to ${formatUsd(storyUsd)}, billed for the actual length`
                          : tokensUsd > 0 || videoRefSeconds !== null
                          ? ` = up to ${formatUsd(storyUsd)}`
                          : ` = ${formatUsd(storyUsd)}`}
                      </span>
                    )}
                  </div>
                  <span className="font-mono text-xs tabular text-muted-foreground">{currentPrompt.length}/{STORY_PROMPT_MAX_CHARS}</span>
                </div>
                {isLongClip && (
                  <p className="mt-1 px-1 text-xs text-muted-foreground">
                    Long clip: complex scenes hold together best near 5s. Give each part of the clip its own beat (0-4s, 4-8s and so on); the enhancer writes them for you.
                  </p>
                )}
                {preview && (
                  <p className="mt-1 px-1 text-xs text-muted-foreground">
                    Preview renders at {preview.resolution} for up to {STORY_PREVIEW_MAX_SECONDS}s to check composition and motion. The final render is a new take, so details will differ.
                  </p>
                )}
              </div>

              {/* Advanced Settings (Subtitles) */}
              <div className="mt-4 max-w-3xl">
                <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="w-full justify-between text-muted-foreground">
                      <span className="flex items-center gap-2 text-xs font-medium"><Settings2 className="h-3.5 w-3.5" />Subtitle settings</span>
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${showAdvanced ? 'rotate-180' : ''}`} />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-4 pt-3">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label>Add subtitles</Label>
                        <p className="text-xs text-muted-foreground">
                          Auto-generate subtitles after video creation, billed by fal per minute
                        </p>
                      </div>
                      <Switch checked={addSubtitles} onCheckedChange={setAddSubtitles} disabled={isGenerating} />
                    </div>

                    {addSubtitles && (
                      <Collapsible open={showSubtitleSettings} onOpenChange={setShowSubtitleSettings}>
                        <CollapsibleTrigger asChild>
                          <Button variant="outline" size="sm" className="w-full justify-between">
                            <span className="text-xs font-medium">Customize subtitles</span>
                            <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${showSubtitleSettings ? 'rotate-180' : ''}`} />
                          </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="space-y-4 pt-4">
                          <div className="grid grid-cols-2 gap-4">
                            <ColorSelect value={subtitleFontColor} onChange={(v) => setSubtitleFontColor(v || 'white')} label="Text color" disabled={isGenerating} />
                            <ColorSelect value={subtitleStrokeColor} onChange={(v) => setSubtitleStrokeColor(v || 'black')} label="Stroke color" disabled={isGenerating} />
                            <ColorSelect value={subtitleHighlightColor} onChange={(v) => setSubtitleHighlightColor(v || 'purple')} label="Highlight color" disabled={isGenerating} />
                            <ColorSelect value={subtitleBackgroundColor} onChange={(v) => setSubtitleBackgroundColor(v || 'none')} label="Background color" disabled={isGenerating} allowNone />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className="text-xs font-medium text-muted-foreground">Font family</Label>
                              <Select value={subtitleFontName} onValueChange={setSubtitleFontName} disabled={isGenerating}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>{FONT_FAMILIES.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}</SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-2">
                              <Label className="text-xs font-medium text-muted-foreground">Font weight</Label>
                              <Select value={subtitleFontWeight} onValueChange={setSubtitleFontWeight} disabled={isGenerating}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="normal">Normal</SelectItem>
                                  <SelectItem value="bold">Bold</SelectItem>
                                  <SelectItem value="black">Black</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className="text-xs font-medium text-muted-foreground">Font size ({subtitleFontSize}px)</Label>
                              <Slider value={[subtitleFontSize]} onValueChange={(v) => setSubtitleFontSize(v[0])} min={20} max={150} step={5} disabled={isGenerating} />
                            </div>
                            <div className="space-y-2">
                              <Label className="text-xs font-medium text-muted-foreground">Stroke width ({subtitleStrokeWidth}px)</Label>
                              <Slider value={[subtitleStrokeWidth]} onValueChange={(v) => setSubtitleStrokeWidth(v[0])} min={0} max={10} step={1} disabled={isGenerating} />
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className="text-xs font-medium text-muted-foreground">Position</Label>
                              <Select value={subtitlePosition} onValueChange={setSubtitlePosition} disabled={isGenerating}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>{SUBTITLE_POSITIONS.map((p) => <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>)}</SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-2">
                              <Label className="text-xs font-medium text-muted-foreground">Vertical offset ({subtitleYOffset}px)</Label>
                              <Slider value={[subtitleYOffset]} onValueChange={(v) => setSubtitleYOffset(v[0])} min={-200} max={200} step={5} disabled={isGenerating} />
                            </div>
                          </div>
                          <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Words per subtitle ({subtitleWordsPerSubtitle})</Label>
                            <Slider value={[subtitleWordsPerSubtitle]} onValueChange={(v) => setSubtitleWordsPerSubtitle(v[0])} min={1} max={12} step={1} disabled={isGenerating} />
                          </div>
                          <div className="flex items-center justify-between">
                            <div className="space-y-0.5"><Label>Word animation</Label><p className="text-xs text-muted-foreground">Karaoke-style highlight</p></div>
                            <Switch checked={subtitleEnableAnimation} onCheckedChange={setSubtitleEnableAnimation} disabled={isGenerating} />
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              </div>

              {/* Error */}
              {error && (
                <div className="mt-4 max-w-3xl">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                    {error}
                    {filterSwitches.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {filterSwitches.map((o) => (
                          <Button key={o.id} variant="outline" size="sm" className="h-7 text-xs" onClick={() => switchModel(o.id)}>
                            Switch to {STORY_VIDEO_MODELS[o.id].label}
                          </Button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Progress */}
              {isGenerating && (
                <div className="mt-4 max-w-3xl space-y-2" aria-live="polite">
                  <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                    <span>{isUploading ? 'Uploading references' : `${isPreviewing ? 'Preview: ' : ''}${generationStatus}`}</span>
                    <span className="shrink-0 font-mono tabular">
                      {formatElapsed(elapsed)} elapsed, <span className="text-foreground">{generationProgress}%</span>
                    </span>
                  </div>
                  <Progress value={generationProgress} />
                </div>
              )}

              {/* Reset button when generating or video exists */}
              {(isGenerating || generatedVideo) && (
                <div className="mt-3 flex max-w-3xl justify-start">
                  <Button variant="outline" size="sm" onClick={reset}><RefreshCcw className="h-4 w-4" />New video</Button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Space for the clip while it generates, in its aspect ratio */}
        {isGenerating && !generatedVideo && (
          <div className="px-4 pb-8">
            <div
              className="beam-border flex w-full max-w-4xl items-center justify-center rounded-xl border border-border bg-secondary/20"
              style={{ aspectRatio: placeholderRatio, maxWidth: placeholderRatio < 1 ? 360 : undefined }}
            >
              <p className="px-4 text-center text-sm text-muted-foreground">
                {isPreviewing ? 'Rendering the preview' : 'Rendering the clip'}
              </p>
            </div>
          </div>
        )}

        {/* Generated Video */}
        {generatedVideo && (
          <div className="px-4 pb-8">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.25, ease: studioEase }}
              className="max-w-4xl"
            >
              <VideoPlayer src={generatedVideo.url} poster={generatedVideo.thumbnailUrl} className="border border-border" showDownload={false} />
              <div className="mt-4 flex flex-col items-start justify-between gap-3 px-1 sm:flex-row sm:items-center">
                <div className="flex items-center gap-2">
                  {showingPreview && <Badge variant="outline">Preview</Badge>}
                  {generatedVideo.durationSeconds && <Badge variant="outline" className="font-mono tabular">{generatedVideo.durationSeconds.toFixed(1)}s</Badge>}
                  {generatedVideo.width && generatedVideo.height && <Badge variant="outline" className="font-mono tabular">{generatedVideo.width}x{generatedVideo.height}</Badge>}
                  {generatedVideo.hasSubtitles > 0 && <Badge variant="success">Subtitled</Badge>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {showingPreview && (
                    <Button size="sm" onClick={handleRenderFinal} disabled={isGenerating || missingInput}>
                      {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                      {isGenerating ? 'Rendering' : 'Render final'}
                      {priceLabel && <span className="font-mono text-xs tabular opacity-75">{priceLabel}</span>}
                    </Button>
                  )}
                  <Button size="sm" variant={showingPreview ? 'outline' : 'default'} onClick={() => handleDownload(generatedVideo.url, generatedVideo.filename)}>
                    <Download className="h-4 w-4" />Download video
                  </Button>
                </div>
              </div>
              {showingPreview && (
                <p className="mt-2 px-1 text-xs text-muted-foreground">
                  This preview checks composition and motion. Render final uses the same prompt at {resolution}, {duration === 'auto' ? 'auto length' : `${duration}s`}
                  {modelConfig.takesSeed ? ' and the same seed' : ''}; it is a new take, so details will differ.
                </p>
              )}
            </motion.div>
          </div>
        )}

        {/* Gallery */}
        <div className="flex-1 px-4 pb-8">
          <div className="max-w-6xl">
            <div className="mb-4">
              <h2 className="text-base font-semibold">Your clips</h2>
            </div>
            {isLoadingGallery && videos.length === 0 ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5" aria-busy="true" aria-label="Loading clips">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="overflow-hidden rounded-xl border border-border">
                    <Skeleton className="aspect-[9/16] w-full rounded-none" />
                    <div className="space-y-1.5 p-2">
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-2.5 w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : videos.length === 0 ? (
              <div className="flex flex-col items-center rounded-xl border border-dashed border-border py-12 text-center">
                <Film className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p className="mt-3 text-base font-semibold">No clips yet</p>
                <p className="mt-1 text-sm text-muted-foreground">Clips you generate appear here.</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
                {videos.map((video) => (
                  <Card key={video.id} className="group overflow-hidden transition-colors duration-150 hover:border-foreground/20">
                    <div className="relative aspect-[9/16] bg-muted">
                      {video.thumbnailUrl ? (
                        <img src={video.thumbnailUrl} alt={video.prompt} loading="lazy" className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center"><Play className="h-8 w-8 text-muted-foreground" /></div>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center gap-2 bg-background/60 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:bg-transparent [@media(hover:none)]:opacity-100 [@media(hover:none)]:items-end [@media(hover:none)]:justify-end [@media(hover:none)]:p-2">
                        <Button size="icon" variant="glass" aria-label="Download clip" onClick={() => handleDownload(video.url, video.filename)}><Download className="h-4 w-4" /></Button>
                        <Button size="icon" variant="destructive" aria-label="Delete clip" onClick={() => setDeleting({ id: video.id, prompt: video.prompt })}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    </div>
                    <CardContent className="p-2">
                      <p className="truncate text-xs text-muted-foreground">{video.prompt}</p>
                      <p className="font-mono text-[10px] tabular text-muted-foreground">{formatLocalDate(video.createdAt)}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
        <ConfirmDialog
          open={!!deleting}
          onOpenChange={(open) => !open && setDeleting(null)}
          title="Delete this clip?"
          description={`The clip "${(deleting?.prompt ?? '').slice(0, 80)}" is deleted from your library.`}
          confirmText="Delete"
          variant="destructive"
          onConfirm={async () => {
            if (deleting) await deleteVideo(deleting.id);
          }}
        />
      </div>
    </>
  );
}
