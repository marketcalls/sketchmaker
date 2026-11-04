// Faceless Studio API (/api/faceless). The contract is the docstring of
// backend/app/routers/faceless.py, request bodies are
// backend/app/schemas/faceless.py, and responses are built by
// backend/app/services/faceless/views.py (Character, Series, Project),
// orchestrator.run_view (StepRun), pricing.quote_view (Quote) and the
// storyscript models (Template, Script, OriginalityReport, Packaging).
//
// Types keep the wire's snake_case names so a backend change shows up here
// as a type error instead of a silent undefined from a camelCase mapper.
import apiClient from './client';
import type { Quality } from './quality';

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type FacelessAspect = '9:16' | '16:9' | '1:1' | '4:5';
export const FACELESS_ASPECTS: FacelessAspect[] = ['9:16', '16:9', '1:1', '4:5'];

// catalog.MAX_LENGTH_SECONDS and MIN_LENGTH_SECONDS (also served by /config).
export const FACELESS_MAX_SECONDS: Record<FacelessAspect, number> = {
  '9:16': 180,
  '16:9': 900,
  '1:1': 180,
  '4:5': 180,
};
export const FACELESS_MIN_SECONDS = 15;
export const MAX_CAST = 6;

// catalog.STEPS: the paid steps the quote and run endpoints take.
export type PaidStep = 'storyboard' | 'clips' | 'voice' | 'music' | 'render' | 'thumbnails';

// What the editor rail shows; `animate` runs the `clips` step.
export type StudioStep =
  | 'script'
  | 'storyboard'
  | 'animate'
  | 'voice'
  | 'music'
  | 'captions'
  | 'render'
  | 'package';

export type ProjectStatus = 'draft' | 'scripted' | 'producing' | 'rendered';
export type RunStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';
export type RunItemStatus = 'pending' | 'submitted' | 'done' | 'failed' | 'cancelled';
export type ShotKind = 'still' | 'clip' | 'user_media' | 'card';
export type Camera =
  | 'pov'
  | 'handheld'
  | 'establishing'
  | 'close_up'
  | 'over_the_shoulder'
  | 'medium'
  | 'wide'
  | 'insert';
export type ShotMotion = 'none' | 'push_in' | 'pull_out' | 'pan_left' | 'pan_right';
export type Severity = 'block' | 'warn' | 'info';
export type ClipResolution = '480p' | '768p' | '1080p';
export type ClipMode = 'image' | 'reference';
export type StillResolution = '1k' | '2k';
export type RenderResolution = '1080p' | '720p';
export type CharacterKind = 'fictional' | 'real_person';
export type ConsentRelationship = 'self' | 'with_permission';
export type ConsentStatus = 'not_required' | 'missing' | 'outdated' | 'valid' | 'revoked';
export type SafeZone = 'shorts' | 'tiktok' | 'reels' | 'youtube';

// catalog.SAFE_ZONE: the platform zone the render keeps captions out of.
export const SAFE_ZONE_FOR_ASPECT: Record<FacelessAspect, SafeZone> = {
  '9:16': 'shorts',
  '16:9': 'youtube',
  '1:1': 'reels',
  '4:5': 'reels',
};

// ---------------------------------------------------------------------------
// Catalogues
// ---------------------------------------------------------------------------

// storyscript.Beat: start and end are fractions of the runtime.
export interface TemplateBeat {
  id: string;
  name: string;
  start: number;
  end: number;
  job: string;
  rehook: boolean;
  silence_after: number;
}

export interface TemplateVoiceStyle {
  wpm: number;
  stability: number;
  similarity_boost: number;
  description: string;
  suggested_voices: string[];
}

export interface TemplateMusicPlan {
  mood: string;
  positive_global_styles: string[];
  negative_global_styles: string[];
  force_instrumental: boolean;
  gain_db: number;
}

