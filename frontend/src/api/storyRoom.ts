import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';
import apiClient from './client';
import { friendlyError, getErrorMessage } from '@/utils/errors';

/**
 * Story Room client (/api/story-room). The contract is docs/STORY_ROOM.md.
 *
 * Envelopes (threads, messages, config, environments) are mapped to camelCase
 * like api/assets.ts. The story document itself keeps the wire's snake_case
 * names (as api/faceless.ts does): it is sent back whole on every save, so it
 * must round-trip without a mapper silently dropping a field the server added.
 */

/* ------------------------------------------------------------------------ */
/* StoryDoc (app/services/story_room/models.py)                              */
/* ------------------------------------------------------------------------ */

export type StoryFormat = 'story' | 'ad';
export type StoryAspect = '9:16' | '16:9' | '1:1';

export type ShotType =
  | 'establishing' | 'wide' | 'medium' | 'close_up' | 'extreme_close_up' | 'insert'
  | 'over_the_shoulder' | 'pov' | 'two_shot' | 'aerial' | 'tracking' | 'cutaway';

export type ShotCamera =
  | 'static' | 'pan' | 'tilt' | 'dolly_in' | 'dolly_out' | 'tracking' | 'handheld'
  | 'crane' | 'orbit' | 'whip_pan' | 'zoom' | 'rack_focus';

export type ShotTransition =
  | 'cut' | 'jump_cut' | 'match_cut' | 'smash_cut' | 'cross_cut' | 'dissolve'
  | 'whip_pan' | 'j_cut' | 'l_cut' | 'fade_in' | 'fade_out';

export type StoryRegister = 'cinematic' | 'ugc' | 'documentary' | 'animated';
export type AdObjective = 'awareness' | 'consideration' | 'conversion';

export interface AdBrief {
  product: string;
  brand: string;
  offer: string;
  key_message: string;
  cta: string;
  mandatories: string[];
  objective: AdObjective;
  // The viewer as a person with a current mindset, not a demographic.
  audience_mindset: string;
  // The single reason to buy, in one sentence.
  proposition: string;
  // on-code, twist or wild.
  creativity: string;
  // Up to three alternate opening shots for the hook.
  hook_variants: string[];
}

export interface Look {
  visual_style: string;
  palette: string;
  lighting: string;
  camera_feel: string;
  music: string;
  register: StoryRegister;
}

// A real product shown in the piece. Its picture is only ever an uploaded
// photo, set by the server; a product never gets a generated image.
export interface Product {
  key: string;
  name: string;
  description: string;
  // Label text, colours and shape notes that must never drift.
  must_keep: string[];
  image_url: string;
  image_approved: boolean;
}

export interface CastEntry {
  key: string;
  ref_id: number | null;
  name: string;
  role: string;
  description: string;
  wardrobe: string;
  voice_notes: string;
  // Director-written prompt for the reference image (editable).
  image_prompt: string;
  // Set only by the server, from an approved gallery image or My Assets image.
  image_url: string | null;
  image_approved: boolean;
}

export interface EnvEntry {
  key: string;
  ref_id: number | null;
  name: string;
  description: string;
  time_of_day: string;
  mood: string;
  image_prompt: string;
  image_url: string | null;
  image_approved: boolean;
}

export interface DialogueLine {
  character_key: string;
  line: string;
  delivery: string;
}

export interface Shot {
  id: string;
  type: ShotType;
  b_roll: boolean;
  camera: ShotCamera;
  duration_seconds: number;
  transition_in: ShotTransition;
  action: string;
  characters: string[];
  dialogue: DialogueLine[];
  voiceover: string;
  on_screen_text: string;
  sound: string;
  // Product keys in frame.
  props: string[];
  // Who is where and which way they face.
  frame_position: string;
  // The pose or state the shot ends in; the next shot begins from it.
  end_state: string;
  // Set only by the server: the shot's first frame. A keyframe from "Make
  // keyframe" waits here unapproved until the user approves it.
  keyframe_url: string;
  keyframe_approved: boolean;
}

export interface DocScene {
  id: string;
  heading: string;
  environment_key: string | null;
  purpose: string;
  summary: string;
  shots: Shot[];
}

