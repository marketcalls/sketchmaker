import { create } from 'zustand';
import { AxiosError } from 'axios';
import { videoApi } from '../api/video';
import type { MotionModelTier } from '../api/video';
import type { GeneratedVideo } from '../types';
import type { Asset } from '../api/assets';
import { getErrorMessage, withContentFilterAdvice } from '@/utils/errors';

// Helper to extract error message from API errors

// Job tracking state
interface VideoGenerationJob {
  jobId: string;
  status: 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
}

interface VideoState {
  // Generation state
  isGenerating: boolean;
  sourceImage: string | null;  // Hosted URL after upload
  sourceImagePreview: string | null;  // Local preview (data URL or blob URL)
  sourceImageFile: File | null;  // Original file for upload
  motionReferenceUrl: string | null;
  motionReferenceFile: File | null;
  motionReferencePreview: string | null;
  // Set when the reference video comes from My Assets.
  motionReferenceAssetId: number | null;
  characterOrientation: 'video' | 'image';
  // Kling tier, scene prompt, reference audio and V3 face lock
  modelTier: MotionModelTier;
  prompt: string;
  keepOriginalSound: boolean;
  faceImage: { url: string; preview: string; width: number; height: number; assetId?: number } | null;
  isUploadingFace: boolean;
  faceError: string | null;
  generatedVideo: GeneratedVideo | null;
  error: string | null;

  // Async job tracking
  currentJob: VideoGenerationJob | null;
  generationProgress: number;
  generationStatus: string;

  // Upload state
  isUploading: boolean;
  uploadProgress: number;

  // Gallery state
  videos: GeneratedVideo[];
  galleryPage: number;
  galleryTotalPages: number;
  galleryTotal: number;
  isLoadingGallery: boolean;

  // Actions
  setSourceImage: (image: string | null, preview?: string | null, file?: File | null) => void;
  uploadSourceImage: (file: File) => Promise<string>;
  pickSourceImageAsset: (asset: Asset) => Promise<void>;
  selectMotionReferenceAsset: (asset: Asset) => void;
  selectFaceAsset: (asset: Asset) => void;
  setMotionReferenceUrl: (url: string | null) => void;
  setMotionReferenceFile: (file: File | null) => void;
  setCharacterOrientation: (orientation: 'video' | 'image') => void;
  setModelTier: (tier: MotionModelTier) => void;
  setPrompt: (prompt: string) => void;
  setKeepOriginalSound: (keep: boolean) => void;
  uploadFaceImage: (file: File) => Promise<void>;
  clearFaceImage: () => void;
  uploadMotionVideo: (file: File) => Promise<string>;
  generateVideo: () => Promise<void>;
  clearError: () => void;
  clearGeneratedVideo: () => void;
  cancelGeneration: () => void;
  reset: () => void;

  // Gallery actions
  loadGallery: (page?: number, pageSize?: number) => Promise<void>;
  deleteVideo: (videoId: number) => Promise<void>;
}

