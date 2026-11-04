import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Clapperboard, Layers, Plus, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Stagger, StaggerItem } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { getErrorMessage } from '@/utils/errors';
import { facelessApi, type ProjectSummary } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { ProjectCard, SpendSummary } from '@/components/faceless/ProjectCard';
import { CharacterAvatar } from '@/components/faceless/CharacterCard';
import { SeriesDialog } from '@/components/faceless/SeriesDialog';
import { TemplateGallery } from '@/components/faceless/TemplateGallery';
import { CatalogError } from '@/components/faceless/CatalogError';
import { EmptyState, ErrorNote, PageHeader, SectionTitle } from '@/components/faceless/shared';

export function FacelessHomePage() {
  const navigate = useNavigate();
  const {
    templates, characters, series, projects, projectsLoaded, listError, catalogError,
    loadCatalog, loadCharacters, loadSeries, loadProjects, removeProject,
  } = useFacelessStore();
  const [seriesOpen, setSeriesOpen] = useState(false);
  const [toDelete, setToDelete] = useState<ProjectSummary | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    loadCatalog();
    loadCharacters();
    loadSeries();
    loadProjects();
  }, [loadCatalog, loadCharacters, loadSeries, loadProjects]);

  const templateById = useMemo(() => new Map(templates.map((t) => [t.id, t])), [templates]);
  const seriesById = useMemo(() => new Map(series.map((s) => [s.id, s])), [series]);
  const cast = characters.filter((c) => !c.is_archived);

  const deleteProject = async () => {
    if (!toDelete) return;
    setDeleteError(null);
    try {
      await facelessApi.deleteProject(toDelete.id);
      removeProject(toDelete.id);
    } catch (err) {
      setDeleteError(getErrorMessage(err, 'Could not delete the project'));
    }
  };

  return (
    <>
      <SEO
        title="Faceless Studio"
        description="Character-driven faceless videos and stories: cast, script, storyboard, voice, music, captions and render in one studio."
        url="/faceless"
        noindex
      />
      <Stagger className="w-full">
        <StaggerItem>
          <PageHeader
            title="Your studio"
            description="Recurring characters, real stories, every step priced before it runs."
            actions={
              <>
                <Button asChild variant="outline">
                  <Link to="/faceless/characters">
                    <Users className="h-4 w-4" /> Cast library
                  </Link>
                </Button>
                <Button asChild>
                  <Link to="/faceless/new">
                    <Plus className="h-4 w-4" /> New video
                  </Link>
                </Button>
              </>
            }
          />
        </StaggerItem>

        {listError && (
          <StaggerItem className="mb-6">
            <ErrorNote>{listError}</ErrorNote>
          </StaggerItem>
        )}
        {catalogError && (
          <StaggerItem className="mb-6">
            <CatalogError />
          </StaggerItem>
        )}

        <StaggerItem>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <section className="lg:col-span-2" aria-labelledby="fh-projects">
              <SectionTitle>
                <span id="fh-projects">Recent projects</span>
              </SectionTitle>
              {!projectsLoaded ? (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="shimmer h-36 rounded-xl" />
                  ))}
                </div>
              ) : projects.length === 0 ? (
                <EmptyState
                  icon={Clapperboard}
                  title="No projects yet"
                  action={
                    <Button asChild>
                      <Link to="/faceless/new">Start your first video</Link>
                    </Button>
                  }
                >
                  Pick a template, give it an idea, and the studio drafts a script you can edit.
                </EmptyState>
              ) : (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {projects.slice(0, 12).map((p) => (
                    <ProjectCard
                      key={p.id}
                      project={p}
                      template={templateById.get(p.template_id)}
                      seriesName={p.series_id ? seriesById.get(p.series_id)?.title : undefined}
                      onDelete={setToDelete}
                    />
                  ))}
                </div>
              )}
              {deleteError && <div className="mt-3"><ErrorNote>{deleteError}</ErrorNote></div>}
            </section>

            <aside className="space-y-6">
              <SpendSummary projects={projects} />

              <section className="panel rounded-xl p-4" aria-labelledby="fh-cast">
                <SectionTitle
                  aside={
                    <Link to="/faceless/characters" className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
                      Manage <ArrowRight className="h-3 w-3" />
                    </Link>
                  }
                >
                  <span id="fh-cast">Cast</span>
                </SectionTitle>
                {cast.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Build recurring characters from two or three photos, a short video, or a description.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {cast.slice(0, 10).map((c) => (
                      <CharacterAvatar key={c.id} character={c} size={44} />
                    ))}
                    {cast.length > 10 && (
                      <span className="flex h-11 w-11 items-center justify-center rounded-full border border-border font-mono text-xs tabular text-muted-foreground">
                        +{cast.length - 10}
                      </span>
                    )}
                  </div>
                )}
              </section>

              <section className="panel rounded-xl p-4" aria-labelledby="fh-series">
                <SectionTitle
                  aside={
                    <Button variant="ghost" size="sm" onClick={() => setSeriesOpen(true)}>
                      <Plus className="h-3.5 w-3.5" /> Add series
                    </Button>
                  }
                >
                  <span id="fh-series">Series</span>
                </SectionTitle>
                {series.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Group episodes with the same cast and world. The studio checks each new episode against the last ones.
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {series.map((s) => (
                      <li key={s.id}>
                        <Link
                          to={`/faceless/series/${s.id}`}
                          className="flex items-center gap-3 rounded-md px-2 py-2 transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <Layers className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="min-w-0 flex-1 truncate text-sm">{s.title}</span>
                          <span className="font-mono text-[11px] tabular text-muted-foreground">
                            {s.project_count ?? 0} ep
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>
        </StaggerItem>

        <StaggerItem className="mt-12">
          <section aria-labelledby="fh-templates">
            <SectionTitle>
              <span id="fh-templates">Start from a template</span>
            </SectionTitle>
            <p className="mb-5 -mt-1 text-sm text-muted-foreground">
              Each template is a tested beat structure with a pace, a look and a voice. You can change all of it.
            </p>
            {templates.length === 0 && catalogError ? (
              <p className="text-sm text-muted-foreground">The templates did not load.</p>
            ) : templates.length === 0 ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="shimmer h-64 rounded-xl" />
                ))}
              </div>
            ) : (
              <TemplateGallery templates={templates} onSelect={(t) => navigate(`/faceless/new?template=${encodeURIComponent(t.id)}`)} />
            )}
          </section>
        </StaggerItem>
      </Stagger>

      <SeriesDialog open={seriesOpen} onOpenChange={setSeriesOpen} series={null} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete project"
        description={`Delete "${toDelete?.title || 'Untitled project'}" and its stills, clips, audio and renders? This cannot be undone.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={deleteProject}
      />
    </>
  );
}
