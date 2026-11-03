import { create } from 'zustand';
import { AxiosError } from 'axios';
import { lipsyncApi, type LipSyncAudioUpload, type LipSyncImageUpload, type LipSyncResolution } from '@/api/lipsync';
import { videoApi } from '@/api/video';
import type { Asset } from '@/api/assets';
import { getErrorMessage, withContentFilterAdvice } from '@/utils/errors';
import { LIPSYNC_MAX_SECONDS, LIPSYNC_MIN_SECONDS } from './pricingStore';
import type { GeneratedVideo } from '@/types';

// Client-side limits, checked again by the server (lipsync_service).
export const LIPSYNC_IMAGE_MAX_MB = 10;
export const LIPSYNC_AUDIO_MAX_MB = 25;
export const LIPSYNC_ASPECT_MIN = 0.4;
export const LIPSYNC_ASPECT_MAX = 2.5;

// 'ready' means fal finished and the result can be fetched.
type JobStatus = 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';

/** Why an asset cannot be the Lip Sync portrait, or null. */
export function lipsyncImageProblem(asset: Asset): string | null {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(asset.contentType ?? '')) {
    return 'Needs a PNG, JPEG or WebP image (SVG cannot be animated)';
  }
  if (asset.fileSizeBytes > LIPSYNC_IMAGE_MAX_MB * 1024 * 1024) return `Larger than ${LIPSYNC_IMAGE_MAX_MB} MB`;
  if (asset.width && asset.height) {
    const ratio = asset.width / asset.height;
    if (ratio < LIPSYNC_ASPECT_MIN || ratio > LIPSYNC_ASPECT_MAX) {
      return `Aspect ratio ${ratio.toFixed(2)}, needs ${LIPSYNC_ASPECT_MIN} to ${LIPSYNC_ASPECT_MAX}`;
    }
  }
  return null;
}

/** Why an asset cannot be the Lip Sync audio, or null. */
export function lipsyncAudioProblem(asset: Asset): string | null {
  if (asset.kind !== 'audio') return 'Not audio';
  const seconds = asset.durationSeconds ?? 0;
  if (seconds < LIPSYNC_MIN_SECONDS) return `${seconds.toFixed(1)}s, needs at least ${LIPSYNC_MIN_SECONDS}s`;
  if (seconds > LIPSYNC_MAX_SECONDS) return `${Math.round(seconds)}s, the limit is ${LIPSYNC_MAX_SECONDS}s`;
  if (asset.fileSizeBytes > LIPSYNC_AUDIO_MAX_MB * 1024 * 1024) return `Larger than ${LIPSYNC_AUDIO_MAX_MB} MB`;
  return null;
}

// Whole seconds the video is priced on (backend pricing.lipsync_seconds).
function billableSeconds(seconds: number): number {
  if (!seconds || seconds <= 0) return 0;
  return Math.max(1, Math.ceil(Math.round(seconds * 100) / 100));
}

function revoke(url: string | null) {
  if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
}

const POLL_MS = 10000;
const MAX_POLLS = 360; // one hour; a 2 minute 2K video can take a while

function readImageSize(file: File): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
      URL.revokeObjectURL(url);
    };
    img.onerror = () => {
      resolve(null);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  });
}

function readAudioSeconds(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = document.createElement('audio');
    audio.preload = 'metadata';
    const done = (value: number | null) => {
      audio.removeAttribute('src');
      URL.revokeObjectURL(url);
      resolve(value);
    };
    audio.onloadedmetadata = () => done(Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null);
    audio.onerror = () => done(null);
    audio.src = url;
  });
}

interface LipSyncState {
  imagePreview: string | null;
  image: LipSyncImageUpload | null;
  imageError: string | null;
  isUploadingImage: boolean;

  audioPreview: string | null;
  audioName: string | null;
  audio: LipSyncAudioUpload | null;
  audioError: string | null;
  isUploadingAudio: boolean;

  resolution: LipSyncResolution;
  enableTranscription: boolean;
  faceCheck: boolean;

  isGenerating: boolean;
  jobId: string | null;
  jobStatus: JobStatus | null;
  progress: number;
  statusText: string;
  estimatedUsd: number | null;
  generatedVideo: GeneratedVideo | null;
  error: string | null;

  videos: GeneratedVideo[];
  isLoadingGallery: boolean;

  selectImage: (file: File) => Promise<void>;
  selectImageAsset: (asset: Asset) => void;
  clearImage: () => void;
  selectAudio: (file: File) => Promise<void>;
  selectAudioAsset: (asset: Asset) => void;
  clearAudio: () => void;
  setResolution: (resolution: LipSyncResolution) => void;
  setEnableTranscription: (value: boolean) => void;
  setFaceCheck: (value: boolean) => void;
  generate: () => Promise<void>;
  clearError: () => void;
  startOver: () => void;
  loadGallery: () => Promise<void>;
  deleteVideo: (videoId: number) => Promise<void>;
}