// storyscript.Template (fields the studio reads).
export interface FacelessTemplate {
  id: string;
  name: string;
  pitch: string;
  niche: string;
  kind: 'format' | 'viral';
  aspects: FacelessAspect[];
  default_aspect: FacelessAspect;
  length: { min_seconds: number; default_seconds: number; max_seconds: number };
  shorts: boolean;
  beats: TemplateBeat[];
  hook_formulas: string[];
  rehook_seconds: number[];
  ending: 'loop' | 'cliffhanger_vote' | 'payoff';
  ending_note: string;
  shots_per_minute: number;
  words_per_scene: number | null;
  dialogue_mode: 'narration' | 'dialogue' | 'mixed';
  visual_style: string;
  realistic: boolean;
  voice: TemplateVoiceStyle;
  music: TemplateMusicPlan;
  caption_preset: string;
  fact_mode: boolean;
  kids_safe: boolean;
  stat_cards: boolean;
  clip_share: number;
  policy_notes: string[];
  dramatization_label: string | null;
}

export interface VisualStyle {
  id: string;
  label: string;
  prompt: string;
}

export interface FacelessVoice {
  id: string;
  gender: string;
  accent: string;
  tone: string;
}

export interface MusicMood {
  id: string;
  label: string;
  positive: string[];
  negative: string[];
}

export interface CaptionStyle {
  id: string;
  label: string;
  description: string;
}

export interface ConsentText {
  version: string;
  text: string;
  relationships: ConsentRelationship[];
}

export interface FacelessConfig {
  aspects: FacelessAspect[];
  limits: {
    min_length_seconds: number;
    max_length_seconds: Record<FacelessAspect, number>;
    max_scenes: number;
    max_cast: number;
    max_character_media: number;
    image_upload_max_bytes: number;
    video_upload_max_bytes: number;
    character_video_max_seconds: number;
    scene_video_max_seconds: number;
    drafts_per_hour: number;
  };
  models: {
    t2i: string[];
    edit: string[];
    default_t2i: string;
    default_edit: string;
    still_resolutions: StillResolution[];
    clip_resolutions: ClipResolution[];
    default_clip_resolution: ClipResolution;
    clip_modes: ClipMode[];
    render_resolutions: RenderResolution[];
  };
  consent: ConsentText;
  // Estimated USD per unit, keyed like pricing.USD_COSTS (audio:eleven-v4:1k-chars...).
  prices: Record<string, number>;
  steps: PaidStep[];
  // House colour grade looks for the render step (app/render/grade.py).
  grade_looks?: GradeLook[];
}

