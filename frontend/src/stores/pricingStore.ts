import { create } from 'zustand';
import apiClient from '../api/client';
import { STORY_VIDEO_MODELS } from '../api/story';

// Price keys, built exactly like backend/app/services/pricing.py.
export const imageKey = (model: string, resolution: string = '1k') =>
  `image:${model}:${(resolution || '1k').toLowerCase()}`;

// 1K edits use the plain key; 2K and 4K add a suffix.
export const editKey = (model: string, resolution: string = '1k') => {
  const res = (resolution || '1k').toLowerCase();
  return res === '1k' ? `edit:${model}` : `edit:${model}:${res}`;
};

// Logo showcase images: Nano Banana 2.1 edit at 2K (logo_service.SHOWCASE_MODEL).
export const LOGO_SHOWCASE_KEY = editKey('google/nano-banana-2.1/edit', '2k');

export const videoKey = (family: string, resolution: string) => `video:${family}:${resolution}`;

// Explainer images: per resolution, with a separate key when reference images
// send the request to the edit endpoint. Unknown resolutions price as 2K, the
// size the backend renders them at.
export const explainerKey = (resolution: string, withReferences: boolean = false) => {
  const raw = (resolution || '2k').toLowerCase();
  const res = ['1k', '2k', '4k'].includes(raw) ? raw : '2k';
  return withReferences ? `explainer:edit:${res}` : `explainer:${res}`;
};

// Motion Control: per second of output on one of three Kling tiers (backend
// pricing.MOTION_CONTROL_KEYS), and the output follows the reference video up
// to a cap set by the character orientation (MOTION_CONTROL_MAX_SECONDS).
export type MotionControlTier = 'v3-standard' | 'v3-pro' | 'v2.6';
export const MOTION_CONTROL_DEFAULT_TIER: MotionControlTier = 'v3-standard';
export const MOTION_CONTROL_KEYS: Record<MotionControlTier, string> = {
  'v3-standard': 'video:kling-v3-motion:standard',
  'v3-pro': 'video:kling-v3-motion:pro',
  'v2.6': 'video:kling-2.6-motion:any',
};

// Multi-character motion transfer, MiniMax H3 Max Recast (backend
// pricing.RECAST_KEYS): per second of output, which is the source video's
// length (5 to 15 s).
export const RECAST_KEYS = { '768p': 'video:h3-max-recast:768p', '1080p': 'video:h3-max-recast:1080p' } as const;
export const RECAST_MIN_SECONDS = 5;
export const RECAST_MAX_SECONDS = 15;
export const RECAST_MAX_PEOPLE = 4;
export const MOTION_CONTROL_MAX_SECONDS: Record<'video' | 'image', number> = { video: 30, image: 10 };

// Whole seconds a Motion Control job is priced on: the reference length
// rounded up (ignoring padding under 0.05s), capped at the orientation's
// maximum, or that maximum when the length is unknown.
export function motionControlSeconds(orientation: 'video' | 'image', durationSeconds?: number | null): number {
  const cap = MOTION_CONTROL_MAX_SECONDS[orientation] ?? MOTION_CONTROL_MAX_SECONDS.video;
  if (!durationSeconds || !Number.isFinite(durationSeconds) || durationSeconds <= 0) return cap;
  return Math.min(cap, Math.max(1, Math.ceil(Math.round(durationSeconds * 10) / 10)));
}

// Lip Sync: per second of output (the audio length) by resolution, with fal's
// 1.2x multiplier on videos over 15 seconds. Mirrors backend pricing
// (LIPSYNC_*, lipsync_seconds, lipsync_usd) and the audio limits in
// lipsync_service (AUDIO_MIN_SECONDS, AUDIO_MAX_SECONDS).
export const LIPSYNC_KEY_PREFIX = 'video:h3-max-lipsync:';
export const lipsyncKey = (resolution: string) => `${LIPSYNC_KEY_PREFIX}${(resolution || '768p').toLowerCase()}`;
export const LIPSYNC_LONG_AFTER_SECONDS = 15;
export const LIPSYNC_LONG_MULTIPLIER = 1.2;
export const LIPSYNC_MIN_SECONDS = 5;
export const LIPSYNC_MAX_SECONDS = 120;

// Whole seconds a Lip Sync video is priced on: the length rounded up.
export function lipsyncSeconds(durationSeconds?: number | null): number {
  if (!durationSeconds || !Number.isFinite(durationSeconds) || durationSeconds <= 0) return 0;
  return Math.max(1, Math.ceil(Math.round(durationSeconds * 100) / 100));
}

