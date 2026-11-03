import { useState, useCallback, useEffect, useRef } from 'react';
import { Download, Upload, Loader2, Play, Trash2, RefreshCcw, Settings2, ChevronDown, X, FileVideo } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { studioEase } from '@/components/motion';
import { cn } from '@/lib/utils';
import { useSubtitleStore } from '@/stores/subtitleStore';
import { formatUsd } from '@/stores/pricingStore';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { SEO } from '@/components/SEO';
import { formatLocalDate } from '@/lib/dateUtils';
import { MediaDropzone } from '@/components/media/MediaDropzone';

// Allowed colors for FAL auto-subtitle API
const SUBTITLE_COLORS = [
  { value: 'white', label: 'White', hex: '#FFFFFF' },
  { value: 'black', label: 'Black', hex: '#000000' },
  { value: 'red', label: 'Red', hex: '#FF0000' },
  { value: 'green', label: 'Green', hex: '#00FF00' },
  { value: 'blue', label: 'Blue', hex: '#0000FF' },
  { value: 'yellow', label: 'Yellow', hex: '#FFFF00' },
  { value: 'orange', label: 'Orange', hex: '#FFA500' },
  { value: 'purple', label: 'Purple', hex: '#800080' },
  { value: 'pink', label: 'Pink', hex: '#FFC0CB' },
  { value: 'brown', label: 'Brown', hex: '#A52A2A' },
  { value: 'gray', label: 'Gray', hex: '#808080' },
  { value: 'cyan', label: 'Cyan', hex: '#00FFFF' },
  { value: 'magenta', label: 'Magenta', hex: '#FF00FF' },
];

// Whether a video file is portrait (taller than wide by a clear margin), read
// in the browser from its metadata; false when it cannot be read in time.
function isVerticalVideo(file: File): Promise<boolean> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement('video');
    const done = (value: boolean) => {
      window.clearTimeout(timer);
      URL.revokeObjectURL(url);
      video.removeAttribute('src');
      resolve(value);
    };
    const timer = window.setTimeout(() => done(false), 4000);
    video.preload = 'metadata';
    video.onloadedmetadata = () => done(video.videoHeight > video.videoWidth * 1.1);
    video.onerror = () => done(false);
    video.src = url;
  });
}

// Subtitle positions
const SUBTITLE_POSITIONS = [
  { value: 'top', label: 'Top' },
  { value: 'center', label: 'Center' },
  { value: 'bottom', label: 'Bottom' },
];

// Font families available in FAL
const FONT_FAMILIES = [
  { value: 'Montserrat', label: 'Montserrat' },
  { value: 'Arial', label: 'Arial' },
  { value: 'Helvetica', label: 'Helvetica' },
  { value: 'Roboto', label: 'Roboto' },
  { value: 'Open Sans', label: 'Open Sans' },
  { value: 'Poppins', label: 'Poppins' },
];

// Languages for transcription
const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'it', label: 'Italian' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'hi', label: 'Hindi' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'zh', label: 'Chinese' },
];

const settingsHeadingClass = 'text-xs font-medium text-muted-foreground';

// Seconds since `active` turned on, for the plain status line while working.
function useElapsed(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return;
    }
    const started = Date.now();
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [active]);
  return seconds;
}

