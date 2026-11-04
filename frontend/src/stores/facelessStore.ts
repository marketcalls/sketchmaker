import { create } from 'zustand';
import {
  facelessApi,
  isRunActive,
  type CaptionStyle,
  type FacelessCharacter,
  type FacelessConfig,
  type FacelessProject,
  type FacelessSeries,
  type FacelessTemplate,
  type FacelessVoice,
  type MusicMood,
  type ProjectSummary,
  type StepRun,
  type VisualStyle,
} from '@/api/faceless';
import { getErrorMessage } from '@/utils/errors';

// Polling: quick while a step runs, back off while nothing changes, reset
// when the project moves, stop once no run is active.
const POLL_MIN_MS = 2000;
const POLL_MAX_MS = 15000;
const POLL_BACKOFF = 1.5;
// Give up after this long without any change (the scheduler is stuck or
// down); the studio offers a manual refresh.
const POLL_STALE_MS = 15 * 60 * 1000;

export function isProjectBusy(project: FacelessProject | null): boolean {
  return !!project && (project.active_runs ?? []).some(isRunActive);
}

function fingerprint(p: FacelessProject): string {
  const runs = (p.active_runs ?? []).map((r) => `${r.id}:${r.status}:${r.progress}`).join('|');
  return `${p.status}#${p.updated_at}#${runs}`;
}

interface FacelessState {
  templates: FacelessTemplate[];
  styles: VisualStyle[];
  voices: FacelessVoice[];
  defaultNarrator: string | null;
  musicMoods: MusicMood[];
  captionStyles: CaptionStyle[];
  config: FacelessConfig | null;
  catalogLoaded: boolean;
  catalogError: string | null;

  characters: FacelessCharacter[];
  charactersLoaded: boolean;
  series: FacelessSeries[];
  seriesLoaded: boolean;
  projects: ProjectSummary[];
  projectsLoaded: boolean;
  listError: string | null;

  project: FacelessProject | null;
  // Recent runs of the open project, newest first (failures show here).
  runs: StepRun[];
  projectLoading: boolean;
  projectError: string | null;
  pollStalled: boolean;

  loadCatalog: (force?: boolean) => Promise<void>;
  loadCharacters: () => Promise<void>;
  loadSeries: () => Promise<void>;
  loadProjects: () => Promise<void>;
  upsertCharacter: (c: FacelessCharacter) => void;
  removeCharacter: (id: number) => void;
  upsertSeries: (s: FacelessSeries) => void;
  removeSeries: (id: number) => void;
  removeProject: (id: number) => void;

  openProject: (id: number) => Promise<void>;
  setProject: (p: FacelessProject) => void;
  refreshProject: () => Promise<void>;
  closeProject: () => void;
  ensurePolling: () => void;
  stopPolling: () => void;
}

let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollDelay = POLL_MIN_MS;
let lastChangeAt = 0;
let lastPrint = '';
let pollProjectId: number | null = null;
let pollInFlight = false;
// Pages and dialogs all ask for the catalog on opening: one request serves them.
let catalogRequest: Promise<void> | null = null;
// Bumped by every open and close, so a reply for a project the user has left is dropped.
let openToken = 0;

