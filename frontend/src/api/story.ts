import apiClient from './client';

// Story video response type
export interface StoryVideo {
  id: number;
  filename: string;
  thumbnailUrl?: string;
  url: string;
  prompt: string;
  originalPrompt?: string;
  videoType: string;
  hasSubtitles: number;
  durationSeconds?: number;
  width?: number;
  height?: number;
  fps?: number;
  model?: string;
  seed?: number;
  fileSizeBytes?: number;
  createdAt: string;
}

export interface EnhancePromptRequest {
  topic: string;
  style?: string;
  contentType?: string;
  videoModel?: StoryVideoModel;
  // The clip the prompt is for: the enhancer writes the whole shot for text
  // to video, only motion and camera over supplied frames, and names
  // references by their tags.
  mode?: StoryMode;
  duration?: string;
  aspectRatio?: string;
  frames?: 'start' | 'end' | 'both';
  referenceTags?: string[];
  generateAudio?: boolean;
}

export interface EnhancePromptResponse {
  originalPrompt: string;
  enhancedPrompt: string;
}

// Kept for backward compat: alias
export type StoryUploadImageResponse = StoryUploadResponse;

// 'image-to-video' is first frame plus optional last frame. The third mode
// differs per model: 'reference-to-video' (H3 Max, Seedance, Kling),
// 'keyframes' (FLUX).
export type StoryMode = 'text-to-video' | 'image-to-video' | 'reference-to-video' | 'keyframes';

export type StoryVideoModel = 'h3-max' | 'seedance-2.5' | 'kling-v4' | 'flux-3-max' | 'omni-flash';

// Worst-case reference tokens per input, for models that price tokens beyond
// a per-request allowance (backend STORY_VIDEO_MODELS[...]['reference_tokens']).
export interface StoryReferenceTokens {
  included: number;
  perImage: number;
  // By output resolution; video references cost more tokens at 768p and up.
  perVideoSecond: Record<string, number>;
  perAudioSecond: number;
  maxVideoSeconds: number;
  maxAudioSeconds: number;
}

// Reference videos change the bill (backend STORY_VIDEO_MODELS[...]
// ['video_reference_pricing']): a per-second rate (storyVideoRefKey) on the
// input plus the output length, at least minOutputMultiple times the output.
// The page does not know the upload lengths, so it shows the maximum.
export interface StoryVideoReferencePricing {
  maxInputSeconds: number;
  minOutputMultiple: number;
}

// Mirrors STORY_VIDEO_MODELS in backend/app/clients/fal_client.py, which
// validates every request. Prices are not here: they come per second from
// the price table (usePricingStore().getModelCost('video:<id>:<res>')).
export interface StoryModelConfig {
  id: StoryVideoModel;
  label: string;
  tagline: string;
  // In tab order; the label is what the mode tab shows.
  modes: { value: StoryMode; label: string }[];
  durations: string[];
  defaultDuration: string;
  // Seconds the estimate assumes for 'auto', the longest it can run.
  autoReserveSeconds?: number;
  resolutions: string[];
  defaultResolution: string;
  // Per mode; null when the model takes no aspect ratio (follows the image).
  aspectRatios: Partial<Record<StoryMode, string[] | null>>;
  audio: boolean;
  maxRefImages: number;
  maxRefVideos: number;
  maxRefAudios: number;
  // Reference mode needs at least one reference.
  requiresReference: boolean;
  maxKeyframes: number;
  keyframesFps: number;
  // Start & end frame needs the first frame (false: either frame will do).
  startRequired?: boolean;
  // Text and image modes take an uploaded soundtrack pinned to the clip.
  soundtrack?: boolean;
  // How the prompt names references: '@Image1', 'Image 1' or '<IMAGE_REF_0>'.
  refNaming?: 'at' | 'plain' | 'tag';
  referenceTokens?: StoryReferenceTokens;
  videoReferencePricing?: StoryVideoReferencePricing;
  // The clip always has sound although there is no audio switch.
  alwaysAudio?: boolean;
  // Who makes the model: a provider's content filter refuses the same
  // request on every model it makes, so a blocked clip switches provider.
  provider: string;
  // Preview: the cheapest resolution, for a composition and motion check
  // before the final render.
  previewResolution: string;
  // The family takes a seed, so the final render reuses the preview's.
  takesSeed?: boolean;
}

