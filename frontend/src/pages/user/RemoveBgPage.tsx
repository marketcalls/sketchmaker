import { useState, useCallback } from 'react';
import { Upload, Download, Loader2, RotateCcw, Image as ImageIcon, Lightbulb, Plus, X, Eraser } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatUsd, REMOVE_BG_KEY, usePricingStore } from '@/stores/pricingStore';
import { Stagger, StaggerItem } from '@/components/motion';
import apiClient from '@/api/client';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { getErrorMessage } from '@/utils/errors';
import { useElapsedSeconds, formatElapsed } from '@/components/generate';

// The backend takes up to 20 images per batch (MAX_BATCH_IMAGES).
const MAX_IMAGES = 20;

interface UploadedImage {
  url: string;
  name: string;
}

interface RemoveBgImageResult {
  url: string;
  gallery_id: number | null;
  width: number | null;
  height: number | null;
}

interface RemoveBgResult {
  image_url?: string;
  images?: RemoveBgImageResult[];
  gallery_id?: number | null;
  width?: number | null;
  height?: number | null;
  estimated_usd: number;
}

export function RemoveBgPage() {
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState<RemoveBgImageResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [costUsed, setCostUsed] = useState<number>(0);

  const { getModelCost } = usePricingStore();
  // Flat price per image from the live table.
  const perImage = getModelCost(REMOVE_BG_KEY);

  const processFile = useCallback((file: File): Promise<UploadedImage | null> => {
    return new Promise((resolve) => {
      if (file.size > 25 * 1024 * 1024) {
        setError(`${file.name} is larger than 25 MB. Choose a smaller image.`);
        resolve(null);
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        resolve({
          url: e.target?.result as string,
          name: file.name,
        });
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFilesSelect = useCallback(async (files: FileList | File[], append = false) => {
    const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) return;

    const newImages: UploadedImage[] = [];
    for (const file of imageFiles) {
      const img = await processFile(file);
      if (img) newImages.push(img);
    }

    if (newImages.length > 0) {
      if (append) {
        setUploadedImages(prev => [...prev, ...newImages]);
      } else {
        setUploadedImages(newImages);
      }
      setResults([]);
      setError(null);
    }
  }, [processFile]);

  const replacePicker = useMediaPicker({
    kinds: ['image'],
    multiple: true,
    maxFiles: MAX_IMAGES,
    title: 'Add images',
    onFiles: (files) => handleFilesSelect(files, false),
  });
  const addPicker = useMediaPicker({
    kinds: ['image'],
    multiple: true,
    maxFiles: MAX_IMAGES,
    title: 'Add more images',
    onFiles: (files) => handleFilesSelect(files, true),
  });

  const removeImage = (index: number) => {
    setUploadedImages(prev => prev.filter((_, i) => i !== index));
  };

  const handleGenerate = async () => {
    if (uploadedImages.length === 0) {
      setError('Add at least one image first.');
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const requestData: Record<string, unknown> = {
        image_urls: uploadedImages.map(img => img.url),
      };

      const response = await apiClient.post('/remove-bg/generate', requestData);
      const data = response.data as RemoveBgResult;

      // Handle both single and batch results
      if (data.images && data.images.length > 0) {
        setResults(data.images);
      } else if (data.image_url) {
        setResults([{
          url: data.image_url,
          gallery_id: data.gallery_id || null,
          width: data.width || null,
          height: data.height || null,
        }]);
      }
      setCostUsed(data.estimated_usd);
    } catch (err: unknown) {
      // The API client has already made the detail readable.
      setError(getErrorMessage(err, 'The backgrounds could not be removed. Please try again.'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownload = async (url: string, index: number) => {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `removed_bg_${index + 1}_${Date.now()}.png`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch {
      setError('The image could not be downloaded. Please try again.');
    }
  };

  const handleDownloadAll = async () => {
    for (let i = 0; i < results.length; i++) {
      await handleDownload(results[i].url, i);
      // Small delay between downloads
      await new Promise(resolve => setTimeout(resolve, 300));
    }
  };

  const handleUseAsInput = (url: string) => {
    setUploadedImages([{ url, name: 'Processed Image' }]);
    setResults([]);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleRegenerate = () => {
    handleGenerate();
  };

  const canGenerate = uploadedImages.length > 0 && !isProcessing;
  const elapsed = useElapsedSeconds(isProcessing);

  return (
    <Stagger className="space-y-6" interval={0.08}>
      <StaggerItem>
        <header className="mb-2">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Remove Background</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Cut out the subject of up to {MAX_IMAGES} images at once and download transparent PNGs.
          </p>
        </header>
      </StaggerItem>

      <StaggerItem>
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column: Upload and Controls */}
        <div className="space-y-6">
          {/* Image Upload/Preview */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ImageIcon className="h-5 w-5 text-muted-foreground" />
                Images
              </CardTitle>
              <CardDescription>
                One image, or a batch of up to {MAX_IMAGES}.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {uploadedImages.length === 0 ? (
                <MediaDropzone
                  kinds={['image']}
                  multiple
                  maxFiles={MAX_IMAGES}
                  title="Add images"
                  icon={Upload}
                  label="Drop images here"
                  hint={`Up to ${MAX_IMAGES} images for batch processing`}
                  className="min-h-[250px] sm:min-h-[400px]"
                  onFiles={(files) => handleFilesSelect(files, false)}
                />
              ) : (
                <div className="space-y-4">
                  {/* Image Grid */}
                  <div
                    className={`grid gap-3 ${
                      uploadedImages.length === 1 ? 'grid-cols-1' :
                      uploadedImages.length === 2 ? 'grid-cols-2' :
                      'grid-cols-2 md:grid-cols-3'
                    }`}
                    {...addPicker.dropProps}
                  >
                    {uploadedImages.map((img, index) => (
                      <div key={index} className="relative group">
                        <div className="overflow-hidden rounded-xl border border-border bg-muted">
                          <img
                            src={img.url}
                            alt={img.name}
                            className="w-full h-auto max-h-[200px] object-contain"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => removeImage(index)}
                          disabled={isProcessing}
                          aria-label={`Remove ${img.name}`}
                          title="Remove"
                          className="glass absolute top-2 right-2 rounded-md p-1.5 text-foreground transition-opacity duration-150 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:opacity-0 sm:group-hover:opacity-100"
                        >
                          <X className="h-3 w-3" />
                        </button>
                        <p className="mt-1 truncate text-center text-[11px] text-muted-foreground">
                          {img.name}
                        </p>
                      </div>
                    ))}
                  </div>

                  {/* Action Buttons */}
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={replacePicker.open}
                    >
                      Replace all
                    </Button>
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={addPicker.open}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Add more
                    </Button>
                  </div>
                  <p className="text-center text-xs tabular text-muted-foreground">
                    {uploadedImages.length} image{uploadedImages.length > 1 ? 's' : ''} uploaded
                  </p>
                </div>
              )}
              {replacePicker.dialog}
              {addPicker.dialog}
            </CardContent>
          </Card>

          {/* Process Button */}
          <Card>
            <CardContent className="pt-6 space-y-4">
              {error && (
                <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              {/* Generate Button */}
              <Button
                className="w-full"
                onClick={handleGenerate}
                disabled={!canGenerate}
                size="lg"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Removing backgrounds
                  </>
                ) : (
                  <>
                    Remove background{uploadedImages.length > 1 ? ` from ${uploadedImages.length} images` : ''}
                  </>
                )}
              </Button>

              <p className="min-h-4 text-center text-xs text-muted-foreground">
                {perImage === undefined
                  ? ''
                  : uploadedImages.length > 0
                    ? <><span className="font-mono tabular text-foreground">{formatUsd(perImage * uploadedImages.length)}</span> for this batch</>
                    : <><span className="font-mono tabular text-foreground">{formatUsd(perImage)}</span> per image</>}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Results */}
        <div className="space-y-6">
          {/* Result Section */}
          {results.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-baseline gap-2">
                  Results
                  <span className="text-sm font-normal tabular text-muted-foreground">{results.length}</span>
                </CardTitle>
                <CardDescription className="text-xs">
                  <span className="font-mono tabular">{formatUsd(costUsed)}</span> used
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Results Grid */}
                <div className="space-y-4">
                  {results.map((result, index) => (
                    <motion.div
                      key={index}
                      className="relative group"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.2 }}
                    >
                      <div className="overflow-hidden rounded-xl border border-border bg-[repeating-conic-gradient(var(--color-secondary)_0%_25%,transparent_0%_50%)_50%/20px_20px] p-2">
                        <img
                          src={result.url}
                          alt={`Result ${index + 1}`}
                          width={result.width ?? undefined}
                          height={result.height ?? undefined}
                          className="h-auto w-full rounded-lg"
                        />
                        {/* Actions: shown on touch screens, on hover or focus elsewhere */}
                        <div className="absolute right-4 top-4 flex flex-wrap justify-end gap-2 transition-opacity duration-150 focus-within:opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                          <Button
                            size="sm"
                            variant="glass"
                            onClick={() => handleDownload(result.url, index)}
                          >
                            <Download className="h-4 w-4 mr-1" />
                            Download PNG
                          </Button>
                          <Button
                            size="sm"
                            variant="glass"
                            onClick={() => handleUseAsInput(result.url)}
                          >
                            <RotateCcw className="h-4 w-4 mr-1" />
                            Use as input
                          </Button>
                        </div>
                      </div>
                      {/* Result info */}
                      <div className="mt-1 flex justify-between px-1 text-xs text-muted-foreground">
                        <span>Result {index + 1}</span>
                        {result.width && result.height && (
                          <span className="font-mono tabular">{result.width} x {result.height}</span>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>

                {/* Batch Actions */}
                <div className="flex gap-3">
                  {results.length > 1 && (
                    <Button variant="secondary" onClick={handleDownloadAll} className="flex-1">
                      <Download className="mr-2 h-4 w-4" />
                      Download all
                    </Button>
                  )}
                  <Button variant="outline" onClick={handleRegenerate} className="flex-1">
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Process again
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Results</CardTitle>
                <CardDescription>Transparent PNGs, saved to your gallery.</CardDescription>
              </CardHeader>
              <CardContent>
                {isProcessing ? (
                  <div className="space-y-4" aria-busy="true">
                    <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
                      Removing backgrounds from {uploadedImages.length} image{uploadedImages.length > 1 ? 's' : ''}, usually a few seconds each.{' '}
                      <span className="font-mono tabular text-foreground">{formatElapsed(elapsed)}</span>
                    </p>
                    {/* Placeholders in each input's own shape, so results do not jump in */}
                    {uploadedImages.map((img, index) => (
                      <div key={index} className="beam-border relative overflow-hidden rounded-xl border border-border bg-card p-2">
                        <img src={img.url} alt="" aria-hidden="true" className="h-auto w-full rounded-lg opacity-30" />
                        <div className="shimmer absolute inset-2 rounded-lg" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex aspect-square items-center justify-center rounded-xl border border-border bg-secondary/20 p-6">
                    <div className="max-w-xs text-center">
                      <Eraser className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
                      <p className="font-semibold tracking-tight">No results yet</p>
                      <p className="mt-1 text-sm text-muted-foreground">Add images, then choose Remove background.</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Tips Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Lightbulb className="h-5 w-5 text-muted-foreground" />
                Tips
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="text-sm space-y-2 text-muted-foreground">
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  Use images with clear subjects and defined edges
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  Works best with product photos and portraits
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  Results are saved as transparent PNGs
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  Batch process multiple images at once
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  All results are saved to your gallery
                </li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
      </StaggerItem>
    </Stagger>
  );
}