export interface GradeLook {
  id: string;
  label: string;
  description: string;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface SafetyFlag {
  kind: 'real_person' | 'possible_minor' | 'public_figure' | 'copyrighted_character' | 'brand_logo' | 'sensitive_content';
  confidence: number;
  note: string;
}

export interface ComplianceFlag {
  code: string;
  severity: Severity;
  message: string;
  advice: string;
  scene_id: string | null;
  character_id: string | null;
  platform: 'youtube' | 'tiktok' | 'instagram' | 'all' | null;
}

export interface ComplianceReport {
  flags: ComplianceFlag[];
  blocked: boolean;
  checked_at: string | null;
  script_version: number | null;
  unavailable?: boolean;
}

export interface OriginalityMatch {
  title: string;
  index: number;
  similarity: number;
  features: Record<string, number>;
}

export interface OriginalityReport {
  score: number;
  verdict: 'original' | 'similar' | 'repetitive';
  same_situation_same_outcome: boolean;
  compared: number;
  closest: OriginalityMatch[];
  findings: string[];
  suggestions: string[];
  script_version: number | null;
  checked_at?: string | null;
  unavailable?: boolean;
}

// ---------------------------------------------------------------------------
// Characters
// ---------------------------------------------------------------------------

export interface CharacterBible {
  name: string;
  canonical_description: string;
  outfit: string;
  distinguishing_features: string[];
  likeness_clause: string;
  style_notes: string;
  age_range: string;
  species: string;
  safety_flags: SafetyFlag[];
  source: 'vision' | 'notes' | 'name_only';
  model: string | null;
}

export interface CharacterMedia {
  id: string;
  kind: 'image' | 'video';
  role: 'reference' | 'sheet' | 'source_video' | 'frame';
  url: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  source_id: string | null;
  usable_as_reference: boolean;
  created_at: string | null;
}

export interface CharacterConsent {
  status: ConsentStatus;
  attested_at: string | null;
  text_version: string | null;
  relationship: ConsentRelationship | null;
  revoked_at: string | null;
  current_version: string;
}

export interface VoiceSettings {
  stability: number;
  similarity_boost: number;
}

export interface FacelessCharacter {
  id: number;
  name: string;
  kind: CharacterKind;
  role: string | null;
  personality: string | null;
  notes: string | null;
  style_notes: string | null;
  species: string | null;
  catchphrase: string | null;
  consent: CharacterConsent;
  bible: CharacterBible | null;
  media: CharacterMedia[];
  voice_id: string | null;
  voice_settings: VoiceSettings | null;
  safety_flags: SafetyFlag[];
  can_generate: boolean;
  block_reason: string | null;
  is_archived: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConsentIn {
  accepted: boolean;
  text_version: string;
  relationship: ConsentRelationship;
}

export interface CharacterCreate {
  name: string;
  kind?: CharacterKind;
  role?: string | null;
  personality?: string | null;
  notes?: string | null;
  style_notes?: string | null;
  species?: string | null;
  catchphrase?: string | null;
  voice_id?: string | null;
  voice_settings?: VoiceSettings | null;
  consent?: ConsentIn | null;
}

export interface CharacterUpdate {
  name?: string;
  role?: string | null;
  personality?: string | null;
  notes?: string | null;
  style_notes?: string | null;
  species?: string | null;
  catchphrase?: string | null;
  voice_id?: string | null;
  voice_settings?: VoiceSettings | null;
  // Merged over the stored bible and validated as storyscript.CharacterBible.
  bible?: Partial<CharacterBible> | null;
  is_archived?: boolean;
  consent?: ConsentIn | null;
  revoke_consent?: boolean;
}

// ---------------------------------------------------------------------------
// Series
// ---------------------------------------------------------------------------

export interface EpisodeMemory {
  project_id: number;
  title: string;
  premise: string;
  outcome: string;
  situation: string | null;
}

export interface FacelessSeries {
  id: number;
  title: string;
  logline: string | null;
  template_id: string | null;
  style: string | null;
  tone: string | null;
  cast_ids: number[];
  world_notes: string | null;
  rules: string[];
  episode_memory: EpisodeMemory[];
  project_count: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SeriesDetail extends FacelessSeries {
  projects: ProjectSummary[];
}

export interface SeriesInput {
  title: string;
  logline?: string | null;
  template_id?: string | null;
  style?: string | null;
  tone?: string | null;
  cast_ids?: number[];
  world_notes?: string | null;
  rules?: string[];
}

// ---------------------------------------------------------------------------
// Script (storyscript.Script)
// ---------------------------------------------------------------------------

export interface DialogueLine {
  character_id: string;
  character: string;
  text: string;
  emotion: string | null;
}

export interface ShotPlan {
  kind: ShotKind;
  camera: Camera;
  characters: string[];
  direction: string;
  visual_prompt: string;
  images: number;
  clip_seconds: number | null;
  motion: ShotMotion;
}

export interface Stat {
  value: string;
  label: string;
  fact_id: string | null;
}

export interface SourceRef {
  fact_id: string;
  claim: string;
  source: string;
  date: string;
}

export interface Scene {
  id: string;
  index: number;
  beat: string;
  beat_name: string;
  start: number;
  duration: number;
  narration: string;
  narration_emotion: string | null;
  dialogue: DialogueLine[];
  shot: ShotPlan;
  on_screen_text: string | null;
  stat: Stat | null;
  sources: SourceRef[];
  questions: string[];
  is_hook: boolean;
  is_rehook: boolean;
  dramatization: boolean;
  silence_after: number;
  word_target: number;
  notes: string;
}

export interface Fact {
  id?: string;
  text: string;
  source: string;
  date: string;
}

export interface Script {
  template_id: string;
  title: string;
  logline: string;
  premise: string;
  language: string;
  aspect: FacelessAspect;
  length_seconds: number;
  estimated_seconds: number;
  wpm: number;
  word_budget: number;
  word_count: number;
  hook_formula: string;
  ending: string;
  ending_line: string;
  vote_prompt: string | null;
  outro_title: string;
  scenes: Scene[];
  cast_ids: string[];
  narrator_voice: string | null;
  fact_mode: boolean;
  facts: Fact[];
  needs_facts: boolean;
  dramatization_label: string | null;
  visual_style: string;
  caption_preset: string;
  warnings: string[];
  version: number;
  // Every other storyscript field round-trips untouched on save.
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Project
// ---------------------------------------------------------------------------

export interface ProjectSummary {
  id: number;
  title: string;
  template_id: string;
  series_id: number | null;
  aspect: FacelessAspect;
  length_seconds: number;
  status: ProjectStatus;
  script_version: number;
  scene_count: number;
  output_video_id: number | null;
  usd_by_step: Record<string, number>;
  // Card image: the chosen thumbnail, the render's thumbnail or the first still.
  thumbnail_url?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SceneStill {
  url: string | null;
  model: string | null;
  seed: number | null;
  width: number | null;
  height: number | null;
  created_at?: string | null;
  // The quality check quoted with the storyboard step (api/quality.ts)
  quality?: Quality | null;
}

export interface SceneClip {
  url: string | null;
  model: string | null;
  mode: ClipMode | null;
  resolution: ClipResolution | null;
  duration: number | null;
  created_at?: string | null;
  // The quality check of its first, middle and last frames
  quality?: Quality | null;
}

export interface WordTiming {
  text: string;
  start: number;
  end: number;
}

export interface SceneVoiceLine {
  index: number;
  speaker: string;
  character_id: string | null;
  voice: string;
  text: string;
  // The clip was generated from the line's current text and voice.
  current: boolean;
  url: string | null;
  duration: number | null;
  words: WordTiming[] | null;
  // Check of the stored take (pace, long pauses): a hint for the user, who
  // may voice the line again (priced as a normal line).
  warning?: string | null;
  wpm?: number | null;
}

export interface SceneAssets {
  scene_id: string;
  shot: ShotKind;
  start: number;
  duration: number;
  measured: boolean;
  stills: (SceneStill | null)[];
  clips: (SceneClip | null)[];
  user_media: { url: string | null; kind: 'image' | 'video'; duration: number | null; width: number | null; height: number | null } | null;
  voice: SceneVoiceLine[];
}

export interface MusicState {
  tracks: { url: string | null; duration: number | null; start: number | null }[];
  mood: string | null;
  instrumental: boolean | null;
  rights: Record<string, unknown> | null;
}

export interface RenderResult {
  video_id?: number | null;
  run_id?: number | null;
  url?: string | null;
  thumbnail_url?: string | null;
  duration?: number | null;
  width?: number | null;
  height?: number | null;
  resolution?: RenderResolution | null;
  captions?: string | null;
  rendered_at?: string | null;
  // The gallery video was deleted.
  deleted?: boolean;
}

export interface PackagingChapter {
  start: number;
  timestamp: string;
  title: string;
}

export interface PlatformDisclosure {
  platform: 'youtube' | 'tiktok' | 'instagram';
  required: boolean;
  label: string;
  reason: string;
}

export interface Packaging {
  titles: string[];
  description: string;
  first_line: string;
  sources_section: string | null;
  disclosure_line: string;
  tags: string[];
  hashtags: string[];
  chapters: PackagingChapter[];
  thumbnail_prompts: { prompt: string; text: string; characters: string[] }[];
  disclosure_advice: PlatformDisclosure[];
  script_version?: number;
  created_at?: string;
}

export interface ProjectThumbnail {
  index: number | null;
  image_id: number | null;
  text: string | null;
  url: string | null;
  raw_url: string | null;
}

export interface ProjectSettings {
  t2i_model?: string | null;
  edit_model?: string | null;
  still_resolution?: StillResolution | null;
  clip_resolution?: ClipResolution | null;
  clip_mode?: ClipMode | null;
  render_resolution?: RenderResolution | null;
  // Caption choices used by the render: the active word's color (#RRGGBB)
  // and where the caption block sits. Unset: the render defaults.
  caption_highlight?: string | null;
  caption_position?: CaptionPosition | null;
  // Packaging choices kept with the project.
  selected_thumbnail?: number | null;
  disclosure_checks?: string[] | null;
  // Ads: a My Assets logo drawn on the end card (0 removes it).
  ad_logo_asset_id?: number | null;
  // Colour grade of the render (backend services/faceless/grade.py): a house
  // look id from config.grade_looks, its strength 0 to 1, and colour matching
  // to the approved environment plates a Story Room hand-off recorded.
  grade_look?: string | null;
  grade_strength?: number | null;
  grade_match?: boolean | null;
  grade_plates?: Record<string, unknown> | null;
}

export type CaptionPosition = 'lower' | 'middle' | 'upper';

export interface RunItem {
  id: string;
  kind: string;
  scene_id: string | null;
  index: number | null;
  status: RunItemStatus;
  usd: number | null;
  error: string | null;
  // Error code of a failed item (a queued script draft carries it here).
  code?: string | null;
  // The item's quality check, when one ran.
  qa?: Quality | null;
  qa_verdict?: string | null;
}

export interface StepRun {
  id: number;
  project_id: number | null;
  character_id: number | null;
  step: PaidStep | 'sheet' | 'script';
  status: RunStatus;
  progress: number;
  scene_ids: string[];
  options: Record<string, unknown>;
  quote: Partial<Quote>;
  // The quote total when the run started, and what has landed so far.
  estimated_usd: number;
  usd_spent: number;
  cancel_requested: boolean;
  error: string | null;
  items: RunItem[];
  idempotency_key: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface FacelessProject extends ProjectSummary {
  idea: string | null;
  language: string;
  style: string | null;
  narrator_voice: string;
  voice_settings: VoiceSettings;
  caption_preset: string | null;
  music_mood: string | null;
  cast_ids: number[];
  facts: Fact[];
  settings: ProjectSettings;
  // Mirrors of settings.selected_thumbnail and settings.disclosure_checks.
  selected_thumbnail?: number | null;
  disclosure_checks?: string[];
  script: Script | null;
  scenes: SceneAssets[];
  total_seconds: number;
  timing_measured: boolean;
  music: MusicState | null;
  render: RenderResult | null;
  packaging: Packaging | null;
  thumbnails: ProjectThumbnail[];
  compliance: ComplianceReport | null;
  originality: OriginalityReport | null;
  active_runs: StepRun[];
}

export interface ProjectCreate {
  title?: string | null;
  idea?: string | null;
  template_id: string;
  series_id?: number | null;
  aspect?: FacelessAspect;
  length_seconds?: number;
  language: string;
  style?: string | null;
  narrator_voice?: string | null;
  voice_settings?: VoiceSettings | null;
  caption_preset?: string | null;
  music_mood?: string | null;
  cast_ids: number[];
  facts: { text: string; source: string; date: string }[];
  settings?: ProjectSettings | null;
}

export type ProjectUpdate = Partial<Omit<ProjectCreate, 'template_id'>> & { template_id?: string };

// ---------------------------------------------------------------------------
// Quotes and steps
// ---------------------------------------------------------------------------

export interface QuoteLine {
  label: string;
  key: string;
  unit: string;
  units: number;
  unit_usd: number;
  usd: number;
  count: number;
}

export interface Quote {
  step: PaidStep | 'sheet';
  usd: number;
  breakdown: QuoteLine[];
  assumptions: string[];
  scene_ids: string[];
  characters: number[];
}

// Step options per the router docstring; all optional.
export interface StepOptions {
  t2i_model?: string;
  edit_model?: string;
  resolution?: string;
  regenerate?: boolean;
  mode?: ClipMode;
  max_clips_per_scene?: number;
  mood?: string;
  instrumental?: boolean;
  captions?: string;
  music?: boolean;
  music_gain_db?: number;
  texts?: string[];
  // Voice step: only these line indexes of the given scene.
  lines?: number[];
  // Storyboard and clips: false skips the paid quality check of each result.
  quality_check?: boolean;
}

export interface StepRunRequest {
  scene_ids?: string[];
  options?: StepOptions;
  idempotency_key?: string;
  // The total of the quote the user confirmed: the server refuses with 409
  // quote_changed (and the new quote) when the fresh price differs.
  expected_usd?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE = '/faceless';
const multipart = { headers: { 'Content-Type': 'multipart/form-data' } };

function fileForm(file: File): FormData {
  const fd = new FormData();
  fd.append('file', file);
  return fd;
}

// A fresh key per confirmed action: a retried request never runs twice.
export function newIdempotencyKey(prefix: string): string {
  const rand =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${rand}`.slice(0, 80);
}

function optionsParam(options?: StepOptions): string | undefined {
  return options && Object.keys(options).length > 0 ? JSON.stringify(options) : undefined;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const facelessApi = {
  // Catalogues
  templates: async (): Promise<{ templates: FacelessTemplate[]; styles: VisualStyle[] }> =>
    (await apiClient.get(`${BASE}/templates`)).data,
  voices: async (): Promise<{ voices: FacelessVoice[]; default_narrator: string }> =>
    (await apiClient.get(`${BASE}/voices`)).data,
  musicMoods: async (): Promise<MusicMood[]> => (await apiClient.get(`${BASE}/music-moods`)).data.moods ?? [],
  captionStyles: async (): Promise<CaptionStyle[]> =>
    (await apiClient.get(`${BASE}/caption-styles`)).data.styles ?? [],
  config: async (): Promise<FacelessConfig> => (await apiClient.get(`${BASE}/config`)).data,

  // Characters
  characters: async (includeArchived = true): Promise<FacelessCharacter[]> =>
    (await apiClient.get(`${BASE}/characters`, { params: { include_archived: includeArchived } })).data.characters ?? [],
  character: async (id: number): Promise<FacelessCharacter> => (await apiClient.get(`${BASE}/characters/${id}`)).data,
  createCharacter: async (body: CharacterCreate): Promise<FacelessCharacter> =>
    (await apiClient.post(`${BASE}/characters`, body)).data,
  updateCharacter: async (id: number, body: CharacterUpdate): Promise<FacelessCharacter> =>
    (await apiClient.put(`${BASE}/characters/${id}`, body)).data,
  deleteCharacter: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/characters/${id}`);
  },
  attestConsent: async (id: number, body: ConsentIn): Promise<FacelessCharacter> =>
    (await apiClient.post(`${BASE}/characters/${id}/consent`, body)).data,
  revokeConsent: async (id: number): Promise<FacelessCharacter> =>
    (await apiClient.post(`${BASE}/characters/${id}/consent/revoke`)).data,
  uploadCharacterMedia: async (id: number, file: File): Promise<FacelessCharacter> =>
    (await apiClient.post(`${BASE}/characters/${id}/media`, fileForm(file), multipart)).data,
  deleteCharacterMedia: async (id: number, mediaId: string): Promise<FacelessCharacter> =>
    (await apiClient.delete(`${BASE}/characters/${id}/media/${encodeURIComponent(mediaId)}`)).data,
  // 20 per hour. Returns the character with bible and flags.
  characterBible: async (id: number): Promise<FacelessCharacter> =>
    (await apiClient.post(`${BASE}/characters/${id}/bible`)).data,
  characterSheetQuote: async (id: number): Promise<Quote> =>
    (await apiClient.get(`${BASE}/characters/${id}/sheet/quote`)).data,
  characterSheet: async (id: number, idempotencyKey: string, expectedUsd?: number): Promise<StepRun> =>
    (
      await apiClient.post(`${BASE}/characters/${id}/sheet`, {
        idempotency_key: idempotencyKey,
        expected_usd: expectedUsd,
      })
    ).data,

