import apiClient from './client';
import type { GeneratedImage } from '../types';

// Quality checks (backend app/services/quality_gate.py): one paid vision read
// of a finished image or clip. The verdict is computed on the server from
// the rubric lines; a check that could not be read is "unverified". A failed
// check is a badge with reasons; fixing it is the user's call, at the fix's
// own price.
export type QualityVerdict = 'pass' | 'warn' | 'fail' | 'unverified';
export type QualityFixTarget = 'spelling' | 'defects';

export interface QualityLine {
  id: string;
  text: string;
  verdict: QualityVerdict;
  evidence: string;
}

export interface QualityDefect {
  region: string;
  kind: string;
  severity: 'minor' | 'major' | 'critical';
  fix_instruction: string;
}

export interface Quality {
  status: 'pending' | 'done';
  verdict?: QualityVerdict;
  reasons?: string[];
  lines?: QualityLine[];
  defects?: QualityDefect[];
  kind?: string | null;
  checked_at?: string | null;
  fixable?: QualityFixTarget[];
}

export interface QualityConfig {
  available: boolean;
  estimated_usd: number;
  // /generate does not offer the check on these (cheapest) models.
  skip_models: string[];
  // Fixes are instruction edits on this model, priced by its edit key.
  fix_model: string;
}

export const qualityApi = {
  config: async (): Promise<QualityConfig> => {
    const { data } = await apiClient.get<QualityConfig>('/quality/config');
    return data;
  },

  image: async (imageId: number): Promise<Quality | null> => {
    const { data } = await apiClient.get<{ image_id: number; quality: Quality | null }>(`/quality/image/${imageId}`);
    return data.quality;
  },

  // A paid edit of the kept image: the failed spelling or the defects, with
  // "change nothing else". Returns the new image (snake_case, as stored).
  fix: async (imageId: number, target: QualityFixTarget): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.post(`/quality/image/${imageId}/fix`, { target });
    return data as Record<string, unknown>;
  },
};

// The edit resolution a fix runs at, matching the backend fix_resolution.
export function fixResolution(width?: number | null, height?: number | null): '1k' | '2k' | '4k' {
  const side = Math.max(Number(width) || 0, Number(height) || 0);
  if (side > 2600) return '4k';
  if (side > 1500) return '2k';
  return '1k';
}

// The image a fix returns, in the shape the generate page keeps.
export function fixedImage(data: Record<string, unknown>): GeneratedImage {
  return {
    id: data.id as number,
    filename: data.filename as string,
    prompt: data.prompt as string,
    magicPrompt: data.magic_prompt as string | undefined,
    artStyle: data.art_style as string | undefined,
    width: data.width as number | undefined,
    height: data.height as number | undefined,
    model: data.model as string | undefined,
    aspectRatio: data.aspect_ratio as string | undefined,
    createdAt: data.created_at as string,
    url: data.url as string,
    thumbnailUrl: data.thumbnail_url as string | undefined,
    quality: (data.quality as Quality | null) ?? null,
  };
}
