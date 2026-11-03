import { create } from 'zustand';
import {
  storyRoomApi,
  errorStatus,
  isAbort,
  isGatewayTimeout,
  KEYFRAME_MODEL,
  KEYFRAME_RESOLUTION,
  type ImageSource,
  type KeyframeResult,
  type StoryDoc,
  type StoryEnvironment,
  type StoryFormat,
  type StoryRoomConfig,
  type StoryThread,
  type StoryVersioned,
  type ThreadSummary,
  type TurnResult,
} from '@/api/storyRoom';
import { generateApi } from '@/api/generate';
import type { GeneratedImage } from '@/types';
import { editKey, usePricingStore, STORY_CHAT_TURN_KEY } from '@/stores/pricingStore';
import { getErrorMessage } from '@/utils/errors';

// Why the last chat turn did not go through. 'pending' means the turn is still
// running on the server.
export type TurnErrorKind = 'busy' | 'pending' | 'general';
export interface TurnError {
  kind: TurnErrorKind;
  message: string;
}

// Reference images generated for one character or environment, waiting for
// the user to approve one. Keyed by `${threadId}:${castKey}`.
export interface CastDraft {
  images: GeneratedImage[];
  generating: boolean;
  error: string | null;
}

export const castDraftKey = (threadId: number, key: string) => `${threadId}:${key}`;

// A "Make keyframe" request for one shot. Keyed by `${threadId}:${shotId}`.
// `notice` is set when the proxy gave up but the server is still making it.
export interface KeyframeJob {
  generating: boolean;
  error: string | null;
  notice: string | null;
}

export const keyframeJobKey = (threadId: number, shotId: string) => `${threadId}:${shotId}`;

interface StoryRoomState {
  config: StoryRoomConfig | null;

  threads: ThreadSummary[];
  threadsLoading: boolean;
  threadsError: string | null;
  query: string;
  showArchived: boolean;

  thread: StoryThread | null;
  threadLoading: boolean;
  threadError: string | null;

  // Chat turn in flight, and the message shown while it runs.
  sending: boolean;
  pendingText: string | null;
  // The director's reply as it streams in (null when no reply is streaming),
  // and the status line shown once the reply is written.
  streamText: string | null;
  streamStatus: string | null;
  turnError: TurnError | null;
  composer: string;

  // Hand edits to the document: saved one at a time with expected_version.
  saving: boolean;
  dirty: boolean;
  saveError: string | null;
  saveNotice: string | null;

  environments: StoryEnvironment[];
  environmentsLoaded: boolean;

  castDrafts: Record<string, CastDraft>;
  keyframeJobs: Record<string, KeyframeJob>;

  loadConfig: () => Promise<StoryRoomConfig | null>;
  pricePerTurn: () => number | undefined;
  setQuery: (q: string) => void;
  setShowArchived: (v: boolean) => void;
  loadThreads: () => Promise<void>;
  openThread: (id: number) => Promise<void>;
  refreshThread: () => Promise<void>;
  closeThread: () => void;
  createThread: (format: StoryFormat) => Promise<StoryThread>;
  renameThread: (title: string) => Promise<void>;
  archiveThread: (id: number, archived: boolean) => Promise<void>;
  deleteThread: (id: number) => Promise<void>;

  setComposer: (text: string) => void;
  sendMessage: (text: string) => Promise<boolean>;
  // Stop showing the streamed reply. The server still finishes and saves it.
  stopTurn: () => void;
  clearTurnError: () => void;

  // Apply a hand edit locally and queue its save.
  editStory: (mutate: (doc: StoryDoc) => StoryDoc) => void;
  flushSave: () => Promise<void>;
  retrySave: () => void;
  dismissSaveNotice: () => void;

  restoreVersion: (messageId: number) => Promise<void>;
  saveCast: (key: string) => Promise<void>;
  linkCast: (key: string, refId: number) => Promise<void>;
  // Characters (c1), environments (e1) and products (p1; My Assets photos only).
  approveCastImage: (key: string, source: ImageSource) => Promise<void>;
  clearCastImage: (key: string) => Promise<void>;
  approveKeyframe: (shotId: string, source: ImageSource) => Promise<void>;
  clearKeyframe: (shotId: string) => Promise<void>;
  generateCastImages: (key: string, req: { prompt: string; model: string; aspectRatio: string }) => Promise<void>;
  // USD for one keyframe, as /config reports it (else the pricing table).
  keyframePrice: () => number | undefined;
  // "Make keyframe" for one shot; true when the keyframe arrived.
  generateKeyframe: (shotId: string) => Promise<boolean>;

