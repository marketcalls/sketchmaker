import { useState } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, PenLine, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import {
  CAMERAS,
  EMOTIONS,
  SHOT_KINDS,
  estimateSeconds,
  sceneWords,
  type Camera,
  type ComplianceFlag,
  type FacelessCharacter,
  type Scene,
  type ShotKind,
  type ShotMotion,
} from '@/api/faceless';
import { CharacterAvatar } from '../CharacterCard';
import { FlagList, Kicker, MutedChip, TechChip } from '../shared';

const MOTIONS: { value: ShotMotion; label: string }[] = [
  { value: 'push_in', label: 'Push in' },
  { value: 'pull_out', label: 'Pull out' },
  { value: 'pan_left', label: 'Pan left' },
  { value: 'pan_right', label: 'Pan right' },
  { value: 'none', label: 'Static' },
];

function EmotionSelect({ value, onChange, label }: { value: string | null; onChange: (v: string | null) => void; label: string }) {
  const options = value && !EMOTIONS.includes(value) ? [value, ...EMOTIONS] : EMOTIONS;
  return (
    <Select value={value ?? '__none'} onValueChange={(v) => onChange(v === '__none' ? null : v)}>
      <SelectTrigger aria-label={label} className="h-9 w-full font-mono text-xs sm:w-36">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none">No tag</SelectItem>
        {options.map((e) => (
          <SelectItem key={e} value={e}>
            [{e}]
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function SceneEditor({
  scene,
  position,
  total,
  cast,
  flags,
  wpm,
  reviseDisabled,
  onChange,
  onRevise,
  onDelete,
  onMove,
}: {
  scene: Scene;
  position: number;
  total: number;
  cast: FacelessCharacter[];
  flags: ComplianceFlag[];
  wpm: number;
  reviseDisabled?: string;
  onChange: (s: Scene) => void;
  onRevise: () => void;
  onDelete: () => void;
  onMove: (dir: -1 | 1) => void;
}) {
  const [showDirection, setShowDirection] = useState(false);
  const words = sceneWords(scene);
  const seconds = estimateSeconds(words, wpm) + (scene.silence_after || 0);
  const target = scene.word_target || 0;
  const off = target > 0 && (words < target * 0.7 || words > target * 1.3);
  const castById = new Map(cast.map((c) => [String(c.id), c]));
  const set = (patch: Partial<Scene>) => onChange({ ...scene, ...patch });
  const setShot = (patch: Partial<Scene['shot']>) => onChange({ ...scene, shot: { ...scene.shot, ...patch } });
  const fieldId = (f: string) => `scene-${scene.id}-${f}`;

  const toggleInShot = (cid: string) =>
    setShot({
      characters: scene.shot.characters.includes(cid)
        ? scene.shot.characters.filter((c) => c !== cid)
        : [...scene.shot.characters, cid],
    });

  return (
    <article
      aria-labelledby={fieldId('title')}
      className={cn(
        'rounded-xl border bg-card p-4 shadow-card',
        flags.some((f) => f.severity === 'block') ? 'border-destructive/50' : 'border-border',
      )}
    >
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border font-mono text-[11px] tabular text-muted-foreground">
          {String(position + 1).padStart(2, '0')}
        </span>
        <h3 id={fieldId('title')} className="text-base font-semibold leading-none">
          {scene.beat_name || scene.beat}
        </h3>
        {scene.is_hook && <TechChip>Hook</TechChip>}
        {scene.is_rehook && <TechChip>Re-hook</TechChip>}
        {scene.dramatization && <MutedChip>Dramatization</MutedChip>}
        <span className={cn('ml-auto font-mono text-[11px] tabular', off ? 'text-warning' : 'text-muted-foreground')}>
          {words}
          {target > 0 && ` / ${target}`} words, {seconds.toFixed(1)}s
        </span>
        <div className="flex items-center">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onMove(-1)} disabled={position === 0} aria-label="Move scene up">
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onMove(1)} disabled={position === total - 1} aria-label="Move scene down">
            <ArrowDown className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onDelete} disabled={total <= 1} aria-label="Delete scene">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </header>

      <div className="space-y-3">
        <div>
          <div className="mb-1 flex items-center justify-between gap-2">
            <label htmlFor={fieldId('narration')} className="text-xs font-medium text-muted-foreground">
              Narration
            </label>
            <EmotionSelect value={scene.narration_emotion} onChange={(v) => set({ narration_emotion: v })} label="Narration emotion" />
          </div>
          <Textarea
            id={fieldId('narration')}
            rows={3}
            value={scene.narration}
            onChange={(e) => set({ narration: e.target.value })}
            className="text-[15px] leading-relaxed"
          />
        </div>

        {(scene.dialogue.length > 0 || cast.length > 0) && (
          <div>
            <Kicker className="mb-1.5">Dialogue</Kicker>
            <ul className="space-y-2">
              {scene.dialogue.map((line, i) => {
                const c = castById.get(line.character_id);
                return (
                  <li key={i} className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/20 p-2 sm:flex-row sm:items-start">
                    <div className="flex items-center gap-2 sm:w-44">
                      <CharacterAvatar character={c ?? { name: line.character, media: [] }} size={28} />
                      <Select
                        value={line.character_id}
                        onValueChange={(v) => {
                          const next = [...scene.dialogue];
                          next[i] = { ...line, character_id: v, character: castById.get(v)?.name ?? line.character };
                          set({ dialogue: next });
                        }}
                      >
                        <SelectTrigger aria-label={`Speaker of line ${i + 1}`} className="h-9 min-w-0 flex-1 text-xs">
                          <SelectValue>{c?.name ?? line.character}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {!c && <SelectItem value={line.character_id}>{line.character}</SelectItem>}
                          {cast.map((x) => (
                            <SelectItem key={x.id} value={String(x.id)}>
                              {x.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Textarea
                      rows={1}
                      aria-label={`Line ${i + 1}`}
                      value={line.text}
                      onChange={(e) => {
                        const next = [...scene.dialogue];
                        next[i] = { ...line, text: e.target.value };
                        set({ dialogue: next });
                      }}
                      className="min-h-9 flex-1 py-1.5"
                    />
                    <div className="flex items-center gap-1">
                      <EmotionSelect
                        value={line.emotion}
                        label={`Emotion of line ${i + 1}`}
                        onChange={(v) => {
                          const next = [...scene.dialogue];
                          next[i] = { ...line, emotion: v };
                          set({ dialogue: next });
                        }}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9 shrink-0"
                        onClick={() => set({ dialogue: scene.dialogue.filter((_, idx) => idx !== i) })}
                        aria-label={`Remove line ${i + 1}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
            {cast.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1"
                onClick={() =>
                  set({
                    dialogue: [
                      ...scene.dialogue,
                      { character_id: String(cast[0].id), character: cast[0].name, text: '', emotion: null },
                    ],
                  })
                }
              >
                <Plus className="h-3.5 w-3.5" /> Add line
              </Button>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor={fieldId('shot')} className="mb-1 block text-xs font-medium text-muted-foreground">
              Shot
            </label>
            <Select value={scene.shot.kind} onValueChange={(v) => setShot({ kind: v as ShotKind })}>
              <SelectTrigger id={fieldId('shot')} className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SHOT_KINDS.map((k) => (
                  <SelectItem key={k.value} value={k.value}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label htmlFor={fieldId('camera')} className="mb-1 block text-xs font-medium text-muted-foreground">
              Camera
            </label>
            <Select value={scene.shot.camera} onValueChange={(v) => setShot({ camera: v as Camera })}>
              <SelectTrigger id={fieldId('camera')} className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CAMERAS.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label htmlFor={fieldId('motion')} className="mb-1 block text-xs font-medium text-muted-foreground">
              Move
            </label>
            <Select value={scene.shot.motion} onValueChange={(v) => setShot({ motion: v as ShotMotion })}>
              <SelectTrigger id={fieldId('motion')} className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MOTIONS.map((m) => (
                  <SelectItem key={m.value} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {cast.length > 0 && (
          <div>
            <Kicker className="mb-1.5">In shot</Kicker>
            <div className="flex flex-wrap gap-1.5">
              {cast.map((c) => {
                const on = scene.shot.characters.includes(String(c.id));
                return (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleInShot(String(c.id))}
                    className={cn(
                      'inline-flex min-h-9 items-center gap-1.5 rounded-full border py-0.5 pl-0.5 pr-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      on ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <CharacterAvatar character={c} size={24} />
                    {c.name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto]">
          <div>
            <label htmlFor={fieldId('ost')} className="mb-1 block text-xs font-medium text-muted-foreground">
              On-screen text
            </label>
            <Input
              id={fieldId('ost')}
              value={scene.on_screen_text ?? ''}
              onChange={(e) => set({ on_screen_text: e.target.value || null })}
              placeholder="Optional"
              className="h-9"
            />
          </div>
          <div>
            <span className="mb-1 block text-xs font-medium text-muted-foreground">Stat card</span>
            {scene.stat ? (
              <div className="flex items-center gap-1.5">
                <Input
                  aria-label="Stat value"
                  value={scene.stat.value}
                  onChange={(e) => set({ stat: { ...scene.stat!, value: e.target.value } })}
                  className="h-9 w-24 font-mono"
                />
                <Input
                  aria-label="Stat label"
                  value={scene.stat.label}
                  onChange={(e) => set({ stat: { ...scene.stat!, label: e.target.value } })}
                  className="h-9 w-36"
                />
                <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => set({ stat: null })} aria-label="Remove stat card">
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <Button variant="outline" size="sm" className="h-9" onClick={() => set({ stat: { value: '', label: '', fact_id: null } })}>
                <Plus className="h-3.5 w-3.5" /> Add stat
              </Button>
            )}
          </div>
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowDirection((v) => !v)}
            aria-expanded={showDirection}
            aria-controls={fieldId('direction')}
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronDown className={cn('h-3 w-3 transition-transform', showDirection && 'rotate-180')} /> Direction and visual prompt
          </button>
          {showDirection && (
            <div id={fieldId('direction')} className="mt-2 space-y-2">
              <Textarea
                rows={2}
                aria-label="Scene direction"
                value={scene.shot.direction}
                onChange={(e) => setShot({ direction: e.target.value })}
                placeholder="What happens in the frame"
              />
              <Textarea
                rows={3}
                aria-label="Visual prompt"
                value={scene.shot.visual_prompt}
                onChange={(e) => setShot({ visual_prompt: e.target.value })}
                className="font-mono text-xs"
              />
            </div>
          )}
        </div>

        {scene.questions.length > 0 && (
          <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
            <Kicker className="mb-1 text-warning">Facts needed</Kicker>
            <ul className="list-inside list-disc space-y-0.5">
              {scene.questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        )}
        {scene.sources.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Sources: {scene.sources.map((s) => s.source || s.fact_id).join('; ')}
          </p>
        )}
        {flags.length > 0 && <FlagList flags={flags} />}

        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={onRevise} disabled={!!reviseDisabled} title={reviseDisabled}>
            <PenLine className="h-3.5 w-3.5" /> Revise this scene
          </Button>
        </div>
      </div>
    </article>
  );
}
