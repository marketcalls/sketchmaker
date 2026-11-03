import { create } from 'zustand';
import { AxiosError } from 'axios';
import { videoApi, type RecastResolution } from '@/api/video';
import type { Asset } from '@/api/assets';
import { getErrorMessage, withContentFilterAdvice } from '@/utils/errors';
import { RECAST_MAX_PEOPLE, RECAST_MAX_SECONDS, RECAST_MIN_SECONDS } from './pricingStore';
import type { GeneratedVideo } from '@/types';

// Multi-character motion transfer (MiniMax H3 Max Recast, backend
// POST /video/recast). The job runs through the Motion Control pipeline, so
// it is polled on /video/status and fetched from /video/result.

export const RECAST_PHOTO_MAX_MB = 20;
const PHOTO_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const POLL_MS = 10000;
const MAX_POLLS = 240; // forty minutes

export interface RecastVideo {
  url: string;
  preview: string;
  name: string;
  seconds: number;
  assetId?: number;
}

export interface RecastPerson {
  key: string;
  url: string;
  preview: string;
  assetId?: number;
}

/** Why an image asset cannot be a recast photo, or null (backend _face_asset_url). */
export function recastPhotoProblem(asset: Asset): string | null {
  if (!PHOTO_TYPES.includes(asset.contentType ?? '')) return 'Needs a JPG, PNG or WebP photo';
  const w = asset.width ?? 0;
  const h = asset.height ?? 0;
  if (!w || !h) return 'Size unknown';
  if (Math.min(w, h) < 300) return `${w}x${h}, needs at least 300 px a side`;
  const ratio = w / h;
  if (ratio < 0.4 || ratio > 2.5) return `Aspect ratio ${ratio.toFixed(2)}, needs 0.4 to 2.5`;
  if (asset.fileSizeBytes > RECAST_PHOTO_MAX_MB * 1024 * 1024) return `Larger than ${RECAST_PHOTO_MAX_MB} MB`;
  return null;
}

/** Why a video asset cannot be the recast source, or null. */
// Lengths must sit inside the range by this margin, never on its edge (the
// server applies the same, app/routers/video.py DURATION_SLACK_SECONDS).
const DURATION_SLACK_SECONDS = 0.05;
const secondsText = (s: number) => s.toFixed(2).replace(/\.?0+$/, '');

export function recastVideoProblem(asset: Asset): string | null {
  const seconds = asset.durationSeconds ?? 0;
  if (seconds < RECAST_MIN_SECONDS + DURATION_SLACK_SECONDS) return `${secondsText(seconds)}s, needs more than ${RECAST_MIN_SECONDS}s`;
  if (seconds > RECAST_MAX_SECONDS - DURATION_SLACK_SECONDS) return `${secondsText(seconds)}s, needs under ${RECAST_MAX_SECONDS}s`;
  return null;
}

function lengthProblem(seconds: number | null | undefined): string | null {
  if (!seconds) return 'The video length could not be read. Upload an MP4, MOV or WebM file.';
  if (seconds < RECAST_MIN_SECONDS + DURATION_SLACK_SECONDS) {
    return `The video is ${secondsText(seconds)} seconds long. Multi-character recast needs a clip longer than ${RECAST_MIN_SECONDS} seconds.`;
  }
  if (seconds > RECAST_MAX_SECONDS - DURATION_SLACK_SECONDS) {
    return `The video is ${secondsText(seconds)} seconds long. Multi-character recast accepts clips shorter than ${RECAST_MAX_SECONDS} seconds. Trim it and try again.`;
  }
  return null;
}

function revoke(url: string | null | undefined) {
  if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
}

interface RecastState {
  video: RecastVideo | null;
  videoError: string | null;
  isUploadingVideo: boolean;
  people: RecastPerson[];
  peopleError: string | null;
  isUploadingPhoto: boolean;
  resolution: RecastResolution;
  enhanceRealism: boolean;
  prompt: string;

