import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { ChevronDown, Loader2, Palette, Trash2, Type } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { studioEase } from '@/components/motion';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { SEO } from '@/components/SEO';
import { getErrorMessage } from '@/utils/errors';
import {
  ASPECT_LABEL,
  MG_ASPECTS,
  motionGraphicsApi,
  type MGAspect,
  type MGTemplate,
  type ProjectSummary,
} from '@/api/motionGraphics';
import { useMotionGraphicsStore } from '@/stores/motionGraphicsStore';
import { TemplateGallery } from '@/components/motion-graphics/TemplateGallery';
import { BrandKitDialog } from '@/components/motion-graphics/BrandKitDialog';
import {
  AspectGlyph,
  ErrorNote,
  FieldLabel,
  MutedChip,
  PageHeader,
  PillGroup,
  SectionTitle,
} from '@/components/motion-graphics/shared';

const AUTO = '__auto__';

export function MotionGraphicsHomePage() {
  const navigate = useNavigate();
  const { catalog, catalogError, projects, projectsLoaded, listError, loadCatalog, loadProjects, removeProject } =
    useMotionGraphicsStore();
  const [brief, setBrief] = useState('');
  const [templateId, setTemplateId] = useState<string>(AUTO);
  const [aspect, setAspect] = useState<MGAspect>('9:16');
  const [voiceover, setVoiceover] = useState(false);
  const [showData, setShowData] = useState(false);
  const [dataCsv, setDataCsv] = useState('');
  const [drafting, setDrafting] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [galleryStyle, setGalleryStyle] = useState<string>('default');
  const [galleryAspect, setGalleryAspect] = useState<MGAspect>('9:16');
  const [creating, setCreating] = useState<string | null>(null);
  const [brandOpen, setBrandOpen] = useState(false);
  const [toDelete, setToDelete] = useState<ProjectSummary | null>(null);

  useEffect(() => {
    void loadCatalog();
    void loadProjects();
  }, [loadCatalog, loadProjects]);

  const templates = catalog?.templates ?? [];
  const templateName = (id: string) => templates.find((t) => t.id === id)?.name ?? id;

  const generate = async () => {
    if (brief.trim().length < 3) return;
    setDrafting(true);
    setDraftError(null);
    try {
      const p = await motionGraphicsApi.createFromBrief({
        brief: brief.trim(),
        template_id: templateId === AUTO ? null : templateId,
        aspect,
        voiceover,
        data_csv: dataCsv.trim() || null,
      });
      navigate(`/motion-graphics/${p.id}`);
    } catch (err) {
      setDraftError(getErrorMessage(err, 'The AI writer could not draft this brief'));
    } finally {
      setDrafting(false);
    }
  };

  const startFromTemplate = async (t: MGTemplate) => {
    setCreating(t.id);
    setDraftError(null);
    try {
      const p = await motionGraphicsApi.createProject({
        template_id: t.id,
        aspect: t.aspects.includes(galleryAspect) ? galleryAspect : t.default_aspect,
        style_id: galleryStyle === 'default' ? null : galleryStyle,
      });
      navigate(`/motion-graphics/${p.id}`);
    } catch (err) {
      setDraftError(getErrorMessage(err, 'Could not create the project'));
    } finally {
      setCreating(null);
    }
  };

  const deleteProject = async () => {
    if (!toDelete) return;
    try {
      await motionGraphicsApi.deleteProject(toDelete.id);
      removeProject(toDelete.id);
    } catch (err) {
      setDraftError(getErrorMessage(err, 'Could not delete the project'));
    }
  };

  return (
    <>
      <SEO
        title="Motion Graphics"
        description="Kinetic typography, number reveals, bar chart races and data stories from a brief or your CSV."
        url="/motion-graphics"
        noindex
      />
      <div className="w-full">
        <PageHeader
          title="Motion graphics"
          description="Describe the video or start from a template. Edit scene by scene with instant previews; every render is priced before it runs."
          actions={
            <Button variant="outline" onClick={() => setBrandOpen(true)}>
              <Palette className="h-4 w-4" /> Brand kit
            </Button>
          }
        />

        <section className="mb-10">
          <Card className={drafting ? 'beam-border' : undefined}>
            <CardContent className="space-y-4 p-5 sm:p-6">
              <div>
                <FieldLabel htmlFor="mg-brief" count={brief.length} max={4000}>
                  Brief
                </FieldLabel>
                <Textarea
                  id="mg-brief"
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  rows={4}
                  maxLength={4000}
                  placeholder="For example: 30 second vertical video on how solar module prices fell 90 percent from 2010 to 2024, source IRENA. End with 'Cheaper than coal in most of the world'."
                  className="resize-y"
                />
              </div>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
                <div className="min-w-0 flex-1 space-y-1.5">
                  <FieldLabel>Template</FieldLabel>
                  <Select value={templateId} onValueChange={setTemplateId}>
                    <SelectTrigger className="w-full lg:w-64">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={AUTO}>Let the AI choose</SelectItem>
                      {templates.map((t) => (
                        <SelectItem key={t.id} value={t.id}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <FieldLabel>Aspect</FieldLabel>
                  <PillGroup
                    value={aspect}
                    onChange={setAspect}
                    options={MG_ASPECTS.map((a) => ({
                      id: a,
                      label: (
                        <span className="flex items-center gap-1.5">
                          <AspectGlyph aspect={a} /> {a}
                        </span>
                      ),
                      title: ASPECT_LABEL[a],
                    }))}
                  />
                </div>
                <label className="flex min-h-10 items-center gap-2 text-sm text-muted-foreground">
                  <Switch checked={voiceover} onCheckedChange={setVoiceover} /> Write a voiceover
                </label>
              </div>
              <div>
                <button
                  type="button"
                  aria-expanded={showData}
                  className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => setShowData((v) => !v)}
                >
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-150 ${showData ? 'rotate-180' : ''}`} />
                  Attach data (CSV, optional)
                </button>
                {showData && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, ease: studioEase }}
                    className="mt-2"
                  >
                    <Textarea
                      value={dataCsv}
                      onChange={(e) => setDataCsv(e.target.value)}
                      rows={4}
                      placeholder={'Year,United States,China,India\n2000,10.25,1.21,0.47\n2024,28.78,18.53,3.89'}
                      className="font-mono text-xs"
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                      Paste from a spreadsheet. Your numbers are used as is; the AI only writes the words around them.
                    </p>
                  </motion.div>
                )}
              </div>
              {draftError && <ErrorNote>{draftError}</ErrorNote>}
              <div className="flex flex-wrap items-center gap-3">
                <Button size="lg" onClick={generate} disabled={drafting || brief.trim().length < 3}>
                  {drafting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {drafting ? 'Writing the storyboard' : 'Write the storyboard'}
                </Button>
                <span className="text-xs text-muted-foreground" aria-live="polite">
                  {catalog ? `${catalog.limits.drafts_per_hour} drafts per hour. ` : ''}Drafting uses your LLM key; fal costs start when you generate audio or render.
                </span>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="mb-10">
          <SectionTitle
            aside={
              <div className="flex flex-wrap items-center gap-2">
                <PillGroup
                  size="xs"
                  value={galleryAspect}
                  onChange={setGalleryAspect}
                  options={MG_ASPECTS.map((a) => ({ id: a, label: a }))}
                />
              </div>
            }
          >
            Templates
          </SectionTitle>
          <div className="mb-4">
            <PillGroup
              size="xs"
              value={galleryStyle}
              onChange={setGalleryStyle}
              options={[
                { id: 'default', label: 'Template style' },
                ...(catalog?.styles ?? []).map((s) => ({ id: s.id, label: s.name, title: s.description })),
              ]}
            />
          </div>
          {catalogError && <ErrorNote>{catalogError}</ErrorNote>}
          {!catalog && !catalogError ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {Array.from({ length: 10 }).map((_, i) => (
                <Skeleton key={i} className="aspect-[9/16] rounded-xl" />
              ))}
            </div>
          ) : (
            <TemplateGallery
              templates={templates}
              style={galleryStyle === 'default' ? undefined : galleryStyle}
              aspect={galleryAspect}
              onPick={startFromTemplate}
              busyId={creating}
            />
          )}
        </section>

        <section>
          <SectionTitle>Your projects</SectionTitle>
          {listError && <ErrorNote>{listError}</ErrorNote>}
          {projectsLoaded && projects.length === 0 && !listError && (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border px-6 py-12 text-center">
              <Type className="mb-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
              <h3 className="text-base font-semibold">No motion graphics yet</h3>
              <p className="max-w-md text-sm text-muted-foreground">
                Write a brief above or pick a template. Projects save as you edit.
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {!projectsLoaded &&
              !listError &&
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex gap-3 rounded-xl border border-border bg-card p-3">
                  <Skeleton className="h-20 w-20 shrink-0 rounded-lg" />
                  <div className="flex-1 space-y-2 pt-1">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                    <Skeleton className="h-4 w-24" />
                  </div>
                </div>
              ))}
            {projects.map((p) => (
              <div
                key={p.id}
                className="group relative flex gap-3 rounded-xl border border-border bg-card p-3 transition-colors duration-150 focus-within:border-foreground/20 hover:border-foreground/20"
              >
                <Link
                  to={`/motion-graphics/${p.id}`}
                  className="flex min-w-0 flex-1 gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-secondary/40">
                    {p.thumbnail_url ? (
                      <img src={p.thumbnail_url} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <AspectGlyph aspect={p.aspect} className="scale-150 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0 space-y-1">
                    <p className="truncate font-medium">{p.title}</p>
                    <p className="truncate text-xs text-muted-foreground">{templateName(p.template_id)}</p>
                    <div className="flex flex-wrap gap-1.5">
                      <MutedChip>{p.aspect}</MutedChip>
                      {p.status === 'rendered' ? (
                        <Badge variant="success">Rendered</Badge>
                      ) : (
                        <MutedChip>{p.status.charAt(0).toUpperCase() + p.status.slice(1)}</MutedChip>
                      )}
                    </div>
                  </div>
                </Link>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100"
                  onClick={() => setToDelete(p)}
                  aria-label="Delete project"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </section>
      </div>

      <BrandKitDialog open={brandOpen} onOpenChange={setBrandOpen} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete this project?"
        description="The storyboard, uploads and generated audio are removed. Rendered videos stay in your gallery."
        confirmText="Delete"
        variant="destructive"
        onConfirm={deleteProject}
      />
    </>
  );
}
