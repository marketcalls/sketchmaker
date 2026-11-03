import { useState, useCallback } from 'react';
import { X, Video, Link, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import type { Asset } from '@/api/assets';
import { cn } from '@/lib/utils';

interface VideoUploaderProps {
  videoFile: File | null;
  videoPreview: string | null;
  videoUrl: string | null;
  // Shown under the preview when the video is not a picked file.
  sourceLabel?: string;
  onFileChange: (file: File | null) => void;
  onUrlChange: (url: string | null) => void;
  maxSizeMB?: number;
  className?: string;
  // Media window copy and checks for videos picked from My Assets.
  pickerTitle?: string;
  pickerDescription?: string;
  unusableReason?: (asset: Asset) => string | null;
  // Library picks go here (read by id on the server) instead of being downloaded as a File.
  onAssets?: (assets: Asset[]) => void | Promise<void>;
}

export function VideoUploader({
  videoFile,
  videoPreview,
  videoUrl,
  sourceLabel,
  onFileChange,
  onUrlChange,
  maxSizeMB = 100,
  className,
  pickerTitle,
  pickerDescription,
  unusableReason,
  onAssets,
}: VideoUploaderProps) {
  const [error, setError] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState(videoUrl || '');
  const [activeTab, setActiveTab] = useState<string>(videoUrl ? 'url' : 'upload');

  const validateFile = useCallback((file: File): boolean => {
    // Check MIME type OR file extension (some browsers don't report MIME correctly)
    // The formats Kling Motion Control takes (the server checks the real bytes).
    const allowedTypes = ['video/mp4', 'video/webm', 'video/quicktime', 'video/x-m4v'];
    const allowedExtensions = ['.mp4', '.webm', '.mov', '.m4v'];

    const fileName = file.name.toLowerCase();
    const hasValidExtension = allowedExtensions.some(ext => fileName.endsWith(ext));
    const hasValidMimeType = file.type === '' || allowedTypes.includes(file.type);

    // Accept if either extension OR MIME type is valid
    if (!hasValidExtension && !hasValidMimeType) {
      setError('Please select a video file: MP4, MOV, WebM or M4V');
      return false;
    }

    if (file.size > maxSizeMB * 1024 * 1024) {
      setError(`File size must be less than ${maxSizeMB}MB`);
      return false;
    }

    return true;
  }, [maxSizeMB]);

  const handleFileSelect = useCallback((file: File) => {
    console.log('[VideoUploader] handleFileSelect called for:', file.name);
    if (!validateFile(file)) {
      console.log('[VideoUploader] File validation failed');
      return;
    }

    console.log('[VideoUploader] File validated successfully, calling onFileChange');
    setError(null);
    onFileChange(file);
    onUrlChange(null);
  }, [validateFile, onFileChange, onUrlChange]);

  const handleUrlSubmit = () => {
    if (!urlInput.trim()) {
      setError('Please enter a video URL');
      return;
    }

    // Basic URL validation
    try {
      new URL(urlInput);
    } catch {
      setError('Please enter a valid URL');
      return;
    }

    setError(null);
    onUrlChange(urlInput.trim());
    onFileChange(null);
  };

  const clearVideo = () => {
    onFileChange(null);
    onUrlChange(null);
    setUrlInput('');
    setError(null);
  };

  const hasVideo = videoFile !== null || videoUrl !== null;

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardContent className="p-4">
        {hasVideo ? (
          // Preview
          <div className="relative">
            <div className="aspect-video bg-muted rounded-xl border border-border overflow-hidden flex items-center justify-center">
              <video
                key={videoPreview || videoUrl}
                src={videoPreview || videoUrl || undefined}
                className="w-full h-full object-contain"
                controls
                muted
                loop
                autoPlay
                playsInline
                onError={(e) => console.error('[VideoUploader] Video load error:', e)}
              />
            </div>
            <button
              type="button"
              onClick={clearVideo}
              aria-label="Remove video"
              title="Remove video"
              className="glass absolute top-2 right-2 rounded-md p-1.5 text-foreground transition-colors duration-150 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="h-4 w-4" />
            </button>
            <div className="mt-2 truncate text-center text-xs text-muted-foreground">
              {videoFile ? videoFile.name : sourceLabel ?? 'Video from URL'}
            </div>
          </div>
        ) : (
          // Upload/URL tabs
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-2 mb-4">
              <TabsTrigger value="upload">
                <Upload className="h-4 w-4 mr-2" />
                Upload
              </TabsTrigger>
              <TabsTrigger value="url">
                <Link className="h-4 w-4 mr-2" />
                URL
              </TabsTrigger>
            </TabsList>

            <TabsContent value="upload" className="mt-0">
              <MediaDropzone
                kinds={['video']}
                icon={Video}
                label="Motion reference video"
                hint={`MP4, MOV, WebM or M4V, max ${maxSizeMB} MB`}
                title={pickerTitle}
                description={pickerDescription}
                unusableReason={unusableReason}
                onFiles={(files) => handleFileSelect(files[0])}
                onAssets={onAssets}
                className="min-h-[200px]"
              />
            </TabsContent>

            <TabsContent value="url" className="mt-0">
              <div className="space-y-4 min-h-[200px] flex flex-col justify-center">
                <Link className="mx-auto h-6 w-6 text-muted-foreground" />
                <div className="text-center">
                  <p className="font-medium">Video URL</p>
                  <p className="text-muted-foreground text-sm">Paste a direct link to a video file.</p>
                </div>
                <div className="flex gap-2">
                  <Input
                    type="url"
                    placeholder="https://example.com/video.mp4"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    aria-label="Video URL"
                    onKeyDown={(e) => e.key === 'Enter' && handleUrlSubmit()}
                    className="flex-1"
                  />
                  <Button onClick={handleUrlSubmit}>Use URL</Button>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        )}

        {/* Error Display */}
        {error && (
          <div role="alert" className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-center text-sm text-destructive">
            {error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default VideoUploader;
