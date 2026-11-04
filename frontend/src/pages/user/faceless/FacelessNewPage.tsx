import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, Loader2, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Stagger, StaggerItem } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import {
  FACELESS_LANGUAGES,
  FACELESS_MAX_SECONDS,
  FACELESS_MIN_SECONDS,
  facelessApi,
  type FacelessAspect,
  type FacelessTemplate,
} from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { TemplateGallery, BeatStrip } from '@/components/faceless/TemplateGallery';
import { VoiceGrid } from '@/components/faceless/VoicePicker';
import { CastPicker } from '@/components/faceless/CastPicker';
import { CatalogError } from '@/components/faceless/CatalogError';
import { CharacterAvatar } from '@/components/faceless/CharacterCard';
import {
  AspectGlyph,
  ErrorNote,
  FieldLabel,
  Kicker,
  PageHeader,
  PillGroup,
  TechChip,
  formatDuration,
} from '@/components/faceless/shared';

const STEPS = ['Template', 'Story', 'Format', 'Look and voice', 'Cast and series', 'Review'] as const;
type SeriesMode = 'none' | 'existing' | 'new';
const DRAFT_KEY = 'faceless:new-draft';

interface FactRow {
  text: string;
  source: string;
  date: string;
}

interface Draft {
  templateId: string | null;
  title: string;
  idea: string;
  facts: FactRow[];
  lengthSeconds: number;
  aspect: FacelessAspect;
  language: string;
  style: string;
  voiceId: string | null;
  cast: number[];
  seriesMode: SeriesMode;
  seriesId: number | null;
  newSeriesTitle: string;
}

const EMPTY_FACT: FactRow = { text: '', source: '', date: '' };

const EMPTY: Draft = {
  templateId: null,
  title: '',
  idea: '',
  facts: [{ ...EMPTY_FACT }],
  lengthSeconds: 60,
  aspect: '9:16',
  language: 'en',
  style: 'template',
  voiceId: null,
  cast: [],
  seriesMode: 'none',
  seriesId: null,
  newSeriesTitle: '',
};

function readDraft(): Draft {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return EMPTY;
    const parsed = { ...EMPTY, ...(JSON.parse(raw) as Partial<Draft>) };
    return Array.isArray(parsed.facts) ? parsed : { ...parsed, facts: [{ ...EMPTY_FACT }] };
  } catch {
    return EMPTY;
  }
}

function lengthBounds(t: FacelessTemplate | undefined, aspect: FacelessAspect) {
  const cap = FACELESS_MAX_SECONDS[aspect];
  const min = Math.max(FACELESS_MIN_SECONDS, Math.min(t?.length.min_seconds ?? 30, cap));
  const max = Math.max(min, Math.min(t?.length.max_seconds ?? cap, cap));
  const step = max > 240 ? 30 : 5;
  return { min, max, step };
}

const filledFacts = (facts: FactRow[]) => facts.filter((f) => f.text.trim());