  // Series
  series: async (): Promise<FacelessSeries[]> => (await apiClient.get(`${BASE}/series`)).data.series ?? [],
  seriesOne: async (id: number): Promise<SeriesDetail> => (await apiClient.get(`${BASE}/series/${id}`)).data,
  createSeries: async (body: SeriesInput): Promise<FacelessSeries> =>
    (await apiClient.post(`${BASE}/series`, body)).data,
  updateSeries: async (id: number, body: Partial<SeriesInput>): Promise<FacelessSeries> =>
    (await apiClient.put(`${BASE}/series/${id}`, body)).data,
  deleteSeries: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/series/${id}`);
  },

  // Projects
  projects: async (params?: { series_id?: number; page?: number; page_size?: number }) =>
    (await apiClient.get(`${BASE}/projects`, { params })).data as {
      projects: ProjectSummary[];
      total: number;
      page: number;
      page_size: number;
    },
  project: async (id: number): Promise<FacelessProject> => (await apiClient.get(`${BASE}/projects/${id}`)).data,
  createProject: async (body: ProjectCreate): Promise<FacelessProject> =>
    (await apiClient.post(`${BASE}/projects`, body)).data,
  updateProject: async (id: number, body: ProjectUpdate): Promise<FacelessProject> =>
    (await apiClient.put(`${BASE}/projects/${id}`, body)).data,
  deleteProject: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/projects/${id}`);
  },

