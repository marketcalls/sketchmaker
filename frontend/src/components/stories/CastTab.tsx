import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BookmarkPlus, Check, ChevronDown, ImagePlus, Library, Loader2, Plus, RefreshCw, Search, Trash2, Upload, Wand2, X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { assetsApi } from '@/api/assets';
import {
  storyRoomApi, imageProgress, ENVIRONMENT_MAX_PHOTOS, ENVIRONMENT_PHOTO_ACCEPT,
  type CastEntry, type EnvEntry, type StoryDoc, type StoryEnvironment,
} from '@/api/storyRoom';
import type { FacelessCharacter } from '@/api/faceless';
import {
  useStoryRoomStore, castDraftKey, CAST_IMAGE_COUNT, CAST_IMAGE_RESOLUTION, type CastDraft,
} from '@/stores/storyRoomStore';
import { useFacelessStore } from '@/stores/facelessStore';
import { formatUsd, imageKey, usePricingStore } from '@/stores/pricingStore';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { Chip, EditableText } from './fields';
import { ProductsPanel } from './ProductsPanel';

// Image models offered for reference images: the same model ids and price
// keys as /generate (GeneratePage MODELS), limited to a few that hold a
// likeness and a wardrobe well.
const IMAGE_MODELS = [
  { value: 'google/nano-banana-2.1', label: 'Nano Banana 2.1' },
  { value: 'openai/gpt-image-2.5/sunburst/text-to-image', label: 'GPT Image 2.5' },
  { value: 'bytedance/seedream/v5/pro/text-to-image', label: 'Seedream V5 Pro' },
  { value: 'blackforestlabs/flux-3/klein/text-to-image', label: 'Flux 3 Klein' },
];
const CHARACTER_IMAGE_ASPECT = '2:3';

type CastKind = 'character' | 'environment';
type Entry = CastEntry | EnvEntry;

const EMPTY_DRAFT: CastDraft = { images: [], generating: false, error: null };

function characterThumb(c: FacelessCharacter | undefined): string | null {
  if (!c) return null;
  const media = c.media.filter((m) => m.kind === 'image' && m.url);
  return (media.find((m) => m.role === 'reference') ?? media[0])?.url ?? null;
}

function nextKey(prefix: 'c' | 'e', entries: Entry[]): string {
  const used = new Set(entries.map((e) => e.key));
  let n = entries.length + 1;
  while (used.has(`${prefix}${n}`)) n += 1;
  return `${prefix}${n}`;
}

