import { useRef, useState } from 'react';
import { FileUp, Loader2, Plus, Shuffle, Trash2, Wand2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { getErrorMessage } from '@/utils/errors';
import {
  motionGraphicsApi,
  type DataTable,
  type DataView,
  type Intensity,
  type MGCatalog,
  type MGProject,
  type MGSpec,
  type MGTemplate,
} from '@/api/motionGraphics';
import { useMotionGraphicsStore } from '@/stores/motionGraphicsStore';
import { ErrorNote, FieldLabel, MutedChip, PillGroup, SectionTitle, TechChip } from './shared';
import { VoicePacing } from './VoicePacing';
import { VoiceSettings } from './VoiceSettings';

// ---------------------------------------------------------------------------
// Style
// ---------------------------------------------------------------------------

export function StylePanel({
  catalog,
  spec,
  onSpec,
}: {
  catalog: MGCatalog;
  spec: MGSpec;
  onSpec: (fn: (s: MGSpec) => MGSpec) => void;
}) {
  return (
    <div className="space-y-5">
      <div>
        <SectionTitle>Style</SectionTitle>
        <div className="grid gap-2">
          {catalog.styles.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onSpec((x) => ({ ...x, style_id: s.id }))}
              className={cn(
                'flex items-center gap-3 rounded-lg border p-3 text-left transition-colors',
                spec.style_id === s.id ? 'border-primary/60 bg-primary/10' : 'border-border hover:border-foreground/20',
              )}
            >
              <div className="flex shrink-0 overflow-hidden rounded-md border border-border">
                {s.swatches.map((c, i) => (
                  // Swatches are the style's own video colors (data), not UI styling.
                  // A style may repeat a color (background and panel), so key by position.
                  <span key={`${i}-${c}`} className="h-8 w-3" style={{ backgroundColor: c }} />
                ))}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium">{s.name}</p>
                <p className="line-clamp-2 text-xs text-muted-foreground">{s.description}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
      <div>
        <FieldLabel hint="overrides the brand kit">Motion intensity</FieldLabel>
        <PillGroup<Intensity | 'brand'>
          value={spec.options.intensity ?? 'brand'}
          onChange={(v) => onSpec((x) => ({ ...x, options: { ...x.options, intensity: v === 'brand' ? null : v } }))}
          options={[
            { id: 'brand', label: 'Brand' },
            { id: 'calm', label: 'Calm' },
            { id: 'standard', label: 'Standard' },
            { id: 'punchy', label: 'Punchy' },
          ]}
        />
      </div>
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-secondary/20 p-3">
        <div>
          <p className="text-sm">Layout variation</p>
          <p className="font-mono text-[10px] text-muted-foreground">seed {spec.seed}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onSpec((x) => ({ ...x, seed: Math.floor(Math.random() * 2_000_000_000) + 1 }))}
        >
          <Shuffle className="h-4 w-4" /> Shuffle
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

function tableToCsv(t: DataTable | null): string {
  if (!t) return '';
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [t.columns, ...t.rows].map((r) => r.map(esc).join(',')).join('\n');
}

const MAX_ROWS_SHOWN = 40;

export function DataPanel({
  tpl,
  spec,
  view,
  onSpec,
}: {
  tpl: MGTemplate;
  spec: MGSpec;
  view: DataView | null;
  onSpec: (fn: (s: MGSpec) => MGSpec) => void;
}) {
  const [paste, setPaste] = useState('');
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [local, setLocal] = useState<DataView | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const table = spec.data;
  const shown = local ?? view;

  const load = async (csv: string) => {
    setParsing(true);
    setError(null);
    try {
      const { table: t, view: v } = await motionGraphicsApi.parseData(csv, tpl.data_kind);
      setLocal(v);
      onSpec((s) => ({ ...s, data: t }));
      setPaste('');
    } catch (err) {
      setError(getErrorMessage(err, 'Could not read the data'));
    } finally {
      setParsing(false);
    }
  };

  const setCell = (r: number, c: number, v: string) => {
    setLocal(null);
    onSpec((s) => {
      if (!s.data) return s;
      const rows = s.data.rows.map((row, i) => (i === r ? row.map((x, j) => (j === c ? v : x)) : row));
      return { ...s, data: { ...s.data, rows } };
    });
  };
  const setHeader = (c: number, v: string) =>
    onSpec((s) => (s.data ? { ...s, data: { ...s.data, columns: s.data.columns.map((x, j) => (j === c ? v : x)) } } : s));
  const addRow = () =>
    onSpec((s) => (s.data ? { ...s, data: { ...s.data, rows: [...s.data.rows, s.data.columns.map(() => '')] } } : s));
  const addCol = () =>
    onSpec((s) =>
      s.data
        ? { ...s, data: { columns: [...s.data.columns, `Column ${s.data.columns.length + 1}`], rows: s.data.rows.map((r) => [...r, '']) } }
        : s,
    );
  const delRow = (r: number) =>
    onSpec((s) => (s.data ? { ...s, data: { ...s.data, rows: s.data.rows.filter((_, i) => i !== r) } } : s));

  const opts = spec.data_options;
  const setOpt = (k: keyof MGSpec['data_options'], v: unknown) =>
    onSpec((s) => ({ ...s, data_options: { ...s.data_options, [k]: v } }));

  if (!tpl.data_kind) {
    return <p className="text-sm text-muted-foreground">This template takes its numbers from the scene fields.</p>;
  }
  return (
    <div className="space-y-5">
      <div>
        <SectionTitle aside={shown?.format && <TechChip>{shown.format} format</TechChip>}>Data</SectionTitle>
        <Textarea
          value={paste}
          onChange={(e) => setPaste(e.target.value)}
          rows={4}
          placeholder="Paste CSV or spreadsheet cells here (wide: one row per period; long: period, name, value)"
          className="font-mono text-xs"
        />
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => load(paste)} disabled={!paste.trim() || parsing}>
            {parsing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />} Use pasted data
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt,text/csv"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (!f) return;
              if (f.size > 190_000) {
                setError('The file is too large; keep it under 190 KB (400 rows).');
                return;
              }
              await load(await f.text());
            }}
          />
          <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
            <FileUp className="h-4 w-4" /> Upload CSV
          </Button>
          {table && table.rows.length > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setPaste(tableToCsv(table))}>
              Edit as text
            </Button>
          )}
          {tpl.sample_data && (
            <Button size="sm" variant="ghost" onClick={() => load(tpl.sample_data as string)}>
              Sample
            </Button>
          )}
        </div>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      {shown && (
        <div className="space-y-1.5">
          {shown.problems.map((p) => (
            <p key={p} className="text-xs text-destructive">
              {p}
            </p>
          ))}
          {shown.warnings.map((w) => (
            <p key={w} className="text-xs text-warning">
              {w}
            </p>
          ))}
          {shown.ok && (
            <p className="font-mono text-[11px] text-success">
              {shown.periods ? `${shown.periods.length} periods, ${shown.entities?.length} names` : ''}
              {shown.series ? `${shown.labels?.length} rows, ${shown.series.length} series, suggested ${shown.suggested_chart}` : ''}
              {shown.items ? `${shown.items.length} rows` : ''}
              {shown.metrics ? `${shown.metrics.length} metrics` : ''}
              {shown.units?.prefix || shown.units?.suffix ? `, units ${shown.units.prefix}${shown.units.suffix}` : ''}
            </p>
          )}
        </div>
      )}
      {table && table.columns.length > 0 && (
        <div className="max-h-80 overflow-auto rounded-lg border border-border">
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 bg-card">
              <tr>
                {table.columns.map((c, j) => (
                  <th key={j} className="border-b border-border p-0">
                    <input
                      value={c}
                      onChange={(e) => setHeader(j, e.target.value)}
                      className="w-24 bg-transparent px-2 py-1.5 font-mono text-[11px] font-semibold text-foreground outline-none focus:bg-primary/5"
                      aria-label={`Column ${j + 1} name`}
                    />
                  </th>
                ))}
                <th className="w-8 border-b border-border">
                  <button type="button" onClick={addCol} className="p-1 text-muted-foreground hover:text-foreground" aria-label="Add column">
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {table.rows.slice(0, MAX_ROWS_SHOWN).map((row, i) => (
                <tr key={i} className="border-b border-border/50">
                  {row.map((v, j) => (
                    <td key={j} className="p-0">
                      <input
                        value={v === null ? '' : String(v)}
                        onChange={(e) => setCell(i, j, e.target.value)}
                        className="w-24 bg-transparent px-2 py-1 font-mono text-[11px] text-muted-foreground outline-none focus:bg-primary/5 focus:text-foreground"
                        aria-label={`Row ${i + 1} ${table.columns[j]}`}
                      />
                    </td>
                  ))}
                  <td>
                    <button type="button" onClick={() => delRow(i)} className="p-1 text-muted-foreground hover:text-destructive" aria-label="Delete row">
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {table.rows.length > MAX_ROWS_SHOWN && (
            <p className="p-2 text-xs text-muted-foreground">
              Showing {MAX_ROWS_SHOWN} of {table.rows.length} rows. Edit larger tables in a spreadsheet and paste again.
            </p>
          )}
          <div className="p-2">
            <Button size="sm" variant="ghost" onClick={addRow}>
              <Plus className="h-4 w-4" /> Row
            </Button>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        {tpl.data_kind === 'race' && (
          <>
            <div>
              <FieldLabel hint="bars on screen">Top N</FieldLabel>
              <Input type="number" min={3} max={15} value={opts.top_n ?? ''} placeholder="auto"
                onChange={(e) => setOpt('top_n', e.target.value ? Number(e.target.value) : null)} className="font-mono" />
            </div>
            <div>
              <FieldLabel hint="seconds">Per period</FieldLabel>
              <Input type="number" min={0.3} max={4} step={0.1} value={opts.period_seconds ?? ''} placeholder="0.8"
                onChange={(e) => setOpt('period_seconds', e.target.value ? Number(e.target.value) : null)} className="font-mono" />
            </div>
          </>
        )}
        {tpl.data_kind === 'series' && (
          <div className="col-span-2">
            <FieldLabel>Chart</FieldLabel>
            <PillGroup
              size="xs"
              value={opts.chart ?? 'auto'}
              onChange={(v) => setOpt('chart', v === 'auto' ? null : v)}
              options={[
                { id: 'auto', label: 'Auto' },
                { id: 'line', label: 'Line' },
                { id: 'bar', label: 'Bar' },
                { id: 'donut', label: 'Donut' },
              ]}
            />
          </div>
        )}
        <div>
          <FieldLabel>Prefix</FieldLabel>
          <Input value={opts.prefix ?? ''} maxLength={6} placeholder="auto" onChange={(e) => setOpt('prefix', e.target.value || null)} />
        </div>
        <div>
          <FieldLabel>Suffix</FieldLabel>
          <Input value={opts.suffix ?? ''} maxLength={12} placeholder="auto" onChange={(e) => setOpt('suffix', e.target.value || null)} />
        </div>
        <div>
          <FieldLabel>Decimals</FieldLabel>
          <Input type="number" min={0} max={4} value={opts.decimals ?? ''} placeholder="auto"
            onChange={(e) => setOpt('decimals', e.target.value === '' ? null : Number(e.target.value))} className="font-mono" />
        </div>
        <label className="flex items-end gap-2 pb-2 text-xs text-muted-foreground">
          <Switch checked={!!opts.compact} onCheckedChange={(v) => setOpt('compact', v)} /> 1.2M style
        </label>
      </div>
      <p className="text-xs text-muted-foreground">Bars always start at zero. A source card is added to every data video.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------

export function AudioPanel({
  catalog,
  project,
  spec,
  onSpec,
  onGenerate,
}: {
  catalog: MGCatalog;
  project: MGProject;
  spec: MGSpec;
  onSpec: (fn: (s: MGSpec) => MGSpec) => void;
  onGenerate: () => void;
}) {
  const setProject = useMotionGraphicsStore((s) => s.setProject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const a = project.audio;

  const update = async (body: Parameters<typeof motionGraphicsApi.updateProject>[1]) => {
    setBusy(true);
    setError(null);
    try {
      setProject(await motionGraphicsApi.updateProject(project.id, body));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not update the audio settings'));
    } finally {
      setBusy(false);
    }
  };

  const audiogram = project.template_id === 'audiogram';
  return (
    <div className="space-y-5">
      <div className="space-y-3 rounded-lg border border-border p-3">
        <div className="flex items-center justify-between">
          <SectionTitle>Voiceover</SectionTitle>
          <Switch
            checked={a.voice.enabled || audiogram}
            disabled={busy || audiogram}
            onCheckedChange={(v) => update({ audio: { voice: { enabled: v } } })}
          />
        </div>
        <VoiceSettings
          catalog={catalog}
          voice={a.voice}
          busy={busy}
          onChange={(patch) => update({ audio: { voice: patch } })}
        />
        <VoicePacing spec={spec} onSpec={onSpec} />
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>
            <span className="font-mono tabular">{project.voice.chars}</span> characters
          </span>
          {project.voice.current ? <TechChip>Voice ready</TechChip> : project.voice.needed ? <MutedChip>Not generated</MutedChip> : null}
        </div>
        {project.voice.url && project.voice.current && <audio controls src={project.voice.url} className="h-9 w-full" />}
        <p className="text-xs text-muted-foreground">
          Write each scene's line in the storyboard. Text on screen follows the voice; captions are word synced.
        </p>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-3">
        <div className="flex items-center justify-between">
          <SectionTitle>Music</SectionTitle>
          <Switch checked={a.music.enabled} disabled={busy} onCheckedChange={(v) => update({ audio: { music: { enabled: v } } })} />
        </div>
        <div>
          <FieldLabel>Mood</FieldLabel>
          <Select value={a.music.mood} onValueChange={(v) => update({ audio: { music: { mood: v } } })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {catalog.music_moods
                .filter((m) => m.id !== 'none')
                .map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
        {project.music.url && project.music.current && <audio controls src={project.music.url} className="h-9 w-full" />}
        {project.music.current && project.music.beats.bpm && (
          <p className="text-xs text-muted-foreground">
            {project.music.beats.bpm} BPM, beat sync {project.music.beats.reliable ? 'on' : 'off (no steady beat found)'}
          </p>
        )}
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch
            checked={spec.options.beat_sync}
            onCheckedChange={(v) => onSpec((x) => ({ ...x, options: { ...x.options, beat_sync: v } }))}
          />
          Snap cuts to the beat when there is no voice
        </label>
        <p className="text-xs text-muted-foreground">
          Original instrumental music from ElevenLabs Music. It ducks under the voice; a generation receipt is kept.
        </p>
      </div>

      <label className="flex items-center justify-between gap-2 rounded-lg border border-border p-3 text-sm">
        <span>
          Sound effects
          <span className="block text-xs text-muted-foreground">Whooshes on transitions, hits on reveals. No provider cost.</span>
        </span>
        <Switch checked={spec.options.sfx} onCheckedChange={(v) => onSpec((x) => ({ ...x, options: { ...x.options, sfx: v } }))} />
      </label>

      {error && <ErrorNote>{error}</ErrorNote>}
      <Button variant="outline" className="w-full" onClick={onGenerate} disabled={!(a.voice.enabled || audiogram || a.music.enabled)}>
        Generate audio to listen first
      </Button>
    </div>
  );
}
