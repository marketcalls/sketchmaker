import { useState, useRef, useEffect } from 'react';
import { Download, Send, Check, ImageIcon, Palette, Sparkles, ArrowLeft, Loader2, RotateCcw, Layers } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { usePricingStore, editKey, formatUsd } from '@/stores/pricingStore';
import { DEFAULT_EDIT_MODEL, EDIT_MODELS, type EditModelId } from '@/utils/models';
import { MagixUploadStep, MagixModeCarousel, type UploadedImage } from '@/components/magix';
import { Stagger, StaggerItem } from '@/components/motion';
import { useElapsedSeconds, formatElapsed } from '@/components/generate';
import { getErrorMessage } from '@/utils/errors';
import apiClient from '@/api/client';

// Types
interface ChatMessage {
  id: string;
  type: 'user' | 'system' | 'result';
  content: string;
  imageUrl?: string;
  timestamp: Date;
  // A re-run of every edit on the original; not an edit of its own
  reapply?: boolean;
  // A failed edit, shown in the destructive colour
  error?: boolean;
}

// Product mode: the surface the product stands on (edit_prompts.PRODUCT_SURFACES)
const PRODUCT_SURFACES = [
  { value: 'white_seamless', label: 'White sweep' },
  { value: 'marble', label: 'Marble' },
  { value: 'wood', label: 'Oak' },
  { value: 'concrete', label: 'Concrete' },
  { value: 'linen', label: 'Linen' },
  { value: 'slate', label: 'Wet slate' },
];

// After this many edits, re-running them all on the original avoids the
// drift that builds up when each edit starts from the last result.
const REAPPLY_AFTER_EDITS = 3;

// GPT Image 2.5 pads a source outside 1:3 to 3:1 with white bands.
const PADDED_EDIT_MODELS = new Set(['openai/gpt-image-2.5/sunburst/edit']);

interface MagixImageResult {
  url: string;
  seed: number | null;
  gallery_id: number | null;
  width: number | null;
  height: number | null;
}

interface MagixResult {
  image_url?: string;
  images?: MagixImageResult[];
  seed: number | null;
  prompt: string;
  gallery_id?: number | null;
  width?: number | null;
  height?: number | null;
}

// Magix renders every edit at 1K; the backend prices edits by model and resolution.
const MAGIX_RESOLUTION = '1K';

// Wizard steps
const STEPS = [
  { id: 1, label: 'Upload', icon: ImageIcon },
  { id: 2, label: 'Style', icon: Palette },
  { id: 3, label: 'Edit', icon: Sparkles },
];

