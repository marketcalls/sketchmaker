import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, Palette } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { SEO } from '@/components/SEO';
import { getErrorMessage } from '@/utils/errors';
import { motionGraphicsApi, type JobKind, type MGAspect, type MGSpec, type SpecScene } from '@/api/motionGraphics';
import { useMotionGraphicsStore } from '@/stores/motionGraphicsStore';
import { SceneEditor } from '@/components/motion-graphics/SceneEditor';
import { PreviewStage, SceneRail, sceneDef } from '@/components/motion-graphics/Storyboard';
import { AudioPanel, DataPanel, StylePanel } from '@/components/motion-graphics/Panels';
import { QuoteDialog, RenderPanel } from '@/components/motion-graphics/RenderPanel';
import { BrandKitDialog } from '@/components/motion-graphics/BrandKitDialog';
import { ErrorNote, FieldLabel, MutedChip, SectionTitle, TechChip, formatSeconds } from '@/components/motion-graphics/shared';

function RewriteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const project = useMotionGraphicsStore((s) => s.project);
  const setProject = useMotionGraphicsStore((s) => s.setProject);
  const [brief, setBrief] = useState('');
  const [keep, setKeep] = useState(true);
  const [voiceover, setVoiceover] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && project) {
      setBrief(project.brief ?? '');
      setVoiceover(project.audio.voice.enabled);
      setError(null);
    }
  }, [open, project]);

  if (!project) return null;
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await motionGraphicsApi.draft(project.id, {
        brief,
        template_id: keep ? project.template_id : null,
        style_id: keep ? project.style_id : null,
        aspect: project.aspect,
        voiceover,
      });
      useMotionGraphicsStore.setState({ dirty: false });
      setProject(p);
      useMotionGraphicsStore.setState({ spec: JSON.parse(JSON.stringify(p.spec)) as MGSpec });
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'The AI writer could not draft this brief'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Rewrite with AI</DialogTitle>
          <DialogDescription>Replaces the storyboard text. Your data table, uploads and audio settings stay.</DialogDescription>
        </DialogHeader>
        <Textarea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={4000} placeholder="What should this video say?" />
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={keep} onCheckedChange={setKeep} /> Keep this template and style
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={voiceover} onCheckedChange={setVoiceover} /> Write a voiceover
        </label>
        {error && <ErrorNote>{error}</ErrorNote>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={run} disabled={busy || brief.trim().length < 3} className="min-w-28">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy ? 'Rewriting' : 'Rewrite'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MotionGraphicsStudioPage() {
  const { id } = useParams();
  const pid = Number(id);
  const {
    catalog,
    project,
    spec,
    dirty,
    saving,
    saveError,
    loadError,
    loadCatalog,
    openProject,
    closeProject,
    editSpec,
    setProject,
  } = useMotionGraphicsStore();
  const [selected, setSelected] = useState<string | null>(null);
  const [previewAspect, setPreviewAspect] = useState<MGAspect | null>(null);
  const [quoteKind, setQuoteKind] = useState<JobKind | null>(null);
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);
  const [tab, setTab] = useState('style');
  const [brandBusy, setBrandBusy] = useState(false);

  useEffect(() => {
    void loadCatalog();
    void openProject(pid);
    return () => closeProject();
  }, [pid, loadCatalog, openProject, closeProject]);

  const tpl = useMemo(() => catalog?.templates.find((t) => t.id === project?.template_id), [catalog, project?.template_id]);
  useEffect(() => {
    if (spec && (!selected || !spec.scenes.some((s) => s.id === selected))) setSelected(spec.scenes[0]?.id ?? null);
  }, [spec, selected]);
  useEffect(() => {
    if (project) setPreviewAspect((a) => (a && project.variants.concat(project.aspect).includes(a) ? a : project.aspect));
  }, [project]);

  if (loadError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <ErrorNote>{loadError}</ErrorNote>
        <Button asChild variant="outline" className="mt-4">
          <Link to="/motion-graphics">Back to Motion Graphics</Link>
        </Button>
      </div>
    );
  }
  if (!project || !spec || !catalog || !tpl) {
    return (
      <div className="w-full space-y-4">
        <div className="shimmer h-12 w-72 rounded-lg" />
        <div className="grid gap-4 lg:grid-cols-[260px_1fr_360px]">
          <div className="shimmer h-96 rounded-xl" />
          <div className="shimmer h-96 rounded-xl" />
          <div className="shimmer h-96 rounded-xl" />
        </div>
      </div>
    );
  }

  const scene = spec.scenes.find((s) => s.id === selected) ?? null;
  const def = scene ? sceneDef(tpl, scene.type) : undefined;
  const plan = project.plan;
  const planScene = plan?.scenes.find((s) => s.id === scene?.id);
  const issues = [...project.validation.errors, ...project.validation.warnings];
  const aspects = [project.aspect, ...project.variants.filter((a) => a !== project.aspect)];
  const allAspects = tpl.aspects;
  const setScene = (s: SpecScene) => editSpec((x) => ({ ...x, scenes: x.scenes.map((y) => (y.id === s.id ? s : y)) }));

  const applyBrand = async (on: boolean) => {
    setBrandBusy(true);
    try {
      setProject(await motionGraphicsApi.updateProject(project.id, { apply_brand: on }));
    } finally {
      setBrandBusy(false);
    }
  };

  return (
    <>
      <SEO title={`${project.title} | Motion Graphics`} description="Motion graphics storyboard" url={`/motion-graphics/${project.id}`} noindex />
      <div className="w-full">
        <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0 space-y-2">
            <Link
              to="/motion-graphics"
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Motion graphics
            </Link>
            <Input
              value={spec.title}
              onChange={(e) => editSpec((x) => ({ ...x, title: e.target.value.slice(0, 120) }))}
              className="h-auto border-transparent bg-transparent px-0 text-2xl font-semibold tracking-tight shadow-none focus-visible:border-border"
              aria-label="Project title"
            />
            <div className="flex flex-wrap items-center gap-2">
              <TechChip>{tpl.name}</TechChip>
              <MutedChip>{catalog.styles.find((s) => s.id === spec.style_id)?.name ?? spec.style_id}</MutedChip>
              {plan && <MutedChip>{formatSeconds(plan.total)}</MutedChip>}
              {plan?.beat_synced && <MutedChip>Beat synced</MutedChip>}
              <span className="flex items-center gap-1 text-xs text-muted-foreground" aria-live="polite">
                {saving ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Saving
                  </>
                ) : dirty ? (
                  'Unsaved'
                ) : (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-success" /> Saved
                  </>
                )}
              </span>
              {project.validation.errors.length > 0 && (
                <span className="text-xs text-destructive">
                  {project.validation.errors.length} to fix
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setRewriteOpen(true)}>
              Rewrite with AI
            </Button>
            {/* The render tab has its own primary button, so this one steps back while that tab is open. */}
            <Button variant={tab === 'render' ? 'outline' : 'default'} onClick={() => setTab('render')}>
              Render
            </Button>
          </div>
        </header>
        {saveError && (
          <div className="mb-4">
            <ErrorNote>{saveError}</ErrorNote>
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)] xl:grid-cols-[250px_minmax(0,1fr)_380px]">
          <aside className="order-2 lg:order-1">
            <SectionTitle>Storyboard</SectionTitle>
            <div className="lg:max-h-[calc(100vh-220px)] lg:overflow-y-auto lg:pr-1">
              <SceneRail
                projectId={project.id}
                spec={spec}
                tpl={tpl}
                plan={plan?.scenes ?? []}
                aspect={project.aspect}
                selected={selected}
                onSelect={setSelected}
                onSpec={editSpec}
                issues={project.validation.errors}
              />
            </div>
          </aside>

          <main className="order-1 min-w-0 space-y-5 lg:order-2">
            <PreviewStage
              projectId={project.id}
              spec={spec}
              scene={scene}
              planScene={planScene}
              aspects={allAspects}
              aspect={previewAspect ?? project.aspect}
              onAspect={setPreviewAspect}
            />
            {scene && def && (
              <div className="rounded-xl border border-border bg-card p-4 sm:p-5">
                <SectionTitle aside={planScene && <span className="font-mono text-[11px] tabular text-muted-foreground">starts {formatSeconds(planScene.start)}</span>}>
                  {def.label}
                </SectionTitle>
                <SceneEditor
                  scene={scene}
                  def={def}
                  onChange={setScene}
                  issues={issues.filter((i) => i.scene_id === scene.id)}
                  uploads={project.uploads}
                  projectId={project.id}
                  voiceOn={project.audio.voice.enabled}
                  plannedSeconds={planScene?.duration}
                />
              </div>
            )}
          </main>

          <aside className="order-3 lg:col-span-2 xl:col-span-1">
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="style">Style</TabsTrigger>
                <TabsTrigger value="data">Data</TabsTrigger>
                <TabsTrigger value="brand">Brand</TabsTrigger>
                <TabsTrigger value="audio">Audio</TabsTrigger>
                <TabsTrigger value="render">Render</TabsTrigger>
              </TabsList>
              <div className="mt-4 rounded-xl border border-border bg-card p-4">
                <TabsContent value="style" className="mt-0">
                  <StylePanel catalog={catalog} spec={spec} onSpec={editSpec} />
                </TabsContent>
                <TabsContent value="data" className="mt-0">
                  <DataPanel tpl={tpl} spec={spec} view={project.validation.data} onSpec={editSpec} />
                </TabsContent>
                <TabsContent value="brand" className="mt-0 space-y-4">
                  <SectionTitle>Brand kit</SectionTitle>
                  {project.brand ? (
                    <div className="space-y-3 rounded-lg border border-border p-3">
                      <div className="flex items-center gap-3">
                        {project.brand.logo_url && (
                          <img src={project.brand.logo_url} alt="Logo" className="h-10 max-w-[7rem] object-contain" />
                        )}
                        <p className="text-sm">{project.brand.name ?? 'Your brand'}</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5 font-mono text-[10px] text-muted-foreground">
                        {Object.entries(project.brand.palette).map(([k, v]) => (
                          <span key={k}>
                            {k} {v}
                          </span>
                        ))}
                        {project.brand.fonts.display && <span>Headings {project.brand.fonts.display}</span>}
                        <span>{project.brand.intensity}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No brand applied: the style's own palette and fonts are used.</p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => applyBrand(true)} disabled={brandBusy}>
                      <Palette className="h-4 w-4" /> {project.brand ? 'Re-apply brand kit' : 'Apply brand kit'}
                    </Button>
                    {project.brand && (
                      <Button size="sm" variant="outline" onClick={() => applyBrand(false)} disabled={brandBusy}>
                        Remove
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setBrandOpen(true)}>
                      Edit brand kit
                    </Button>
                  </div>
                  <div>
                    <FieldLabel hint="optional">Logo sting and end card</FieldLabel>
                    <p className="text-xs text-muted-foreground">
                      Add a Logo sting or End card scene from the storyboard's Add scene menu. Both use your brand logo.
                    </p>
                  </div>
                </TabsContent>
                <TabsContent value="audio" className="mt-0">
                  <AudioPanel catalog={catalog} project={project} spec={spec} onSpec={editSpec} onGenerate={() => setQuoteKind('audio')} />
                </TabsContent>
                <TabsContent value="render" className="mt-0">
                  <RenderPanel
                    catalog={catalog}
                    tpl={tpl}
                    project={project}
                    spec={spec}
                    onSpec={editSpec}
                    onRender={() => setQuoteKind('render')}
                  />
                </TabsContent>
              </div>
            </Tabs>
            {aspects.length > 1 && (
              <p className="mt-2 text-xs text-muted-foreground">Rendering {aspects.join(', ')} in one job.</p>
            )}
          </aside>
        </div>
      </div>

      <RewriteDialog open={rewriteOpen} onOpenChange={setRewriteOpen} />
      <BrandKitDialog open={brandOpen} onOpenChange={setBrandOpen} />
      {quoteKind && (
        <QuoteDialog
          open={!!quoteKind}
          onOpenChange={(o) => !o && setQuoteKind(null)}
          project={project}
          kind={quoteKind}
          onStarted={() => setTab(quoteKind === 'render' ? 'render' : 'audio')}
        />
      )}
    </>
  );
}