  loadEnvironments: (force?: boolean) => Promise<void>;
  upsertEnvironment: (env: StoryEnvironment) => void;
}

// Images per "Generate image": two options to choose from, at 1K.
export const CAST_IMAGE_COUNT = 2;
export const CAST_IMAGE_RESOLUTION = '1k';

const EMPTY_KEYFRAME_JOB: KeyframeJob = { generating: false, error: null, notice: null };
// After a proxy timeout, look for the keyframe the server is still making.
const KEYFRAME_RECHECK_MS = 45000;

let saveRun: Promise<void> | null = null;
// The streamed turn being read, so Stop (or opening another story) can let go of it.
let turnAbort: AbortController | null = null;

const STOPPED_NOTICE =
  'You stopped the live reply. The director is still finishing it, and it will appear here when it is ready.';

const detachTurn = () => {
  turnAbort?.abort();
  turnAbort = null;
};

export const useStoryRoomStore = create<StoryRoomState>((set, get) => {
  // Replace the open thread's document after a server-side change. A reply
  // that does not report the version means the thread is reloaded instead.
  const applyVersioned = async (threadId: number, result: StoryVersioned) => {
    const t = get().thread;
    if (!t || t.id !== threadId) return;
    if (result.storyVersion === null) {
      await get().refreshThread();
      return;
    }
    set({ thread: { ...t, story: result.story, storyVersion: result.storyVersion } });
  };

  // A finished turn: the saved messages, the new document and the title the
  // director may have given an untitled story, in the open thread and the list.
  const applyTurn = (threadId: number, r: TurnResult) => {
    const t = get().thread;
    const title = r.title || t?.title || '';
    if (t && t.id === threadId) {
      set({
        thread: {
          ...t,
          title,
          story: r.story,
          storyVersion: r.storyVersion,
          busy: false,
          turnsUsed: t.turnsUsed + 1,
          estimatedUsd: t.estimatedUsd + r.estimatedUsd,
          messages: [...t.messages, r.userMessage, r.assistantMessage],
        },
      });
    }
    const scenes = r.story?.scenes ?? [];
    set((s) => ({
      threads: s.threads.map((x) =>
        x.id === threadId
          ? {
              ...x,
              title: r.title || x.title,
              busy: false,
              updatedAt: new Date().toISOString(),
              scenes: scenes.length,
              shots: scenes.reduce((n, sc) => n + sc.shots.length, 0),
            }
          : x,
      ),
    }));
  };

  // A keyframe arrived. With hand edits still waiting to be saved, those are
  // kept and only the shot's keyframe is taken from the server (it owns it).
  const applyKeyframe = async (threadId: number, shotId: string, result: KeyframeResult) => {
    const t = get().thread;
    if (!t || t.id !== threadId) return;
    if (result.storyVersion === null) {
      await get().refreshThread();
      return;
    }
    if (!get().dirty && !get().saving) {
      set({ thread: { ...t, story: result.story, storyVersion: result.storyVersion } });
      return;
    }
    const made = result.story.scenes.flatMap((s) => s.shots).find((s) => s.id === shotId);
    if (!made) return;
    set({
      thread: {
        ...t,
        storyVersion: Math.max(t.storyVersion, result.storyVersion),
        story: {
          ...t.story,
          scenes: t.story.scenes.map((sc) => ({
            ...sc,
            shots: sc.shots.map((sh) =>
              sh.id === shotId ? { ...sh, keyframe_url: made.keyframe_url, keyframe_approved: made.keyframe_approved } : sh,
            ),
          })),
        },
      },
    });
  };

  // Server-side edits (restore, library, images) start from the stored
  // document, so pending hand edits are saved first.
  const serverEdit = async (run: (threadId: number) => Promise<StoryVersioned>) => {
    await get().flushSave();
    const t = get().thread;
    if (!t) return;
    const result = await run(t.id);
    await applyVersioned(t.id, result);
  };

  const runSaves = async () => {
    while (get().dirty && get().thread) {
      const t = get().thread!;
      set({ dirty: false, saving: true, saveError: null });
      try {
        const result = await storyRoomApi.saveStory(t.id, t.story, t.storyVersion);
        const now = get().thread;
        if (!now || now.id !== t.id) break;
        if (result.storyVersion === null) {
          if (!get().dirty) await get().refreshThread();
        } else {
          // Keep newer local edits; otherwise take the server's normalised copy.
          set({ thread: { ...now, storyVersion: result.storyVersion, story: get().dirty ? now.story : result.story } });
        }
      } catch (err) {
        if (errorStatus(err) === 409) {
          set({
            dirty: false,
            saveNotice: 'This story changed in another reply or tab, so the latest version was loaded. Make your edit again if it is missing.',
          });
          await get().refreshThread();
        } else {
          set({ saveError: getErrorMessage(err, 'Your change could not be saved. Please try again.') });
        }
        break;
      } finally {
        set({ saving: false });
      }
    }
  };

  return {
    config: null,
    threads: [],
    threadsLoading: false,
    threadsError: null,
    query: '',
    showArchived: false,
    thread: null,
    threadLoading: false,
    threadError: null,
    sending: false,
    pendingText: null,
    streamText: null,
    streamStatus: null,
    turnError: null,
    composer: '',
    saving: false,
    dirty: false,
    saveError: null,
    saveNotice: null,
    environments: [],
    environmentsLoaded: false,
    castDrafts: {},
    keyframeJobs: {},

    loadConfig: async () => {
      try {
        const config = await storyRoomApi.config();
        set({ config });
        return config;
      } catch {
        // The price falls back to the model pricing table.
        return null;
      }
    },

    pricePerTurn: () => get().config?.pricePerTurn ?? usePricingStore.getState().getModelCost(STORY_CHAT_TURN_KEY),

    setQuery: (query) => set({ query }),
    setShowArchived: (showArchived) => {
      set({ showArchived });
      get().loadThreads();
    },

    loadThreads: async () => {
      const { query, showArchived } = get();
      set({ threadsLoading: true, threadsError: null });
      try {
        const threads = await storyRoomApi.threads({ q: query.trim(), archived: showArchived });
        // A slower earlier search must not overwrite a newer one.
        if (get().query === query && get().showArchived === showArchived) set({ threads });
      } catch (err) {
        set({ threadsError: getErrorMessage(err, 'Your stories could not be loaded.') });
      } finally {
        set({ threadsLoading: false });
      }
    },

    openThread: async (id) => {
      if (get().thread?.id === id) return;
      detachTurn();
      await get().flushSave();
      set({
        threadLoading: true,
        threadError: null,
        thread: null,
        turnError: null,
        pendingText: null,
        streamText: null,
        streamStatus: null,
        saveError: null,
        saveNotice: null,
        composer: '',
      });
      try {
        const thread = await storyRoomApi.thread(id);
        set({ thread });
      } catch (err) {
        set({ threadError: getErrorMessage(err, 'This story could not be opened.') });
      } finally {
        set({ threadLoading: false });
      }
    },

    refreshThread: async () => {
      const t = get().thread;
      if (!t) return;
      try {
        const fresh = await storyRoomApi.thread(t.id);
        if (get().thread?.id !== t.id) return;
        const finished = !fresh.busy;
        set((s) => ({
          thread: fresh,
          pendingText: finished && !s.sending ? null : s.pendingText,
          streamText: finished && !s.sending ? null : s.streamText,
          turnError: finished && s.turnError?.kind === 'pending' ? null : s.turnError,
        }));
        // Keep the list's busy flag and title in step.
        set((s) => ({
          threads: s.threads.map((x) => (x.id === fresh.id ? { ...x, busy: fresh.busy, title: fresh.title } : x)),
        }));
      } catch {
        // A failed background refresh keeps what is on screen.
      }
    },

    closeThread: () => {
      detachTurn();
      set({ thread: null, threadError: null, turnError: null, pendingText: null, streamText: null, streamStatus: null, composer: '' });
    },

    createThread: async (format) => {
      await get().flushSave();
      const thread = await storyRoomApi.createThread({ format });
      detachTurn();
      set((s) => ({
        thread,
        threadError: null,
        turnError: null,
        pendingText: null,
        streamText: null,
        streamStatus: null,
        composer: '',
        saveError: null,
        saveNotice: null,
        threads: [
          {
            id: thread.id,
            title: thread.title,
            format: thread.format,
            updatedAt: new Date().toISOString(),
            scenes: 0,
            shots: 0,
            busy: false,
          },
          ...s.threads.filter((x) => x.id !== thread.id),
        ],
      }));
      return thread;
    },

    renameThread: async (title) => {
      const t = get().thread;
      if (!t || title === t.title) return;
      await storyRoomApi.updateThread(t.id, { title });
      set((s) => ({
        thread: s.thread && s.thread.id === t.id ? { ...s.thread, title } : s.thread,
        threads: s.threads.map((x) => (x.id === t.id ? { ...x, title } : x)),
      }));
    },

    archiveThread: async (id, archived) => {
      await storyRoomApi.updateThread(id, { isArchived: archived });
      // It moves to the other list.
      set((s) => ({ threads: s.threads.filter((x) => x.id !== id) }));
    },

    deleteThread: async (id) => {
      await storyRoomApi.deleteThread(id);
      set((s) => ({
        threads: s.threads.filter((x) => x.id !== id),
        thread: s.thread?.id === id ? null : s.thread,
      }));
    },

    setComposer: (composer) => set({ composer }),
    clearTurnError: () => set({ turnError: null }),
    stopTurn: () => detachTurn(),

    sendMessage: async (text) => {
      const message = text.trim();
      const start = get().thread;
      if (!start || !message || get().sending) return false;
      set({ sending: true, pendingText: message, streamText: '', streamStatus: null, turnError: null, composer: '' });
      await get().flushSave();
      const threadId = start.id;
      const abort = new AbortController();
      detachTurn();
      turnAbort = abort;
      // Stream events only touch the screen while this turn's story is open.
      const mine = () => turnAbort === abort && get().thread?.id === threadId;
      try {
        const r = await storyRoomApi.streamTurn(
          threadId,
          { message },
          {
            onDelta: (text) => {
              if (mine()) set((s) => ({ streamText: (s.streamText ?? '') + text }));
            },
            onStatus: (text) => {
              if (mine()) set({ streamStatus: text });
            },
            onReplace: (text) => {
              if (mine()) set({ streamText: text });
            },
          },
          abort.signal,
        );
        if (turnAbort === abort) turnAbort = null;
        applyTurn(threadId, r);
        set({ sending: false, pendingText: null, streamText: null, streamStatus: null });
        // Pick up the server's order and counts.
        get().loadThreads();
        return true;
      } catch (err) {
        if (turnAbort === abort) turnAbort = null;
        if (isAbort(err)) {
          // Stopped, or another story was opened: the server still finishes
          // and saves this turn, and the busy thread is polled until it lands.
          set((s) => {
            if (s.thread?.id !== threadId) return { sending: false };
            return {
              sending: false,
              streamText: null,
              streamStatus: null,
              turnError: { kind: 'pending', message: STOPPED_NOTICE },
              thread: { ...s.thread, busy: true },
            };
          });
          return true;
        }
        set({ streamText: null, streamStatus: null });
        const status = errorStatus(err);
        if (isGatewayTimeout(err)) {
          // The turn keeps running on the server; sending again would run it twice.
          set((s) => ({
            sending: false,
            turnError: {
              kind: 'pending',
              message: 'The director is taking longer than usual. The reply will appear here when it is ready, so there is no need to send again.',
            },
            thread: s.thread && s.thread.id === threadId ? { ...s.thread, busy: true } : s.thread,
          }));
          return true;
        }
        set({ sending: false, pendingText: null, composer: message });
        if (status === 409) {
          set({
            turnError: {
              kind: 'busy',
              message: getErrorMessage(err, 'The director is still working on the previous reply. Your message is kept; send it again when the reply arrives.'),
            },
          });
          await get().refreshThread();
        } else {
          set({ turnError: { kind: 'general', message: getErrorMessage(err, 'The director could not reply. Please try again.') } });
        }
        return false;
      }
    },

    editStory: (mutate) => {
      const t = get().thread;
      if (!t) return;
      set({ thread: { ...t, story: mutate(t.story) }, dirty: true, saveNotice: null });
      get().flushSave();
    },

    flushSave: () => {
      if (!saveRun) {
        saveRun = runSaves().finally(() => {
          saveRun = null;
        });
      }
      return saveRun;
    },

    retrySave: () => {
      set({ dirty: true, saveError: null });
      get().flushSave();
    },

    dismissSaveNotice: () => set({ saveNotice: null }),

    restoreVersion: (messageId) => serverEdit((id) => storyRoomApi.restore(id, messageId)),
    saveCast: (key) => serverEdit((id) => storyRoomApi.saveCast(id, key)).then(() => get().loadEnvironments(true)),
    linkCast: (key, refId) => serverEdit((id) => storyRoomApi.linkCast(id, key, refId)),
    approveCastImage: (key, source) => serverEdit((id) => storyRoomApi.approveCastImage(id, key, source)),
    clearCastImage: (key) => serverEdit((id) => storyRoomApi.clearCastImage(id, key)),
    approveKeyframe: (shotId, source) => serverEdit((id) => storyRoomApi.approveKeyframe(id, shotId, source)),
    clearKeyframe: (shotId) => serverEdit((id) => storyRoomApi.clearKeyframe(id, shotId)),

    generateCastImages: async (key, req) => {
      const t = get().thread;
      if (!t) return;
      const draftKey = castDraftKey(t.id, key);
      const update = (patch: Partial<CastDraft>) =>
        set((s) => ({
          castDrafts: {
            ...s.castDrafts,
            [draftKey]: { ...(s.castDrafts[draftKey] ?? { images: [], generating: false, error: null }), ...patch },
          },
        }));
      update({ generating: true, error: null });
      try {
        const images = await generateApi.generateImage({
          prompt: req.prompt,
          model: req.model,
          aspectRatio: req.aspectRatio,
          resolution: CAST_IMAGE_RESOLUTION,
          numImages: CAST_IMAGE_COUNT,
        });
        update({ generating: false, images });
      } catch (err) {
        update({ generating: false, error: getErrorMessage(err, 'The image could not be generated. Please try again.') });
      }
    },

    keyframePrice: () => {
      const keyframe = get().config?.keyframe;
      return keyframe?.price ?? usePricingStore.getState().getModelCost(
        editKey(keyframe?.model ?? KEYFRAME_MODEL, keyframe?.resolution ?? KEYFRAME_RESOLUTION),
      );
    },

    generateKeyframe: async (shotId) => {
      const t = get().thread;
      if (!t) return false;
      const threadId = t.id;
      const jobKey = keyframeJobKey(threadId, shotId);
      if (get().keyframeJobs[jobKey]?.generating) return false;
      const update = (patch: Partial<KeyframeJob>) =>
        set((s) => ({
          keyframeJobs: { ...s.keyframeJobs, [jobKey]: { ...(s.keyframeJobs[jobKey] ?? EMPTY_KEYFRAME_JOB), ...patch } },
        }));
      update({ generating: true, error: null, notice: null });
      try {
        // The server writes the prompt from the stored document.
        await get().flushSave();
        const result = await storyRoomApi.generateKeyframe(threadId, shotId);
        await applyKeyframe(threadId, shotId, result);
        update({ generating: false });
        return true;
      } catch (err) {
        if (isGatewayTimeout(err)) {
          // The server is still making it and saves it on the shot; asking
          // again would pay for a second one.
          update({
            generating: false,
            notice: 'This keyframe is taking longer than usual. It will appear on the shot when it is ready, so there is no need to make another.',
          });
          setTimeout(() => {
            if (get().thread?.id === threadId) get().refreshThread();
          }, KEYFRAME_RECHECK_MS);
          return false;
        }
        update({ generating: false, error: getErrorMessage(err, 'The keyframe could not be made. Please try again.') });
        return false;
      }
    },

    loadEnvironments: async (force = false) => {
      if (get().environmentsLoaded && !force) return;
      try {
        const environments = await storyRoomApi.environments();
        set({ environments, environmentsLoaded: true });
      } catch {
        set({ environmentsLoaded: true });
      }
    },

    upsertEnvironment: (env) =>
      set((s) => ({
        environments: s.environments.some((e) => e.id === env.id)
          ? s.environments.map((e) => (e.id === env.id ? env : e))
          : [env, ...s.environments],
      })),
  };
});