export interface StoryDoc {
  format: StoryFormat;
  title: string;
  logline: string;
  synopsis: string;
  genre: string;
  tone: string;
  audience: string;
  language: string;
  aspect: StoryAspect;
  target_seconds: number;
  ad: AdBrief | null;
  look: Look;
  characters: CastEntry[];
  environments: EnvEntry[];
  products: Product[];
  scenes: DocScene[];
  // Assumptions the director made and what it still needs from the user,
  // then the app's plan checks (they start with PLAN_CHECK_PREFIX).
  open_questions: string[];
  // The full production prompt, regenerated on every turn (plain text with
  // headed sections: Setting, Scene N (a-b seconds), Visual direction...).
  treatment: string;
}

// Fallbacks while /config loads; the server's lists win.
export const SHOT_TYPES: ShotType[] = [
  'establishing', 'wide', 'medium', 'close_up', 'extreme_close_up', 'insert',
  'over_the_shoulder', 'pov', 'two_shot', 'aerial', 'tracking', 'cutaway',
];
export const SHOT_CAMERAS: ShotCamera[] = [
  'static', 'pan', 'tilt', 'dolly_in', 'dolly_out', 'tracking', 'handheld',
  'crane', 'orbit', 'whip_pan', 'zoom', 'rack_focus',
];
export const SHOT_TRANSITIONS: ShotTransition[] = [
  'cut', 'jump_cut', 'match_cut', 'smash_cut', 'cross_cut', 'dissolve',
  'whip_pan', 'j_cut', 'l_cut', 'fade_in', 'fade_out',
];
export const STORY_ASPECTS: StoryAspect[] = ['9:16', '16:9', '1:1'];
export const STORY_REGISTERS: StoryRegister[] = ['cinematic', 'ugc', 'documentary', 'animated'];
export const AD_OBJECTIVES: AdObjective[] = ['awareness', 'consideration', 'conversion'];
export const MAX_PRODUCTS = 4;
// "Make keyframe" (app/services/story_room/keyframe.py); /config reports both.
export const KEYFRAME_MODEL = 'google/nano-banana-2.1/edit';
export const KEYFRAME_RESOLUTION = '1K';
export const MAX_HOOK_VARIANTS = 3;
// Open questions that start with this are the app's own plan checks
// (app/services/story_room/lint.py), refreshed after every reply and edit.
export const PLAN_CHECK_PREFIX = 'Plan check: ';
export const TARGET_SECONDS_MIN = 5;
export const TARGET_SECONDS_MAX = 600;
export const SHOT_SECONDS_MIN = 1;
export const SHOT_SECONDS_MAX = 15;

