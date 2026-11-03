import { create } from 'zustand';
import { AxiosError } from 'axios';
import { subtitleApi, type SubtitleVideo, type SubtitleUploadResponse } from '../api/subtitle';
import { getErrorMessage } from '@/utils/errors';

// Helper to extract error message from API errors

// Job tracking state
interface SubtitleGenerationJob {
  jobId: string;
  status: 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
}

interface SubtitleState {
  // Upload state
  uploadedVideo: SubtitleUploadResponse | null;
  uploadedFile: File | null;
  uploadPreview: string | null;
  isUploading: boolean;
  uploadProgress: number;

  // Generation settings - matching FAL API field names
  fontColor: string;
  strokeColor: string;
  highlightColor: string | null;
  backgroundColor: string | null;
  position: string;
  fontSize: number;
  fontName: string;
  fontWeight: string;
  strokeWidth: number;
  yOffset: number;
  wordsPerSubtitle: number;
  enableAnimation: boolean;
  language: string;

  // Generation state
  isGenerating: boolean;
  generatedVideo: SubtitleVideo | null;
  transcript: string | null;
  error: string | null;

  // Async job tracking
  currentJob: SubtitleGenerationJob | null;
  generationProgress: number;
  generationStatus: string;

  // Gallery state
  videos: SubtitleVideo[];
  galleryPage: number;
  galleryTotalPages: number;
  galleryTotal: number;
  isLoadingGallery: boolean;

  // Actions
  uploadVideo: (file: File) => Promise<void>;
  setFontColor: (color: string) => void;
  setStrokeColor: (color: string) => void;
  setHighlightColor: (color: string | null) => void;
  setBackgroundColor: (color: string | null) => void;
  setPosition: (position: string) => void;
  setFontSize: (size: number) => void;
  setFontName: (name: string) => void;
  setFontWeight: (weight: string) => void;
  setStrokeWidth: (width: number) => void;
  setYOffset: (offset: number) => void;
  setWordsPerSubtitle: (words: number) => void;
  setEnableAnimation: (enable: boolean) => void;
  setLanguage: (lang: string) => void;
  generateSubtitles: () => Promise<void>;
  clearUpload: () => void;
  clearError: () => void;
  clearGeneratedVideo: () => void;
  cancelGeneration: () => void;
  reset: () => void;

  // Gallery actions
  loadGallery: (page?: number, pageSize?: number) => Promise<void>;
  deleteVideo: (videoId: number) => Promise<void>;
}

