// Motion Graphics Studio API (/api/motion-graphics). The contract is the
// docstring of backend/app/routers/motion_graphics.py; request bodies are
// backend/app/schemas/motion_graphics.py; responses are built by
// backend/app/services/motion_graphics/views.py (Project), jobs.job_view
// (Job), pricing.quote_view (Quote) and spec.Template.view (catalog).
//
// Types keep the wire's snake_case names.
import apiClient from './client';

export type MGAspect = '9:16' | '4:5' | '1:1' | '16:9';
export const MG_ASPECTS: MGAspect[] = ['9:16', '4:5', '1:1', '16:9'];
export type SafeZonePreset = 'organic' | 'strict_ads' | 'cover' | 'none';
export type Intensity = 'calm' | 'standard' | 'punchy';
export type JobKind = 'audio' | 'render';
export type JobStatus =
  | 'queued'
  | 'running'
  | 'render_queued'
  | 'rendering'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'cancelled';
export const ACTIVE_JOB: JobStatus[] = ['queued', 'running', 'render_queued', 'rendering'];

export interface SlotDef {
  key: string;
  kind: 'text' | 'longtext' | 'number' | 'image' | 'items' | 'bool' | 'choice';
  label: string;
  required: boolean;
  max_chars?: number;
  max_words?: number;
  max_items?: number;
  min?: number;
  max?: number;
  choices?: string[];
  help?: string;
  item_fields?: SlotDef[];
  ai_image?: boolean;
}

export interface SceneTypeDef {
  type: string;
  label: string;
  slots: SlotDef[];
  min_count: number;
  max_count: number;
  default_seconds: number;
  min_seconds: number;
  voiceover: boolean;
  removable: boolean;
}

export interface MGTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  aspects: MGAspect[];
  default_aspect: MGAspect;
  length: { min_seconds: number; max_seconds: number };
  scene_types: SceneTypeDef[];
  shared_scene_types: SceneTypeDef[];
  data_kind: 'race' | 'series' | 'tickers' | 'versus' | null;
  requires_source: boolean;
  requires_disclaimer: boolean;
  default_style: string;
  music_mood: string;
  sample_data: string | null;
}

export interface MGStyle {
  id: string;
  name: string;
  description: string;
  fonts: { display: string; text: string };
  swatches: string[];
  transition: string;
  text_animation: string;
}

export interface MGVoice {
  id: string;
  gender: string;
  accent: string;
  tone: string;
}

export interface MusicMood {
  id: string;
  label: string;
}

export interface MGCatalog {
  templates: MGTemplate[];
  styles: MGStyle[];
  aspects: MGAspect[];
  safe_zones: Record<MGAspect, Record<SafeZonePreset, { top: number; bottom: number; left: number; right: number }>>;
  safe_zone_presets: SafeZonePreset[];
  intensities: { id: Intensity; label: string }[];
  fonts: string[];
  voices: MGVoice[];
  default_voice: string;
  music_moods: MusicMood[];
  prices: Record<string, number>;
  price_units: Record<string, string>;
  limits: {
    max_seconds: Record<MGAspect, number>;
    image_max_bytes: number;
    audio_max_bytes: number;
    audio_max_seconds: number;
    drafts_per_hour: number;
  };
}

export type SlotValue = string | number | boolean | null | UploadRef | Record<string, unknown>[];
export interface UploadRef {
  upload_id: string;
  ai?: boolean;
}

export interface SpecScene {
  id: string;
  type: string;
  slots: Record<string, SlotValue | undefined>;
  duration: number | null;
  voiceover: string | null;
}

export interface DataTable {
  columns: string[];
  rows: (string | number | null)[][];
}

export interface DataOptions {
  top_n?: number | null;
  period_seconds?: number | null;
  chart?: 'auto' | 'line' | 'bar' | 'donut' | null;
  highlight?: string | null;
  prefix?: string | null;
  suffix?: string | null;
  decimals?: number | null;
  compact?: boolean | null;
}

