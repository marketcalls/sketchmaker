import { useEffect, useState } from 'react';
import { Check, ExternalLink, ImagePlus, Loader2, Package, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { errorSuffix, getErrorMessage } from '@/utils/errors';
import { facelessApi, type FacelessProject, type StepRun } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { ASPECT_CLASS, CopyButton, EmptyState, ErrorNote, Kicker, MutedChip, SectionTitle } from '../shared';
import { usePaidStep } from './usePaidStep';
import { usePaidGate } from './gate';
import { activeRun, lastRun } from './stepState';

const PLATFORM: Record<string, string> = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram' };

// Earlier builds kept the chosen thumbnail and ticked disclosures in this
// browser only; read once as a fallback until the project has its own.
function legacyLocal<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function PackageStep({ project, runs }: { project: FacelessProject; runs: StepRun[] }) {
  const refreshProject = useFacelessStore((s) => s.refreshProject);
  const setProject = useFacelessStore((s) => s.setProject);
  const gate = usePaidGate(project, 'thumbnails');
  const { request, dialog } = usePaidStep(project.id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Saved with the project (settings.selected_thumbnail, settings.disclosure_checks).
  const savedPick = project.settings?.selected_thumbnail ?? project.selected_thumbnail ?? null;
  const savedTicks = project.settings?.disclosure_checks ?? project.disclosure_checks ?? null;
  const [picked, setPickedState] = useState<number | null>(
    () => savedPick ?? legacyLocal<number>(`faceless:thumb:${project.id}`),
  );
  const [ticked, setTickedState] = useState<string[]>(
    () => savedTicks ?? legacyLocal<string[]>(`faceless:disclosed:${project.id}`) ?? [],
  );
  useEffect(() => {
    if (savedPick !== null) setPickedState(savedPick);
  }, [savedPick]);
  useEffect(() => {
    if (savedTicks !== null) setTickedState(savedTicks);
  }, [savedTicks]);
  const saveChoice = async (settings: { selected_thumbnail?: number; disclosure_checks?: string[] }) => {
    setError(null);
    try {
      setProject(await facelessApi.updateProject(project.id, { settings }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save your choice'));
    }
  };
  const setPicked = (index: number) => {
    setPickedState(index);
    void saveChoice({ selected_thumbnail: index });
  };
  const setTicked = (keys: string[]) => {
    setTickedState(keys);
    void saveChoice({ disclosure_checks: keys });
  };
  const pkg = project.packaging;
  const [texts, setTexts] = useState<string[]>(['', '', '']);
  const thumbRun = activeRun(project, 'thumbnails');
  const lastThumbs = lastRun(runs, 'thumbnails');
  const thumbs = project.thumbnails.filter((t) => t.url);
  const facts = project.script?.facts ?? [];
  const stale = pkg?.script_version !== undefined && pkg.script_version !== project.script_version;

  useEffect(() => {
    const fromPkg = (pkg?.thumbnail_prompts ?? []).map((t) => t.text);
    setTexts([0, 1, 2].map((i) => fromPkg[i] ?? ''));
  }, [pkg?.thumbnail_prompts]);

  const write = async () => {
    setBusy(true);
    setError(null);
    try {
      await facelessApi.pack(project.id);
      await refreshProject();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not write the package'));
    } finally {
      setBusy(false);
    }
  };

  if (!project.script) {
    return <EmptyState icon={Package} title="Script first">Titles, description and chapters are written from the script.</EmptyState>;
  }

  if (!pkg) {
    return (
      <div className="space-y-4">
        <EmptyState
          icon={Package}
          title="Package the episode"
          action={
            <Button onClick={write} disabled={busy}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? 'Writing titles and description' : 'Write titles and description'}
            </Button>
          }
        >
          Three titles, a description with its first line tuned for search, tags, chapters, thumbnail ideas and the disclosure each platform expects.
        </EmptyState>
        <ErrorNote>{error}</ErrorNote>
      </div>
    );
  }

  const description = [pkg.first_line, pkg.description, pkg.sources_section, pkg.disclosure_line].filter(Boolean).join('\n\n');
  const chaptersText = pkg.chapters.map((c) => `${c.timestamp} ${c.title}`).join('\n');
  const tagsText = pkg.tags.join(', ');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Written for script version {pkg.script_version ?? project.script_version}.
          {stale && <span className="text-warning"> The script changed since; rewrite to match.</span>}
        </p>
        <Button variant="outline" size="sm" onClick={write} disabled={busy}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />} {busy ? 'Rewriting' : 'Rewrite'}
        </Button>
      </div>
      <ErrorNote>{error}</ErrorNote>

      <section aria-labelledby="pk-titles">
        <SectionTitle>
          <span id="pk-titles">Titles</span>
        </SectionTitle>
        <ol className="space-y-2">
          {pkg.titles.slice(0, 3).map((t, i) => (
            <li key={i} className="panel flex items-center gap-3 rounded-xl px-4 py-3">
              <span className="font-mono text-[11px] tabular text-muted-foreground">{i + 1}</span>
              <span className="min-w-0 flex-1 text-base font-medium leading-snug">{t}</span>
              <span className="hidden text-[11px] text-muted-foreground sm:inline"><span className="font-mono tabular">{t.length}</span> chars</span>
              <CopyButton text={t} label="Copy" />
            </li>
          ))}
        </ol>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="panel rounded-xl p-4" aria-labelledby="pk-desc">
          <div className="mb-2 flex items-center justify-between">
            <h3 id="pk-desc" className="text-base font-semibold">Description</h3>
            <CopyButton text={description} label="Copy all" />
          </div>
          <p className="text-sm font-medium">{pkg.first_line}</p>
          <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">{pkg.description}</p>
          {pkg.disclosure_line && <p className="mt-2 text-xs text-muted-foreground">{pkg.disclosure_line}</p>}
        </section>

        <section className="space-y-4">
          <div className="panel rounded-xl p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-base font-semibold">Tags</h3>
              <CopyButton text={tagsText} label="Copy tags" />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {pkg.tags.map((t) => (
                <MutedChip key={t}>{t}</MutedChip>
              ))}
            </div>
            {pkg.hashtags.length > 0 && (
              <div className="mt-3 flex items-center justify-between gap-2">
                <p className="min-w-0 truncate font-mono text-xs text-muted-foreground">{pkg.hashtags.join(' ')}</p>
                <CopyButton text={pkg.hashtags.join(' ')} label="Copy" />
              </div>
            )}
          </div>
          {pkg.chapters.length > 0 && (
            <div className="panel rounded-xl p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-base font-semibold">Chapters</h3>
                <CopyButton text={chaptersText} label="Copy" />
              </div>
              <ol className="space-y-1 text-sm">
                {pkg.chapters.map((c) => (
                  <li key={`${c.timestamp}-${c.title}`} className="flex gap-3">
                    <span className="w-14 font-mono text-xs tabular text-muted-foreground">{c.timestamp}</span>
                    <span>{c.title}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      </div>

      <section aria-labelledby="pk-thumbs">
        <SectionTitle
          aside={
            <Button
              size="sm"
              disabled={!!gate}
              title={gate ?? undefined}
              onClick={() =>
                request({
                  step: 'thumbnails',
                  options: { texts: texts.map((t) => t.trim()).filter(Boolean).length ? texts.map((t) => t.trim()) : undefined },
                  title: 'Generate 3 thumbnails',
                  description: 'Three variants with your cast and a clean area for the headline, drawn by the app.',
                })
              }
            >
              {thumbRun ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />} {thumbRun ? 'Generating' : 'Generate 3'}
            </Button>
          }
        >
          <span id="pk-thumbs">Thumbnails</span>
        </SectionTitle>
        <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {texts.map((t, i) => (
            <Input
              key={i}
              aria-label={`Headline ${i + 1}`}
              value={t}
              maxLength={60}
              placeholder={`Headline ${i + 1}, 2 to 4 words`}
              onChange={(e) => setTexts(texts.map((x, idx) => (idx === i ? e.target.value : x)))}
            />
          ))}
        </div>
        {thumbs.length === 0 && thumbRun ? (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="Thumbnails being generated" role="status">
            {[0, 1, 2].map((i) => (
              <li key={i} className={cn('beam-border flex items-center justify-center rounded-xl bg-secondary/30', ASPECT_CLASS[project.aspect])}>
                <span className="text-xs text-muted-foreground">{i === 0 ? 'Generating thumbnails' : ''}</span>
              </li>
            ))}
          </ul>
        ) : thumbs.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No thumbnails yet.
          </p>
        ) : (
          <ul role="radiogroup" aria-label="Choose a thumbnail" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {thumbs.map((t, i) => {
              const idx = t.index ?? i;
              const on = picked === idx;
              return (
                <li key={idx}>
                  <div className={cn('overflow-hidden rounded-xl border bg-card transition-colors duration-150', on ? 'border-primary/60' : 'border-border hover:border-foreground/20')}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={on}
                      onClick={() => setPicked(idx)}
                      className={cn('relative block w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring', ASPECT_CLASS[project.aspect])}
                    >
                      <img src={t.url ?? undefined} alt={`Thumbnail ${i + 1}${t.text ? `: ${t.text}` : ''}`} className="h-full w-full object-cover" />
                      {on && (
                        <span className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                          <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        </span>
                      )}
                    </button>
                    <div className="flex items-center justify-between gap-2 p-2">
                      <span className="truncate text-xs text-muted-foreground">{t.text}</span>
                      <div className="flex gap-1">
                        <Button asChild variant="ghost" size="sm">
                          <a href={t.url ?? undefined} target="_blank" rel="noreferrer" download>
                            <ExternalLink className="h-3.5 w-3.5" /> Open
                          </a>
                        </Button>
                        {t.raw_url && (
                          <Button asChild variant="ghost" size="sm">
                            <a href={t.raw_url} target="_blank" rel="noreferrer">No text</a>
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {lastThumbs?.status === 'failed' && !thumbRun && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
            Thumbnails failed{errorSuffix(lastThumbs.error)}
          </p>
        )}
      </section>

      <section aria-labelledby="pk-disclose">
        <SectionTitle>
          <span id="pk-disclose">Disclosure checklist</span>
        </SectionTitle>
        {pkg.disclosure_advice.length === 0 ? (
          <p className="text-sm text-muted-foreground">No platform advice for this episode.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {pkg.disclosure_advice.map((d) => {
              const key = `${d.platform}:${d.label}`;
              const done = ticked.includes(key);
              return (
                <li key={key} className={cn('panel rounded-xl p-4', d.required && !done && 'border-warning/40')}>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-base font-semibold">{PLATFORM[d.platform] ?? d.platform}</span>
                    <span className={cn('text-xs font-medium', d.required ? 'text-warning' : 'text-muted-foreground')}>
                      {d.required ? 'Required' : 'Not required'}
                    </span>
                  </div>
                  <p className="text-sm">{d.label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{d.reason}</p>
                  {d.required && (
                    <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-[var(--color-primary)]"
                        checked={done}
                        onChange={(e) => setTicked(e.target.checked ? [...ticked, key] : ticked.filter((k) => k !== key))}
                      />
                      Done when uploading
                    </label>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {(facts.length > 0 || pkg.sources_section) && (
        <section aria-labelledby="pk-sources">
          <SectionTitle aside={pkg.sources_section ? <CopyButton text={pkg.sources_section} label="Copy" /> : undefined}>
            <span id="pk-sources">Sources</span>
          </SectionTitle>
          <ol className="space-y-2">
            {facts.map((f, i) => (
              <li key={f.id ?? i} className="rounded-lg border border-border bg-secondary/30 p-3 text-sm">
                <p>{f.text}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {f.source ? (
                    /^https?:\/\//.test(f.source) ? (
                      <a href={f.source} target="_blank" rel="noreferrer noopener" className="break-all text-foreground underline-offset-4 hover:underline">
                        {f.source}
                      </a>
                    ) : (
                      f.source
                    )
                  ) : (
                    'No source given'
                  )}
                  {f.date && `, ${f.date}`}
                </p>
              </li>
            ))}
          </ol>
          {facts.length === 0 && pkg.sources_section && <p className="whitespace-pre-line text-sm text-muted-foreground">{pkg.sources_section}</p>}
          <Kicker className="mt-2">Fact mode lists every source the script used.</Kicker>
        </section>
      )}
      {dialog}
    </div>
  );
}
