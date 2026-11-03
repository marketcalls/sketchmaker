import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { motionGraphicsApi, type MGAspect, type MGTemplate } from '@/api/motionGraphics';
import { ASPECT_RATIO_CLASS, AspectGlyph, MutedChip, TechChip } from './shared';

// Template cards with a flipbook preview: one still per scene of the sample
// storyboard, rendered by the server (GET /templates/{id}/preview.png) and
// cycled while the card is hovered or focused.

const cache = new Map<string, string>();
const inflight = new Map<string, Promise<string>>();

function stillUrl(tid: string, style: string | undefined, aspect: MGAspect, scene: number): Promise<string> {
  const key = `${tid}|${style ?? ''}|${aspect}|${scene}`;
  const hit = cache.get(key);
  if (hit) return Promise.resolve(hit);
  const pending = inflight.get(key);
  if (pending) return pending;
  const p = motionGraphicsApi
    .templatePreview(tid, { style, aspect, scene, scale: 0.35 })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      cache.set(key, url);
      inflight.delete(key);
      return url;
    })
    .catch((err) => {
      inflight.delete(key);
      throw err;
    });
  inflight.set(key, p);
  return p;
}

function Flipbook({ template, style, aspect, frames }: { template: MGTemplate; style?: string; aspect: MGAspect; frames: number }) {
  const [urls, setUrls] = useState<(string | null)[]>(() => Array(frames).fill(null));
  const [index, setIndex] = useState(1 % frames);
  const [hover, setHover] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let alive = true;
    setUrls(Array(frames).fill(null));
    const first = 1 % frames;
    stillUrl(template.id, style, aspect, first)
      .then((u) => alive && setUrls((prev) => prev.map((x, i) => (i === first ? u : x))))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [template.id, style, aspect, frames]);

  useEffect(() => {
    if (!hover) {
      if (timer.current) clearInterval(timer.current);
      setIndex(1 % frames);
      return;
    }
    let alive = true;
    for (let i = 0; i < frames; i++) {
      stillUrl(template.id, style, aspect, i)
        .then((u) => alive && setUrls((prev) => prev.map((x, k) => (k === i ? u : x))))
        .catch(() => undefined);
    }
    timer.current = setInterval(() => setIndex((i) => (i + 1) % frames), 750);
    return () => {
      alive = false;
      if (timer.current) clearInterval(timer.current);
    };
  }, [hover, template.id, style, aspect, frames]);

  const shown = urls[index] ?? urls.find(Boolean) ?? null;
  return (
    <div
      className={cn('relative overflow-hidden rounded-lg border border-border bg-secondary/30', ASPECT_RATIO_CLASS[aspect])}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
    >
      {shown ? (
        <img src={shown} alt={`${template.name} preview`} className="h-full w-full object-cover" draggable={false} />
      ) : (
        <div className="shimmer h-full w-full" />
      )}
      <div className="absolute bottom-2 left-2 flex gap-1">
        {Array.from({ length: frames }).map((_, i) => (
          <span key={i} className={cn('h-1 w-3 rounded-full', i === index ? 'bg-foreground/90' : 'bg-foreground/30')} />
        ))}
      </div>
    </div>
  );
}

export function TemplateGallery({
  templates,
  style,
  aspect,
  onPick,
  busyId,
}: {
  templates: MGTemplate[];
  style?: string;
  aspect: MGAspect;
  onPick: (t: MGTemplate) => void;
  busyId?: string | null;
}) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {templates.map((t) => {
        const a = t.aspects.includes(aspect) ? aspect : t.default_aspect;
        const frames = Math.min(4, t.scene_types.length + (t.requires_source ? 1 : 0));
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onPick(t)}
            disabled={!!busyId}
            className="group flex flex-col gap-3 rounded-xl border border-border bg-card p-3 text-left transition-colors duration-150 hover:border-foreground/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
          >
            <Flipbook template={t} style={style} aspect={a} frames={Math.max(2, frames)} />
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold leading-tight">{t.name}</h3>
                {busyId === t.id ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Creating" />
                ) : (
                  <ArrowRight className="h-4 w-4 text-muted-foreground transition-colors group-hover:text-foreground" />
                )}
              </div>
              <p className="line-clamp-2 text-xs text-muted-foreground">{t.description}</p>
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                {t.data_kind ? <TechChip>Data</TechChip> : <MutedChip>{t.category}</MutedChip>}
                <span className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
                  {t.aspects.map((x) => (
                    <AspectGlyph key={x} aspect={x} className="opacity-70" />
                  ))}
                </span>
                <span className="font-mono text-[11px] tabular text-muted-foreground">
                  {t.length.min_seconds} to {t.length.max_seconds} s
                </span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