  isGenerating: boolean;
  jobId: string | null;
  progress: number;
  statusText: string;
  generatedVideo: GeneratedVideo | null;
  error: string | null;

  selectVideo: (file: File) => Promise<void>;
  selectVideoAsset: (asset: Asset) => void;
  clearVideo: () => void;
  addPhoto: (file: File) => Promise<void>;
  addPhotoAsset: (asset: Asset) => void;
  removePerson: (key: string) => void;
  movePerson: (key: string, direction: -1 | 1) => void;
  setResolution: (resolution: RecastResolution) => void;
  setEnhanceRealism: (value: boolean) => void;
  setPrompt: (prompt: string) => void;
  generate: () => Promise<void>;
  clearError: () => void;
  startOver: () => void;
}

let personSeq = 0;

export const useRecastStore = create<RecastState>((set, get) => ({
  video: null,
  videoError: null,
  isUploadingVideo: false,
  people: [],
  peopleError: null,
  isUploadingPhoto: false,
  resolution: '1080p',
  enhanceRealism: true,
  prompt: '',

  isGenerating: false,
  jobId: null,
  progress: 0,
  statusText: '',
  generatedVideo: null,
  error: null,

  selectVideo: async (file) => {
    revoke(get().video?.preview);
    set({ video: null, videoError: null, isUploadingVideo: true });
    const preview = URL.createObjectURL(file);
    try {
      const result = await videoApi.uploadVideo(file);
      const problem = lengthProblem(result.durationSeconds);
      if (problem) {
        revoke(preview);
        set({ isUploadingVideo: false, videoError: problem });
        return;
      }
      set({
        isUploadingVideo: false,
        video: { url: result.url, preview, name: file.name, seconds: result.durationSeconds as number },
      });
    } catch (err) {
      revoke(preview);
      set({ isUploadingVideo: false, videoError: getErrorMessage(err, 'Video upload failed') });
    }
  },

  selectVideoAsset: (asset) => {
    revoke(get().video?.preview);
    const problem = recastVideoProblem(asset);
    if (problem) {
      set({ video: null, videoError: `That video cannot be used: ${problem}.` });
      return;
    }
    set({
      videoError: null,
      video: { url: asset.url, preview: asset.url, name: asset.name, seconds: asset.durationSeconds ?? 0, assetId: asset.id },
    });
  },

  clearVideo: () => {
    revoke(get().video?.preview);
    set({ video: null, videoError: null });
  },

  addPhoto: async (file) => {
    if (get().people.length >= RECAST_MAX_PEOPLE) return;
    if (!PHOTO_TYPES.includes(file.type)) {
      set({ peopleError: 'Upload a JPG, PNG or WebP photo.' });
      return;
    }
    if (file.size > RECAST_PHOTO_MAX_MB * 1024 * 1024) {
      set({ peopleError: `The photo is larger than ${RECAST_PHOTO_MAX_MB} MB.` });
      return;
    }
    set({ isUploadingPhoto: true, peopleError: null });
    try {
      const result = await videoApi.uploadFaceImage(file);
      personSeq += 1;
      const person = { key: `p${personSeq}`, url: result.url, preview: URL.createObjectURL(file) };
      set((s) => ({ isUploadingPhoto: false, people: [...s.people, person].slice(0, RECAST_MAX_PEOPLE) }));
    } catch (err) {
      set({ isUploadingPhoto: false, peopleError: getErrorMessage(err, 'Photo upload failed') });
    }
  },

  addPhotoAsset: (asset) => {
    if (get().people.length >= RECAST_MAX_PEOPLE) return;
    const problem = recastPhotoProblem(asset);
    if (problem) {
      set({ peopleError: `That photo cannot be used: ${problem}.` });
      return;
    }
    if (get().people.some((p) => p.assetId === asset.id)) {
      set({ peopleError: 'That photo is already in the list. Use one photo per person.' });
      return;
    }
    personSeq += 1;
    set((s) => ({
      peopleError: null,
      people: [...s.people, { key: `p${personSeq}`, url: asset.url, preview: asset.url, assetId: asset.id }],
    }));
  },

  removePerson: (key) => {
    const person = get().people.find((p) => p.key === key);
    revoke(person?.preview);
    set((s) => ({ people: s.people.filter((p) => p.key !== key), peopleError: null }));
  },

  movePerson: (key, direction) => {
    const people = [...get().people];
    const i = people.findIndex((p) => p.key === key);
    const j = i + direction;
    if (i < 0 || j < 0 || j >= people.length) return;
    [people[i], people[j]] = [people[j], people[i]];
    set({ people });
  },

  setResolution: (resolution) => set({ resolution }),
  setEnhanceRealism: (enhanceRealism) => set({ enhanceRealism }),
  setPrompt: (prompt) => set({ prompt }),

  generate: async () => {
    const { video, people, resolution, enhanceRealism, prompt, isGenerating } = get();
    if (isGenerating) return;
    if (!video || people.length === 0) {
      set({ error: 'Add a source video and at least one photo.' });
      return;
    }
    set({ isGenerating: true, error: null, generatedVideo: null, jobId: null, progress: 5, statusText: 'Submitting...' });

    let jobId: string;
    try {
      const job = await videoApi.submitRecast({
        videoUrl: video.assetId ? null : video.url,
        videoAssetId: video.assetId ?? null,
        references: people.map((p) => ({ url: p.url, assetId: p.assetId })),
        resolution,
        prompt,
        enhanceRealism,
      });
      jobId = job.jobId;
      set({ jobId, progress: 10, statusText: 'Queued...' });
    } catch (err) {
      set({ isGenerating: false, progress: 0, statusText: '', error: getErrorMessage(err, 'Could not start the recast') });
      return;
    }

    let polls = 0;
    const poll = async (): Promise<void> => {
      if (get().jobId !== jobId || !get().isGenerating) return; // started over
      try {
        const status = await videoApi.getJobStatus(jobId);
        const labels: Record<string, [number, string]> = {
          pending: [10, 'Queued...'],
          in_progress: [50, 'Recasting the people...'],
          processing: [85, 'Saving the video...'],
          ready: [90, 'Downloading the video...'],
          completed: [95, 'Finishing...'],
        };
        const [progress, statusText] = labels[status.status] ?? [get().progress, get().statusText];
        set({ progress, statusText });
        if (status.status === 'failed') throw new Error(status.error || 'The recast failed');
        if (status.status === 'ready' || status.status === 'completed') {
          try {
            const result = await videoApi.getJobResult(jobId);
            if (get().jobId !== jobId) return;
            set({ generatedVideo: result.video, isGenerating: false, progress: 100, statusText: 'Complete' });
            return;
          } catch (resultError) {
            // 409: the scheduler is finishing it; keep polling.
            if (!(resultError instanceof AxiosError && resultError.response?.status === 409)) throw resultError;
          }
        }
        polls += 1;
        if (polls >= MAX_POLLS) throw new Error('The recast is taking too long. Check My Jobs later.');
        setTimeout(poll, POLL_MS);
      } catch (err) {
        if (get().jobId !== jobId) return;
        // One character (Kling) runs on a different provider than Recast.
        const message = withContentFilterAdvice(
          getErrorMessage(err, 'The recast failed'),
          'Reword the prompt or use other photos, or switch to One character, which uses a different provider.',
        );
        set({ isGenerating: false, progress: 0, statusText: '', error: message });
      }
    };
    setTimeout(poll, 3000);
  },

  clearError: () => set({ error: null }),

  startOver: () => {
    const { video, people } = get();
    revoke(video?.preview);
    people.forEach((p) => revoke(p.preview));
    set({
      video: null, videoError: null, isUploadingVideo: false, people: [], peopleError: null, isUploadingPhoto: false,
      prompt: '', isGenerating: false, jobId: null, progress: 0, statusText: '', generatedVideo: null, error: null,
    });
  },
}));
