import { useState } from 'react';
import { FileText } from 'lucide-react';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import {
  AD_OBJECTIVES, MAX_HOOK_VARIANTS, PLAN_CHECK_PREFIX, STORY_ASPECTS, STORY_REGISTERS, TARGET_SECONDS_MAX,
  TARGET_SECONDS_MIN, emptyAdBrief, enumLabel, formatRuntime, storyRuntime,
  type AdBrief, type AdObjective, type Look, type StoryDoc, type StoryFormat, type StoryRegister,
} from '@/api/storyRoom';
import { cn } from '@/lib/utils';
import { CopyButton, EditableText, FieldLabel, InlineSelect, Treatment } from './fields';

const REGISTER_HINTS: Record<StoryRegister, string> = {
  cinematic: 'A produced film or commercial.',
  ugc: 'A person talking into their own phone: available light, real rooms, no cinematic moves.',
  documentary: 'Observational and unposed, in available light.',
  animated: 'Animated in the visual style below.',
};

const LOOK_FIELDS: { id: Exclude<keyof Look, 'register'>; label: string }[] = [
  { id: 'visual_style', label: 'Visual style' },
  { id: 'palette', label: 'Palette' },
  { id: 'lighting', label: 'Lighting' },
  { id: 'camera_feel', label: 'Camera feel' },
  { id: 'music', label: 'Music' },
];

type AdTextField = 'product' | 'brand' | 'offer' | 'key_message' | 'cta' | 'creativity';

const AD_FIELDS: { id: AdTextField; label: string }[] = [
  { id: 'product', label: 'Product' },
  { id: 'brand', label: 'Brand' },
  { id: 'offer', label: 'Offer' },
  { id: 'key_message', label: 'Key message' },
  { id: 'cta', label: 'Call to action' },
  { id: 'creativity', label: 'Creativity (on-code, twist, wild)' },
];

