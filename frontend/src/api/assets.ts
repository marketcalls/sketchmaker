import apiClient from './client';

// My Assets (backend app/routers/assets.py): files uploaded once and reused
// across tools, plus voices generated with ElevenLabs.
export type AssetKind = 'image' | 'logo' | 'video' | 'audio';

export interface Asset {
  id: number;
  kind: AssetKind;
  name: string;
  url: string;
  contentType: string | null;
  fileSizeBytes: number;
  width: number | null;
  height: number | null;
  durationSeconds: number | null;
  source: 'upload' | 'voice' | string;
  voice: string | null;
  voiceProvider: string | null;
  text: string | null;
  createdAt: string;
}

export interface AssetList {
  assets: Asset[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export type VoiceProviderId = 'elevenlabs' | 'sarvam';

export interface VoiceOption {
  id: string;
  label: string;
  // Sarvam voices belong to one language (VoiceLanguage.id); ElevenLabs voices are null.
  language: string | null;
  description: string | null;
  gender?: 'female' | 'male' | 'neutral' | null;
}

export interface VoiceLanguage {
  id: string;
  code: string;
  label: string;
}

// One voice model (backend assets.voice_catalog): ElevenLabs always, Sarvam
// Bulbul v4 once its key is saved.
export interface VoiceProvider {
  id: VoiceProviderId;
  label: string;
  model: string;
  description: string;
  priceKey: string;
  maxCharacters: number;
  defaultVoice: string;
  defaultLanguage: string | null;
  languages: VoiceLanguage[];
  voices: VoiceOption[];
}

export interface VoiceCatalog {
  providers: VoiceProvider[];
}

export interface VoiceRequest {
  text: string;
  voice: string;
  provider: VoiceProviderId;
  stability?: number;
  pace?: number;
  name?: string;
}

export function transformAsset(data: Record<string, unknown>): Asset {
  return {
    id: data.id as number,
    kind: data.kind as AssetKind,
    name: data.name as string,
    url: data.url as string,
    contentType: (data.content_type as string | null) ?? null,
    fileSizeBytes: (data.file_size_bytes as number) ?? 0,
    width: (data.width as number | null) ?? null,
    height: (data.height as number | null) ?? null,
    durationSeconds: (data.duration_seconds as number | null) ?? null,
    source: (data.source as string) ?? 'upload',
    voice: (data.voice as string | null) ?? null,
    voiceProvider: (data.voice_provider as string | null) ?? null,
    text: (data.text as string | null) ?? null,
    createdAt: data.created_at as string,
  };
}

export const assetsApi = {
  list: async (params: { kinds?: AssetKind[]; q?: string; page?: number; pageSize?: number } = {}): Promise<AssetList> => {
    const response = await apiClient.get('/assets', {
      params: {
        kind: params.kinds && params.kinds.length ? params.kinds.join(',') : undefined,
        q: params.q || undefined,
        page: params.page ?? 1,
        page_size: params.pageSize ?? 24,
      },
    });
    const data = response.data as Record<string, unknown>;
    return {
      assets: (data.assets as Record<string, unknown>[]).map(transformAsset),
      total: data.total as number,
      page: data.page as number,
      pageSize: data.page_size as number,
      totalPages: data.total_pages as number,
    };
  },

  upload: async (file: File, opts: { asLogo?: boolean; onProgress?: (percent: number) => void } = {}): Promise<Asset> => {
    const form = new FormData();
    form.append('file', file);
    if (opts.asLogo) form.append('kind', 'logo');
    const response = await apiClient.post('/assets/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        if (opts.onProgress && event.total) opts.onProgress(Math.round((event.loaded / event.total) * 100));
      },
    });
    return transformAsset(response.data as Record<string, unknown>);
  },

  // The asset as a File, for a page's ordinary upload (same-origin, owner only).
  toFile: async (asset: Asset): Promise<File> => {
    const response = await apiClient.get(`/assets/${asset.id}/file`, { responseType: 'blob', timeout: 300000 });
    const ext = asset.url.split('?')[0].match(/\.[a-z0-9]{2,5}$/i)?.[0] ?? '';
    const name = asset.name.toLowerCase().endsWith(ext.toLowerCase()) ? asset.name : `${asset.name}${ext}`;
    const type = asset.contentType || (response.data as Blob).type || 'application/octet-stream';
    return new File([response.data as Blob], name, { type, lastModified: Date.now() });
  },

  rename: async (id: number, name: string): Promise<Asset> => {
    const response = await apiClient.patch(`/assets/${id}`, { name });
    return transformAsset(response.data as Record<string, unknown>);
  },

  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/assets/${id}`);
  },

  // A short sample of a voice (made once on the server, then kept).
  voiceSample: async (provider: VoiceProviderId, voice: string): Promise<string> => {
    const response = await apiClient.get(`/assets/voices/${provider}/${encodeURIComponent(voice)}/sample`, { timeout: 90000 });
    return (response.data as { url: string }).url;
  },

  voices: async (): Promise<VoiceCatalog> => {
    const response = await apiClient.get('/assets/voices');
    const data = response.data as { providers: Record<string, unknown>[] };
    return {
      providers: data.providers.map((p) => ({
        id: p.id as VoiceProviderId,
        label: p.label as string,
        model: p.model as string,
        description: p.description as string,
        priceKey: p.price_key as string,
        maxCharacters: p.max_characters as number,
        defaultVoice: p.default_voice as string,
        defaultLanguage: (p.default_language as string | null) ?? null,
        languages: p.languages as VoiceLanguage[],
        voices: p.voices as VoiceOption[],
      })),
    };
  },

  generateVoice: async (req: VoiceRequest): Promise<{ asset: Asset }> => {
    // A voice takes a few seconds; the server gives fal up to 120 s and the
    // download 30 s, so the page waits longer than that.
    const response = await apiClient.post('/assets/voice', req, { timeout: 240000 });
    const data = response.data as Record<string, unknown>;
    return {
      asset: transformAsset(data.asset as Record<string, unknown>),
    };
  },
};
