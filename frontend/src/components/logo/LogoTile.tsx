import { useState } from 'react';
import { motion } from 'motion/react';
import { Check, Columns2, Copy, FileCode, ImageDown, Loader2, Star, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { downloadBlob, downloadSvgText, fetchSvgText, svgToPngBlob, PNG_EXPORT_SIZE } from './svgUtils';
import { getErrorMessage } from '@/utils/errors';

export interface LogoAsset {
  id: number;
  url: string;
  prompt: string;
  width?: number | null;
  height?: number | null;
  art_style?: string | null;
  created_at?: string | null;
  seed?: number | null;
  aspect_ratio?: string | null;
  rendering?: string | null;
  // Explore directions only: the pattern family and a one-line rationale.
  direction?: string | null;
  rationale?: string | null;
}

export type PreviewSurface = 'paper' | 'checker' | 'dark';

export const PREVIEW_SURFACES: { value: PreviewSurface; label: string }[] = [
  { value: 'paper', label: 'Paper' },
  { value: 'checker', label: 'Checker' },
  { value: 'dark', label: 'Dark' },
];

// Logos are usually drawn for light backgrounds, so the default tile stays
// light in both themes: the foreground token is the light ink of the dark
// theme, the card token the light surface of the light theme.
const SURFACE_CLASS: Record<PreviewSurface, string> = {
  paper: 'bg-foreground [.light_&]:bg-card',
  checker: 'bg-foreground [.light_&]:bg-card',
  dark: 'bg-background [.light_&]:bg-foreground',
};

const CHECKER_STYLE: React.CSSProperties = {
  backgroundImage:
    'repeating-conic-gradient(color-mix(in oklab, var(--color-muted-foreground) 22%, transparent) 0% 25%, transparent 0% 50%)',
  backgroundSize: '18px 18px',
  backgroundPosition: '50% 50%',
};

export function LogoSurface({
  surface,
  className,
  children,
}: {
  surface: PreviewSurface;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn(SURFACE_CLASS[surface], className)} style={surface === 'checker' ? CHECKER_STYLE : undefined}>
      {children}
    </div>
  );
}

interface LogoTileProps {
  logo: LogoAsset;
  fileBase: string;
  surface: PreviewSurface;
  compact?: boolean;
  onError?: (message: string) => void;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
  selected?: boolean;
  onToggleSelect?: () => void;
  onOpenStudio?: () => void;
}

type Busy = 'svg' | 'png' | 'copy' | null;

const KIND_LABEL: Record<string, string> = {
  logo_vectorize: 'Vectorized',
  logo_edit: 'Edited',
  logo_lockup: 'Wordmark',
};