export const useLipSyncStore = create<LipSyncState>((set, get) => ({
  imagePreview: null,
  image: null,
  imageError: null,
  isUploadingImage: false,

  audioPreview: null,
  audioName: null,
  audio: null,
  audioError: null,
  isUploadingAudio: false,

  resolution: '768p',
  enableTranscription: false,
  faceCheck: false,

  isGenerating: false,
  jobId: null,
  jobStatus: null,
  progress: 0,
  statusText: '',
  estimatedUsd: null,
  generatedVideo: null,
  error: null,

  videos: [],
  isLoadingGallery: false,

  selectImage: async (file) => {
    const previous = get().imagePreview;
    revoke(previous);
    set({ image: null, imagePreview: null, imageError: null });

    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      set({ imageError: 'Upload a PNG, JPEG or WebP image.' });
      return;
    }
    if (file.size > LIPSYNC_IMAGE_MAX_MB * 1024 * 1024) {
      set({ imageError: `The image is larger than ${LIPSYNC_IMAGE_MAX_MB} MB.` });
      return;
    }
    const size = await readImageSize(file);
    if (size && size.height > 0) {
      const ratio = size.width / size.height;
      if (ratio < LIPSYNC_ASPECT_MIN || ratio > LIPSYNC_ASPECT_MAX) {
        set({
          imageError: `This image is ${size.width}x${size.height} (aspect ratio ${ratio.toFixed(2)}). Lip Sync needs an aspect ratio between ${LIPSYNC_ASPECT_MIN} and ${LIPSYNC_ASPECT_MAX}. Crop it and try again.`,
        });
        return;
      }
    }

    const preview = URL.createObjectURL(file);
    set({ imagePreview: preview, isUploadingImage: true });
    try {
      const image = await lipsyncApi.uploadImage(file);
      if (get().imagePreview !== preview) return; // replaced while uploading
      set({ image, isUploadingImage: false });
    } catch (err) {
      if (get().imagePreview !== preview) return;
      set({ imageError: getErrorMessage(err, 'Image upload failed'), isUploadingImage: false });
    }
  },

  selectImageAsset: (asset) => {
    revoke(get().imagePreview);
    const problem = lipsyncImageProblem(asset);
    if (problem) {
      set({ image: null, imagePreview: null, isUploadingImage: false, imageError: `That image cannot be used: ${problem}.` });
      return;
    }
    set({
      imagePreview: asset.url,
      imageError: null,
      isUploadingImage: false,
      image: {
        url: asset.url,
        filename: asset.name,
        fileSizeBytes: asset.fileSizeBytes,
        width: asset.width ?? 0,
        height: asset.height ?? 0,
        aspectRatio: asset.width && asset.height ? asset.width / asset.height : 1,
        assetId: asset.id,
      },
    });
  },

  clearImage: () => {
    const previous = get().imagePreview;
    revoke(previous);
    set({ image: null, imagePreview: null, imageError: null, isUploadingImage: false });
  },

  selectAudio: async (file) => {
    const previous = get().audioPreview;
    revoke(previous);
    set({ audio: null, audioPreview: null, audioName: null, audioError: null });

    if (file.size > LIPSYNC_AUDIO_MAX_MB * 1024 * 1024) {
      set({ audioError: `The audio file is larger than ${LIPSYNC_AUDIO_MAX_MB} MB.` });
      return;
    }
    // A quick check in the browser; the server measures the file and decides.
    const seconds = await readAudioSeconds(file);
    if (seconds !== null && seconds < LIPSYNC_MIN_SECONDS - 0.05) {
      set({ audioError: `The audio is ${seconds.toFixed(1)} seconds long. Lip Sync needs at least ${LIPSYNC_MIN_SECONDS} seconds.` });
      return;
    }
    if (seconds !== null && seconds > LIPSYNC_MAX_SECONDS + 0.5) {
      set({
        audioError: `The audio is ${seconds.toFixed(1)} seconds long. Lip Sync accepts up to ${LIPSYNC_MAX_SECONDS} seconds (${LIPSYNC_MAX_SECONDS / 60} minutes) for now. Trim it and try again.`,
      });
      return;
    }

    const preview = URL.createObjectURL(file);
    set({ audioPreview: preview, audioName: file.name, isUploadingAudio: true });
    try {
      const audio = await lipsyncApi.uploadAudio(file);
      if (get().audioPreview !== preview) return; // replaced while uploading
      set({ audio, isUploadingAudio: false });
    } catch (err) {
      if (get().audioPreview !== preview) return;
      set({ audioError: getErrorMessage(err, 'Audio upload failed'), isUploadingAudio: false });
    }
  },

  selectAudioAsset: (asset) => {
    revoke(get().audioPreview);
    const problem = lipsyncAudioProblem(asset);
    if (problem) {
      set({ audio: null, audioPreview: null, audioName: null, isUploadingAudio: false, audioError: `That audio cannot be used: ${problem}.` });
      return;
    }
    const seconds = asset.durationSeconds ?? 0;
    set({
      audioPreview: asset.url,
      audioName: asset.name,
      audioError: null,
      isUploadingAudio: false,
      audio: {
        url: asset.url,
        filename: asset.name,
        fileSizeBytes: asset.fileSizeBytes,
        durationSeconds: seconds,
        billableSeconds: billableSeconds(seconds),
        assetId: asset.id,
      },
    });
  },

  clearAudio: () => {
    const previous = get().audioPreview;
    revoke(previous);
    set({ audio: null, audioPreview: null, audioName: null, audioError: null, isUploadingAudio: false });
  },

  setResolution: (resolution) => set({ resolution }),
  setEnableTranscription: (enableTranscription) => set({ enableTranscription }),
  setFaceCheck: (faceCheck) => set({ faceCheck }),

  generate: async () => {
    const { image, audio, resolution, enableTranscription, faceCheck, isGenerating } = get();
    if (isGenerating) return;
    if (!image || !audio) {
      set({ error: 'Add a portrait and audio first.' });
      return;
    }

    set({
      isGenerating: true,
      error: null,
      generatedVideo: null,
      jobId: null,
      jobStatus: 'pending',
      progress: 5,
      statusText: 'Submitting job...',
      estimatedUsd: null,
    });

    let jobId: string;
    try {
      const job = await lipsyncApi.submit({
        imageUrl: image.url,
        audioUrl: audio.url,
        imageAssetId: image.assetId,
        audioAssetId: audio.assetId,
        resolution,
        enableTranscription,
        faceCheck,
      });
      jobId = job.jobId;
      set({ jobId, estimatedUsd: job.estimatedUsd, progress: 10, statusText: 'Queued...' });
    } catch (err) {
      set({
        isGenerating: false,
        jobStatus: null,
        progress: 0,
        statusText: '',
        error: getErrorMessage(err, 'Could not start the lip sync job'),
      });
      return;
    }

    let polls = 0;
    const poll = async (): Promise<void> => {
      if (get().jobId !== jobId || !get().isGenerating) return; // started over

      try {
        const status = await lipsyncApi.getStatus(jobId);
        const labels: Record<string, [number, string]> = {
          pending: [10, 'Queued...'],
          in_progress: [50, 'Animating the portrait...'],
          processing: [85, 'Saving the video...'],
          ready: [90, 'Downloading the video...'],
          completed: [95, 'Finishing...'],
        };
        const [progress, statusText] = labels[status.status] ?? [get().progress, get().statusText];
        set({ jobStatus: status.status as JobStatus, progress, statusText });

        if (status.status === 'failed') {
          throw new Error(status.error || 'Lip sync failed');
        }

        if (status.status === 'ready' || status.status === 'completed') {
          try {
            const result = await lipsyncApi.getResult(jobId);
            if (get().jobId !== jobId) return;
            set({
              generatedVideo: result.video,
              isGenerating: false,
              jobStatus: 'completed',
              progress: 100,
              statusText: 'Complete',
            });
            get().loadGallery();
            return;
          } catch (resultError) {
            // 409: the scheduler is finishing it; keep polling.
            if (!(resultError instanceof AxiosError && resultError.response?.status === 409)) {
              throw resultError;
            }
          }
        }

        polls += 1;
        if (polls >= MAX_POLLS) throw new Error('Lip sync is taking too long. Check My Jobs later.');
        setTimeout(poll, POLL_MS);
      } catch (err) {
        if (get().jobId !== jobId) return;
        set({
          isGenerating: false,
          jobStatus: 'failed',
          progress: 0,
          statusText: '',
          // Lip Sync has one model, so the advice is to change the inputs.
          error: withContentFilterAdvice(
            getErrorMessage(err, 'Lip sync failed'),
            'Try a different portrait or audio track.',
          ),
        });
      }
    };

    setTimeout(poll, 3000);
  },

  clearError: () => set({ error: null }),

  startOver: () => {
    const { imagePreview, audioPreview } = get();
    revoke(imagePreview);
    revoke(audioPreview);
    set({
      imagePreview: null,
      image: null,
      imageError: null,
      isUploadingImage: false,
      audioPreview: null,
      audioName: null,
      audio: null,
      audioError: null,
      isUploadingAudio: false,
      isGenerating: false,
      jobId: null,
      jobStatus: null,
      progress: 0,
      statusText: '',
      estimatedUsd: null,
      generatedVideo: null,
      error: null,
    });
  },

  loadGallery: async () => {
    set({ isLoadingGallery: true });
    try {
      const result = await lipsyncApi.getGallery(1, 12);
      set({ videos: result.videos, isLoadingGallery: false });
    } catch {
      set({ isLoadingGallery: false });
    }
  },

  deleteVideo: async (videoId) => {
    try {
      await videoApi.deleteVideo(videoId);
      set((state) => ({
        videos: state.videos.filter((v) => v.id !== videoId),
        generatedVideo: state.generatedVideo?.id === videoId ? null : state.generatedVideo,
      }));
    } catch (err) {
      set({ error: getErrorMessage(err, 'Could not delete the video') });
    }
  },
}));
