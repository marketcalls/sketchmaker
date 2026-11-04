import { useEffect, useRef, useState } from 'react';
import { FileText, ImagePlus, Loader2, ShieldAlert, Trash2, Video, Wand2, X } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { cn } from '@/lib/utils';
import { errorSuffix, getErrorMessage } from '@/utils/errors';
import {
  facelessApi,
  isRunActive,
  newIdempotencyKey,
  type CharacterBible,
  type ConsentRelationship,
  type FacelessCharacter,
  type FacelessVoice,
  type SafetyFlag,
} from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { MultiUploadDropzone } from './MultiUploadDropzone';
import { VoiceSelect } from './VoicePicker';
import { QuoteConfirmDialog } from './QuoteConfirmDialog';
import { ErrorNote, FieldLabel, Kicker, PillGroup } from './shared';

type Source = 'images' | 'video' | 'text';

const IMAGE_ACCEPT = 'image/png,image/jpeg,image/webp,image/avif';
const VIDEO_ACCEPT = 'video/mp4,video/quicktime,video/webm';

interface Pending {
  file: File;
  preview: string;
}

const RELATIONSHIPS: { value: ConsentRelationship; label: string }[] = [
  { value: 'self', label: 'This is me' },
  { value: 'with_permission', label: 'Someone who gave me permission' },
];

// The versioned attestation text from GET /config, a relationship and the
// checkbox. The backend refuses any other text version.
function ConsentForm({
  attested,
  onAttested,
  relationship,
  onRelationship,
  disabled,
}: {
  attested: boolean;
  onAttested: (v: boolean) => void;
  relationship: ConsentRelationship;
  onRelationship: (v: ConsentRelationship) => void;
  disabled?: boolean;
}) {
  const consent = useFacelessStore((s) => s.config?.consent);
  const catalogError = useFacelessStore((s) => s.catalogError);
  const loadCatalog = useFacelessStore((s) => s.loadCatalog);
  if (!consent && catalogError) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="alert" className="text-xs text-destructive">
          The consent statement could not be loaded, so a real person cannot be added right now.
        </p>
        <Button type="button" variant="outline" size="sm" onClick={() => loadCatalog(true)}>
          Try again
        </Button>
      </div>
    );
  }
  if (!consent) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading the consent statement
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <Kicker>Likeness consent, version {consent.version}</Kicker>
      <p className="whitespace-pre-line rounded-md bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
        {consent.text}
      </p>
      <PillGroup<ConsentRelationship>
        label="Who is this person"
        value={relationship}
        onChange={onRelationship}
        disabled={disabled}
        options={RELATIONSHIPS.filter((r) => consent.relationships.includes(r.value))}
      />
      <label className="flex cursor-pointer items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-primary)]"
          checked={attested}
          disabled={disabled}
          onChange={(e) => onAttested(e.target.checked)}
        />
        <span>I attest to the statement above.</span>
      </label>
    </div>
  );
}

