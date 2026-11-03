import { create } from 'zustand';
import {
  ACTIVE_JOB,
  errorCode,
  motionGraphicsApi,
  type Job,
  type MGCatalog,
  type MGProject,
  type MGSpec,
  type ProjectSummary,
} from '@/api/motionGraphics';
import { getErrorMessage } from '@/utils/errors';

// Motion Graphics Studio state: the catalog (loaded once), the project list,
// and the open project with a local copy of its spec. Edits change the local
// spec immediately (previews read it, unsaved) and are saved after a short
// pause; the server's validation and timing plan come back with each save.

const SAVE_DELAY_MS = 900;
const POLL_MS = 2500;

interface MGState {
  catalog: MGCatalog | null;
  catalogError: string | null;
  projects: ProjectSummary[];
  projectsLoaded: boolean;
  listError: string | null;

  project: MGProject | null;
  spec: MGSpec | null;
  dirty: boolean;
  saving: boolean;
  saveError: string | null;
  loadError: string | null;

  loadCatalog: () => Promise<void>;
  loadProjects: () => Promise<void>;
  removeProject: (id: number) => void;
  openProject: (id: number) => Promise<void>;
  closeProject: () => void;
  setProject: (p: MGProject) => void;
  editSpec: (fn: (spec: MGSpec) => MGSpec) => void;
  saveNow: () => Promise<void>;
  refresh: () => Promise<void>;
  watchJob: (job: Job) => void;
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

export const useMotionGraphicsStore = create<MGState>((set, get) => ({
  catalog: null,
  catalogError: null,
  projects: [],
  projectsLoaded: false,
  listError: null,
  project: null,
  spec: null,
  dirty: false,
  saving: false,
  saveError: null,
  loadError: null,

  loadCatalog: async () => {
    if (get().catalog) return;
    try {
      set({ catalog: await motionGraphicsApi.catalog(), catalogError: null });
    } catch (err) {
      set({ catalogError: getErrorMessage(err, 'Could not load the templates') });
    }
  },

  loadProjects: async () => {
    try {
      const { projects } = await motionGraphicsApi.projects(1, 48);
      set({ projects, projectsLoaded: true, listError: null });
    } catch (err) {
      set({ projectsLoaded: true, listError: getErrorMessage(err, 'Could not load your projects') });
    }
  },

  removeProject: (id) => set({ projects: get().projects.filter((p) => p.id !== id) }),

  openProject: async (id) => {
    set({ loadError: null });
    try {
      const p = await motionGraphicsApi.project(id);
      get().setProject(p);
      if (p.active_job) get().watchJob(p.active_job);
    } catch (err) {
      set({ loadError: getErrorMessage(err, 'Could not open the project') });
    }
  },

  closeProject: () => {
    if (saveTimer) clearTimeout(saveTimer);
    if (pollTimer) clearTimeout(pollTimer);
    saveTimer = pollTimer = null;
    set({ project: null, spec: null, dirty: false, saveError: null });
  },

  setProject: (p) => {
    // Keep unsaved local edits when a background refresh arrives.
    const keepLocal = get().dirty && get().project?.id === p.id;
    set({ project: p, spec: keepLocal ? get().spec : clone(p.spec) });
  },

  editSpec: (fn) => {
    const spec = get().spec;
    if (!spec) return;
    set({ spec: fn(clone(spec)), dirty: true, saveError: null });
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void get().saveNow();
    }, SAVE_DELAY_MS);
  },

  saveNow: async () => {
    const { project, spec, dirty, saving } = get();
    if (!project || !spec || !dirty) return;
    if (saving) {
      // A save is in flight: try again once it lands.
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => void get().saveNow(), SAVE_DELAY_MS);
      return;
    }
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = null;
    const sent = JSON.stringify(spec);
    set({ saving: true });
    try {
      const p = await motionGraphicsApi.saveSpec(project.id, spec, project.spec_version);
      const changedSince = JSON.stringify(get().spec) !== sent;
      set({ project: p, saving: false, dirty: changedSince, spec: changedSince ? get().spec : clone(p.spec) });
      if (changedSince) {
        saveTimer = setTimeout(() => void get().saveNow(), SAVE_DELAY_MS);
      }
    } catch (err) {
      if (errorCode(err) === 'version_conflict') {
        // A job (AI images) or another tab changed the storyboard: reload it.
        const p = await motionGraphicsApi.project(project.id).catch(() => null);
        set({ saving: false, dirty: false, saveError: 'The storyboard changed elsewhere and was reloaded.' });
        if (p) set({ project: p, spec: clone(p.spec) });
        return;
      }
      set({ saving: false, saveError: getErrorMessage(err, 'Could not save the storyboard') });
    }
  },

  refresh: async () => {
    const p = get().project;
    if (!p) return;
    try {
      get().setProject(await motionGraphicsApi.project(p.id));
    } catch {
      /* a failed background refresh keeps the current view */
    }
  },

  watchJob: (job) => {
    if (pollTimer) clearTimeout(pollTimer);
    const tick = async (j: Job) => {
      const project = get().project;
      if (!project || project.id !== j.project_id) return;
      set({ project: { ...project, active_job: ACTIVE_JOB.includes(j.status) ? j : null } });
      if (!ACTIVE_JOB.includes(j.status)) {
        await get().refresh();
        return;
      }
      pollTimer = setTimeout(async () => {
        try {
          await tick(await motionGraphicsApi.job(j.id));
        } catch {
          pollTimer = setTimeout(() => void tick(j), POLL_MS * 2);
        }
      }, POLL_MS);
    };
    void tick(job);
  },
}));