export interface SpecOptions {
  loop: boolean;
  captions: boolean | null;
  safe_zone: SafeZonePreset;
  intensity: Intensity | null;
  sfx: boolean;
  beat_sync: boolean;
  logo_bug: boolean;
  paid_partnership: { enabled: boolean; brand: string | null };
  ai_label: boolean;
  // Close pauses inside a scene's narration to about 0.3 s.
  tight_pauses?: boolean;
  // Reel series: "NAME . PART 2 OF 6" header with pips on every frame.
  series?: { enabled: boolean; name: string; part: number; total: number };
  progress_bar?: boolean;
}

// How the voice says a word written differently on screen (API -> A P I).
export interface Pronunciation {
  written: string;
  spoken: string;
}

export interface MGSpec {
  template_id: string;
  style_id: string;
  title: string;
  seed: number;
  scenes: SpecScene[];
  data: DataTable | null;
  data_options: DataOptions;
  source: string | null;
  disclaimer: string | null;
  options: SpecOptions;
  pronunciations?: Pronunciation[];
}

export interface ValidationIssue {
  scene_id?: string;
  slot?: string;
  message: string;
}

export interface DataView {
  ok: boolean;
  problems: string[];
  warnings: string[];
  format?: string;
  periods?: string[];
  entities?: string[];
  labels?: string[];
  series?: { name: string; values: (number | null)[] }[];
  items?: { name: string; value: number; change: number | null }[];
  metrics?: { label: string; a: number; b: number; higher_is_better: boolean }[];
  units?: { prefix: string; suffix: string };
  suggested_chart?: string;
}

export interface Validation {
  ok: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  data: DataView | null;
}

export interface PlanScene {
  id: string;
  type: string;
  start: number;
  duration: number;
  voiced: boolean;
}

export interface Plan {
  total: number;
  aspect: MGAspect;
  captions: boolean;
  scenes: PlanScene[];
  transitions: { into: string; type: string; seconds: number }[];
  beat_synced: boolean;
}

export interface Upload {
  id: string;
  kind: 'image' | 'audio';
  name: string;
  width: number | null;
  height: number | null;
  duration: number | null;
  created_at: string;
  ai_generated: boolean | null;
  url: string | null;
}

export interface AudioSettings {
  voice: {
    enabled: boolean;
    // elevenlabs (Eleven v4) or sarvam (Bulbul v4, Indian voices and languages)
    provider?: 'elevenlabs' | 'sarvam';
    voice_id: string;
    stability: number;
    similarity_boost: number;
    pace?: number; // Sarvam only
  };
  music: { enabled: boolean; mood: string };
}

export interface JobItem {
  id: string;
  kind: 'voice' | 'music' | 'image' | 'render';
  status: string;
  label: string;
  aspect: MGAspect | null;
  estimated_usd: number;
  error: string | null;
  video_id: number | null;
}

export interface Job {
  id: number;
  project_id: number;
  kind: JobKind;
  status: JobStatus;
  progress: number;
  quote: Quote;
  estimated_usd: number;
  cancel_requested: boolean;
  error: string | null;
  items: JobItem[];
  created_at: string;
  completed_at: string | null;
}

export interface Output {
  video_id: number;
  duration: number;
  width: number;
  height: number;
  url: string;
  download_url: string;
  thumbnail_url: string | null;
  stale: boolean;
  rendered_at: string;
}

export interface ComplianceItem {
  id: string;
  level: 'ok' | 'info' | 'error';
  title: string;
  detail: string;
}

export interface BrandSnapshot {
  name: string | null;
  palette: Record<string, string>;
  fonts: Record<string, string>;
  intensity: Intensity;
  use_brand_background: boolean;
  logo_url: string | null;
}

