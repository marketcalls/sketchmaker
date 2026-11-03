import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Trash2, Play, ChevronLeft, ChevronRight, Video } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useVideoStore } from '@/stores/videoStore';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { videoApi } from '@/api/video';
import type { GeneratedVideo } from '@/types';
import { formatLocalDate } from '@/lib/dateUtils';

// Which tool made a video (Video.video_type).
const VIDEO_TYPE_LABELS: Record<string, string> = {
  motion: 'Motion Control',
  story: 'Story',
  subtitle: 'Subtitles',
  lipsync: 'Lip Sync',
};

function videoTypeLabel(video: GeneratedVideo): string | null {
  return video.videoType ? VIDEO_TYPE_LABELS[video.videoType] ?? null : null;
}

export function VideoGalleryTab() {
  const {
    videos,
    galleryTotal: total,
    isLoadingGallery: isLoading,
    error,
    loadGallery,
    deleteVideo,
  } = useVideoStore();

  const [selectedVideo, setSelectedVideo] = useState<GeneratedVideo | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [page, setPage] = useState(1);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Fetch initial data on mount
  useEffect(() => {
    loadGallery(1, 20);
  }, [loadGallery]);

  // Update hasMore based on loaded videos
  useEffect(() => {
    setHasMore(videos.length < total);
  }, [videos.length, total]);

  // Load more handler
  const handleLoadMore = async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    const nextPage = page + 1;
    await loadGallery(nextPage, 20);
    setPage(nextPage);
    setIsLoadingMore(false);
  };

  // Infinite scroll observer
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore || isLoadingMore || isLoading) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore && !isLoading) {
          handleLoadMore();
        }
      },
      {
        root: null,
        rootMargin: '200px',
        threshold: 0,
      }
    );

    observer.observe(sentinel);

    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, isLoading]);

  const handleDownload = async (video: GeneratedVideo) => {
    try {
      await videoApi.downloadVideo(video.id, video.filename);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const handleDelete = async (videoId: number) => {
    try {
      await deleteVideo(videoId);
      setDeleteConfirm(null);
      if (selectedVideo?.id === videoId) {
        setSelectedVideo(null);
      }
    } catch {
      // Error handled by store
    }
  };

  const handlePrevVideo = () => {
    if (!selectedVideo) return;
    const currentIndex = videos.findIndex((v) => v.id === selectedVideo.id);
    if (currentIndex > 0) {
      setSelectedVideo(videos[currentIndex - 1]);
    }
  };

  const handleNextVideo = () => {
    if (!selectedVideo) return;
    const currentIndex = videos.findIndex((v) => v.id === selectedVideo.id);
    if (currentIndex < videos.length - 1) {
      setSelectedVideo(videos[currentIndex + 1]);
    }
  };

  return (
    <div className="space-y-6">
      {error && (
        <div role="alert" className="p-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg">
          {error}
        </div>
      )}

      {isLoading && videos.length === 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" aria-busy="true" aria-label="Loading videos">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="shimmer aspect-video rounded-xl bg-muted" />
          ))}
        </div>
      ) : videos.length > 0 ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {videos.map((video) => (
              <Card
                key={video.id}
                role="button"
                tabIndex={0}
                aria-label="Open video details"
                className="overflow-hidden cursor-pointer group transition-colors duration-150 hover:border-foreground/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => setSelectedVideo(video)}
                onKeyDown={(e) => {
                  if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    setSelectedVideo(video);
                  }
                }}
              >
                <CardContent className="p-0 relative aspect-video bg-muted">
                  {/* Thumbnail or video preview */}
                  {video.thumbnailUrl ? (
                    <img
                      src={video.thumbnailUrl}
                      alt="Video thumbnail"
                      loading="lazy"
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                      }}
                    />
                  ) : (
                    <video
                      src={video.url}
                      className="w-full h-full object-contain"
                      muted
                      preload="metadata"
                    />
                  )}

                  {/* Play icon overlay */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="glass flex h-10 w-10 items-center justify-center rounded-full">
                      <Play className="ml-0.5 h-4 w-4 fill-current text-foreground" />
                    </div>
                  </div>

                  {/* Tool badge */}
                  {videoTypeLabel(video) && (
                    <div className="glass absolute left-2 top-2 rounded-md px-1.5 py-0.5 text-[11px] font-medium text-foreground">
                      {videoTypeLabel(video)}
                    </div>
                  )}

                  {/* Duration badge */}
                  {video.durationSeconds && (
                    <div className="glass absolute bottom-2 right-2 rounded-md px-1.5 py-0.5 font-mono tabular text-[11px] text-foreground">
                      {Math.floor(video.durationSeconds / 60)}:
                      {Math.floor(video.durationSeconds % 60).toString().padStart(2, '0')}
                    </div>
                  )}

                  {/* Actions: on hover or keyboard focus */}
                  <div className="absolute right-2 top-2 flex gap-1.5 opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100">
                    <Button
                      size="icon"
                      variant="glass"
                      className="h-8 w-8"
                      aria-label="Download video"
                      title="Download"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownload(video);
                      }}
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                    <Button
                      size="icon"
                      variant="glass"
                      className="h-8 w-8 hover:text-destructive"
                      aria-label="Delete video"
                      title="Delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirm(video.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-1" />

          {/* Loading more: a row of tiles in the grid's shape */}
          {isLoadingMore && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" aria-busy="true" aria-label="Loading more videos">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="shimmer aspect-video rounded-xl bg-muted" />
              ))}
            </div>
          )}

          {/* End of gallery message */}
          {!hasMore && videos.length > 0 && (
            <div className="text-center py-8 text-xs text-muted-foreground">
              That is everything.
            </div>
          )}
        </>
      ) : (
        !error && (
          <div className="text-center py-16">
            <Video className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
            <p className="font-semibold tracking-tight">No videos yet</p>
            <p className="mt-1 text-sm text-muted-foreground">Videos from every video tool are saved here.</p>
            <Button className="mt-5" asChild>
              <Link to="/motion-control">Make a video</Link>
            </Button>
          </div>
        )
      )}

      {/* Video Detail Modal */}
      <Dialog open={!!selectedVideo} onOpenChange={() => setSelectedVideo(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Video details</span>
              <div className="flex gap-2 mr-6">
                <Button size="sm" onClick={() => selectedVideo && handleDownload(selectedVideo)}>
                  <Download className="h-4 w-4 mr-1" />
                  Download
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="hover:border-destructive/50 hover:text-destructive"
                  onClick={() => selectedVideo && setDeleteConfirm(selectedVideo.id)}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Delete
                </Button>
              </div>
            </DialogTitle>
            <DialogDescription className="sr-only">View and manage your generated video</DialogDescription>
          </DialogHeader>
          {selectedVideo && (
            <div className="space-y-4">
              <div className="relative flex items-center justify-center">
                <VideoPlayer
                  src={selectedVideo.url}
                  poster={selectedVideo.thumbnailUrl}
                  showDownload={false}
                  className="border border-border"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute left-2 top-1/2 -translate-y-1/2 bg-background/80 hover:bg-background"
                  aria-label="Previous video"
                  onClick={handlePrevVideo}
                  disabled={videos.findIndex((v) => v.id === selectedVideo.id) === 0}
                >
                  <ChevronLeft className="h-6 w-6" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-2 top-1/2 -translate-y-1/2 bg-background/80 hover:bg-background"
                  aria-label="Next video"
                  onClick={handleNextVideo}
                  disabled={videos.findIndex((v) => v.id === selectedVideo.id) === videos.length - 1}
                >
                  <ChevronRight className="h-6 w-6" />
                </Button>
              </div>

              {/* Video Metadata */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                {videoTypeLabel(selectedVideo) && (
                  <div>
                    <span className="text-muted-foreground">Tool:</span>{' '}
                    <span className="font-medium">{videoTypeLabel(selectedVideo)}</span>
                  </div>
                )}
                {selectedVideo.durationSeconds && (
                  <div>
                    <span className="text-muted-foreground">Duration:</span>{' '}
                    <span className="font-mono tabular font-medium">{selectedVideo.durationSeconds.toFixed(1)}s</span>
                  </div>
                )}
                {selectedVideo.width && selectedVideo.height && (
                  <div>
                    <span className="text-muted-foreground">Resolution:</span>{' '}
                    <span className="font-mono tabular font-medium">{selectedVideo.width}x{selectedVideo.height}</span>
                  </div>
                )}
                {selectedVideo.fps && (
                  <div>
                    <span className="text-muted-foreground">FPS:</span>{' '}
                    <span className="font-mono tabular font-medium">{selectedVideo.fps}</span>
                  </div>
                )}
                {selectedVideo.fileSizeBytes && (
                  <div>
                    <span className="text-muted-foreground">Size:</span>{' '}
                    <span className="font-mono tabular font-medium">
                      {(selectedVideo.fileSizeBytes / 1024 / 1024).toFixed(2)} MB
                    </span>
                  </div>
                )}
                {selectedVideo.characterOrientation && (
                  <div>
                    <span className="text-muted-foreground">Orientation:</span>{' '}
                    <span className="font-medium capitalize">{selectedVideo.characterOrientation}</span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">Created:</span>{' '}
                  <span className="font-medium">
                    {formatLocalDate(selectedVideo.createdAt)}
                  </span>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <ConfirmDialog
        open={!!deleteConfirm}
        onOpenChange={(open) => !open && setDeleteConfirm(null)}
        title="Delete this video?"
        description={(() => {
          const video = videos.find((v) => v.id === deleteConfirm);
          const label = video ? videoTypeLabel(video) : null;
          const name = video ? `The ${label ? `${label} ` : ''}video from ${formatLocalDate(video.createdAt)}` : 'This video';
          return `${name} will be removed from your gallery and its storage freed. This cannot be undone.`;
        })()}
        confirmText="Delete video"
        variant="destructive"
        onConfirm={() => (deleteConfirm ? handleDelete(deleteConfirm) : undefined)}
      />
    </div>
  );
}

export default VideoGalleryTab;