// Readable label for an enum value: "close_up" -> "Close up", "pov" -> "POV".
const UPPER = new Set(['pov', 'cta', 'ugc']);
export function enumLabel(value: string): string {
  if (UPPER.has(value)) return value.toUpperCase();
  const words = value.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const emptyAdBrief = (): AdBrief => ({
  product: '', brand: '', offer: '', key_message: '', cta: '', mandatories: [],
  objective: 'consideration', audience_mindset: '', proposition: '', creativity: '', hook_variants: [],
});

export const newProduct = (key: string): Product => ({
  key, name: '', description: '', must_keep: [], image_url: '', image_approved: false,
});

export function newShot(id: string): Shot {
  return {
    id,
    type: 'medium',
    b_roll: false,
    camera: 'static',
    duration_seconds: 3,
    transition_in: 'cut',
    action: '',
    characters: [],
    dialogue: [],
    voiceover: '',
    on_screen_text: '',
    sound: '',
    props: [],
    frame_position: '',
    end_state: '',
    keyframe_url: '',
    keyframe_approved: false,
  };
}

export const storyRuntime = (doc: StoryDoc | null | undefined): number =>
  (doc?.scenes ?? []).reduce((sum, sc) => sum + sc.shots.reduce((s, sh) => s + (Number(sh.duration_seconds) || 0), 0), 0);

export const shotCount = (doc: StoryDoc | null | undefined): number =>
  (doc?.scenes ?? []).reduce((n, sc) => n + sc.shots.length, 0);

// "45s", "1:05" for metadata.
export function formatRuntime(seconds: number): string {
  const s = Math.round(seconds * 10) / 10;
  if (s < 60) return `${Number.isInteger(s) ? s : s.toFixed(1)}s`;
  const whole = Math.round(s);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

/* ------------------------------------------------------------------------ */
/* Envelopes                                                                 */
/* ------------------------------------------------------------------------ */

export interface StoryRoomConfig {
  pricePerTurn: number;
  // "Make keyframe": the edit model and its price for one keyframe.
  keyframe: { price: number | null; model: string; resolution: string };
  limits: {
    maxThreads: number;
    maxMessages: number;
    maxMessageChars: number;
    maxScenes: number;
    maxShots: number;
    maxProducts: number;
  };
  enums: {
    shotTypes: ShotType[];
    cameras: ShotCamera[];
    transitions: ShotTransition[];
    registers: StoryRegister[];
    objectives: AdObjective[];
  };
}

export interface ThreadSummary {
  id: number;
  title: string;
  format: StoryFormat;
  updatedAt: string;
  scenes: number;
  shots: number;
  busy: boolean;
}

export interface StoryMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  // The document version this reply produced (assistant replies only).
  storyVersion: number | null;
  estimatedUsd: number;
  createdAt: string;
}

export interface StoryThread {
  id: number;
  title: string;
  format: StoryFormat;
  story: StoryDoc;
  storyVersion: number;
  busy: boolean;
  turnsUsed: number;
  estimatedUsd: number;
  messages: StoryMessage[];
}

export interface TurnResult {
  userMessage: StoryMessage;
  assistantMessage: StoryMessage;
  story: StoryDoc;
  storyVersion: number;
  estimatedUsd: number;
  // The thread's title after the turn (the director names an untitled story).
  title: string;
}

// Events of a streamed turn before its result.
export interface TurnStreamHandlers {
  // Reply text as it is written.
  onDelta?: (text: string) => void;
  // The reply is complete and the document is being written.
  onStatus?: (text: string) => void;
  // The reply to show instead of what was streamed (the server asked again).
  onReplace?: (text: string) => void;
}

export interface StoryVersioned {
  story: StoryDoc;
  // Left out by a reply that does not report it; the caller reloads then.
  storyVersion: number | null;
}

export interface EnvironmentMedia {
  url: string;
  key: string;
  contentType: string | null;
  width: number | null;
  height: number | null;
}

export interface StoryEnvironment {
  id: number;
  name: string;
  description: string;
  timeOfDay: string;
  mood: string;
  styleNotes: string;
  media: EnvironmentMedia[];
  isArchived: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface EnvironmentInput {
  name?: string;
  description?: string;
  timeOfDay?: string;
  mood?: string;
  styleNotes?: string;
  isArchived?: boolean;
}

export interface KeyframeResult extends StoryVersioned {
  estimatedUsd: number;
  // The new image in My Assets.
  assetId: number | null;
}

export interface ClipReference {
  url: string;
  label: string;
}

export interface ShotClip {
  prompt: string;
  references: ClipReference[];
  // The image the clip opens on (image-to-video): the shot's approved
  // keyframe, or the product photo of a hero product shot. References are
  // empty then, and the prompt animates from this frame.
  startFrame: ClipReference | null;
  durationSeconds: number;
  aspect: string;
}

type Raw = Record<string, unknown>;

const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback);
const num = (v: unknown, fallback = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : fallback);
const numOrNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function transformConfig(data: Raw): StoryRoomConfig {
  const limits = (data.limits ?? {}) as Raw;
  const enums = (data.enums ?? {}) as Raw;
  const list = <T,>(v: unknown, fallback: T[]): T[] => (Array.isArray(v) && v.length > 0 ? (v as T[]) : fallback);
  const keyframe = (data.keyframe ?? {}) as Raw;
  return {
    pricePerTurn: num(data.price_per_turn),
    keyframe: {
      price: numOrNull(keyframe.price),
      model: str(keyframe.model, KEYFRAME_MODEL),
      resolution: str(keyframe.resolution, KEYFRAME_RESOLUTION),
    },
    limits: {
      maxThreads: num(limits.max_threads, 200),
      maxMessages: num(limits.max_messages, 200),
      maxMessageChars: num(limits.max_message_chars, 4000),
      maxScenes: num(limits.max_scenes, 30),
      maxShots: num(limits.max_shots, 12),
      maxProducts: num(limits.max_products, MAX_PRODUCTS),
    },
    enums: {
      shotTypes: list(enums.shot_types, SHOT_TYPES),
      cameras: list(enums.cameras, SHOT_CAMERAS),
      transitions: list(enums.transitions, SHOT_TRANSITIONS),
      registers: list(enums.registers, STORY_REGISTERS),
      objectives: list(enums.objectives, AD_OBJECTIVES),
    },
  };
}

export function transformThreadSummary(data: Raw): ThreadSummary {
  return {
    id: data.id as number,
    title: str(data.title),
    format: data.format === 'ad' ? 'ad' : 'story',
    updatedAt: str(data.updated_at),
    scenes: num(data.scenes),
    shots: num(data.shots),
    busy: !!data.busy,
  };
}

export function transformMessage(data: Raw): StoryMessage {
  return {
    id: data.id as number,
    role: data.role === 'user' ? 'user' : 'assistant',
    content: str(data.content),
    storyVersion: numOrNull(data.story_version),
    estimatedUsd: num(data.estimated_usd),
    createdAt: str(data.created_at),
  };
}

export function transformThread(data: Raw): StoryThread {
  return {
    id: data.id as number,
    title: str(data.title),
    format: data.format === 'ad' ? 'ad' : 'story',
    story: data.story as StoryDoc,
    storyVersion: num(data.story_version),
    busy: !!data.busy,
    turnsUsed: num(data.turns_used),
    estimatedUsd: num(data.estimated_usd),
    messages: ((data.messages as Raw[] | undefined) ?? []).map(transformMessage),
  };
}

function transformTurn(data: Raw): TurnResult {
  return {
    userMessage: transformMessage(data.user_message as Raw),
    assistantMessage: transformMessage(data.assistant_message as Raw),
    story: data.story as StoryDoc,
    storyVersion: num(data.story_version),
    estimatedUsd: num(data.estimated_usd),
    title: str(data.title),
  };
}

function transformClip(data: Raw): ShotClip {
  const start = (data.start_frame ?? null) as Raw | null;
  return {
    prompt: str(data.prompt),
    references: ((data.references as Raw[] | undefined) ?? [])
      .map((r) => ({ url: str(r.url), label: str(r.label) }))
      .filter((r) => r.url),
    startFrame: start && str(start.url) ? { url: str(start.url), label: str(start.label) } : null,
    durationSeconds: num(data.duration_seconds, 5),
    aspect: str(data.aspect, '9:16'),
  };
}

function transformVersioned(data: Raw): StoryVersioned {
  return { story: data.story as StoryDoc, storyVersion: numOrNull(data.story_version) };
}

export function transformEnvironment(data: Raw): StoryEnvironment {
  return {
    id: data.id as number,
    name: str(data.name),
    description: str(data.description),
    timeOfDay: str(data.time_of_day),
    mood: str(data.mood),
    styleNotes: str(data.style_notes),
    media: ((data.media as Raw[] | undefined) ?? []).map((m) => ({
      url: str(m.url),
      key: str(m.key),
      contentType: (m.content_type as string | null) ?? null,
      width: numOrNull(m.width),
      height: numOrNull(m.height),
    })),
    isArchived: !!data.is_archived,
    createdAt: (data.created_at as string | null) ?? null,
    updatedAt: (data.updated_at as string | null) ?? null,
  };
}

function environmentBody(input: EnvironmentInput): Raw {
  const body: Raw = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.description !== undefined) body.description = input.description;
  if (input.timeOfDay !== undefined) body.time_of_day = input.timeOfDay;
  if (input.mood !== undefined) body.mood = input.mood;
  if (input.styleNotes !== undefined) body.style_notes = input.styleNotes;
  if (input.isArchived !== undefined) body.is_archived = input.isArchived;
  return body;
}

