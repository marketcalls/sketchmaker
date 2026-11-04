import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { AlertOctagon, ArrowLeft, Check, Pencil, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { SEO } from '@/components/SEO';
import { getErrorMessage } from '@/utils/errors';
import { STUDIO_STEPS, facelessApi, type StudioStep } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { formatUsd } from '@/stores/pricingStore';
import { StepRail } from '@/components/faceless/studio/StepRail';
import { RunsStrip } from '@/components/faceless/studio/RunsStrip';
import { ScriptStep } from '@/components/faceless/studio/ScriptStep';
import { StoryboardStep } from '@/components/faceless/studio/StoryboardStep';
import { AnimateStep } from '@/components/faceless/studio/AnimateStep';
import { VoiceStep } from '@/components/faceless/studio/VoiceStep';
import { MusicStep } from '@/components/faceless/studio/MusicStep';
import { CaptionsStep } from '@/components/faceless/studio/CaptionsStep';
import { RenderStep } from '@/components/faceless/studio/RenderStep';
import { PackageStep } from '@/components/faceless/studio/PackageStep';
import { CatalogError } from '@/components/faceless/CatalogError';
import { AspectGlyph, ErrorNote, ProjectStatusBadge, formatDuration } from '@/components/faceless/shared';

const STEP_IDS = STUDIO_STEPS.map((s) => s.id);

export function FacelessStudioPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const [params, setParams] = useSearchParams();
  const {
    project, runs, projectLoading, projectError, pollStalled, templates,
    openProject, closeProject, refreshProject, setProject, loadCatalog, loadCharacters,
  } = useFacelessStore();
  const [editingTitle, setEditingTitle] = useState(false);
  const [title, setTitle] = useState('');
  const [titleError, setTitleError] = useState<string | null>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    loadCatalog();
    loadCharacters();
  }, [loadCatalog, loadCharacters]);

  useEffect(() => {
    if (Number.isFinite(projectId)) openProject(projectId);
    return () => closeProject();
  }, [projectId, openProject, closeProject]);

  // The active step lives in the URL so a reload returns to it.
  const raw = params.get('step') as StudioStep | null;
  const active: StudioStep = raw && STEP_IDS.includes(raw) ? raw : 'script';
  const setActive = (s: StudioStep) => {
    const next = new URLSearchParams(params);
    next.set('step', s);
    next.delete('draft');
    setParams(next, { replace: true });
    // Keep the user's place: only scroll when the new step's top would be out of view.
    requestAnimationFrame(() => {
      const el = panelRef.current;
      if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: 'start' });
    });
  };
  const autoDraft = params.get('draft') === '1';
  const hasScript = !!project?.script;
  useEffect(() => {
    if (autoDraft && hasScript) {
      const next = new URLSearchParams(params);
      next.delete('draft');
      setParams(next, { replace: true });
    }
  }, [autoDraft, hasScript, params, setParams]);

  const template = templates.find((t) => t.id === project?.template_id);
  const spent = Object.values(project?.usd_by_step ?? {}).reduce((n, v) => n + (Number(v) || 0), 0);
  const blocked = !!project?.compliance?.blocked;

  const saveTitle = async () => {
    if (!project) return;
    const t = title.trim();
    setEditingTitle(false);
    if (!t || t === project.title) return;
    try {
      setProject(await facelessApi.updateProject(project.id, { title: t }));
      setTitleError(null);
    } catch (err) {
      setTitleError(getErrorMessage(err, 'Could not rename the project'));
    }
  };

  if (!project) {
    return (
      <div className="w-full">
        <SEO title="Studio" noindex />
        {projectError ? (
          <div className="space-y-4">
            <ErrorNote>{projectError}</ErrorNote>
            <Button asChild variant="outline">
              <Link to="/faceless">
                <ArrowLeft className="h-4 w-4" /> Back to the studio
              </Link>
            </Button>
          </div>
        ) : (
          <div aria-busy={projectLoading} aria-label="Loading project">
            <div className="mb-6 space-y-2">
              <Skeleton className="h-8 w-72 max-w-full" />
              <Skeleton className="h-4 w-96 max-w-full" />
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[230px_1fr]">
              <div className="hidden space-y-1 lg:block">
                {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
              <Skeleton className="h-96 w-full rounded-xl" />
            </div>
          </div>
        )}
      </div>
    );
  }

  const panelProps = { project, runs };

  return (
    <>
      <SEO title={project.title || 'Studio'} url={`/faceless/projects/${project.id}`} noindex />
      <div className="w-full">
        {/* Header */}
        <header className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <Link to="/faceless" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
              <ArrowLeft className="h-3 w-3" /> Faceless Studio
            </Link>
            {editingTitle ? (
              <form
                className="flex items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  saveTitle();
                }}
              >
                <Input
                  autoFocus
                  aria-label="Project title"
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                  onBlur={saveTitle}
                  onKeyDown={(e) => e.key === 'Escape' && setEditingTitle(false)}
                  className="h-10 max-w-xl text-lg font-semibold"
                />
                <Button type="submit" size="icon" variant="outline" aria-label="Save title">
                  <Check className="h-4 w-4" />
                </Button>
              </form>
            ) : (
              <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
                <span className="truncate">{project.title || 'Untitled'}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => {
                    setTitle(project.title);
                    setEditingTitle(true);
                  }}
                  aria-label="Rename project"
                >
                  <Pencil className="h-4 w-4" />
                </Button>
              </h1>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <ProjectStatusBadge status={project.status} />
              <span>{template?.name ?? project.template_id}</span>
              <span className="inline-flex items-center gap-1">
                <AspectGlyph aspect={project.aspect} className="scale-75" /> <span className="font-mono tabular">{project.aspect}</span>
              </span>
              <span className="font-mono tabular">
                {formatDuration(project.total_seconds)} of {formatDuration(project.length_seconds)}
                {project.script && !project.timing_measured && ' est.'}
              </span>
              <span className="font-mono tabular">v{project.script_version}</span>
              {spent > 0 && <span><span className="font-mono tabular">{formatUsd(spent)}</span> estimated spend</span>}
            </div>
            {titleError && <p className="mt-1 text-xs text-destructive">{titleError}</p>}
          </div>
          <Button variant="outline" size="sm" onClick={() => refreshProject()} aria-label="Refresh project">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </header>

        {pollStalled && (
          <p role="status" className="mb-4 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
            Nothing has changed for a while. The step may still be running; refresh to check.
          </p>
        )}
        {blocked && (
          <p role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            A blocking compliance flag stops every paid step. Fix it in the script, then save.
          </p>
        )}

        <CatalogError className="mb-4" />

        <RunsStrip project={project} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[230px_1fr]">
          <nav aria-label="Studio steps" className="lg:sticky lg:top-20 lg:self-start">
            <StepRail project={project} runs={runs} active={active} onChange={setActive} />
          </nav>
          <section
            ref={panelRef}
            id={`studio-panel-${active}`}
            role="tabpanel"
            aria-labelledby={`studio-tab-${active}`}
            tabIndex={-1}
            className="min-w-0 scroll-mt-20 focus:outline-none"
          >
            {active === 'script' && <ScriptStep {...panelProps} autoDraft={autoDraft} onNext={() => setActive('storyboard')} />}
            {active === 'storyboard' && <StoryboardStep {...panelProps} />}
            {active === 'animate' && <AnimateStep {...panelProps} />}
            {active === 'voice' && <VoiceStep {...panelProps} />}
            {active === 'music' && <MusicStep {...panelProps} />}
            {active === 'captions' && <CaptionsStep {...panelProps} />}
            {active === 'render' && <RenderStep {...panelProps} onGoto={setActive} />}
            {active === 'package' && <PackageStep {...panelProps} />}
          </section>
        </div>
      </div>
    </>
  );
}
