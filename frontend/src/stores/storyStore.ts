import { create } from 'zustand';
import { AxiosError } from 'axios';
import {
  storyApi,
  STORY_VIDEO_MODELS,
  STORY_VIDEO_MODEL_ORDER,
  DEFAULT_STORY_VIDEO_MODEL,
  storyAspectRatios,
  storyRefName,
  storyPreviewSettings,
  STORY_PROMPT_MAX_CHARS,
  type StoryVideo,
  type StoryMode,
  type StoryVideoModel,
  type StoryKeyframeInput,
} from '../api/story';
import { getErrorMessage, isContentFilterError, CONTENT_FILTER_CODE } from '@/utils/errors';


interface StoryGenerationJob {
  jobId: string;
  status: 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
}

// Reference file with local preview and hosted URL
interface RefFile {
  id: string;
  file: File;
  preview: string;  // local blob URL
  url: string | null; // hosted URL after upload
  uploading: boolean;
}

// Keyframe image pinned to a time in the clip (FLUX 3 Max keyframes mode)
export interface KeyframeRef extends RefFile {
  timeSeconds: number | null;
}

export interface StoryClipPrefill {
  prompt: string;
  references: { url: string; label: string }[];
  // A hosted first frame (the shot's keyframe or a product photo): the clip
  // opens on it in First & Last Frame mode, and references are not used.
  startFrame?: { url: string; label: string } | null;
  durationSeconds?: number | null;
  aspect?: string | null;
}

// The clip maker's prompt box takes at most this many characters.
const PROMPT_MAX_CHARS = STORY_PROMPT_MAX_CHARS;

// The error to show and its code ('content_filter' when the provider's
// content filter blocked the clip, so the page can offer another provider).
function errorState(error: unknown, code?: string | null): { error: string; errorCode: string | null } {
  const message = getErrorMessage(error);
  return { error: message, errorCode: isContentFilterError(message, code) ? CONTENT_FILTER_CODE : null };
}

// A finished preview: the final render reuses its seed (families that take one).
export interface StoryPreviewTake {
  videoId: number;
  videoModel: StoryVideoModel;
  seed: number | null;
}

interface StoryState {
  // Model family and mode
  videoModel: StoryVideoModel;
  mode: StoryMode;

  // Prompt
  currentPrompt: string;
  originalPrompt: string | null;
  enhancedPrompt: string | null;
  isEnhancing: boolean;
  contentType: string;

  // Start & end frame (image-to-video)
  startFrame: RefFile | null;
  endFrame: RefFile | null;

  // Reference-to-video references
  refImages: RefFile[];
  refVideos: RefFile[];
  refAudios: RefFile[];

  // Keyframes
  keyframes: KeyframeRef[];

  // Soundtrack pinned to the clip (models with `soundtrack`, text and image modes)
  soundtrack: RefFile | null;

  // Generation settings
  duration: string;
  resolution: string;
  aspectRatio: string;
  generateAudio: boolean;

  // Subtitle settings
  addSubtitles: boolean;
  subtitleFontColor: string;
  subtitleStrokeColor: string;
  subtitleHighlightColor: string;
  subtitleBackgroundColor: string;
  subtitlePosition: string;
  subtitleFontSize: number;
  subtitleFontName: string;
  subtitleFontWeight: string;
  subtitleStrokeWidth: number;
  subtitleYOffset: number;
  subtitleWordsPerSubtitle: number;
  subtitleEnableAnimation: boolean;
  subtitleLanguage: string;

  // Generation state
  isGenerating: boolean;
  isUploading: boolean;
  generatedVideo: StoryVideo | null;
  error: string | null;
  errorCode: string | null;
  // Set while a preview renders and after it finishes.
  isPreviewing: boolean;
  lastPreview: StoryPreviewTake | null;
  currentJob: StoryGenerationJob | null;
  generationProgress: number;
  generationStatus: string;

  // Gallery
  videos: StoryVideo[];
  galleryPage: number;
  galleryTotalPages: number;
  galleryTotal: number;
  isLoadingGallery: boolean;

