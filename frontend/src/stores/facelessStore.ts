import { create } from 'zustand';
import { facelessApi, type FacelessCharacter, type FacelessConfig, type FacelessVoice } from '@/api/faceless';
import { getErrorMessage } from '@/utils/errors';

interface FacelessState {
  voices: FacelessVoice[];
  config: FacelessConfig | null;
  catalogLoaded: boolean;
  catalogError: string | null;

  characters: FacelessCharacter[];
  charactersLoaded: boolean;
  listError: string | null;

  loadCatalog: (force?: boolean) => Promise<void>;
  loadCharacters: () => Promise<void>;
  upsertCharacter: (c: FacelessCharacter) => void;
  removeCharacter: (id: number) => void;
}

export const useFacelessStore = create<FacelessState>((set, get) => ({
  voices: [],
  config: null,
  catalogLoaded: false,
  catalogError: null,

  characters: [],
  charactersLoaded: false,
  listError: null,

  loadCatalog: async (force = false) => {
    if (get().catalogLoaded && !force) return;
    try {
      const [voices, config] = await Promise.all([
        facelessApi.voices(),
        facelessApi.config().catch(() => null),
      ]);
      set({
        voices: voices.voices ?? [],
        config,
        catalogLoaded: true,
        catalogError: null,
      });
    } catch (err) {
      set({ catalogError: getErrorMessage(err, 'Could not load the voices') });
    }
  },

  loadCharacters: async () => {
    try {
      const characters = await facelessApi.characters(true);
      set({ characters, charactersLoaded: true, listError: null });
    } catch (err) {
      set({ charactersLoaded: true, listError: getErrorMessage(err, 'Could not load your cast') });
    }
  },

  upsertCharacter: (c) =>
    set((s) => ({
      characters: s.characters.some((x) => x.id === c.id)
        ? s.characters.map((x) => (x.id === c.id ? c : x))
        : [c, ...s.characters],
    })),
  removeCharacter: (id) => set((s) => ({ characters: s.characters.filter((c) => c.id !== id) })),
}));