export const useFacelessStore = create<FacelessState>((set, get) => {
  const clearTimer = () => {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
  };

  const schedule = () => {
    clearTimer();
    pollTimer = setTimeout(tick, pollDelay);
  };

  const loadRuns = async (id: number) => {
    try {
      const runs = await facelessApi.runs(id);
      if (get().project?.id === id) set({ runs });
    } catch {
      // runs are a detail; the project view still works
    }
  };

  const tick = async () => {
    pollTimer = null;
    const id = pollProjectId;
    if (id === null) return;
    pollInFlight = true;
    let keepGoing = true;
    try {
      const fresh = await facelessApi.project(id);
      if (pollProjectId !== id) {
        pollInFlight = false;
        return;
      }
      const print = fingerprint(fresh);
      if (print !== lastPrint) {
        lastPrint = print;
        lastChangeAt = Date.now();
        pollDelay = POLL_MIN_MS;
        loadRuns(id);
      } else {
        pollDelay = Math.min(POLL_MAX_MS, Math.round(pollDelay * POLL_BACKOFF));
      }
      set({ project: fresh, projectError: null });
      if (!isProjectBusy(fresh)) {
        // Finished: nothing left to follow.
        keepGoing = false;
        set({ pollStalled: false });
      } else if (Date.now() - lastChangeAt > POLL_STALE_MS) {
        keepGoing = false;
        set({ pollStalled: true });
      }
    } catch {
      pollDelay = Math.min(POLL_MAX_MS, Math.round(pollDelay * POLL_BACKOFF));
    }
    pollInFlight = false;
    if (!keepGoing) {
      if (pollProjectId === id) pollProjectId = null;
      return;
    }
    if (pollProjectId === id) schedule();
  };

  return {
    templates: [],
    styles: [],
    voices: [],
    defaultNarrator: null,
    musicMoods: [],
    captionStyles: [],
    config: null,
    catalogLoaded: false,
    catalogError: null,

    characters: [],
    charactersLoaded: false,
    series: [],
    seriesLoaded: false,
    projects: [],
    projectsLoaded: false,
    listError: null,

    project: null,
    runs: [],
    projectLoading: false,
    projectError: null,
    pollStalled: false,

    // Keeps whatever arrived, but any failure leaves catalogLoaded false, so the
    // next page or dialog to open asks again.
    loadCatalog: (force = false) => {
      if (get().catalogLoaded && !force) return Promise.resolve();
      if (catalogRequest) return catalogRequest;
      catalogRequest = (async () => {
        const [tpl, voices, musicMoods, captionStyles, config] = await Promise.allSettled([
          facelessApi.templates(),
          facelessApi.voices(),
          facelessApi.musicMoods(),
          facelessApi.captionStyles(),
          facelessApi.config(),
        ]);
        const failed = [tpl, voices, musicMoods, captionStyles, config].find(
          (r): r is PromiseRejectedResult => r.status === 'rejected',
        );
        set((s) => ({
          templates: tpl.status === 'fulfilled' ? tpl.value.templates ?? [] : s.templates,
          styles: tpl.status === 'fulfilled' ? tpl.value.styles ?? [] : s.styles,
          voices: voices.status === 'fulfilled' ? voices.value.voices ?? [] : s.voices,
          defaultNarrator: voices.status === 'fulfilled' ? voices.value.default_narrator ?? null : s.defaultNarrator,
          musicMoods: musicMoods.status === 'fulfilled' ? musicMoods.value : s.musicMoods,
          captionStyles: captionStyles.status === 'fulfilled' ? captionStyles.value : s.captionStyles,
          config: config.status === 'fulfilled' ? config.value : s.config,
          catalogLoaded: !failed,
          catalogError: failed ? getErrorMessage(failed.reason, 'The studio catalog could not be loaded.') : null,
        }));
      })().finally(() => {
        catalogRequest = null;
      });
      return catalogRequest;
    },

    loadCharacters: async () => {
      try {
        const characters = await facelessApi.characters(true);
        set({ characters, charactersLoaded: true, listError: null });
      } catch (err) {
        set({ charactersLoaded: true, listError: getErrorMessage(err, 'Could not load your cast') });
      }
    },

    loadSeries: async () => {
      try {
        const series = await facelessApi.series();
        set({ series, seriesLoaded: true });
      } catch (err) {
        set({ seriesLoaded: true, listError: getErrorMessage(err, 'Could not load your series') });
      }
    },

    loadProjects: async () => {
      try {
        const res = await facelessApi.projects({ page_size: 50 });
        set({ projects: res.projects ?? [], projectsLoaded: true, listError: null });
      } catch (err) {
        set({ projectsLoaded: true, listError: getErrorMessage(err, 'Could not load your projects') });
      }
    },

    upsertCharacter: (c) =>
      set((s) => ({
        characters: s.characters.some((x) => x.id === c.id)
          ? s.characters.map((x) => (x.id === c.id ? c : x))
          : [c, ...s.characters],
      })),
    removeCharacter: (id) => set((s) => ({ characters: s.characters.filter((c) => c.id !== id) })),
    upsertSeries: (series) =>
      set((s) => ({
        series: s.series.some((x) => x.id === series.id)
          ? s.series.map((x) => (x.id === series.id ? series : x))
          : [series, ...s.series],
      })),
    removeSeries: (id) => set((s) => ({ series: s.series.filter((x) => x.id !== id) })),
    removeProject: (id) => set((s) => ({ projects: s.projects.filter((p) => p.id !== id) })),

    openProject: async (id) => {
      const token = ++openToken;
      if (get().project?.id !== id) {
        get().stopPolling();
        set({ project: null, runs: [] });
      }
      set({ projectLoading: true, projectError: null, pollStalled: false });
      try {
        const project = await facelessApi.project(id);
        if (token !== openToken) return;
        set({ project, projectLoading: false });
        loadRuns(id);
        get().ensurePolling();
      } catch (err) {
        if (token !== openToken) return;
        set({ projectLoading: false, projectError: getErrorMessage(err, 'Could not open this project') });
      }
    },

    // Ignores a reply for any project but the open one: it would put that
    // project's buttons under the wrong URL.
    setProject: (project) => {
      if (get().project?.id !== project.id) return;
      set({ project, projectError: null });
      get().ensurePolling();
    },

    // After starting a step (the response is the run, not the project).
    refreshProject: async () => {
      const id = get().project?.id;
      if (!id) return;
      try {
        const project = await facelessApi.project(id);
        if (get().project?.id !== id) return;
        set({ project, pollStalled: false });
        loadRuns(id);
        get().ensurePolling();
      } catch (err) {
        if (get().project?.id !== id) return;
        set({ projectError: getErrorMessage(err, 'Could not refresh the project') });
      }
    },

    closeProject: () => {
      openToken += 1;
      get().stopPolling();
      set({ project: null, runs: [], projectLoading: false, projectError: null, pollStalled: false });
    },

    ensurePolling: () => {
      const project = get().project;
      if (!project || !isProjectBusy(project)) return;
      const restart = pollProjectId !== project.id || (pollTimer === null && !pollInFlight);
      pollProjectId = project.id;
      pollDelay = POLL_MIN_MS;
      lastChangeAt = Date.now();
      lastPrint = fingerprint(project);
      set({ pollStalled: false });
      if (restart) schedule();
    },

    stopPolling: () => {
      pollProjectId = null;
      clearTimer();
    },
  };
});
