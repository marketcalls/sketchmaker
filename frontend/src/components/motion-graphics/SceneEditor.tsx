import { useState } from 'react';
import { ImagePlus, Loader2, Plus, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { getErrorMessage } from '@/utils/errors';
import {
  motionGraphicsApi,
  type SceneTypeDef,
  type SlotDef,
  type SlotValue,
  type SpecScene,
  type Upload,
  type UploadRef,
  type ValidationIssue,
} from '@/api/motionGraphics';
import { useMotionGraphicsStore } from '@/stores/motionGraphicsStore';
import { ErrorNote, FieldLabel } from './shared';

function words(s: string): number {
  return s.trim() ? s.trim().split(/\s+/).length : 0;
}

function ImagePicker({
  value,
  onChange,
  uploads,
  projectId,
  kind = 'image',
}: {
  value: SlotValue | undefined;
  onChange: (v: UploadRef | null) => void;
  uploads: Upload[];
  projectId: number;
  kind?: 'image' | 'audio';
}) {
  const refresh = useMotionGraphicsStore((s) => s.refresh);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = value && typeof value === 'object' && 'upload_id' in (value as object) ? (value as UploadRef).upload_id : null;
  const mine = uploads.filter((u) => u.kind === kind);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const u = await motionGraphicsApi.upload(projectId, file);
      onChange({ upload_id: u.id });
      await refresh();
    } catch (err) {
      setError(getErrorMessage(err, 'Upload failed'));
    } finally {
      setBusy(false);
    }
  };

  const media = useMediaPicker({
    kinds: [kind],
    // Audio takes FLAC here, unlike the My Assets default.
    accept: kind === 'audio' ? 'audio/mpeg,audio/wav,audio/mp4,audio/ogg,audio/flac,.m4a' : undefined,
    title: kind === 'image' ? 'Add an image' : 'Add audio',
    disabled: busy,
    onFiles: (files) => upload(files[0]),
  });

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {mine.map((u) => (
          <button
            key={u.id}
            type="button"
            onClick={() => onChange(selected === u.id ? null : { upload_id: u.id })}
            className={cn(
              'relative overflow-hidden rounded-lg border transition-colors',
              kind === 'image' ? 'h-16 w-16' : 'h-10 max-w-[12rem] px-3',
              selected === u.id ? 'border-primary ring-2 ring-primary/40' : 'border-border hover:border-primary/40',
            )}
            title={u.name || u.id}
          >
            {kind === 'image' && u.url ? (
              <img src={u.url} alt={u.name} className="h-full w-full object-cover" />
            ) : (
              <span className="truncate font-mono text-[10px] text-muted-foreground">
                {u.name || 'audio'} {u.duration ? `${u.duration.toFixed(1)} s` : ''}
              </span>
            )}
            {u.ai_generated && (
              <span className="absolute left-1 top-1 rounded bg-background/80 px-1 text-[9px] font-medium text-foreground">AI</span>
            )}
          </button>
        ))}
        <button
          type="button"
          onClick={media.open}
          {...media.dropProps}
          disabled={busy}
          aria-label={kind === 'image' ? 'Add an image' : undefined}
          title={kind === 'image' ? 'Add an image: upload, drop or choose from My Assets' : undefined}
          className={cn(
            'flex items-center justify-center gap-1.5 rounded-xl border border-dashed bg-secondary/20 text-xs text-muted-foreground transition-colors hover:border-foreground/30',
            kind === 'image' ? 'h-16 w-16' : 'h-10 px-3',
            media.dragOver ? 'border-primary bg-primary/5' : 'border-border',
          )}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
          {kind === 'audio' && 'Add audio'}
        </button>
        {media.dialog}
        {selected && (
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange(null)}>
            <X className="h-3.5 w-3.5" /> Clear
          </Button>
        )}
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
    </div>
  );
}

function ItemsEditor({ slot, value, onChange }: { slot: SlotDef; value: SlotValue | undefined; onChange: (v: Record<string, unknown>[]) => void }) {
  const items = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
  const fields = (slot.item_fields ?? []).filter((f) => f.kind !== 'image');
  const set = (i: number, key: string, v: string | boolean) =>
    onChange(items.map((it, k) => (k === i ? { ...it, [key]: v } : it)));
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="flex items-start gap-2 rounded-lg border border-border bg-secondary/20 p-2">
          <span className="mt-2 w-5 shrink-0 font-mono text-[10px] text-muted-foreground">{i + 1}</span>
          <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-2">
            {fields.map((f) =>
              f.kind === 'bool' ? (
                <label key={f.key} className="flex h-9 items-center gap-2 text-xs text-muted-foreground">
                  {/* Unset counts as on, matching the scene builders. */}
                  <Switch checked={it[f.key] !== false} onCheckedChange={(v) => set(i, f.key, v)} /> {f.label}
                </label>
              ) : f.kind === 'choice' && f.choices?.length ? (
                <Select key={f.key} value={String(it[f.key] ?? f.choices[0])} onValueChange={(v) => set(i, f.key, v)}>
                  <SelectTrigger className="h-9 text-sm" aria-label={f.label}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {f.choices.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  key={f.key}
                  value={String(it[f.key] ?? '')}
                  placeholder={f.label}
                  maxLength={f.max_chars ? f.max_chars + 20 : undefined}
                  onChange={(e) => set(i, f.key, e.target.value)}
                  className={cn('h-9 text-sm', f.key === 'desc' || f.key === 'text' ? 'sm:col-span-2' : '')}
                />
              ),
            )}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onChange(items.filter((_, k) => k !== i))}
            aria-label="Remove"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {(!slot.max_items || items.length < slot.max_items) && (
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...items, {}])}>
          <Plus className="h-4 w-4" /> Add
        </Button>
      )}
    </div>
  );
}

