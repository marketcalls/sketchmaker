import { useEffect, useState } from 'react';
import { Star, X } from 'lucide-react';
import apiClient from '@/api/client';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { LogoSurface, type LogoAsset } from './LogoTile';

// Sizes a logo has to survive: favicon, tab, list avatar.
const SMALL_SIZES = [64, 32, 16];

/**
 * The logo without its solid background (model SVGs carry a white one), so
 * the dark and small-size checks show the mark itself. Falls back to the
 * stored file when there is no background to remove.
 */
function useTransparentUrl(logo: LogoAsset, enabled: boolean): string {
  const [url, setUrl] = useState(logo.url);
  useEffect(() => {
    if (!enabled) return;
    let href: string | null = null;
    let cancelled = false;
    apiClient
      .post<{ svg: string }>(`/logo/${logo.id}/edit`, { operation: 'transparent', save: false })
      .then(({ data }) => {
        if (cancelled) return;
        href = URL.createObjectURL(new Blob([data.svg], { type: 'image/svg+xml' }));
        setUrl(href);
      })
      .catch(() => !cancelled && setUrl(logo.url));
    return () => {
      cancelled = true;
      if (href) URL.revokeObjectURL(href);
    };
  }, [logo.id, logo.url, enabled]);
  return url;
}

function MarkChecks({ logo, index, open }: { logo: LogoAsset; index: number; open: boolean }) {
  const clear = useTransparentUrl(logo, open);
  return (
    <>
      <LogoSurface surface="dark" className="flex aspect-[2/1] items-center justify-center overflow-hidden rounded-lg p-4">
        <img src={clear} alt={`Concept ${index + 1} on dark`} className="h-full w-full object-contain" />
      </LogoSurface>
      <LogoSurface surface="paper" className="flex items-end justify-around gap-2 rounded-lg p-3">
        {SMALL_SIZES.map((size) => (
          <span key={size} className="flex flex-col items-center gap-1">
            <img src={clear} alt="" style={{ width: size, height: size }} className="object-contain" />
            <span className="font-mono text-[9px] text-background [.light_&]:text-muted-foreground">{size}px</span>
          </span>
        ))}
      </LogoSurface>
    </>
  );
}

interface LogoCompareProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  logos: LogoAsset[];
  isFavorite: (id: number) => boolean;
  onToggleFavorite: (id: number) => void;
  onRemove: (id: number) => void;
  onOpenStudio: (logo: LogoAsset) => void;
}

export function LogoCompare({ open, onOpenChange, logos, isFavorite, onToggleFavorite, onRemove, onOpenStudio }: LogoCompareProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Compare concepts</DialogTitle>
          <DialogDescription>
            Check each mark on light and dark backgrounds and at favicon sizes before you commit.
          </DialogDescription>
        </DialogHeader>
        <div className={cn('grid gap-4', logos.length > 1 && 'sm:grid-cols-2', logos.length > 2 && 'lg:grid-cols-4')}>
          {logos.map((logo, index) => (
            <div key={logo.id} className="flex flex-col gap-3 rounded-xl border border-border p-3">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Concept {index + 1}</span>
                <span className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => onToggleFavorite(logo.id)}
                    aria-pressed={isFavorite(logo.id)}
                    aria-label={isFavorite(logo.id) ? 'Remove from favorites' : 'Add to favorites'}
                    className={cn(
                      'flex h-8 w-8 items-center justify-center rounded-md border border-border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      isFavorite(logo.id) ? 'text-primary' : 'hover:text-foreground'
                    )}
                  >
                    <Star className={cn('h-3.5 w-3.5', isFavorite(logo.id) && 'fill-current')} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemove(logo.id)}
                    aria-label="Remove from comparison"
                    className="flex h-8 w-8 items-center justify-center rounded-md border border-border transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
              <LogoSurface surface="paper" className="flex aspect-square items-center justify-center rounded-lg p-4">
                <img src={logo.url} alt={`Concept ${index + 1} on light`} className="max-h-full max-w-full object-contain" />
              </LogoSurface>
              <MarkChecks logo={logo} index={index} open={open} />
              <p className="line-clamp-2 text-xs text-muted-foreground">{logo.prompt}</p>
              <Button size="sm" variant="outline" onClick={() => onOpenStudio(logo)}>
                Open studio
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