function SafetyFlags({ flags, blockReason }: { flags: SafetyFlag[]; blockReason: string | null }) {
  if (flags.length === 0 && !blockReason) return null;
  return (
    <div className="space-y-2">
      <Kicker>Safety review</Kicker>
      {blockReason && (
        <p role="alert" className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {blockReason}
        </p>
      )}
      <ul className="space-y-1.5">
        {flags.map((f, i) => (
          <li
            key={`${f.kind}-${i}`}
            className={cn(
              'flex items-start justify-between gap-3 rounded-lg border p-2.5 text-sm',
              f.confidence >= 0.5 ? 'border-warning/40 bg-warning/10' : 'border-border bg-secondary/30',
            )}
          >
            <span>
              <span className="text-xs font-medium capitalize text-muted-foreground">
                {f.kind.replace(/_/g, ' ')}
              </span>
              {f.note && <span className="mt-0.5 block text-xs">{f.note}</span>}
            </span>
            <span className="font-mono text-[11px] tabular text-muted-foreground">{Math.round(f.confidence * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CharacterEditorDialog({
  open,
  onOpenChange,
  character,
  voices,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // null to create a new character
  character: FacelessCharacter | null;
  voices: FacelessVoice[];
  onSaved?: (c: FacelessCharacter) => void;
}) {
  const { upsertCharacter, config, loadCatalog } = useFacelessStore();
  const [current, setCurrent] = useState<FacelessCharacter | null>(character);
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [source, setSource] = useState<Source>('images');
  const [pending, setPending] = useState<Pending[]>([]);
  const [notes, setNotes] = useState('');
  const [personality, setPersonality] = useState('');
  const [catchphrase, setCatchphrase] = useState('');
  const [realPerson, setRealPerson] = useState(false);
  const [attested, setAttested] = useState(false);
  const [relationship, setRelationship] = useState<ConsentRelationship>('self');
  const [bible, setBible] = useState<Pick<CharacterBible, 'canonical_description' | 'outfit' | 'likeness_clause' | 'style_notes'>>({
    canonical_description: '',
    outfit: '',
    likeness_clause: '',
    style_notes: '',
  });
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  // Characters with a sheet being made: it keeps going if another one is opened.
  const [sheetsRunning, setSheetsRunning] = useState<number[]>([]);
  const [revokeOpen, setRevokeOpen] = useState(false);

  // On every open, so a catalog that failed last time is asked for again.
  useEffect(() => {
    if (open) loadCatalog();
  }, [open, loadCatalog]);

  // The character on screen, for replies that arrive after another was opened.
  const shownId = useRef<number | null>(null);
  useEffect(() => {
    shownId.current = current?.id ?? null;
  }, [current]);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const loadForm = (c: FacelessCharacter | null) => {
    setName(c?.name ?? '');
    setRole(c?.role ?? '');
    setPersonality(c?.personality ?? '');
    setCatchphrase(c?.catchphrase ?? '');
    setNotes(c?.notes ?? '');
    setRealPerson(c?.kind === 'real_person');
    setAttested(c?.consent.status === 'valid');
    setRelationship(c?.consent.relationship ?? 'self');
    setBible({
      canonical_description: c?.bible?.canonical_description ?? '',
      outfit: c?.bible?.outfit ?? '',
      likeness_clause: c?.bible?.likeness_clause ?? '',
      style_notes: c?.bible?.style_notes ?? c?.style_notes ?? '',
    });
    setVoiceId(c?.voice_id ?? null);
  };

  useEffect(() => {
    if (!open) return;
    setCurrent(character);
    loadForm(character);
    setSource('images');
    setPending([]);
    setError(null);
    setBusy(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, character]);

  // Object URLs are revoked when a file leaves the list and on unmount.
  const pendingRef = useRef<Pending[]>([]);
  useEffect(() => {
    const kept = new Set(pending.map((p) => p.preview));
    pendingRef.current.filter((p) => !kept.has(p.preview)).forEach((p) => URL.revokeObjectURL(p.preview));
    pendingRef.current = pending;
  }, [pending]);
  useEffect(() => () => pendingRef.current.forEach((p) => URL.revokeObjectURL(p.preview)), []);

  const creating = !current;
  const consent = config?.consent;
  const maxMedia = config?.limits.max_character_media ?? 12;
  const consentStatus = current?.consent.status;
  const needsAttestation = realPerson && (creating || consentStatus === 'missing' || consentStatus === 'outdated');
  const consentOk = !needsAttestation || (attested && !!consent);
  const references = (current?.media ?? []).filter((m) => m.role !== 'sheet');
  const sheet = (current?.media ?? []).find((m) => m.role === 'sheet');
  const hasImages = references.some((m) => m.kind === 'image');
  const canUpload = !current || current.consent.status === 'not_required' || current.consent.status === 'valid';
  const sheetRunning = !!current && sheetsRunning.includes(current.id);

  // A reply for any other character only updates the library: taking it as
  // current would save this form's fields onto that character.
  const apply = (c: FacelessCharacter) => {
    upsertCharacter(c);
    setCurrent((shown) => (shown?.id === c.id ? c : shown));
  };

  const addFiles = (files: File[]) => {
    const room = Math.max(0, maxMedia - references.length - pending.length);
    const next = files.slice(0, creating && source === 'video' ? 1 : room).map((file) => ({
      file,
      preview: URL.createObjectURL(file),
    }));
    setPending((p) => (creating && source === 'video' ? next : [...p, ...next]));
  };

  const uploadAll = async (id: number): Promise<FacelessCharacter | null> => {
    const files = pending;
    let latest: FacelessCharacter | null = null;
    for (let i = 0; i < files.length; i++) {
      setBusy(`Uploading ${i + 1} of ${files.length}`);
      latest = await facelessApi.uploadCharacterMedia(id, files[i].file);
      // Off the list at once, so trying again after a failure does not send it twice.
      const done = files[i];
      setPending((list) => list.filter((p) => p !== done));
      apply(latest);
    }
    return latest;
  };

  const writeBible = async (id: number) => {
    setBusy('Writing the character bible');
    const c = await facelessApi.characterBible(id);
    apply(c);
    loadForm(c);
    return c;
  };

  const create = async () => {
    if (!name.trim()) return setError('Give the character a name.');
    if (!consentOk || (realPerson && !consent)) return setError('Tick the likeness consent for a real person.');
    setError(null);
    let c: FacelessCharacter;
    try {
      setBusy('Creating');
      c = await facelessApi.createCharacter({
        name: name.trim(),
        kind: realPerson ? 'real_person' : 'fictional',
        role: role.trim() || null,
        personality: personality.trim() || null,
        notes: notes.trim() || null,
        consent: realPerson && consent ? { accepted: attested, text_version: consent.version, relationship } : null,
      });
    } catch (err) {
      setError(getErrorMessage(err, 'Could not create the character'));
      setBusy(null);
      return;
    }
    // From here the character exists: the dialog is its editor, whatever happens next.
    setCurrent(c);
    upsertCharacter(c);
    onSaved?.(c);
    try {
      if (pending.length > 0) c = (await uploadAll(c.id)) ?? c;
    } catch (err) {
      loadForm(c);
      setError(
        `${c.name} was created, but a reference did not upload. ${getErrorMessage(err, 'Please try again.')} Files still listed below were not saved; Save character tries them again.`,
      );
      setBusy(null);
      return;
    }
    try {
      c = await writeBible(c.id);
    } catch (err) {
      setError(`Created. The AI bible is unavailable right now: ${getErrorMessage(err, 'try again later')}`);
    }
    loadForm(c);
    setBusy(null);
  };

  const regenerateBible = async () => {
    if (!current) return;
    setError(null);
    try {
      await writeBible(current.id);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not write the bible'));
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (!current) return;
    if (!name.trim()) return setError('Give the character a name.');
    setError(null);
    try {
      if (needsAttestation) {
        if (!consent || !attested) return setError('Tick the likeness consent for a real person.');
        setBusy('Recording consent');
        apply(await facelessApi.attestConsent(current.id, { accepted: true, text_version: consent.version, relationship }));
      }
      if (pending.length > 0) await uploadAll(current.id);
      setBusy('Saving');
      const bibleFilled = bible.canonical_description.trim() && bible.likeness_clause.trim();
      const saved = await facelessApi.updateCharacter(current.id, {
        name: name.trim(),
        role: role.trim() || null,
        personality: personality.trim() || null,
        catchphrase: catchphrase.trim() || null,
        notes: notes.trim() || null,
        style_notes: bible.style_notes.trim() || null,
        voice_id: voiceId,
        // A bible needs a description and a likeness clause to validate.
        bible: current.bible || bibleFilled ? { name: name.trim(), ...bible } : undefined,
      });
      apply(saved);
      onSaved?.(saved);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the character'));
    } finally {
      setBusy(null);
    }
  };

  const removeMedia = async (mediaId: string) => {
    if (!current) return;
    try {
      apply(await facelessApi.deleteCharacterMedia(current.id, mediaId));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not remove that reference'));
    }
  };

  const revoke = async () => {
    if (!current) return;
    try {
      const c = await facelessApi.revokeConsent(current.id);
      apply(c);
      if (shownId.current === c.id) loadForm(c);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not revoke consent'));
    }
  };

  // The sheet is a queued run: follow it, then reload the character.
  const followSheet = async (runId: number, charId: number) => {
    setSheetsRunning((ids) => [...ids, charId]);
    try {
      let finished = false;
      for (let i = 0; i < 120 && !finished; i++) {
        await new Promise((r) => setTimeout(r, Math.min(10000, 2000 + i * 500)));
        if (!mounted.current) return;
        let run;
        try {
          run = await facelessApi.run(runId);
        } catch (err) {
          // A 429, a 5xx or a dropped connection says nothing about the run: ask
          // again next round. Any other refusal means there is nothing to follow.
          const status = (err as { response?: { status?: number } }).response?.status;
          if (status && status < 500 && status !== 408 && status !== 429) return;
          continue;
        }
        if (isRunActive(run)) continue;
        finished = true;
        if ((run.status === 'failed' || run.status === 'cancelled') && shownId.current === charId) {
          setError(`The reference sheet failed${errorSuffix(run.error, '.')}`);
        }
      }
      if (!mounted.current) return;
      if (!finished && shownId.current === charId) {
        setError('The reference sheet is still being made. Open this character again later to see it.');
      }
      apply(await facelessApi.character(charId));
    } catch {
      // the library reload shows the sheet later
    } finally {
      setSheetsRunning((ids) => ids.filter((id) => id !== charId));
    }
  };

  const uploadHint =
    creating && source === 'video'
      ? 'MP4, MOV or WebM up to 60 s. Three clean frames are pulled from it on the server.'
      : `Images up to 25 MB, videos up to 60 s. ${Math.max(0, maxMedia - references.length)} slots left`;

  const bibleField = (key: keyof typeof bible, value: string) => setBible((b) => ({ ...b, [key]: value }));

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {creating ? 'New character' : current?.name}
          </DialogTitle>
          <DialogDescription>
            {creating
              ? 'Give the studio references to hold this character steady across every scene.'
              : 'The likeness clause goes word for word into every frame prompt with this character. Edit it until it reads exactly right.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="fc-name">Name</FieldLabel>
              <Input id="fc-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="Milo the fox" />
            </div>
            <div>
              <FieldLabel htmlFor="fc-role" hint="optional">Role</FieldLabel>
              <Input id="fc-role" value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} placeholder="Protagonist, rival, mascot" />
            </div>
          </div>

          {/* Real person and consent */}
          <div className="rounded-lg border border-border bg-secondary/30 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <label htmlFor="fc-real" className="text-sm font-medium">Based on a real person</label>
                <p className="text-xs text-muted-foreground">
                  {creating
                    ? 'Turn on if the references show a real, identifiable person. This cannot be changed later.'
                    : current?.kind === 'real_person'
                      ? `Consent: ${consentStatus?.replace(/_/g, ' ')}`
                      : 'Fictional character'}
                </p>
              </div>
              <Switch
                id="fc-real"
                checked={realPerson}
                onCheckedChange={(v) => {
                  setRealPerson(v);
                  if (!v) setAttested(false);
                }}
                disabled={!creating || !!busy}
              />
            </div>
            {needsAttestation && (
              <div className="mt-3 border-t border-border pt-3">
                <ConsentForm
                  attested={attested}
                  onAttested={setAttested}
                  relationship={relationship}
                  onRelationship={setRelationship}
                  disabled={!!busy}
                />
              </div>
            )}
            {!creating && current?.kind === 'real_person' && consentStatus === 'valid' && (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                <p className="text-xs text-muted-foreground">
                  Attested version {current.consent.text_version}, {current.consent.relationship === 'self' ? 'self' : 'with permission'}
                </p>
                <Button type="button" variant="outline" size="sm" onClick={() => setRevokeOpen(true)} disabled={!!busy}>
                  Revoke consent
                </Button>
              </div>
            )}
            {consentStatus === 'revoked' && (
              <p className="mt-3 border-t border-border pt-3 text-xs text-destructive">
                Consent was revoked. Nothing more can be generated with this character.
              </p>
            )}
          </div>

          {/* References */}
          <div>
            <FieldLabel hint={creating ? undefined : `${references.length} of ${maxMedia}`}>References</FieldLabel>
            {creating && (
              <div className="mb-3">
                <PillGroup<Source>
                  label="Reference source"
                  value={source}
                  onChange={(s) => {
                    setSource(s);
                    setPending([]);
                  }}
                  options={[
                    { value: 'images', label: <><ImagePlus className="h-3.5 w-3.5" /> Images</> },
                    { value: 'video', label: <><Video className="h-3.5 w-3.5" /> Video</> },
                    { value: 'text', label: <><FileText className="h-3.5 w-3.5" /> Text only</> },
                  ]}
                />
              </div>
            )}

            {!creating && references.length > 0 && (
              <ul className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
                {references.map((m) => (
                  <li key={m.id} className="group relative aspect-square overflow-hidden rounded-lg border border-border bg-secondary/40">
                    {m.kind === 'video' ? (
                      <video src={m.url ?? undefined} className="h-full w-full object-cover" muted aria-label="Reference video" />
                    ) : (
                      <img src={m.url ?? undefined} alt={m.role === 'frame' ? 'Frame from video' : 'Reference'} className="h-full w-full object-cover" />
                    )}
                    <span className="absolute bottom-1 left-1 rounded bg-background/80 px-1 text-[10px] capitalize text-muted-foreground">
                      {m.role === 'source_video' ? 'video' : m.role}
                    </span>
                    {m.role !== 'frame' && (
                      <Button
                        type="button"
                        size="icon"
                        variant="glass"
                        className="absolute right-1 top-1 h-7 w-7 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                        onClick={() => removeMedia(m.id)}
                        aria-label={m.role === 'source_video' ? 'Remove video and its frames' : 'Remove reference'}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {(creating ? source !== 'text' : canUpload) && (
              <>
                <MultiUploadDropzone
                  accept={creating && source === 'video' ? VIDEO_ACCEPT : creating ? IMAGE_ACCEPT : `${IMAGE_ACCEPT},${VIDEO_ACCEPT}`}
                  icon={creating && source === 'video' ? Video : ImagePlus}
                  title={creating && source === 'video' ? 'Add a short video' : 'Add reference images'}
                  hint={uploadHint}
                  multiple={!(creating && source === 'video')}
                  compact={!creating}
                  disabled={!!busy || references.length >= maxMedia}
                  maxFiles={Math.max(1, maxMedia - references.length - pending.length)}
                  assetKinds={creating && source === 'video' ? ['video'] : creating ? ['image'] : ['image', 'video']}
                  onFiles={addFiles}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Two to three angles hold a likeness best: front, three quarter and profile. Even light, a plain
                  background and one face per image. A 2 to 15 second video also works as a motion reference for clips.
                </p>
              </>
            )}

            {pending.length > 0 && (
              <ul className="mt-3 flex flex-wrap gap-2" aria-label="Files to upload">
                {pending.map((p, i) => (
                  <li key={p.preview} className="relative h-20 w-20 overflow-hidden rounded-lg border border-border bg-secondary/40">
                    {p.file.type.startsWith('video') ? (
                      <video src={p.preview} className="h-full w-full object-cover" muted />
                    ) : (
                      <img src={p.preview} alt={p.file.name} className="h-full w-full object-cover" />
                    )}
                    <Button
                      type="button"
                      size="icon"
                      variant="glass"
                      className="absolute right-1 top-1 h-6 w-6"
                      onClick={() => setPending((list) => list.filter((_, idx) => idx !== i))}
                      aria-label={`Remove ${p.file.name}`}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {creating && (
            <div className="grid grid-cols-1 gap-3">
              <div>
                <FieldLabel htmlFor="fc-notes" hint={source === 'text' ? 'the bible is written from this' : 'optional'}>
                  {source === 'text' ? 'Describe the character' : 'Notes for the bible'}
                </FieldLabel>
                <Textarea
                  id="fc-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  maxLength={4000}
                  placeholder="A small orange fox with a chipped left ear and a green scarf"
                />
              </div>
              <div>
                <FieldLabel htmlFor="fc-pers" hint="optional">Personality</FieldLabel>
                <Input id="fc-pers" value={personality} onChange={(e) => setPersonality(e.target.value)} maxLength={2000} placeholder="Curious, a little clumsy, never gives up" />
              </div>
            </div>
          )}

          {!creating && (
            <div className="space-y-4 rounded-xl border border-border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Kicker>Character bible{current?.bible?.source ? `, from ${current.bible.source.replace('_', ' ')}` : ''}</Kicker>
                <Button type="button" variant="outline" size="sm" onClick={regenerateBible} disabled={!!busy || (current?.kind === 'real_person' && !current.can_generate)}>
                  <FileText className="h-3.5 w-3.5" /> {current?.bible ? 'Rewrite with AI' : 'Write with AI'}
                </Button>
              </div>
              <div>
                <FieldLabel htmlFor="fc-desc">Description</FieldLabel>
                <Textarea id="fc-desc" rows={3} value={bible.canonical_description} onChange={(e) => bibleField('canonical_description', e.target.value)} />
              </div>
              <div>
                <FieldLabel htmlFor="fc-outfit">Outfit</FieldLabel>
                <Textarea id="fc-outfit" rows={2} value={bible.outfit} onChange={(e) => bibleField('outfit', e.target.value)} />
              </div>
              <div>
                <FieldLabel htmlFor="fc-likeness" hint="first in every frame prompt">Likeness clause</FieldLabel>
                <Textarea id="fc-likeness" rows={3} value={bible.likeness_clause} onChange={(e) => bibleField('likeness_clause', e.target.value)} className="font-mono text-xs" />
              </div>
              <div>
                <FieldLabel htmlFor="fc-style">Style notes</FieldLabel>
                <Textarea id="fc-style" rows={2} value={bible.style_notes} onChange={(e) => bibleField('style_notes', e.target.value)} />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <FieldLabel htmlFor="fc-pers2">Personality</FieldLabel>
                  <Input id="fc-pers2" value={personality} onChange={(e) => setPersonality(e.target.value)} maxLength={2000} />
                </div>
                <div>
                  <FieldLabel htmlFor="fc-catch" hint="optional">Catchphrase</FieldLabel>
                  <Input id="fc-catch" value={catchphrase} onChange={(e) => setCatchphrase(e.target.value)} maxLength={200} />
                </div>
              </div>
              <div>
                <FieldLabel htmlFor="fc-voice">Voice</FieldLabel>
                <VoiceSelect id="fc-voice" voices={voices} value={voiceId} onChange={setVoiceId} label="Character voice" allowNone="Narrator voice" />
              </div>
              {hasImages && (
                <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
                  {sheet?.url && (
                    <a href={sheet.url} target="_blank" rel="noreferrer" className="block h-14 w-24 shrink-0 overflow-hidden rounded-md border border-border">
                      <img src={sheet.url} alt="Reference sheet" className="h-full w-full object-cover" />
                    </a>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">Reference sheet</p>
                    <p className="text-xs text-muted-foreground">One 16:9 turnaround made from your references, for steadier likeness.</p>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={() => setSheetOpen(true)} disabled={!!busy || sheetRunning || !current?.can_generate}>
                    {sheetRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                    {sheetRunning ? 'Making sheet' : sheet ? 'New sheet' : 'Make sheet'}
                  </Button>
                </div>
              )}
            </div>
          )}

          {current && <SafetyFlags flags={current.safety_flags} blockReason={current.block_reason} />}

          <ErrorNote>{error}</ErrorNote>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={!!busy}>
              {creating ? 'Cancel' : 'Close'}
            </Button>
            <Button
              onClick={creating ? create : save}
              disabled={
                !!busy ||
                !name.trim() ||
                (needsAttestation && !attested) ||
                (creating && source !== 'text' && pending.length === 0)
              }
            >
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span aria-live="polite">{busy}</span>
                </>
              ) : creating ? (
                'Create and write bible'
              ) : (
                'Save character'
              )}
            </Button>
          </div>
        </div>

        {current && (
          <QuoteConfirmDialog
            open={sheetOpen}
            onOpenChange={setSheetOpen}
            title="Reference sheet"
            description={`A turnaround sheet for ${current.name} from the references on file.`}
            loadQuote={() => facelessApi.characterSheetQuote(current.id)}
            onConfirm={async (quote) => {
              const run = await facelessApi.characterSheet(
                current.id,
                newIdempotencyKey(`sheet-${current.id}`),
                quote.usd,
              );
              followSheet(run.id, current.id);
            }}
          />
        )}
        <ConfirmDialog
          open={revokeOpen}
          onOpenChange={setRevokeOpen}
          title="Revoke likeness consent"
          description="Every later generation with this character will be blocked, and its stored photos, videos and reference sheets are deleted. Results already in your projects stay there, where you can delete them."
          confirmText="Revoke"
          variant="destructive"
          onConfirm={revoke}
        />
      </DialogContent>
    </Dialog>
  );
}