/* ------------------------------------------------------------------------ */
/* Errors                                                                    */
/* ------------------------------------------------------------------------ */

/**
 * A streamed turn that failed. `message` is written for people; `status` is
 * the HTTP status (or the one the error event carried). `lost` means the
 * stream broke after the server accepted the turn, which keeps running there.
 */
export class StoryTurnError extends Error {
  status: number | undefined;
  lost: boolean;

  constructor(message: string, status?: number, lost = false) {
    super(message);
    this.name = 'StoryTurnError';
    this.status = status;
    this.lost = lost;
  }
}

export function errorStatus(err: unknown): number | undefined {
  if (err instanceof StoryTurnError) return err.status;
  return axios.isAxiosError(err) ? err.response?.status : undefined;
}

// 524 is Cloudflare's "the origin did not answer in 100 seconds".
const GATEWAY_TIMEOUTS = new Set([502, 504, 524]);

/**
 * The proxy gave up before the server answered, or the stream broke after the
 * turn started. A chat turn keeps running on the server (the thread stays busy
 * until it finishes), so the caller reloads the thread instead of sending again.
 */
export function isGatewayTimeout(err: unknown): boolean {
  if (err instanceof StoryTurnError) return err.lost || (err.status !== undefined && GATEWAY_TIMEOUTS.has(err.status));
  if (!axios.isAxiosError(err)) return false;
  if (err.code === 'ERR_CANCELED') return false;
  const status = err.response?.status;
  return (status !== undefined && GATEWAY_TIMEOUTS.has(status)) || (!err.response && !!err.request);
}

