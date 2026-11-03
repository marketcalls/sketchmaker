import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import {
  textOverlayApi,
  type LayerBox,
  type TextAlign,
  type TextBackdrop,
  type TextLayer,
  type TextOverlayConfig,
  type TextPreview,
  type TextRole,
  type TextSpec,
} from '@/api/textOverlay';
import type { GeneratedImage } from '@/types';

// Add text: an editor for up to four exact text layers on a copy of a gallery
// image. The server draws every preview with the same bundled fonts as the
// final image (backend services/text_overlay.py), so what you see is what is
// saved. Layers are dragged by their outlines; the guides show the format's
// safe zone and the warnings say where text would be too small to read.

let configCache: TextOverlayConfig | null = null;

const PREVIEW_DELAY_MS = 280;

function layerFromRole(config: TextOverlayConfig, role: TextRole): TextLayer {
  const r = config.roles.find((x) => x.id === role)!;
  const paper = config.palette[0]?.hex ?? '#F7F7F2';
  const ink = config.palette[1]?.hex ?? '#0B0D12';
  const lime = config.palette[2]?.hex ?? paper;
  return {
    role,
    text: '',
    weight: r.weight,
    size: r.size,
    color: role === 'label' ? ink : paper,
    uppercase: r.uppercase,
    align: 'center',
    x: 0.5,
    y: r.y,
    max_width: 0.86,
    line_height: 1.1,
    backdrop: r.backdrop,
    backdrop_color: role === 'label' ? lime : ink,
    backdrop_opacity: role === 'headline' ? 0.55 : 0.92,
    stroke: false,
    stroke_color: ink,
    shadow: false,
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {hint && <span className="text-[11px] text-muted-foreground/80">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function Pills<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            'rounded-md border px-2.5 py-1 text-xs transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            o.value === value
              ? 'border-primary/60 bg-primary/10 text-foreground'
              : 'border-border bg-secondary/40 text-muted-foreground hover:border-foreground/30 hover:text-foreground'
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Swatches({
  palette,
  value,
  onChange,
  label,
}: {
  palette: { name: string; hex: string }[];
  value: string;
  onChange: (hex: string) => void;
  label: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label={label}>
      {palette.map((p) => (
        <button
          key={p.hex}
          type="button"
          role="radio"
          aria-checked={value.toUpperCase() === p.hex.toUpperCase()}
          title={p.name}
          onClick={() => onChange(p.hex)}
          className={cn(
            'h-7 w-7 rounded-full border transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            value.toUpperCase() === p.hex.toUpperCase() ? 'scale-110 border-primary ring-2 ring-primary/50' : 'border-border'
          )}
          style={{ backgroundColor: p.hex }}
        >
          <span className="sr-only">{p.name}</span>
        </button>
      ))}
      <label className="ml-1 flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-7 w-9 cursor-pointer rounded border border-border bg-transparent"
          aria-label={`${label}: custom colour`}
        />
        {value.toUpperCase()}
      </label>
    </div>
  );
}

export function AddTextDialog({
  image,
  open,
  onOpenChange,
  onCreated,
}: {
  image: Pick<GeneratedImage, 'id' | 'url' | 'width' | 'height'> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (image: GeneratedImage) => void;
}) {
  const [config, setConfig] = useState<TextOverlayConfig | null>(configCache);
  const [font, setFont] = useState('anton');
  const [layers, setLayers] = useState<TextLayer[]>([]);
  const [selected, setSelected] = useState(0);
  const [preview, setPreview] = useState<TextPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [drag, setDrag] = useState<{ index: number; dx: number; dy: number } | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const dragStart = useRef<{ index: number; px: number; py: number; x: number; y: number } | null>(null);
  const seq = useRef(0);

  // Load the editor's config once, and start every session with a headline.
  useEffect(() => {
    if (!open) return;
    let alive = true;
    const start = (cfg: TextOverlayConfig) => {
      setLayers([layerFromRole(cfg, 'headline')]);
      setSelected(0);
      setPreview(null);
      setError(null);
      setSaved(null);
    };
    if (configCache) {
      start(configCache);
    } else {
      textOverlayApi
        .config()
        .then((cfg) => {
          configCache = cfg;
          if (!alive) return;
          setConfig(cfg);
          start(cfg);
        })
        .catch((err) => alive && setError(getErrorMessage(err, 'Could not load the text editor')));
    }
    return () => {
      alive = false;
    };
  }, [open, image?.id]);

  const spec: TextSpec = useMemo(
    () => ({ font, layers: layers.filter((l) => l.text.trim().length > 0) }),
    [font, layers]
  );
  // Index in `layers` of each layer sent to the server (blank ones are skipped).
  const sentIndex = useMemo(() => layers.map((l, i) => (l.text.trim() ? i : -1)).filter((i) => i >= 0), [layers]);

  // Server preview, debounced; stale replies are dropped.
  const imageId = image?.id;
  useEffect(() => {
    if (!open || !imageId || !config) return;
    if (spec.layers.length === 0) {
      setPreview(null);
      return;
    }
    const id = ++seq.current;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setPreviewing(true);
      try {
        const p = await textOverlayApi.preview(imageId, spec, controller.signal);
        if (id === seq.current) {
          setPreview(p);
          setError(null);
        }
      } catch (err) {
        if (id === seq.current && !controller.signal.aborted) setError(getErrorMessage(err, 'The preview could not be drawn'));
      } finally {
        if (id === seq.current) setPreviewing(false);
      }
    }, PREVIEW_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, imageId, config, spec]);

  const update = useCallback((index: number, patch: Partial<TextLayer>) => {
    setLayers((ls) => ls.map((l, i) => (i === index ? { ...l, ...patch } : l)));
    setSaved(null);
  }, []);

  const format = preview?.format ?? guessFormat(image?.width, image?.height);
  const fmt = config?.formats[format] ?? config?.formats.other;
  const zone = fmt?.safe_zone;
  const layer = layers[selected];
  const fontInfo = config?.fonts.find((f) => f.key === font);
  const usedRoles = new Set(layers.map((l) => l.role));
  const addable = (config?.roles ?? []).filter((r) => !usedRoles.has(r.id));
  const warnings = preview?.warnings ?? [];

  const boxFor = (index: number): LayerBox | null => {
    const k = sentIndex.indexOf(index);
    if (k < 0 || !preview?.boxes[k]) return null;
    const b = preview.boxes[k];
    if (drag && drag.index === index) return { x0: b.x0 + drag.dx, x1: b.x1 + drag.dx, y0: b.y0 + drag.dy, y1: b.y1 + drag.dy };
    return b;
  };

  const onPointerDown = (index: number, e: ReactPointerEvent<HTMLDivElement>) => {
    const l = layers[index];
    setSelected(index);
    dragStart.current = { index, px: e.clientX, py: e.clientY, x: l.x, y: l.y };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const s = dragStart.current;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!s || !rect) return;
    const dx = (e.clientX - s.px) / rect.width;
    const dy = (e.clientY - s.py) / rect.height;
    setDrag({ index: s.index, dx, dy });
  };
  const onPointerUp = () => {
    const s = dragStart.current;
    if (s && drag) {
      update(s.index, { x: clamp(s.x + drag.dx), y: clamp(s.y + drag.dy) });
    }
    dragStart.current = null;
    setDrag(null);
  };

  const save = async () => {
    if (!image || spec.layers.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const res = await textOverlayApi.render(image.id, spec);
      setSaved('Saved as a new image in your gallery. The original is unchanged.');
      onCreated?.(res.image);
    } catch (err) {
      setError(getErrorMessage(err, 'The text could not be added'));
    } finally {
      setSaving(false);
    }
  };

  const aspect = image?.width && image?.height ? image.width / image.height : 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add text</DialogTitle>
          <DialogDescription>
            Exact text in one typeface, drawn on a copy of this image. Free; the original stays in your gallery.
          </DialogDescription>
        </DialogHeader>

        {!config || !image ? (
          <p className="py-10 text-center text-sm text-muted-foreground">{error ?? 'Loading the editor'}</p>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            {/* Stage */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="font-mono tabular">
                  {image.width && image.height ? `${image.width}x${image.height}` : ''} {format !== 'other' ? format : ''}
                </span>
                <span aria-live="polite">{previewing ? 'Drawing preview' : preview ? 'Exact preview' : 'Type to preview'}</span>
              </div>
              <div
                ref={stageRef}
                className="relative mx-auto w-full overflow-hidden rounded-xl border border-border bg-secondary/30 select-none"
                style={{ aspectRatio: String(aspect), maxHeight: '70vh', maxWidth: `calc(70vh * ${aspect})` }}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
              >
                <img
                  src={preview?.image ?? image.url}
                  alt="Preview of the image with its text"
                  className="absolute inset-0 h-full w-full object-contain"
                  draggable={false}
                />
                {zone && (
                  <div className="pointer-events-none absolute inset-0" aria-hidden="true">
                    <div className="absolute inset-x-0 top-0 bg-warning/15" style={{ height: `${zone.top * 100}%` }} />
                    <div className="absolute inset-x-0 bottom-0 bg-warning/15" style={{ height: `${zone.bottom * 100}%` }} />
                    <div
                      className="absolute border border-dashed border-warning/60"
                      style={{
                        left: `${zone.left * 100}%`,
                        right: `${zone.right * 100}%`,
                        top: `${zone.top * 100}%`,
                        bottom: `${zone.bottom * 100}%`,
                      }}
                    />
                  </div>
                )}
                {layers.map((l, i) => {
                  const b = boxFor(i);
                  if (!b) return null;
                  return (
                    <div
                      key={i}
                      role="button"
                      tabIndex={0}
                      aria-label={`Move the ${roleLabel(config, l.role)}`}
                      onPointerDown={(e) => onPointerDown(i, e)}
                      onKeyDown={(e) => nudge(e, i, l, update)}
                      className={cn(
                        'absolute cursor-move rounded-sm border touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        i === selected ? 'border-primary bg-primary/5' : 'border-foreground/30 hover:border-foreground/60'
                      )}
                      style={{
                        left: `${b.x0 * 100}%`,
                        top: `${b.y0 * 100}%`,
                        width: `${(b.x1 - b.x0) * 100}%`,
                        height: `${(b.y1 - b.y0) * 100}%`,
                      }}
                    />
                  );
                })}
              </div>
              {zone && (
                <p className="text-xs text-muted-foreground">
                  Guides: keep text inside the dashed frame, clear of {zone.name}. Drag a layer, or use the arrow keys.
                </p>
              )}
            </div>

            {/* Controls */}
            <div className="space-y-5">
              <Field label="Typeface" hint="one per card">
                <Select value={font} onValueChange={setFont}>
                  <SelectTrigger aria-label="Typeface">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {config.fonts.map((f) => (
                      <SelectItem key={f.key} value={f.key}>
                        {f.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fontInfo && <p className="text-xs text-muted-foreground">{fontInfo.hint}</p>}
              </Field>

              <Field label="Layers" hint={`${layers.length} of ${config.max_layers}`}>
                <div className="flex flex-wrap gap-1.5">
                  {layers.map((l, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setSelected(i)}
                      className={cn(
                        'rounded-md border px-3 py-1.5 text-xs transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        i === selected ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground'
                      )}
                    >
                      {roleLabel(config, l.role)}
                    </button>
                  ))}
                  {layers.length < config.max_layers &&
                    addable.map((r) => (
                      <Button
                        key={r.id}
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setLayers((ls) => [...ls, layerFromRole(config, r.id)]);
                          setSelected(layers.length);
                        }}
                      >
                        Add {r.label.toLowerCase()}
                      </Button>
                    ))}
                </div>
              </Field>

              {layer && (
                <div className="space-y-4 rounded-xl border border-border bg-secondary/20 p-4">
                  <Field label="Text" hint={`${layer.text.length}/${config.max_text_chars}`}>
                    <Textarea
                      value={layer.text}
                      maxLength={config.max_text_chars}
                      rows={2}
                      placeholder={`${roleLabel(config, layer.role)} text, exactly as it should read`}
                      onChange={(e) => update(selected, { text: e.target.value })}
                    />
                  </Field>
                  <div className="grid grid-cols-2 gap-4">
                    <Field label="Size" hint={`${layer.size.toFixed(1)}% of width`}>
                      <Slider
                        aria-label="Text size"
                        min={1}
                        max={20}
                        step={0.2}
                        value={[layer.size]}
                        onValueChange={(v) => update(selected, { size: v[0] })}
                      />
                    </Field>
                    <Field label="Weight" hint={String(layer.weight)}>
                      <Slider
                        aria-label="Text weight"
                        min={fontInfo?.weights[0] ?? 100}
                        max={fontInfo?.weights[1] ?? 900}
                        step={100}
                        value={[layer.weight]}
                        disabled={!fontInfo || fontInfo.weights[0] === fontInfo.weights[1]}
                        onValueChange={(v) => update(selected, { weight: v[0] })}
                      />
                    </Field>
                  </div>
                  {fmt && layer.size < fmt.min_size && (
                    <p className="text-xs text-warning">
                      Under {fmt.min_size.toFixed(1)}% this reads too small on {fmt.destination}.
                    </p>
                  )}
                  <Field label="Colour">
                    <Swatches palette={config.palette} value={layer.color} label="Text colour" onChange={(hex) => update(selected, { color: hex })} />
                  </Field>
                  <div className="grid grid-cols-2 gap-4">
                    <Field label="Align">
                      <Pills<TextAlign>
                        label="Alignment"
                        value={layer.align}
                        onChange={(v) => update(selected, { align: v })}
                        options={[
                          { value: 'left', label: 'Left' },
                          { value: 'center', label: 'Centre' },
                          { value: 'right', label: 'Right' },
                        ]}
                      />
                    </Field>
                    <div className="flex items-end justify-between gap-2 pb-1">
                      <label htmlFor="to-upper" className="text-sm">Capitals</label>
                      <Switch id="to-upper" checked={layer.uppercase} onCheckedChange={(v) => update(selected, { uppercase: v })} />
                    </div>
                  </div>
                  <Field label="Position">
                    <Pills<string>
                      label="Position preset"
                      value={positionId(config, layer)}
                      onChange={(id) => {
                        const p = config.positions.find((x) => x.id === id);
                        if (p) update(selected, { x: p.x, y: p.y });
                      }}
                      options={config.positions.map((p) => ({ value: p.id, label: positionLabel(p.id) }))}
                    />
                  </Field>
                  <Field label="Legibility">
                    <Pills<TextBackdrop>
                      label="Backdrop"
                      value={layer.backdrop}
                      onChange={(v) => update(selected, { backdrop: v })}
                      options={[
                        { value: 'none', label: 'None' },
                        { value: 'scrim', label: 'Soft scrim' },
                        { value: 'box', label: 'Box' },
                      ]}
                    />
                  </Field>
                  {layer.backdrop !== 'none' && (
                    <div className="space-y-3">
                      <Swatches
                        palette={config.palette}
                        value={layer.backdrop_color}
                        label="Backdrop colour"
                        onChange={(hex) => update(selected, { backdrop_color: hex })}
                      />
                      <Field label="Backdrop opacity" hint={`${Math.round(layer.backdrop_opacity * 100)}%`}>
                        <Slider
                          aria-label="Backdrop opacity"
                          min={0}
                          max={100}
                          step={5}
                          value={[Math.round(layer.backdrop_opacity * 100)]}
                          onValueChange={(v) => update(selected, { backdrop_opacity: v[0] / 100 })}
                        />
                      </Field>
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                    <label className="flex items-center gap-2 text-sm">
                      <Switch checked={layer.stroke} onCheckedChange={(v) => update(selected, { stroke: v })} aria-label="Outline" />
                      Outline
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <Switch checked={layer.shadow} onCheckedChange={(v) => update(selected, { shadow: v })} aria-label="Shadow" />
                      Shadow
                    </label>
                    {layers.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="ml-auto text-destructive"
                        onClick={() => {
                          setLayers((ls) => ls.filter((_, i) => i !== selected));
                          setSelected(0);
                        }}
                      >
                        Remove layer
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {warnings.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-warning/40 bg-warning/10 p-3 text-xs text-warning" aria-live="polite">
                  {warnings.map((w, i) => (
                    <li key={i}>{w.message}</li>
                  ))}
                </ul>
              )}
              {error && <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
              {saved && <p role="status" className="rounded-lg border border-success/40 bg-success/10 p-3 text-sm text-success">{saved}</p>}

              <div className="flex items-center justify-end gap-2">
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  Close
                </Button>
                <Button className="min-w-[10.5rem]" onClick={save} disabled={saving || spec.layers.length === 0}>
                  {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                  {saving ? 'Saving' : 'Save as new image'}
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function clamp(v: number) {
  return Math.min(1, Math.max(0, v));
}

function roleLabel(config: TextOverlayConfig, role: TextRole) {
  return config.roles.find((r) => r.id === role)?.label ?? role;
}

function positionLabel(id: string) {
  return (
    { top: 'Top', centre: 'Centre', bottom: 'Bottom', upper_third: 'Upper third', lower_third: 'Lower third' } as Record<
      string,
      string
    >
  )[id] ?? id;
}

function positionId(config: TextOverlayConfig, l: TextLayer) {
  const p = config.positions.find((x) => Math.abs(x.x - l.x) < 0.01 && Math.abs(x.y - l.y) < 0.01);
  return p?.id ?? 'custom';
}

function guessFormat(w?: number, h?: number) {
  if (!w || !h) return 'other';
  const r = w / h;
  const named: [string, number][] = [
    ['9:16', 9 / 16],
    ['4:5', 4 / 5],
    ['1:1', 1],
    ['16:9', 16 / 9],
  ];
  const best = named.reduce((a, b) => (Math.abs(b[1] - r) / b[1] < Math.abs(a[1] - r) / a[1] ? b : a));
  return Math.abs(best[1] - r) / best[1] < 0.06 ? best[0] : 'other';
}

function nudge(
  e: React.KeyboardEvent<HTMLDivElement>,
  index: number,
  l: TextLayer,
  update: (index: number, patch: Partial<TextLayer>) => void
) {
  const step = e.shiftKey ? 0.05 : 0.01;
  const moves: Record<string, [number, number]> = {
    ArrowLeft: [-step, 0],
    ArrowRight: [step, 0],
    ArrowUp: [0, -step],
    ArrowDown: [0, step],
  };
  const m = moves[e.key];
  if (!m) return;
  e.preventDefault();
  update(index, { x: clamp(l.x + m[0]), y: clamp(l.y + m[1]) });
}