/** Library picker: the user's Faceless characters or saved environments. */
function LibraryPicker({
  kind, open, onOpenChange, onPick,
}: {
  kind: CastKind;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPick: (refId: number) => Promise<void>;
}) {
  const { characters, charactersLoaded, loadCharacters } = useFacelessStore();
  const { environments, environmentsLoaded, loadEnvironments } = useStoryRoomStore();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (kind === 'character') loadCharacters();
    else loadEnvironments(true);
  }, [open, kind, loadCharacters, loadEnvironments]);

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rows = kind === 'character'
      ? characters.filter((c) => !c.is_archived).map((c) => ({ id: c.id, name: c.name, sub: c.role || c.bible?.canonical_description || '', thumb: characterThumb(c) }))
      : environments.filter((e) => !e.isArchived).map((e) => ({ id: e.id, name: e.name, sub: e.description, thumb: e.media[0]?.url ?? null }));
    return needle ? rows.filter((r) => `${r.name} ${r.sub}`.toLowerCase().includes(needle)) : rows;
  }, [kind, characters, environments, q]);
  const loaded = kind === 'character' ? charactersLoaded : environmentsLoaded;

  const pick = async (id: number) => {
    setBusy(id);
    setError(null);
    try {
      await onPick(id);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'That library item could not be used.'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{kind === 'character' ? 'Use a character from your library' : 'Use an environment from your library'}</DialogTitle>
          <DialogDescription>
            {kind === 'character' ? 'Your Faceless Studio characters. Their likeness and wardrobe carry into this story.' : 'Places you saved from earlier stories.'}
          </DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" className="h-9 pl-8" aria-label="Search the library" />
        </div>
        {error && <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}
        <div className="max-h-[50vh] space-y-1 overflow-y-auto">
          {!loaded && [0, 1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-3 p-2">
              <Skeleton className="h-12 w-12 shrink-0" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </div>
          ))}
          {loaded && items.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {q ? 'Nothing matches that search.' : kind === 'character'
                ? <>No characters yet. Save one from a story, or create one in <Link to="/faceless/characters" className="text-foreground underline underline-offset-4">Faceless Studio</Link>.</>
                : 'No environments yet. Save one from a story to reuse it.'}
            </p>
          )}
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={busy !== null}
              onClick={() => pick(item.id)}
              className="flex w-full items-center gap-3 rounded-lg border border-transparent p-2 text-left transition-colors hover:border-border hover:bg-secondary/40 disabled:opacity-60"
            >
              <div className="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-border bg-muted">
                {item.thumb && <img src={item.thumb} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{item.name || 'Untitled'}</p>
                {item.sub && <p className="truncate text-xs text-muted-foreground">{item.sub}</p>}
              </div>
              {busy === item.id ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : <span className="font-mono text-[10px] tabular text-muted-foreground">#{item.id}</span>}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Library photos of a saved environment, added through the media window. */
function EnvironmentPhotos({ env, disabled }: { env: StoryEnvironment; disabled: boolean }) {
  const upsertEnvironment = useStoryRoomStore((s) => s.upsertEnvironment);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const room = ENVIRONMENT_MAX_PHOTOS - env.media.length;
  const media = useMediaPicker({
    kinds: ['image'],
    accept: ENVIRONMENT_PHOTO_ACCEPT,
    multiple: room > 1,
    maxFiles: Math.max(1, room),
    title: `Add photos of ${env.name || 'this place'}`,
    description: 'PNG, JPEG or WebP up to 25 MB, at most 6 per environment.',
    disabled: disabled || uploading || room <= 0,
    onFiles: async (files) => {
      setUploading(true);
      setError(null);
      try {
        for (const file of files) upsertEnvironment(await storyRoomApi.uploadEnvironmentMedia(env.id, file));
      } catch (err) {
        setError(getErrorMessage(err, 'That photo could not be added.'));
        throw err;
      } finally {
        setUploading(false);
      }
    },
  });

  const remove = async (key: string) => {
    setError(null);
    try {
      upsertEnvironment(await storyRoomApi.deleteEnvironmentMedia(env.id, key));
    } catch (err) {
      setError(getErrorMessage(err, 'That photo could not be removed.'));
    }
  };

  return (
    <div {...media.dropProps}>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">
        Library photos <span className="font-mono font-normal tabular">{env.media.length}/{ENVIRONMENT_MAX_PHOTOS}</span>
      </p>
      <div className="flex flex-wrap gap-1.5">
        {env.media.map((m) => (
          <div key={m.key} className="group relative h-14 w-14 overflow-hidden rounded-md border border-border bg-muted">
            <img src={m.url} alt="" className="h-full w-full object-cover" />
            <button
              type="button"
              aria-label="Remove photo"
              disabled={disabled}
              onClick={() => setRemoving(m.key)}
              className="absolute right-0.5 top-0.5 rounded-full bg-background/80 p-0.5 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
            >
              <X className="h-3 w-3 text-foreground" />
            </button>
          </div>
        ))}
        {room > 0 && (
          <button
            type="button"
            onClick={media.open}
            disabled={disabled || uploading}
            className={cn(
              'flex h-14 w-14 items-center justify-center rounded-md border-2 border-dashed bg-secondary/20 text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground',
              media.dragOver ? 'border-foreground/40 bg-accent/40' : 'border-border',
            )}
            aria-label="Add photos"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
      {media.dialog}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Remove this photo?"
        description={`The photo is removed from ${env.name || 'this environment'} in your library.`}
        confirmText="Remove"
        variant="destructive"
        onConfirm={async () => {
          if (removing) await remove(removing);
        }}
      />
    </div>
  );
}

/** The reference image of one character or environment: generate, upload or pick, then approve. */
function ReferenceImage({
  kind, entry, aspect, imageModel, disabled,
}: {
  kind: CastKind;
  entry: Entry;
  aspect: string;
  imageModel: string;
  disabled: boolean;
}) {
  const { thread, castDrafts, generateCastImages, approveCastImage, clearCastImage, editStory } = useStoryRoomStore();
  const { getModelCost } = usePricingStore();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const draft = thread ? castDrafts[castDraftKey(thread.id, entry.key)] ?? EMPTY_DRAFT : EMPTY_DRAFT;
  const perImage = getModelCost(imageKey(imageModel, CAST_IMAGE_RESOLUTION));
  const price = perImage !== undefined ? perImage * CAST_IMAGE_COUNT : undefined;
  const prompt = entry.image_prompt?.trim() || entry.description?.trim() || entry.name;
  const approved = entry.image_approved && !!entry.image_url;

  const run = async (label: string, fn: () => Promise<void>, fallback: string) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(getErrorMessage(err, fallback));
      throw err;
    } finally {
      setBusy(null);
    }
  };

  // "Use my own": library picks go by asset id; uploads go to My Assets first.
  const own = useMediaPicker({
    kinds: ['image'],
    title: kind === 'character' ? `Reference image for ${entry.name || 'this character'}` : `Reference image for ${entry.name || 'this place'}`,
    description: kind === 'character'
      ? 'One person, full or three-quarter body, in the exact wardrobe.'
      : 'An empty plate of the place, no people, in the story\'s light.',
    disabled: disabled || busy !== null,
    saveUploads: false,
    onAssets: (assets) =>
      run('own', () => approveCastImage(entry.key, { assetId: assets[0].id }), 'That image could not be used.'),
    onFiles: (files) =>
      run('own', async () => {
        const asset = await assetsApi.upload(files[0]);
        await approveCastImage(entry.key, { assetId: asset.id });
      }, 'That image could not be used.'),
  });

  const setPrompt = (image_prompt: string) =>
    editStory((d) =>
      kind === 'character'
        ? { ...d, characters: d.characters.map((c) => (c.key === entry.key ? { ...c, image_prompt } : c)) }
        : { ...d, environments: d.environments.map((e) => (e.key === entry.key ? { ...e, image_prompt } : e)) },
    );

  if (approved) {
    return (
      <div className="flex gap-3">
        <div className={cn('relative shrink-0 overflow-hidden rounded-lg border-2 border-primary/60 bg-muted', kind === 'character' ? 'aspect-[2/3] w-28' : 'aspect-video w-40')}>
          <img src={entry.image_url!} alt={entry.name} className="h-full w-full object-cover" />
          <span className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded-md bg-background/85 px-1.5 py-0.5 text-[11px] text-foreground">
            <Check className="h-3 w-3 text-success" aria-hidden="true" /> Approved
          </span>
        </div>
        <div className="flex min-w-0 flex-col justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            Used as the reference in every clip {kind === 'character' ? 'this character appears in' : 'set here'}.
          </p>
          <div>
            <Button
              size="sm"
              variant="outline"
              disabled={disabled || busy !== null}
              onClick={() => run('clear', () => clearCastImage(entry.key), 'The approval could not be cleared.').catch(() => {})}
            >
              {busy === 'clear' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Change
            </Button>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2" {...own.dropProps}>
      <EditableText
        label="Image prompt"
        multiline
        rows={2}
        value={entry.image_prompt ?? ''}
        placeholder={kind === 'character'
          ? 'One person, full or three-quarter body, exact wardrobe, neutral seamless background, soft light'
          : 'An empty establishing plate of the place, no people, the story\'s lighting and time of day'}
        disabled={disabled}
        onCommit={setPrompt}
      />
      <div className="flex flex-wrap items-center gap-2 px-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={disabled || draft.generating || !prompt}
          onClick={() => generateCastImages(entry.key, { prompt, model: imageModel, aspectRatio: aspect })}
          title={`${CAST_IMAGE_COUNT} options at ${aspect}`}
        >
          {draft.generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
          {draft.generating ? 'Generating' : draft.images.length > 0 ? 'Generate again' : 'Generate image'}
          {price !== undefined && <span className="font-mono text-xs opacity-75">{formatUsd(price)}</span>}
        </Button>
        <Button size="sm" variant="outline" disabled={disabled || busy !== null} onClick={own.open}>
          {busy === 'own' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Use my own
        </Button>
      </div>

      {draft.generating && (
        <p className="px-2 text-xs text-muted-foreground" aria-live="polite">Generating {CAST_IMAGE_COUNT} options</p>
      )}
      {(draft.generating || draft.images.length > 0) && (
        <div className="grid grid-cols-2 gap-2 px-2">
          {draft.generating
            ? Array.from({ length: CAST_IMAGE_COUNT }).map((_, i) => (
                <div key={i} className={cn('shimmer rounded-lg border border-border bg-muted', kind === 'character' ? 'aspect-[2/3]' : 'aspect-video')} />
              ))
            : draft.images.map((img) => (
                <div key={img.id} className="group relative overflow-hidden rounded-lg border border-border bg-muted">
                  <img src={img.thumbnailUrl || img.url} alt="" className={cn('w-full object-cover', kind === 'character' ? 'aspect-[2/3]' : 'aspect-video')} />
                  <div className="absolute inset-x-0 bottom-0 p-1.5">
                    <Button
                      size="sm"
                      variant="glass"
                      className="h-7 w-full"
                      disabled={disabled || busy !== null}
                      onClick={() => run(`img${img.id}`, () => approveCastImage(entry.key, { imageId: img.id }), 'That image could not be approved.').catch(() => {})}
                    >
                      {busy === `img${img.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Approve
                    </Button>
                  </div>
                </div>
              ))}
        </div>
      )}
      {(draft.error || error) && <p className="px-2 text-xs text-destructive">{draft.error || error}</p>}
      {own.dialog}
    </div>
  );
}

function CastCard({
  kind, entry, story, imageModel, disabled, onPickLibrary,
}: {
  kind: CastKind;
  entry: Entry;
  story: StoryDoc;
  imageModel: string;
  disabled: boolean;
  onPickLibrary: () => void;
}) {
  const { saveCast, editStory, environments } = useStoryRoomStore();
  const characters = useFacelessStore((s) => s.characters);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const linkedEnv = kind === 'environment' && entry.ref_id !== null ? environments.find((e) => e.id === entry.ref_id) : undefined;
  const linkedChar = kind === 'character' && entry.ref_id !== null ? characters.find((c) => c.id === entry.ref_id) : undefined;

  const patch = (p: Partial<CastEntry> & Partial<EnvEntry>) =>
    editStory((d) =>
      kind === 'character'
        ? { ...d, characters: d.characters.map((c) => (c.key === entry.key ? { ...c, ...p } : c)) }
        : { ...d, environments: d.environments.map((e) => (e.key === entry.key ? { ...e, ...p } : e)) },
    );

  const remove = () =>
    editStory((d) =>
      kind === 'character'
        ? {
            ...d,
            characters: d.characters.filter((c) => c.key !== entry.key),
            scenes: d.scenes.map((s) => ({ ...s, shots: s.shots.map((sh) => ({ ...sh, characters: sh.characters.filter((k) => k !== entry.key) })) })),
          }
        : {
            ...d,
            environments: d.environments.filter((e) => e.key !== entry.key),
            scenes: d.scenes.map((s) => (s.environment_key === entry.key ? { ...s, environment_key: null } : s)),
          },
    );

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveCast(entry.key);
    } catch (err) {
      setError(getErrorMessage(err, 'This could not be saved to your library.'));
    } finally {
      setSaving(false);
    }
  };

  const libraryThumb = kind === 'character' ? characterThumb(linkedChar) : linkedEnv?.media[0]?.url ?? null;
  const char = kind === 'character' ? (entry as CastEntry) : null;
  const env = kind === 'environment' ? (entry as EnvEntry) : null;

  return (
    <div className={cn('rounded-xl border p-3', entry.image_approved ? 'border-border' : 'border-border bg-secondary/10')}>
      <div className="mb-2 flex items-start gap-2">
        {libraryThumb && (
          <img src={libraryThumb} alt="" className="mt-1 h-8 w-8 shrink-0 rounded-md border border-border object-cover" />
        )}
        <div className="min-w-0 flex-1">
          <EditableText
            value={entry.name}
            placeholder={kind === 'character' ? 'Name' : 'Place'}
            disabled={disabled}
            maxLength={120}
            onCommit={(name) => patch({ name })}
            className="text-sm font-semibold"
          />
          <p className="flex flex-wrap items-center gap-1.5 px-2 text-[11px] text-muted-foreground">
            <span className="font-mono tabular">{entry.key}</span>
            {char?.role && <span className="truncate">{char.role}</span>}
            {env && [env.time_of_day, env.mood].filter(Boolean).map((x) => <span key={x} className="truncate">{x}</span>)}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {entry.ref_id !== null ? (
            <Chip accent>In library #{entry.ref_id}</Chip>
          ) : (
            <Button size="sm" variant="outline" className="h-7 px-2" disabled={disabled || saving} onClick={save}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookmarkPlus className="h-3.5 w-3.5" />} Save to library
            </Button>
          )}
          <button
            type="button"
            disabled={disabled}
            onClick={onPickLibrary}
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            <Library className="h-3 w-3" /> Use from library
          </button>
        </div>
      </div>
      {error && <p className="mb-2 px-2 text-xs text-destructive">{error}</p>}

      <ReferenceImage
        kind={kind}
        entry={entry}
        aspect={kind === 'character' ? CHARACTER_IMAGE_ASPECT : story.aspect}
        imageModel={imageModel}
        disabled={disabled}
      />

      <Collapsible open={details} onOpenChange={setDetails} className="mt-2">
        <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Details
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-200', details && 'rotate-180')} />
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-1 pt-1">
          {char && <EditableText label="Role" value={char.role} disabled={disabled} onCommit={(role) => patch({ role })} />}
          <EditableText label="Description" multiline value={entry.description} disabled={disabled} onCommit={(description) => patch({ description })} />
          {char && (
            <>
              <EditableText label="Wardrobe" multiline rows={1} value={char.wardrobe} disabled={disabled} onCommit={(wardrobe) => patch({ wardrobe })} />
              <EditableText label="Voice" multiline rows={1} value={char.voice_notes} disabled={disabled} onCommit={(voice_notes) => patch({ voice_notes })} />
            </>
          )}
          {env && (
            <div className="grid grid-cols-2 gap-x-2">
              <EditableText label="Time of day" value={env.time_of_day} disabled={disabled} onCommit={(time_of_day) => patch({ time_of_day })} />
              <EditableText label="Mood" value={env.mood} disabled={disabled} onCommit={(mood) => patch({ mood })} />
            </div>
          )}
          {linkedEnv && (
            <div className="px-2 pt-1">
              <EnvironmentPhotos env={linkedEnv} disabled={disabled} />
            </div>
          )}
          <div className="flex justify-end">
            <Button size="sm" variant="ghost" disabled={disabled} onClick={() => setConfirmRemove(true)} className="text-muted-foreground hover:text-destructive">
              <Trash2 className="h-3.5 w-3.5" /> Remove from story
            </Button>
          </div>
        </CollapsibleContent>
      </Collapsible>
      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title={kind === 'character' ? 'Remove this character?' : 'Remove this environment?'}
        description={`"${entry.name || 'Untitled'}" is removed from this story and from every shot it appears in. A copy saved to your library stays there.`}
        confirmText="Remove"
        variant="destructive"
        onConfirm={remove}
      />
    </div>
  );
}

/** Cast: characters and environments, each with a reference image to approve. */
export function CastTab({ story, disabled }: { story: StoryDoc; disabled: boolean }) {
  const { editStory, linkCast, loadEnvironments } = useStoryRoomStore();
  const { charactersLoaded, loadCharacters } = useFacelessStore();
  const { getModelCost } = usePricingStore();
  const [imageModel, setImageModel] = useState(IMAGE_MODELS[0].value);
  const [picking, setPicking] = useState<{ kind: CastKind; key: string } | null>(null);
  const progress = imageProgress(story);

  useEffect(() => {
    loadEnvironments();
    if (!charactersLoaded) loadCharacters();
  }, [loadEnvironments, charactersLoaded, loadCharacters]);

  const addCharacter = () =>
    editStory((d) => ({
      ...d,
      characters: [
        ...d.characters,
        { key: nextKey('c', d.characters), ref_id: null, name: '', role: '', description: '', wardrobe: '', voice_notes: '', image_prompt: '', image_url: null, image_approved: false },
      ],
    }));
  const addEnvironment = () =>
    editStory((d) => ({
      ...d,
      environments: [
        ...d.environments,
        { key: nextKey('e', d.environments), ref_id: null, name: '', description: '', time_of_day: '', mood: '', image_prompt: '', image_url: null, image_approved: false },
      ],
    }));

  const priceOf = (model: string) => {
    const per = getModelCost(imageKey(model, CAST_IMAGE_RESOLUTION));
    return per !== undefined ? formatUsd(per * CAST_IMAGE_COUNT) : '';
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-secondary/20 p-3">
        <div>
          <p className="text-xs">
            <span className={cn('font-mono tabular', progress.total > 0 && progress.approved === progress.total ? 'text-success' : 'text-foreground')}>
              {progress.approved} of {progress.total}
            </span>{' '}
            <span className="text-muted-foreground">reference images approved</span>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">Approve one image per character and place, and a photo of each product, before making video.</p>
        </div>
        <Select value={imageModel} onValueChange={setImageModel}>
          <SelectTrigger className="h-8 w-auto gap-1.5 text-xs" aria-label="Image model">
            <ImagePlus className="h-3.5 w-3.5 text-muted-foreground" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {IMAGE_MODELS.map((m) => (
              <SelectItem key={m.value} value={m.value}>
                <span className="flex w-full items-center justify-between gap-3">
                  {m.label}
                  <span className="font-mono text-[10px] tabular text-muted-foreground">{priceOf(m.value)}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-base font-semibold">Characters</h3>
          <Button size="sm" variant="ghost" disabled={disabled} onClick={addCharacter}><Plus className="h-3.5 w-3.5" /> Add</Button>
        </div>
        {story.characters.length === 0 && <p className="text-sm text-muted-foreground">No characters yet. The director proposes a cast in its first reply.</p>}
        <div className="space-y-3">
          {story.characters.map((c) => (
            <CastCard key={c.key} kind="character" entry={c} story={story} imageModel={imageModel} disabled={disabled} onPickLibrary={() => setPicking({ kind: 'character', key: c.key })} />
          ))}
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-base font-semibold">Environments</h3>
          <Button size="sm" variant="ghost" disabled={disabled} onClick={addEnvironment}><Plus className="h-3.5 w-3.5" /> Add</Button>
        </div>
        {story.environments.length === 0 && <p className="text-sm text-muted-foreground">No environments yet.</p>}
        <div className="space-y-3">
          {story.environments.map((e) => (
            <CastCard key={e.key} kind="environment" entry={e} story={story} imageModel={imageModel} disabled={disabled} onPickLibrary={() => setPicking({ kind: 'environment', key: e.key })} />
          ))}
        </div>
      </section>

      <ProductsPanel story={story} disabled={disabled} />

      <LibraryPicker
        kind={picking?.kind ?? 'character'}
        open={!!picking}
        onOpenChange={(open) => !open && setPicking(null)}
        onPick={async (refId) => {
          if (picking) await linkCast(picking.key, refId);
        }}
      />
    </div>
  );
}