  // Actions
  setVideoModel: (model: StoryVideoModel) => void;
  setMode: (mode: StoryMode) => void;
  setPrompt: (prompt: string) => void;
  setContentType: (type: string) => void;
  setDuration: (d: string) => void;
  setResolution: (r: string) => void;
  setAspectRatio: (r: string) => void;
  setGenerateAudio: (g: boolean) => void;

  // Frame actions (image-to-video)
  setStartFrame: (file: File) => void;
  clearStartFrame: () => void;
  setEndFrame: (file: File) => void;
  clearEndFrame: () => void;

  // Reference actions (reference-to-video)
  addRefImage: (file: File) => void;
  removeRefImage: (id: string) => void;
  addRefVideo: (file: File) => void;
  removeRefVideo: (id: string) => void;
  addRefAudio: (file: File) => void;
  removeRefAudio: (id: string) => void;

  // Keyframe actions
  addKeyframe: (file: File) => void;
  removeKeyframe: (id: string) => void;
  setKeyframeTime: (id: string, seconds: number | null) => void;

  // Soundtrack actions
  setSoundtrack: (file: File) => void;
  clearSoundtrack: () => void;

  // Subtitle actions
  setAddSubtitles: (add: boolean) => void;
  setSubtitleFontColor: (color: string) => void;
  setSubtitleStrokeColor: (color: string) => void;
  setSubtitleHighlightColor: (color: string) => void;
  setSubtitleBackgroundColor: (color: string) => void;
  setSubtitlePosition: (position: string) => void;
  setSubtitleFontSize: (size: number) => void;
  setSubtitleFontName: (name: string) => void;
  setSubtitleFontWeight: (weight: string) => void;
  setSubtitleStrokeWidth: (width: number) => void;
  setSubtitleYOffset: (offset: number) => void;
  setSubtitleWordsPerSubtitle: (words: number) => void;
  setSubtitleEnableAnimation: (enable: boolean) => void;
  setSubtitleLanguage: (lang: string) => void;

  // Fill the clip maker from a Story Room shot or treatment: the prompt, the
  // length and aspect where the model allows them, and the hosted reference
  // images (used as they are, never uploaded again).
  prefillFromShot: (clip: StoryClipPrefill) => void;

  enhancePrompt: () => Promise<void>;
  // preview: render at the family's cheapest resolution and a short length
  // (storyPreviewSettings). seed: reuse a preview's seed for the final.
  generateStory: (options?: { preview?: boolean; seed?: number | null }) => Promise<void>;
  clearError: () => void;
  clearGeneratedVideo: () => void;
  cancelGeneration: () => void;
  reset: () => void;
  loadGallery: (page?: number, pageSize?: number) => Promise<void>;
  deleteVideo: (videoId: number) => Promise<void>;
}

let refIdCounter = 0;
const nextRefId = () => `ref_${++refIdCounter}_${Date.now()}`;

// Keep an aspect ratio if the model offers it in this mode, else its default.
function coerceAspect(model: StoryVideoModel, mode: StoryMode, current: string): string {
  const list = storyAspectRatios(model, mode);
  if (!list) return current; // not sent for this mode; keep the choice for later
  if (list.includes(current)) return current;
  return list.includes('16:9') ? '16:9' : list[0];
}

// Keep a duration the model offers, else the nearest one it does.
function coerceDuration(model: StoryVideoModel, current: string): string {
  const cfg = STORY_VIDEO_MODELS[model];
  if (cfg.durations.includes(current)) return current;
  const n = Number(current);
  if (current === 'auto' || !Number.isFinite(n)) return cfg.defaultDuration;
  const numeric = cfg.durations.filter((d) => d !== 'auto').map(Number);
  const nearest = numeric.reduce((best, d) => (Math.abs(d - n) < Math.abs(best - n) ? d : best), numeric[0]);
  return String(nearest);
}

// The model's equivalent of a mode: the third tab maps reference <-> keyframes.
function coerceMode(model: StoryVideoModel, mode: StoryMode): StoryMode {
  const modes = STORY_VIDEO_MODELS[model].modes.map((m) => m.value);
  if (modes.includes(mode)) return mode;
  if (mode === 'reference-to-video' || mode === 'keyframes') {
    return modes.find((m) => m === 'reference-to-video' || m === 'keyframes') ?? 'text-to-video';
  }
  return 'text-to-video';
}

