import { useState, useCallback } from 'react';
import { Upload, Download, Loader2, Image as ImageIcon, Lightbulb, Plus, X, Lock, Unlock, FileDown } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Stagger, StaggerItem } from '@/components/motion';
import apiClient from '@/api/client';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { useMediaPicker, type MediaPickerOptions } from '@/components/media/useMediaPicker';
import { getErrorMessage } from '@/utils/errors';

const MAX_IMAGES = 50;

interface UploadedImage {
  dataUrl: string;
  name: string;
  size: number;
  width: number;
  height: number;
}

interface ProcessedImage {
  filename: string;
  data_url: string;
  original_size: number;
  new_size: number;
  original_dimensions: string;
  new_dimensions: string;
  format: string;
  reduction_percent: number;
}

interface ReduceResult {
  images: ProcessedImage[];
  total_original_size: number;
  total_new_size: number;
  total_reduction_percent: number;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function ReducePage() {
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState<ProcessedImage[]>([]);
  const [totalStats, setTotalStats] = useState<{ original: number; reduced: number; percent: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Resize options
  const [resizeMode, setResizeMode] = useState<'percent' | 'pixels'>('percent');
  const [width, setWidth] = useState(70);
  const [height, setHeight] = useState(70);
  const [lockAspectRatio, setLockAspectRatio] = useState(true);

  // Output options
  const [outputFormat, setOutputFormat] = useState<'jpg' | 'png' | 'webp'>('jpg');
  const [quality, setQuality] = useState(90);
  const [dpi, setDpi] = useState(72);
  const [backgroundColor, setBackgroundColor] = useState<'white' | 'black'>('white');

  const processFile = useCallback((file: File): Promise<UploadedImage | null> => {
    return new Promise((resolve) => {
      if (file.size > 50 * 1024 * 1024) {
        setError(`${file.name} is larger than 50 MB. Choose a smaller image.`);
        resolve(null);
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        const img = new Image();
        img.onload = () => {
          resolve({
            dataUrl,
            name: file.name,
            size: file.size,
            width: img.width,
            height: img.height,
          });
        };
        img.onerror = () => resolve(null);
        img.src = dataUrl;
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
      setTotalStats(null);
      setError(null);
    }
  }, [processFile]);

  const imageOptions: Pick<MediaPickerOptions, 'kinds' | 'accept' | 'multiple' | 'maxFiles'> = {
    kinds: ['image'],
    accept: 'image/*',
    multiple: true,
    maxFiles: MAX_IMAGES,
  };
  const replacePicker = useMediaPicker({ ...imageOptions, title: 'Add images', onFiles: (files) => handleFilesSelect(files, false) });
  const addPicker = useMediaPicker({ ...imageOptions, title: 'Add more images', onFiles: (files) => handleFilesSelect(files, true) });

  const removeImage = (index: number) => {
    setUploadedImages(prev => prev.filter((_, i) => i !== index));
  };

  const handleWidthChange = (value: number) => {
    setWidth(value);
    if (lockAspectRatio && uploadedImages.length > 0 && resizeMode === 'pixels') {
      const firstImg = uploadedImages[0];
      const aspectRatio = firstImg.width / firstImg.height;
      setHeight(Math.round(value / aspectRatio));
    } else if (lockAspectRatio && resizeMode === 'percent') {
      setHeight(value);
    }
  };

  const handleHeightChange = (value: number) => {
    setHeight(value);
    if (lockAspectRatio && uploadedImages.length > 0 && resizeMode === 'pixels') {
      const firstImg = uploadedImages[0];
      const aspectRatio = firstImg.width / firstImg.height;
      setWidth(Math.round(value * aspectRatio));
    } else if (lockAspectRatio && resizeMode === 'percent') {
      setWidth(value);
    }
  };

  const handleProcess = async () => {
    if (uploadedImages.length === 0) {
      setError('Add at least one image first.');
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const requestData = {
        images: uploadedImages.map(img => ({
          data_url: img.dataUrl,
          filename: img.name,
        })),
        resize_mode: resizeMode,
        width: resizeMode === 'pixels' ? width : width,
        height: resizeMode === 'pixels' ? height : height,
        maintain_aspect_ratio: lockAspectRatio,
        output_format: outputFormat,
        quality,
        dpi,
        background_color: backgroundColor,
      };

      const response = await apiClient.post('/reduce/process', requestData);
      const data = response.data as ReduceResult;

      setResults(data.images);
      setTotalStats({
        original: data.total_original_size,
        reduced: data.total_new_size,
        percent: data.total_reduction_percent,
      });
    } catch (err: unknown) {
      // The API client has already made the detail readable.
      setError(getErrorMessage(err, 'The images could not be processed. Please try again.'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownload = (result: ProcessedImage) => {
    try {
      // Extract base64 data from data URL and convert to blob
      const [header, base64Data] = result.data_url.split(',');
      const mimeType = header.match(/:(.*?);/)?.[1] || 'image/jpeg';
      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: mimeType });

      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = result.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch {
      setError('The image could not be downloaded. Please try again.');
    }
  };

  const handleDownloadAll = async () => {
    if (results.length === 1) {
      handleDownload(results[0]);
      return;
    }

    // Download as ZIP for multiple files
    try {
      const requestData = {
        images: uploadedImages.map(img => ({
          data_url: img.dataUrl,
          filename: img.name,
        })),
        resize_mode: resizeMode,
        width,
        height,
        maintain_aspect_ratio: lockAspectRatio,
        output_format: outputFormat,
        quality,
        dpi,
        background_color: backgroundColor,
      };

      const response = await apiClient.post('/reduce/download-zip', requestData, {
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'application/zip' });
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `reduced_images_${Date.now()}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch {
      setError('The ZIP file could not be downloaded. Please try again.');
    }
  };

  const canProcess = uploadedImages.length > 0 && !isProcessing;

  return (
    <Stagger className="space-y-6" interval={0.08}>
      <StaggerItem>
        <header className="mb-2">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Reduce and Convert Images</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Resize, compress and convert images to JPG, PNG or WebP. No provider cost.
          </p>
        </header>
      </StaggerItem>

      <StaggerItem>
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column: Upload and Settings */}
        <div className="space-y-6">
          {/* Image Upload */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ImageIcon className="h-5 w-5 text-muted-foreground" />
                Images
              </CardTitle>
              <CardDescription>
                Up to {MAX_IMAGES} images, 50 MB each.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {uploadedImages.length === 0 ? (
                <MediaDropzone
                  {...imageOptions}
                  title="Add images"
                  icon={Upload}
                  label="Drop images here"
                  className="min-h-[200px]"
                  onFiles={(files) => handleFilesSelect(files, false)}
                />
              ) : (
                <div className="space-y-4">
                  <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 max-h-[300px] overflow-y-auto">
                    {uploadedImages.map((img, index) => (
                      <div key={index} className="relative group">
                        <div className="aspect-square overflow-hidden rounded-xl border border-border bg-muted">
                          <img
                            src={img.dataUrl}
                            alt={img.name}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => removeImage(index)}
                          disabled={isProcessing}
                          aria-label={`Remove ${img.name}`}
                          title="Remove"
                          className="glass absolute top-1 right-1 rounded-md p-1 text-foreground transition-opacity duration-150 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:opacity-0 sm:group-hover:opacity-100"
                        >
                          <X className="h-3 w-3" />
                        </button>
                        <div className="mt-1 truncate px-1 text-center text-[11px] text-muted-foreground">
                          <p className="truncate">{img.name}</p>
                          <p className="font-mono tabular">{img.width} x {img.height}</p>
                          <p className="font-mono tabular">{formatFileSize(img.size)}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-2">
                    <Button variant="outline" className="flex-1" onClick={replacePicker.open}>
                      Replace all
                    </Button>
                    <Button variant="outline" className="flex-1" onClick={addPicker.open}>
                      <Plus className="h-4 w-4 mr-2" />
                      Add more
                    </Button>
                  </div>
                </div>
              )}
              {replacePicker.dialog}
              {addPicker.dialog}
            </CardContent>
          </Card>

          {/* Resize Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Size</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Resize Mode */}
              <div className="space-y-2">
                <Label>Resize by</Label>
                <Select value={resizeMode} onValueChange={(v) => setResizeMode(v as 'percent' | 'pixels')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">Percentage</SelectItem>
                    <SelectItem value="pixels">Pixels</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Width & Height */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Width {resizeMode === 'percent' ? '(%)' : '(px)'}</Label>
                  <Input
                    type="number"
                    value={width}
                    onChange={(e) => handleWidthChange(parseInt(e.target.value) || 0)}
                    min={1}
                    max={resizeMode === 'percent' ? 200 : 10000}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Height {resizeMode === 'percent' ? '(%)' : '(px)'}</Label>
                  <Input
                    type="number"
                    value={height}
                    onChange={(e) => handleHeightChange(parseInt(e.target.value) || 0)}
                    min={1}
                    max={resizeMode === 'percent' ? 200 : 10000}
                  />
                </div>
              </div>

              {/* Aspect Ratio Lock */}
              <Button
                variant={lockAspectRatio ? 'secondary' : 'outline'}
                size="sm"
                onClick={() => setLockAspectRatio(!lockAspectRatio)}
                className="w-full"
              >
                {lockAspectRatio ? <Lock className="h-4 w-4 mr-2" /> : <Unlock className="h-4 w-4 mr-2" />}
                {lockAspectRatio ? 'Aspect ratio locked' : 'Aspect ratio unlocked'}
              </Button>

              {/* DPI */}
              <div className="space-y-2">
                <Label>Resolution (DPI)</Label>
                <Input
                  type="number"
                  value={dpi}
                  onChange={(e) => setDpi(parseInt(e.target.value) || 72)}
                  min={1}
                  max={600}
                />
              </div>
            </CardContent>
          </Card>

          {/* Output Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Output</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Format */}
              <div className="space-y-2">
                <Label>Format</Label>
                <Select value={outputFormat} onValueChange={(v) => setOutputFormat(v as 'jpg' | 'png' | 'webp')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="jpg">JPG</SelectItem>
                    <SelectItem value="png">PNG</SelectItem>
                    <SelectItem value="webp">WebP</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Quality */}
              <div className="space-y-2">
                <div className="flex justify-between">
                  <Label>Quality</Label>
                  <span className="font-mono tabular text-xs text-muted-foreground">{quality}%</span>
                </div>
                <Slider
                  value={[quality]}
                  onValueChange={(v) => setQuality(v[0])}
                  min={1}
                  max={100}
                  step={1}
                />
              </div>

              {/* Background Color (for transparent to JPG) */}
              {outputFormat === 'jpg' && (
                <div className="space-y-2">
                  <Label>Background (for transparent images)</Label>
                  <div className="flex gap-2">
                    <Button
                      variant={backgroundColor === 'white' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => setBackgroundColor('white')}
                      className={`flex items-center gap-2 ${backgroundColor === 'white' ? 'ring-2 ring-primary' : ''}`}
                    >
                      <span className="h-4 w-4 rounded-full border border-border" style={{ backgroundColor: '#fff' }}></span>
                      White
                    </Button>
                    <Button
                      variant={backgroundColor === 'black' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => setBackgroundColor('black')}
                      className={`flex items-center gap-2 ${backgroundColor === 'black' ? 'ring-2 ring-primary' : ''}`}
                    >
                      <span className="h-4 w-4 rounded-full border border-border" style={{ backgroundColor: '#000' }}></span>
                      Black
                    </Button>
                  </div>
                </div>
              )}

              {error && (
                <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              {/* Process Button */}
              <Button className="w-full" onClick={handleProcess} disabled={!canProcess} size="lg">
                {isProcessing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Processing
                  </>
                ) : (
                  <>
                    Resize {uploadedImages.length > 0 ? `${uploadedImages.length} image${uploadedImages.length > 1 ? 's' : ''}` : 'images'}
                  </>
                )}
              </Button>

              <p className="text-center text-xs text-muted-foreground">
                No provider cost.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Results */}
        <div className="space-y-6">
          {results.length > 0 ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-baseline gap-2">
                  Results
                  <span className="text-sm font-normal tabular text-muted-foreground">{results.length}</span>
                </CardTitle>
                {totalStats && (
                  <div className="mt-3 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border">
                    <div className="bg-card p-3 text-center">
                      <p className="font-mono tabular text-lg font-medium">{formatFileSize(totalStats.original)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">Before</p>
                    </div>
                    <div className="bg-card p-3 text-center">
                      <p className="font-mono tabular text-lg font-medium">{formatFileSize(totalStats.reduced)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">After</p>
                    </div>
                    <div className="bg-card p-3 text-center">
                      <p className={`font-mono tabular text-lg font-medium ${totalStats.percent > 0 ? 'text-success' : 'text-warning'}`}>
                        {totalStats.percent > 0 ? `-${totalStats.percent}%` : `+${Math.abs(totalStats.percent)}%`}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">Size change</p>
                    </div>
                  </div>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3 max-h-[500px] overflow-y-auto">
                  {results.map((result, index) => (
                    <div key={index} className="flex items-center gap-3 rounded-lg border border-border bg-secondary/20 p-3">
                      <div className="h-16 w-16 flex-shrink-0 overflow-hidden rounded-lg border border-border bg-muted">
                        <img src={result.data_url} alt={result.filename} className="w-full h-full object-cover" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{result.filename}</p>
                        <p className="font-mono tabular text-[11px] text-muted-foreground">
                          {result.original_dimensions} to {result.new_dimensions}
                        </p>
                        <p className="font-mono tabular text-[11px] text-muted-foreground">
                          {formatFileSize(result.original_size)} to {formatFileSize(result.new_size)}
                          <span className={result.reduction_percent > 0 ? 'text-success ml-1' : 'text-warning ml-1'}>
                            ({result.reduction_percent > 0 ? `-${result.reduction_percent}%` : `+${Math.abs(result.reduction_percent)}%`})
                          </span>
                        </p>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => handleDownload(result)} aria-label={`Download ${result.filename}`} title="Download">
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>

                <Button variant="secondary" onClick={handleDownloadAll} className="w-full">
                  <Download className="mr-2 h-4 w-4" />
                  {results.length > 1 ? 'Download all (ZIP)' : 'Download'}
                </Button>
              </CardContent>
            </Card>
            </motion.div>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Results</CardTitle>
                <CardDescription>Each file with its new size and dimensions.</CardDescription>
              </CardHeader>
              <CardContent>
                {isProcessing ? (
                  <div className="space-y-3" aria-busy="true">
                    <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
                      Processing {uploadedImages.length} image{uploadedImages.length > 1 ? 's' : ''}.
                    </p>
                    {/* Rows in the shape of the results list */}
                    {uploadedImages.slice(0, 6).map((_, index) => (
                      <div key={index} className="beam-border flex items-center gap-3 rounded-lg border border-border bg-secondary/20 p-3">
                        <div className="shimmer h-16 w-16 flex-shrink-0 rounded-lg bg-muted" />
                        <div className="flex-1 space-y-2">
                          <div className="shimmer h-3 w-2/3 rounded bg-muted" />
                          <div className="shimmer h-2.5 w-1/2 rounded bg-muted" />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex aspect-video items-center justify-center rounded-xl border border-border bg-secondary/20 p-6">
                    <div className="max-w-xs text-center">
                      <FileDown className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
                      <p className="font-semibold tracking-tight">No results yet</p>
                      <p className="mt-1 text-sm text-muted-foreground">Add images, set the size and format, then choose Resize.</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Tips */}
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
                  Use percentage mode to reduce all images proportionally
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  WebP format offers best compression with quality
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  Lower quality gives a smaller file
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  72 DPI is standard for web, 300 DPI for print
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  PNG preserves transparency, JPG does not
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