export interface ProjectSummary {
  id: number;
  title: string;
  template_id: string;
  style_id: string;
  aspect: MGAspect;
  variants: MGAspect[];
  status: 'draft' | 'producing' | 'rendered';
  spec_version: number;
  outputs: MGAspect[];
  thumbnail_url: string | null;
  usd_by_step: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface MGProject extends Omit<ProjectSummary, 'outputs'> {
  brief: string | null;
  spec: MGSpec;
  validation: Validation;
  brand: BrandSnapshot | null;
  audio: AudioSettings;
  uploads: Upload[];
  voice: { current: boolean; needed: boolean; duration: number | null; voice_id: string | null; url: string | null; chars: number };
  music: {
    current: boolean;
    duration: number | null;
    mood: string | null;
    url: string | null;
    beats: { bpm: number | null; reliable: boolean | null; confidence: number | null };
    rights: Record<string, unknown> | null;
  };
  plan: Plan | null;
  outputs: Partial<Record<MGAspect, Output>>;
  jobs: Job[];
  active_job: Job | null;
  compliance: ComplianceItem[];
}

export interface QuoteLine {
  label: string;
  key: string;
  unit: string;
  units: number;
  unit_usd: number;
  estimated_usd: number;
  aspect: MGAspect | null;
}

export interface Quote {
  kind: JobKind;
  estimated_usd: number;
  breakdown: QuoteLine[];
  notes: string[];
  seconds: number;
  warnings: string[];
}

export interface BrandKit {
  exists: boolean;
  name: string | null;
  palette: { primary?: string; secondary?: string; background?: string; text?: string };
  fonts: { display?: string; text?: string };
  intensity: Intensity;
  use_brand_background: boolean;
  auto_apply: boolean;
  logo_url: string | null;
}

export interface DraftRequest {
  brief: string;
  template_id?: string | null;
  style_id?: string | null;
  aspect?: MGAspect | null;
  length_seconds?: number | null;
  data_csv?: string | null;
  voiceover?: boolean;
}

export interface PreviewRequest {
  scene_id?: string | null;
  t?: number | null;
  at?: number | null;
  aspect?: MGAspect | null;
  scale?: number;
  safe_zone_overlay?: boolean;
  spec?: MGSpec | null;
}

const BASE = '/motion-graphics';
const multipart = { headers: { 'Content-Type': 'multipart/form-data' } };

function fileForm(file: File): FormData {
  const fd = new FormData();
  fd.append('file', file);
  return fd;
}

export function newIdempotencyKey(prefix = 'mg'): string {
  const rand =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${rand}`.slice(0, 80);
}

/** Machine readable error code of a Motion Graphics API error, if any. */
export function errorCode(err: unknown): string | undefined {
  const data = (err as { response?: { data?: { code?: string } } })?.response?.data;
  return data?.code;
}

export const motionGraphicsApi = {
  catalog: async (): Promise<MGCatalog> => (await apiClient.get(`${BASE}/catalog`)).data,
  voices: async (): Promise<{ voices: MGVoice[]; default: string }> => (await apiClient.get(`${BASE}/voices`)).data,
  templatePreview: async (
    templateId: string,
    params: { style?: string; aspect?: MGAspect; scene?: number; scale?: number },
  ): Promise<Blob> =>
    (await apiClient.get(`${BASE}/templates/${templateId}/preview.png`, { params, responseType: 'blob' })).data,

  brandKit: async (): Promise<BrandKit> => (await apiClient.get(`${BASE}/brand-kit`)).data,
  saveBrandKit: async (body: Partial<Omit<BrandKit, 'exists' | 'logo_url'>>): Promise<BrandKit> =>
    (await apiClient.put(`${BASE}/brand-kit`, body)).data,
  uploadLogo: async (file: File): Promise<BrandKit> =>
    (await apiClient.post(`${BASE}/brand-kit/logo`, fileForm(file), multipart)).data,
  deleteLogo: async (): Promise<BrandKit> => (await apiClient.delete(`${BASE}/brand-kit/logo`)).data,

  projects: async (page = 1, pageSize = 24) =>
    (await apiClient.get(`${BASE}/projects`, { params: { page, page_size: pageSize } })).data as {
      projects: ProjectSummary[];
      total: number;
    },
  createProject: async (body: {
    template_id: string;
    style_id?: string | null;
    aspect?: MGAspect | null;
    title?: string | null;
    apply_brand?: boolean;
    sample_content?: boolean;
  }): Promise<MGProject> => (await apiClient.post(`${BASE}/projects`, body)).data,
  createFromBrief: async (body: DraftRequest): Promise<MGProject> =>
    (await apiClient.post(`${BASE}/projects/draft`, body)).data,
  project: async (id: number): Promise<MGProject> => (await apiClient.get(`${BASE}/projects/${id}`)).data,
  updateProject: async (
    id: number,
    body: {
      title?: string;
      style_id?: string;
      aspect?: MGAspect;
      variants?: MGAspect[];
      audio?: { voice?: Partial<AudioSettings['voice']>; music?: Partial<AudioSettings['music']> };
      apply_brand?: boolean;
    },
  ): Promise<MGProject> => (await apiClient.put(`${BASE}/projects/${id}`, body)).data,
  deleteProject: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/projects/${id}`);
  },
  saveSpec: async (id: number, spec: MGSpec, expectedVersion?: number): Promise<MGProject> =>
    (await apiClient.put(`${BASE}/projects/${id}/spec`, { spec, expected_version: expectedVersion })).data,
  draft: async (id: number, body: DraftRequest): Promise<MGProject> =>
    (await apiClient.post(`${BASE}/projects/${id}/draft`, body)).data,
  preview: async (id: number, body: PreviewRequest): Promise<Blob> =>
    (await apiClient.post(`${BASE}/projects/${id}/preview`, body, { responseType: 'blob' })).data,
  // A silent animated WebP of one scene, or of the video's opening when no scene is given.
  motionPreview: async (
    id: number,
    body: { scene_id?: string | null; aspect?: MGAspect; spec?: MGSpec },
  ): Promise<Blob> =>
    (await apiClient.post(`${BASE}/projects/${id}/motion-preview`, body, { responseType: 'blob' })).data,
  parseData: async (csv: string, kind?: MGTemplate['data_kind']): Promise<{ table: DataTable; view: DataView }> =>
    (await apiClient.post(`${BASE}/data/parse`, { csv, kind: kind ?? undefined })).data,
  upload: async (id: number, file: File): Promise<Upload> =>
    (await apiClient.post(`${BASE}/projects/${id}/uploads`, fileForm(file), multipart)).data.upload,
  deleteUpload: async (id: number, uploadId: string): Promise<void> => {
    await apiClient.delete(`${BASE}/projects/${id}/uploads/${encodeURIComponent(uploadId)}`);
  },
  quote: async (id: number, kind: JobKind): Promise<Quote> =>
    (await apiClient.get(`${BASE}/projects/${id}/quote`, { params: { kind } })).data,
  startJob: async (id: number, kind: JobKind, idempotencyKey: string): Promise<Job> =>
    (await apiClient.post(`${BASE}/projects/${id}/jobs`, { kind, idempotency_key: idempotencyKey })).data,
  job: async (jobId: number): Promise<Job> => (await apiClient.get(`${BASE}/jobs/${jobId}`)).data,
  cancelJob: async (jobId: number): Promise<Job> => (await apiClient.post(`${BASE}/jobs/${jobId}/cancel`)).data,
};

export const ASPECT_LABEL: Record<MGAspect, string> = {
  '9:16': 'Vertical',
  '4:5': 'Portrait',
  '1:1': 'Square',
  '16:9': 'Landscape',
};

export const SAFE_ZONE_LABEL: Record<SafeZonePreset, string> = {
  organic: 'Organic feed',
  strict_ads: 'Ads (strict)',
  cover: 'Cover crop',
  none: 'None',
};