// USD for `seconds` of Lip Sync at `perSecond`: times 1.2 over 15 seconds,
// rounded to 4 decimals like the backend.
export function lipsyncUsd(perSecond: number, seconds: number): number {
  let total = perSecond * Math.max(0, Math.floor(seconds));
  if (seconds > LIPSYNC_LONG_AFTER_SECONDS) total *= LIPSYNC_LONG_MULTIPLIER;
  return Math.round(total * 1e4) / 1e4;
}

// Format a USD amount for display. Every amount shown is an estimate, so this
// is the only formatter: ~$0.05, with more decimals for smaller amounts.
export const formatUsd = (usd: number) => {
  const value = Number(usd) || 0;
  if (value === 0) return '$0.00';
  const size = Math.abs(value);
  const decimals = size >= 0.1 ? 2 : size >= 0.01 ? 3 : 4;
  return `~$${value.toFixed(decimals)}`;
};

// Smallest and largest per-unit price among keys with a prefix ('image:',
// 'edit:', 'explainer:', 'logo:text:', 'video:'), or null if none. `exclude`
// drops keys the page does not offer (for example 2K and 4K edits).
export function priceRange(
  models: Record<string, number> | null | undefined,
  prefix: string,
  exclude?: RegExp,
): { min: number; max: number } | null {
  const values = Object.entries(models ?? {})
    .filter(([key]) => key.startsWith(prefix) && !(exclude && exclude.test(key)))
    .map(([, v]) => v);
  if (values.length === 0) return null;
  return { min: Math.min(...values), max: Math.max(...values) };
}

// "~$0.05" or "~$0.05 to ~$0.24" for a range from priceRange.
export function formatPriceRange(range: { min: number; max: number }): string {
  if (range.min === range.max) return formatUsd(range.min);
  return `${formatUsd(range.min)} to ${formatUsd(range.max)}`;
}

// Per-second Stories prices of the models and resolutions the Stories page
// offers (a key priced but not offered, such as Seedance 1080p, is left out,
// and so are the reference-token and reference-video rates).
export function storyPriceRange(models: Record<string, number> | null | undefined): { min: number; max: number } | null {
  const values = Object.values(STORY_VIDEO_MODELS)
    .flatMap((cfg) => cfg.resolutions.map((res) => models?.[videoKey(cfg.id, res)]))
    .filter((v): v is number => typeof v === 'number');
  if (values.length === 0) return null;
  return { min: Math.min(...values), max: Math.max(...values) };
}

// Edit keys for 2K and 4K, which the Magix and Try-On pages do not offer.
export const HIGH_RES_EDIT = /^edit:.*:(2k|4k)$/;

// Motion Graphics and Faceless keys (backend pricing: ELEVEN_V4_KEY,
// ELEVEN_MUSIC_KEY, RENDER_MINUTE_KEY). Stills and thumbnails reuse the image
// and edit keys, clips the MiniMax H3 Max video keys.
export const VOICE_KEY = 'audio:eleven-v4:1k-chars';
export const MUSIC_KEY = 'audio:elevenlabs-music:minute';
export const RENDER_MINUTE_KEY = 'render:minute';
// Story Room: each AI reply in the chat, and each Quick clip prompt enhance.
export const STORY_CHAT_TURN_KEY = 'story:chat-turn';
export const STORY_ENHANCE_KEY = 'story:prompt-enhance';
// Quality checks (backend quality_gate.py): one vision read of an image or
// clip, an LLM estimate like the Story Room keys.
export const QA_CHECK_KEY = 'qa:vision-check';
// Background removal per image, subtitles per minute of video.
export const REMOVE_BG_KEY = 'utility:remove-bg';
export const SUBTITLES_MINUTE_KEY = 'utility:subtitles:minute';

// The render price of a studio: a render key that names it (for example a
// motion graphics key under "render:"), else the shared per-minute key.
export function renderMinuteCost(models: Record<string, number> | null | undefined, studio?: string): number | undefined {
  const all = models ?? {};
  if (studio) {
    const own = Object.keys(all).find((k) => k.startsWith('render:') && k.includes(studio));
    if (own) return all[own];
  }
  return all[RENDER_MINUTE_KEY];
}

interface PricingState {
  costs: Record<string, number> | null;
  fetchCosts: () => Promise<void>;
  // USD for one unit of a price key, or undefined while prices are loading or
  // for an unknown key.
  getModelCost: (key: string) => number | undefined;
}

export const usePricingStore = create<PricingState>((set, get) => ({
  costs: null,

  fetchCosts: async () => {
    try {
      const { data } = await apiClient.get<{ models?: Record<string, number> }>('/pricing/costs');
      set({ costs: data.models ?? {} });
    } catch {
      // Prices are display only: pages show nothing until a later fetch works.
    }
  },

  getModelCost: (key) => get().costs?.[key],
}));