// Tab names. "Characters & references" keeps identity and look without
// fixing the opening moment; "Start frame" opens on the user's picture.
const REFERENCE_TAB = 'Characters & references';
const START_END_TAB = 'Start & end frame';

// The prompt box holds this many characters: the families read a shot of a
// few sentences, and long clips add time-coded beats. The API accepts more
// (CreateStoryRequest.prompt); the enhancer takes the same limit.
export const STORY_PROMPT_MAX_CHARS = 2500;

// A preview renders at most this many seconds.
export const STORY_PREVIEW_MAX_SECONDS = 5;

// Past this length a clip tends to fall apart; the enhancer writes timed beats.
export const STORY_LONG_CLIP_SECONDS = 10;

const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => String(from + i));

const SEEDANCE_ASPECTS = ['auto', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16'];
const KLING_ASPECTS = ['16:9', '9:16', '1:1', '21:9'];
const FLUX_MAX_ASPECTS = ['auto', '21:9', '2:1', '16:9', '4:3', '1:1', '3:4', '9:16'];
const H3_ASPECTS = ['21:9', '16:9', '4:3', '1:1', '3:4', '9:16'];

export const STORY_VIDEO_MODELS: Record<StoryVideoModel, StoryModelConfig> = {
  'h3-max': {
    id: 'h3-max',
    label: 'MiniMax H3 Max',
    tagline: 'Fastest, native sound',
    modes: [
      { value: 'text-to-video', label: 'Text to Video' },
      { value: 'reference-to-video', label: REFERENCE_TAB },
      { value: 'image-to-video', label: START_END_TAB },
    ],
    durations: range(2, 15),
    defaultDuration: '5',
    resolutions: ['480p', '768p', '1080p'],
    defaultResolution: '768p',
    aspectRatios: {
      'text-to-video': H3_ASPECTS,
      'image-to-video': null,
      'reference-to-video': ['adaptive', ...H3_ASPECTS],
    },
    audio: false,
    maxRefImages: 9,
    maxRefVideos: 3,
    maxRefAudios: 3,
    requiresReference: true,
    maxKeyframes: 0,
    keyframesFps: 24,
    startRequired: false,
    soundtrack: true,
    refNaming: 'plain',
    provider: 'MiniMax',
    previewResolution: '480p',
    takesSeed: true,
    referenceTokens: {
      included: 4096,
      perImage: 2560,
      perVideoSecond: { '480p': 2652, '768p': 6855, '1080p': 6855 },
      perAudioSecond: 256,
      maxVideoSeconds: 15,
      maxAudioSeconds: 15,
    },
  },
  'seedance-2.5': {
    id: 'seedance-2.5',
    label: 'Seedance 2.5',
    tagline: 'Native audio, lip-sync',
    modes: [
      { value: 'text-to-video', label: 'Text to Video' },
      { value: 'reference-to-video', label: REFERENCE_TAB },
      { value: 'image-to-video', label: START_END_TAB },
    ],
    durations: ['auto', ...range(4, 15)],
    defaultDuration: '5',
    autoReserveSeconds: 30,
    resolutions: ['480p', '720p'],
    defaultResolution: '720p',
    aspectRatios: {
      'text-to-video': SEEDANCE_ASPECTS,
      'image-to-video': null,
      'reference-to-video': SEEDANCE_ASPECTS,
    },
    audio: true,
    maxRefImages: 9,
    maxRefVideos: 3,
    maxRefAudios: 3,
    requiresReference: false,
    maxKeyframes: 0,
    keyframesFps: 24,
    videoReferencePricing: { maxInputSeconds: 31, minOutputMultiple: 1 },
    provider: 'ByteDance',
    previewResolution: '480p',
  },
  'kling-v4': {
    id: 'kling-v4',
    label: 'Kling v4',
    tagline: 'Up to 30s, 1080p',
    modes: [
      { value: 'text-to-video', label: 'Text to Video' },
      { value: 'reference-to-video', label: REFERENCE_TAB },
      { value: 'image-to-video', label: START_END_TAB },
    ],
    durations: range(3, 30),
    defaultDuration: '5',
    resolutions: ['720p', '1080p'],
    defaultResolution: '1080p',
    aspectRatios: {
      'text-to-video': KLING_ASPECTS,
      'image-to-video': null,
      'reference-to-video': ['auto', ...KLING_ASPECTS],
    },
    audio: false,
    maxRefImages: 10,
    maxRefVideos: 5,
    maxRefAudios: 0,
    requiresReference: true,
    maxKeyframes: 0,
    keyframesFps: 24,
    videoReferencePricing: { maxInputSeconds: 30, minOutputMultiple: 2 },
    provider: 'Kuaishou',
    previewResolution: '720p',
  },
  'flux-3-max': {
    id: 'flux-3-max',
    label: 'FLUX 3 Max',
    tagline: 'Keyframes, native audio',
    modes: [
      { value: 'text-to-video', label: 'Text to Video' },
      { value: 'keyframes', label: 'Keyframes' },
      { value: 'image-to-video', label: START_END_TAB },
    ],
    durations: range(5, 20),
    defaultDuration: '5',
    resolutions: ['720p', '1080p'],
    defaultResolution: '720p',
    aspectRatios: {
      'text-to-video': FLUX_MAX_ASPECTS,
      'image-to-video': FLUX_MAX_ASPECTS,
      keyframes: FLUX_MAX_ASPECTS,
    },
    audio: true,
    maxRefImages: 0,
    maxRefVideos: 0,
    maxRefAudios: 0,
    requiresReference: false,
    maxKeyframes: 10,
    keyframesFps: 24,
    provider: 'Black Forest Labs',
    previewResolution: '720p',
    takesSeed: true,
  },
  'omni-flash': {
    id: 'omni-flash',
    label: 'Gemini Omni Flash',
    tagline: 'v1.1, up to 4K',
    modes: [
      { value: 'text-to-video', label: 'Text to Video' },
      { value: 'reference-to-video', label: REFERENCE_TAB },
      { value: 'image-to-video', label: START_END_TAB },
    ],
    durations: range(3, 10),
    defaultDuration: '8',
    resolutions: ['360p', '720p', '1080p', '4k'],
    defaultResolution: '720p',
    aspectRatios: {
      'text-to-video': ['16:9', '9:16'],
      'image-to-video': ['16:9', '9:16'],
      'reference-to-video': ['16:9', '9:16'],
    },
    audio: false,
    alwaysAudio: true,
    maxRefImages: 10,
    maxRefVideos: 3,
    maxRefAudios: 0,
    requiresReference: true,
    maxKeyframes: 0,
    keyframesFps: 24,
    refNaming: 'tag',
    provider: 'Google',
    previewResolution: '360p',
  },
};

export const STORY_VIDEO_MODEL_ORDER: StoryVideoModel[] = ['h3-max', 'seedance-2.5', 'kling-v4', 'flux-3-max', 'omni-flash'];

// After a content filter block, models from other providers in this order:
// providers' filters differ, most permissive first (Google's blocks the most).
export const STORY_FILTER_SWITCH_ORDER: StoryVideoModel[] = ['flux-3-max', 'kling-v4', 'seedance-2.5', 'h3-max', 'omni-flash'];

// One line under the mode tabs.
export const STORY_MODE_HINTS: Partial<Record<StoryMode, string>> = {
  'reference-to-video': 'References keep identity and look. To open on your picture, use Start & end frame.',
  'image-to-video': 'The clip opens on your picture. To keep a character without fixing the opening, use Characters & references.',
};

// The preview of a clip: the family's cheapest resolution and at most
// STORY_PREVIEW_MAX_SECONDS ("auto" becomes a fixed short length), or null
// when that would be the same render as the final.
export function storyPreviewSettings(
  model: StoryVideoModel,
  duration: string,
  resolution: string,
): { duration: string; resolution: string } | null {
  const cfg = STORY_VIDEO_MODELS[model];
  const fixed = cfg.durations.filter((d) => d !== 'auto').map(Number);
  const wanted = duration === 'auto' ? STORY_PREVIEW_MAX_SECONDS : Math.min(Number(duration) || STORY_PREVIEW_MAX_SECONDS, STORY_PREVIEW_MAX_SECONDS);
  const seconds = fixed.reduce((best, d) => (d <= wanted && d > best ? d : best), Math.min(...fixed));
  const preview = { duration: String(seconds), resolution: cfg.previewResolution };
  if (preview.resolution === resolution && preview.duration === duration) return null;
  return preview;
}
export const DEFAULT_STORY_VIDEO_MODEL: StoryVideoModel = 'h3-max';

// How the prompt refers to the nth reference of a kind ('Image' etc.).
// n counts from 1; tag-style names count from 0 (<IMAGE_REF_0> is the first).
export function storyRefName(model: StoryVideoModel, kind: 'Image' | 'Video' | 'Audio', n: number): string {
  const naming = STORY_VIDEO_MODELS[model].refNaming;
  if (naming === 'plain') return `${kind} ${n}`;
  if (naming === 'tag') return `<${kind.toUpperCase()}_REF_${n - 1}>`;
  return `@${kind}${n}`;
}

// Price key for reference tokens beyond a request's allowance (per 1,000).
export const storyReferenceTokensKey = (model: StoryVideoModel) => `video:${model}:reference-1k-tokens`;

// Worst-case reference tokens beyond the allowance, as the backend estimates
// them (0 for models without token pricing or outside reference mode).
export function storyReferenceTokenBudget(
  model: StoryVideoModel,
  mode: StoryMode,
  images: number,
  videos: number,
  audios: number,
  resolution?: string,
): number {
  const rt = STORY_VIDEO_MODELS[model].referenceTokens;
  if (!rt || mode !== 'reference-to-video') return 0;
  const perVideo = (resolution && rt.perVideoSecond[resolution]) || Math.max(...Object.values(rt.perVideoSecond));
  let tokens = images * rt.perImage;
  if (videos > 0) tokens += perVideo * rt.maxVideoSeconds;
  if (audios > 0) tokens += rt.perAudioSecond * rt.maxAudioSeconds;
  return Math.max(0, Math.ceil(tokens) - rt.included);
}

// Per-second price key with reference videos (backend pricing.video_ref_key).
export const storyVideoRefKey = (model: StoryVideoModel, resolution: string) => `video:${model}:${resolution}:video-ref`;

// Seconds billed with reference videos, at the longest inputs fal accepts, or
// null when the model and mode do not price reference videos.
export function storyVideoRefSeconds(
  model: StoryVideoModel,
  mode: StoryMode,
  videos: number,
  outputSeconds: number,
): number | null {
  const vr = STORY_VIDEO_MODELS[model].videoReferencePricing;
  if (!vr || mode !== 'reference-to-video' || videos <= 0) return null;
  return Math.max(vr.maxInputSeconds + outputSeconds, vr.minOutputMultiple * outputSeconds);
}

// Aspect ratios a model offers in a mode (null: none, the image decides).
export function storyAspectRatios(model: StoryVideoModel, mode: StoryMode): string[] | null {
  const list = STORY_VIDEO_MODELS[model].aspectRatios[mode];
  return list === undefined ? null : list;
}

// Seconds a job is priced at: the duration, or the auto estimate.
export function storyBillableSeconds(model: StoryVideoModel, duration: string): number {
  if (duration === 'auto') return STORY_VIDEO_MODELS[model].autoReserveSeconds ?? 0;
  const n = Number(duration);
  return Number.isFinite(n) ? n : 0;
}

// The first problem with a keyframe list, or null. Same rules as the backend:
// frame = round(seconds * fps), unique, within the clip.
export function storyKeyframeIssue(times: (number | null)[], durationSeconds: number, fps: number): string | null {
  const seen = new Map<number, number>();
  for (let i = 0; i < times.length; i++) {
    const t = times[i] ?? (i === 0 ? 0 : null);
    if (t === null || !Number.isFinite(t)) return `Keyframe ${i + 1} needs a time in seconds`;
    if (t < 0 || t > durationSeconds) return `Keyframe ${i + 1} at ${t}s is outside the ${durationSeconds}s clip`;
    const frame = Math.round(t * fps);
    const other = seen.get(frame);
    if (other !== undefined) return `Keyframes ${other} and ${i + 1} land on the same frame`;
    seen.set(frame, i + 1);
  }
  return null;
}

export interface StoryKeyframeInput {
  imageUrl: string;
  timeSeconds: number | null;
}

export interface StoryUploadResponse {
  url: string;
  filename: string;
  fileSizeBytes: number;
  // Reference videos: the length the server measured (it prices on it).
  durationSeconds?: number;
  message: string;
}

export interface StoryGenerateRequest {
  prompt: string;
  originalPrompt?: string;
  videoModel?: StoryVideoModel;
  mode?: StoryMode;
  // Image-to-video (Start & end frame)
  imageUrl?: string;
  endImageUrl?: string;
  // Soundtrack pinned to the clip (H3 Max text and image modes)
  targetAudioUrl?: string;
  // Reference-to-video
  imageUrls?: string[];
  videoUrls?: string[];
  audioUrls?: string[];
  // Keyframes (FLUX 3 Max)
  keyframes?: StoryKeyframeInput[];
  // Common settings
  duration?: string;
  resolution?: string;
  aspectRatio?: string;
  generateAudio?: boolean;
  // A final render reuses its preview's seed (families that take one).
  seed?: number;
  // Subtitle settings
  addSubtitles?: boolean;
  subtitleFontColor?: string;
  subtitleStrokeColor?: string;
  subtitleHighlightColor?: string;
  subtitleBackgroundColor?: string;
  subtitlePosition?: string;
  subtitleFontSize?: number;
  subtitleFontName?: string;
  subtitleFontWeight?: string;
  subtitleStrokeWidth?: number;
  subtitleYOffset?: number;
  subtitleWordsPerSubtitle?: number;
  subtitleEnableAnimation?: boolean;
  subtitleLanguage?: string;
}

export interface StoryJobSubmitResponse {
  jobId: string;
  status: string;
  message: string;
}

export interface StoryJobStatusResponse {
  jobId: string;
  status: 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
  // 'content_filter' when the provider's content filter blocked the clip.
  errorCode?: string;
  createdAt?: string;
  startedAt?: string;
}

export interface StoryJobResultResponse {
  jobId: string;
  status: string;
  video: StoryVideo;
  completedAt?: string;
}

export interface StoryGalleryResponse {
  videos: StoryVideo[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// Transform snake_case video response to camelCase
function transformStoryVideo(data: Record<string, unknown>): StoryVideo {
  return {
    id: data.id as number,
    filename: data.filename as string,
    thumbnailUrl: data.thumbnail_url as string | undefined,
    url: data.url as string,
    prompt: data.prompt as string,
    originalPrompt: data.original_prompt as string | undefined,
    videoType: data.video_type as string,
    hasSubtitles: data.has_subtitles as number,
    durationSeconds: data.duration_seconds as number | undefined,
    width: data.width as number | undefined,
    height: data.height as number | undefined,
    fps: data.fps as number | undefined,
    model: data.model as string | undefined,
    seed: data.seed as number | undefined,
    fileSizeBytes: data.file_size_bytes as number | undefined,
    createdAt: data.created_at as string,
  };
}

export const storyApi = {
  // Enhance a story prompt using LLM (director-style)
  enhancePrompt: async (data: EnhancePromptRequest): Promise<EnhancePromptResponse> => {
    const response = await apiClient.post('/story/enhance-prompt', {
      topic: data.topic,
      style: data.style,
      content_type: data.contentType,
      video_model: data.videoModel,
      mode: data.mode,
      duration: data.duration,
      aspect_ratio: data.aspectRatio,
      frames: data.frames,
      reference_tags: data.referenceTags,
      generate_audio: data.generateAudio,
    });
    const responseData = response.data as Record<string, unknown>;
    return {
      originalPrompt: responseData.original_prompt as string,
      enhancedPrompt: responseData.enhanced_prompt as string,
    };
  },

  // Upload a source image for image-to-video mode
  uploadImage: async (file: File): Promise<StoryUploadImageResponse> => {
    const formData = new FormData();
    formData.append('image', file);

    const response = await apiClient.post('/story/upload-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      message: data.message as string,
    };
  },

  // Upload a reference video for reference-to-video mode
  uploadVideo: async (file: File): Promise<StoryUploadResponse> => {
    const formData = new FormData();
    formData.append('video', file);

    const response = await apiClient.post('/story/upload-video', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      durationSeconds: (data.duration_seconds as number | null) ?? undefined,
      message: data.message as string,
    };
  },

  // Upload a reference audio for reference-to-video mode
  uploadAudio: async (file: File): Promise<StoryUploadResponse> => {
    const formData = new FormData();
    formData.append('audio', file);

    const response = await apiClient.post('/story/upload-audio', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      message: data.message as string,
    };
  },

  // Submit async story generation job. Options left out use the model's defaults.
  submitGenerateJob: async (data: StoryGenerateRequest): Promise<StoryJobSubmitResponse> => {
    const response = await apiClient.post('/story/generate', {
      prompt: data.prompt,
      original_prompt: data.originalPrompt,
      video_model: data.videoModel ?? DEFAULT_STORY_VIDEO_MODEL,
      mode: data.mode ?? 'text-to-video',
      image_url: data.imageUrl,
      end_image_url: data.endImageUrl,
      target_audio_url: data.targetAudioUrl,
      image_urls: data.imageUrls,
      video_urls: data.videoUrls,
      audio_urls: data.audioUrls,
      keyframes: data.keyframes?.map((k) => ({ image_url: k.imageUrl, time_seconds: k.timeSeconds })),
      duration: data.duration,
      resolution: data.resolution,
      aspect_ratio: data.aspectRatio,
      generate_audio: data.generateAudio ?? true,
      seed: data.seed,
      // Subtitle settings
      add_subtitles: data.addSubtitles ?? false,
      subtitle_font_color: data.subtitleFontColor ?? 'white',
      subtitle_stroke_color: data.subtitleStrokeColor ?? 'black',
      subtitle_highlight_color: data.subtitleHighlightColor ?? 'purple',
      subtitle_background_color: data.subtitleBackgroundColor ?? 'none',
      subtitle_position: data.subtitlePosition ?? 'bottom',
      subtitle_font_size: data.subtitleFontSize ?? 100,
      subtitle_font_name: data.subtitleFontName ?? 'Montserrat',
      subtitle_font_weight: data.subtitleFontWeight ?? 'bold',
      subtitle_stroke_width: data.subtitleStrokeWidth ?? 3,
      subtitle_y_offset: data.subtitleYOffset ?? 75,
      subtitle_words_per_subtitle: data.subtitleWordsPerSubtitle ?? 3,
      subtitle_enable_animation: data.subtitleEnableAnimation ?? true,
      subtitle_language: data.subtitleLanguage ?? 'en',
    });
    const responseData = response.data as Record<string, unknown>;
    return {
      jobId: responseData.job_id as string,
      status: responseData.status as string,
      message: responseData.message as string,
    };
  },

  // Poll job status
  getJobStatus: async (jobId: string): Promise<StoryJobStatusResponse> => {
    const response = await apiClient.get(`/story/status/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed',
      progress: data.progress as number,
      logs: data.logs as string[] | undefined,
      error: data.error as string | undefined,
      errorCode: (data.error_code as string | null) ?? undefined,
      createdAt: data.created_at as string | undefined,
      startedAt: data.started_at as string | undefined,
    };
  },

  // Get job result (video)
  getJobResult: async (jobId: string): Promise<StoryJobResultResponse> => {
    const response = await apiClient.get(`/story/result/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as string,
      video: transformStoryVideo(data.video as Record<string, unknown>),
      completedAt: data.completed_at as string | undefined,
    };
  },

  // Get user's story video gallery
  getGallery: async (page: number = 1, pageSize: number = 20): Promise<StoryGalleryResponse> => {
    const response = await apiClient.get('/story/gallery', {
      params: { page, page_size: pageSize },
    });
    const data = response.data as Record<string, unknown>;
    return {
      videos: (data.videos as Record<string, unknown>[]).map(transformStoryVideo),
      total: data.total as number,
      page: data.page as number,
      pageSize: data.page_size as number,
      totalPages: data.total_pages as number,
    };
  },

  // Delete a story video
  deleteVideo: async (videoId: number): Promise<void> => {
    await apiClient.delete(`/story/${videoId}`);
  },

  // Download a story video
  downloadVideo: async (videoId: number): Promise<{ downloadUrl: string; filename: string }> => {
    const response = await apiClient.get(`/story/${videoId}/download`);
    const data = response.data as Record<string, unknown>;
    return {
      downloadUrl: data.download_url as string,
      filename: data.filename as string,
    };
  },
};