  // Script
  // Short formats draft inline (200, Project). Long-form projects, or
  // background: true, are queued (202, StepRun with step "script"): the
  // run shows in active_runs and the project gains the script when it ends.
  draftScript: async (
    id: number,
    body: { idea?: string; background?: boolean; idempotency_key?: string } = {},
  ): Promise<FacelessProject | StepRun> => (await apiClient.post(`${BASE}/projects/${id}/script`, body)).data,
  saveScript: async (id: number, script: Script): Promise<FacelessProject> =>
    (await apiClient.put(`${BASE}/projects/${id}/script`, { script })).data,
  scriptVersions: async (id: number) =>
    (await apiClient.get(`${BASE}/projects/${id}/script/versions`)).data as {
      versions: { version: number; source: string; created_at: string; title: string | null }[];
      current: number;
    },
  restoreVersion: async (id: number, version: number): Promise<FacelessProject> =>
    (await apiClient.post(`${BASE}/projects/${id}/script/versions/${version}/restore`)).data,
  reviseScene: async (id: number, sceneId: string, instruction: string): Promise<FacelessProject> =>
    (await apiClient.post(`${BASE}/projects/${id}/scenes/${encodeURIComponent(sceneId)}/revise`, { instruction })).data,
  uploadSceneMedia: async (id: number, sceneId: string, file: File): Promise<FacelessProject> =>
    (await apiClient.post(`${BASE}/projects/${id}/scenes/${encodeURIComponent(sceneId)}/media`, fileForm(file), multipart)).data,
  deleteSceneMedia: async (id: number, sceneId: string): Promise<FacelessProject> =>
    (await apiClient.delete(`${BASE}/projects/${id}/scenes/${encodeURIComponent(sceneId)}/media`)).data,
  originality: async (id: number, refresh = false): Promise<OriginalityReport> =>
    (await apiClient.get(`${BASE}/projects/${id}/originality`, { params: refresh ? { refresh: true } : undefined })).data,
  compliance: async (id: number, refresh = false): Promise<ComplianceReport> =>
    (await apiClient.get(`${BASE}/projects/${id}/compliance`, { params: refresh ? { refresh: true } : undefined })).data,

