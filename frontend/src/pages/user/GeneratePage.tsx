import { useState, useMemo, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Download, ChevronDown, Check, Copy, Wand2, Loader2, MoreHorizontal, Split } from 'lucide-react';
import { motion } from 'motion/react';
import { formatLocalDate } from '@/lib/dateUtils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { studioEase } from '@/components/motion';
import { cn } from '@/lib/utils';
import { useElapsedSeconds, formatElapsed, ratioToCss } from '@/components/generate';
import { useGenerationStore, modelSettings } from '@/stores/generationStore';
import { usePricingStore, imageKey, editKey, formatUsd } from '@/stores/pricingStore';
import { AddTextDialog } from '@/components/text-overlay/AddTextDialog';
import { generateApi } from '@/api/generate';
import { getErrorMessage } from '@/utils/errors';
import { useQualityConfig } from '@/components/quality/QualityBadge';
import { ImageQuality } from '@/components/quality/ImageQuality';
import { fixResolution } from '@/api/quality';
import type { GeneratedImage } from '@/types';

// FAL Models with their capabilities. maxImages: images one request returns
// (the estimate uses the same number).
const MODELS = [
  { value: 'blackforestlabs/flux-3/klein/text-to-image', label: 'Flux 3 Klein', shortLabel: 'Klein', group: 'flux3' },
  { value: 'fal-ai/z-image/turbo/lora', label: 'Z-Image Turbo', shortLabel: 'Z-Image', group: 'zimage', supportsLora: true },
  { value: 'blackforestlabs/flux-3/text-to-image', label: 'Flux 3', shortLabel: 'Flux 3', group: 'flux3', maxImages: 1 },
  { value: 'openai/gpt-image-2.5/sunburst/text-to-image', label: 'GPT Image 2.5', shortLabel: 'GPT 2.5', group: 'gpt' },
  { value: 'google/nano-banana-2.1', label: 'Nano Banana 2.1', shortLabel: 'Banana', group: 'banana' },
  { value: 'ideogram/v4.5', label: 'Ideogram V4.5', shortLabel: 'Ideogram', group: 'ideogram' },
  { value: 'bytedance/seedream/v5/pro/text-to-image', label: 'Seedream V5 Pro', shortLabel: 'Seedream', group: 'seedream' },
  { value: 'microsoft/mai-image-2.5', label: 'MAI Image 2.5', shortLabel: 'MAI', group: 'mai' },
  { value: 'xai/grok-imagine-image/v2.0/text-to-image', label: 'Grok Imagine 2.0', shortLabel: 'Grok', group: 'grok' },
];

const IMAGE_COUNTS = [1, 2, 3, 4];

// Edits under a result run on Ideogram V4.5 in its precise mode (backend
// routers/image_edit.py), which keeps every pixel the edit does not change.
const IMAGE_EDIT_MODEL = 'ideogram/v4.5/edit';

// Unified aspect ratios. Models without one render the nearest they have
// (MAI and Grok: 4:5 as 3:4).
const ASPECT_RATIOS = [
  { value: '1:1', label: '1:1' },
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
  { value: '4:5', label: '4:5' },
  { value: '4:3', label: '4:3' },
  { value: '3:4', label: '3:4' },
  { value: '3:2', label: '3:2' },
  { value: '2:3', label: '2:3' },
  { value: '21:9', label: '21:9' },
];

// "Use for": sets the frame and tells Magic Prompt what the image is for
// (PURPOSES in backend/app/services/image_prompt_profiles.py). Formats that
// need exact pixels are exported at that size from the download menu.
const PURPOSES = [
  { value: 'none', label: 'Any use', aspect: null },
  { value: 'instagram_post', label: 'Instagram post', aspect: '4:5' },
  { value: 'story_reel', label: 'Story or Reel', aspect: '9:16' },
  { value: 'youtube_thumbnail', label: 'YouTube thumbnail', aspect: '16:9' },
  { value: 'pinterest', label: 'Pinterest pin', aspect: '2:3' },
  { value: 'linkedin', label: 'LinkedIn post', aspect: '16:9' },
];
const EXPORTS = [
  { purpose: 'youtube_thumbnail', label: 'YouTube thumbnail', size: '1280x720' },
  { purpose: 'linkedin', label: 'LinkedIn', size: '1200x627' },
];

