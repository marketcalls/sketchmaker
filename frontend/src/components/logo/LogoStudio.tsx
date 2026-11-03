import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Download,
  FileCode,
  Frame,
  ImageDown,
  Layers,
  Loader2,
  Package,
  Palette,
  RefreshCw,
  Save,
  Shapes,
  Sparkles,
  Store,
  Type,
  Wand2,
} from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Progress } from '@/components/ui/progress';
import { usePricingStore, formatUsd } from '@/stores/pricingStore';
import { cn } from '@/lib/utils';
import apiClient from '@/api/client';
import { LogoSurface, type LogoAsset, type PreviewSurface } from './LogoTile';
import { downloadBlob, downloadSvgText, fetchSvgText, logoPngDataUrl, slugify, svgToPngBlob, PNG_EXPORT_SIZE } from './svgUtils';
import { MOCKUPS, buildBrandKit, canvasToBlob, renderMockup, type KitSources, type MockupKind } from './brandKit';
import { ShowcasePanel } from './ShowcasePanel';
import { getErrorMessage } from '@/utils/errors';

// ---------------------------------------------------------------------------
// API shapes (backend/app/routers/logo.py)
// ---------------------------------------------------------------------------

interface SvgResponse {
  svg: string;
  width: number | null;
  height: number | null;
  item: LogoAsset | null;
}

interface ColorsResponse {
  colors: { hex: string; share: number }[];
  background: string | null;
  total_colors: number;
}

export interface LogoFont {
  key: string;
  name: string;
  category: string;
  weights: number[];
  default_weight: number;
  preview: { d: string; view_box: [number, number, number, number] };
}

export interface FontPairing {
  label: string;
  heading: string;
  heading_weight: number;
  body: string;
}

interface FontsResponse {
  fonts: LogoFont[];
  pairings: Record<string, FontPairing>;
}

interface GenerateResponse {
  images: LogoAsset[];
  estimated_usd: number;
  delivered: number;
  requested: number;
}

let fontsCache: Promise<FontsResponse> | null = null;

export function loadLogoFonts(): Promise<FontsResponse> {
  if (!fontsCache) {
    fontsCache = apiClient.get<FontsResponse>('/logo/fonts').then((r) => r.data);
    fontsCache.catch(() => {
      fontsCache = null;
    });
  }
  return fontsCache;
}

export function errorDetail(err: unknown, fallback: string): string {
  return getErrorMessage(err, fallback);
}

// ---------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------

function useDebounced<T>(value: T, ms: number): T {
  const [out, setOut] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setOut(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return out;
}

function useSvgUrl(svg: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!svg) {
      setUrl(null);
      return;
    }
    const href = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    setUrl(href);
    return () => URL.revokeObjectURL(href);
  }, [svg]);
  return url;
}

