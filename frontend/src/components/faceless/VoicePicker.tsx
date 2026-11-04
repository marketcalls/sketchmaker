import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { FacelessVoice } from '@/api/faceless';

// GET /voices returns stock Eleven v4 voices by name with gender, accent and
// tone; it offers no preview samples, so the studio describes each voice.
export function voiceMeta(v: FacelessVoice): string {
  return [v.gender, v.accent, v.tone].filter(Boolean).join(', ');
}

export function VoiceSelect({
  voices,
  value,
  onChange,
  label,
  placeholder = 'Choose a voice',
  allowNone,
  disabled,
  id,
}: {
  voices: FacelessVoice[];
  value: string | null;
  onChange: (id: string | null) => void;
  label: string;
  placeholder?: string;
  allowNone?: string;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <Select value={value ?? '__none'} onValueChange={(v) => onChange(v === '__none' ? null : v)} disabled={disabled}>
      <SelectTrigger id={id} aria-label={label} className="min-w-0">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowNone && <SelectItem value="__none">{allowNone}</SelectItem>}
        {voices.map((v) => (
          <SelectItem key={v.id} value={v.id}>
            <span>{v.id}</span>
            <span className="ml-2 text-[11px] text-muted-foreground">{voiceMeta(v)}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// Grid of voice cards for the wizard; suggested voices first.
export function VoiceGrid({
  voices,
  value,
  onChange,
  suggested = [],
}: {
  voices: FacelessVoice[];
  value: string | null;
  onChange: (id: string) => void;
  suggested?: string[];
}) {
  const ordered = [...voices].sort(
    (a, b) => Number(suggested.includes(b.id)) - Number(suggested.includes(a.id)),
  );
  return (
    <div role="radiogroup" aria-label="Narrator voice" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {ordered.map((v) => {
        const active = v.id === value;
        return (
          <button
            key={v.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(v.id)}
            className={cn(
              'flex min-h-14 flex-col justify-center rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              active ? 'border-primary/60 bg-primary/10' : 'border-border bg-secondary/30 hover:border-foreground/30',
            )}
          >
            <span className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">{v.id}</span>
              {suggested.includes(v.id) && (
                <span className="rounded-md border border-border px-1.5 text-[11px] text-muted-foreground">
                  Suggested
                </span>
              )}
            </span>
            <span className="block truncate text-[11px] text-muted-foreground">{voiceMeta(v)}</span>
          </button>
        );
      })}
    </div>
  );
}
