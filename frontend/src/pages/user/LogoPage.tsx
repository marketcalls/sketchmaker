import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronDown, Columns2, ImagePlus, Loader2, PenTool, Plus, Shapes, Type, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Stagger, StaggerItem } from '@/components/motion';
import {
  LogoCompare,
  LogoStudio,
  LogoSurface,
  LogoTile,
  PREVIEW_SURFACES,
  slugify,
  useLogoFavorites,
  type LogoAsset,
  type PreviewSurface,
} from '@/components/logo';
import { usePricingStore, formatUsd } from '@/stores/pricingStore';
import { cn } from '@/lib/utils';
import apiClient from '@/api/client';
import { MediaDropzone } from '@/components/media/MediaDropzone';
import { useMediaPicker, type MediaPickerOptions } from '@/components/media/useMediaPicker';
import type { Asset } from '@/api/assets';
import { getErrorMessage } from '@/utils/errors';
import { useElapsedSeconds, formatElapsed, isSubmitShortcut } from '@/components/generate';

// Must match backend/app/services/logo_service.py and routers/logo.py.
const STYLE_PRESETS = [
  { value: 'minimal', label: 'Minimal' },
  { value: 'wordmark', label: 'Wordmark' },
  { value: 'lettermark', label: 'Lettermark' },
  { value: 'emblem', label: 'Emblem' },
  { value: 'mascot', label: 'Mascot' },
  { value: 'abstract', label: 'Abstract' },
  { value: 'geometric', label: 'Geometric' },
  { value: 'vintage', label: 'Vintage' },
  { value: 'hand-drawn', label: 'Hand-drawn' },
] as const;

const ASPECT_RATIOS = ['1:1', '4:3', '3:4', '3:2', '16:9', '2:1', '3:1', '4:1'] as const;
const QUALITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
] as const;
const COUNTS = [1, 2, 4, 6, 8] as const;

// Brief options; keys must match logo_service.PERSONALITY_AXES and
// FONT_STYLE_DESCRIPTORS.
const PERSONALITY = [
  { axis: 'tone', low: 'Classic', high: 'Modern' },
  { axis: 'mood', low: 'Playful', high: 'Serious' },
  { axis: 'energy', low: 'Calm', high: 'Energetic' },
  { axis: 'market', low: 'Accessible', high: 'Luxurious' },
  { axis: 'form', low: 'Minimal', high: 'Ornate' },
] as const;
type Axis = (typeof PERSONALITY)[number]['axis'];

const FONT_STYLES = [
  { value: 'sans', label: 'Clean sans' },
  { value: 'geometric', label: 'Geometric' },
  { value: 'serif', label: 'Elegant serif' },
  { value: 'display', label: 'Expressive' },
  { value: 'condensed', label: 'Condensed' },
  { value: 'rounded', label: 'Friendly' },
  { value: 'script', label: 'Script' },
  { value: 'tech', label: 'Technical' },
] as const;
type FontStyle = (typeof FONT_STYLES)[number]['value'];

// Palette presets: brand colors the user picks, sent to the model as hex.
const PALETTE_PRESETS: { name: string; colors: string[] }[] = [
  { name: 'Forest', colors: ['#1f4d3a', '#c9a227', '#f2ede3'] },
  { name: 'Ocean', colors: ['#0b3c5d', '#328cc1', '#d9e9f2'] },
  { name: 'Sunset', colors: ['#e4572e', '#f3a712', '#29335c'] },
  { name: 'Berry', colors: ['#6a1b4d', '#d64f7b', '#f7d6e0'] },
  { name: 'Earth', colors: ['#7a4e2d', '#d9a066', '#2f2a26'] },
  { name: 'Mono', colors: ['#111111', '#6b6b6b', '#f5f5f5'] },
  { name: 'Electric', colors: ['#3a0ca3', '#4cc9f0', '#f72585'] },
  { name: 'Mint', colors: ['#2a9d8f', '#e9c46a', '#264653'] },
];
const MAX_PALETTE = 5;
const INDUSTRIES = [
  'Coffee and cafe', 'Restaurant', 'Technology and software', 'Finance', 'Health and wellness', 'Fitness',
  'Beauty and cosmetics', 'Fashion', 'Real estate', 'Education', 'Consulting', 'Construction', 'Travel',
  'Outdoor and sports', 'Pets', 'Music and entertainment', 'Nonprofit', 'Gaming',
];
const VECTORIZE_MODES = [
  { value: 'default', label: 'Detailed', hint: 'Keeps finer details and small features of the original.' },
  { value: 'simple', label: 'Simple', hint: 'Uses fewer, simpler shapes for a cleaner, flatter result.' },
] as const;

const MAX_REFERENCES = 5;
const REFERENCE_MAX_MB = 10;
const VECTORIZE_MAX_MB = 20;
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