// Art Styles for quick selection
const STYLES = [
  { value: 'none', label: 'None' },
  { value: 'photorealism', label: 'Photorealistic' },
  { value: 'digital art', label: 'Digital Art' },
  { value: 'anime', label: 'Anime' },
  { value: 'oil painting', label: 'Oil Painting' },
  { value: 'watercolor', label: 'Watercolor' },
  { value: '3D render', label: '3D Render' },
  { value: 'cinematic', label: 'Cinematic' },
];

// Magic Prompt options
type MagicPromptMode = 'off' | 'on' | 'auto';

// One calm toolbar: every control in the composer row shares this height,
// radius, border and focus ring. Only the Generate button is lime.
const pillTriggerClass =
  'h-8 w-auto gap-1 rounded-md border border-border bg-transparent px-2.5 text-xs font-medium text-foreground transition-colors duration-150 hover:border-foreground/30 hover:bg-accent/60 focus:ring-2 focus:ring-ring focus:ring-offset-0';
const toggleClass = (on: boolean) =>
  cn(
    'h-8 gap-1.5 rounded-md border px-2.5 text-xs font-medium focus-visible:ring-offset-0',
    on
      ? 'border-foreground/30 bg-accent text-foreground hover:bg-accent hover:text-foreground'
      : 'border-border bg-transparent text-muted-foreground hover:border-foreground/30 hover:text-foreground'
  );

// Small copy control for the prompt panel; says "Copied" for a moment instead of a toast.
function CopyTextButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <Button
      size="sm"
      variant="ghost"
      className="h-7 px-2 text-xs text-muted-foreground"
      aria-label={label}
      onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true), () => undefined)}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : 'Copy'}
    </Button>
  );
}

