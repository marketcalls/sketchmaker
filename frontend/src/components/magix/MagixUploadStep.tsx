import { useState, useCallback } from 'react';
import { Upload, X, Plus, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { useMediaPicker } from '@/components/media/useMediaPicker';

export interface UploadedImage {
  url: string;
  name: string;
  // The one job this photo has when it is not the photo being edited
  // (edit_prompts.IMAGE_ROLES on the server).
  role?: MagixRole;
  width?: number;
  height?: number;
}

export type MagixRole = 'subject' | 'scene' | 'style' | 'outfit' | 'product' | 'light';

export const MAGIX_ROLES: { value: MagixRole; label: string; hint: string }[] = [
  { value: 'subject', label: 'Person', hint: 'Add this person' },
  { value: 'scene', label: 'Scene', hint: 'Use this place as the setting' },
  { value: 'style', label: 'Style', hint: 'Copy only the look: colour, grain, light quality' },
  { value: 'outfit', label: 'Outfit', hint: 'Dress the person in this outfit' },
  { value: 'product', label: 'Product', hint: 'Add this exact product' },
  { value: 'light', label: 'Light', hint: 'Match only the lighting' },
];

interface MagixUploadStepProps {
  uploadedImages: UploadedImage[];
  onImagesChange: (images: UploadedImage[]) => void;
  onNext: () => void;
}

export function MagixUploadStep({ uploadedImages, onImagesChange, onNext }: MagixUploadStepProps) {
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
        const url = e.target?.result as string;
        // The size is kept so the page can warn about edit models that pad
        // extreme shapes.
        const probe = new Image();
        probe.onload = () => resolve({ url, name: file.name, role: 'subject', width: probe.naturalWidth, height: probe.naturalHeight });
        probe.onerror = () => resolve({ url, name: file.name, role: 'subject' });
        probe.src = url;
      };
      reader.onerror = () => {
        setError(`${file.name} could not be read. Try another photo.`);
        resolve(null);
      };
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
        onImagesChange([...uploadedImages, ...newImages]);
      } else {
        onImagesChange(newImages);
      }
      setError(null);
    }
  }, [processFile, onImagesChange, uploadedImages]);

  const replacePicker = useMediaPicker({
    kinds: ['image'],
    multiple: true,
    title: 'Add photos',
    onFiles: (files) => handleFilesSelect(files, false),
  });
  const addPicker = useMediaPicker({
    kinds: ['image'],
    multiple: true,
    title: 'Add more photos',
    onFiles: (files) => handleFilesSelect(files, true),
  });

  const removeImage = (index: number) => {
    onImagesChange(uploadedImages.filter((_, i) => i !== index));
  };

  const setRole = (index: number, role: MagixRole) => {
    onImagesChange(uploadedImages.map((img, i) => (i === index ? { ...img, role } : img)));
  };

  const canProceed = uploadedImages.length > 0;

  return (
    <div className="max-w-3xl space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">Upload photos</h2>
        <p className="max-w-prose text-pretty text-sm text-muted-foreground">
          Upload the photo to edit. Add more photos to lend one thing each: a person, a scene, a style, an outfit, a
          product or the light.
        </p>
      </div>

      {/* Upload Area */}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          {uploadedImages.length === 0 ? (
            <MediaDropzone
              kinds={['image']}
              multiple
              title="Add photos"
              icon={Upload}
              label="Drop photos here"
              hint="JPEG, PNG, WebP up to 25MB"
              className="min-h-[300px] p-8 sm:min-h-[400px] sm:p-12"
              onFiles={(files) => handleFilesSelect(files, false)}
            />
          ) : (
            <div className="p-4 space-y-4">
              {/* Image Grid */}
              <div
                className={`grid gap-3 ${
                  uploadedImages.length === 1 ? 'grid-cols-1 max-w-md mx-auto' :
                  uploadedImages.length === 2 ? 'grid-cols-2' :
                  'grid-cols-2 md:grid-cols-3'
                }`}
                {...addPicker.dropProps}
              >
                {uploadedImages.map((img, index) => (
                  <div key={index} className="space-y-2">
                    <div className="relative group aspect-square">
                      <div className="h-full w-full overflow-hidden rounded-xl border border-border bg-muted">
                        <img
                          src={img.url}
                          alt={img.name}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeImage(index)}
                        aria-label={`Remove ${img.name}`}
                        title="Remove"
                        className="glass absolute top-2 right-2 rounded-md p-1.5 text-foreground transition-opacity duration-150 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:opacity-0 sm:group-hover:opacity-100"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    {/* One job per photo: the first is the one you edit,
                        every other lends only its role. */}
                    {uploadedImages.length > 1 && (
                      index === 0 ? (
                        <p className="text-xs font-medium text-foreground">
                          Photo 1: the one you edit
                        </p>
                      ) : (
                        <Select value={img.role || 'subject'} onValueChange={(v) => setRole(index, v as MagixRole)}>
                          <SelectTrigger
                            aria-label={`Role of photo ${index + 1}`}
                            className="h-8 rounded-md border border-border bg-transparent px-2.5 text-xs"
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {MAGIX_ROLES.map((r) => (
                              <SelectItem key={r.value} value={r.value}>
                                <span className="flex flex-col">
                                  <span>Photo {index + 1}: {r.label}</span>
                                  <span className="text-[11px] text-muted-foreground">{r.hint}</span>
                                </span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )
                    )}
                  </div>
                ))}
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={replacePicker.open}
                >
                  Replace all
                </Button>
                <Button
                  variant="outline"
                  onClick={addPicker.open}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add more
                </Button>
              </div>

              <p className="text-center text-xs tabular text-muted-foreground">
                {uploadedImages.length} photo{uploadedImages.length > 1 ? 's' : ''} ready
              </p>
            </div>
          )}
          {replacePicker.dialog}
          {addPicker.dialog}
        </CardContent>
      </Card>

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
              Choose style
              <ArrowRight className="h-4 w-4 ml-2" />
            </>
          ) : (
            'Upload a photo to continue'
          )}
        </Button>
      </div>
    </div>
  );
}
