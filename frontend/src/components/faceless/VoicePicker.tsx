import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { FacelessVoice } from '@/api/faceless';

// GET /voices returns stock Eleven v4 voices by name with gender, accent and
// tone; it offers no preview samples, so the studio describes each voice.
function voiceMeta(v: FacelessVoice): string {
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