  // Paid steps
  quote: async (id: number, step: PaidStep, sceneIds?: string[], options?: StepOptions): Promise<Quote> =>
    (
      await apiClient.get(`${BASE}/projects/${id}/quote`, {
        params: {
          step,
          scene_ids: sceneIds && sceneIds.length > 0 ? sceneIds.join(',') : undefined,
          options: optionsParam(options),
        },
      })
    ).data,
  runStep: async (id: number, step: PaidStep, body: StepRunRequest): Promise<StepRun> =>
    (await apiClient.post(`${BASE}/projects/${id}/steps/${step}`, body)).data,
  runs: async (id: number, limit = 30): Promise<StepRun[]> =>
    (await apiClient.get(`${BASE}/projects/${id}/runs`, { params: { limit } })).data.runs ?? [],
  run: async (runId: number): Promise<StepRun> => (await apiClient.get(`${BASE}/runs/${runId}`)).data,
  cancelRun: async (runId: number): Promise<StepRun> => (await apiClient.post(`${BASE}/runs/${runId}/cancel`)).data,

  // Packaging metadata (10 per hour). Thumbnails run as the paid step.
  pack: async (id: number): Promise<{ packaging: Packaging; run: StepRun | null }> =>
    (await apiClient.post(`${BASE}/projects/${id}/package`, { thumbnails: false })).data,
};

// ---------------------------------------------------------------------------
// Shared constants and helpers
// ---------------------------------------------------------------------------

export const FACELESS_LANGUAGES: { code: string; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Spanish' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'it', label: 'Italian' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ta', label: 'Tamil' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'ar', label: 'Arabic' },
  { code: 'id', label: 'Indonesian' },
];

export const CAMERAS: { value: Camera; label: string }[] = [
  { value: 'pov', label: 'POV' },
  { value: 'handheld', label: 'Handheld' },
  { value: 'establishing', label: 'Establishing' },
  { value: 'close_up', label: 'Close up' },
  { value: 'over_the_shoulder', label: 'Over the shoulder' },
  { value: 'medium', label: 'Medium' },
  { value: 'wide', label: 'Wide' },
  { value: 'insert', label: 'Insert' },
];

export const SHOT_KINDS: { value: ShotKind; label: string; hint: string }[] = [
  { value: 'still', label: 'Still', hint: 'A storyboard still with a slow Ken Burns move' },
  { value: 'clip', label: 'Animate', hint: 'An H3 Max video clip, made from the still or the cast references' },
  { value: 'card', label: 'Card', hint: 'A text card, no picture needed' },
  { value: 'user_media', label: 'My media', hint: 'Your own image or video' },
];

// Eleven v4 audio tags the script engine uses for emotion.
export const EMOTIONS = [
  'calm', 'excited', 'whispering', 'sad', 'angry', 'curious', 'sarcastic', 'laughing', 'nervous', 'serious',
];

// Studio rail order, with the paid step each one runs (if any).
export const STUDIO_STEPS: { id: StudioStep; label: string; paid: PaidStep | null }[] = [
  { id: 'script', label: 'Script', paid: null },
  { id: 'storyboard', label: 'Storyboard', paid: 'storyboard' },
  { id: 'animate', label: 'Animate', paid: 'clips' },
  { id: 'voice', label: 'Voice', paid: 'voice' },
  { id: 'music', label: 'Music', paid: 'music' },
  { id: 'captions', label: 'Captions', paid: null },
  { id: 'render', label: 'Render', paid: 'render' },
  { id: 'package', label: 'Package', paid: 'thumbnails' },
];

export const PAID_TO_STUDIO: Record<PaidStep, StudioStep> = {
  storyboard: 'storyboard',
  clips: 'animate',
  voice: 'voice',
  music: 'music',
  render: 'render',
  thumbnails: 'package',
};

// About 165 words a minute before voices exist (catalog.ESTIMATE_WPM).
export const ESTIMATE_WPM = 165;

export function countWords(text: string | null | undefined): number {
  const t = (text ?? '').replace(/\[[^\]]*\]/g, ' ').trim();
  return t ? t.split(/\s+/).length : 0;
}

export function sceneWords(scene: Pick<Scene, 'narration' | 'dialogue'>): number {
  return countWords(scene.narration) + scene.dialogue.reduce((n, d) => n + countWords(d.text), 0);
}

export function scriptWords(script: Script | null): number {
  return (script?.scenes ?? []).reduce((n, s) => n + sceneWords(s), 0);
}

export function estimateSeconds(words: number, wpm = ESTIMATE_WPM): number {
  return words <= 0 ? 0 : (words / wpm) * 60;
}

export function isStepRun(value: FacelessProject | StepRun): value is StepRun {
  return 'items' in value && 'step' in value && !('script_version' in value);
}

export function isRunActive(run: Pick<StepRun, 'status'>): boolean {
  return run.status === 'queued' || run.status === 'running';
}