export const isAbort = (err: unknown): boolean =>
  (err instanceof DOMException && err.name === 'AbortError') || (axios.isAxiosError(err) && err.code === 'ERR_CANCELED');

/* ------------------------------------------------------------------------ */
/* Server-Sent Events                                                        */
/* ------------------------------------------------------------------------ */

interface SseEvent {
  event: string;
  data: string;
}

/**
 * Incremental text/event-stream parser: feed it decoded chunks in any split
 * (an event across chunks, several events in one), get whole events back.
 * Comment lines (": keep-alive") are skipped; data lines are joined by "\n".
 */
export function createSseParser() {
  let buffer = '';
  // A "\r" that ended the last chunk may be the first half of "\r\n".
  let carry = '';
  const parseBlock = (block: string): SseEvent | null => {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (!line || line.startsWith(':')) continue;
      const colon = line.indexOf(':');
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? '' : line.slice(colon + 1);
      if (value.startsWith(' ')) value = value.slice(1);
      if (field === 'event') event = value;
      else if (field === 'data') data.push(value);
    }
    return data.length ? { event, data: data.join('\n') } : null;
  };
  return {
    push(chunk: string): SseEvent[] {
      const text = carry + chunk;
      carry = text.endsWith('\r') ? '\r' : '';
      buffer += (carry ? text.slice(0, -1) : text).replace(/\r\n?/g, '\n');
      const out: SseEvent[] = [];
      let end = buffer.indexOf('\n\n');
      while (end !== -1) {
        const parsed = parseBlock(buffer.slice(0, end));
        if (parsed) out.push(parsed);
        buffer = buffer.slice(end + 2);
        end = buffer.indexOf('\n\n');
      }
      return out;
    },
  };
}

interface ErrorReply {
  status: number;
  statusText: string;
  headers: Record<string, string>;
  data: unknown;
}

async function readErrorReply(response: Response): Promise<ErrorReply> {
  const raw = await response.text().catch(() => '');
  let data: unknown = raw;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    // Not JSON (a proxy's page): kept as text, never shown.
  }
  const headers: Record<string, string> = {};
  response.headers.forEach((value, key) => {
    headers[key.toLowerCase()] = value;
  });
  return { status: response.status, statusText: response.statusText, headers, data };
}