export const useSubtitleStore = create<SubtitleState>((set, get) => ({
  // Initial state
  uploadedVideo: null,
  uploadedFile: null,
  uploadPreview: null,
  isUploading: false,
  uploadProgress: 0,
  fontColor: 'white',
  strokeColor: 'black',
  highlightColor: null,
  backgroundColor: null,
  position: 'bottom',
  fontSize: 100,
  fontName: 'Montserrat',
  fontWeight: 'bold',
  strokeWidth: 3,
  yOffset: 75,
  wordsPerSubtitle: 3,
  enableAnimation: true,
  language: 'en',
  isGenerating: false,
  generatedVideo: null,
  transcript: null,
  error: null,
  currentJob: null,
  generationProgress: 0,
  generationStatus: '',
  videos: [],
  galleryPage: 1,
  galleryTotalPages: 0,
  galleryTotal: 0,
  isLoadingGallery: false,

  // Actions
  uploadVideo: async (file) => {
    set({
      isUploading: true,
      uploadProgress: 0,
      error: null,
      uploadedFile: file,
      uploadPreview: URL.createObjectURL(file),
    });

    try {
      const result = await subtitleApi.uploadVideo(file);
      set({
        uploadedVideo: result,
        isUploading: false,
        uploadProgress: 100,
      });
    } catch (error) {
      const message = getErrorMessage(error);
      set({
        error: message,
        isUploading: false,
        uploadProgress: 0,
        uploadedFile: null,
        uploadPreview: null,
      });
      throw error;
    }
  },

  setFontColor: (color) => set({ fontColor: color }),
  setStrokeColor: (color) => set({ strokeColor: color }),
  setHighlightColor: (color) => set({ highlightColor: color }),
  setBackgroundColor: (color) => set({ backgroundColor: color }),
  setPosition: (position) => set({ position }),
  setFontSize: (size) => set({ fontSize: size }),
  setFontName: (name) => set({ fontName: name }),
  setFontWeight: (weight) => set({ fontWeight: weight }),
  setStrokeWidth: (width) => set({ strokeWidth: width }),
  setYOffset: (offset) => set({ yOffset: offset }),
  setWordsPerSubtitle: (words) => set({ wordsPerSubtitle: words }),
  setEnableAnimation: (enable) => set({ enableAnimation: enable }),
  setLanguage: (lang) => set({ language: lang }),

  generateSubtitles: async () => {
    const {
      uploadedVideo,
      fontColor,
      strokeColor,
      highlightColor,
      backgroundColor,
      position,
      fontSize,
      fontName,
      fontWeight,
      strokeWidth,
      yOffset,
      wordsPerSubtitle,
      enableAnimation,
      language,
    } = get();

    if (!uploadedVideo?.url) {
      set({ error: 'Please upload a video first' });
      return;
    }

    set({
      isGenerating: true,
      error: null,
      generationProgress: 0,
      generationStatus: 'Submitting job...',
      currentJob: null,
      generatedVideo: null,
      transcript: null,
    });

    try {
      // Submit the job
      const job = await subtitleApi.submitGenerateJob({
        videoUrl: uploadedVideo.url,
        fontColor,
        strokeColor,
        highlightColor: highlightColor || undefined,
        backgroundColor: backgroundColor || undefined,
        position,
        fontSize,
        fontName,
        fontWeight,
        strokeWidth,
        yOffset,
        wordsPerSubtitle,
        enableAnimation,
        language,
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
      const maxAttempts = 120; // 30 minutes with 15s intervals
      let attempts = 0;

      const pollStatus = async (): Promise<void> => {
        const currentState = get();
        if (!currentState.isGenerating || !currentState.currentJob) {
          return; // Cancelled
        }

        try {
          const status = await subtitleApi.getJobStatus(job.jobId);

          // Update progress based on status
          let progress = 10;
          let statusText = 'Queued...';

          if (status.status === 'in_progress') {
            progress = 50;
            statusText = 'Processing video...';
          } else if (status.status === 'processing') {
            progress = 85;
            statusText = 'Adding subtitles...';
          } else if (status.status === 'ready' || status.status === 'completed') {
            progress = 90;
            statusText = 'Downloading result...';
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
              const result = await subtitleApi.getJobResult(job.jobId);

              set({
                generatedVideo: result.video,
                transcript: result.transcript,
                isGenerating: false,
                currentJob: null,
                generationProgress: 100,
                generationStatus: 'Complete!',
              });
              return;
            } catch (resultError) {
              // Handle 409 Conflict - another process is handling this job
              if (resultError instanceof AxiosError && resultError.response?.status === 409) {
                attempts++;
                if (attempts < maxAttempts) {
                  setTimeout(pollStatus, 15000);
                  return;
                }
              }
              throw resultError;
            }
          }

          if (status.status === 'failed') {
            throw new Error(status.error || 'Subtitle generation failed');
          }

          // Continue polling
          attempts++;
          if (attempts < maxAttempts) {
            setTimeout(pollStatus, 15000);
          } else {
            throw new Error('Subtitle generation timed out');
          }
        } catch (error) {
          const message = getErrorMessage(error);
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

  clearUpload: () => set({
    uploadedVideo: null,
    uploadedFile: null,
    uploadPreview: null,
    uploadProgress: 0,
  }),

  clearError: () => set({ error: null }),

  clearGeneratedVideo: () => set({ generatedVideo: null, transcript: null }),

  cancelGeneration: () => set({
    isGenerating: false,
    currentJob: null,
    generationProgress: 0,
    generationStatus: '',
  }),

  reset: () => set({
    uploadedVideo: null,
    uploadedFile: null,
    uploadPreview: null,
    isUploading: false,
    uploadProgress: 0,
    fontColor: 'white',
    strokeColor: 'black',
    highlightColor: null,
    backgroundColor: null,
    position: 'bottom',
    fontSize: 100,
    fontName: 'Montserrat',
    fontWeight: 'bold',
    strokeWidth: 3,
    yOffset: 75,
    wordsPerSubtitle: 3,
    enableAnimation: true,
    language: 'en',
    isGenerating: false,
    generatedVideo: null,
    transcript: null,
    error: null,
    currentJob: null,
    generationProgress: 0,
    generationStatus: '',
  }),

  // Gallery actions
  loadGallery: async (page = 1, pageSize = 20) => {
    set({ isLoadingGallery: true, error: null });

    try {
      const result = await subtitleApi.getGallery(page, pageSize);
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
      await subtitleApi.deleteVideo(videoId);
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
