import { useMemo, useState } from 'react';
import { BookOpenCheck, Check, Clock, LayoutTemplate } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FacelessTemplate, TemplateBeat } from '@/api/faceless';
import { AspectGlyph, EmptyState, MutedChip, PillGroup, TechChip, formatDuration, formatLengthRange } from './shared';

// A template's beats as proportional segments (beat start and end are
// fractions of the runtime), with timings at the default length.
export function BeatStrip({ beats, seconds, className }: { beats: TemplateBeat[]; seconds: number; className?: string }) {
  if (beats.length === 0) return null;
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex h-2 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
        {beats.map((b, i) => (
          <span
            key={b.id}
            title={`${b.name}: ${b.job}`}
            className={cn(
              'h-full rounded-[2px]',
              i === 0 ? 'bg-foreground/60' : b.rehook ? 'bg-foreground/40' : 'bg-foreground/20',
            )}
            style={{ flexGrow: Math.max(b.end - b.start, 0.01), flexBasis: 0 }}
          />
        ))}
      </div>
      <ol className="flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground" aria-label="Beats">
        {beats.map((b, i) => (
          <li key={b.id} title={b.job}>
            {b.name}
            <span className="font-mono tabular opacity-60"> {formatDuration(b.start * seconds)}</span>
            {i < beats.length - 1 && <span className="ml-2 opacity-40">/</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function templateFormat(t: FacelessTemplate): 'shorts' | 'long' {
  return t.shorts ? 'shorts' : 'long';
}

export function TemplateCard({
  template,
  selected,
  onSelect,
}: {
  template: FacelessTemplate;
  selected?: boolean;
  onSelect: (t: FacelessTemplate) => void;
}) {
  const hook = template.hook_formulas[0];
  return (
    <button
      type="button"
      onClick={() => onSelect(template)}
      aria-pressed={selected}
      className={cn(
        'relative flex h-full flex-col rounded-xl border bg-card p-4 text-left shadow-card transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        selected ? 'border-primary/60 bg-primary/10' : 'border-border hover:border-foreground/20',
      )}
    >
      {selected && (
        <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Check className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="sr-only">Selected</span>
        </span>
      )}
      <div className="mb-2 flex flex-wrap items-center gap-1.5 pr-8">
        <MutedChip>{template.niche}</MutedChip>
        <MutedChip>{template.shorts ? 'Shorts' : 'Long-form'}</MutedChip>
        {template.dialogue_mode !== 'narration' && <MutedChip>Dialogue</MutedChip>}
        {template.fact_mode && (
          <TechChip>
            <BookOpenCheck className="h-3 w-3" aria-hidden="true" />
            Fact mode
          </TechChip>
        )}
      </div>
      <h3 className="text-base font-semibold leading-tight">{template.name}</h3>
      <p className="mt-1.5 text-sm text-muted-foreground">{template.pitch}</p>
      {hook && (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">Hook: </span>
          {hook}
        </p>
      )}
      <div className="mt-auto pt-4">
        <BeatStrip beats={template.beats} seconds={template.length.default_seconds} className="mb-3" />
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" aria-hidden="true" />
            <span className="font-mono tabular">{formatLengthRange(template.length.min_seconds, template.length.max_seconds)}</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            {template.aspects.map((a) => (
              <span key={a} className="inline-flex items-center" title={a}>
                <AspectGlyph aspect={a} />
                <span className="sr-only">{a}</span>
              </span>
            ))}
          </span>
          <span><span className="font-mono tabular">{template.voice.wpm}</span> wpm</span>
        </div>
      </div>
    </button>
  );
}

type FormatFilter = 'all' | 'shorts' | 'long';

export function TemplateGallery({
  templates,
  selectedId,
  onSelect,
}: {
  templates: FacelessTemplate[];
  selectedId?: string | null;
  onSelect: (t: FacelessTemplate) => void;
}) {
  const [niche, setNiche] = useState<string>('all');
  const [format, setFormat] = useState<FormatFilter>('all');

  const niches = useMemo(() => Array.from(new Set(templates.map((t) => t.niche))).sort(), [templates]);
  const shown = templates.filter(
    (t) => (niche === 'all' || t.niche === niche) && (format === 'all' || templateFormat(t) === format),
  );

  return (
    <div>
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <PillGroup<FormatFilter>
          label="Format"
          value={format}
          onChange={setFormat}
          options={[
            { value: 'all', label: 'All formats' },
            { value: 'shorts', label: 'Shorts' },
            { value: 'long', label: 'Long-form' },
          ]}
        />
        <div role="radiogroup" aria-label="Niche" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
          {['all', ...niches].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={niche === n}
              onClick={() => setNiche(n)}
              className={cn(
                'shrink-0 rounded-md border px-3 py-1.5 text-xs capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                niche === n
                  ? 'border-primary/60 bg-primary/10 text-foreground'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {n === 'all' ? 'All niches' : n}
            </button>
          ))}
        </div>
      </div>
      {shown.length === 0 ? (
        <EmptyState icon={LayoutTemplate} title="No templates match">
          Try another niche or format.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((t) => (
            <TemplateCard key={t.id} template={t} selected={t.id === selectedId} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}
