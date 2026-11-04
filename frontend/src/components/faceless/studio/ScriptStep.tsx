import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, FileText, History, Loader2, Plus, RotateCcw, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/dateUtils';
import { friendlyError, getErrorMessage } from '@/utils/errors';
import {
  estimateSeconds,
  facelessApi,
  isStepRun,
  newIdempotencyKey,
  scriptWords,
  type FacelessCharacter,
  type FacelessProject,
  type Scene,
  type Script,
  type StepRun,
} from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { EmptyState, ErrorNote, Kicker, MutedChip, formatDuration } from '../shared';
import { SceneEditor } from './SceneEditor';
import { activeRun, lastRun } from './stepState';
import { ScriptChecks } from './ScriptChecks';
import { Elapsed } from './RunsStrip';

function nextSceneId(scenes: Scene[]): string {
  const nums = scenes.map((s) => Number(String(s.id).replace(/\D/g, '')) || 0);
  return `s${Math.max(0, ...nums) + 1}`;
}

function reindex(scenes: Scene[]): Scene[] {
  return scenes.map((s, i) => ({ ...s, index: i }));
}

export function ScriptStep({
  project,
  runs,
  autoDraft,
  onNext,
}: {
  project: FacelessProject;
  runs: StepRun[];
  autoDraft?: boolean;
  onNext: () => void;
}) {
  const { setProject, refreshProject, characters } = useFacelessStore();
  const [draft, setDraft] = useState<Script | null>(project.script);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [redraftOpen, setRedraftOpen] = useState(false);
  const [idea, setIdea] = useState(project.idea ?? '');
  const [revising, setRevising] = useState<Scene | null>(null);
  const [instruction, setInstruction] = useState('');
  const [versions, setVersions] = useState<{ version: number; source: string; created_at: string; title: string | null }[] | null>(null);
  const autoRan = useRef(false);

  // Take the server's script whenever a new version lands and nothing local is pending.
  useEffect(() => {
    if (!dirty) setDraft(project.script);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.script_version, project.script]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const cast = useMemo(
    () =>
      project.cast_ids
        .map((id) => characters.find((c) => c.id === id))
        .filter((c): c is FacelessCharacter => !!c),
    [project.cast_ids, characters],
  );

  const draftRun = activeRun(project, 'script');
  const lastDraft = lastRun(runs, 'script');
  const draftFailed =
    !draftRun && lastDraft && (lastDraft.status === 'failed' || lastDraft.status === 'cancelled')
      ? friendlyError(lastDraft.items[0]?.error || lastDraft.error, 'The draft failed.')
      : null;

  const runDraft = async (newIdea?: string) => {
    setBusy('Drafting the script');
    setError(null);
    try {
      const res = await facelessApi.draftScript(project.id, {
        idea: newIdea,
        idempotency_key: newIdempotencyKey(`script-${project.id}`),
      });
      if (isStepRun(res)) {
        // Long-form: queued for the scheduler; polling brings the script in.
        await refreshProject();
      } else {
        setDirty(false);
        setDraft(res.script);
        setProject(res);
      }
      setRedraftOpen(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not draft the script'));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (autoDraft && !project.script && !autoRan.current) {
      autoRan.current = true;
      runDraft();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoDraft, project.script]);

  const edit = (next: Script) => {
    setDraft(next);
    setDirty(true);
  };

  const updateScene = (i: number, s: Scene) => {
    if (!draft) return;
    const scenes = [...draft.scenes];
    scenes[i] = s;
    edit({ ...draft, scenes });
  };

  const moveScene = (i: number, dir: -1 | 1) => {
    if (!draft) return;
    const j = i + dir;
    if (j < 0 || j >= draft.scenes.length) return;
    const scenes = [...draft.scenes];
    [scenes[i], scenes[j]] = [scenes[j], scenes[i]];
    edit({ ...draft, scenes: reindex(scenes) });
  };

  const addScene = () => {
    if (!draft) return;
    const last = draft.scenes[draft.scenes.length - 1];
    const scene: Scene = {
      ...(last ?? ({} as Scene)),
      id: nextSceneId(draft.scenes),
      index: draft.scenes.length,
      narration: '',
      narration_emotion: null,
      dialogue: [],
      on_screen_text: null,
      stat: null,
      sources: [],
      questions: [],
      is_hook: false,
      is_rehook: false,
      notes: '',
      shot: { ...(last?.shot ?? { kind: 'still', camera: 'medium', characters: [], images: 1, clip_seconds: null, motion: 'push_in' }), direction: '', visual_prompt: '' },
    };
    edit({ ...draft, scenes: [...draft.scenes, scene] });
  };

  const save = async () => {
    if (!draft) return;
    setBusy('Saving');
    setError(null);
    try {
      const words = scriptWords(draft);
      const p = await facelessApi.saveScript(project.id, {
        ...draft,
        scenes: reindex(draft.scenes),
        word_count: words,
        estimated_seconds: Math.round(estimateSeconds(words, draft.wpm || 165) * 10) / 10,
      });
      setDirty(false);
      setDraft(p.script);
      setProject(p);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the script'));
    } finally {
      setBusy(null);
    }
  };

  const discard = () => {
    setDraft(project.script);
    setDirty(false);
  };

  const revise = async () => {
    if (!revising || !instruction.trim()) return;
    setBusy('Revising the scene');
    setError(null);
    try {
      const p = await facelessApi.reviseScene(project.id, revising.id, instruction.trim());
      setDraft(p.script);
      setProject(p);
      setRevising(null);
      setInstruction('');
    } catch (err) {
      setError(getErrorMessage(err, 'Could not revise the scene'));
    } finally {
      setBusy(null);
    }
  };

  const loadVersions = async () => {
    try {
      setVersions((await facelessApi.scriptVersions(project.id)).versions);
    } catch {
      setVersions([]);
    }
  };

  const restore = async (version: number) => {
    setBusy(`Restoring version ${version}`);
    try {
      const p = await facelessApi.restoreVersion(project.id, version);
      setDirty(false);
      setDraft(p.script);
      setProject(p);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not restore that version'));
    } finally {
      setBusy(null);
    }
  };

  if (!draft) {
    return (
      <div className="space-y-4">
        {busy || draftRun ? (
          <div className="beam-border panel flex flex-col items-center rounded-xl px-6 py-16 text-center" aria-live="polite">
            <FileText className="mb-3 h-6 w-6 text-muted-foreground" aria-hidden="true" />
            <p className="text-base font-semibold">
              {draftRun ? `Writing the script, ${draftRun.progress}%` : 'Writing the script'}
            </p>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Hook, beats, re-hooks and the ending, timed to {formatDuration(project.length_seconds)}.
              {draftRun
                ? ' Long scripts are written outline first, then in chunks; you can leave this page and come back.'
                : ' This takes up to a minute.'}
            </p>
            {draftRun && <Elapsed since={draftRun.started_at ?? draftRun.created_at} className="mt-2 font-mono text-xs tabular text-muted-foreground" />}
            <div className="mt-6 w-full max-w-md space-y-2">
              <div className="shimmer h-4 rounded" />
              <div className="shimmer h-4 w-4/5 rounded" />
              <div className="shimmer h-4 w-3/5 rounded" />
            </div>
          </div>
        ) : (
          <EmptyState
            icon={FileText}
            title="No script yet"
            action={
              <Button onClick={() => runDraft()}>
                <FileText className="h-4 w-4" /> Draft the script
              </Button>
            }
          >
            The studio writes scene by scene from your idea, template and cast. You edit everything before any paid step runs.
          </EmptyState>
        )}
        <ErrorNote>{error || (busy || draftRun ? null : draftFailed)}</ErrorNote>
      </div>
    );
  }

  const words = scriptWords(draft);
  const wpm = draft.wpm || 165;
  const targetWords = draft.word_budget || Math.round((project.length_seconds * wpm) / 60);
  const est = estimateSeconds(words, wpm);
  const pct = targetWords > 0 ? Math.min(150, Math.round((words / targetWords) * 100)) : 0;
  const offTarget = pct < 85 || pct > 115;
  const flags = project.compliance?.flags ?? [];

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_300px]">
      <div className="min-w-0 space-y-4">
        {/* Toolbar */}
        <div className="panel sticky top-16 z-10 rounded-xl p-3 sm:p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-[180px] flex-1">
              <div className="flex items-baseline justify-between gap-2 font-mono text-[11px] tabular">
                <span className={cn(offTarget ? 'text-warning' : 'text-muted-foreground')}>
                  {words} / {targetWords} words
                </span>
                <span className="text-muted-foreground">
                  about {formatDuration(est)} of {formatDuration(project.length_seconds)}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary" role="meter" aria-valuemin={0} aria-valuemax={150} aria-valuenow={pct} aria-label="Script length against target">
                <div className={cn('h-full rounded-full transition-[width] duration-200', offTarget ? 'bg-warning' : 'bg-primary')} style={{ width: `${(pct / 150) * 100}%` }} />
              </div>
            </div>
            {dirty && <MutedChip className="border-warning/40 text-warning">Unsaved</MutedChip>}
            <DropdownMenu onOpenChange={(o) => o && loadVersions()}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" disabled={!!busy}>
                  <History className="h-3.5 w-3.5" /> v{project.script_version}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
                <DropdownMenuLabel>Versions</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {versions === null ? (
                  <DropdownMenuItem disabled>Loading</DropdownMenuItem>
                ) : (
                  versions.map((v) => (
                    <DropdownMenuItem key={v.version} disabled={v.version === project.script_version} onSelect={() => restore(v.version)}>
                      <span className="font-mono text-xs">v{v.version}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {v.source}, {formatRelativeTime(v.created_at)}
                      </span>
                    </DropdownMenuItem>
                  ))
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setError(null);
                setRedraftOpen(true);
              }}
              disabled={!!busy || !!draftRun}
            >
              <RotateCcw className="h-3.5 w-3.5" /> Re-draft
            </Button>
            {dirty && (
              <Button variant="ghost" size="sm" onClick={discard} disabled={!!busy}>
                Discard
              </Button>
            )}
            <Button size="sm" onClick={save} disabled={!dirty || !!busy}>
              {busy === 'Saving' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {busy === 'Saving' ? 'Saving' : 'Save'}
            </Button>
          </div>
          {draftRun && (
            <p className="mt-2 text-xs text-muted-foreground" aria-live="polite">
              A new draft is being written, <span className="font-mono tabular">{draftRun.progress}%</span>. It becomes the next version.
            </p>
          )}
          {busy && busy !== 'Saving' && (
            <p className="mt-2 text-xs text-muted-foreground" aria-live="polite">
              {busy}
            </p>
          )}
          {/* In the sticky bar: Save can be pressed far down a long script. */}
          {error && !redraftOpen && !revising && (
            <div className="mt-2">
              <ErrorNote>{error}</ErrorNote>
            </div>
          )}
        </div>

        {(draft.needs_facts || draft.warnings.length > 0) && (
          <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
            {draft.needs_facts && <p>Fact mode without enough facts: the script asks questions instead of making claims. Add facts and re-draft.</p>}
            {draft.warnings.length > 0 && (
              <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs">
                {draft.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="rounded-xl border border-border bg-secondary/20 p-4">
          <Kicker>Title</Kicker>
          <p className="mt-1 text-lg font-semibold tracking-tight">{draft.title || project.title}</p>
          {draft.logline && <p className="mt-1 text-sm text-muted-foreground">{draft.logline}</p>}
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {draft.hook_formula && <span>Hook: {draft.hook_formula}</span>}
            {draft.outro_title && <span>Outro: {draft.outro_title}</span>}
            {draft.dramatization_label && <span>Label: {draft.dramatization_label}</span>}
          </div>
        </div>

        <ol className="space-y-4" aria-label="Scenes">
          {draft.scenes.map((scene, i) => (
            <li key={scene.id}>
              <SceneEditor
                scene={scene}
                position={i}
                total={draft.scenes.length}
                cast={cast}
                wpm={wpm}
                flags={flags.filter((f) => f.scene_id === scene.id)}
                reviseDisabled={dirty ? 'Save your edits first' : busy ? 'Busy' : undefined}
                onChange={(s) => updateScene(i, s)}
                onMove={(dir) => moveScene(i, dir)}
                onDelete={() => edit({ ...draft, scenes: reindex(draft.scenes.filter((_, idx) => idx !== i)) })}
                onRevise={() => {
                  setError(null);
                  setRevising(scene);
                  setInstruction('');
                }}
              />
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="outline" onClick={addScene} disabled={!!busy}>
            <Plus className="h-4 w-4" /> Add scene
          </Button>
          <Button onClick={onNext} disabled={dirty}>
            Storyboard <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
        <ScriptChecks project={project} />
      </aside>

      <Dialog
        open={redraftOpen}
        onOpenChange={(o) => {
          if (busy) return;
          setRedraftOpen(o);
          if (!o) setError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Re-draft the script</DialogTitle>
            <DialogDescription>
              A fresh draft replaces the current script as a new version. Older versions stay restorable.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={5} aria-label="Idea" value={idea} onChange={(e) => setIdea(e.target.value)} maxLength={8000} />
          <ErrorNote>{redraftOpen ? error : null}</ErrorNote>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              onClick={() => {
                setRedraftOpen(false);
                setError(null);
              }}
              disabled={!!busy}
            >
              Cancel
            </Button>
            <Button onClick={() => runDraft(idea.trim() || undefined)} disabled={!!busy}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? 'Drafting' : 'Draft again'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!revising}
        onOpenChange={(o) => {
          if (busy || o) return;
          setRevising(null);
          setError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Revise scene {revising ? draft.scenes.findIndex((s) => s.id === revising.id) + 1 : ''}
            </DialogTitle>
            <DialogDescription>Say what to change. The rest of the script stays as it is.</DialogDescription>
          </DialogHeader>
          {revising && <p className="rounded-lg border border-border bg-secondary/40 p-3 text-sm">{revising.narration}</p>}
          <Textarea
            rows={3}
            aria-label="Instruction"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            maxLength={2000}
            placeholder="Make the hook land harder and end on a question"
          />
          <ErrorNote>{revising ? error : null}</ErrorNote>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              onClick={() => {
                setRevising(null);
                setError(null);
              }}
              disabled={!!busy}
            >
              Cancel
            </Button>
            <Button onClick={revise} disabled={!!busy || !instruction.trim()}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? 'Revising' : 'Revise'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