function Pill({
  active,
  children,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { active: boolean }) {
  return (
    <button
      type="button"
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

function Label({ children, hint, htmlFor }: { children: React.ReactNode; hint?: string; htmlFor?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {children}
      </label>
      {hint && <span className="text-xs tabular text-muted-foreground">{hint}</span>}
    </div>
  );
}

function ColorField({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="inline-flex items-center gap-2 rounded-md border border-border py-1 pl-1 pr-3 text-xs">
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value.toLowerCase())}
        aria-label={label}
        className="h-7 w-7 cursor-pointer rounded-full border-0 bg-transparent p-0"
      />
      <span className="font-mono text-muted-foreground">{value}</span>
    </label>
  );
}

function Preview({
  url,
  surface,
  loading,
  alt,
  className,
}: {
  url: string | null;
  surface: PreviewSurface;
  loading: boolean;
  alt: string;
  className?: string;
}) {
  return (
    <LogoSurface
      surface={surface}
      className={cn('relative flex items-center justify-center overflow-hidden rounded-xl border border-border p-6', className)}
    >
      {url ? (
        <img src={url} alt={alt} className={cn('max-h-full max-w-full object-contain transition-opacity', loading && 'opacity-50')} />
      ) : (
        <div className="shimmer h-1/2 w-1/2 rounded-lg bg-muted" />
      )}
      {loading && <Loader2 className="absolute right-3 top-3 h-4 w-4 animate-spin text-muted-foreground" />}
    </LogoSurface>
  );
}

function SurfaceSwitch({ value, onChange }: { value: PreviewSurface; onChange: (v: PreviewSurface) => void }) {
  return (
    <div className="inline-flex rounded-md border border-border bg-muted/60 p-0.5" role="radiogroup" aria-label="Preview background">
      {(['paper', 'checker', 'dark'] as PreviewSurface[]).map((s) => (
        <button
          key={s}
          type="button"
          role="radio"
          aria-checked={value === s}
          onClick={() => onChange(s)}
          className={cn(
            'rounded px-2.5 py-1 text-xs capitalize transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            value === s ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

function FontButton({ font, active, onClick }: { font: LogoFont; active: boolean; onClick: () => void }) {
  const vb = font.preview.view_box;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex min-h-16 flex-col items-start justify-center gap-1 rounded-lg border p-3 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active ? 'border-primary/60 bg-primary/10 text-foreground' : 'border-border text-foreground hover:border-foreground/30'
      )}
    >
      <svg viewBox={vb.join(' ')} className="h-6 w-auto max-w-full" fill="currentColor" aria-hidden="true">
        <path d={font.preview.d} />
      </svg>
      <span className="text-[11px] text-muted-foreground">
        {font.name} / {font.category}
      </span>
    </button>
  );
}

async function downloadSvgAsPng(svg: string, filename: string) {
  downloadBlob(await svgToPngBlob(svg, PNG_EXPORT_SIZE), filename);
}

// ---------------------------------------------------------------------------
// Studio
// ---------------------------------------------------------------------------

export interface StudioBrief {
  brandName: string;
  tagline: string;
  fontStyle: string | null;
  // Used to suggest showcase backgrounds.
  industry?: string;
  personality?: Record<string, number>;
}

interface LogoStudioProps {
  logo: LogoAsset | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  brief: StudioBrief;
  onCreated: (logos: LogoAsset[]) => void;
}

type StudioTab = 'refine' | 'color' | 'wordmark' | 'kit' | 'mockups' | 'showcase';
type ColorMode = 'recolor' | 'mono' | 'invert' | 'transparent';

const QUALITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
] as const;
type Quality = (typeof QUALITIES)[number]['value'];

// Iterations send the logo as a reference image (see pricing.logo_text_key).
const iterateKey = (q: Quality) => (q === 'high' ? 'logo:text:high_ref' : `logo:text:${q}`);

export function LogoStudio({ logo, open, onOpenChange, brief, onCreated }: LogoStudioProps) {
  const { getModelCost } = usePricingStore();
  const [tab, setTab] = useState<StudioTab>('refine');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [colors, setColors] = useState<ColorsResponse | null>(null);
  const [fonts, setFonts] = useState<FontsResponse | null>(null);

  // Brand identity shared by the wordmark, kit and mockups.
  const [brandName, setBrandName] = useState(brief.brandName);
  const [tagline, setTagline] = useState(brief.tagline);

  // Refine
  const [instruction, setInstruction] = useState('');
  const [quality, setQuality] = useState<Quality>('medium');
  const [count, setCount] = useState(2);
  const [busyAi, setBusyAi] = useState<'refine' | 'variations' | 'simplify' | null>(null);
  const [created, setCreated] = useState<LogoAsset[]>([]);

  // Color
  const [mode, setMode] = useState<ColorMode>('recolor');
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [tolerance, setTolerance] = useState(20);
  const [monoColor, setMonoColor] = useState('#111111');
  const [dropBackground, setDropBackground] = useState(false);
  const [colorSurface, setColorSurface] = useState<PreviewSurface>('paper');
  const [colorSvg, setColorSvg] = useState<string | null>(null);
  const [colorLoading, setColorLoading] = useState(false);

  // Wordmark
  const [font, setFont] = useState('poppins');
  const [weight, setWeight] = useState<number | null>(null);
  const [layout, setLayout] = useState<'horizontal' | 'stacked' | 'text'>('horizontal');
  const [textColor, setTextColor] = useState('#111111');
  const [tracking, setTracking] = useState(0);
  const [uppercase, setUppercase] = useState(false);
  const [lockupSvg, setLockupSvg] = useState<string | null>(null);
  const [lockupLoading, setLockupLoading] = useState(false);
  const [lockupSurface, setLockupSurface] = useState<PreviewSurface>('paper');

  // Kit
  const [headingFont, setHeadingFont] = useState('playfair');
  const [bodyFont, setBodyFont] = useState('inter');
  const [includeWordmark, setIncludeWordmark] = useState(true);
  const [kitProgress, setKitProgress] = useState<{ fraction: number; label: string } | null>(null);

  // Mockups
  const [mockups, setMockups] = useState<{ kind: MockupKind; label: string; url: string; blob: Blob }[]>([]);
  const [mockupsLoading, setMockupsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const sourcesRef = useRef<{ key: string; value: KitSources } | null>(null);

  const logoId = logo?.id ?? null;

  // Reset per logo.
  useEffect(() => {
    if (!open || !logo) return;
    setError(null);
    setNotice(null);
    setCreated([]);
    setColors(null);
    setTargets({});
    setColorSvg(null);
    setLockupSvg(null);
    setMockups([]);
    sourcesRef.current = null;
    autoDrawn.current = null;
    setBrandName(brief.brandName);
    setTagline(brief.tagline);
    apiClient
      .get<ColorsResponse>(`/logo/${logo.id}/colors`)
      .then(({ data }) => {
        setColors(data);
        const dark = data.colors.find((c) => c.hex !== data.background && lum(c.hex) < 0.25);
        if (dark) setTextColor(dark.hex);
      })
      .catch((err) => setError(errorDetail(err, 'Could not read the logo colors')));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, logoId]);

  useEffect(() => {
    if (!open) return;
    loadLogoFonts()
      .then((data) => {
        setFonts(data);
        const pairing = brief.fontStyle ? data.pairings[brief.fontStyle] : undefined;
        if (pairing) {
          setFont(pairing.heading);
          setWeight(pairing.heading_weight);
          setHeadingFont(pairing.heading);
          setBodyFont(pairing.body);
        }
      })
      .catch((err) => setError(errorDetail(err, 'Could not load fonts')));
  }, [open, brief.fontStyle]);

  // ----------------------------------------------------------------- AI
  const perIterate = getModelCost(iterateKey(quality));
  const perSimplify = getModelCost('logo:vectorize');
  const iterateTotal = perIterate !== undefined ? perIterate * count : undefined;

  const runAi = async (kind: 'refine' | 'variations' | 'simplify') => {
    if (!logo) return;
    setBusyAi(kind);
    setError(null);
    setNotice(null);
    try {
      const png = await logoPngDataUrl(logo.url, logo.id, 1024);
      const { data } =
        kind === 'simplify'
          ? await apiClient.post<GenerateResponse>(`/logo/${logo.id}/simplify`, { image: png })
          : await apiClient.post<GenerateResponse>(`/logo/${logo.id}/iterate`, {
              reference_image: png,
              instruction: kind === 'refine' ? instruction.trim() : null,
              quality,
              num_images: count,
            });
      setCreated((prev) => [...data.images, ...prev]);
      onCreated(data.images);
      setNotice(`${data.delivered} new logo${data.delivered === 1 ? '' : 's'}, ${formatUsd(data.estimated_usd)} used.`);
    } catch (err) {
      setError(errorDetail(err, 'The request failed'));
    } finally {
      setBusyAi(null);
    }
  };

  // ----------------------------------------------------------------- Color
  const mapping = useMemo(
    () =>
      Object.entries(targets)
        .filter(([source, target]) => source !== target)
        .map(([source, target]) => ({ source, target })),
    [targets]
  );
  const colorRequest = useMemo(() => {
    if (mode === 'recolor') {
      if (mapping.length === 0) return null;
      return { operation: 'recolor', mapping, tolerance, remove_background: dropBackground };
    }
    if (mode === 'mono') return { operation: 'mono', color: monoColor };
    return { operation: mode };
  }, [mode, mapping, tolerance, dropBackground, monoColor]);
  const debouncedColor = useDebounced(colorRequest, 350);

  useEffect(() => {
    if (!open || !logo || tab !== 'color') return;
    if (!debouncedColor) {
      setColorSvg(null);
      return;
    }
    let cancelled = false;
    setColorLoading(true);
    apiClient
      .post<SvgResponse>(`/logo/${logo.id}/edit`, { ...debouncedColor, save: false })
      .then(({ data }) => {
        if (!cancelled) {
          setColorSvg(data.svg);
          setError(null);
        }
      })
      .catch((err) => !cancelled && setError(errorDetail(err, 'Could not preview this change')))
      .finally(() => !cancelled && setColorLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, logo, tab, debouncedColor]);
  const colorUrl = useSvgUrl(colorSvg);

  const saveColor = async () => {
    if (!logo || !colorRequest) return;
    setSaving(true);
    try {
      const { data } = await apiClient.post<SvgResponse>(`/logo/${logo.id}/edit`, { ...colorRequest, save: true });
      if (data.item) {
        onCreated([data.item]);
        setNotice('Saved as a new logo in your library. No provider cost.');
      }
    } catch (err) {
      setError(errorDetail(err, 'Could not save'));
    } finally {
      setSaving(false);
    }
  };

  // ----------------------------------------------------------------- Wordmark
  const fontInfo = fonts?.fonts.find((f) => f.key === font);
  const lockupRequest = useMemo(
    () =>
      brandName.trim()
        ? {
            brand_name: brandName.trim(),
            tagline: tagline.trim() || null,
            font,
            weight: weight ?? fontInfo?.default_weight ?? null,
            layout,
            text_color: textColor,
            tracking,
            uppercase,
          }
        : null,
    [brandName, tagline, font, weight, fontInfo, layout, textColor, tracking, uppercase]
  );
  const debouncedLockup = useDebounced(lockupRequest, 350);

  useEffect(() => {
    if (!open || !logo || tab !== 'wordmark') return;
    if (!debouncedLockup) {
      setLockupSvg(null);
      return;
    }
    let cancelled = false;
    setLockupLoading(true);
    apiClient
      .post<SvgResponse>(`/logo/${logo.id}/lockup`, { ...debouncedLockup, save: false })
      .then(({ data }) => {
        if (!cancelled) {
          setLockupSvg(data.svg);
          setError(null);
        }
      })
      .catch((err) => !cancelled && setError(errorDetail(err, 'Could not set the wordmark')))
      .finally(() => !cancelled && setLockupLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, logo, tab, debouncedLockup]);
  const lockupUrl = useSvgUrl(lockupSvg);

  const saveLockup = async () => {
    if (!logo || !lockupRequest) return;
    setSaving(true);
    try {
      const { data } = await apiClient.post<SvgResponse>(`/logo/${logo.id}/lockup`, { ...lockupRequest, save: true });
      if (data.item) {
        onCreated([data.item]);
        setNotice('Wordmark saved as a new logo. No provider cost.');
      }
    } catch (err) {
      setError(errorDetail(err, 'Could not save'));
    } finally {
      setSaving(false);
    }
  };

  // ----------------------------------------------------------------- Kit and mockups
  const slug = slugify(brandName || logo?.prompt, 'brand');
  const palette = useMemo(
    () => (colors?.colors ?? []).map((c) => c.hex).filter((hex) => hex !== colors?.background).slice(0, 6),
    [colors]
  );

  const kitSources = useCallback(
    async (withSheet: boolean): Promise<KitSources> => {
      if (!logo) throw new Error('No logo selected');
      const lockup = includeWordmark && brandName.trim() ? lockupSvg : null;
      const key = JSON.stringify([logo.id, brandName, tagline, headingFont, bodyFont, lockup?.length, withSheet]);
      if (sourcesRef.current?.key === key) return sourcesRef.current.value;
      const edit = (body: object) =>
        apiClient.post<SvgResponse>(`/logo/${logo.id}/edit`, { ...body, save: false }).then((r) => r.data.svg);
      const original = await fetchSvgText(logo.url, logo.id);
      const transparent = colors?.background ? await edit({ operation: 'transparent' }).catch(() => original) : original;
      const [monoBlack, monoWhite] = await Promise.all([
        edit({ operation: 'mono', color: '#111111' }),
        edit({ operation: 'mono', color: '#ffffff' }),
      ]);
      let brandSheet: string | null = null;
      if (withSheet && brandName.trim()) {
        const { data } = await apiClient.post<SvgResponse>(`/logo/${logo.id}/brand-sheet`, {
          brand_name: brandName.trim(),
          tagline: tagline.trim() || null,
          heading_font: headingFont,
          body_font: bodyFont,
          palette: palette.length ? palette : null,
        });
        brandSheet = data.svg;
      }
      const nameOf = (key: string) => fonts?.fonts.find((f) => f.key === key)?.name ?? key;
      const value: KitSources = {
        slug,
        brandName: brandName.trim(),
        tagline: tagline.trim(),
        original,
        transparent,
        monoBlack,
        monoWhite,
        lockup,
        brandSheet,
        paper: colors?.background ?? '#ffffff',
        palette,
        headingFont: nameOf(headingFont),
        bodyFont: nameOf(bodyFont),
      };
      sourcesRef.current = { key, value };
      return value;
    },
    [logo, includeWordmark, brandName, tagline, lockupSvg, headingFont, bodyFont, colors, palette, fonts, slug]
  );

  const downloadKit = async () => {
    setError(null);
    setKitProgress({ fraction: 0, label: 'Preparing files' });
    try {
      const sources = await kitSources(true);
      const blob = await buildBrandKit(sources, (fraction, label) => setKitProgress({ fraction, label }));
      downloadBlob(blob, `${slug}-brand-kit.zip`);
      setNotice('Brand kit downloaded. No provider cost.');
    } catch (err) {
      setError(errorDetail(err, 'Could not build the brand kit'));
    } finally {
      setKitProgress(null);
    }
  };

  const downloadSheet = async () => {
    setError(null);
    setKitProgress({ fraction: 0.5, label: 'Brand sheet' });
    try {
      const sources = await kitSources(true);
      if (sources.brandSheet) downloadBlob(await svgToPngBlob(sources.brandSheet, 2240), `${slug}-brand-sheet.png`);
    } catch (err) {
      setError(errorDetail(err, 'Could not build the brand sheet'));
    } finally {
      setKitProgress(null);
    }
  };

  const renderMockups = useCallback(async () => {
    setMockupsLoading(true);
    setError(null);
    try {
      const sources = await kitSources(false);
      const out: { kind: MockupKind; label: string; url: string; blob: Blob }[] = [];
      for (const m of MOCKUPS) {
        const blob = await canvasToBlob(await renderMockup(m.kind, sources));
        out.push({ ...m, blob, url: URL.createObjectURL(blob) });
      }
      setMockups((prev) => {
        prev.forEach((p) => URL.revokeObjectURL(p.url));
        return out;
      });
    } catch (err) {
      setError(errorDetail(err, 'Could not draw the mockups'));
    } finally {
      setMockupsLoading(false);
    }
  }, [kitSources]);

  // Draw the mockups once per logo when the tab is first opened (a failure
  // is shown and not retried in a loop; Redraw tries again).
  const autoDrawn = useRef<number | null>(null);
  useEffect(() => {
    if (open && tab === 'mockups' && logo && colors && autoDrawn.current !== logo.id) {
      autoDrawn.current = logo.id;
      renderMockups();
    }
  }, [open, tab, logo, colors, renderMockups]);

  useEffect(() => () => mockups.forEach((m) => URL.revokeObjectURL(m.url)), [mockups]);

  if (!logo) return null;
  const fileBase = `${slug}-${logo.id}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-6xl overflow-y-auto p-5 sm:p-6">
        <DialogHeader>
          <DialogTitle>Logo studio</DialogTitle>
          <DialogDescription className="line-clamp-2">{logo.prompt}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
          <div className="space-y-3">
            <LogoSurface surface="paper" className="flex aspect-square items-center justify-center rounded-xl border border-border p-6">
              <img src={logo.url} alt={`Logo: ${logo.prompt}`} className="max-h-full max-w-full object-contain" />
            </LogoSurface>
            <p className="font-mono text-xs text-muted-foreground">
              #{logo.id}
              {logo.width && logo.height ? ` / ${logo.width} x ${logo.height}` : ''}
              {logo.seed != null ? ` / seed ${logo.seed}` : ''}
            </p>
            {colors && colors.colors.length > 0 && (
              <div className="flex flex-wrap gap-1.5" aria-label="Logo colors">
                {colors.colors.map((c) => (
                  <span
                    key={c.hex}
                    title={`${c.hex} (${Math.round(c.share * 100)}%)`}
                    className="h-6 w-6 rounded-full border border-border"
                    style={{ backgroundColor: c.hex }}
                  />
                ))}
              </div>
            )}
            {error && (
              <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}
            {notice && !error && (
              <div role="status" className="rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success">
                {notice}
              </div>
            )}
          </div>

          <Tabs value={tab} onValueChange={(v) => setTab(v as StudioTab)}>
            <TabsList className="h-auto w-full flex-wrap justify-start">
              <TabsTrigger value="refine"><Sparkles className="h-3.5 w-3.5" />Refine</TabsTrigger>
              <TabsTrigger value="color"><Palette className="h-3.5 w-3.5" />Color</TabsTrigger>
              <TabsTrigger value="wordmark"><Type className="h-3.5 w-3.5" />Wordmark</TabsTrigger>
              <TabsTrigger value="kit"><Package className="h-3.5 w-3.5" />Brand kit</TabsTrigger>
              <TabsTrigger value="mockups"><Store className="h-3.5 w-3.5" />Mockups</TabsTrigger>
              <TabsTrigger value="showcase"><Frame className="h-3.5 w-3.5" />Showcase</TabsTrigger>
            </TabsList>

            {/* Refine */}
            <TabsContent value="refine" className="mt-5 space-y-5">
              <div>
                <Label htmlFor="studio-instruction" hint={`${instruction.length}/500`}>
                  What should change?
                </Label>
                <Textarea
                  id="studio-instruction"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  maxLength={500}
                  rows={3}
                  placeholder="Make the leaf rounder and drop the outline"
                />
                <p className="mt-1.5 text-xs text-muted-foreground">
                  This logo is sent as the reference, so the concept stays. Small color or text changes are free in the Color and
                  Wordmark tabs.
                </p>
              </div>
              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <Label>Quality</Label>
                  <div className="flex gap-2" role="radiogroup" aria-label="Quality">
                    {QUALITIES.map((q) => {
                      const price = getModelCost(iterateKey(q.value));
                      return (
                        <Pill
                          key={q.value}
                          role="radio"
                          aria-checked={quality === q.value}
                          active={quality === q.value}
                          onClick={() => setQuality(q.value)}
                          className="flex-1 flex-col gap-0 py-1.5"
                        >
                          <span>{q.label}</span>
                          <span className="font-mono tabular text-[11px] text-muted-foreground">{price !== undefined ? formatUsd(price) : ' '}</span>
                        </Pill>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <Label>New versions</Label>
                  <div className="flex gap-2" role="radiogroup" aria-label="New versions">
                    {[1, 2, 3, 4].map((n) => (
                      <Pill key={n} role="radio" aria-checked={count === n} active={count === n} onClick={() => setCount(n)} className="flex-1 font-mono">
                        {n}
                      </Pill>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex items-baseline justify-between text-xs text-muted-foreground">
                <span className="font-mono tabular">{perIterate !== undefined ? `${formatUsd(perIterate)} x ${count}` : 'Loading price'}</span>
                <span>
                  <span className="font-mono tabular text-base font-medium text-foreground">{iterateTotal !== undefined ? formatUsd(iterateTotal) : ' '}</span>
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  className="flex-1"
                  disabled={!instruction.trim() || busyAi !== null}
                  onClick={() => runAi('refine')}
                >
                  {busyAi === 'refine' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                  Apply change
                </Button>
                <Button
                  variant="outline"
                  className="flex-1"
                  disabled={busyAi !== null}
                  onClick={() => runAi('variations')}
                >
                  {busyAi === 'variations' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Layers className="h-4 w-4" />}
                  More like this
                </Button>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-secondary/20 p-3">
                <div>
                  <p className="text-sm font-medium">Simplify shapes</p>
                  <p className="text-xs text-muted-foreground">
                    Retrace with fewer, flatter shapes. <span className="font-mono tabular">{perSimplify !== undefined ? formatUsd(perSimplify) : ' '}</span>
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyAi !== null}
                  onClick={() => runAi('simplify')}
                >
                  {busyAi === 'simplify' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Shapes className="h-3.5 w-3.5" />}
                  Simplify
                </Button>
              </div>
              {busyAi && (
                <div aria-busy="true">
                  <div className="beam-border grid grid-cols-4 gap-2 rounded-xl border border-border bg-card p-3">
                    {Array.from({ length: busyAi === 'simplify' ? 1 : count }).map((_, i) => (
                      <div key={i} className="shimmer aspect-square rounded-lg bg-muted" />
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground" role="status">
                    {busyAi === 'simplify' ? 'Simplifying, usually a few seconds.' : 'Generating new versions, usually under a minute.'}
                  </p>
                </div>
              )}
              {created.length > 0 && (
                <div className="grid grid-cols-4 gap-2">
                  {created.map((c) => (
                    <LogoSurface key={c.id} surface="paper" className="flex aspect-square items-center justify-center rounded-lg border border-border p-2">
                      <img src={c.url} alt={`New version: ${c.prompt}`} className="max-h-full max-w-full object-contain" />
                    </LogoSurface>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Color */}
            <TabsContent value="color" className="mt-5 space-y-5">
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Version">
                {(
                  [
                    ['recolor', 'Recolor'],
                    ['mono', 'One color'],
                    ['invert', 'Inverted'],
                    ['transparent', 'No background'],
                  ] as [ColorMode, string][]
                ).map(([value, label]) => (
                  <Pill
                    key={value}
                    role="radio"
                    aria-checked={mode === value}
                    active={mode === value}
                    disabled={value === 'transparent' && !colors?.background}
                    onClick={() => {
                      setMode(value);
                      if (value === 'invert') setColorSurface('dark');
                    }}
                  >
                    {label}
                  </Pill>
                ))}
              </div>
              {mode === 'recolor' && (
                <div className="space-y-4">
                  <div className="space-y-2">
                    {(colors?.colors ?? []).map((c) => (
                      <div key={c.hex} className="flex flex-wrap items-center gap-3">
                        <span className="h-8 w-8 rounded-full border border-border" style={{ backgroundColor: c.hex }} />
                        <span className="w-20 font-mono text-xs uppercase text-muted-foreground">{c.hex}</span>
                        <span className="text-muted-foreground" aria-hidden="true">to</span>
                        <ColorField
                          value={targets[c.hex] ?? c.hex}
                          onChange={(v) => setTargets((prev) => ({ ...prev, [c.hex]: v }))}
                          label={`New color for ${c.hex}`}
                        />
                        <span className="font-mono text-[10px] text-muted-foreground">{Math.round(c.share * 100)}%</span>
                      </div>
                    ))}
                    {colors && colors.total_colors > colors.colors.length && (
                      <p className="text-xs text-muted-foreground">
                        {colors.total_colors} colors in total; similar shades follow the closest swatch within the tolerance.
                      </p>
                    )}
                  </div>
                  <div>
                    <Label hint={`${tolerance}`}>Tolerance for similar shades</Label>
                    <Slider value={[tolerance]} min={0} max={100} step={1} onValueChange={([v]) => setTolerance(v)} aria-label="Tolerance" />
                  </div>
                  {colors?.background && (
                    <label className="flex items-center justify-between gap-3 text-sm">
                      Remove the {colors.background} background
                      <Switch checked={dropBackground} onCheckedChange={setDropBackground} />
                    </label>
                  )}
                  {mapping.length > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => setTargets({})}>
                      <RefreshCw className="h-3.5 w-3.5" />
                      Reset colors
                    </Button>
                  )}
                </div>
              )}
              {mode === 'mono' && (
                <div className="flex flex-wrap items-center gap-2">
                  {['#111111', '#ffffff', ...palette.slice(0, 3)].map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => {
                        setMonoColor(c);
                        setColorSurface(lum(c) > 0.6 ? 'dark' : 'paper');
                      }}
                      aria-label={`One color ${c}`}
                      aria-pressed={monoColor === c}
                      className={cn(
                        'h-9 w-9 rounded-full border-2 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        monoColor === c ? 'border-primary ring-2 ring-primary/40 ring-offset-1 ring-offset-background' : 'border-border'
                      )}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                  <ColorField value={monoColor} onChange={setMonoColor} label="Custom color" />
                </div>
              )}
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground">Preview, free</span>
                <SurfaceSwitch value={colorSurface} onChange={setColorSurface} />
              </div>
              <Preview
                url={colorUrl ?? (mode === 'recolor' && mapping.length === 0 ? logo.url : null)}
                surface={colorSurface}
                loading={colorLoading}
                alt="Color preview"
                className="aspect-[4/3]"
              />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={!colorSvg} onClick={() => colorSvg && downloadSvgText(colorSvg, `${fileBase}-${mode}.svg`)}>
                  <FileCode className="h-3.5 w-3.5" />
                  SVG
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!colorSvg}
                  onClick={() => colorSvg && downloadSvgAsPng(colorSvg, `${fileBase}-${mode}.png`).catch((e) => setError(errorDetail(e, 'PNG export failed')))}
                >
                  <ImageDown className="h-3.5 w-3.5" />
                  PNG
                </Button>
                <Button size="sm" variant="default" disabled={!colorRequest || saving} onClick={saveColor}>
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  Save as new logo
                </Button>
              </div>
            </TabsContent>

            {/* Wordmark */}
            <TabsContent value="wordmark" className="mt-5 space-y-5">
              <p className="text-sm text-muted-foreground">
                Sets your name in a real typeface as vector outlines, so the spelling is always exact. Free.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="studio-brand" hint={`${brandName.length}/60`}>Brand name</Label>
                  <Input id="studio-brand" value={brandName} maxLength={60} onChange={(e) => setBrandName(e.target.value)} placeholder="Northwind" />
                </div>
                <div>
                  <Label htmlFor="studio-tagline" hint="Optional">Tagline</Label>
                  <Input id="studio-tagline" value={tagline} maxLength={80} onChange={(e) => setTagline(e.target.value)} placeholder="Outdoor gear since 1998" />
                </div>
              </div>
              <div>
                <Label>Typeface</Label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {(fonts?.fonts ?? []).map((f) => (
                    <FontButton
                      key={f.key}
                      font={f}
                      active={font === f.key}
                      onClick={() => {
                        setFont(f.key);
                        setWeight(f.default_weight);
                      }}
                    />
                  ))}
                  {!fonts && Array.from({ length: 6 }).map((_, i) => <div key={i} className="shimmer h-16 rounded-xl bg-muted" />)}
                </div>
              </div>
              {fontInfo && fontInfo.weights.length > 1 && (
                <div>
                  <Label>Weight</Label>
                  <div className="flex flex-wrap gap-2">
                    {fontInfo.weights.map((w) => (
                      <Pill key={w} active={(weight ?? fontInfo.default_weight) === w} onClick={() => setWeight(w)} className="font-mono text-xs">
                        {w}
                      </Pill>
                    ))}
                  </div>
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label>Layout</Label>
                  <div className="flex flex-wrap gap-2">
                    {(
                      [
                        ['horizontal', 'Side by side'],
                        ['stacked', 'Stacked'],
                        ['text', 'Name only'],
                      ] as const
                    ).map(([value, label]) => (
                      <Pill key={value} active={layout === value} onClick={() => setLayout(value)}>
                        {label}
                      </Pill>
                    ))}
                  </div>
                </div>
                <div>
                  <Label>Text color</Label>
                  <div className="flex flex-wrap items-center gap-2">
                    <ColorField value={textColor} onChange={setTextColor} label="Text color" />
                    {palette.slice(0, 4).map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setTextColor(c)}
                        aria-label={`Text color ${c}`}
                        className={cn('h-8 w-8 rounded-full border-2', textColor === c ? 'border-primary' : 'border-border')}
                        style={{ backgroundColor: c }}
                      />
                    ))}
                  </div>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label hint={`${tracking}`}>Letter spacing</Label>
                  <Slider value={[tracking]} min={-50} max={300} step={10} onValueChange={([v]) => setTracking(v)} aria-label="Letter spacing" />
                </div>
                <label className="flex items-center justify-between gap-3 self-end text-sm">
                  All capitals
                  <Switch checked={uppercase} onCheckedChange={setUppercase} />
                </label>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground">Preview, free</span>
                <SurfaceSwitch value={lockupSurface} onChange={setLockupSurface} />
              </div>
              <Preview url={lockupUrl} surface={lockupSurface} loading={lockupLoading} alt="Wordmark preview" className="aspect-[2/1]" />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={!lockupSvg} onClick={() => lockupSvg && downloadSvgText(lockupSvg, `${fileBase}-wordmark.svg`)}>
                  <FileCode className="h-3.5 w-3.5" />
                  SVG
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!lockupSvg}
                  onClick={() => lockupSvg && downloadSvgAsPng(lockupSvg, `${fileBase}-wordmark.png`).catch((e) => setError(errorDetail(e, 'PNG export failed')))}
                >
                  <ImageDown className="h-3.5 w-3.5" />
                  PNG
                </Button>
                <Button size="sm" variant="default" disabled={!lockupRequest || saving} onClick={saveLockup}>
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  Save as new logo
                </Button>
              </div>
            </TabsContent>

            {/* Brand kit */}
            <TabsContent value="kit" className="mt-5 space-y-5">
              <p className="text-sm text-muted-foreground">
                Everything below is made on your device from the vector file. No provider cost.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="kit-brand">Brand name</Label>
                  <Input id="kit-brand" value={brandName} maxLength={60} onChange={(e) => setBrandName(e.target.value)} placeholder="Needed for the brand sheet" />
                </div>
                <div>
                  <Label htmlFor="kit-tagline" hint="Optional">Tagline</Label>
                  <Input id="kit-tagline" value={tagline} maxLength={80} onChange={(e) => setTagline(e.target.value)} />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {(
                  [
                    ['Heading font', headingFont, setHeadingFont],
                    ['Body font', bodyFont, setBodyFont],
                  ] as const
                ).map(([label, value, setter]) => (
                  <div key={label}>
                    <Label>{label}</Label>
                    <div className="flex flex-wrap gap-1.5">
                      {(fonts?.fonts ?? []).map((f) => (
                        <Pill key={f.key} active={value === f.key} onClick={() => setter(f.key)} className="min-h-9 px-3 text-xs">
                          {f.name}
                        </Pill>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <label className="flex items-center justify-between gap-3 text-sm">
                <span>
                  Include the wordmark
                  <span className="block text-xs text-muted-foreground">
                    {lockupSvg ? 'Uses the current Wordmark tab settings.' : 'Set one up in the Wordmark tab first.'}
                  </span>
                </span>
                <Switch checked={includeWordmark && !!lockupSvg} disabled={!lockupSvg} onCheckedChange={setIncludeWordmark} />
              </label>
              <ul className="grid gap-1.5 rounded-xl border border-border bg-secondary/20 p-4 font-mono text-xs text-muted-foreground sm:grid-cols-2">
                <li>SVG: original, transparent, black, white</li>
                <li>PNG: 256 to 2048 px, transparent</li>
                <li>Favicon: .ico, 16 / 32 px, SVG, Apple, Android</li>
                <li>Social: profile, OG, X, LinkedIn, YouTube</li>
                <li>Brand sheet: SVG and PNG with palette</li>
                <li>Mockups: card, app icon, storefront, tee</li>
              </ul>
              {kitProgress && (
                <div className="space-y-1.5" aria-live="polite">
                  <Progress value={Math.round(kitProgress.fraction * 100)} />
                  <p className="text-xs text-muted-foreground">{kitProgress.label}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button className="flex-1" disabled={!!kitProgress || !colors || !brandName.trim()} onClick={downloadKit}>
                  {kitProgress ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  Download brand kit (.zip)
                </Button>
                <Button variant="outline" disabled={!!kitProgress || !colors || !brandName.trim()} onClick={downloadSheet}>
                  <ImageDown className="h-4 w-4" />
                  Brand sheet PNG
                </Button>
              </div>
              {!brandName.trim() && <p className="text-xs text-muted-foreground">Enter the brand name to build the kit.</p>}
            </TabsContent>

            {/* Mockups */}
            <TabsContent value="mockups" className="mt-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">Drawn on your device from built-in scenes. Free.</p>
                <Button size="sm" variant="outline" disabled={mockupsLoading} onClick={() => { sourcesRef.current = null; renderMockups(); }}>
                  {mockupsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                  Redraw
                </Button>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {mockups.length > 0
                  ? mockups.map((m) => (
                      <figure key={m.kind} className="space-y-2">
                        <img src={m.url} alt={`${m.label} mockup`} className="w-full rounded-xl border border-border" />
                        <figcaption className="flex items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground">{m.label}</span>
                          <Button size="sm" variant="ghost" onClick={() => downloadBlob(m.blob, `${slug}-${m.kind}.png`)}>
                            <Download className="h-3.5 w-3.5" />
                            PNG
                          </Button>
                        </figcaption>
                      </figure>
                    ))
                  : MOCKUPS.map((m) => <div key={m.kind} className="shimmer aspect-[4/3] rounded-xl bg-muted" />)}
              </div>
            </TabsContent>

            {/* Showcase (AI, priced). Kept mounted so results and a running
                request survive switching tabs. */}
            <TabsContent value="showcase" forceMount className="mt-5 data-[state=inactive]:hidden">
              <ShowcasePanel
                logo={logo}
                brandName={brandName}
                onBrandNameChange={setBrandName}
                tagline={tagline}
                industry={brief.industry ?? ''}
                personality={brief.personality}
                onError={setError}
                onNotice={setNotice}
                errorDetail={errorDetail}
              />
            </TabsContent>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function lum(hex: string): number {
  const v = hex.replace('#', '');
  if (v.length !== 6) return 0;
  const ch = (i: number) => {
    const c = parseInt(v.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(0) + 0.7152 * ch(2) + 0.0722 * ch(4);
}