// Step indicator component
function StepIndicator({ currentStep }: { currentStep: number }) {
  return (
    <div className="flex items-center justify-center">
      {STEPS.map((step, index) => {
        const isCompleted = currentStep > step.id;
        const isCurrent = currentStep === step.id;

        return (
          <div key={step.id} className="flex items-center">
            <div className="flex items-center gap-2">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium tabular transition-colors duration-150 ${
                  isCompleted
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : isCurrent
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground'
                }`}
              >
                {isCompleted ? <Check className="h-3.5 w-3.5" /> : step.id}
              </span>
              <span
                className={`hidden text-sm sm:block ${
                  isCurrent ? 'text-foreground' : 'text-muted-foreground'
                }`}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <div
                className={`mx-3 h-px w-8 sm:mx-5 sm:w-16 ${
                  currentStep > step.id ? 'bg-primary/50' : 'bg-border'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export function MagixPage() {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

  // Upload state (Step 1)
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);

  // Mode state (Step 2)
  const [selectedMode, setSelectedMode] = useState('studio_portrait');
  const [editModel, setEditModel] = useState<EditModelId>(DEFAULT_EDIT_MODEL);

  // Chat state (Step 3)
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentWorkingImage, setCurrentWorkingImage] = useState<string | null>(null);
  // Product mode options
  const [productSurface, setProductSurface] = useState('white_seamless');
  const [labelText, setLabelText] = useState('');

  // Refs
  const chatEndRef = useRef<HTMLDivElement>(null);

  const costs = usePricingStore((s) => s.costs);
  // Magix edits at 1K (MAGIX_RESOLUTION) and bills one output per edit,
  // priced by edit model from the live table (undefined while prices load).
  const editCost = (model: string): number | undefined => costs?.[editKey(model, MAGIX_RESOLUTION)];
  const perEdit = editCost(editModel);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Initialize chat when entering Step 3
  useEffect(() => {
    if (currentStep === 3 && uploadedImages.length > 0 && messages.length === 0) {
      setCurrentWorkingImage(uploadedImages[0].url);
      setMessages([{
        id: Date.now().toString(),
        type: 'system',
        content: `Ready to edit with "${selectedMode.replace(/_/g, ' ')}" style. Describe your first edit or just press Send to apply the style.`,
        imageUrl: uploadedImages[0].url,
        timestamp: new Date(),
      }]);
    }
  }, [currentStep, uploadedImages, selectedMode, messages.length]);

  // The original photo stays pinned: edits can always start over from it.
  const originalImage = uploadedImages[0]?.url ?? null;
  // The edits made so far (re-runs on the original are not edits of their own)
  const userEdits = messages.filter(m => m.type === 'user' && !m.reapply);
  const first = uploadedImages[0];
  const paddedWarning = !!first?.width && !!first?.height && PADDED_EDIT_MODELS.has(editModel)
    && (first.width / first.height > 3 || first.height / first.width > 3);

  // Build edit history from messages for context
  const buildEditHistory = () => {
    return userEdits.map(m => ({
      prompt: m.content,
      timestamp: m.timestamp.toISOString(),
    }));
  };

  // Handle send message / generate. With `reapply`, every edit so far runs
  // again in one pass on the original photo.
  const handleSend = async (reapply = false) => {
    if (!currentWorkingImage || isProcessing) return;
    if (reapply && (!originalImage || userEdits.length < REAPPLY_AFTER_EDITS)) return;

    const promptText = reapply
      ? `Apply all of these edits: ${userEdits.map((m, i) => `${i + 1}. ${m.content}`).join(' ')}`
      : inputText.trim() || `Apply ${selectedMode.replace(/_/g, ' ')} style`;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: reapply ? `Re-apply all ${userEdits.length} edits to the original photo` : promptText,
      timestamp: new Date(),
      reapply,
    };
    setMessages(prev => [...prev, userMessage]);
    if (!reapply) setInputText('');
    setIsProcessing(true);

    try {
      // Get edit history for context (previous user prompts in this session)
      const editHistory = reapply ? [] : buildEditHistory();

      // Photo 1 is the one being edited; every other photo lends one job.
      const extras = uploadedImages.slice(1);
      const requestData: Record<string, unknown> = {
        prompt: promptText,
        mode: selectedMode,
        model: editModel,
        aspect_ratio: 'auto',
        resolution: MAGIX_RESOLUTION,
        image_urls: [reapply ? originalImage : currentWorkingImage, ...extras.map(img => img.url)],
        image_roles: [selectedMode === 'product' ? 'product' : 'subject', ...extras.map(img => img.role || 'subject')],
        edit_history: editHistory.length > 0 ? editHistory : undefined,
        ...(selectedMode === 'product'
          ? { surface: productSurface, label_text: labelText.trim() || undefined }
          : {}),
      };

      const response = await apiClient.post('/magix/generate', requestData);
      const data = response.data as MagixResult;

      let resultUrl: string | undefined;
      if (data.images && data.images.length > 0) {
        resultUrl = data.images[0].url;
      } else if (data.image_url) {
        resultUrl = data.image_url;
      }

      if (resultUrl) {
        // Update current working image to the result (for next edit)
        setCurrentWorkingImage(resultUrl);

        // Add result message
        const resultMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          type: 'result',
          content: data.prompt || promptText,
          imageUrl: resultUrl,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, resultMessage]);
      }
    } catch (err: unknown) {
      // The API client has already made the detail readable.
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        type: 'system',
        content: `The edit did not go through. ${getErrorMessage(err, 'Please try again.')}`,
        timestamp: new Date(),
        error: true,
      }]);
    } finally {
      setIsProcessing(false);
    }
  };

  // Handle key press (Enter or Ctrl+Enter sends, Shift+Enter adds a line)
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  // Handle download
  const handleDownload = async (url: string, index: number) => {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `magix_${selectedMode}_${index + 1}_${Date.now()}.jpg`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch {
      // Silent fail
    }
  };

  // Use a specific image from history as the new base
  const handleUseAsBase = (imageUrl: string) => {
    setCurrentWorkingImage(imageUrl);
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      type: 'system',
      content: 'Switched to this image. Continue editing from here.',
      timestamp: new Date(),
    }]);
  };

  // Start new session
  const handleStartNew = () => {
    setCurrentStep(1);
    setUploadedImages([]);
    setSelectedMode('studio_portrait');
    setMessages([]);
    setInputText('');
    setCurrentWorkingImage(null);
    setLabelText('');
  };

  const canGenerate = currentWorkingImage && !isProcessing;
  const elapsed = useElapsedSeconds(isProcessing);
  // Edits keep the photo's frame, so the placeholder borrows its shape.
  const workingRatio = first?.width && first?.height ? first.width / first.height : null;

  return (
    <Stagger className="flex flex-col h-[calc(100vh-4rem)]" interval={0.08}>
      {/* Header */}
      <StaggerItem className="border-b border-border pb-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <header>
            <h1 className="text-balance text-2xl font-semibold tracking-tight">Magix Studio</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Restyle a portrait or product photo, then refine it in plain words.
            </p>
          </header>
          <StepIndicator currentStep={currentStep} />
        </div>
      </StaggerItem>

      {/* Main Content Area */}
      <StaggerItem className="flex-1 overflow-y-auto">
        {/* Step 1: Upload */}
        {currentStep === 1 && (
          <div className="py-6">
            <MagixUploadStep
              uploadedImages={uploadedImages}
              onImagesChange={setUploadedImages}
              onNext={() => setCurrentStep(2)}
            />
          </div>
        )}

        {/* Step 2: Mode Selection */}
        {currentStep === 2 && (
          <div className="py-6">
            <MagixModeCarousel
              selectedMode={selectedMode}
              onModeSelect={setSelectedMode}
              onNext={() => setCurrentStep(3)}
              onBack={() => setCurrentStep(1)}
            />
          </div>
        )}

        {/* Step 3: Chat-based Editing */}
        {currentStep === 3 && (
          <div className="flex flex-col h-full">
            {/* Back button and info bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setMessages([]);
                  setCurrentStep(2);
                }}
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Change style
              </Button>
              <div className="flex items-center gap-2">
                <span className="hidden text-xs text-muted-foreground sm:inline">Style</span>
                <span className="rounded-md border border-border px-2 py-0.5 text-xs font-medium capitalize text-foreground">
                  {selectedMode.replace(/_/g, ' ')}
                </span>
                <Select value={editModel} onValueChange={(v) => setEditModel(v as EditModelId)} disabled={isProcessing}>
                  <SelectTrigger
                    aria-label="Edit model"
                    className="h-8 w-auto gap-1 rounded-md border border-border bg-transparent px-2.5 text-xs text-foreground"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EDIT_MODELS.map((m) => {
                      const cost = editCost(m.value);
                      return (
                        <SelectItem key={m.value} value={m.value}>
                          <span className="inline-flex w-full items-center gap-1.5">
                            {m.label}
                            {cost !== undefined && (
                              <span className="ml-auto pl-3 font-mono tabular text-[11px] text-muted-foreground">
                                {formatUsd(cost)}
                              </span>
                            )}
                          </span>
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>
              <Button variant="outline" size="sm" onClick={handleStartNew}>
                <RotateCcw className="h-4 w-4 mr-2" />
                New image
              </Button>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((message, index) => (
                <div
                  key={message.id}
                  className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] sm:max-w-[70%] p-4 ${
                      message.type === 'user'
                        ? 'rounded-2xl rounded-br-sm bg-secondary/60'
                        : 'rounded-2xl rounded-bl-sm bg-card border border-border'
                    }`}
                  >
                    {message.imageUrl && (
                      <motion.div
                        className="mb-3 relative group"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: 0.2 }}
                      >
                        <img
                          src={message.imageUrl}
                          alt=""
                          className="rounded-lg max-h-80 w-auto border border-border"
                        />
                        {message.type === 'result' && (
                          <div className="absolute top-2 right-2 flex gap-2 transition-opacity duration-150 focus-within:opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                            <Button
                              size="icon"
                              variant="glass"
                              className="h-8 w-8"
                              onClick={() => handleDownload(message.imageUrl!, index)}
                              title="Download"
                              aria-label="Download"
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                            {message.imageUrl !== currentWorkingImage && (
                              <Button
                                size="icon"
                                variant="glass"
                                className="h-8 w-8"
                                onClick={() => handleUseAsBase(message.imageUrl!)}
                                title="Edit from this version"
                                aria-label="Edit from this version"
                              >
                                <RotateCcw className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        )}
                      </motion.div>
                    )}
                    <p className={`text-sm ${message.error ? 'text-destructive' : 'text-foreground'}`} role={message.error ? 'alert' : undefined}>
                      {message.type === 'result' && (
                        <span className="mb-1 block text-xs font-medium text-muted-foreground">
                          Edit applied
                        </span>
                      )}
                      {message.content}
                    </p>
                    <span className="mt-2 block text-[11px] tabular text-muted-foreground">
                      {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              ))}

              {/* Processing indicator */}
              {isProcessing && (
                <div className="flex justify-start" role="status" aria-live="polite">
                  <div className="beam-border max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-card p-4 sm:max-w-[70%]">
                    <div
                      className={`shimmer mb-3 max-w-full rounded-lg bg-muted ${workingRatio ? 'h-60 sm:h-80' : 'h-40 w-40'}`}
                      style={workingRatio ? { aspectRatio: String(workingRatio) } : undefined}
                    />
                    <p className="text-sm text-muted-foreground">
                      Applying your edit, <span className="font-mono tabular">{formatElapsed(elapsed)}</span>
                    </p>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Current Image Indicator, with the original pinned beside it */}
            {currentWorkingImage && (
              <div className="border-t border-border bg-secondary/20 px-4 py-2">
                <div className="flex max-w-4xl flex-wrap items-center gap-3">
                  {originalImage && originalImage !== currentWorkingImage && (
                    <button
                      type="button"
                      onClick={() => handleUseAsBase(originalImage)}
                      disabled={isProcessing}
                      title="Edit from the original photo"
                      className="group flex items-center gap-2"
                    >
                      <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-border bg-muted transition-colors duration-150 group-hover:border-foreground/30">
                        <img src={originalImage} alt="" className="w-full h-full object-cover" />
                      </div>
                      <span className="text-xs text-muted-foreground group-hover:text-foreground">
                        Original
                      </span>
                    </button>
                  )}
                  <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-primary/40 bg-muted">
                    <img src={currentWorkingImage} alt="" className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-muted-foreground">Currently editing</p>
                    <p className="text-sm">Your next edit will apply to this image</p>
                  </div>
                  {userEdits.length >= REAPPLY_AFTER_EDITS && originalImage && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleSend(true)}
                      disabled={!canGenerate}
                      title="Each edit starting from the last result slowly drifts. This runs all your edits again, in one pass, on the original photo."
                    >
                      <Layers className="h-4 w-4 mr-2" />
                      Re-apply all edits to the original
                      {perEdit !== undefined && (
                        <span className="ml-2 font-mono tabular text-[11px] text-muted-foreground">{formatUsd(perEdit)}</span>
                      )}
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Product mode: the surface and the exact label copy */}
            {selectedMode === 'product' && (
              <div className="border-t border-border px-4 py-2">
                <div className="flex max-w-4xl flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">Surface</span>
                  <Select value={productSurface} onValueChange={setProductSurface} disabled={isProcessing}>
                    <SelectTrigger
                      aria-label="Surface"
                      className="h-8 w-auto gap-1 rounded-md border border-border bg-transparent px-2.5 text-xs text-foreground"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRODUCT_SURFACES.map((s) => (
                        <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    value={labelText}
                    onChange={(e) => setLabelText(e.target.value)}
                    maxLength={120}
                    placeholder="Label text, exactly as printed (optional)"
                    aria-label="Label text"
                    className="h-8 flex-1 min-w-[12rem] text-xs"
                    disabled={isProcessing}
                  />
                </div>
              </div>
            )}

            {paddedWarning && (
              <p className="border-t border-border px-4 py-2 text-center text-xs text-warning">
                GPT Image 2.5 adds white bands to photos wider than 3:1 or taller than 1:3. Crop the photo or pick
                another model.
              </p>
            )}

            {/* Input Area */}
            <div className="border-t border-border p-4">
              <div className="max-w-4xl">
                <div className={`panel flex gap-3 rounded-xl p-2 transition-colors duration-150 focus-within:border-foreground/25 ${isProcessing ? 'beam-border' : ''}`}>
                  <Textarea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Describe your edit, for example: change the dress to blue. Leave it empty to apply the style."
                    aria-label="Describe your edit"
                    className="flex-1 min-h-[48px] max-h-32 resize-none border-0 bg-transparent focus-visible:ring-0"
                    disabled={isProcessing || !canGenerate}
                  />
                  <Button
                    size="icon"
                    className="h-12 w-12 self-end"
                    onClick={() => void handleSend()}
                    disabled={!canGenerate}
                    aria-label={isProcessing ? 'Applying edit' : 'Apply edit'}
                    title={perEdit !== undefined ? `Apply edit, ${formatUsd(perEdit)}` : 'Apply edit'}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-5 w-5" />
                    )}
                  </Button>
                </div>
                <p className="mt-2 text-center text-xs text-muted-foreground">
                  Enter sends, Shift+Enter adds a line. Each edit builds on the previous result.
                  {perEdit !== undefined && (
                    <span className="font-mono tabular text-foreground">
                      {' '}
                      {formatUsd(perEdit)} per edit.
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>
        )}
      </StaggerItem>
    </Stagger>
  );
}