// A non-2xx reply before the stream started, run through the same rules as
// the axios client (X-SM-Origin, technical details, proxy pages), so people
// get the same sentence either way.
function turnHttpError(reply: ErrorReply, url: string): StoryTurnError {
  const config = { url, method: 'post', headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  const axiosError = new AxiosError(
    `Request failed with status code ${reply.status}`,
    reply.status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
    config,
    null,
    { status: reply.status, statusText: reply.statusText, headers: reply.headers, config, data: reply.data },
  );
  return new StoryTurnError(friendlyError(getErrorMessage(axiosError)), reply.status);
}

// The stream route is missing (a server not updated yet): use the plain POST.
const isMissingRoute = (reply: ErrorReply) =>
  (reply.status === 404 || reply.status === 405) &&
  !!reply.data && typeof reply.data === 'object' &&
  ['Not Found', 'Method Not Allowed'].includes(String((reply.data as Raw).detail));

const STREAM_LOST =
  'The connection dropped while the director was writing. The reply will appear here when it is ready, so there is no need to send again.';

/* ------------------------------------------------------------------------ */
/* Endpoints                                                                 */
/* ------------------------------------------------------------------------ */

const BASE = '/story-room';
const seg = (s: string) => encodeURIComponent(s);

// `made` approves the keyframe "Make keyframe" left on a shot (keyframes only).
export type ImageSource = { imageId: number } | { assetId: number } | { made: true };
const imageBody = (source: ImageSource): Raw =>
  'imageId' in source ? { image_id: source.imageId } : 'assetId' in source ? { asset_id: source.assetId } : { made: true };
// A keyframe waits on the image model; the server gives it up to 150 seconds.
const KEYFRAME_TIMEOUT_MS = 200000;
// A turn is one LLM call over the whole document; give it as long as the proxy does.
const TURN_TIMEOUT_MS = 300000;

export const storyRoomApi = {
  config: async (): Promise<StoryRoomConfig> =>
    transformConfig((await apiClient.get(`${BASE}/config`)).data as Raw),

  threads: async (params: { q?: string; archived?: boolean } = {}): Promise<ThreadSummary[]> => {
    const response = await apiClient.get(`${BASE}/threads`, {
      params: { q: params.q || undefined, archived: params.archived ?? false },
    });
    const data = response.data as Raw[] | { threads?: Raw[] };
    const rows = Array.isArray(data) ? data : (data.threads ?? []);
    return rows.map(transformThreadSummary);
  },

  createThread: async (body: { format: StoryFormat; title?: string; message?: string }): Promise<StoryThread> =>
    transformThread((await apiClient.post(`${BASE}/threads`, body, { timeout: TURN_TIMEOUT_MS })).data as Raw),

  thread: async (id: number): Promise<StoryThread> =>
    transformThread((await apiClient.get(`${BASE}/threads/${id}`)).data as Raw),

  updateThread: async (id: number, body: { title?: string; isArchived?: boolean }): Promise<void> => {
    const payload: Raw = {};
    if (body.title !== undefined) payload.title = body.title;
    if (body.isArchived !== undefined) payload.is_archived = body.isArchived;
    await apiClient.patch(`${BASE}/threads/${id}`, payload);
  },

  deleteThread: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/threads/${id}`);
  },

  sendMessage: async (id: number, message: string): Promise<TurnResult> => {
    const response = await apiClient.post(
      `${BASE}/threads/${id}/messages`,
      { message },
      { timeout: TURN_TIMEOUT_MS },
    );
    return transformTurn(response.data as Raw);
  },

  /**
   * The same turn as sendMessage, streamed: the reply arrives through
   * `handlers` while the director writes it, and the promise resolves with
   * the saved turn. Errors are StoryTurnError (a sentence for people and the
   * status); aborting `signal` only stops reading, the server still finishes
   * and saves the turn. Falls back to sendMessage when the stream cannot be
   * opened (no streaming support, a network error, a server without the route).
   */
  streamTurn: async (
    id: number,
    body: { message: string },
    handlers: TurnStreamHandlers,
    signal?: AbortSignal,
  ): Promise<TurnResult> => {
    const plain = () => storyRoomApi.sendMessage(id, body.message);
    if (typeof fetch !== 'function' || typeof ReadableStream === 'undefined' || typeof TextDecoder === 'undefined') {
      return plain();
    }
    const path = `${BASE}/threads/${id}/messages/stream`;
    const url = `${(apiClient.defaults.baseURL ?? '/api').replace(/\/$/, '')}${path}`;
    const open = () =>
      fetch(url, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ message: body.message }),
        signal,
      });

    let response: Response;
    try {
      response = await open();
      if (response.status === 401) {
        // The access cookie expired: refresh once and ask again, as the axios client does.
        await response.body?.cancel().catch(() => undefined);
        try {
          await apiClient.post('/auth/refresh');
        } catch (err) {
          throw new StoryTurnError(getErrorMessage(err, 'Your session has expired. Please sign in again.'), 401);
        }
        response = await open();
      }
    } catch (err) {
      if (err instanceof StoryTurnError || signal?.aborted || isAbort(err)) throw err;
      return plain();
    }

    if (!response.ok) {
      const reply = await readErrorReply(response);
      if (isMissingRoute(reply)) return plain();
      throw turnHttpError(reply, path);
    }
    if (!response.body || !(response.headers.get('content-type') ?? '').includes('text/event-stream')) {
      // Accepted but not streamed by something in between: the turn still runs on the server.
      throw new StoryTurnError(STREAM_LOST, response.status, true);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const parser = createSseParser();
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        for (const ev of parser.push(decoder.decode(value, { stream: true }))) {
          let data: Raw;
          try {
            data = JSON.parse(ev.data) as Raw;
          } catch {
            continue;
          }
          if (ev.event === 'delta') handlers.onDelta?.(str(data.text));
          else if (ev.event === 'status') handlers.onStatus?.(str(data.text));
          else if (ev.event === 'replace') handlers.onReplace?.(str(data.text));
          else if (ev.event === 'done') return transformTurn(data);
          else if (ev.event === 'error') {
            throw new StoryTurnError(
              friendlyError(str(data.detail), 'The director could not reply. Please try again.'),
              num(data.status, 503),
            );
          }
        }
      }
    } catch (err) {
      if (err instanceof StoryTurnError || signal?.aborted || isAbort(err)) throw err;
      throw new StoryTurnError(STREAM_LOST, undefined, true);
    } finally {
      reader.cancel().catch(() => undefined);
    }
    // The stream ended without a result: the server is still finishing the turn.
    throw new StoryTurnError(STREAM_LOST, undefined, true);
  },

  saveStory: async (id: number, story: StoryDoc, expectedVersion: number): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.put(`${BASE}/threads/${id}/story`, { story, expected_version: expectedVersion })).data as Raw),

  restore: async (id: number, messageId: number): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.post(`${BASE}/threads/${id}/restore/${messageId}`)).data as Raw),

  // Saves a proposed character (to Faceless characters) or environment and sets its ref_id.
  saveCast: async (id: number, key: string): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.post(`${BASE}/threads/${id}/cast/${seg(key)}/save`)).data as Raw),

  linkCast: async (id: number, key: string, refId: number): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.post(`${BASE}/threads/${id}/cast/${seg(key)}/link`, { ref_id: refId })).data as Raw),

  shotClip: async (id: number, shotId: string): Promise<ShotClip> =>
    transformClip((await apiClient.get(`${BASE}/threads/${id}/shots/${seg(shotId)}/clip`)).data as Raw),

  // The whole piece as one clip (pieces up to 15 s), approved images as references.
  treatmentClip: async (id: number): Promise<ShotClip> =>
    transformClip((await apiClient.get(`${BASE}/threads/${id}/treatment/clip`)).data as Raw),

  // Approve a reference image for a character or environment: a gallery image
  // the user generated, or a My Assets image. A product ("p1") takes a My
  // Assets photo only. The server resolves the URL.
  approveCastImage: async (id: number, key: string, source: ImageSource): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.post(`${BASE}/threads/${id}/cast/${seg(key)}/image`, imageBody(source))).data as Raw),

  clearCastImage: async (id: number, key: string): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.delete(`${BASE}/threads/${id}/cast/${seg(key)}/image`)).data as Raw),

  // Approve the first frame of a shot (gallery image or My Assets image).
  approveKeyframe: async (id: number, shotId: string, source: ImageSource): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.post(`${BASE}/threads/${id}/shots/${seg(shotId)}/keyframe`, imageBody(source))).data as Raw),

  clearKeyframe: async (id: number, shotId: string): Promise<StoryVersioned> =>
    transformVersioned((await apiClient.delete(`${BASE}/threads/${id}/shots/${seg(shotId)}/keyframe`)).data as Raw),

  // "Make keyframe": a still from the shot's approved cast, place and product
  // images. The image goes to My Assets and waits on the shot unapproved.
  generateKeyframe: async (id: number, shotId: string): Promise<KeyframeResult> => {
    const response = await apiClient.post(
      `${BASE}/threads/${id}/shots/${seg(shotId)}/keyframe/generate`,
      {},
      { timeout: KEYFRAME_TIMEOUT_MS },
    );
    const data = response.data as Raw;
    return {
      ...transformVersioned(data),
      estimatedUsd: num(data.estimated_usd),
      assetId: numOrNull(((data.asset ?? {}) as Raw).id),
    };
  },

  // Environment library
  environments: async (): Promise<StoryEnvironment[]> => {
    const data = (await apiClient.get(`${BASE}/environments`)).data as Raw[] | { environments?: Raw[] };
    const rows = Array.isArray(data) ? data : (data.environments ?? []);
    return rows.map(transformEnvironment);
  },

  environment: async (envId: number): Promise<StoryEnvironment> =>
    transformEnvironment((await apiClient.get(`${BASE}/environments/${envId}`)).data as Raw),

  createEnvironment: async (input: EnvironmentInput): Promise<StoryEnvironment> =>
    transformEnvironment((await apiClient.post(`${BASE}/environments`, environmentBody(input))).data as Raw),

  updateEnvironment: async (envId: number, input: EnvironmentInput): Promise<StoryEnvironment> =>
    transformEnvironment((await apiClient.put(`${BASE}/environments/${envId}`, environmentBody(input))).data as Raw),

  deleteEnvironment: async (envId: number): Promise<void> => {
    await apiClient.delete(`${BASE}/environments/${envId}`);
  },

  // PNG, JPEG or WebP up to 25 MB, at most 6 per environment.
  uploadEnvironmentMedia: async (envId: number, file: File): Promise<StoryEnvironment> => {
    const form = new FormData();
    form.append('file', file);
    const response = await apiClient.post(`${BASE}/environments/${envId}/media`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    });
    return transformEnvironment(response.data as Raw);
  },

  deleteEnvironmentMedia: async (envId: number, key: string): Promise<StoryEnvironment> =>
    transformEnvironment((await apiClient.delete(`${BASE}/environments/${envId}/media/${seg(key)}`)).data as Raw),
};

// Pieces up to this length can be made as one clip from the treatment.
export const ONE_TAKE_MAX_SECONDS = 15;

// Characters, environments and products that still need an approved image.
export function imageProgress(doc: StoryDoc | null | undefined): { approved: number; total: number } {
  const entries = [...(doc?.characters ?? []), ...(doc?.environments ?? []), ...(doc?.products ?? [])];
  return { approved: entries.filter((e) => e.image_approved && e.image_url).length, total: entries.length };
}

const joinNames = (names: string[]) =>
  names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;

/**
 * Why "Make keyframe" cannot run for a shot yet, or null when it can: the
 * same checks, in the same words, as keyframe.references on the server.
 */
export function keyframeBlock(doc: StoryDoc, scene: DocScene, shot: Shot): string | null {
  const inFrame = shot.characters.map((k) => doc.characters.find((c) => c.key === k)).filter((c): c is CastEntry => !!c);
  const props = (shot.props ?? []).map((k) => (doc.products ?? []).find((p) => p.key === k)).filter((p): p is Product => !!p);
  const missing = inFrame.filter((c) => !(c.image_approved && c.image_url));
  if (missing.length) return `Approve a reference image for ${joinNames(missing.map((c) => c.name || c.key))} in the Cast tab first.`;
  const unpictured = props.filter((p) => !(p.image_approved && p.image_url));
  if (unpictured.length) {
    return `Add a photo of ${joinNames(unpictured.map((p) => p.name || p.key))} in the Cast tab first. A product is never generated.`;
  }
  const place = doc.environments.find((e) => e.key === scene.environment_key);
  const placeReady = !!place && place.image_approved && !!place.image_url;
  if (!inFrame.length && !props.length && !placeReady) {
    return place
      ? `Approve the image of ${place.name || place.key} in the Cast tab first.`
      : 'This shot has no character, product or place with an approved image to make a keyframe from. Add one to the shot first.';
  }
  return null;
}

export const ENVIRONMENT_MAX_PHOTOS = 6;
export const ENVIRONMENT_PHOTO_ACCEPT = 'image/png,image/jpeg,image/webp';