// Drop references beyond a model's limits, releasing their previews.
function trimRefs<T extends RefFile>(list: T[], max: number): T[] {
  list.slice(max).forEach((r) => r.preview && URL.revokeObjectURL(r.preview));
  return list.slice(0, max);
}

const modelDefaults = (model: StoryVideoModel) => {
  const cfg = STORY_VIDEO_MODELS[model];
  return {
    duration: cfg.defaultDuration,
    resolution: cfg.defaultResolution,
    aspectRatio: coerceAspect(model, 'text-to-video', '16:9'),
  };
};

export const useStoryStore = create<StoryState>((set, get) => ({
  videoModel: DEFAULT_STORY_VIDEO_MODEL,
  mode: 'text-to-video',
  currentPrompt: '',
  originalPrompt: null,
  enhancedPrompt: null,
  isEnhancing: false,
  contentType: 'cinematic',
  startFrame: null,
  endFrame: null,
  refImages: [],
  refVideos: [],
  refAudios: [],
  keyframes: [],
  soundtrack: null,
  ...modelDefaults(DEFAULT_STORY_VIDEO_MODEL),
  generateAudio: true,
  addSubtitles: false,
  subtitleFontColor: 'white',
  subtitleStrokeColor: 'black',
  subtitleHighlightColor: 'purple',
  subtitleBackgroundColor: 'none',
  subtitlePosition: 'bottom',
  subtitleFontSize: 100,
  subtitleFontName: 'Montserrat',
  subtitleFontWeight: 'bold',
  subtitleStrokeWidth: 3,
  subtitleYOffset: 75,
  subtitleWordsPerSubtitle: 3,
  subtitleEnableAnimation: true,
  subtitleLanguage: 'en',
  isGenerating: false,
  isUploading: false,
  generatedVideo: null,
  error: null,
  errorCode: null,
  isPreviewing: false,
  lastPreview: null,
  currentJob: null,
  generationProgress: 0,
  generationStatus: '',
  videos: [],
  galleryPage: 1,
  galleryTotalPages: 0,
  galleryTotal: 0,
  isLoadingGallery: false,

  setVideoModel: (videoModel) => {
    const s = get();
    if (!STORY_VIDEO_MODELS[videoModel] || s.videoModel === videoModel) return;
    const cfg = STORY_VIDEO_MODELS[videoModel];
    const mode = coerceMode(videoModel, s.mode);
    set({
      videoModel,
      mode,
      duration: coerceDuration(videoModel, s.duration),
      resolution: cfg.resolutions.includes(s.resolution) ? s.resolution : cfg.defaultResolution,
      aspectRatio: coerceAspect(videoModel, mode, s.aspectRatio),
      refImages: trimRefs(s.refImages, cfg.maxRefImages),
      refVideos: trimRefs(s.refVideos, cfg.maxRefVideos),
      refAudios: trimRefs(s.refAudios, cfg.maxRefAudios),
      keyframes: trimRefs(s.keyframes, cfg.maxKeyframes),
      soundtrack: cfg.soundtrack ? s.soundtrack : null,
    });
  },
  setMode: (mode) => {
    const { videoModel, aspectRatio } = get();
    const next = coerceMode(videoModel, mode);
    set({ mode: next, aspectRatio: coerceAspect(videoModel, next, aspectRatio) });
  },
  setPrompt: (prompt) => set({ currentPrompt: prompt }),
  setContentType: (type) => set({ contentType: type }),
  setDuration: (d) => {
    const cfg = STORY_VIDEO_MODELS[get().videoModel];
    set({ duration: cfg.durations.includes(d) ? d : cfg.defaultDuration });
  },
  setResolution: (r) => {
    const cfg = STORY_VIDEO_MODELS[get().videoModel];
    set({ resolution: cfg.resolutions.includes(r) ? r : cfg.defaultResolution });
  },
  setAspectRatio: (r) => {
    const { videoModel, mode } = get();
    set({ aspectRatio: coerceAspect(videoModel, mode, r) });
  },
  setGenerateAudio: (g) => set({ generateAudio: g }),

  // Frame actions
  setStartFrame: (file) => {
    const preview = URL.createObjectURL(file);
    set({ startFrame: { id: nextRefId(), file, preview, url: null, uploading: false } });
  },
  clearStartFrame: () => {
    const f = get().startFrame;
    if (f) URL.revokeObjectURL(f.preview);
    set({ startFrame: null });
  },
  setEndFrame: (file) => {
    const preview = URL.createObjectURL(file);
    set({ endFrame: { id: nextRefId(), file, preview, url: null, uploading: false } });
  },
  clearEndFrame: () => {
    const f = get().endFrame;
    if (f) URL.revokeObjectURL(f.preview);
    set({ endFrame: null });
  },

  // Reference actions
  addRefImage: (file) => {
    const s = get();
    if (s.refImages.length >= STORY_VIDEO_MODELS[s.videoModel].maxRefImages) return;
    const preview = URL.createObjectURL(file);
    set((st) => ({ refImages: [...st.refImages, { id: nextRefId(), file, preview, url: null, uploading: false }] }));
  },
  removeRefImage: (id) => {
    const item = get().refImages.find((r) => r.id === id);
    if (item) URL.revokeObjectURL(item.preview);
    set((s) => ({ refImages: s.refImages.filter((r) => r.id !== id) }));
  },
  addRefVideo: (file) => {
    const s = get();
    if (s.refVideos.length >= STORY_VIDEO_MODELS[s.videoModel].maxRefVideos) return;
    const preview = URL.createObjectURL(file);
    set((st) => ({ refVideos: [...st.refVideos, { id: nextRefId(), file, preview, url: null, uploading: false }] }));
  },
  removeRefVideo: (id) => {
    const item = get().refVideos.find((r) => r.id === id);
    if (item) URL.revokeObjectURL(item.preview);
    set((s) => ({ refVideos: s.refVideos.filter((r) => r.id !== id) }));
  },
  addRefAudio: (file) => {
    const s = get();
    if (s.refAudios.length >= STORY_VIDEO_MODELS[s.videoModel].maxRefAudios) return;
    set((st) => ({ refAudios: [...st.refAudios, { id: nextRefId(), file, preview: '', url: null, uploading: false }] }));
  },
  removeRefAudio: (id) => {
    set((s) => ({ refAudios: s.refAudios.filter((r) => r.id !== id) }));
  },

  // Keyframe actions. The first keyframe sits at 0s; each new one lands two
  // seconds after the latest, within the clip.
  addKeyframe: (file) => {
    const s = get();
    const cfg = STORY_VIDEO_MODELS[s.videoModel];
    if (s.keyframes.length >= cfg.maxKeyframes) return;
    const clip = Number(s.duration) || Number(cfg.defaultDuration);
    const latest = s.keyframes.reduce((m, k) => Math.max(m, k.timeSeconds ?? 0), 0);
    const timeSeconds = s.keyframes.length === 0 ? 0 : Math.min(clip, latest + 2);
    const preview = URL.createObjectURL(file);
    set((st) => ({
      keyframes: [...st.keyframes, { id: nextRefId(), file, preview, url: null, uploading: false, timeSeconds }],
    }));
  },
  removeKeyframe: (id) => {
    const item = get().keyframes.find((k) => k.id === id);
    if (item) URL.revokeObjectURL(item.preview);
    set((s) => ({ keyframes: s.keyframes.filter((k) => k.id !== id) }));
  },
  setKeyframeTime: (id, seconds) => {
    set((s) => ({ keyframes: s.keyframes.map((k) => (k.id === id ? { ...k, timeSeconds: seconds } : k)) }));
  },

  // Soundtrack actions (audio files have no preview URL)
  setSoundtrack: (file) => set({ soundtrack: { id: nextRefId(), file, preview: '', url: null, uploading: false } }),
  clearSoundtrack: () => set({ soundtrack: null }),

  // Subtitle actions
  setAddSubtitles: (add) => set({ addSubtitles: add }),
  setSubtitleFontColor: (color) => set({ subtitleFontColor: color }),
  setSubtitleStrokeColor: (color) => set({ subtitleStrokeColor: color }),
  setSubtitleHighlightColor: (color) => set({ subtitleHighlightColor: color }),
  setSubtitleBackgroundColor: (color) => set({ subtitleBackgroundColor: color }),
  setSubtitlePosition: (position) => set({ subtitlePosition: position }),
  setSubtitleFontSize: (size) => set({ subtitleFontSize: size }),
  setSubtitleFontName: (name) => set({ subtitleFontName: name }),
  setSubtitleFontWeight: (weight) => set({ subtitleFontWeight: weight }),
  setSubtitleStrokeWidth: (width) => set({ subtitleStrokeWidth: width }),
  setSubtitleYOffset: (offset) => set({ subtitleYOffset: offset }),
  setSubtitleWordsPerSubtitle: (words) => set({ subtitleWordsPerSubtitle: words }),
  setSubtitleEnableAnimation: (enable) => set({ subtitleEnableAnimation: enable }),
  setSubtitleLanguage: (lang) => set({ subtitleLanguage: lang }),

  prefillFromShot: ({ prompt, references, startFrame, durationSeconds, aspect }) => {
    const s = get();
    if (s.isGenerating) return;
    // A start frame opens the clip in First & Last Frame mode when the
    // chosen model has it.
    const hasStartMode = (m: StoryVideoModel) => STORY_VIDEO_MODELS[m].modes.some((x) => x.value === 'image-to-video');
    const useStart = !!startFrame?.url && hasStartMode(s.videoModel);
    // Reference images need a model with a reference mode; keep the chosen
    // model when it has one, else take the first that does.
    const hasRefMode = (m: StoryVideoModel) => STORY_VIDEO_MODELS[m].modes.some((x) => x.value === 'reference-to-video');
    const videoModel = !useStart && references.length > 0 && !hasRefMode(s.videoModel)
      ? (STORY_VIDEO_MODEL_ORDER.find(hasRefMode) ?? s.videoModel)
      : s.videoModel;
    const cfg = STORY_VIDEO_MODELS[videoModel];
    const mode: StoryMode = useStart
      ? 'image-to-video'
      : references.length > 0 && hasRefMode(videoModel) ? 'reference-to-video' : 'text-to-video';

    // Release the previous inputs' previews.
    if (s.startFrame) URL.revokeObjectURL(s.startFrame.preview);
    if (s.endFrame) URL.revokeObjectURL(s.endFrame.preview);
    s.refImages.forEach((r) => URL.revokeObjectURL(r.preview));
    s.refVideos.forEach((r) => URL.revokeObjectURL(r.preview));
    s.keyframes.forEach((k) => URL.revokeObjectURL(k.preview));

    // A hosted reference has its URL already, so generateStory skips the
    // upload; the empty File only names it.
    const refImages: RefFile[] = (mode === 'reference-to-video' ? references : [])
      .slice(0, cfg.maxRefImages)
      .map((r, i) => ({
        id: nextRefId(),
        file: new File([], r.label || `Reference ${i + 1}`, { type: 'image/jpeg' }),
        preview: r.url,
        url: r.url,
        uploading: false,
      }));

    const duration = durationSeconds && durationSeconds > 0
      ? coerceDuration(videoModel, String(Math.round(durationSeconds)))
      : coerceDuration(videoModel, s.duration);

    set({
      videoModel,
      mode,
      currentPrompt: prompt.slice(0, PROMPT_MAX_CHARS),
      originalPrompt: null,
      enhancedPrompt: null,
      // Hosted like the references: generateStory uses the URL as it is.
      startFrame: useStart && startFrame
        ? {
            id: nextRefId(),
            file: new File([], startFrame.label || 'First frame', { type: 'image/jpeg' }),
            preview: startFrame.url,
            url: startFrame.url,
            uploading: false,
          }
        : null,
      endFrame: null,
      refImages,
      refVideos: [],
      refAudios: [],
      keyframes: [],
      soundtrack: cfg.soundtrack ? s.soundtrack : null,
      duration,
      resolution: cfg.resolutions.includes(s.resolution) ? s.resolution : cfg.defaultResolution,
      aspectRatio: coerceAspect(videoModel, mode, aspect || s.aspectRatio),
      generatedVideo: null,
      error: null,
      errorCode: null,
      lastPreview: null,
    });
  },

  enhancePrompt: async () => {
    const s = get();
    const { currentPrompt, contentType, videoModel, mode } = s;
    if (!currentPrompt.trim()) return;
    const cfg = STORY_VIDEO_MODELS[videoModel];
    // How the prompt names each upload, in order, so the enhancer binds them.
    const referenceTags = mode === 'reference-to-video'
      ? [
          ...s.refImages.map((_, i) => storyRefName(videoModel, 'Image', i + 1)),
          ...s.refVideos.map((_, i) => storyRefName(videoModel, 'Video', i + 1)),
          ...(cfg.maxRefAudios > 0 ? s.refAudios.map((_, i) => storyRefName(videoModel, 'Audio', i + 1)) : []),
        ]
      : undefined;
    const frames = mode === 'image-to-video'
      ? (s.startFrame && s.endFrame ? 'both' : s.endFrame && !s.startFrame ? 'end' : 'start')
      : undefined;
    set({ isEnhancing: true, error: null, errorCode: null });
    try {
      const result = await storyApi.enhancePrompt({
        topic: currentPrompt,
        contentType: contentType || undefined,
        videoModel,
        mode,
        duration: s.duration,
        aspectRatio: storyAspectRatios(videoModel, mode) ? s.aspectRatio : undefined,
        frames,
        referenceTags,
        generateAudio: cfg.audio ? s.generateAudio : undefined,
      });
      set({
        originalPrompt: result.originalPrompt,
        enhancedPrompt: result.enhancedPrompt,
        currentPrompt: result.enhancedPrompt,
        isEnhancing: false,
      });
    } catch (error) {
      set({ ...errorState(error), isEnhancing: false });
      throw error;
    }
  },

  generateStory: async (options) => {
    const state = get();
    if (!state.currentPrompt.trim()) {
      set({ error: 'Please enter a prompt', errorCode: null });
      return;
    }
    const cfg = STORY_VIDEO_MODELS[state.videoModel];
    const preview = options?.preview ? storyPreviewSettings(state.videoModel, state.duration, state.resolution) : null;
    const isPreview = preview !== null;
    const seed = !isPreview && cfg.takesSeed && options?.seed != null ? options.seed : undefined;

    set({
      isGenerating: true,
      isUploading: true,
      isPreviewing: isPreview,
      lastPreview: isPreview ? null : state.lastPreview,
      error: null,
      errorCode: null,
      generationProgress: 0,
      generationStatus: 'Uploading references...',
      currentJob: null,
      generatedVideo: null,
    });

    try {
      // Upload all reference files that don't have hosted URLs yet
      let imageUrl: string | undefined;
      let endImageUrl: string | undefined;
      let imageUrls: string[] | undefined;
      let videoUrls: string[] | undefined;
      let audioUrls: string[] | undefined;
      let keyframes: StoryKeyframeInput[] | undefined;
      let targetAudioUrl: string | undefined;

      if (cfg.soundtrack && state.soundtrack && (state.mode === 'text-to-video' || state.mode === 'image-to-video')) {
        targetAudioUrl = state.soundtrack.url ?? (await storyApi.uploadAudio(state.soundtrack.file)).url;
      }

      if (state.mode === 'image-to-video') {
        // Upload start frame
        if (state.startFrame?.file && !state.startFrame.url) {
          const res = await storyApi.uploadImage(state.startFrame.file);
          imageUrl = res.url;
        } else if (state.startFrame?.url) {
          imageUrl = state.startFrame.url;
        }
        // Upload end frame
        if (state.endFrame?.file && !state.endFrame.url) {
          const res = await storyApi.uploadImage(state.endFrame.file);
          endImageUrl = res.url;
        } else if (state.endFrame?.url) {
          endImageUrl = state.endFrame.url;
        }
      } else if (state.mode === 'reference-to-video') {
        // Upload reference images
        if (state.refImages.length > 0) {
          const urls: string[] = [];
          for (const ref of state.refImages) {
            if (ref.url) { urls.push(ref.url); continue; }
            const res = await storyApi.uploadImage(ref.file);
            urls.push(res.url);
          }
          imageUrls = urls;
        }
        // Upload reference videos
        if (state.refVideos.length > 0) {
          const urls: string[] = [];
          for (const ref of state.refVideos) {
            if (ref.url) { urls.push(ref.url); continue; }
            const res = await storyApi.uploadVideo(ref.file);
            urls.push(res.url);
          }
          videoUrls = urls;
        }
        // Upload reference audios (only models that take them)
        if (cfg.maxRefAudios > 0 && state.refAudios.length > 0) {
          const urls: string[] = [];
          for (const ref of state.refAudios) {
            if (ref.url) { urls.push(ref.url); continue; }
            const res = await storyApi.uploadAudio(ref.file);
            urls.push(res.url);
          }
          audioUrls = urls;
        }
      } else if (state.mode === 'keyframes') {
        const items: StoryKeyframeInput[] = [];
        for (const kf of state.keyframes) {
          const url = kf.url ?? (await storyApi.uploadImage(kf.file)).url;
          items.push({ imageUrl: url, timeSeconds: kf.timeSeconds });
        }
        keyframes = items;
      }

      set({ isUploading: false, generationStatus: 'Submitting job...' });

      const job = await storyApi.submitGenerateJob({
        prompt: state.currentPrompt,
        originalPrompt: state.originalPrompt || undefined,
        videoModel: state.videoModel,
        mode: state.mode,
        imageUrl: imageUrl,
        endImageUrl: endImageUrl,
        targetAudioUrl: targetAudioUrl,
        imageUrls: imageUrls,
        videoUrls: videoUrls,
        audioUrls: audioUrls,
        keyframes: keyframes,
        duration: preview?.duration ?? state.duration,
        resolution: preview?.resolution ?? state.resolution,
        // Models without an aspect ratio for this mode follow the image.
        aspectRatio: storyAspectRatios(state.videoModel, state.mode) ? state.aspectRatio : undefined,
        generateAudio: cfg.audio ? state.generateAudio : undefined,
        seed,
        // A preview checks composition and motion; subtitles wait for the final.
        addSubtitles: isPreview ? false : state.addSubtitles,
        subtitleFontColor: state.subtitleFontColor,
        subtitleStrokeColor: state.subtitleStrokeColor,
        subtitleHighlightColor: state.subtitleHighlightColor,
        subtitleBackgroundColor: state.subtitleBackgroundColor,
        subtitlePosition: state.subtitlePosition,
        subtitleFontSize: state.subtitleFontSize,
        subtitleFontName: state.subtitleFontName,
        subtitleFontWeight: state.subtitleFontWeight,
        subtitleStrokeWidth: state.subtitleStrokeWidth,
        subtitleYOffset: state.subtitleYOffset,
        subtitleWordsPerSubtitle: state.subtitleWordsPerSubtitle,
        subtitleEnableAnimation: state.subtitleEnableAnimation,
        subtitleLanguage: state.subtitleLanguage,
      });

      set({
        currentJob: { jobId: job.jobId, status: 'pending', progress: 0 },
        generationStatus: 'Queued...',
        generationProgress: 10,
      });

      // Poll for status
      const maxAttempts = 120;
      let attempts = 0;

      const pollStatus = async (): Promise<void> => {
        const currentState = get();
        if (!currentState.isGenerating || !currentState.currentJob) return;

        try {
          const status = await storyApi.getJobStatus(job.jobId);

          let progress = 10;
          let statusText = 'Queued...';
          if (status.status === 'in_progress') { progress = 50; statusText = 'Generating video...'; }
          else if (status.status === 'processing') { progress = 85; statusText = 'Processing video...'; }
          else if (status.status === 'ready' || status.status === 'completed') { progress = 90; statusText = 'Downloading video...'; }

          set({
            currentJob: { jobId: job.jobId, status: status.status, progress: status.progress, logs: status.logs, error: status.error },
            generationProgress: progress,
            generationStatus: statusText,
          });

          if (status.status === 'ready' || status.status === 'completed') {
            try {
              const result = await storyApi.getJobResult(job.jobId);
              set({
                generatedVideo: result.video,
                isGenerating: false,
                currentJob: null,
                generationProgress: 100,
                generationStatus: 'Complete!',
                lastPreview: isPreview
                  ? { videoId: result.video.id, videoModel: state.videoModel, seed: result.video.seed ?? null }
                  : null,
              });
              return;
            } catch (resultError) {
              if (resultError instanceof AxiosError && resultError.response?.status === 409) {
                attempts++;
                if (attempts < maxAttempts) { setTimeout(pollStatus, 15000); return; }
              }
              throw resultError;
            }
          }

          if (status.status === 'failed') {
            set({ ...errorState(new Error(status.error || 'Story generation failed'), status.errorCode), isGenerating: false, currentJob: null, generationProgress: 0, generationStatus: '' });
            return;
          }

          attempts++;
          if (attempts < maxAttempts) setTimeout(pollStatus, 15000);
          else throw new Error('Story generation timed out');
        } catch (error) {
          set({ ...errorState(error), isGenerating: false, currentJob: null, generationProgress: 0, generationStatus: '' });
        }
      };

      pollStatus();
    } catch (error: unknown) {
      set({ ...errorState(error), isGenerating: false, isUploading: false, currentJob: null, generationProgress: 0, generationStatus: '' });
      throw error;
    }
  },

  clearError: () => set({ error: null, errorCode: null }),
  clearGeneratedVideo: () => set({ generatedVideo: null }),
  cancelGeneration: () => set({ isGenerating: false, currentJob: null, generationProgress: 0, generationStatus: '' }),

  reset: () => {
    // Revoke blob URLs
    const s = get();
    if (s.startFrame) URL.revokeObjectURL(s.startFrame.preview);
    if (s.endFrame) URL.revokeObjectURL(s.endFrame.preview);
    s.refImages.forEach((r) => URL.revokeObjectURL(r.preview));
    s.refVideos.forEach((r) => URL.revokeObjectURL(r.preview));
    s.keyframes.forEach((k) => URL.revokeObjectURL(k.preview));

    // The chosen model stays; its settings go back to their defaults.
    const defaults = modelDefaults(s.videoModel);
    set({
      currentPrompt: '',
      originalPrompt: null,
      enhancedPrompt: null,
      isEnhancing: false,
      contentType: 'cinematic',
      startFrame: null,
      endFrame: null,
      refImages: [],
      refVideos: [],
      refAudios: [],
      keyframes: [],
      soundtrack: null,
      ...defaults,
      aspectRatio: coerceAspect(s.videoModel, s.mode, defaults.aspectRatio),
      generateAudio: true,
      addSubtitles: false,
      subtitleFontColor: 'white',
      subtitleStrokeColor: 'black',
      subtitleHighlightColor: 'purple',
      subtitleBackgroundColor: 'none',
      subtitlePosition: 'bottom',
      subtitleFontSize: 100,
      subtitleFontName: 'Montserrat',
      subtitleFontWeight: 'bold',
      subtitleStrokeWidth: 3,
      subtitleYOffset: 75,
      subtitleWordsPerSubtitle: 3,
      subtitleEnableAnimation: true,
      subtitleLanguage: 'en',
      isGenerating: false,
      isUploading: false,
      generatedVideo: null,
      error: null,
      errorCode: null,
      isPreviewing: false,
      lastPreview: null,
      currentJob: null,
      generationProgress: 0,
      generationStatus: '',
    });
  },

  loadGallery: async (page = 1, pageSize = 20) => {
    set({ isLoadingGallery: true, error: null });
    try {
      const result = await storyApi.getGallery(page, pageSize);
      set({ videos: result.videos, galleryPage: result.page, galleryTotalPages: result.totalPages, galleryTotal: result.total, isLoadingGallery: false });
    } catch (error) {
      set({ error: getErrorMessage(error), isLoadingGallery: false });
    }
  },

  deleteVideo: async (videoId: number) => {
    try {
      await storyApi.deleteVideo(videoId);
      set((state) => ({ videos: state.videos.filter((v) => v.id !== videoId), galleryTotal: state.galleryTotal - 1 }));
    } catch (error) {
      set({ error: getErrorMessage(error) });
      throw error;
    }
  },
}));