// SVG logos in My Assets cannot be sent as raster references or vectorized.
const rasterOnly = (asset: Asset) => (ACCEPTED_TYPES.includes(asset.contentType ?? '') ? null : 'Needs a PNG, JPEG or WebP image');
const HISTORY_PAGE = 12;

type StyleValue = (typeof STYLE_PRESETS)[number]['value'];

// Styles where Explore directions applies (logo_service.DIRECTION_STYLES).
const DIRECTION_STYLES: (StyleValue | null)[] = [null, 'minimal', 'abstract', 'geometric'];
type AspectRatio = (typeof ASPECT_RATIOS)[number];
type Quality = (typeof QUALITIES)[number]['value'];
type VectorizeMode = (typeof VECTORIZE_MODES)[number]['value'];
type Tab = 'text' | 'vectorize';

interface UploadedImage {
  url: string;
  name: string;
}

interface LogoResponse {
  images: LogoAsset[];
  prompt: string;
  seed: number | null;
  requested: number;
  delivered: number;
  estimated_usd: number;
}

interface HistoryResponse {
  items: LogoAsset[];
  total: number;
  limit: number;
  offset: number;
}

function errorDetail(err: unknown, fallback: string): string {
  return getErrorMessage(err, fallback);
}

function readImage(file: File, maxMb: number): Promise<UploadedImage> {
  return new Promise((resolve, reject) => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      reject(new Error(`${file.name}: use a PNG, JPEG or WebP image`));
      return;
    }
    if (file.size > maxMb * 1024 * 1024) {
      reject(new Error(`${file.name}: images must be ${maxMb} MB or smaller`));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve({ url: reader.result as string, name: file.name });
    reader.onerror = () => reject(new Error(`${file.name}: could not be read`));
    reader.readAsDataURL(file);
  });
}

function AspectGlyph({ ratio }: { ratio: string }) {
  const [w, h] = ratio.split(':').map(Number);
  const scale = 14 / Math.max(w, h);
  return (
    <span
      aria-hidden="true"
      className="inline-block rounded-[2px] border border-current"
      style={{ width: Math.max(4, w * scale), height: Math.max(4, h * scale) }}
    />
  );
}

