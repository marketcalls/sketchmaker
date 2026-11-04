import { Archive, ArchiveRestore, MoreVertical, Pencil, ShieldAlert, Trash2, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import type { FacelessCharacter, FacelessVoice } from '@/api/faceless';
import { MutedChip, TechChip } from './shared';

// The first reference image, else an extracted frame, else the sheet.
export function characterImage(c: Pick<FacelessCharacter, 'media'>): string | null {
  const images = c.media.filter((m) => m.kind === 'image' && m.url);
  const pick =
    images.find((m) => m.role === 'reference') ?? images.find((m) => m.role === 'frame') ?? images[0];
  return pick?.url ?? null;
}

export function characterDescription(c: FacelessCharacter): string {
  return c.bible?.canonical_description || c.personality || c.notes || '';
}

export function CharacterAvatar({
  character,
  size = 32,
  className,
}: {
  character: Pick<FacelessCharacter, 'name' | 'media'> | null | undefined;
  size?: number;
  className?: string;
}) {
  const src = character ? characterImage(character) : null;
  const initials = (character?.name ?? '?')
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-secondary font-mono text-[10px] text-muted-foreground',
        className,
      )}
      style={{ width: size, height: size }}
      title={character?.name}
    >
      {src ? <img src={src} alt="" className="h-full w-full object-cover" loading="lazy" /> : initials}
    </span>
  );
}

export function CharacterCard({
  character,
  voices,
  onEdit,
  onToggleArchive,
  onDelete,
}: {
  character: FacelessCharacter;
  voices: FacelessVoice[];
  onEdit: (c: FacelessCharacter) => void;
  onToggleArchive: (c: FacelessCharacter) => void;
  onDelete: (c: FacelessCharacter) => void;
}) {
  const img = characterImage(character);
  const voice = voices.find((v) => v.id === character.voice_id);
  const flagged = character.safety_flags.filter((f) => f.confidence >= 0.4);
  const imageCount = character.media.filter((m) => m.kind === 'image' && m.role !== 'sheet').length;
  const hasSheet = character.media.some((m) => m.role === 'sheet');
  const description = characterDescription(character);

  return (
    <article
      className={cn(
        'relative flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card transition-colors duration-150 hover:border-foreground/20',
        character.is_archived && 'opacity-60',
      )}
    >
      <button
        type="button"
        onClick={() => onEdit(character)}
        className="relative aspect-[4/5] w-full overflow-hidden bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        aria-label={`Edit ${character.name}`}
      >
        {img ? (
          <img src={img} alt="" className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <span className="flex h-full w-full items-center justify-center">
            <UserRound className="h-10 w-10 text-muted-foreground/50" aria-hidden="true" />
          </span>
        )}
        <span className="absolute left-3 top-3 flex flex-wrap gap-1">
          {character.kind === 'real_person' && <TechChip className="bg-background/80">Real person</TechChip>}
          {character.is_archived && <MutedChip className="bg-background/70">Archived</MutedChip>}
          {!character.is_archived && !character.can_generate && (
            <MutedChip className="border-warning/40 bg-background/70 text-warning">Blocked</MutedChip>
          )}
        </span>
        {flagged.length > 0 && (
          <span
            className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-md border border-warning/40 bg-background/80 px-2 py-0.5 text-[11px] tabular text-warning"
            title={flagged.map((f) => f.note || f.kind.replace(/_/g, ' ')).join(', ')}
          >
            <ShieldAlert className="h-3 w-3" aria-hidden="true" />
            {flagged.length}
            <span className="sr-only">safety flags</span>
          </span>
        )}
      </button>
      <div className="flex items-start gap-2 p-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold leading-tight">{character.name}</h3>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
            {description || 'No character bible yet'}
          </p>
          <p className="mt-2 text-[11px] text-muted-foreground">
            {imageCount} ref{imageCount === 1 ? '' : 's'}
            {hasSheet && ' / sheet'}
            {voice && <> / {voice.id}</>}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" aria-label={`Actions for ${character.name}`}>
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => onEdit(character)}>
              <Pencil className="mr-2 h-4 w-4" /> Edit
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => onToggleArchive(character)}>
              {character.is_archived ? (
                <>
                  <ArchiveRestore className="mr-2 h-4 w-4" /> Restore
                </>
              ) : (
                <>
                  <Archive className="mr-2 h-4 w-4" /> Archive
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => onDelete(character)}>
              <Trash2 className="mr-2 h-4 w-4" /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </article>
  );
}