export function FacelessNewPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const {
    templates, styles, voices, defaultNarrator, characters, series, catalogError,
    loadCatalog, loadCharacters, loadSeries, upsertSeries,
  } = useFacelessStore();
  const [draft, setDraft] = useState<Draft>(readDraft);
  const [step, setStep] = useState(0);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCatalog();
    loadCharacters();
    loadSeries();
  }, [loadCatalog, loadCharacters, loadSeries]);

  useEffect(() => {
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // storage unavailable; the wizard still works
    }
  }, [draft]);

  const template = templates.find((t) => t.id === draft.templateId);
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  const applyTemplate = (t: FacelessTemplate) => {
    setDraft((d) => {
      const same = d.templateId === t.id;
      const aspect = same && t.aspects.includes(d.aspect) ? d.aspect : t.default_aspect;
      const b = lengthBounds(t, aspect);
      const suggested = t.voice.suggested_voices.find((v) => voices.some((x) => x.id === v));
      return {
        ...d,
        templateId: t.id,
        aspect,
        lengthSeconds: Math.min(b.max, Math.max(b.min, same ? d.lengthSeconds : t.length.default_seconds)),
        voiceId: same && d.voiceId ? d.voiceId : suggested ?? d.voiceId ?? defaultNarrator,
      };
    });
  };

  // Preselect from ?template= and ?series= (home gallery, series page).
  const templatesReady = templates.length > 0;
  const wantedTemplate = params.get('template');
  const wantedSeries = Number(params.get('series')) || null;
  useEffect(() => {
    if (!templatesReady) return;
    const t = wantedTemplate ? templates.find((x) => x.id === wantedTemplate) : undefined;
    if (t) {
      applyTemplate(t);
      setStep(1);
    }
    // once the catalog is in
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedTemplate, templatesReady]);

  useEffect(() => {
    if (!wantedSeries) return;
    const s = series.find((x) => x.id === wantedSeries);
    if (s) {
      setDraft((d) => ({
        ...d,
        seriesMode: 'existing',
        seriesId: s.id,
        cast: d.cast.length ? d.cast : s.cast_ids.slice(0, 6),
        style: s.style ?? d.style,
      }));
    }
  }, [wantedSeries, series]);

  useEffect(() => {
    if (!draft.voiceId && (defaultNarrator || voices[0])) set({ voiceId: defaultNarrator ?? voices[0].id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voices, defaultNarrator]);

  // A series' cast or a restored draft can name a character the backend now
  // refuses, and that would only fail later, at the quote.
  const blockedCast = useMemo(() => new Set(characters.filter((c) => !c.can_generate).map((c) => c.id)), [characters]);
  useEffect(() => {
    setDraft((d) => (d.cast.some((id) => blockedCast.has(id)) ? { ...d, cast: d.cast.filter((id) => !blockedCast.has(id)) } : d));
  }, [blockedCast]);

  const bounds = lengthBounds(template, draft.aspect);
  const wpm = template?.voice.wpm || 165;
  const words = Math.round((draft.lengthSeconds * wpm) / 60);
  const factsOk = !template?.fact_mode || filledFacts(draft.facts).length > 0;

  const stepValid = useMemo(
    () => [
      !!template,
      draft.idea.trim().length >= 8 && factsOk,
      draft.lengthSeconds >= bounds.min && draft.lengthSeconds <= bounds.max,
      !!draft.voiceId,
      draft.seriesMode === 'existing'
        ? !!draft.seriesId
        : draft.seriesMode === 'new'
          ? draft.newSeriesTitle.trim().length > 0
          : true,
      true,
    ],
    [template, draft, bounds.min, bounds.max, factsOk],
  );

  const firstInvalid = stepValid.findIndex((v) => !v);
  const canReach = (i: number) => firstInvalid === -1 || i <= firstInvalid;
  const styleLabel = draft.style === 'template' ? 'Template default' : styles.find((s) => s.id === draft.style)?.label ?? draft.style;

  const updateFact = (i: number, patch: Partial<FactRow>) =>
    setDraft((d) => ({ ...d, facts: d.facts.map((f, idx) => (idx === i ? { ...f, ...patch } : f)) }));

  const create = async () => {
    if (!template) return;
    setCreating(true);
    setError(null);
    try {
      let seriesId: number | null = draft.seriesMode === 'existing' ? draft.seriesId : null;
      if (draft.seriesMode === 'new') {
        const created = await facelessApi.createSeries({
          title: draft.newSeriesTitle.trim(),
          template_id: template.id,
          style: draft.style !== 'template' ? draft.style : null,
          cast_ids: draft.cast,
        });
        upsertSeries(created);
        seriesId = created.id;
        set({ seriesMode: 'existing', seriesId });
      }
      const project = await facelessApi.createProject({
        title: draft.title.trim() || null,
        idea: draft.idea.trim(),
        template_id: template.id,
        series_id: seriesId,
        aspect: draft.aspect,
        length_seconds: draft.lengthSeconds,
        language: draft.language,
        style: draft.style,
        narrator_voice: draft.voiceId,
        cast_ids: draft.cast,
        facts: filledFacts(draft.facts).map((f) => ({ text: f.text.trim(), source: f.source.trim(), date: f.date.trim() })),
      });
      try {
        sessionStorage.removeItem(DRAFT_KEY);
      } catch {
        // ignore
      }
      navigate(`/faceless/projects/${project.id}?draft=1`);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not create the project'));
      setCreating(false);
    }
  };

  // Keep the user's place between steps: bring the step into view only when
  // its top has scrolled away, and move focus to its heading.
  const stepRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const firstStep = useRef(true);
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    const el = stepRef.current;
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: 'start' });
    titleRef.current?.focus({ preventScroll: true });
  }, [step]);

  const next = () => setStep((s) => Math.min(STEPS.length - 1, s + 1));
  const back = () => setStep((s) => Math.max(0, s - 1));

  return (
    <>
      <SEO title="New faceless video" url="/faceless/new" noindex />
      <Stagger className="w-full">
        <StaggerItem>
          <PageHeader
            title="Set up the episode"
            description="Draft and edit the script first. Every paid step shows an estimate and waits for you to confirm it."
            actions={
              <Button asChild variant="ghost">
                <Link to="/faceless">
                  <ArrowLeft className="h-4 w-4" /> Studio
                </Link>
              </Button>
            }
          />
        </StaggerItem>

        <StaggerItem>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
            <nav aria-label="Setup steps" className="lg:sticky lg:top-20 lg:self-start">
              <ol className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 lg:flex-col lg:overflow-visible">
                {STEPS.map((label, i) => {
                  const done = i < step && stepValid[i];
                  return (
                    <li key={label} className="shrink-0">
                      <button
                        type="button"
                        onClick={() => canReach(i) && setStep(i)}
                        disabled={!canReach(i)}
                        aria-current={i === step ? 'step' : undefined}
                        className={cn(
                          'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40',
                          i === step ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        <span
                          aria-hidden="true"
                          className={cn(
                            'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] tabular',
                            i === step ? 'border-primary text-foreground' : 'border-border text-muted-foreground',
                          )}
                        >
                          {done && i !== step ? <Check className="h-3 w-3" /> : i + 1}
                        </span>
                        <span className="whitespace-nowrap">{label}</span>
                        {done && <span className="sr-only">(done)</span>}
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>

            <section ref={stepRef} className="panel min-w-0 scroll-mt-20 rounded-xl p-4 sm:p-6" aria-labelledby="wizard-step-title">
              <h2 id="wizard-step-title" ref={titleRef} tabIndex={-1} className="mb-1 text-lg font-semibold tracking-tight focus:outline-none">{STEPS[step]}</h2>
              <CatalogError className="mb-4" />

              {step === 0 && (
                <div className="mt-4">
                  {templates.length === 0 && catalogError ? null : templates.length === 0 ? (
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="shimmer h-60 rounded-xl" />
                      ))}
                    </div>
                  ) : (
                    <TemplateGallery
                      templates={templates}
                      selectedId={draft.templateId}
                      onSelect={(t) => {
                        applyTemplate(t);
                        next();
                      }}
                    />
                  )}
                </div>
              )}

              {step === 1 && template && (
                <div className="mt-4 space-y-5">
                  <TemplateSummary template={template} />
                  <div>
                    <FieldLabel htmlFor="fn-idea" hint={`${draft.idea.trim().length} / 8000`}>
                      {template.fact_mode ? 'Topic' : 'Idea'}
                    </FieldLabel>
                    <Textarea
                      id="fn-idea"
                      rows={4}
                      maxLength={8000}
                      value={draft.idea}
                      onChange={(e) => set({ idea: e.target.value })}
                      placeholder={
                        template.fact_mode
                          ? 'The night the Library of Alexandria burned, and what was really lost'
                          : 'Milo the fox opens a noodle stall at the night market, and his rival sets up right next door'
                      }
                    />
                  </div>
                  <fieldset aria-describedby="fn-facts-help">
                    <legend className="mb-1.5 flex w-full items-baseline justify-between text-xs font-medium text-muted-foreground">
                      Facts and sources
                      <span className="text-[11px] font-normal text-muted-foreground/80">
                        {template.fact_mode ? 'required' : 'optional'}
                      </span>
                    </legend>
                    <p id="fn-facts-help" className="mb-3 text-xs text-muted-foreground">
                      {template.fact_mode
                        ? 'Fact mode: every claim in the script must come from these facts, and the sources go into the package. Add at least one.'
                        : 'Anything the story must stay true to: names, places, dates.'}
                    </p>
                    <ol className="space-y-3">
                      {draft.facts.map((f, i) => (
                        <li key={i} className="rounded-lg border border-border bg-secondary/20 p-3">
                          <div className="mb-2 flex items-center justify-between">
                            <Kicker>Fact {i + 1}</Kicker>
                            {draft.facts.length > 1 && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => set({ facts: draft.facts.filter((_, idx) => idx !== i) })}
                                aria-label={`Remove fact ${i + 1}`}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            )}
                          </div>
                          <Textarea
                            rows={2}
                            maxLength={2000}
                            aria-label={`Fact ${i + 1}`}
                            value={f.text}
                            onChange={(e) => updateFact(i, { text: e.target.value })}
                            placeholder="The library held an estimated 40,000 scrolls in 48 BC."
                          />
                          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_160px]">
                            <Input
                              aria-label={`Source for fact ${i + 1}`}
                              maxLength={1000}
                              value={f.source}
                              onChange={(e) => updateFact(i, { source: e.target.value })}
                              placeholder="Source URL or citation"
                            />
                            <Input
                              aria-label={`Date for fact ${i + 1}`}
                              maxLength={40}
                              value={f.date}
                              onChange={(e) => updateFact(i, { date: e.target.value })}
                              placeholder="Date"
                            />
                          </div>
                        </li>
                      ))}
                    </ol>
                    {draft.facts.length < 60 && (
                      <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => set({ facts: [...draft.facts, { ...EMPTY_FACT }] })}>
                        <Plus className="h-3.5 w-3.5" /> Add fact
                      </Button>
                    )}
                  </fieldset>
                  <div>
                    <FieldLabel htmlFor="fn-title" hint="optional, the script suggests one">Working title</FieldLabel>
                    <Input id="fn-title" value={draft.title} onChange={(e) => set({ title: e.target.value })} maxLength={200} />
                  </div>
                </div>
              )}

              {step === 2 && template && (
                <div className="mt-4 space-y-6">
                  <div>
                    <FieldLabel>Aspect</FieldLabel>
                    <PillGroup<FacelessAspect>
                      label="Aspect ratio"
                      value={draft.aspect}
                      onChange={(aspect) => {
                        const b = lengthBounds(template, aspect);
                        set({ aspect, lengthSeconds: Math.min(b.max, Math.max(b.min, draft.lengthSeconds)) });
                      }}
                      options={template.aspects.map((a) => ({
                        value: a,
                        label: (
                          <>
                            <AspectGlyph aspect={a} /> {a}
                          </>
                        ),
                        hint: `Up to ${formatDuration(FACELESS_MAX_SECONDS[a])}`,
                      }))}
                    />
                  </div>
                  <div>
                    <FieldLabel hint={`${formatDuration(bounds.min)} to ${formatDuration(bounds.max)}`}>Length</FieldLabel>
                    <div className="flex items-center gap-4">
                      <Slider
                        value={[draft.lengthSeconds]}
                        min={bounds.min}
                        max={bounds.max}
                        step={bounds.step}
                        onValueChange={([v]) => set({ lengthSeconds: v })}
                        aria-label="Target length in seconds"
                        className="flex-1"
                      />
                      <span className="w-20 text-right font-mono text-2xl font-medium tabular text-foreground">{formatDuration(draft.lengthSeconds)}</span>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">
                      About {words} words at {wpm} wpm. The recorded voice sets the final timing.
                    </p>
                  </div>
                  <div className="max-w-xs">
                    <FieldLabel htmlFor="fn-lang">Language</FieldLabel>
                    <Select value={draft.language} onValueChange={(language) => set({ language })}>
                      <SelectTrigger id="fn-lang">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {FACELESS_LANGUAGES.map((l) => (
                          <SelectItem key={l.code} value={l.code}>
                            {l.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}

              {step === 3 && template && (
                <div className="mt-4 space-y-6">
                  <div>
                    <FieldLabel hint="appended to every image prompt">Visual style</FieldLabel>
                    <div role="radiogroup" aria-label="Visual style" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {styles.map((s) => {
                        const active = s.id === draft.style;
                        const prompt = s.id === 'template' ? template.visual_style : s.prompt;
                        return (
                          <button
                            key={s.id}
                            type="button"
                            role="radio"
                            aria-checked={active}
                            onClick={() => set({ style: s.id })}
                            className={cn(
                              'rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                              active ? 'border-primary/60 bg-primary/10' : 'border-border bg-secondary/30 hover:border-foreground/30',
                            )}
                          >
                            <span className="block text-sm font-medium text-foreground">{s.label}</span>
                            <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{prompt}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div>
                    <FieldLabel hint={template.voice.description || undefined}>Narrator voice</FieldLabel>
                    {voices.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Voices load with the catalog.</p>
                    ) : (
                      <VoiceGrid
                        voices={voices}
                        value={draft.voiceId}
                        onChange={(voiceId) => set({ voiceId })}
                        suggested={template.voice.suggested_voices}
                      />
                    )}
                    <p className="mt-2 text-xs text-muted-foreground">
                      Stock Eleven v4 voices. Each character can have its own voice in the cast library.
                    </p>
                  </div>
                </div>
              )}

              {step === 4 && template && (
                <div className="mt-4 space-y-6">
                  <div>
                    <FieldLabel hint={template.dialogue_mode !== 'narration' ? 'this template is character led' : 'optional'}>Cast</FieldLabel>
                    <CastPicker characters={characters} voices={voices} value={draft.cast} onChange={(cast) => set({ cast })} />
                  </div>
                  <div>
                    <FieldLabel>Series</FieldLabel>
                    <PillGroup<SeriesMode>
                      label="Series"
                      value={draft.seriesMode}
                      onChange={(seriesMode) => set({ seriesMode })}
                      options={[
                        { value: 'none', label: 'Standalone' },
                        { value: 'existing', label: 'Add to a series', disabled: series.length === 0 },
                        { value: 'new', label: 'Start a series' },
                      ]}
                    />
                    {draft.seriesMode === 'existing' && (
                      <div className="mt-3 max-w-sm">
                        <Select
                          value={draft.seriesId ? String(draft.seriesId) : undefined}
                          onValueChange={(v) => {
                            const s = series.find((x) => x.id === Number(v));
                            set({
                              seriesId: Number(v),
                              cast: draft.cast.length === 0 && s ? s.cast_ids.filter((id) => !blockedCast.has(id)).slice(0, 6) : draft.cast,
                            });
                          }}
                        >
                          <SelectTrigger aria-label="Series">
                            <SelectValue placeholder="Choose a series" />
                          </SelectTrigger>
                          <SelectContent>
                            {series.map((s) => (
                              <SelectItem key={s.id} value={String(s.id)}>
                                {s.title}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    {draft.seriesMode === 'new' && (
                      <div className="mt-3 max-w-sm">
                        <Input
                          aria-label="New series title"
                          placeholder="Series title"
                          value={draft.newSeriesTitle}
                          onChange={(e) => set({ newSeriesTitle: e.target.value })}
                          maxLength={200}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {step === 5 && template && (
                <div className="mt-4 space-y-4">
                  <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <ReviewItem label="Template" value={template.name} onEdit={() => setStep(0)} />
                    <ReviewItem
                      label="Format"
                      value={`${draft.aspect}, ${formatDuration(draft.lengthSeconds)}, ${FACELESS_LANGUAGES.find((l) => l.code === draft.language)?.label ?? draft.language}`}
                      onEdit={() => setStep(2)}
                    />
                    <ReviewItem label={template.fact_mode ? 'Topic' : 'Idea'} value={draft.idea} onEdit={() => setStep(1)} wide />
                    <ReviewItem label="Facts" value={`${filledFacts(draft.facts).length} with ${filledFacts(draft.facts).filter((f) => f.source.trim()).length} sources`} onEdit={() => setStep(1)} />
                    <ReviewItem label="Narrator" value={draft.voiceId ?? 'Default'} onEdit={() => setStep(3)} />
                    <ReviewItem label="Style" value={styleLabel} onEdit={() => setStep(3)} />
                    <div className="rounded-lg border border-border bg-secondary/30 p-3">
                      <dt className="text-xs font-medium text-muted-foreground">Cast</dt>
                      <dd className="mt-2 flex flex-wrap gap-1.5">
                        {draft.cast.length === 0 ? (
                          <span className="text-sm text-muted-foreground">Narration only</span>
                        ) : (
                          draft.cast.map((id) => {
                            const c = characters.find((x) => x.id === id);
                            return (
                              <span key={id} className="inline-flex items-center gap-1.5 rounded-full border border-border py-0.5 pl-0.5 pr-2 text-xs">
                                <CharacterAvatar character={c} size={20} />
                                {c?.name ?? `#${id}`}
                              </span>
                            );
                          })
                        )}
                      </dd>
                    </div>
                    <ReviewItem
                      label="Series"
                      value={
                        draft.seriesMode === 'new'
                          ? `New: ${draft.newSeriesTitle}`
                          : draft.seriesMode === 'existing'
                            ? series.find((s) => s.id === draft.seriesId)?.title ?? ''
                            : 'Standalone'
                      }
                      onEdit={() => setStep(4)}
                    />
                  </dl>
                  <p className="text-sm text-muted-foreground">
                    Next the studio drafts the script. You edit it, check originality and compliance, then
                    produce step by step with an estimate before each paid step.
                  </p>
                  <ErrorNote>{error}</ErrorNote>
                </div>
              )}

              <div className="mt-8 flex items-center justify-between gap-2 border-t border-border pt-4">
                <Button variant="outline" onClick={back} disabled={step === 0 || creating}>
                  <ArrowLeft className="h-4 w-4" /> Back
                </Button>
                {step < STEPS.length - 1 ? (
                  <Button onClick={next} disabled={!stepValid[step]}>
                    Next <ArrowRight className="h-4 w-4" />
                  </Button>
                ) : (
                  <Button size="lg" onClick={create} disabled={creating || firstInvalid !== -1}>
                    {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                    {creating ? 'Creating the project' : 'Create and draft script'}
                  </Button>
                )}
              </div>
            </section>
          </div>
        </StaggerItem>
      </Stagger>
    </>
  );
}

function TemplateSummary({ template }: { template: FacelessTemplate }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Kicker>Template</Kicker>
        <span className="text-sm">{template.name}</span>
        {template.fact_mode && <TechChip>Fact mode</TechChip>}
      </div>
      <BeatStrip beats={template.beats} seconds={template.length.default_seconds} className="mt-2" />
      {template.policy_notes.length > 0 && (
        <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
          {template.policy_notes.slice(0, 3).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewItem({ label, value, onEdit, wide }: { label: string; value: string; onEdit: () => void; wide?: boolean }) {
  return (
    <div className={cn('rounded-lg border border-border bg-secondary/30 p-3', wide && 'sm:col-span-2')}>
      <div className="flex items-center justify-between gap-2">
        <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
        <button type="button" onClick={onEdit} className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Edit<span className="sr-only"> {label}</span>
        </button>
      </div>
      <dd className="mt-1 line-clamp-3 text-sm">{value || '--'}</dd>
    </div>
  );
}