export const useVideoStore = create<VideoState>((set, get) => ({
  // Initial state
  isGenerating: false,
  sourceImage: null,
  sourceImagePreview: null,
  sourceImageFile: null,
  motionReferenceUrl: null,
  motionReferenceFile: null,
  motionReferencePreview: null,
  motionReferenceAssetId: null,
  characterOrientation: 'video',
  modelTier: 'v3-standard',
  prompt: '',
  keepOriginalSound: true,
  faceImage: null,
  isUploadingFace: false,
  faceError: null,
  generatedVideo: null,
  error: null,
  currentJob: null,
  generationProgress: 0,
  generationStatus: '',
  isUploading: false,
  uploadProgress: 0,
  videos: [],
  galleryPage: 1,
  galleryTotalPages: 0,
  galleryTotal: 0,
  isLoadingGallery: false,

  // Actions
  setSourceImage: (image, preview = null, file = null) => set({
    sourceImage: image,
    sourceImagePreview: preview || image,
    sourceImageFile: file,
  }),

  uploadSourceImage: async (file) => {
    set({ isUploading: true, uploadProgress: 0, error: null });

    try {
      const result = await videoApi.uploadSourceImage(file);
      set({
        isUploading: false,
        uploadProgress: 100,
        sourceImage: result.url,
        sourceImageFile: file,
        sourceImagePreview: URL.createObjectURL(file),
      });
      return result.url;
    } catch (error) {
      const message = getErrorMessage(error);
      set({
        isUploading: false,
        uploadProgress: 0,
        error: message,
      });
      throw error;
    }
  },

  pickSourceImageAsset: async (asset) => {
    set({ isUploading: true, uploadProgress: 0, error: null });
    try {
      const result = await videoApi.characterFromAsset(asset.id);
      set({
        isUploading: false,
        uploadProgress: 100,
        sourceImage: result.url,
        sourceImageFile: null,
        sourceImagePreview: asset.url,
      });
    } catch (error) {
      set({ isUploading: false, uploadProgress: 0, error: getErrorMessage(error) });
    }
  },

  selectMotionReferenceAsset: (asset) => {
    set({
      motionReferenceUrl: asset.url,
      motionReferenceFile: null,
      motionReferencePreview: null,
      motionReferenceAssetId: asset.id,
    });
  },

  selectFaceAsset: (asset) => {
    const previous = get().faceImage;
    if (previous && previous.preview.startsWith('blob:')) URL.revokeObjectURL(previous.preview);
    set({
      faceError: null,
      faceImage: {
        url: asset.url,
        preview: asset.url,
        width: asset.width ?? 0,
        height: asset.height ?? 0,
        assetId: asset.id,
      },
    });
  },

  setMotionReferenceUrl: (url) => {
    // Only clear file/preview when setting a non-null URL
    // Setting null just means "no URL selected" and shouldn't affect file state
    if (url) {
      set({
        motionReferenceUrl: url,
        motionReferenceFile: null,
        motionReferencePreview: null,
        motionReferenceAssetId: null,
      });
    } else {
      set({ motionReferenceUrl: null, motionReferenceAssetId: null });
    }
  },

  setMotionReferenceFile: (file) => {
    if (file) {
      const preview = URL.createObjectURL(file);
      set({
        motionReferenceFile: file,
        motionReferencePreview: preview,
        motionReferenceUrl: null,
        motionReferenceAssetId: null,
      });
    } else {
      set({
        motionReferenceFile: null,
        motionReferencePreview: null,
      });
    }
  },

  setCharacterOrientation: (orientation) => set({ characterOrientation: orientation }),

  setModelTier: (tier) => set({ modelTier: tier }),

  setPrompt: (prompt) => set({ prompt }),

  setKeepOriginalSound: (keep) => set({ keepOriginalSound: keep }),

  // Uploaded as soon as it is picked, so the server's size and aspect checks
  // show next to the picker rather than at generate time.
  uploadFaceImage: async (file) => {
    set({ isUploadingFace: true, faceError: null });
    try {
      const result = await videoApi.uploadFaceImage(file);
      const previous = get().faceImage;
      if (previous && previous.preview.startsWith('blob:')) URL.revokeObjectURL(previous.preview);
      set({
        isUploadingFace: false,
        faceImage: {
          url: result.url,
          preview: URL.createObjectURL(file),
          width: result.width,
          height: result.height,
        },
      });
    } catch (error) {
      set({ isUploadingFace: false, faceError: getErrorMessage(error) });
    }
  },

  clearFaceImage: () => {
    const previous = get().faceImage;
    if (previous && previous.preview.startsWith('blob:')) URL.revokeObjectURL(previous.preview);
    set({ faceImage: null, faceError: null });
  },

  uploadMotionVideo: async (file) => {
    set({ isUploading: true, uploadProgress: 0, error: null });

    try {
      const result = await videoApi.uploadVideo(file);
      set({
        isUploading: false,
        uploadProgress: 100,
        motionReferenceUrl: result.url,
        motionReferenceFile: file,
        motionReferencePreview: URL.createObjectURL(file),
      });
      return result.url;
    } catch (error) {
      const message = getErrorMessage(error);
      set({
        isUploading: false,
        uploadProgress: 0,
        error: message,
      });
      throw error;
    }
  },

  generateVideo: async () => {
    const {
      sourceImage,
      sourceImageFile,
      motionReferenceUrl,
      motionReferenceFile,
      motionReferenceAssetId,
      characterOrientation,
      modelTier,
      prompt,
      keepOriginalSound,
      faceImage,
    } = get();

    if (!sourceImage && !sourceImageFile) {
      set({ error: 'Please upload a source image' });
      return;
    }

    // Upload source image file if not already uploaded to get a hosted URL
    // FAL's Kling Video API requires hosted URLs, not base64 data URLs
    let sourceImageUrl = sourceImage;
    if (sourceImageFile && (!sourceImage || sourceImage.startsWith('data:'))) {
      try {
        set({ generationStatus: 'Uploading source image...' });
        sourceImageUrl = await get().uploadSourceImage(sourceImageFile);
      } catch {
        return; // Error already set in uploadSourceImage
      }
    }

    if (!sourceImageUrl) {
      set({ error: 'Please upload a source image' });
      return;
    }

    // Upload motion reference file if not already uploaded
    let motionUrl = motionReferenceUrl;
    if (!motionUrl && motionReferenceFile) {
      try {
        set({ generationStatus: 'Uploading motion video...' });
        motionUrl = await get().uploadMotionVideo(motionReferenceFile);
      } catch {
        return; // Error already set in uploadMotionVideo
      }
    }

    if (!motionUrl) {
      set({ error: 'Please provide a motion reference video' });
      return;
    }

    set({
      isGenerating: true,
      error: null,
      generationProgress: 0,
      generationStatus: 'Submitting job...',
      currentJob: null,
      generatedVideo: null,
    });

    try {
      // Submit the job with hosted URLs (not base64 data URLs)
      // Face lock applies to the V3 tiers with the video orientation only; a
      // face picked earlier stays in the store but is not sent otherwise.
      const sendFace = faceImage !== null && modelTier !== 'v2.6' && characterOrientation === 'video';
      const job = await videoApi.submitGenerateJob({
        sourceImage: sourceImageUrl,
        motionReference: motionUrl,
        characterOrientation,
        modelTier,
        prompt,
        keepOriginalSound,
        faceImageUrl: sendFace ? faceImage.url : null,
        faceAssetId: sendFace ? faceImage.assetId ?? null : null,
        motionReferenceAssetId,
      });

      set({
        currentJob: {
          jobId: job.jobId,
          status: 'pending',
          progress: 0,
        },
        generationStatus: 'Queued...',
        generationProgress: 10,
      });

      // Poll for status
      const maxAttempts = 120; // 30 minutes with 15s intervals (video generation can take a while)
      let attempts = 0;

      const pollStatus = async (): Promise<void> => {
        const currentState = get();
        if (!currentState.isGenerating || !currentState.currentJob) {
          return; // Cancelled
        }

        try {
          const status = await videoApi.getJobStatus(job.jobId);

          // Update progress based on status
          let progress = 10;
          let statusText = 'Queued...';

          if (status.status === 'in_progress') {
            progress = 50;
            statusText = 'Generating video...';
          } else if (status.status === 'processing') {
            progress = 85;
            statusText = 'Processing video...';
          } else if (status.status === 'ready' || status.status === 'completed') {
            progress = 90;
            statusText = 'Downloading video...';
          }

          set({
            currentJob: {
              jobId: job.jobId,
              status: status.status,
              progress: status.progress,
              logs: status.logs,
              error: status.error,
            },
            generationProgress: progress,
            generationStatus: statusText,
          });

          // 'ready' means FAL is done, fetch result; 'completed' means already processed
          if (status.status === 'ready' || status.status === 'completed') {
            try {
              // Fetch result - backend handles deduplication with locks
              const result = await videoApi.getJobResult(job.jobId);

              set({
                generatedVideo: result.video,
                isGenerating: false,
                currentJob: null,
                generationProgress: 100,
                generationStatus: 'Complete!',
              });
              return;
            } catch (resultError) {
              // Handle 409 Conflict - another process is handling this job
              // Continue polling until it's actually completed
              if (resultError instanceof AxiosError && resultError.response?.status === 409) {
                // Another process is handling it, continue polling
                attempts++;
                if (attempts < maxAttempts) {
                  setTimeout(pollStatus, 15000);
                  return;
                }
              }
              // Re-throw other errors
              throw resultError;
            }
          }

          if (status.status === 'failed') {
            throw new Error(status.error || 'Video generation failed');
          }

          // Continue polling
          attempts++;
          if (attempts < maxAttempts) {
            setTimeout(pollStatus, 15000);
          } else {
            throw new Error('Video generation timed out');
          }
        } catch (error) {
          // Several characters (MiniMax Recast) runs on a different provider than Kling.
          const message = withContentFilterAdvice(
            getErrorMessage(error),
            'Reword the prompt or use another character image, or switch to Several characters, which uses a different provider.',
          );
          set({
            error: message,
            isGenerating: false,
            currentJob: null,
            generationProgress: 0,
            generationStatus: '',
          });
        }
      };

      // Start polling
      pollStatus();
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      set({
        error: message,
        isGenerating: false,
        currentJob: null,
        generationProgress: 0,
        generationStatus: '',
      });
      throw error;
    }
  },

  clearError: () => set({ error: null }),

  clearGeneratedVideo: () => set({ generatedVideo: null }),

  cancelGeneration: () => set({
    isGenerating: false,
    currentJob: null,
    generationProgress: 0,
    generationStatus: '',
  }),

  reset: () => set({
    isGenerating: false,
    sourceImage: null,
    sourceImagePreview: null,
    sourceImageFile: null,
    motionReferenceUrl: null,
    motionReferenceFile: null,
    motionReferencePreview: null,
    motionReferenceAssetId: null,
    characterOrientation: 'video',
    // The chosen tier and audio setting carry over to the next video.
    prompt: '',
    faceImage: null,
    isUploadingFace: false,
    faceError: null,
    generatedVideo: null,
    error: null,
    currentJob: null,
    generationProgress: 0,
    generationStatus: '',
    isUploading: false,
    uploadProgress: 0,
  }),

  // Gallery actions
  loadGallery: async (page = 1, pageSize = 20) => {
    set({ isLoadingGallery: true, error: null });

    try {
      const result = await videoApi.getGallery(page, pageSize);
      set({
        videos: result.videos,
        galleryPage: result.page,
        galleryTotalPages: result.totalPages,
        galleryTotal: result.total,
        isLoadingGallery: false,
      });
    } catch (error) {
      const message = getErrorMessage(error);
      set({
        error: message,
        isLoadingGallery: false,
      });
    }
  },

  deleteVideo: async (videoId: number) => {
    try {
      await videoApi.deleteVideo(videoId);
      // Remove from local state
      set((state) => ({
        videos: state.videos.filter((v) => v.id !== videoId),
        galleryTotal: state.galleryTotal - 1,
      }));
    } catch (error) {
      const message = getErrorMessage(error);
      set({ error: message });
      throw error;
    }
  },
}));
