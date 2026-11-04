import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Clapperboard, Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Stagger, StaggerItem } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { getErrorMessage } from '@/utils/errors';
import { facelessApi, type FacelessCharacter, type FacelessSeries, type SeriesDetail } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { ProjectCard } from '@/components/faceless/ProjectCard';
import { CharacterAvatar } from '@/components/faceless/CharacterCard';
import { SeriesDialog } from '@/components/faceless/SeriesDialog';
import { EmptyState, ErrorNote, Kicker, PageHeader, SectionTitle } from '@/components/faceless/shared';

export function FacelessSeriesPage() {
  const { id } = useParams();
  const seriesId = Number(id);
  const navigate = useNavigate();
  const { templates, styles, characters, loadCatalog, loadCharacters, removeSeries } = useFacelessStore();
  const [series, setSeries] = useState<SeriesDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    loadCatalog();
    loadCharacters();
  }, [loadCatalog, loadCharacters]);

  useEffect(() => {
    if (!Number.isFinite(seriesId)) return;
    let cancelled = false;
    facelessApi
      .seriesOne(seriesId)
      .then((s) => !cancelled && setSeries(s))
      .catch((err) => !cancelled && setError(getErrorMessage(err, 'Could not load this series')));
    return () => {
      cancelled = true;
    };
  }, [seriesId]);

  const cast = useMemo(
    () =>
      (series?.cast_ids ?? [])
        .map((cid) => characters.find((c) => c.id === cid))
        .filter((c): c is FacelessCharacter => !!c),
    [series, characters],
  );
  const template = templates.find((t) => t.id === series?.template_id);
  const style = styles.find((s) => s.id === series?.style);
  const episodes = series?.projects ?? null;

  const remove = async () => {
    try {
      await facelessApi.deleteSeries(seriesId);
      removeSeries(seriesId);
      navigate('/faceless');
    } catch (err) {
      setError(getErrorMessage(err, 'Could not delete the series'));
    }
  };

  const onSaved = (s: FacelessSeries) => setSeries((prev) => (prev ? { ...prev, ...s } : prev));

  return (
    <>
      <SEO title={series?.title ?? 'Series'} url={`/faceless/series/${seriesId}`} noindex />
      <Stagger className="w-full">
        <StaggerItem>
          <PageHeader
            title={series?.title ?? 'Series'}
            description={series?.logline || (template ? `Default template: ${template.name}` : undefined)}
            actions={
              <>
                <Button asChild variant="ghost">
                  <Link to="/faceless">
                    <ArrowLeft className="h-4 w-4" /> Studio
                  </Link>
                </Button>
                {series && (
                  <>
                    <Button variant="outline" onClick={() => setEditOpen(true)}>
                      <Pencil className="h-4 w-4" /> Edit
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteOpen(true)} aria-label="Delete series">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                    <Button asChild>
                      <Link
                        to={`/faceless/new?series=${series.id}${series.template_id ? `&template=${encodeURIComponent(series.template_id)}` : ''}`}
                      >
                        <Plus className="h-4 w-4" /> New episode
                      </Link>
                    </Button>
                  </>
                )}
              </>
            }
          />
        </StaggerItem>

        {error && (
          <StaggerItem className="mb-6">
            <ErrorNote>{error}</ErrorNote>
          </StaggerItem>
        )}

        <StaggerItem>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <aside className="panel space-y-4 rounded-xl p-4 lg:order-2">
              <div>
                <Kicker className="mb-1.5">World</Kicker>
                <p className="whitespace-pre-line text-sm text-muted-foreground">
                  {series?.world_notes || 'No world notes yet. Describe places, history and running jokes so each episode stays in character.'}
                </p>
              </div>
              {(series?.tone || style) && (
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  {series?.tone && (
                    <div>
                      <dt><Kicker>Tone</Kicker></dt>
                      <dd className="mt-0.5">{series.tone}</dd>
                    </div>
                  )}
                  {style && (
                    <div>
                      <dt><Kicker>Style</Kicker></dt>
                      <dd className="mt-0.5">{style.label}</dd>
                    </div>
                  )}
                </dl>
              )}
              {(series?.rules ?? []).length > 0 && (
                <div>
                  <Kicker className="mb-1.5">Continuity rules</Kicker>
                  <ul className="list-inside list-disc space-y-0.5 text-sm text-muted-foreground">
                    {series?.rules.map((r) => <li key={r}>{r}</li>)}
                  </ul>
                </div>
              )}
              <div>
                <Kicker className="mb-2">Cast</Kicker>
                {cast.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Cast is chosen per episode.</p>
                ) : (
                  <ul className="space-y-2">
                    {cast.map((c) => (
                      <li key={c.id} className="flex items-center gap-2 text-sm">
                        <CharacterAvatar character={c} size={28} /> {c.name}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {(series?.episode_memory ?? []).length > 0 && (
                <div>
                  <Kicker className="mb-1.5">Episode memory</Kicker>
                  <ol className="space-y-1.5 text-xs text-muted-foreground">
                    {series?.episode_memory.map((m, i) => (
                      <li key={`${m.project_id}-${i}`}>
                        <span className="text-foreground">{m.title || `Episode ${i + 1}`}</span>
                        {m.premise && <>: {m.premise}</>}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              <p className="text-xs text-muted-foreground">
                Each new draft reads this memory, and the originality check compares it with the earlier episodes.
              </p>
            </aside>

            <section className="lg:col-span-2" aria-labelledby="fs-episodes">
              <SectionTitle>
                <span id="fs-episodes">Episodes</span>
              </SectionTitle>
              {episodes === null ? (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="shimmer h-36 rounded-xl" />
                  ))}
                </div>
              ) : episodes.length === 0 ? (
                <EmptyState icon={Clapperboard} title="No episodes yet">
                  Start the first episode; the series remembers its cast and world for the next one.
                </EmptyState>
              ) : (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {episodes.map((p) => (
                    <ProjectCard key={p.id} project={p} template={templates.find((t) => t.id === p.template_id)} seriesName={series?.title} />
                  ))}
                </div>
              )}
            </section>
          </div>
        </StaggerItem>
      </Stagger>

      <SeriesDialog open={editOpen} onOpenChange={setEditOpen} series={series} onSaved={onSaved} />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete series"
        description="Delete this series? Its episodes stay in your projects as standalone videos."
        confirmText="Delete"
        variant="destructive"
        onConfirm={remove}
      />
    </>
  );
}