export function LogoTile({
  logo,
  fileBase,
  surface,
  compact = false,
  onError,
  isFavorite,
  onToggleFavorite,
  selected,
  onToggleSelect,
  onOpenStudio,
}: LogoTileProps) {
  const [busy, setBusy] = useState<Busy>(null);
  const [copied, setCopied] = useState(false);

  const run = async (kind: Exclude<Busy, null>, action: () => Promise<void>) => {
    setBusy(kind);
    try {
      await action();
    } catch (err) {
      onError?.(getErrorMessage(err, 'Something went wrong with this logo'));
    } finally {
      setBusy(null);
    }
  };

  const handleSvg = () =>
    run('svg', async () => {
      const text = await fetchSvgText(logo.url, logo.id);
      downloadSvgText(text, `${fileBase}.svg`);
    });

  const handlePng = () =>
    run('png', async () => {
      const text = await fetchSvgText(logo.url, logo.id);
      const blob = await svgToPngBlob(text, PNG_EXPORT_SIZE);
      downloadBlob(blob, `${fileBase}-${PNG_EXPORT_SIZE}.png`);
    });

  const handleCopy = () =>
    run('copy', async () => {
      const text = await fetchSvgText(logo.url, logo.id);
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    });

  const alt = logo.prompt ? `Logo: ${logo.prompt}` : 'Generated logo';

  return (
    <motion.figure
      className="group flex flex-col gap-2"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div className="relative">
        <LogoSurface
          surface={surface}
          className={cn(
            'flex aspect-square items-center justify-center overflow-hidden rounded-xl border transition-colors duration-150',
            selected ? 'border-primary ring-2 ring-primary/40' : 'border-border group-hover:border-foreground/20',
            compact ? 'p-3' : 'p-5 sm:p-6'
          )}
        >
          {onOpenStudio ? (
            <button
              type="button"
              onClick={onOpenStudio}
              className="flex h-full w-full items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Open ${alt} in the studio`}
            >
              <img src={logo.url} alt="" loading="lazy" className="max-h-full max-w-full object-contain" />
            </button>
          ) : (
            <img src={logo.url} alt={alt} loading="lazy" className="max-h-full max-w-full object-contain" />
          )}
        </LogoSurface>
        {(onToggleFavorite || onToggleSelect) && (
          <div className="absolute right-2 top-2 flex gap-1.5">
            {onToggleSelect && (
              <button
                type="button"
                onClick={onToggleSelect}
                aria-pressed={!!selected}
                aria-label={selected ? 'Remove from comparison' : 'Add to comparison'}
                title={selected ? 'Remove from comparison' : 'Compare'}
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-md border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  selected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-background/90 text-muted-foreground hover:text-foreground'
                )}
              >
                <Columns2 className="h-3.5 w-3.5" />
              </button>
            )}
            {onToggleFavorite && (
              <button
                type="button"
                onClick={onToggleFavorite}
                aria-pressed={!!isFavorite}
                aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
                title={isFavorite ? 'Favorite' : 'Add to favorites'}
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-md border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  isFavorite
                    ? 'border-primary/50 bg-background/90 text-primary'
                    : 'border-border bg-background/90 text-muted-foreground hover:text-foreground'
                )}
              >
                <Star className={cn('h-3.5 w-3.5', isFavorite && 'fill-current')} />
              </button>
            )}
          </div>
        )}
      </div>

      <figcaption className="flex items-center justify-between gap-2 px-1 text-[11px] text-muted-foreground">
        <span>{KIND_LABEL[logo.art_style ?? ''] ?? 'SVG'}</span>
        {logo.width && logo.height ? (
          <span className="font-mono tabular">
            {logo.width} x {logo.height}
          </span>
        ) : null}
      </figcaption>
      {logo.direction && !compact && (
        <div className="space-y-1 px-1">
          <p className="text-xs font-medium text-foreground">{logo.direction}</p>
          {logo.rationale && <p className="text-xs leading-relaxed text-muted-foreground">{logo.rationale}</p>}
        </div>
      )}

      <div className={cn('flex flex-wrap gap-1.5', compact && 'gap-1')}>
        {onOpenStudio && !compact && (
          <Button size="sm" variant="secondary" className="w-full" onClick={onOpenStudio}>
            <Wand2 className="h-3.5 w-3.5" />
            Open studio
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          className="flex-1"
          onClick={handleSvg}
          disabled={busy !== null}
          aria-label={`Download SVG of ${alt}`}
        >
          {busy === 'svg' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileCode className="h-3.5 w-3.5" />}
          SVG
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="flex-1"
          onClick={handlePng}
          disabled={busy !== null}
          aria-label={`Download ${PNG_EXPORT_SIZE} pixel PNG of ${alt}`}
        >
          {busy === 'png' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageDown className="h-3.5 w-3.5" />}
          PNG
        </Button>
        {!compact && (
          <Button
            size="sm"
            variant="ghost"
            onClick={handleCopy}
            disabled={busy !== null}
            aria-label="Copy SVG code"
            title="Copy SVG code"
          >
            {busy === 'copy' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : copied ? (
              <Check className="h-3.5 w-3.5 text-success" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
            <span className="sr-only sm:not-sr-only">{copied ? 'Copied' : 'Code'}</span>
          </Button>
        )}
      </div>
    </motion.figure>
  );
}
