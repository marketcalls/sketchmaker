import { useState } from 'react';
import { Download, RotateCcw, Shirt, Check, ImageIcon, Palette, Sparkles, ArrowLeft, User } from 'lucide-react';
import { useElapsedSeconds, formatElapsed, ratioToCss } from '@/components/generate';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { VirtualUploadStep, VirtualModeCarousel, VirtualBottomBar } from '@/components/virtual';
import { Stagger, StaggerItem } from '@/components/motion';
import apiClient from '@/api/client';
import { DEFAULT_EDIT_MODEL, EDIT_MODELS, type EditModelId } from '@/utils/models';
import { getErrorMessage } from '@/utils/errors';

// Types
interface UploadedImage {
  url: string;
  name: string;
}

interface VirtualImageResult {
  url: string;
  id?: number;
  width?: number;
  height?: number;
}

// Wizard steps
const STEPS = [
  { id: 1, label: 'Upload', icon: ImageIcon },
  { id: 2, label: 'Setting', icon: Palette },
  { id: 3, label: 'Try on', icon: Sparkles },
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
              {/* Step Circle */}
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

              {/* Step Label (Desktop) */}
              <span
                className={`hidden text-sm sm:block ${
                  isCurrent ? 'text-foreground' : 'text-muted-foreground'
                }`}
              >
                {step.label}
              </span>
            </div>

            {/* Connector Line */}
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

export function VirtualPage() {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

  // Upload state (Step 1)
  const [personImage, setPersonImage] = useState<UploadedImage | null>(null);
  const [dressImage, setDressImage] = useState<UploadedImage | null>(null);

  // Mode state (Step 2)
  const [selectedMode, setSelectedMode] = useState('natural');

  // Generation state (Step 3)
  const [prompt, setPrompt] = useState('');
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [numImages, setNumImages] = useState(1);
  const [useDressBackground, setUseDressBackground] = useState(false);
  const [editModel, setEditModel] = useState<EditModelId>(DEFAULT_EDIT_MODEL);
  const [seed, setSeed] = useState('');

  // Results state
  const [results, setResults] = useState<VirtualImageResult[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Charged per output image by edit model; models that return one image per
  // request are charged for one.
  const chargedImages = Math.min(
    numImages,
    EDIT_MODELS.find((m) => m.value === editModel)?.maxImages ?? numImages,
  );

  // Generate handler
  const handleGenerate = async () => {
    if (!personImage || !dressImage) {
      setError('Upload both photos first.');
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const requestData: Record<string, unknown> = {
        person_image: personImage.url,
        dress_image: dressImage.url,
        use_dress_background: useDressBackground,
        num_images: numImages,
        model: editModel,
        mode: selectedMode,
        aspect_ratio: aspectRatio,
      };

      if (prompt.trim()) {
        requestData.prompt = prompt.trim();
      }

      if (seed) {
        const seedNum = parseInt(seed, 10);
        if (!isNaN(seedNum) && seedNum >= 0) {
          requestData.seed = seedNum;
        } else {
          setError('The seed must be a whole number of 0 or more. Leave it empty for a random seed.');
          setIsProcessing(false);
          return;
        }
      }

      const response = await apiClient.post('/virtual/generate', requestData);
      const data = response.data;

      if (data.images && data.images.length > 0) {
        setResults(data.images);
      } else if (data.url) {
        setResults([{ url: data.url }]);
      }
    } catch (err: unknown) {
      // The API client has already made the detail readable.
      setError(getErrorMessage(err, 'The try-on did not go through. Please try again.'));
    } finally {
      setIsProcessing(false);
    }
  };

  // Download handler
  const handleDownload = async (url: string, index: number) => {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `virtual_tryon_${selectedMode}_${index + 1}_${Date.now()}.jpg`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch (err) {
      const message = getErrorMessage(err, 'The image could not be downloaded. Please try again.');
      setError(message);
      // Auto-clear error after 5 seconds
      setTimeout(() => setError(null), 5000);
    }
  };

  const handleStartOver = () => {
    setPersonImage(null);
    setDressImage(null);
    setResults([]);
    setCurrentStep(1);
  };

  const canGenerate = personImage !== null && dressImage !== null && !isProcessing;
  const elapsed = useElapsedSeconds(isProcessing);

  return (
    <Stagger className="flex flex-col h-[calc(100vh-4rem)]" interval={0.08}>
      {/* Header */}
      <StaggerItem className="border-b border-border pb-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <header>
            <h1 className="text-balance text-2xl font-semibold tracking-tight">Virtual Try-On</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload your photo and an outfit, pick a setting, and see the outfit on you.
            </p>
          </header>

          {/* Step Indicator */}
          <StepIndicator currentStep={currentStep} />
        </div>
      </StaggerItem>

      {/* Main Content Area */}
      <StaggerItem className="flex-1 overflow-y-auto">
        <div className="py-6">
          {/* Step 1: Upload */}
          {currentStep === 1 && (
            <VirtualUploadStep
              personImage={personImage}
              dressImage={dressImage}
              onPersonImageChange={setPersonImage}
              onDressImageChange={setDressImage}
              onNext={() => setCurrentStep(2)}
            />
          )}

          {/* Step 2: Mode Selection */}
          {currentStep === 2 && (
            <VirtualModeCarousel
              selectedMode={selectedMode}
              onModeSelect={setSelectedMode}
              onNext={() => setCurrentStep(3)}
              onBack={() => setCurrentStep(1)}
            />
          )}

          {/* Step 3: Generate */}
          {currentStep === 3 && (
            <div className="max-w-4xl space-y-6 pb-32">
              {/* Back Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCurrentStep(2)}
                className="mb-4"
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Change setting
              </Button>

              {/* Preview Section */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Input Images Preview */}
                <Card>
                  <CardContent className="p-4">
                    <h3 className="mb-3 flex items-center gap-2 font-medium tracking-tight">
                      <ImageIcon className="h-4 w-4 text-muted-foreground" />
                      Your photos
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-2">
                        <div className="aspect-[3/4] overflow-hidden rounded-lg border border-border bg-muted">
                          {personImage && (
                            <img
                              src={personImage.url}
                              alt="Person"
                              className="w-full h-full object-cover"
                            />
                          )}
                        </div>
                        <p className="flex items-center justify-center gap-1 text-center text-xs text-muted-foreground">
                          <User className="h-3 w-3" />
                          Your photo
                        </p>
                      </div>
                      <div className="space-y-2">
                        <div className="aspect-[3/4] overflow-hidden rounded-lg border border-border bg-muted">
                          {dressImage && (
                            <img
                              src={dressImage.url}
                              alt="Outfit"
                              className="w-full h-full object-cover"
                            />
                          )}
                        </div>
                        <p className="flex items-center justify-center gap-1 text-center text-xs text-muted-foreground">
                          <Shirt className="h-3 w-3" />
                          Outfit
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Selected Mode Card */}
                <Card>
                  <CardContent className="p-4">
                    <h3 className="mb-3 flex items-center gap-2 font-medium tracking-tight">
                      <Shirt className="h-4 w-4 text-muted-foreground" />
                      Setting
                    </h3>
                    <div className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3">
                      <div className="text-base font-semibold capitalize">
                        {selectedMode.replace(/_/g, ' ')}
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground mt-3">
                      Add an optional prompt below, then choose Try on.
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Working state: placeholders in the output's frame */}
              {isProcessing && (
                <Card className="beam-border">
                  <CardContent className="space-y-4 p-4">
                    <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
                      Generating {chargedImages} image{chargedImages > 1 ? 's' : ''}, usually under a minute.{' '}
                      <span className="font-mono tabular text-foreground">{formatElapsed(elapsed)}</span>
                    </p>
                    <div className={`grid gap-4 ${chargedImages === 1 ? 'grid-cols-1 max-w-md mx-auto' : 'grid-cols-2'}`}>
                      {Array.from({ length: chargedImages }).map((_, i) => (
                        <div
                          key={i}
                          className="shimmer w-full rounded-xl bg-muted"
                          style={{ aspectRatio: ratioToCss(aspectRatio) }}
                        />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Results Section */}
              {results.length > 0 && !isProcessing && (
                <Card>
                  <CardContent className="p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-medium tracking-tight">
                        Results <span className="tabular text-muted-foreground">({results.length})</span>
                      </h3>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleStartOver}
                      >
                        <RotateCcw className="h-4 w-4 mr-1" />
                        Start over
                      </Button>
                    </div>

                    <div className={`grid gap-4 ${results.length === 1 ? 'grid-cols-1 max-w-md mx-auto' : 'grid-cols-2'}`}>
                      {results.map((result, index) => (
                        <motion.div
                          key={index}
                          className="relative group"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ duration: 0.2 }}
                        >
                          <div className="overflow-hidden rounded-xl border border-border bg-muted">
                            <img
                              src={result.url}
                              alt={`Result ${index + 1}`}
                              width={result.width}
                              height={result.height}
                              className="h-auto w-full"
                            />
                            {/* Actions: shown on touch screens, on hover or focus elsewhere */}
                            <div className="absolute right-2 top-2 flex gap-2 transition-opacity duration-150 focus-within:opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                              <Button
                                size="sm"
                                variant="glass"
                                onClick={() => handleDownload(result.url, index)}
                              >
                                <Download className="h-4 w-4 mr-1" />
                                Download
                              </Button>
                            </div>
                          </div>
                          <div className="mt-1 flex justify-between px-1 text-xs text-muted-foreground">
                            <span>Result {index + 1}</span>
                            {result.width && result.height && (
                              <span className="font-mono tabular">{result.width} x {result.height}</span>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Error Display */}
              {error && (
                <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>
      </StaggerItem>

      {/* Bottom Bar (only on Step 3) */}
      {currentStep === 3 && (
        <VirtualBottomBar
          prompt={prompt}
          onPromptChange={setPrompt}
          aspectRatio={aspectRatio}
          onAspectRatioChange={setAspectRatio}
          editModel={editModel}
          onEditModelChange={setEditModel}
          numImages={numImages}
          onNumImagesChange={setNumImages}
          useDressBackground={useDressBackground}
          onUseDressBackgroundChange={setUseDressBackground}
          seed={seed}
          onSeedChange={setSeed}
          onGenerate={handleGenerate}
          isGenerating={isProcessing}
          canGenerate={canGenerate}
        />
      )}
    </Stagger>
  );
}