function formatElapsed(total: number): string {
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

// Color selector component with visual swatches
function ColorSelect({
  value,
  onChange,
  label,
  disabled,
  allowNone = false,
}: {
  value: string | null;
  onChange: (value: string | null) => void;
  label: string;
  disabled?: boolean;
  allowNone?: boolean;
}) {
  const selectedColor = SUBTITLE_COLORS.find(c => c.value === value);

  return (
    <div className="space-y-2">
      <Label className={settingsHeadingClass}>{label}</Label>
      <Select
        value={value || 'none'}
        onValueChange={(v) => onChange(v === 'none' ? null : v)}
        disabled={disabled}
      >
        <SelectTrigger>
          <SelectValue>
            {value ? (
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded-full border border-border ring-2 ring-primary ring-offset-1 ring-offset-background"
                  style={{ backgroundColor: selectedColor?.hex || '#FFFFFF' }}
                />
                {selectedColor?.label || value}
              </div>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {allowNone && (
            <SelectItem value="none">
              <div className="flex items-center gap-2">
                <div className="h-4 w-4 rounded-full border border-dashed border-muted-foreground" />
                None
              </div>
            </SelectItem>
          )}
          {SUBTITLE_COLORS.map((color) => (
            <SelectItem key={color.value} value={color.value}>
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    'h-4 w-4 rounded-full border border-border',
                    color.value === value && 'ring-2 ring-primary ring-offset-1 ring-offset-background'
                  )}
                  style={{ backgroundColor: color.hex }}
                />
                {color.label}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function SubtitlesPage() {
  const [showSettings, setShowSettings] = useState(false);

  const {
    uploadedVideo,
    uploadPreview,
    isUploading,
    uploadProgress,
    fontColor,
    setFontColor,
    strokeColor,
    setStrokeColor,
    highlightColor,
    setHighlightColor,
    backgroundColor,
    setBackgroundColor,
    position,
    setPosition,
    fontSize,
    setFontSize,
    fontName,
    setFontName,
    fontWeight,
    setFontWeight,
    strokeWidth,
    setStrokeWidth,
    yOffset,
    setYOffset,
    wordsPerSubtitle,
    setWordsPerSubtitle,
    enableAnimation,
    setEnableAnimation,
    language,
    setLanguage,
    isGenerating,
    generatedVideo,
    transcript,
    error,
    generationProgress,
    generationStatus,
    uploadVideo,
    generateSubtitles,
    clearUpload,
    clearError,
    reset,
    videos,
    isLoadingGallery,
    loadGallery,
    deleteVideo,
  } = useSubtitleStore();

  const positionTouched = useRef(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const elapsed = useElapsed(isGenerating);

  // Load gallery on mount
  useEffect(() => {
    loadGallery();
  }, [loadGallery]);

  const handleFileSelect = useCallback(async (file: File) => {
    setFileError(null);
    const allowedTypes = ['video/mp4', 'video/webm', 'video/quicktime'];
    if (!file.type.startsWith('video/') || !allowedTypes.includes(file.type)) {
      setFileError('This file type is not supported. Use an MP4, WebM or MOV video.');
      return;
    }

    // Check file size (500MB max)
    if (file.size > 500 * 1024 * 1024) {
      setFileError('This video is larger than 500 MB. Trim or compress it and try again.');
      return;
    }

    // Vertical video: the platform UI (buttons, caption, CTA) covers the
    // bottom third, so captions default to the centre unless the user chose.
    if (!positionTouched.current) {
      setPosition((await isVerticalVideo(file)) ? 'center' : 'bottom');
    }

    try {
      await uploadVideo(file);
    } catch {
      // Error handled by store
    }
  }, [uploadVideo, setPosition]);

  const handleGenerate = async () => {
    if (!uploadedVideo || isGenerating) return;
    clearError();
    try {
      await generateSubtitles();
    } catch {
      // Error handled by store
    }
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
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  return (
    <>
      <SEO title="Subtitles - Auto-Subtitle Videos" description="Automatically add subtitles to your videos using AI" />
      <div className="flex min-h-[calc(100vh-4rem)] flex-col">
        {/* Header and upload panel */}
        <div className="flex-shrink-0 pb-8">
          <header className="mb-6">
            <h1 className="text-balance text-2xl font-semibold tracking-tight">Subtitles</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload a video and get it back with subtitles burned in from an automatic transcript.
            </p>
          </header>

          <div className="max-w-3xl">
                {/* The dropzone draws its own frame; the card frame only wraps an uploaded video. */}
                <div className={cn('space-y-6', uploadedVideo && 'rounded-xl border border-border bg-card p-4 sm:p-6', isGenerating && 'beam-border')}>
                  {/* Upload Area */}
                  {!uploadedVideo ? (
                    <MediaDropzone
                      kinds={['video']}
                      accept="video/mp4,video/webm,video/quicktime"
                      title="Add a video"
                      icon={Upload}
                      label="Upload Video"
                      hint="MP4, WebM or MOV, max 500MB"
                      className="min-h-[250px] p-8"
                      onFiles={(files) => handleFileSelect(files[0])}
                    >
                      {isUploading ? (
                        <div className="w-full max-w-xs space-y-3" role="status">
                          <p className="text-sm text-muted-foreground">
                            Uploading video, <span className="tabular">{Math.round(uploadProgress)}%</span>
                          </p>
                          <Progress value={uploadProgress} />
                        </div>
                      ) : undefined}
                    </MediaDropzone>
                  ) : (
                    <div className="space-y-4">
                      {/* Video Preview */}
                      <div className="relative">
                        <div className="aspect-video overflow-hidden rounded-xl border border-border bg-black">
                          {uploadPreview && (
                            <video
                              src={uploadPreview}
                              className="h-full w-full object-contain"
                              controls
                            />
                          )}
                        </div>
                        <Button
                          type="button"
                          variant="glass"
                          size="icon"
                          aria-label="Remove video"
                          disabled={isGenerating}
                          onClick={(e) => {
                            e.stopPropagation();
                            clearUpload();
                          }}
                          className="absolute right-2 top-2 h-8 w-8"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>

                      {/* Video Info */}
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                        <div className="flex min-w-0 items-center gap-2">
                          <FileVideo className="h-4 w-4 shrink-0" />
                          <span className="truncate">{uploadedVideo.filename}</span>
                        </div>
                        <div className="font-mono tabular">
                          {uploadedVideo.durationSeconds.toFixed(1)}s, {formatUsd(uploadedVideo.estimatedUsd)}
                        </div>
                      </div>
                    </div>
                  )}

                  {fileError && !uploadedVideo && (
                    <p role="alert" className="text-xs text-destructive">{fileError}</p>
                  )}

                  {/* Subtitle Settings */}
                  {uploadedVideo && (
                    <Collapsible open={showSettings} onOpenChange={setShowSettings}>
                      <CollapsibleTrigger asChild>
                        <Button variant="ghost" className="w-full justify-between text-muted-foreground">
                          <span className="flex items-center gap-2 text-sm">
                            <Settings2 className="h-4 w-4" />
                            Subtitle settings
                          </span>
                          <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${showSettings ? 'rotate-180' : ''}`} />
                        </Button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-6 pt-4">
                        {/* Color Settings */}
                        <div className="space-y-4">
                          <h4 className={settingsHeadingClass}>Colours</h4>
                          <div className="grid grid-cols-2 gap-4">
                            <ColorSelect
                              value={fontColor}
                              onChange={(v) => setFontColor(v || 'white')}
                              label="Text colour"
                              disabled={isGenerating}
                            />
                            <ColorSelect
                              value={strokeColor}
                              onChange={(v) => setStrokeColor(v || 'black')}
                              label="Stroke colour"
                              disabled={isGenerating}
                            />
                            <ColorSelect
                              value={highlightColor}
                              onChange={setHighlightColor}
                              label="Highlight colour"
                              disabled={isGenerating}
                              allowNone
                            />
                            <ColorSelect
                              value={backgroundColor}
                              onChange={setBackgroundColor}
                              label="Background colour"
                              disabled={isGenerating}
                              allowNone
                            />
                          </div>
                        </div>

                        {/* Font Settings */}
                        <div className="space-y-4">
                          <h4 className={settingsHeadingClass}>Font</h4>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Font family</Label>
                              <Select
                                value={fontName}
                                onValueChange={setFontName}
                                disabled={isGenerating}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {FONT_FAMILIES.map((f) => (
                                    <SelectItem key={f.value} value={f.value}>
                                      {f.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Font weight</Label>
                              <Select
                                value={fontWeight}
                                onValueChange={setFontWeight}
                                disabled={isGenerating}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="normal">Normal</SelectItem>
                                  <SelectItem value="bold">Bold</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Font size (<span className="tabular">{fontSize}px</span>)</Label>
                              <Slider
                                value={[fontSize]}
                                onValueChange={(v) => setFontSize(v[0])}
                                min={20}
                                max={200}
                                step={5}
                                disabled={isGenerating}
                              />
                            </div>
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Stroke width (<span className="tabular">{strokeWidth}px</span>)</Label>
                              <Slider
                                value={[strokeWidth]}
                                onValueChange={(v) => setStrokeWidth(v[0])}
                                min={0}
                                max={10}
                                step={1}
                                disabled={isGenerating}
                              />
                            </div>
                          </div>
                        </div>

                        {/* Position Settings */}
                        <div className="space-y-4">
                          <h4 className={settingsHeadingClass}>Position</h4>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Position</Label>
                              <Select
                                value={position}
                                onValueChange={(v) => {
                                  positionTouched.current = true;
                                  setPosition(v);
                                }}
                                disabled={isGenerating}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {SUBTITLE_POSITIONS.map((p) => (
                                    <SelectItem key={p.value} value={p.value}>
                                      {p.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Vertical offset (<span className="tabular">{yOffset}px</span>)</Label>
                              <Slider
                                value={[yOffset]}
                                onValueChange={(v) => setYOffset(v[0])}
                                min={0}
                                max={200}
                                step={5}
                                disabled={isGenerating}
                              />
                            </div>
                          </div>
                        </div>

                        {/* Animation & Language Settings */}
                        <div className="space-y-4">
                          <h4 className={settingsHeadingClass}>Animation and language</h4>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Language</Label>
                              <Select
                                value={language}
                                onValueChange={setLanguage}
                                disabled={isGenerating}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {LANGUAGES.map((l) => (
                                    <SelectItem key={l.value} value={l.value}>
                                      {l.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-2">
                              <Label className={settingsHeadingClass}>Words per subtitle (<span className="tabular">{wordsPerSubtitle}</span>)</Label>
                              <Slider
                                value={[wordsPerSubtitle]}
                                onValueChange={(v) => setWordsPerSubtitle(v[0])}
                                min={1}
                                max={10}
                                step={1}
                                disabled={isGenerating}
                              />
                            </div>
                          </div>
                          <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                              <Label>Word animation</Label>
                              <p className="text-xs text-muted-foreground">
                                Highlight words as they're spoken
                              </p>
                            </div>
                            <Switch
                              checked={enableAnimation}
                              onCheckedChange={setEnableAnimation}
                              disabled={isGenerating}
                            />
                          </div>
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  )}

                  {/* Error Display */}
                  {error && (
                    <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                      {error}
                    </div>
                  )}

                  {/* Generation progress */}
                  {isGenerating && (
                    <div className="space-y-2" role="status">
                      <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>{generationStatus || 'Adding subtitles'}</span>
                        <span className="font-mono tabular">
                          {generationProgress}%, {formatElapsed(elapsed)}
                        </span>
                      </div>
                      <Progress value={generationProgress} />
                    </div>
                  )}

                  {/* Generate Button */}
                  {uploadedVideo && (
                    <div className="flex gap-3">
                      <Button
                        className="flex-1"
                        size="lg"
                        onClick={handleGenerate}
                        disabled={isGenerating}
                      >
                        {isGenerating ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Adding subtitles
                          </>
                        ) : (
                          <>
                            <Play className="h-4 w-4" />
                            Add subtitles, {formatUsd(uploadedVideo.estimatedUsd)}
                          </>
                        )}
                      </Button>
                      {(isGenerating || generatedVideo) && (
                        <Button variant="outline" size="lg" onClick={reset} aria-label="Start over" title="Start over">
                          <RefreshCcw className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  )}
                </div>
          </div>
        </div>

        {/* Generated Video */}
        {generatedVideo && (
          <div className="pb-8">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, ease: studioEase }}
              className="max-w-3xl"
            >
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-semibold">Subtitled video</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-center">
                    <VideoPlayer
                      src={generatedVideo.url}
                      poster={generatedVideo.thumbnailUrl}
                      className="border border-border"
                    />
                  </div>

                  {/* Transcript */}
                  {transcript && (
                    <div className="space-y-2">
                      <Label className={settingsHeadingClass}>Transcript</Label>
                      <div className="max-h-[200px] overflow-y-auto rounded-lg border border-border bg-secondary/40 p-3 text-sm">
                        {transcript}
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-between">
                    <div className="font-mono text-xs tabular text-muted-foreground">
                      {generatedVideo.durationSeconds && (
                        <span>{generatedVideo.durationSeconds.toFixed(1)}s</span>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDownload(generatedVideo.url, generatedVideo.filename)}
                    >
                      <Download className="h-4 w-4" />
                      Download
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        )}

        {/* Gallery Section */}
        <div className="flex-1 pb-8">
          <div>
            <h2 className="mb-4 text-base font-semibold tracking-tight">Your subtitled videos</h2>

            {isLoadingGallery ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4" aria-busy="true">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Card key={i} className="overflow-hidden">
                    <Skeleton className="aspect-video w-full rounded-none" />
                    <CardContent className="space-y-1.5 p-2">
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-2.5 w-16" />
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : videos.length === 0 ? (
              <div className="flex flex-col items-center rounded-xl border border-dashed border-border py-12 text-center">
                <FileVideo className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p className="mt-3 text-base font-semibold">No subtitled videos yet</p>
                <p className="mt-1 text-sm text-muted-foreground">Videos you subtitle are kept here.</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
                {videos.map((video) => (
                  <Card key={video.id} className="group overflow-hidden transition-colors duration-150 hover:border-foreground/20">
                    <div className="relative aspect-video bg-muted">
                      {video.thumbnailUrl ? (
                        <img
                          src={video.thumbnailUrl}
                          alt="Subtitled video"
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <Play className="h-8 w-8 text-muted-foreground" />
                        </div>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center gap-2 bg-background/60 transition-opacity duration-150 focus-within:opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                        <Button
                          size="icon"
                          variant="glass"
                          aria-label="Download video"
                          onClick={() => handleDownload(video.url, video.filename)}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="destructive"
                          aria-label="Delete video"
                          onClick={() => setPendingDelete(video.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <CardContent className="p-2">
                      <p className="truncate text-xs text-muted-foreground">
                        {video.transcript || 'No transcript'}
                      </p>
                      <p className="font-mono text-[10px] tabular text-muted-foreground">
                        {formatLocalDate(video.createdAt)}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Delete this subtitled video?"
        description="The video and its transcript are removed from your library. This cannot be undone."
        confirmText="Delete"
        variant="destructive"
        onConfirm={async () => {
          if (pendingDelete !== null) await deleteVideo(pendingDelete);
        }}
      />
    </>
  );
}
