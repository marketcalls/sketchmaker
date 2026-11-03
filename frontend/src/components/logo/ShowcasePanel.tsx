import { useEffect, useMemo, useState } from 'react';
import { Download, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { LOGO_SHOWCASE_KEY, usePricingStore, formatUsd } from '@/stores/pricingStore';
import { cn } from '@/lib/utils';
import apiClient from '@/api/client';
import type { LogoAsset } from './LogoTile';
import { blobToDataUrl, downloadBlob, fetchSvgText, slugify, svgToPngBlob } from './svgUtils';

// ---------------------------------------------------------------------------
// Backdrops (ids must match logo_service.SHOWCASE_BACKGROUNDS). The swatch is
// a rough preview of the scene; the server writes the actual prompt.
// ---------------------------------------------------------------------------

type Tone = 'dark' | 'light' | 'vivid';

interface ShowcaseBackground {
  id: string;
  name: string;
  tone: Tone;
  hint: string;
  swatch: string;
}

export const SHOWCASE_BACKGROUNDS: ShowcaseBackground[] = [
  {
    id: 'void',
    name: 'The Void',
    tone: 'dark',
    hint: 'Infrastructure, security, hard tech',
    swatch: 'radial-gradient(circle at 88% 12%, rgba(130,175,225,0.4), transparent 45%), #000',
  },
  {
    id: 'frosted-horizon',
    name: 'Frosted Horizon',
    tone: 'dark',
    hint: 'Premium, design, architecture',
    swatch: 'linear-gradient(180deg, #252d37 0%, #4d5a68 50%, #222a33 100%)',
  },
  {
    id: 'fluid-abyss',
    name: 'Fluid Abyss',
    tone: 'dark',
    hint: 'AI, data, dynamic systems',
    swatch:
      'radial-gradient(circle at 28% 72%, #ff7a2f, transparent 42%), radial-gradient(circle at 74% 30%, #2f6bff, transparent 46%), #2a0e5c',
  },
  {
    id: 'studio-spotlight',
    name: 'Studio Spotlight',
    tone: 'dark',
    hint: 'Editorial, media, film',
    swatch: 'radial-gradient(ellipse at 12% 50%, #50463d 0%, #1c1916 62%)',
  },
  {
    id: 'analog-liquid',
    name: 'Analog Liquid',
    tone: 'vivid',
    hint: 'Creative, experimental, music',
    swatch: 'conic-gradient(from 200deg at 40% 60%, #ff5a1f, #1f3cff, #b6ff3a, #ff5a1f)',
  },
  {
    id: 'led-matrix',
    name: 'LED Matrix',
    tone: 'dark',
    hint: 'AI compute, web3, hardware',
    swatch: 'radial-gradient(circle, #3cff8a 1px, transparent 1.6px) 0 0 / 6px 6px, #050805',
  },
  {
    id: 'editorial-paper',
    name: 'Editorial Paper',
    tone: 'light',
    hint: 'Lifestyle, fashion, food',
    swatch: 'radial-gradient(ellipse at center, #f7f4ee 55%, #e6dccb 100%)',
  },
  {
    id: 'iridescent-frost',
    name: 'Iridescent Frost',
    tone: 'light',
    hint: 'Devices, science, research',
    swatch: 'linear-gradient(135deg, #e4e4ea 0%, #e9dff0 35%, #dcefe8 65%, #f2e4da 100%)',
  },
  {
    id: 'morning-aura',
    name: 'Morning Aura',
    tone: 'light',
    hint: 'Consumer apps, friendly AI',
    swatch:
      'radial-gradient(circle at 25% 35%, #bfeedd, transparent 45%), radial-gradient(circle at 75% 40%, #c4dcff, transparent 45%), radial-gradient(circle at 55% 88%, #ffd2b0, transparent 45%), #fbf6ec',
  },
  {
    id: 'clinical-studio',
    name: 'Clinical Studio',
    tone: 'light',
    hint: 'Data, algorithms, health',
    swatch: 'linear-gradient(180deg, #ffffff 0%, #e4e8ed 100%)',
  },
  {
    id: 'ui-container',
    name: 'UI Container',
    tone: 'light',
    hint: 'Apps and SaaS',
    swatch:
      'linear-gradient(rgba(255,255,255,0.65), rgba(255,255,255,0.65)) center / 58% 56% no-repeat, linear-gradient(135deg, #e3e8f0, #cbd5e4)',
  },
  {
    id: 'swiss-flat',
    name: 'Swiss Flat',
    tone: 'dark',
    hint: 'Established, classic, environmental',
    swatch: 'linear-gradient(90deg, #1f4d3a 0 34%, #6b1f2e 34% 67%, #1b2a4a 67% 100%)',
  },
];

const SHOWCASE_MAX = 4;

// Fallback order when the brief gives no signal, and the tie-breaker.
const DEFAULT_ORDER = [
  'void', 'editorial-paper', 'fluid-abyss', 'clinical-studio', 'frosted-horizon', 'morning-aura',
  'swiss-flat', 'studio-spotlight', 'iridescent-frost', 'ui-container', 'led-matrix', 'analog-liquid',
];

// Keywords (word starts) that point to a backdrop. The industry counts more
// than the logo description.
const KEYWORDS: Record<string, string[]> = {
  void: ['secur', 'cyber', 'infra', 'cloud', 'server', 'devops', 'network', 'encrypt', 'defen'],
  'frosted-horizon': ['premium', 'luxur', 'architect', 'interior', 'design', 'real estate', 'law', 'legal', 'jewel'],
  'fluid-abyss': ['ai', 'artificial', 'data', 'analytic', 'machine learning', 'intelligen', 'platform', 'automat'],
  'studio-spotlight': ['media', 'editorial', 'magazine', 'film', 'photo', 'publish', 'podcast', 'entertainment', 'restaurant', 'wine', 'whisk'],
  'analog-liquid': ['creative', 'art', 'agency', 'music', 'festival', 'experimental', 'studio', 'record', 'street'],
  'led-matrix': ['gaming', 'game', 'web3', 'crypto', 'blockchain', 'compute', 'chip', 'semiconductor', 'robot', 'hardware', 'esport'],
  'editorial-paper': ['fashion', 'beauty', 'cosmetic', 'lifestyle', 'coffee', 'cafe', 'bakery', 'food', 'craft', 'book', 'wedding', 'tea'],
  'iridescent-frost': ['hardware', 'device', 'science', 'lab', 'biotech', 'research', 'optic', 'audio', 'electronic'],
  'morning-aura': ['app', 'consumer', 'kids', 'child', 'education', 'learn', 'pet', 'community', 'wellness', 'mindful', 'travel'],
  'clinical-studio': ['data', 'algorithm', 'fintech', 'finance', 'bank', 'health', 'medical', 'clinic', 'pharma', 'insur', 'analytic'],
  'ui-container': ['saas', 'app', 'software', 'startup', 'productivity', 'platform', 'tool', 'dashboard'],
  'swiss-flat': ['nonprofit', 'environment', 'sustainab', 'outdoor', 'construction', 'heritage', 'sport', 'farm', 'garden', 'consult', 'school'],
};

// Personality axis (logo_service.PERSONALITY_AXES) -> backdrops for the low
// (negative) and high (positive) end.
const PERSONALITY_HINTS: Record<string, [string[], string[]]> = {
  tone: [['editorial-paper', 'swiss-flat', 'studio-spotlight'], ['void', 'fluid-abyss', 'ui-container', 'led-matrix']],
  mood: [['morning-aura', 'analog-liquid'], ['void', 'clinical-studio', 'frosted-horizon']],
  energy: [['morning-aura', 'editorial-paper', 'frosted-horizon'], ['analog-liquid', 'fluid-abyss', 'led-matrix']],
  market: [['morning-aura', 'ui-container'], ['frosted-horizon', 'studio-spotlight', 'editorial-paper']],
  form: [['clinical-studio', 'swiss-flat', 'void'], ['analog-liquid', 'iridescent-frost']],
};

const keywordPattern = (kw: string) => new RegExp(`\\b${kw}${kw.length <= 3 ? '\\b' : ''}`, 'i');

/** Four backdrops for a brief, from simple keyword and personality matches,
 *  with at least one light and one dark scene. */
export function recommendShowcase(industry: string, description: string, personality?: Record<string, number>): string[] {
  const score: Record<string, number> = Object.fromEntries(DEFAULT_ORDER.map((id) => [id, 0]));
  for (const [id, words] of Object.entries(KEYWORDS)) {
    for (const kw of words) {
      const pattern = keywordPattern(kw);
      if (industry && pattern.test(industry)) score[id] += 3;
      else if (description && pattern.test(description)) score[id] += 1;
    }
  }
  for (const [axis, value] of Object.entries(personality ?? {})) {
    const hints = PERSONALITY_HINTS[axis];
    if (!hints || !value) continue;
    for (const id of hints[value > 0 ? 1 : 0]) score[id] += Math.abs(value);
  }
  const ranked = [...DEFAULT_ORDER].sort((a, b) => score[b] - score[a] || DEFAULT_ORDER.indexOf(a) - DEFAULT_ORDER.indexOf(b));
  const picked = ranked.slice(0, SHOWCASE_MAX);
  const toneOf = (id: string) => SHOWCASE_BACKGROUNDS.find((b) => b.id === id)?.tone;
  const isLight = (id: string) => toneOf(id) === 'light';
  if (picked.every(isLight)) picked[SHOWCASE_MAX - 1] = ranked.find((id) => !isLight(id))!;
  else if (!picked.some(isLight)) picked[SHOWCASE_MAX - 1] = ranked.find(isLight)!;
  return picked;
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

interface ShowcaseItem {
  id: number;
  url: string;
  background: string;
  background_name: string;
  width: number | null;
  height: number | null;
}

interface ShowcaseResponse {
  images: ShowcaseItem[];
  requested: number;
  delivered: number;
  estimated_usd: number;
}

interface ShowcasePanelProps {
  logo: LogoAsset;
  brandName: string;
  onBrandNameChange: (value: string) => void;
  tagline: string;
  industry: string;
  personality?: Record<string, number>;
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
  errorDetail: (err: unknown, fallback: string) => string;
}

/** The mark as the model input: one color (#111111) with inner details kept
 *  on white paper, rendered to a 1024 px PNG on a white field. Falls back to
 *  the original file when the one-color edit fails. */
async function markPngDataUrl(logo: LogoAsset): Promise<string> {
  let svg: string;
  try {
    const { data } = await apiClient.post<{ svg: string }>(`/logo/${logo.id}/edit`, {
      operation: 'mono',
      color: '#111111',
      paper: '#ffffff',
      save: false,
    });
    svg = data.svg;
  } catch {
    svg = await fetchSvgText(logo.url, logo.id);
  }
  return blobToDataUrl(await svgToPngBlob(svg, 1024, '#ffffff'));
}

export function ShowcasePanel({
  logo,
  brandName,
  onBrandNameChange,
  tagline,
  industry,
  personality,
  onError,
  onNotice,
  errorDetail,
}: ShowcasePanelProps) {
  const { getModelCost } = usePricingStore();
  const recommended = useMemo(
    () => recommendShowcase(industry, logo.prompt, personality),
    // personality is a fresh object on every parent render; compare by value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [industry, logo.prompt, JSON.stringify(personality ?? {})]
  );
  const [selected, setSelected] = useState<string[]>(recommended);
  const [typography, setTypography] = useState(true);
  const [descriptor, setDescriptor] = useState('');
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<ShowcaseItem[]>([]);
  const [downloading, setDownloading] = useState<number | null>(null);

  // Reset per logo.
  useEffect(() => {
    setSelected(recommended);
    setResults([]);
    setDescriptor((tagline || industry).slice(0, 48));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logo.id]);

  const perImage = getModelCost(LOGO_SHOWCASE_KEY);
  const total = perImage !== undefined ? perImage * selected.length : undefined;
  const canGenerate = !busy && selected.length > 0;

  const toggle = (id: string) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : prev.length >= SHOWCASE_MAX ? prev : [...prev, id]
    );

  const generate = async () => {
    if (!canGenerate) return;
    setBusy(true);
    onError(null);
    onNotice(null);
    try {
      const image = await markPngDataUrl(logo);
      const { data } = await apiClient.post<ShowcaseResponse>(`/logo/${logo.id}/showcase`, {
        image,
        backgrounds: selected,
        typography,
        brand_name: brandName.trim() || null,
        descriptor: descriptor.trim() || null,
      });
      setResults((prev) => [...data.images, ...prev]);
      const missing = data.requested - data.delivered;
      onNotice(
        `${data.delivered} showcase image${data.delivered === 1 ? '' : 's'} saved to your gallery, ${formatUsd(data.estimated_usd)} used.` +
          (missing > 0 ? ` ${missing} not delivered.` : '')
      );
    } catch (err) {
      onError(errorDetail(err, 'Could not create the showcase images'));
    } finally {
      setBusy(false);
    }
  };

  const download = async (item: ShowcaseItem) => {
    setDownloading(item.id);
    try {
      const ext = item.url.split('?')[0].split('.').pop()?.toLowerCase();
      const format = ext === 'jpg' || ext === 'jpeg' || ext === 'webp' ? ext : 'png';
      const { data } = await apiClient.get<Blob>(`/gallery/${item.id}/download/${format}`, { responseType: 'blob' });
      downloadBlob(data, `${slugify(brandName || logo.prompt, 'logo')}-showcase-${item.background}.${format}`);
    } catch (err) {
      onError(errorDetail(err, 'Download failed'));
    } finally {
      setDownloading(null);
    }
  };

  const recommendedChanged = selected.join() !== recommended.join();

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Places the one-color mark on a curated 16:9 backdrop at 2K with an AI image model. Pick up to {SHOWCASE_MAX}{' '}
        backgrounds; each image is saved to your gallery.
      </p>

      <div>
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <span id="showcase-bg-label" className="text-sm font-medium">
            Backgrounds
          </span>
          <span className="text-xs tabular text-muted-foreground">
            {selected.length}/{SHOWCASE_MAX}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-labelledby="showcase-bg-label">
          {SHOWCASE_BACKGROUNDS.map((bg) => {
            const active = selected.includes(bg.id);
            const full = !active && selected.length >= SHOWCASE_MAX;
            return (
              <button
                key={bg.id}
                type="button"
                onClick={() => toggle(bg.id)}
                aria-pressed={active}
                disabled={full}
                title={bg.hint}
                className={cn(
                  'flex flex-col gap-1.5 rounded-lg border p-1.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40',
                  active ? 'border-primary/60 bg-primary/10' : 'border-border hover:border-foreground/30'
                )}
              >
                <span className="block aspect-video w-full rounded-lg border border-border" style={{ background: bg.swatch }} />
                <span className="flex items-baseline justify-between gap-1 px-1">
                  <span className="truncate text-xs font-medium">{bg.name}</span>
                  {recommended.includes(bg.id) && (
                    <span className="shrink-0 text-[10px] text-muted-foreground">Suggested</span>
                  )}
                </span>
                <span className="truncate px-1 pb-0.5 text-[11px] text-muted-foreground">{bg.hint}</span>
              </button>
            );
          })}
        </div>
        {recommendedChanged && (
          <Button size="sm" variant="ghost" className="mt-2" onClick={() => setSelected(recommended)}>
            <RefreshCw className="h-3.5 w-3.5" />
            Back to recommended
          </Button>
        )}
      </div>

      <div className="space-y-3">
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>
            Swiss micro typography
            <span className="block text-xs text-muted-foreground">
              Brand name in one corner, version number in the other, a short line at the bottom.
            </span>
          </span>
          <Switch checked={typography} onCheckedChange={setTypography} />
        </label>
        {typography && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="showcase-brand" className="mb-1.5 block text-xs font-medium">
                Brand name
              </label>
              <Input
                id="showcase-brand"
                value={brandName}
                maxLength={60}
                onChange={(e) => onBrandNameChange(e.target.value)}
                placeholder="Northwind"
                autoComplete="off"
              />
            </div>
            <div>
              <label htmlFor="showcase-descriptor" className="mb-1.5 block text-xs font-medium">
                Bottom line
              </label>
              <Input
                id="showcase-descriptor"
                value={descriptor}
                maxLength={48}
                onChange={(e) => setDescriptor(e.target.value)}
                placeholder="Outdoor gear"
                autoComplete="off"
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex items-baseline justify-between text-xs text-muted-foreground" aria-live="polite">
        <span className="font-mono tabular">{perImage !== undefined ? `${formatUsd(perImage)} x ${selected.length}` : 'Loading price'}</span>
        <span>
          <span className="font-mono tabular text-base font-medium text-foreground">{total !== undefined ? formatUsd(total) : ' '}</span>
        </span>
      </div>
      <Button className="w-full" disabled={!canGenerate} onClick={generate}>
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        {busy ? 'Generating' : `Create ${selected.length} showcase image${selected.length === 1 ? '' : 's'}`}
      </Button>

      {busy && (
        <div aria-busy="true">
          <div className="beam-border grid gap-3 rounded-xl border border-border bg-card p-3 sm:grid-cols-2">
            {selected.map((id) => (
              <div key={id} className="shimmer aspect-video rounded-lg bg-muted" />
            ))}
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground" role="status">
            Generating {selected.length} image{selected.length === 1 ? '' : 's'} at 2K, usually under a minute.
          </p>
        </div>
      )}

      {results.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {results.map((item) => (
            <figure key={item.id} className="space-y-2">
              <img
                src={item.url}
                alt={`Showcase on ${item.background_name}`}
                loading="lazy"
                className="aspect-video w-full rounded-xl border border-border object-cover"
              />
              <figcaption className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {item.background_name}
                  {item.width && item.height ? <span className="font-mono tabular">{` / ${item.width} x ${item.height}`}</span> : ''}
                </span>
                <Button size="sm" variant="ghost" disabled={downloading === item.id} onClick={() => download(item)}>
                  {downloading === item.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                  Download
                </Button>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  );
}