export function SlotField({
  slot,
  value,
  onChange,
  issue,
  uploads,
  projectId,
}: {
  slot: SlotDef;
  value: SlotValue | undefined;
  onChange: (v: SlotValue | null) => void;
  issue?: ValidationIssue;
  uploads: Upload[];
  projectId: number;
}) {
  const id = `slot-${slot.key}`;
  const text = typeof value === 'string' ? value : value === null || value === undefined ? '' : String(value);
  const hint = [slot.required ? 'required' : '', slot.max_words ? `${slot.max_words} words max` : '', slot.help ?? '']
    .filter(Boolean)
    .join(', ');
  let control;
  if (slot.kind === 'longtext') {
    control = (
      <Textarea id={id} rows={4} value={text} onChange={(e) => onChange(e.target.value)} className="text-sm" />
    );
  } else if (slot.kind === 'number') {
    control = (
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        value={text}
        min={slot.min}
        max={slot.max}
        step="any"
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="font-mono"
      />
    );
  } else if (slot.kind === 'choice') {
    control = (
      <Select value={text || slot.choices?.[0]} onValueChange={(v) => onChange(v)}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(slot.choices ?? []).map((c) => (
            <SelectItem key={c} value={c}>
              {c}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  } else if (slot.kind === 'bool') {
    control = (
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <Switch checked={value !== false} onCheckedChange={(v) => onChange(v)} />
        {value === false ? 'No' : 'Yes'}
      </label>
    );
  } else if (slot.kind === 'image') {
    control = (
      <ImagePicker
        value={value}
        onChange={onChange}
        uploads={uploads}
        projectId={projectId}
        kind={slot.key === 'audio' ? 'audio' : 'image'}
      />
    );
  } else if (slot.kind === 'items') {
    control = <ItemsEditor slot={slot} value={value} onChange={onChange} />;
  } else {
    control = <Input id={id} value={text} onChange={(e) => onChange(e.target.value)} />;
  }
  const counted = slot.kind === 'text' || slot.kind === 'longtext';
  return (
    <div>
      <FieldLabel
        htmlFor={id}
        hint={hint || undefined}
        count={counted && slot.max_chars ? text.length : undefined}
        max={counted ? slot.max_chars : undefined}
      >
        {slot.label}
      </FieldLabel>
      {control}
      {counted && slot.max_words && words(text) > slot.max_words && (
        <p className="mt-1 text-xs text-warning">
          {words(text)} words; {slot.max_words} or fewer reads best on screen.
        </p>
      )}
      {issue && <p className="mt-1 text-xs text-destructive">{issue.message}</p>}
    </div>
  );
}

export function SceneEditor({
  scene,
  def,
  onChange,
  issues,
  uploads,
  projectId,
  voiceOn,
  plannedSeconds,
}: {
  scene: SpecScene;
  def: SceneTypeDef;
  onChange: (s: SpecScene) => void;
  issues: ValidationIssue[];
  uploads: Upload[];
  projectId: number;
  voiceOn: boolean;
  plannedSeconds?: number;
}) {
  const setSlot = (key: string, v: SlotValue | null) => {
    const slots = { ...scene.slots };
    if (v === null || v === '') delete slots[key];
    else slots[key] = v;
    onChange({ ...scene, slots });
  };
  return (
    <div className="space-y-4">
      {def.slots.length === 0 && (
        <p className="text-sm text-muted-foreground">
          This card uses the project's {def.type === 'disclaimer' ? 'disclaimer' : 'settings'}; edit it under Render.
        </p>
      )}
      {def.slots.map((slot) => (
        <SlotField
          key={slot.key}
          slot={slot}
          value={scene.slots[slot.key]}
          onChange={(v) => setSlot(slot.key, v)}
          issue={issues.find((i) => i.slot === slot.key)}
          uploads={uploads}
          projectId={projectId}
        />
      ))}
      {def.voiceover && (
        <div>
          <FieldLabel
            htmlFor="scene-vo"
            hint={voiceOn ? 'spoken by the AI voice' : 'turn the voice on under Audio'}
            count={(scene.voiceover ?? '').length}
            max={600}
          >
            Voiceover
          </FieldLabel>
          <Textarea
            id="scene-vo"
            rows={2}
            value={scene.voiceover ?? ''}
            onChange={(e) => onChange({ ...scene, voiceover: e.target.value || null })}
            placeholder="Optional spoken line for this scene"
            className="text-sm"
          />
        </div>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-36">
          <FieldLabel htmlFor="scene-dur" hint="seconds">
            Duration
          </FieldLabel>
          <Input
            id="scene-dur"
            type="number"
            min={def.min_seconds}
            max={600}
            step={0.1}
            value={scene.duration ?? ''}
            placeholder={plannedSeconds ? `auto ${plannedSeconds.toFixed(1)}` : 'auto'}
            onChange={(e) => onChange({ ...scene, duration: e.target.value === '' ? null : Number(e.target.value) })}
            className="font-mono"
          />
        </div>
        <p className="pb-2 text-xs text-muted-foreground">
          Minimum {def.min_seconds} s. Auto follows text length and the voice.
        </p>
      </div>
      {issues
        .filter((i) => !i.slot)
        .map((i, k) => (
          <ErrorNote key={k}>{i.message}</ErrorNote>
        ))}
    </div>
  );
}
