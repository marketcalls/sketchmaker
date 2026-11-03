import { useState, useCallback } from 'react';
import { X, User, Shirt, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { MediaDropzone } from '@/components/media/MediaDropzone';

interface UploadedImage {
  url: string;
  name: string;
}

interface VirtualUploadStepProps {
  personImage: UploadedImage | null;
  dressImage: UploadedImage | null;
  onPersonImageChange: (image: UploadedImage | null) => void;
  onDressImageChange: (image: UploadedImage | null) => void;
  onNext: () => void;
}

export function VirtualUploadStep({
  personImage,
  dressImage,
  onPersonImageChange,
  onDressImageChange,
  onNext,
}: VirtualUploadStepProps) {
  const [error, setError] = useState<string | null>(null);

  const processFile = useCallback((file: File): Promise<UploadedImage | null> => {
    return new Promise((resolve) => {
      if (file.size > 25 * 1024 * 1024) {
        setError(`${file.name} is larger than 25 MB. Choose a smaller photo.`);
        resolve(null);
        return;
      }

      const reader = new FileReader();

      reader.onload = (e) => {
        const result = e.target?.result;
        if (typeof result !== 'string') {
          setError(`${file.name} could not be read. Try another photo.`);
          resolve(null);
          return;
        }
        resolve({
          url: result,
          name: file.name,
        });
      };
      reader.onerror = () => {
        setError(`${file.name} could not be read. Try another photo.`);
        resolve(null);
      };
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFileSelect = useCallback(async (file: File, type: 'person' | 'dress') => {
    if (!file.type.startsWith('image/')) {
      setError('Choose an image file (JPEG, PNG or WebP).');
      return;
    }

    const img = await processFile(file);
    if (img) {
      if (type === 'person') {
        onPersonImageChange(img);
      } else {
        onDressImageChange(img);
      }
      setError(null);
    }
  }, [processFile, onPersonImageChange, onDressImageChange]);

  const canProceed = personImage !== null && dressImage !== null;

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">Upload photos</h2>
        <p className="text-sm text-muted-foreground">
          A photo of yourself and a photo of the outfit you want to try on.
        </p>
      </div>

      {/* Upload Areas */}
      <div className="grid gap-4 md:gap-6 grid-cols-1 md:grid-cols-2">
        {/* Person Image Upload */}
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <MediaDropzone
              kinds={['image']}
              title="Add your photo"
              icon={User}
              label="Your photo"
              hint="Full body shot recommended"
              className="min-h-[280px] p-4 sm:min-h-[350px] sm:p-6"
              onFiles={(files) => handleFileSelect(files[0], 'person')}
            >
              {personImage ? (
                <div className="relative w-full h-full">
                  <img
                    src={personImage.url}
                    alt="Person"
                    className="w-full h-full object-contain rounded-lg max-h-[300px]"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onPersonImageChange(null);
                    }}
                    type="button"
                    aria-label="Remove photo"
                    title="Remove"
                    className="glass absolute top-2 right-2 rounded-md p-1.5 text-foreground transition-colors duration-150 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : undefined}
            </MediaDropzone>
          </CardContent>
        </Card>

        {/* Dress Image Upload */}
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <MediaDropzone
              kinds={['image']}
              title="Add an outfit image"
              icon={Shirt}
              label="Outfit image"
              hint="Clear product image works best"
              className="min-h-[280px] p-4 sm:min-h-[350px] sm:p-6"
              onFiles={(files) => handleFileSelect(files[0], 'dress')}
            >
              {dressImage ? (
                <div className="relative w-full h-full">
                  <img
                    src={dressImage.url}
                    alt="Dress"
                    className="w-full h-full object-contain rounded-lg max-h-[300px]"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDressImageChange(null);
                    }}
                    type="button"
                    aria-label="Remove photo"
                    title="Remove"
                    className="glass absolute top-2 right-2 rounded-md p-1.5 text-foreground transition-colors duration-150 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : undefined}
            </MediaDropzone>
          </CardContent>
        </Card>
      </div>

      {/* Status */}
      <div className="flex items-center gap-4 text-xs">
        <div className={`flex items-center gap-2 ${personImage ? 'text-success' : 'text-muted-foreground'}`}>
          <div className={`w-2 h-2 rounded-full ${personImage ? 'bg-success' : 'bg-muted'}`} />
          Your photo
        </div>
        <div className={`flex items-center gap-2 ${dressImage ? 'text-success' : 'text-muted-foreground'}`}>
          <div className={`w-2 h-2 rounded-full ${dressImage ? 'bg-success' : 'bg-muted'}`} />
          Outfit image
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-center text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Next Button */}
      <div className="flex justify-end">
        <Button
          size="lg"
          onClick={onNext}
          disabled={!canProceed}
          className="min-w-[200px]"
        >
          {canProceed ? (
            <>
              Choose setting
              <ArrowRight className="h-4 w-4 ml-2" />
            </>
          ) : (
            'Upload both photos to continue'
          )}
        </Button>
      </div>
    </div>
  );
}
