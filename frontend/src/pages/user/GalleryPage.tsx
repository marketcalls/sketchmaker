import { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Download, Trash2, ChevronLeft, ChevronRight, ChevronDown, ImageIcon, Video } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useGalleryStore } from '@/stores/galleryStore';
import { useVideoStore } from '@/stores/videoStore';
import { getModelDisplayName } from '@/utils/models';
import { apiClient } from '@/api/client';
import { VideoGalleryTab } from '@/components/gallery/VideoGalleryTab';
import { Stagger, StaggerItem } from '@/components/motion';
import { LogoSurface, PNG_EXPORT_SIZE, downloadBlob, fetchSvgText, isSvgImage, svgToPngBlob } from '@/components/logo';
import { AddTextDialog } from '@/components/text-overlay/AddTextDialog';
import type { GeneratedImage } from '@/types';

export function GalleryPage() {
  const [activeTab, setActiveTab] = useState('images');
  const {
    images,
    total,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    selectedImage,
    fetchGallery,
    loadMore,
    deleteImage,
    selectImage,
  } = useGalleryStore();

  const { galleryTotal: videoTotal } = useVideoStore();

  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  // Add text: the editor opens on its own (the details dialog closes first).
  const [textImage, setTextImage] = useState<GeneratedImage | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Fetch initial data on mount
  useEffect(() => {
    fetchGallery();
  }, [fetchGallery]);

  // Infinite scroll observer
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore || isLoadingMore || isLoading) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore && !isLoading) {
          loadMore();
        }
      },
      {
        root: null,
        rootMargin: '200px',
        threshold: 0,
      }
    );

    observer.observe(sentinel);

    // Check immediately if sentinel is already visible (for small viewports)
    const rect = sentinel.getBoundingClientRect();
    const isVisible = rect.top < window.innerHeight + 200;
    if (isVisible && hasMore && !isLoadingMore && !isLoading) {
      loadMore();
    }

    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, isLoading, loadMore]);

  // Logos are stored as SVG: offer the vector file, and a PNG rendered in the
  // browser (the server does not rasterise).
  const handleSvgDownload = async (image: GeneratedImage, format: 'svg' | 'png') => {
    try {
      if (format === 'svg') {
        const response = await apiClient.get(`/gallery/${image.id}/download/svg`, { responseType: 'blob' });
        downloadBlob(new Blob([response.data], { type: 'image/svg+xml' }), `image-${image.id}.svg`);
      } else {
        const text = await fetchSvgText(image.url, image.id);
        downloadBlob(await svgToPngBlob(text, PNG_EXPORT_SIZE), `image-${image.id}.png`);
      }
    } catch {
      window.open(image.url, '_blank', 'noopener');
    }
  };

  const handleDownload = async (image: GeneratedImage, format: 'png' | 'webp' | 'jpg' | 'svg' = 'png') => {
    if (isSvgImage(image)) {
      await handleSvgDownload(image, format === 'svg' ? 'svg' : 'png');
      return;
    }
    if (format === 'svg') return;
    try {
      const response = await apiClient.get(`/gallery/${image.id}/download/${format}`, {
        responseType: 'blob',
      });
      const blob = new Blob([response.data], { type: `image/${format}` });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `image-${image.id}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // Fallback to direct URL download
      const response = await fetch(image.url);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ext = image.url.split('.').pop() || 'png';
      a.download = `image-${image.id}.${ext}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    }
  };

  const handleDelete = async (imageId: number) => {
    try {
      await deleteImage(imageId);
      setDeleteConfirm(null);
    } catch {
      // Error handled by store
    }
  };

  // Left and right arrows step through the gallery while the details are open.
  useEffect(() => {
    if (!selectedImage) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
      const index = images.findIndex((img) => img.id === selectedImage.id);
      if (e.key === 'ArrowLeft' && index > 0) selectImage(images[index - 1]);
      if (e.key === 'ArrowRight' && index >= 0 && index < images.length - 1) selectImage(images[index + 1]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedImage, images, selectImage]);

  const handlePrevImage = () => {
    if (!selectedImage) return;
    const currentIndex = images.findIndex((img) => img.id === selectedImage.id);
    if (currentIndex > 0) {
      selectImage(images[currentIndex - 1]);
    }
  };

  const handleNextImage = () => {
    if (!selectedImage) return;
    const currentIndex = images.findIndex((img) => img.id === selectedImage.id);
    if (currentIndex < images.length - 1) {
      selectImage(images[currentIndex + 1]);
    }
  };

  return (
    <Stagger className="space-y-6" interval={0.08}>
      <StaggerItem>
        <header className="mb-2">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Gallery</h1>
          <p className="mt-1 text-sm text-muted-foreground">Every image and video you have made, newest first.</p>
        </header>
      </StaggerItem>

      {/* Tabs for Images and Videos */}
      <StaggerItem>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList>
            <TabsTrigger value="images" className="flex items-center gap-2">
              <ImageIcon className="h-4 w-4" />
              Images
              {total > 0 && <span className="text-xs tabular text-muted-foreground">{total}</span>}
            </TabsTrigger>
            <TabsTrigger value="videos" className="flex items-center gap-2">
              <Video className="h-4 w-4" />
              Videos
              {videoTotal > 0 && <span className="text-xs tabular text-muted-foreground">{videoTotal}</span>}
            </TabsTrigger>
          </TabsList>

          {/* Images Tab Content */}
          <TabsContent value="images" className="space-y-6">
            {error && (
              <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
                {error}
              </div>
            )}

            {isLoading && images.length === 0 ? (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4" aria-busy="true" aria-label="Loading images">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="shimmer aspect-square rounded-xl bg-muted" />
                ))}
              </div>
            ) : images.length > 0 ? (
              <>
                <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
                  {images.map((image) => (
                    <div
                      key={image.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`Open details: ${image.prompt}`}
                      className="group relative aspect-square cursor-pointer overflow-hidden rounded-xl border border-border bg-muted transition-colors duration-150 hover:border-foreground/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => selectImage(image)}
                      onKeyDown={(e) => {
                        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault();
                          selectImage(image);
                        }
                      }}
                    >
                      {isSvgImage(image) ? (
                        <LogoSurface surface="paper" className="flex h-full w-full items-center justify-center p-5">
                          <img
                            src={image.url}
                            alt={image.prompt}
                            loading="lazy"
                            className="max-h-full max-w-full object-contain"
                          />
                        </LogoSurface>
                      ) : (
                        <img
                          src={image.url}
                          alt={image.prompt}
                          loading="lazy"
                          className="h-full w-full object-cover"
                          onError={(e) => {
                            const target = e.target as HTMLImageElement;
                            target.src = '/placeholder.png';
                          }}
                        />
                      )}
                      <div className="absolute inset-0 opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100">
                        <div className="absolute inset-x-0 bottom-0 border-t border-border bg-background/90 p-3">
                          <p className="line-clamp-2 text-xs text-foreground">{image.prompt}</p>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            {getModelDisplayName(image.model)}
                          </p>
                        </div>
                        <div className="absolute right-2 top-2 flex gap-1.5">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                size="icon"
                                variant="glass"
                                className="h-8 w-8"
                                aria-label="Download"
                                title="Download"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Download className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent>
                              {isSvgImage(image) ? (
                                <>
                                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDownload(image, 'svg'); }}>
                                    SVG
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDownload(image, 'png'); }}>
                                    PNG
                                  </DropdownMenuItem>
                                </>
                              ) : (
                                <>
                                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDownload(image, 'png'); }}>
                                    PNG
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDownload(image, 'jpg'); }}>
                                    JPEG
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDownload(image, 'webp'); }}>
                                    WebP
                                  </DropdownMenuItem>
                                </>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                          <Button
                            size="icon"
                            variant="glass"
                            className="h-8 w-8 hover:text-destructive"
                            aria-label="Delete image"
                            title="Delete"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteConfirm(image.id);
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Infinite scroll sentinel */}
                <div ref={sentinelRef} className="h-1" />

                {/* Loading more: a row of tiles in the grid's shape */}
                {isLoadingMore && (
                  <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4" aria-busy="true" aria-label="Loading more images">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="shimmer aspect-square rounded-xl bg-muted" />
                    ))}
                  </div>
                )}

                {/* End of gallery message */}
                {!hasMore && images.length > 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    That is everything.
                  </div>
                )}
              </>
            ) : (
              !error && (
                <div className="py-16 text-center">
                  <ImageIcon className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
                  <p className="font-semibold tracking-tight">No images yet</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Everything you generate is saved here.
                  </p>
                  <Button className="mt-5" asChild>
                    <Link to="/generate">Generate an image</Link>
                  </Button>
                </div>
              )
            )}
          </TabsContent>

          {/* Videos Tab Content */}
          <TabsContent value="videos">
            <VideoGalleryTab />
          </TabsContent>
        </Tabs>
      </StaggerItem>

      {/* Image Detail Modal */}
      <Dialog open={!!selectedImage} onOpenChange={() => selectImage(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Image details</span>
              <div className="mr-6 flex gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm">
                      <Download className="mr-1 h-4 w-4" />
                      Download
                      <ChevronDown className="ml-1 h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {selectedImage && isSvgImage(selectedImage) ? (
                      <>
                        <DropdownMenuItem onClick={() => handleDownload(selectedImage, 'svg')}>
                          SVG (vector)
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDownload(selectedImage, 'png')}>
                          PNG ({PNG_EXPORT_SIZE} px)
                        </DropdownMenuItem>
                      </>
                    ) : (
                      <>
                        <DropdownMenuItem onClick={() => selectedImage && handleDownload(selectedImage, 'png')}>
                          PNG (lossless)
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => selectedImage && handleDownload(selectedImage, 'jpg')}>
                          JPEG (smaller)
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => selectedImage && handleDownload(selectedImage, 'webp')}>
                          WebP (smallest)
                        </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
                {selectedImage && !isSvgImage(selectedImage) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setTextImage(selectedImage);
                      selectImage(null);
                    }}
                  >
                    Add text
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  className="hover:border-destructive/50 hover:text-destructive"
                  onClick={() => selectedImage && setDeleteConfirm(selectedImage.id)}
                >
                  <Trash2 className="mr-1 h-4 w-4" />
                  Delete
                </Button>
              </div>
            </DialogTitle>
            <DialogDescription className="sr-only">View and manage your generated image</DialogDescription>
          </DialogHeader>
          {selectedImage && (
            <div className="space-y-4">
              {/* Fixed height, so stepping between images does not move the controls */}
              <div className="relative flex h-[50vh] items-center justify-center rounded-xl bg-secondary/30">
                {isSvgImage(selectedImage) ? (
                  <LogoSurface surface="paper" className="flex h-full w-full items-center justify-center rounded-xl p-8">
                    <img
                      src={selectedImage.url}
                      alt={selectedImage.prompt}
                      className="max-h-[50vh] max-w-full object-contain"
                    />
                  </LogoSurface>
                ) : (
                  <img
                    src={selectedImage.url}
                    alt={selectedImage.prompt}
                    className="max-h-full max-w-full rounded-xl object-contain"
                  />
                )}
                <Button
                  variant="glass"
                  size="icon"
                  className="absolute left-2 top-1/2 -translate-y-1/2"
                  aria-label="Previous image"
                  title="Previous (left arrow)"
                  onClick={handlePrevImage}
                  disabled={images.findIndex((img) => img.id === selectedImage.id) === 0}
                >
                  <ChevronLeft className="h-6 w-6" />
                </Button>
                <Button
                  variant="glass"
                  size="icon"
                  className="absolute right-2 top-1/2 -translate-y-1/2"
                  aria-label="Next image"
                  title="Next (right arrow)"
                  onClick={handleNextImage}
                  disabled={
                    images.findIndex((img) => img.id === selectedImage.id) === images.length - 1
                  }
                >
                  <ChevronRight className="h-6 w-6" />
                </Button>
              </div>

              {/* Prompt Section */}
              <div className="space-y-2">
                <h4 className="text-xs font-medium text-muted-foreground">Prompt</h4>
                <p className="whitespace-pre-wrap rounded-lg border border-border bg-secondary/40 p-3 text-sm">
                  {selectedImage.prompt}
                </p>
                {selectedImage.magicPrompt && (
                  <div className="rounded-lg border border-border bg-secondary/20 p-3">
                    <h5 className="mb-1 text-xs font-medium text-muted-foreground">
                      Magic Prompt version
                    </h5>
                    <p className="whitespace-pre-wrap text-xs text-muted-foreground">{selectedImage.magicPrompt}</p>
                  </div>
                )}
              </div>

              {/* Compact Metadata Grid */}
              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground md:grid-cols-4">
                <div>
                  <span>Model</span>{' '}
                  <span className="text-foreground">{getModelDisplayName(selectedImage.model)}</span>
                </div>
                <div>
                  <span>Size</span>{' '}
                  <span className="font-mono tabular text-foreground">
                    {selectedImage.width && selectedImage.height
                      ? `${selectedImage.width}x${selectedImage.height}`
                      : 'N/A'}
                  </span>
                </div>
                <div>
                  <span>Ratio</span>{' '}
                  <span className="font-mono tabular text-foreground">{selectedImage.aspectRatio || 'N/A'}</span>
                </div>
                <div>
                  <span>Seed</span>{' '}
                  <span className="font-mono tabular text-foreground">{selectedImage.seed ?? 'N/A'}</span>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <AddTextDialog
        image={textImage}
        open={!!textImage}
        onOpenChange={(open) => !open && setTextImage(null)}
        onCreated={() => fetchGallery()}
      />

      {/* Delete Confirmation Modal */}
      <ConfirmDialog
        open={!!deleteConfirm}
        onOpenChange={(open) => !open && setDeleteConfirm(null)}
        title="Delete this image?"
        description={(() => {
          const prompt = images.find((img) => img.id === deleteConfirm)?.prompt?.trim();
          const name = prompt ? `"${prompt.length > 80 ? `${prompt.slice(0, 80)}...` : prompt}"` : 'This image';
          return `${name} will be removed from your gallery and its storage freed. This cannot be undone.`;
        })()}
        confirmText="Delete image"
        variant="destructive"
        onConfirm={() => (deleteConfirm ? handleDelete(deleteConfirm) : undefined)}
      />
    </Stagger>
  );
}