function Chip({
  active,
  onClick,
  children,
  disabled,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40',
        active
          ? 'border-primary/60 bg-primary/10 text-foreground'
          : 'border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground',
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

function FieldLabel({ htmlFor, id, children, hint }: { htmlFor?: string; id?: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      {htmlFor ? (
        <label htmlFor={htmlFor} id={id} className="text-sm font-medium">
          {children}
        </label>
      ) : (
        <span id={id} className="text-sm font-medium">
          {children}
        </span>
      )}
      {hint && <span className="text-xs tabular text-muted-foreground">{hint}</span>}
    </div>
  );
}

export function LogoPage() {
  const { getModelCost } = usePricingStore();

  const [tab, setTab] = useState<Tab>('text');

  // Create from text
  const [brandName, setBrandName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [style, setStyle] = useState<StyleValue | null>(null);
  const [colors, setColors] = useState('');
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('1:1');
  const [quality, setQuality] = useState<Quality>('medium');
  const [numImages, setNumImages] = useState<number>(4);
  const [references, setReferences] = useState<UploadedImage[]>([]);
  const [tagline, setTagline] = useState('');
  const [includeTagline, setIncludeTagline] = useState(false);
  const [industry, setIndustry] = useState('');
  const [symbolIdeas, setSymbolIdeas] = useState('');
  const [symbolOnly, setSymbolOnly] = useState(false);
  const [personality, setPersonality] = useState<Record<Axis, number>>({ tone: 0, mood: 0, energy: 0, market: 0, form: 0 });
  const [palette, setPalette] = useState<string[]>([]);
  const [fontStyle, setFontStyle] = useState<FontStyle | null>(null);
  const [avoid, setAvoid] = useState('');
  const [showMore, setShowMore] = useState(false);
  const [directions, setDirections] = useState(false);
  const directionsAllowed = DIRECTION_STYLES.includes(style);

  // Studio, comparison and favorites
  const [studioLogo, setStudioLogo] = useState<LogoAsset | null>(null);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [historyFilter, setHistoryFilter] = useState<'all' | 'favorites'>('all');
  const { isFavorite, toggleFavorite } = useLogoFavorites();

  // Vectorize
  const [source, setSource] = useState<UploadedImage | null>(null);
  const [mode, setMode] = useState<VectorizeMode>('default');

  // Results
  const [isGenerating, setIsGenerating] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [results, setResults] = useState<LogoAsset[]>([]);
  const [lastRun, setLastRun] = useState<LogoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [surface, setSurface] = useState<PreviewSurface>('paper');

  // History
  const [history, setHistory] = useState<LogoAsset[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // A prompt from the URL prefills Create from text, the same way
  // /generate?prompt= works.
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const promptParam = searchParams.get('prompt');
    if (promptParam) {
      setTab('text');
      setPrompt(promptParam.slice(0, 2000));
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const loadHistory = useCallback(async (offset = 0) => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const { data } = await apiClient.get<HistoryResponse>('/logo/history', {
        params: { limit: HISTORY_PAGE, offset },
      });
      setHistory((prev) => (offset === 0 ? data.items : [...prev, ...data.items]));
      setHistoryTotal(data.total);
    } catch (err) {
      setHistoryError(errorDetail(err, 'Could not load your logos'));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory(0);
  }, [loadHistory]);

  // Estimates, from the backend's price table.
  const priceKey =
    tab === 'vectorize'
      ? 'logo:vectorize'
      : quality === 'high' && references.length > 0
        ? 'logo:text:high_ref'
        : `logo:text:${quality}`;
  const perLogo = getModelCost(priceKey);
  const count = tab === 'vectorize' ? 1 : numImages;
  const total = perLogo !== undefined ? perLogo * count : undefined;

  const qualityPrice = useCallback(
    (q: Quality) => getModelCost(q === 'high' && references.length > 0 ? 'logo:text:high_ref' : `logo:text:${q}`),
    [getModelCost, references.length]
  );

  const inputReady = tab === 'text' ? prompt.trim().length > 0 : source !== null;
  const canGenerate = inputReady && !isGenerating;

  const addReferences = async (files: FileList | File[]) => {
    const room = MAX_REFERENCES - references.length;
    const list = Array.from(files);
    if (room <= 0) {
      setError(`You can add up to ${MAX_REFERENCES} reference images.`);
      return;
    }
    const accepted: UploadedImage[] = [];
    for (const file of list.slice(0, room)) {
      try {
        accepted.push(await readImage(file, REFERENCE_MAX_MB));
      } catch (err) {
        setError(getErrorMessage(err, 'Could not add that image'));
      }
    }
    if (list.length > room) setError(`Only ${MAX_REFERENCES} reference images are used; extra files were skipped.`);
    if (accepted.length) setReferences((prev) => [...prev, ...accepted].slice(0, MAX_REFERENCES));
  };

  const setSourceFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      setSource(await readImage(file, VECTORIZE_MAX_MB));
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not use that image'));
    }
  };

  const referencePicker = useMediaPicker({
    kinds: ['image', 'logo'],
    accept: ACCEPTED_TYPES.join(','),
    multiple: true,
    maxFiles: MAX_REFERENCES,
    title: 'Add reference images',
    unusableReason: rasterOnly,
    onFiles: addReferences,
  });
  const sourceOptions: MediaPickerOptions = {
    kinds: ['image', 'logo'],
    accept: ACCEPTED_TYPES.join(','),
    title: 'Add an image to vectorize',
    unusableReason: rasterOnly,
    onFiles: (files) => setSourceFile(files[0]),
  };
  // The Replace button under the preview opens the same window.
  const sourcePicker = useMediaPicker(sourceOptions);

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setIsGenerating(true);
    setPendingCount(count);
    setError(null);
    try {
      const response =
        tab === 'text'
          ? await apiClient.post<LogoResponse>('/logo/generate', {
              prompt: prompt.trim(),
              brand_name: brandName.trim() || null,
              style,
              colors: colors.trim() || null,
              aspect_ratio: aspectRatio,
              quality,
              num_images: numImages,
              reference_image_urls: references.length ? references.map((r) => r.url) : null,
              tagline: tagline.trim() || null,
              include_tagline: includeTagline && !!tagline.trim(),
              industry: industry.trim() || null,
              personality: Object.fromEntries(Object.entries(personality).filter(([, v]) => v !== 0)),
              symbol_ideas: symbolIdeas.trim() || null,
              palette: palette.length ? palette : null,
              font_style: symbolOnly ? null : fontStyle,
              avoid: avoid.trim() || null,
              symbol_only: symbolOnly,
              directions: directionsAllowed && directions,
            })
          : await apiClient.post<LogoResponse>('/logo/vectorize', { image: source?.url, mode });
      setResults(response.data.images);
      setLastRun(response.data);
      loadHistory(0);
    } catch (err) {
      setError(errorDetail(err, 'Logo generation failed'));
    } finally {
      setIsGenerating(false);
    }
  };

  const fileBase = (logo: LogoAsset) =>
    `${slugify(tab === 'text' && brandName ? brandName : logo.prompt, 'logo')}-${logo.id}`;
  const historyFileBase = (logo: LogoAsset) => `${slugify(logo.prompt, 'logo')}-${logo.id}`;

  const actionLabel = tab === 'text' ? `Generate ${numImages} concept${numImages > 1 ? 's' : ''}` : 'Vectorize image';
  const elapsed = useElapsedSeconds(isGenerating);

  const knownLogos = useMemo(() => {
    const map = new Map<number, LogoAsset>();
    for (const logo of [...history, ...results]) map.set(logo.id, logo);
    return map;
  }, [history, results]);
  const compareLogos = compareIds.map((id) => knownLogos.get(id)).filter((l): l is LogoAsset => !!l);
  const toggleCompare = (id: number) =>
    setCompareIds((prev) => (prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id].slice(-4)));

  const onStudioCreated = (logos: LogoAsset[]) => {
    setResults((prev) => [...logos, ...prev.filter((p) => !logos.some((l) => l.id === p.id))]);
    loadHistory(0);
  };
  const visibleHistory = historyFilter === 'favorites' ? history.filter((l) => isFavorite(l.id)) : history;
  const tileActions = (logo: LogoAsset) => ({
    isFavorite: isFavorite(logo.id),
    onToggleFavorite: () => toggleFavorite(logo.id),
    selected: compareIds.includes(logo.id),
    onToggleSelect: () => toggleCompare(logo.id),
    onOpenStudio: () => setStudioLogo(logo),
  });

  return (
    <Stagger className="space-y-6" interval={0.08}>
      <StaggerItem>
        <header className="mb-2">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Logo Generator</h1>
          <p className="mt-1 max-w-prose text-pretty text-sm text-muted-foreground">
            Describe the brand to get up to 8 vector concepts, then refine one, add an exact wordmark and export a brand kit.
          </p>
        </header>
      </StaggerItem>

      <StaggerItem>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          {/* Form */}
          <Card className="h-fit">
            <CardContent className="space-y-6 pt-6">
              <Tabs value={tab} onValueChange={(v) => { setTab(v as Tab); setError(null); }}>
                <TabsList className="w-full">
                  <TabsTrigger value="text" className="flex-1">
                    <Type className="h-4 w-4" />
                    Create from text
                  </TabsTrigger>
                  <TabsTrigger value="vectorize" className="flex-1">
                    <Shapes className="h-4 w-4" />
                    Vectorize an image
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="text" className="mt-6 space-y-6">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <FieldLabel htmlFor="logo-brand" hint={`${brandName.length}/60`}>
                        Brand name
                      </FieldLabel>
                      <Input
                        id="logo-brand"
                        value={brandName}
                        onChange={(e) => setBrandName(e.target.value)}
                        maxLength={60}
                        placeholder="Northwind"
                        autoComplete="off"
                      />
                    </div>
                    <div>
                      <FieldLabel htmlFor="logo-tagline" hint="Optional">
                        Tagline
                      </FieldLabel>
                      <Input
                        id="logo-tagline"
                        value={tagline}
                        onChange={(e) => setTagline(e.target.value)}
                        maxLength={80}
                        placeholder="Outdoor gear since 1998"
                        autoComplete="off"
                      />
                    </div>
                  </div>

                  <div>
                    <FieldLabel id="logo-textmode-label">Text in the logo</FieldLabel>
                    <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-labelledby="logo-textmode-label">
                      {(
                        [
                          [false, 'Name in the artwork', 'The model letters the name. Check the spelling.'],
                          [true, 'Symbol only', 'An icon with no letters. Add the name in the studio with exact fonts.'],
                        ] as const
                      ).map(([value, label, hint]) => (
                        <button
                          key={label}
                          type="button"
                          role="radio"
                          aria-checked={symbolOnly === value}
                          onClick={() => setSymbolOnly(value)}
                          className={cn(
                            'rounded-lg border p-3 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            symbolOnly === value ? 'border-primary/60 bg-primary/10' : 'border-border hover:border-foreground/30'
                          )}
                        >
                          <span className="block text-sm font-medium">{label}</span>
                          <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>
                        </button>
                      ))}
                    </div>
                    {!symbolOnly && tagline.trim() && brandName.trim() && (
                      <label className="mt-3 flex items-center justify-between gap-3 text-sm">
                        <span>
                          Letter the tagline too
                          <span className="block text-xs text-muted-foreground">Otherwise it only guides the concept.</span>
                        </span>
                        <Switch checked={includeTagline} onCheckedChange={setIncludeTagline} />
                      </label>
                    )}
                  </div>

                  <div>
                    <FieldLabel htmlFor="logo-industry" hint="Optional">
                      Industry
                    </FieldLabel>
                    <Input
                      id="logo-industry"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      maxLength={80}
                      list="logo-industries"
                      placeholder="Specialty coffee"
                      autoComplete="off"
                    />
                    <datalist id="logo-industries">
                      {INDUSTRIES.map((i) => (
                        <option key={i} value={i} />
                      ))}
                    </datalist>
                  </div>

                  <div>
                    <FieldLabel htmlFor="logo-prompt" hint={`${prompt.length}/2000`}>
                      Describe the logo
                    </FieldLabel>
                    <Textarea
                      id="logo-prompt"
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      onKeyDown={(e) => {
                        if (isSubmitShortcut(e) && canGenerate) {
                          e.preventDefault();
                          void handleGenerate();
                        }
                      }}
                      maxLength={2000}
                      rows={4}
                      required
                      placeholder="A compass needle merging with a leaf, for an outdoor gear brand"
                      aria-describedby="logo-prompt-help"
                    />
                    <p id="logo-prompt-help" className="mt-1.5 text-xs text-muted-foreground">Ctrl+Enter generates.</p>
                  </div>

                  <div>
                    <FieldLabel htmlFor="logo-symbols" hint="Optional">
                      Symbol ideas
                    </FieldLabel>
                    <Input
                      id="logo-symbols"
                      value={symbolIdeas}
                      onChange={(e) => setSymbolIdeas(e.target.value)}
                      maxLength={300}
                      placeholder="Mountain, compass, pine needle"
                      autoComplete="off"
                    />
                  </div>

                  <div>
                    <FieldLabel id="logo-style-label" hint="Optional">
                      Style
                    </FieldLabel>
                    <div className="flex flex-wrap gap-2" role="group" aria-labelledby="logo-style-label">
                      {STYLE_PRESETS.map((preset) => (
                        <Chip
                          key={preset.value}
                          active={style === preset.value}
                          aria-pressed={style === preset.value}
                          onClick={() => setStyle(style === preset.value ? null : preset.value)}
                        >
                          {preset.label}
                        </Chip>
                      ))}
                    </div>
                    {directionsAllowed && (
                      <label className="mt-3 flex items-center justify-between gap-3 text-sm">
                        <span>
                          Explore directions
                          <span className="block text-xs text-muted-foreground">
                            Each concept follows a different pattern family (geometry, dots, lines, networks) with strict
                            minimalism. Same price per concept.
                          </span>
                        </span>
                        <Switch checked={directions} onCheckedChange={setDirections} />
                      </label>
                    )}
                  </div>

                  {!symbolOnly && (
                    <div>
                      <FieldLabel id="logo-lettering-label" hint="Optional">
                        Lettering
                      </FieldLabel>
                      <div className="flex flex-wrap gap-2" role="group" aria-labelledby="logo-lettering-label">
                        {FONT_STYLES.map((f) => (
                          <Chip
                            key={f.value}
                            active={fontStyle === f.value}
                            aria-pressed={fontStyle === f.value}
                            onClick={() => setFontStyle(fontStyle === f.value ? null : f.value)}
                          >
                            {f.label}
                          </Chip>
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <FieldLabel id="logo-personality-label" hint="Optional">
                      Personality
                    </FieldLabel>
                    <div className="space-y-4 rounded-xl border border-border bg-secondary/20 p-4" role="group" aria-labelledby="logo-personality-label">
                      {PERSONALITY.map((p) => (
                        <div key={p.axis} className="grid grid-cols-[5.5rem_minmax(0,1fr)_5.5rem] items-center gap-3">
                          <span className={cn('text-xs', personality[p.axis] < 0 ? 'text-foreground' : 'text-muted-foreground')}>{p.low}</span>
                          <Slider
                            value={[personality[p.axis]]}
                            min={-2}
                            max={2}
                            step={1}
                            onValueChange={([v]) => setPersonality((prev) => ({ ...prev, [p.axis]: v }))}
                            aria-label={`${p.low} to ${p.high}`}
                          />
                          <span className={cn('text-right text-xs', personality[p.axis] > 0 ? 'text-foreground' : 'text-muted-foreground')}>
                            {p.high}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <FieldLabel id="logo-palette-label" hint={`${palette.length}/${MAX_PALETTE}`}>
                      Colors
                    </FieldLabel>
                    <div className="flex flex-wrap gap-2" role="group" aria-label="Palette presets">
                      {PALETTE_PRESETS.map((preset) => {
                        const active = preset.colors.join() === palette.join();
                        return (
                          <button
                            key={preset.name}
                            type="button"
                            onClick={() => setPalette(active ? [] : preset.colors)}
                            aria-pressed={active}
                            className={cn(
                              'inline-flex min-h-9 items-center gap-2 rounded-md border py-1 pl-1.5 pr-3 text-xs transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                              active ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground'
                            )}
                          >
                            <span className="flex -space-x-1.5">
                              {preset.colors.map((c) => (
                                <span key={c} className="h-5 w-5 rounded-full border border-border" style={{ backgroundColor: c }} />
                              ))}
                            </span>
                            {preset.name}
                          </button>
                        );
                      })}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-labelledby="logo-palette-label">
                      {palette.map((c, index) => (
                        <span key={index} className="inline-flex items-center gap-1.5 rounded-md border border-border py-1 pl-1 pr-1.5">
                          <input
                            type="color"
                            value={c}
                            onChange={(e) => setPalette((prev) => prev.map((v, i) => (i === index ? e.target.value.toLowerCase() : v)))}
                            aria-label={`Brand color ${index + 1}`}
                            className="h-7 w-7 cursor-pointer rounded-full border-0 bg-transparent p-0"
                          />
                          <span className="font-mono text-[11px] text-muted-foreground">{c}</span>
                          <button
                            type="button"
                            onClick={() => setPalette((prev) => prev.filter((_, i) => i !== index))}
                            aria-label={`Remove color ${c}`}
                            className="flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                      {palette.length < MAX_PALETTE && (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setPalette((prev) => [...prev, prev.length ? '#888888' : '#1f4d3a'])}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          Add color
                        </Button>
                      )}
                    </div>
                    <Input
                      id="logo-colors"
                      className="mt-3"
                      value={colors}
                      onChange={(e) => setColors(e.target.value)}
                      maxLength={120}
                      placeholder={palette.length ? 'Color notes, for example: gold only as an accent' : 'Or describe them: deep navy and warm gold'}
                      autoComplete="off"
                      aria-label="Color notes"
                    />
                  </div>

                  <div>
                    <FieldLabel id="logo-aspect-label">Aspect ratio</FieldLabel>
                    <div className="flex flex-wrap gap-2" role="radiogroup" aria-labelledby="logo-aspect-label">
                      {ASPECT_RATIOS.map((ratio) => (
                        <Chip
                          key={ratio}
                          role="radio"
                          aria-checked={aspectRatio === ratio}
                          active={aspectRatio === ratio}
                          onClick={() => setAspectRatio(ratio)}
                          className="font-mono text-xs"
                        >
                          <AspectGlyph ratio={ratio} />
                          {ratio}
                        </Chip>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-6">
                    <div>
                      <FieldLabel id="logo-quality-label">Quality</FieldLabel>
                      <div className="flex flex-wrap gap-2" role="radiogroup" aria-labelledby="logo-quality-label">
                        {QUALITIES.map((q) => {
                          const price = qualityPrice(q.value);
                          return (
                            <Chip
                              key={q.value}
                              role="radio"
                              aria-checked={quality === q.value}
                              active={quality === q.value}
                              onClick={() => setQuality(q.value)}
                              className="flex-1 flex-col gap-0 py-1.5"
                            >
                              <span>{q.label}</span>
                              <span className="font-mono tabular text-[11px] text-muted-foreground">
                                {price !== undefined ? formatUsd(price) : ' '}
                              </span>
                            </Chip>
                          );
                        })}
                      </div>
                    </div>
                    <div>
                      <FieldLabel id="logo-count-label">Concepts</FieldLabel>
                      <div className="flex flex-wrap gap-2" role="radiogroup" aria-labelledby="logo-count-label">
                        {COUNTS.map((n) => (
                          <Chip
                            key={n}
                            role="radio"
                            aria-checked={numImages === n}
                            active={numImages === n}
                            onClick={() => setNumImages(n)}
                            className="flex-1 font-mono"
                          >
                            {n}
                          </Chip>
                        ))}
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setShowMore((v) => !v)}
                    aria-expanded={showMore}
                    className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-sm text-muted-foreground transition-colors duration-150 hover:border-foreground/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    More options: things to avoid, reference images
                    <ChevronDown className={cn('h-4 w-4 transition-transform duration-200', showMore && 'rotate-180')} />
                  </button>

                  {(showMore || references.length > 0) && (
                  <div className="space-y-6">
                  <div>
                    <FieldLabel htmlFor="logo-avoid" hint="Optional">
                      Avoid
                    </FieldLabel>
                    <Input
                      id="logo-avoid"
                      value={avoid}
                      onChange={(e) => setAvoid(e.target.value)}
                      maxLength={300}
                      placeholder="Gradients, clip art, cartoon mascots"
                      autoComplete="off"
                    />
                  </div>
                  <div>
                    <FieldLabel id="logo-refs-label" hint={`${references.length}/${MAX_REFERENCES}`}>
                      Reference images
                    </FieldLabel>
                    <p className="mb-3 text-xs text-muted-foreground">
                      Optional. Guide the look with up to {MAX_REFERENCES} images (PNG, JPEG or WebP, {REFERENCE_MAX_MB} MB
                      each). The first one leads.
                      {quality === 'high' && references.length > 0 && ' High quality with references is priced higher.'}
                    </p>
                    <div className="grid grid-cols-3 gap-2 sm:grid-cols-6" aria-labelledby="logo-refs-label" role="group">
                      {references.map((ref, index) => (
                        <div key={`${ref.name}-${index}`} className="relative">
                          <div className="aspect-square overflow-hidden rounded-lg border border-border bg-secondary/40">
                            <img src={ref.url} alt={`Reference ${index + 1}: ${ref.name}`} className="h-full w-full object-cover" />
                          </div>
                          {index === 0 && (
                            <span className="glass absolute bottom-1 left-1 rounded-md px-1.5 text-[10px] font-medium text-foreground">
                              Lead
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => setReferences((prev) => prev.filter((_, i) => i !== index))}
                            className="absolute -right-1.5 -top-1.5 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            aria-label={`Remove reference ${index + 1}`}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                      {references.length < MAX_REFERENCES && (
                        <button
                          type="button"
                          onClick={referencePicker.open}
                          {...referencePicker.dropProps}
                          className={cn(
                            'flex aspect-square flex-col items-center justify-center gap-1 rounded-lg border border-dashed bg-secondary/20 text-muted-foreground transition-colors duration-150 hover:border-foreground/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            referencePicker.dragOver ? 'border-primary' : 'border-border'
                          )}
                          aria-label="Add reference images"
                        >
                          <ImagePlus className="h-5 w-5" />
                          <span className="text-[11px]">Add</span>
                        </button>
                      )}
                    </div>
                    {referencePicker.dialog}
                  </div>
                  </div>
                  )}
                </TabsContent>

                <TabsContent value="vectorize" className="mt-6 space-y-6">
                  <div>
                    <FieldLabel id="logo-source-label" hint={`Max ${VECTORIZE_MAX_MB} MB`}>
                      Image to vectorize
                    </FieldLabel>
                    {source ? (
                      <div className="space-y-3">
                        <LogoSurface surface="checker" className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded-xl border border-border p-4">
                          <img src={source.url} alt={`Source image: ${source.name}`} className="max-h-full max-w-full object-contain" />
                        </LogoSurface>
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate font-mono text-xs text-muted-foreground">{source.name}</p>
                          <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={sourcePicker.open}>
                              Replace
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setSource(null)} aria-label="Remove image">
                              <X className="h-3.5 w-3.5" />
                              Remove
                            </Button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <MediaDropzone
                        {...sourceOptions}
                        icon={Upload}
                        label="Image to vectorize"
                        hint="PNG, JPEG or WebP"
                        className="min-h-[240px]"
                      />
                    )}
                    {sourcePicker.dialog}
                  </div>

                  <div>
                    <FieldLabel id="logo-mode-label">Mode</FieldLabel>
                    <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-labelledby="logo-mode-label">
                      {VECTORIZE_MODES.map((m) => (
                        <button
                          key={m.value}
                          type="button"
                          role="radio"
                          aria-checked={mode === m.value}
                          onClick={() => setMode(m.value)}
                          className={cn(
                            'rounded-lg border p-3 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            mode === m.value
                              ? 'border-primary/60 bg-primary/10'
                              : 'border-border hover:border-foreground/30'
                          )}
                        >
                          <span className="block text-sm font-medium">{m.label}</span>
                          <span className="mt-1 block text-xs text-muted-foreground">{m.hint}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </TabsContent>
              </Tabs>

              {/* Cost and action */}
              <div className="space-y-3 border-t border-border pt-5">
                {error && (
                  <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                    {error}
                  </div>
                )}
                <div className="flex items-baseline justify-between text-xs text-muted-foreground" aria-live="polite">
                  <span className="font-mono tabular">
                    {perLogo !== undefined ? `${formatUsd(perLogo)} x ${count}` : 'Loading price'}
                  </span>
                  <span>
                    <span className="font-mono tabular text-base font-medium text-foreground">{total !== undefined ? formatUsd(total) : ' '}</span>
                  </span>
                </div>
                <Button
                  className="w-full"
                  size="lg"
                  onClick={handleGenerate}
                  disabled={!canGenerate}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {tab === 'text' ? 'Generating' : 'Vectorizing'}
                    </>
                  ) : (
                    actionLabel
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Results */}
          <Card className="h-fit">
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
              <div>
                <CardTitle className="flex items-baseline gap-2">
                  <span className="text-lg font-semibold tracking-tight">Results</span>
                  {results.length > 0 && !isGenerating && (
                    <span className="text-sm font-normal tabular text-muted-foreground">
                      {results.length} logo{results.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </CardTitle>
                <CardDescription className="text-xs">
                  {lastRun && !isGenerating
                    ? `${formatUsd(lastRun.estimated_usd)} used${lastRun.delivered < lastRun.requested ? `, ${lastRun.requested - lastRun.delivered} not delivered` : ''}`
                    : 'SVG files, saved to your gallery'}
                </CardDescription>
              </div>
              {compareIds.length >= 2 && (
                <Button size="sm" variant="outline" onClick={() => setCompareOpen(true)}>
                  <Columns2 className="h-3.5 w-3.5" />
                  Compare {compareLogos.length}
                </Button>
              )}
              <div
                className="inline-flex rounded-md border border-border bg-muted/60 p-0.5"
                role="radiogroup"
                aria-label="Preview background"
              >
                {PREVIEW_SURFACES.map((s) => (
                  <button
                    key={s.value}
                    type="button"
                    role="radio"
                    aria-checked={surface === s.value}
                    onClick={() => setSurface(s.value)}
                    className={cn(
                      'rounded px-2.5 py-1 text-xs transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      surface === s.value ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent>
              {isGenerating ? (
                <div aria-busy="true" aria-live="polite">
                  <div
                    className={cn(
                      'beam-border grid gap-4 rounded-xl border border-border bg-card p-4',
                      pendingCount > 1 && 'grid-cols-2',
                      pendingCount > 4 && 'xl:grid-cols-3'
                    )}
                  >
                    {Array.from({ length: pendingCount }).map((_, i) => (
                      <div key={i} className="shimmer aspect-square rounded-lg bg-muted" />
                    ))}
                  </div>
                  <p className="mt-3 text-center text-sm text-muted-foreground" role="status">
                    {tab === 'text'
                      ? `Generating ${pendingCount} concept${pendingCount > 1 ? 's' : ''}, usually under a minute.`
                      : 'Tracing shapes, usually a few seconds.'}{' '}
                    <span className="font-mono tabular text-foreground">{formatElapsed(elapsed)}</span>
                  </p>
                </div>
              ) : results.length > 0 ? (
                <div className="space-y-4">
                  <div className={cn('grid gap-5', results.length > 1 && 'grid-cols-2', results.length > 4 && 'xl:grid-cols-3')}>
                    {results.map((logo) => (
                      <LogoTile
                        key={logo.id}
                        logo={logo}
                        fileBase={fileBase(logo)}
                        surface={surface}
                        onError={setError}
                        {...tileActions(logo)}
                      />
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Open a concept in the studio to refine it, recolor it, add an exact wordmark or export a brand kit.
                  </p>
                </div>
              ) : (
                <div className="flex min-h-[320px] items-center justify-center rounded-xl border border-border bg-secondary/20 p-6">
                  <div className="max-w-sm text-center">
                    <PenTool className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
                    <p className="font-semibold tracking-tight">No logos yet</p>
                    <p className="mt-1 text-pretty text-sm text-muted-foreground">
                      Every concept is a scalable SVG. Open one in the studio for edits, wordmarks, mockups and the brand kit.
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </StaggerItem>

      {/* History */}
      <StaggerItem>
        <section aria-labelledby="logo-history-heading" className="space-y-4">
          <div className="flex items-baseline justify-between gap-3">
            <div>
              <h2 id="logo-history-heading" className="text-lg font-semibold tracking-tight">
                Recent logos
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-md border border-border bg-muted/60 p-0.5" role="radiogroup" aria-label="Show">
                {(
                  [
                    ['all', 'All'],
                    ['favorites', 'Favorites'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={historyFilter === value}
                    onClick={() => setHistoryFilter(value)}
                    className={cn(
                      'rounded px-2.5 py-1 text-xs transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      historyFilter === value ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {historyTotal > 0 && (
                <span className="text-xs tabular text-muted-foreground">
                  {history.length} of {historyTotal}
                </span>
              )}
            </div>
          </div>

          {historyError && (
            <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {historyError}
            </div>
          )}

          {history.length > 0 ? (
            <>
              {visibleHistory.length === 0 && (
                <p className="rounded-xl border border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
                  No favorites among the logos loaded so far. Use the star on a logo to keep it here.
                </p>
              )}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                {visibleHistory.map((logo) => (
                  <LogoTile
                    key={logo.id}
                    logo={logo}
                    fileBase={historyFileBase(logo)}
                    surface={surface}
                    compact
                    onError={setHistoryError}
                    {...tileActions(logo)}
                  />
                ))}
              </div>
              {history.length < historyTotal && (
                <div className="flex justify-center">
                  <Button variant="outline" onClick={() => loadHistory(history.length)} disabled={historyLoading}>
                    {historyLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                    Load more
                  </Button>
                </div>
              )}
            </>
          ) : historyLoading ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="shimmer aspect-square rounded-xl bg-muted" />
              ))}
            </div>
          ) : (
            !historyError && (
              <p className="rounded-xl border border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
                No logos yet. Everything you create here is also saved to your gallery.
              </p>
            )
          )}
        </section>
      </StaggerItem>

      <LogoStudio
        logo={studioLogo}
        open={studioLogo !== null}
        onOpenChange={(open) => !open && setStudioLogo(null)}
        brief={{ brandName: brandName.trim(), tagline: tagline.trim(), fontStyle, industry: industry.trim(), personality }}
        onCreated={onStudioCreated}
      />
      <LogoCompare
        open={compareOpen && compareLogos.length > 0}
        onOpenChange={setCompareOpen}
        logos={compareLogos}
        isFavorite={isFavorite}
        onToggleFavorite={toggleFavorite}
        onRemove={toggleCompare}
        onOpenStudio={(logo) => {
          setCompareOpen(false);
          setStudioLogo(logo);
        }}
      />
    </Stagger>
  );
}