export function GeneratePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedImage, setSelectedImage] = useState<number | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [magicPromptMode, setMagicPromptMode] = useState<MagicPromptMode>('on');
  const [isProcessing, setIsProcessing] = useState(false); // Prevents double-click during enhancement

  const {
    currentPrompt,
    setPrompt,
    selectedModel,
    setModel,
    selectedStyle,
    setStyle,
    imageSettings,
    setImageSettings,
    advancedSettings,
    setAdvancedSettings,
    loraUrl,
    setLoraUrl,
    loraScale,
    setLoraScale,
    purpose,
    setPurpose,
    directionsEnabled,
    setDirectionsEnabled,
    directionAxis,
    notice,
    generatedImages,
    isGenerating,
    generationProgress,
    generationStatus,
    error,
    generateImage,
    generatePrompt,
    clearError,
    cancelGeneration,
    qualityCheck,
    setQualityCheck,
    addImage,
  } = useGenerationStore();
  const costs = usePricingStore((s) => s.costs);
  const resolution = imageSettings.resolution || '1k';
  // USD per image for a model at the current resolution, from the live
  // price table (undefined while prices load).
  const perImageCost = (model: string): number | undefined => costs?.[imageKey(model, resolution)];

  // Read prompt from URL query parameter
  useEffect(() => {
    const promptParam = searchParams.get('prompt');
    if (promptParam) {
      setPrompt(promptParam);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setPrompt, setSearchParams]);

  const currentModelConfig = useMemo(() => {
    return MODELS.find(m => m.value === selectedModel);
  }, [selectedModel]);

  const isLoraModel = currentModelConfig?.supportsLora || false;
  const maxImages = currentModelConfig?.maxImages ?? 4;
  const imageCounts = IMAGE_COUNTS.filter((n) => n <= maxImages);
  // Only the controls the selected model takes are shown (and sent).
  const caps = modelSettings(selectedModel);
  // Directions need Magic Prompt and more than one image.
  const directionsAvailable = magicPromptMode !== 'off' && Math.min(imageSettings.numImages, maxImages) > 1;
  const directionsOn = directionsEnabled && directionsAvailable;

  // Determine if we should enhance based on mode and prompt length
  const shouldEnhance = (prompt: string): boolean => {
    if (magicPromptMode === 'off') return false;
    if (magicPromptMode === 'on' || directionsOn) return true;
    // Auto mode: enhance if prompt is short (less than 100 chars)
    return prompt.length < 100;
  };

  const handleGenerate = async () => {
    if (!currentPrompt.trim() || isProcessing) return;

    setIsProcessing(true); // Immediately disable button to prevent double-clicks
    clearError();
    setSelectedImage(null);

    try {
      // If magic prompt is enabled, enhance first then generate
      if (shouldEnhance(currentPrompt)) {
        await generatePrompt(currentPrompt); // This enhances and sets the prompt
      }
      await generateImage();
    } catch {
      // Error handled by store
    } finally {
      setIsProcessing(false);
    }
  };

  const [exportError, setExportError] = useState<string | null>(null);
  // A platform's exact pixels, cropped and resized on the server.
  const handleExport = async (imageId: number, exportPurpose: string, size: string) => {
    setExportError(null);
    try {
      const blob = await generateApi.exportImage(imageId, exportPurpose);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${exportPurpose}-${imageId}-${size}.png`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setExportError(getErrorMessage(err));
    }
  };

  const handleDownload = async (imageUrl: string, format: 'png' | 'jpeg' | 'webp', index: number) => {
    try {
      const response = await fetch(imageUrl);
      const blob = await response.blob();

      let finalBlob = blob;
      if (format !== 'png') {
        const img = new Image();
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const objectUrl = URL.createObjectURL(blob);

        try {
          await new Promise<void>((resolve, reject) => {
            img.onload = () => {
              canvas.width = img.width;
              canvas.height = img.height;
              if (format === 'jpeg') {
                ctx!.fillStyle = '#FFFFFF';
                ctx!.fillRect(0, 0, canvas.width, canvas.height);
              }
              ctx?.drawImage(img, 0, 0);
              resolve();
            };
            img.onerror = () => reject(new Error('Failed to load image'));
            img.src = objectUrl;
          });
        } finally {
          URL.revokeObjectURL(objectUrl);
        }

        finalBlob = await new Promise<Blob>((resolve) => {
          canvas.toBlob((b) => resolve(b!), `image/${format}`, format === 'jpeg' ? 0.95 : undefined);
        });
      }

      const url = window.URL.createObjectURL(finalBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `generated-image-${Date.now()}-${index + 1}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  // fal bills per image returned, which is capped by the model.
  const chargedImages = Math.min(imageSettings.numImages, maxImages);
  const selectedPerImage = perImageCost(selectedModel);
  // The opt-in quality check: not offered on the cheapest models, where it
  // would be a large share of the image's price.
  const qa = useQualityConfig();
  const checkOffered = !!qa?.available && !qa.skip_models.includes(selectedModel);
  const checkOn = qualityCheck && checkOffered;
  const checkCost = checkOn && qa ? qa.estimated_usd * chargedImages : 0;
  const totalCost = selectedPerImage !== undefined ? selectedPerImage * chargedImages + checkCost : undefined;
  const hasPrompt = currentPrompt.trim().length > 0;
  const latestImages = generatedImages.slice(0, 4);
  const baseImage = selectedImage !== null ? latestImages[selectedImage] : latestImages[0];

  // Edits: each one starts from the version on screen and adds a new version,
  // for as many turns as the user likes. versions[0] is the generated image.
  const [versions, setVersions] = useState<GeneratedImage[]>([]);
  const [versionIndex, setVersionIndex] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const baseId = baseImage?.id;
  const baseIdRef = useRef(baseId);
  // A new result, or another thumbnail, starts a fresh set of versions.
  useEffect(() => {
    baseIdRef.current = baseId;
    setVersions([]);
    setVersionIndex(null);
    setEditError(null);
  }, [baseId]);
  const activeImage = versionIndex !== null && versions[versionIndex] ? versions[versionIndex] : baseImage;
  const isEditVersion = activeImage?.model === IMAGE_EDIT_MODEL;
  const editPrice = activeImage
    ? costs?.[editKey(IMAGE_EDIT_MODEL, fixResolution(activeImage.width, activeImage.height))]
    : undefined;
  const editElapsed = useElapsedSeconds(editing);
  const canEdit = !!activeImage?.id && !editing && editText.trim().length >= 2;

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    const instruction = editText.trim();
    if (!activeImage?.id || !canEdit) return;
    const startedOn = baseId;
    const trail = versions.length > 0 ? versions : [activeImage];
    setEditing(true);
    setEditError(null);
    try {
      const edited = await generateApi.editImage(activeImage.id, instruction);
      // The user moved to another result while this ran; the edit is in My Gallery.
      if (baseIdRef.current !== startedOn) return;
      setVersions([...trail, edited]);
      setVersionIndex(trail.length);
      setEditText('');
    } catch (err) {
      if (baseIdRef.current === startedOn) {
        setEditError(getErrorMessage(err, 'The edit did not go through. Please try again.'));
      }
    } finally {
      setEditing(false);
    }
  };
  // Add text on the shown result (a new gallery image; the original is kept).
  const [textOpen, setTextOpen] = useState(false);
  const busy = isGenerating || isProcessing;
  const elapsed = useElapsedSeconds(busy);

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col">
      {/* Prompt composer */}
      <div className="flex-shrink-0 px-4 pb-8 pt-8 sm:pt-12">
        <div className="mx-auto max-w-5xl">
          <header className="mb-6">
            <h1 className="text-balance text-2xl font-semibold tracking-tight">Generate images</h1>
            <p className="mt-1 text-pretty text-sm text-muted-foreground">
              Describe an image, choose a model and format, and generate.
            </p>
          </header>

          <div>
            <div className={cn('panel rounded-xl p-4 transition-shadow duration-150 focus-within:border-foreground/25 sm:p-5', busy && 'beam-border')}>
                {/* Prompt Input */}
                <Textarea
                  placeholder="Describe what you want to see"
                  aria-label="Prompt"
                  value={currentPrompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={2}
                  aria-keyshortcuts="Enter"
                  className="min-h-[56px] resize-none border-0 bg-transparent px-0 py-1 text-base placeholder:text-muted-foreground/70 focus-visible:ring-0 focus-visible:ring-offset-0"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !isProcessing && !isGenerating) {
                      e.preventDefault();
                      handleGenerate();
                    }
                  }}
                />

                {/* Controls: options on the left (they may wrap among themselves),
                    price and Generate pinned to the right of the first line. */}
                <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                  {/* Model Selector */}
                  <Select
                    value={selectedModel}
                    onValueChange={(value) => {
                      const model = MODELS.find(m => m.value === value);
                      setModel(value);
                      if (model?.maxImages && imageSettings.numImages > model.maxImages) {
                        setImageSettings({ numImages: model.maxImages });
                      }
                    }}
                  >
                    <SelectTrigger className={pillTriggerClass}>
                      <SelectValue>
                        {currentModelConfig?.shortLabel || 'Model'}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {MODELS.map((model) => {
                        const cost = perImageCost(model.value);
                        return (
                          <SelectItem
                            key={model.value}
                            value={model.value}
                          >
                            <span className="inline-flex w-full items-center gap-1.5">
                              {model.label}
                              {cost !== undefined && (
                                <span className="ml-auto pl-3 font-mono text-[11px] text-muted-foreground">
                                  {formatUsd(cost)}
                                </span>
                              )}
                            </span>
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>

                  {/* Use for */}
                  <Select
                    value={purpose}
                    onValueChange={(v) => {
                      setPurpose(v);
                      const aspect = PURPOSES.find((p) => p.value === v)?.aspect;
                      if (aspect) setImageSettings({ aspectRatio: aspect });
                    }}
                  >
                    <SelectTrigger className={pillTriggerClass} aria-label="Use for" title="What the image is for">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PURPOSES.map((p) => (
                        <SelectItem key={p.value} value={p.value}>
                          <span className="inline-flex w-full items-center gap-1.5">
                            {p.label}
                            {p.aspect && (
                              <span className="ml-auto pl-3 font-mono text-[11px] text-muted-foreground">{p.aspect}</span>
                            )}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Aspect Ratio */}
                  <Select
                    value={imageSettings.aspectRatio}
                    onValueChange={(v) => {
                      setImageSettings({ aspectRatio: v });
                      // A frame the format does not use clears the format.
                      if (PURPOSES.find((p) => p.value === purpose)?.aspect !== v) setPurpose('none');
                    }}
                  >
                    <SelectTrigger className={pillTriggerClass}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ASPECT_RATIOS.map((ratio) => (
                        <SelectItem key={ratio.value} value={ratio.value}>
                          {ratio.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Style */}
                  <Select value={selectedStyle} onValueChange={setStyle}>
                    <SelectTrigger className={pillTriggerClass}>
                      <SelectValue placeholder="Style" />
                    </SelectTrigger>
                    <SelectContent>
                      {STYLES.map((style) => (
                        <SelectItem key={style.value} value={style.value}>
                          {style.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Number of Images - compact */}
                  <Select
                    value={String(imageSettings.numImages)}
                    onValueChange={(v) => setImageSettings({ numImages: Number(v) })}
                  >
                    <SelectTrigger className={pillTriggerClass} aria-label="Number of images" title="Number of images">
                      <span>x{imageSettings.numImages}</span>
                    </SelectTrigger>
                    <SelectContent>
                      {imageCounts.map((num) => (
                        <SelectItem key={num} value={String(num)}>
                          {num} image{num > 1 ? 's' : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Directions: a different take per image along one axis */}
                  {directionsAvailable && (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-pressed={directionsOn}
                      onClick={() => setDirectionsEnabled(!directionsEnabled)}
                      title="Magic Prompt writes one prompt per image, each a different take along one named axis, instead of one prompt repeated. Same price."
                      className={toggleClass(directionsOn)}
                    >
                      <Split className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Directions</span>
                    </Button>
                  )}

                  {/* More Options (Advanced) */}
                  <Popover open={showAdvanced} onOpenChange={setShowAdvanced}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="More settings"
                        title="More settings"
                        className={cn(toggleClass(showAdvanced), 'w-8 px-0')}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-80" align="start" side="bottom">
                      <div className="space-y-4">
                        <h4 className="text-sm font-medium">More settings</h4>

                        {/* Inference Steps: only the models that take them */}
                        {caps.steps && (
                          <div className="space-y-2">
                            <div className="flex justify-between">
                              <Label className="text-xs font-medium">Inference steps</Label>
                              <span className="font-mono text-xs text-muted-foreground">
                                {Math.min(advancedSettings.inferenceSteps, caps.steps.max)}
                              </span>
                            </div>
                            <input
                              type="range"
                              min="1"
                              max={caps.steps.max}
                              step="1"
                              value={Math.min(advancedSettings.inferenceSteps, caps.steps.max)}
                              onChange={(e) => setAdvancedSettings({ inferenceSteps: Number(e.target.value) })}
                              className="w-full accent-primary"
                            />
                          </div>
                        )}

                        {/* Keep out: no model takes a negative prompt, so Magic
                            Prompt rewrites this as what is there instead. */}
                        {magicPromptMode !== 'off' && (
                          <div className="space-y-2">
                            <Label className="text-xs font-medium">Keep out of the image</Label>
                            <Input
                              placeholder="For example: people, text"
                              value={advancedSettings.negativePrompt}
                              onChange={(e) => setAdvancedSettings({ negativePrompt: e.target.value })}
                              className="h-8 text-xs"
                            />
                            <p className="text-[11px] text-muted-foreground">
                              Magic Prompt describes the scene without these.
                            </p>
                          </div>
                        )}

                        {/* Seed: only the models that take one */}
                        {caps.seed && (
                          <div className="space-y-2">
                            <Label className="text-xs font-medium">Seed</Label>
                            <Input
                              type="number"
                              placeholder="Random"
                              value={advancedSettings.seed}
                              onChange={(e) => setAdvancedSettings({ seed: e.target.value })}
                              className="h-8 text-xs"
                            />
                          </div>
                        )}

                        {!caps.steps && !caps.seed && magicPromptMode === 'off' && !isLoraModel && (
                          <p className="text-xs text-muted-foreground">This model has no extra settings.</p>
                        )}

                        {/* LoRA Settings */}
                        {isLoraModel && (
                          <div className="space-y-3 border-t border-border pt-2">
                            <h5 className="text-xs font-medium text-muted-foreground">LoRA</h5>
                            <Input
                              placeholder="LoRA URL"
                              aria-label="LoRA URL"
                              value={loraUrl || ''}
                              onChange={(e) => setLoraUrl(e.target.value || null)}
                              className="h-8 text-xs"
                            />
                            <div className="space-y-1">
                              <div className="flex justify-between">
                                <span className="text-xs">Scale</span>
                                <span className="font-mono text-xs text-muted-foreground">{loraScale.toFixed(1)}</span>
                              </div>
                              <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.1"
                                value={loraScale}
                                onChange={(e) => setLoraScale(Number(e.target.value))}
                                className="w-full accent-primary"
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </PopoverContent>
                  </Popover>

                  {/* Quality check: opt in, priced per image */}
                  {checkOffered && qa && (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-pressed={checkOn}
                      onClick={() => setQualityCheck(!qualityCheck)}
                      title={`After each image is saved, a vision check reads it against your prompt (counts, positions, quoted text). ${formatUsd(qa.estimated_usd)} per image.`}
                      className={toggleClass(checkOn)}
                    >
                      Check quality
                      <span className="font-mono tabular text-muted-foreground">+{formatUsd(qa.estimated_usd)}</span>
                    </Button>
                  )}

                  {/* Magic Prompt Toggle */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Magic Prompt: ${magicPromptMode}`}
                        title="Magic Prompt"
                        className={toggleClass(magicPromptMode !== 'off')}
                      >
                        <Wand2 className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">
                          Magic Prompt{magicPromptMode !== 'on' && <span className="text-muted-foreground"> {magicPromptMode}</span>}
                        </span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <div className="px-2 py-1.5 text-sm font-medium">Magic Prompt</div>
                      <div className="max-w-[220px] px-2 pb-2 text-xs text-muted-foreground">
                        Rewrites your prompt with more detail before generating. Auto does this for short prompts only.
                      </div>
                      <DropdownMenuItem onClick={() => setMagicPromptMode('auto')}>
                        Auto {magicPromptMode === 'auto' && <Check className="ml-auto h-3.5 w-3.5 text-primary" />}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setMagicPromptMode('on')}>
                        On {magicPromptMode === 'on' && <Check className="ml-auto h-3.5 w-3.5 text-primary" />}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setMagicPromptMode('off')}>
                        Off {magicPromptMode === 'off' && <Check className="ml-auto h-3.5 w-3.5 text-primary" />}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                </div>

                  {/* Price and Generate stay together at the end of the row */}
                  <div className="flex shrink-0 items-center justify-end gap-3">
                    <span
                      className="text-right font-mono tabular text-xs text-muted-foreground"
                      title={`${formatUsd(selectedPerImage ?? 0)} per image at ${resolution.toUpperCase()}${checkOn && qa ? `, plus ${formatUsd(qa.estimated_usd)} per quality check` : ''}`}
                    >
                      {totalCost !== undefined ? formatUsd(totalCost) : ''}
                    </span>

                    <Button
                      onClick={handleGenerate}
                      disabled={!hasPrompt || busy}
                      className="h-8 min-w-[7.5rem] flex-1 rounded-md px-4 text-sm font-medium sm:flex-none"
                    >
                      {isProcessing && !isGenerating ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Enhancing
                        </>
                      ) : isGenerating ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Generating
                        </>
                      ) : (
                        'Generate'
                      )}
                    </Button>
                  </div>
                </div>

                {/* Status Bar */}
                {(error || notice || exportError) && (
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-xs" role="status">
                    {error && (
                      <span className="text-destructive">{error}</span>
                    )}
                    {!error && (notice || exportError) && (
                      <span className="text-warning">{exportError || notice}</span>
                    )}
                  </div>
                )}
            </div>
          </div>
        </div>
      </div>

      {/* Results Section - Only shown when generating or have images */}
      <div className="flex-1 px-4 pb-8">
        {isGenerating ? (
          /* Generation Progress */
          <div className="mx-auto max-w-5xl">
            <div className="mx-auto mb-6 max-w-md space-y-2" role="status" aria-live="polite">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-foreground">
                  Generating {chargedImages} image{chargedImages > 1 ? 's' : ''}
                  {directionsOn && directionAxis
                    ? `, one per direction (${directionAxis})`
                    : magicPromptMode !== 'off' && ', with Magic Prompt'}
                </span>
                <Button variant="ghost" size="sm" onClick={cancelGeneration} className="h-7 px-2">
                  Cancel
                </Button>
              </div>
              <Progress value={generationProgress} />
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{generationStatus || 'Starting'}</span>
                <span className="font-mono tabular">
                  {formatElapsed(elapsed)}, {generationProgress}%
                </span>
              </div>
            </div>
            <div className={`grid gap-4 ${chargedImages === 1 ? 'mx-auto max-w-2xl grid-cols-1' : 'grid-cols-2'}`}>
              {Array.from({ length: chargedImages }).map((_, i) => (
                <div
                  key={i}
                  className="shimmer mx-auto max-h-[60vh] w-full rounded-xl bg-muted"
                  style={{ aspectRatio: ratioToCss(imageSettings.aspectRatio) }}
                />
              ))}
            </div>
          </div>
        ) : generatedImages.length > 0 ? (
          /* Results Gallery */
          <div className="mx-auto max-w-5xl">
            {/* Main Image Display */}
            {activeImage && (
              <motion.div
                key={activeImage.url}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2, ease: studioEase }}
                className="mb-4"
              >
                <div className="group relative overflow-hidden rounded-xl border border-border bg-card">
                  <img
                    src={activeImage.url}
                    alt={activeImage.prompt}
                    width={activeImage.width}
                    height={activeImage.height}
                    className={cn(
                      'mx-auto h-auto max-h-[60vh] w-full object-contain transition-opacity duration-200',
                      editing && 'opacity-40',
                    )}
                  />
                  {editing && (
                    <div className="absolute inset-0 flex items-center justify-center" role="status">
                      <span className="glass flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Editing, usually under a minute
                        <span className="font-mono tabular text-muted-foreground">{formatElapsed(editElapsed)}</span>
                      </span>
                    </div>
                  )}
                  {/* Actions: always shown on touch screens, on hover or focus elsewhere */}
                  <div className="absolute right-4 top-4 flex gap-2 transition-opacity duration-150 focus-within:opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="glass">
                          <Download className="h-4 w-4" />
                          Download
                          <ChevronDown className="h-3 w-3" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem onClick={() => handleDownload(activeImage.url, 'png', 0)}>PNG</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDownload(activeImage.url, 'jpeg', 0)}>JPEG</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDownload(activeImage.url, 'webp', 0)}>WebP</DropdownMenuItem>
                        {activeImage.id && EXPORTS.map((ex) => (
                          <DropdownMenuItem
                            key={ex.purpose}
                            onClick={() => handleExport(activeImage.id, ex.purpose, ex.size)}
                          >
                            {ex.label}
                            <span className="ml-auto pl-3 font-mono text-[11px] text-muted-foreground">{ex.size}</span>
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                    {activeImage.id ? (
                      <Button size="sm" variant="glass" onClick={() => setTextOpen(true)}>
                        Add text
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="glass"
                      aria-label="Copy prompt"
                      title="Copy prompt"
                      onClick={() => navigator.clipboard.writeText(activeImage.prompt)}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {/* Image Info */}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <div className="flex flex-wrap items-center gap-4">
                    <span>{isEditVersion ? 'Ideogram V4.5 edit' : currentModelConfig?.label}</span>
                    <span className="font-mono tabular">{activeImage.aspectRatio || imageSettings.aspectRatio}</span>
                    {activeImage.seed && <span>Seed <span className="font-mono tabular">{activeImage.seed}</span></span>}
                  </div>
                  <span className="tabular">{formatLocalDate(activeImage.createdAt)}</span>
                </div>

                {/* Versions: the generated image and every edit of it */}
                {versions.length > 1 && (
                  <div className="mt-3 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Versions">
                    {versions.map((v, i) => {
                      const on = (versionIndex ?? 0) === i;
                      return (
                        <button
                          key={v.id}
                          type="button"
                          onClick={() => setVersionIndex(i)}
                          aria-pressed={on}
                          title={i === 0 ? 'The generated image' : v.prompt}
                          className="w-20 shrink-0 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <span
                            className={cn(
                              'block overflow-hidden rounded-md border transition-colors duration-150',
                              on ? 'border-primary ring-1 ring-primary' : 'border-border hover:border-foreground/30',
                            )}
                          >
                            <img src={v.url} alt="" className="aspect-square w-full object-cover" />
                          </span>
                          <span className={cn('mt-1 block truncate text-[11px]', on ? 'text-foreground' : 'text-muted-foreground')}>
                            {i === 0 ? 'Original' : `Edit ${i}`}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Edit: describe a change; it applies to the version on screen */}
                {activeImage.id ? (
                  <form onSubmit={handleEdit} className="mt-3">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <Input
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        maxLength={1000}
                        disabled={editing}
                        placeholder="Describe a change, for example: make the background white"
                        aria-label="Describe a change to this image"
                        className="h-9 min-w-0 flex-1 text-sm"
                      />
                      <div className="flex shrink-0 items-center justify-end gap-3">
                        {editPrice !== undefined && (
                          <span className="font-mono tabular text-xs text-muted-foreground">
                            {formatUsd(editPrice)}
                          </span>
                        )}
                        <Button type="submit" variant="outline" disabled={!canEdit} className="h-9 min-w-[6.5rem]">
                          {editing ? (
                            <>
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              Editing
                            </>
                          ) : (
                            'Edit image'
                          )}
                        </Button>
                      </div>
                    </div>
                    <p
                      className={cn('mt-1.5 text-xs', editError ? 'text-destructive' : 'text-muted-foreground')}
                      role={editError ? 'alert' : undefined}
                    >
                      {editError
                        ? editError
                        : 'Ideogram V4.5 changes only what you describe and keeps the rest. Every edit is saved as a new image, so you can keep editing or go back to any version.'}
                    </p>
                  </form>
                ) : null}

                {activeImage.quality && (
                  <ImageQuality
                    key={activeImage.id}
                    image={activeImage}
                    onFixed={(fixed) => {
                      addImage(fixed);
                      setSelectedImage(0);
                    }}
                    className="mt-2"
                  />
                )}

                {/* The user's prompt, then the Magic Prompt version the model actually received */}
                <div className="mt-2 rounded-lg border border-border bg-secondary/40 p-3">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-muted-foreground">
                      {isEditVersion ? `Edit ${versionIndex ?? ''}`.trim() : 'Your prompt'}
                    </p>
                    <CopyTextButton text={activeImage.prompt} label="Copy your prompt" />
                  </div>
                  <p className="whitespace-pre-wrap text-sm">{activeImage.prompt}</p>
                  {isEditVersion && versions[0] && (
                    <div className="mt-3 border-t border-border pt-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Original prompt</p>
                      <p className="whitespace-pre-wrap text-sm text-muted-foreground">{versions[0].prompt}</p>
                    </div>
                  )}
                  {!isEditVersion && activeImage.magicPrompt && activeImage.magicPrompt !== activeImage.prompt && (
                    <div className="mt-3 border-t border-border pt-3">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <p className="text-xs font-medium text-muted-foreground">Magic Prompt version, sent to the model</p>
                        <CopyTextButton text={activeImage.magicPrompt} label="Copy Magic Prompt version" />
                      </div>
                      <p className="whitespace-pre-wrap text-sm text-muted-foreground">{activeImage.magicPrompt}</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {activeImage && (
              <AddTextDialog image={activeImage} open={textOpen} onOpenChange={setTextOpen} />
            )}

            {/* Thumbnail Grid */}
            {latestImages.length > 1 && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {latestImages.map((image, index) => (
                  <button
                    key={image.id || index}
                    onClick={() => setSelectedImage(index)}
                    aria-label={`Show image ${index + 1}`}
                    aria-pressed={selectedImage === index || (selectedImage === null && index === 0)}
                    className={`relative overflow-hidden rounded-lg border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      (selectedImage === index || (selectedImage === null && index === 0))
                        ? 'border-primary ring-2 ring-primary'
                        : 'border-border hover:border-foreground/30'
                    }`}
                  >
                    <img src={image.url} alt={image.prompt} className="aspect-square w-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
