// Character library API (/api/faceless): the cast, voice and config routes that
// Story Room's Cast tab and the character editor use. Request bodies are
// backend/app/schemas/faceless.py and characters are built by
// backend/app/services/faceless/views.py.
//
// Types keep the wire's snake_case names so a backend change shows up here
// as a type error instead of a silent undefined from a camelCase mapper.
import apiClient from './client';

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type CharacterKind = 'fictional' | 'real_person';
export type ConsentRelationship = 'self' | 'with_permission';
export type ConsentStatus = 'not_required' | 'missing' | 'outdated' | 'valid' | 'revoked';

// ---------------------------------------------------------------------------
// Catalogues
// ---------------------------------------------------------------------------

export interface FacelessVoice {
  id: string;
  gender: string;
  accent: string;
  tone: string;
}

export interface ConsentText {
  version: string;
  text: string;
  relationships: ConsentRelationship[];
}

export interface FacelessConfig {
  limits: {
    max_character_media: number;
  };
  consent: ConsentText;
}

// ---------------------------------------------------------------------------
// Characters
// ---------------------------------------------------------------------------

export interface SafetyFlag {
  kind: 'real_person' | 'possible_minor' | 'public_figure' | 'copyrighted_character' | 'brand_logo' | 'sensitive_content';
  confidence: number;
  note: string;
}

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
  role: 'reference' | 'source_video' | 'frame';
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
// Helpers
// ---------------------------------------------------------------------------

const BASE = '/faceless';
const multipart = { headers: { 'Content-Type': 'multipart/form-data' } };

function fileForm(file: File): FormData {
  const fd = new FormData();
  fd.append('file', file);
  return fd;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const facelessApi = {
  // Catalogues
  voices: async (): Promise<{ voices: FacelessVoice[]; default_narrator: string }> =>
    (await apiClient.get(`${BASE}/voices`)).data,
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
};
