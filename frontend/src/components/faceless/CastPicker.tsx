import { useState } from 'react';
import { Check, Plus, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MAX_CAST, type FacelessCharacter, type FacelessVoice } from '@/api/faceless';
import { CharacterAvatar } from './CharacterCard';
import { CharacterEditorDialog } from './CharacterEditorDialog';

// Choose up to MAX_CAST characters from the library, or create one inline.
export function CastPicker({
  characters,
  voices,
  value,
  onChange,
}: {
  characters: FacelessCharacter[];
  voices: FacelessVoice[];
  value: number[];
  onChange: (ids: number[]) => void;
}) {
  const [creating, setCreating] = useState(false);
  const active = characters.filter((c) => !c.is_archived);
  const full = value.length >= MAX_CAST;

  // A blocked character keeps its label but cannot be added: the backend would
  // refuse it at the quote. One already chosen can still be taken off.
  const toggle = (c: FacelessCharacter) => {
    if (value.includes(c.id)) onChange(value.filter((v) => v !== c.id));
    else if (!full && c.can_generate) onChange([...value, c.id]);
  };

  return (
    <div>
      <p className="mb-3 font-mono text-[11px] text-muted-foreground" aria-live="polite">
        {value.length} of {MAX_CAST} cast
      </p>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" aria-label="Your characters">
        {active.map((c) => {
          const on = value.includes(c.id);
          return (
            <li key={c.id}>
              <button
                type="button"
                aria-pressed={on}
                disabled={!on && (full || !c.can_generate)}
                title={c.can_generate ? undefined : c.block_reason ?? undefined}
                onClick={() => toggle(c)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-lg border p-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40',
                  on ? 'border-primary/60 bg-primary/10' : 'border-border bg-secondary/30 hover:border-foreground/30',
                )}
              >
                <CharacterAvatar character={c} size={36} />
                <span className="min-w-0 flex-1">
                  <span className={cn('block truncate text-sm', on && 'font-medium text-foreground')}>{c.name}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">
                    {!c.can_generate ? 'Blocked' : c.kind === 'real_person' ? 'Real person' : c.bible ? 'Bible ready' : 'No bible yet'}
                  </span>
                </span>
                {on && <Check className="h-4 w-4 shrink-0 text-foreground" aria-hidden="true" />}
              </button>
            </li>
          );
        })}
        <li>
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex h-full min-h-[54px] w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border p-2 text-sm text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Plus className="h-4 w-4" aria-hidden="true" /> New character
          </button>
        </li>
      </ul>
      {active.length === 0 && (
        <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <Users className="h-3.5 w-3.5" aria-hidden="true" />
          No characters yet. Faceless formats work without one; recurring characters build a series.
        </p>
      )}
      <CharacterEditorDialog
        open={creating}
        onOpenChange={setCreating}
        character={null}
        voices={voices}
        onSaved={(c) => {
          if (c.can_generate && !value.includes(c.id) && value.length < MAX_CAST) onChange([...value, c.id]);
        }}
      />
    </div>
  );
}
