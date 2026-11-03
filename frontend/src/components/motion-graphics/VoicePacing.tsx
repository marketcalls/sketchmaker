import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import type { MGSpec, Pronunciation } from '@/api/motionGraphics';
import { FieldLabel } from './shared';

const MAX_RULES = 30;

// Pause tightening and the pronunciation list: what the voice says for a
// word written differently on screen (captions keep the written form).
export function VoicePacing({ spec, onSpec }: { spec: MGSpec; onSpec: (fn: (s: MGSpec) => MGSpec) => void }) {
  const rules = spec.pronunciations ?? [];
  const setRules = (next: Pronunciation[]) => onSpec((s) => ({ ...s, pronunciations: next }));
  const setRule = (i: number, patch: Partial<Pronunciation>) =>
    setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div className="space-y-3 border-t border-border pt-3">
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Switch
          checked={spec.options.tight_pauses ?? true}
          onCheckedChange={(v) => onSpec((s) => ({ ...s, options: { ...s.options, tight_pauses: v } }))}
        />
        Tighten pauses to about 0.3 s
      </label>
      <div>
        <FieldLabel hint={`${rules.length} of ${MAX_RULES}`}>Pronunciations</FieldLabel>
        <div className="space-y-2">
          {rules.map((r, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2">
              <Input
                value={r.written}
                maxLength={40}
                placeholder="On screen, like API"
                aria-label="Written form"
                onChange={(e) => setRule(i, { written: e.target.value })}
              />
              <Input
                value={r.spoken}
                maxLength={80}
                placeholder="Spoken, like A P I"
                aria-label="Spoken form"
                onChange={(e) => setRule(i, { spoken: e.target.value })}
              />
              <Button variant="ghost" size="icon" aria-label="Remove" onClick={() => setRules(rules.filter((_, j) => j !== i))}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            disabled={rules.length >= MAX_RULES}
            onClick={() => setRules([...rules, { written: '', spoken: '' }])}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" /> Add pronunciation
          </Button>
        </div>
      </div>
    </div>
  );
}
