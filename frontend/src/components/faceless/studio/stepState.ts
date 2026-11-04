import {
  PAID_TO_STUDIO,
  isRunActive,
  type FacelessProject,
  type PaidStep,
  type Scene,
  type SceneAssets,
  type StepRun,
  type StudioStep,
} from '@/api/faceless';
import type { AssetState, StepState } from '../shared';

export function assetsOf(project: FacelessProject, sceneId: string): SceneAssets | undefined {
  return project.scenes.find((s) => s.scene_id === sceneId);
}

export function hasStill(a: SceneAssets | undefined): boolean {
  return !!a?.stills.some((s) => s?.url);
}

export function hasClip(a: SceneAssets | undefined): boolean {
  return !!a?.clips.some((c) => c?.url);
}

export function voiceReady(a: SceneAssets | undefined): boolean {
  return !!a && a.voice.length > 0 && a.voice.every((v) => v.current && v.url);
}

// Scenes the storyboard step makes pictures for (cards and own media need none).
export function storyboardScenes(scenes: Scene[]): Scene[] {
  return scenes.filter((s) => s.shot.kind === 'still' || s.shot.kind === 'clip');
}

export function clipScenes(scenes: Scene[]): Scene[] {
  return scenes.filter((s) => s.shot.kind === 'clip');
}

export function activeRun(project: FacelessProject, step: PaidStep | 'script'): StepRun | undefined {
  return project.active_runs.find((r) => r.step === step && isRunActive(r));
}

export function lastRun(runs: StepRun[], step: PaidStep | 'script'): StepRun | undefined {
  return runs.find((r) => r.step === step);
}

// The run item working on (or last failed for) a scene in this step.
export function sceneRunState(
  project: FacelessProject,
  runs: StepRun[],
  step: PaidStep,
  sceneId: string,
): { running: boolean; failed: RunFailure | null } {
  const live = activeRun(project, step);
  const liveItems = live?.items.filter((i) => i.scene_id === sceneId) ?? [];
  const running = liveItems.some((i) => i.status === 'pending' || i.status === 'submitted');
  const last = runs.find((r) => r.step === step && !isRunActive(r) && r.items.some((i) => i.scene_id === sceneId));
  const item = last?.items.find((i) => i.scene_id === sceneId && i.status === 'failed');
  return {
    running,
    failed: item ? { error: item.error } : null,
  };
}

export interface RunFailure {
  error: string | null;
}

export function sceneAssetState(running: boolean, done: boolean, failed: boolean): AssetState {
  if (running) return 'running';
  if (done) return 'done';
  if (failed) return 'failed';
  return 'none';
}

function ratio(done: number, total: number): StepState {
  if (total === 0) return 'idle';
  if (done >= total) return 'done';
  return done > 0 ? 'partial' : 'idle';
}

// What the rail shows: the live run first, else derived from the assets so a
// reload shows the truth, with a failed last run when nothing came of it.
export function stepState(project: FacelessProject, runs: StepRun[], step: StudioStep): StepState {
  const paid = (Object.keys(PAID_TO_STUDIO) as PaidStep[]).find((p) => PAID_TO_STUDIO[p] === step);
  const live = step === 'script' ? activeRun(project, 'script') : paid ? activeRun(project, paid) : undefined;
  if (live) return live.status === 'queued' ? 'queued' : 'running';
  const scenes = project.script?.scenes ?? [];
  let derived: StepState = 'idle';
  switch (step) {
    case 'script':
      derived = scenes.length > 0 ? 'done' : 'idle';
      break;
    case 'storyboard': {
      const need = storyboardScenes(scenes);
      derived = ratio(need.filter((s) => hasStill(assetsOf(project, s.id))).length, need.length);
      break;
    }
    case 'animate': {
      const need = clipScenes(scenes);
      derived = ratio(need.filter((s) => hasClip(assetsOf(project, s.id))).length, need.length);
      break;
    }
    case 'voice': {
      const need = project.scenes.filter((a) => a.voice.length > 0);
      derived = ratio(need.filter(voiceReady).length, need.length);
      break;
    }
    case 'music':
      derived = project.music?.tracks.some((t) => t.url) ? 'done' : 'idle';
      break;
    case 'captions':
      derived = project.caption_preset && project.caption_preset !== 'none' ? 'done' : 'idle';
      break;
    case 'render':
      derived = project.render?.url ? 'done' : 'idle';
      break;
    case 'package':
      derived = project.packaging?.titles?.length ? 'done' : 'idle';
      break;
  }
  if ((paid || step === 'script') && derived !== 'done') {
    const last = lastRun(runs, paid ?? 'script');
    if (last && (last.status === 'failed' || last.status === 'partial')) return derived === 'idle' ? 'failed' : 'partial';
  }
  return derived;
}

export function stepProgress(project: FacelessProject, step: StudioStep): number {
  const paid = (Object.keys(PAID_TO_STUDIO) as PaidStep[]).find((p) => PAID_TO_STUDIO[p] === step);
  if (step === 'script') return activeRun(project, 'script')?.progress ?? 0;
  return paid ? activeRun(project, paid)?.progress ?? 0 : 0;
}