const lines = (v: string, max?: number) => {
  const out = v.split('\n').map((x) => x.trim()).filter(Boolean);
  return max ? out.slice(0, max) : out;
};

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-base font-semibold">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Story tab: the treatment first, then the brief, look and ad brief, all editable. */
export function StoryTab({ story, disabled, onAnswer }: { story: StoryDoc; disabled: boolean; onAnswer: (q: string) => void }) {
  const editStory = useStoryRoomStore((s) => s.editStory);
  const registers = useStoryRoomStore((s) => s.config?.enums.registers ?? STORY_REGISTERS);
  const objectives = useStoryRoomStore((s) => s.config?.enums.objectives ?? AD_OBJECTIVES);
  const [lengthDraft, setLengthDraft] = useState<string | null>(null);
  const edit = (patch: Partial<StoryDoc>) => editStory((d) => ({ ...d, ...patch }));
  const editAd = (patch: Partial<AdBrief>) => edit({ ad: { ...emptyAdBrief(), ...(story.ad ?? {}), ...patch } });
  const runtime = storyRuntime(story);
  const treatment = (story.treatment ?? '').trim();
  const register: StoryRegister = story.look?.register ?? 'cinematic';
  const questions = story.open_questions ?? [];

  const commitLength = () => {
    if (lengthDraft === null) return;
    const n = Math.round(Number(lengthDraft));
    setLengthDraft(null);
    if (!Number.isFinite(n)) return;
    const clamped = Math.min(TARGET_SECONDS_MAX, Math.max(TARGET_SECONDS_MIN, n));
    if (clamped !== story.target_seconds) edit({ target_seconds: clamped });
  };

  return (
    <div className="space-y-5">
      {/* Treatment: the production prompt everything else is made from */}
      <section className="panel rounded-xl border border-border p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">Treatment</h3>
            <p className="mt-0.5 text-[11px] tabular text-muted-foreground">
              {story.aspect}, {formatRuntime(story.target_seconds)} target, {formatRuntime(runtime)} cut
            </p>
          </div>
          <CopyButton text={treatment} />
        </div>
        {treatment ? (
          <Treatment text={treatment} />
        ) : (
          <div className="flex flex-col items-center py-8 text-center">
            <FileText className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            <p className="mt-3 text-base font-semibold">No treatment yet</p>
            <p className="mt-1 max-w-xs text-sm text-muted-foreground">
              Send a short brief in the chat. The director writes the full treatment in its first reply.
            </p>
          </div>
        )}
      </section>

      {questions.length > 0 && (
        <section className="rounded-xl border border-border bg-secondary/20 p-4">
          <p className="mb-2 text-xs font-medium text-muted-foreground">Assumptions and open questions</p>
          <ul className="space-y-2">
            {questions.map((q, i) => {
              // The app's plan checks: shown as warnings, refreshed after every reply and edit.
              const check = q.startsWith(PLAN_CHECK_PREFIX);
              const text = check ? q.slice(PLAN_CHECK_PREFIX.length) : q;
              return (
                <li key={i} className="flex items-start justify-between gap-3 text-sm">
                  <span className={cn(check ? 'text-warning' : 'text-foreground/90')}>
                    {check && <span className="mr-1.5 text-xs font-medium">Check:</span>}
                    {text}
                  </span>
                  <button
                    type="button"
                    onClick={() => onAnswer(text)}
                    className="shrink-0 text-xs text-foreground underline-offset-4 hover:underline"
                  >
                    {check ? 'Fix' : 'Answer'}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <Section title="Brief">
        <div className="space-y-2">
          <EditableText label="Title" value={story.title} disabled={disabled} maxLength={200} onCommit={(title) => edit({ title })} />
          <EditableText label="Logline" value={story.logline} multiline disabled={disabled} onCommit={(logline) => edit({ logline })} />
          <EditableText label="Synopsis" value={story.synopsis} multiline rows={3} disabled={disabled} onCommit={(synopsis) => edit({ synopsis })} />
          <div className="grid grid-cols-3 gap-2 px-2">
            <InlineSelect<StoryFormat>
              label="Format"
              value={story.format}
              options={['story', 'ad']}
              render={(v) => (v === 'ad' ? 'Ad' : 'Story')}
              disabled={disabled}
              onChange={(format) => edit({ format, ad: format === 'ad' ? { ...emptyAdBrief(), ...(story.ad ?? {}) } : story.ad })}
            />
            <InlineSelect
              label="Aspect"
              value={story.aspect}
              options={STORY_ASPECTS}
              disabled={disabled}
              onChange={(aspect) => edit({ aspect })}
            />
            <label className="block min-w-0">
              <FieldLabel>Length (s)</FieldLabel>
              <input
                type="number"
                inputMode="numeric"
                min={TARGET_SECONDS_MIN}
                max={TARGET_SECONDS_MAX}
                value={lengthDraft ?? String(story.target_seconds)}
                disabled={disabled}
                onChange={(e) => setLengthDraft(e.target.value)}
                onBlur={commitLength}
                onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
                className="h-8 w-full rounded-md border border-input bg-secondary/40 px-2 font-mono text-xs text-foreground focus-visible:border-ring focus-visible:outline-none disabled:opacity-60"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-x-2">
            <EditableText label="Genre" value={story.genre} disabled={disabled} onCommit={(genre) => edit({ genre })} />
            <EditableText label="Tone" value={story.tone} disabled={disabled} onCommit={(tone) => edit({ tone })} />
            <EditableText label="Audience" value={story.audience} disabled={disabled} onCommit={(audience) => edit({ audience })} />
            <EditableText label="Language" value={story.language} disabled={disabled} maxLength={20} onCommit={(language) => edit({ language })} />
          </div>
        </div>
      </Section>

      {story.format === 'ad' && (
        <Section title="Ad brief">
          <div className="mb-2 px-2">
            <InlineSelect<AdObjective>
              label="Objective"
              value={story.ad?.objective ?? 'consideration'}
              options={objectives}
              render={enumLabel}
              disabled={disabled}
              onChange={(objective) => editAd({ objective })}
            />
          </div>
          <div className="space-y-1">
            <EditableText
              label="Proposition (the one reason to buy)"
              multiline
              rows={1}
              value={story.ad?.proposition ?? ''}
              disabled={disabled}
              onCommit={(proposition) => editAd({ proposition })}
            />
            <EditableText
              label="Audience mindset"
              multiline
              rows={1}
              value={story.ad?.audience_mindset ?? ''}
              disabled={disabled}
              onCommit={(audience_mindset) => editAd({ audience_mindset })}
            />
          </div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1">
            {AD_FIELDS.map((f) => (
              <EditableText
                key={f.id}
                label={f.label}
                value={story.ad?.[f.id] ?? ''}
                disabled={disabled}
                onCommit={(v) => editAd({ [f.id]: v })}
              />
            ))}
          </div>
          <div className="mt-1 space-y-1">
            <EditableText
              label={`Hook alternates (one per line, up to ${MAX_HOOK_VARIANTS})`}
              multiline
              value={(story.ad?.hook_variants ?? []).join('\n')}
              disabled={disabled}
              onCommit={(v) => editAd({ hook_variants: lines(v, MAX_HOOK_VARIANTS) })}
            />
            <EditableText
              label="Mandatories (one per line)"
              multiline
              value={(story.ad?.mandatories ?? []).join('\n')}
              disabled={disabled}
              onCommit={(v) => editAd({ mandatories: lines(v) })}
            />
          </div>
        </Section>
      )}

      <Section title="Look">
        <div className="mb-2 px-2">
          <InlineSelect<StoryRegister>
            label="Register"
            value={register}
            options={registers}
            render={enumLabel}
            disabled={disabled}
            onChange={(v) => edit({ look: { ...story.look, register: v } })}
          />
          <p className="mt-1 text-xs text-muted-foreground">{REGISTER_HINTS[register]}</p>
        </div>
        <div className="space-y-1">
          {LOOK_FIELDS.map((f) => (
            <EditableText
              key={f.id}
              label={f.label}
              multiline
              rows={1}
              value={story.look?.[f.id] ?? ''}
              disabled={disabled}
              onCommit={(v) => edit({ look: { ...story.look, [f.id]: v } })}
            />
          ))}
        </div>
      </Section>
    </div>
  );
}
