import { AudioLines, Film, ImageIcon, PenTool } from 'lucide-react';
import type { Asset, AssetKind } from '@/api/assets';
import { cn } from '@/lib/utils';
import { formatStorageSize } from '@/utils/storage';

export const ASSET_KIND_LABELS: Record<AssetKind, string> = {
  image: 'Image',
  logo: 'Logo',
  video: 'Video',
  audio: 'Audio',
};

export const ASSET_KIND_ICONS = {
  image: ImageIcon,
  logo: PenTool,
  video: Film,
  audio: AudioLines,
} as const;

// What the file inputs accept, per kind (the server recognises the bytes).
export const ASSET_ACCEPT: Record<AssetKind, string> = {
  image: 'image/png,image/jpeg,image/webp',
  logo: 'image/svg+xml,image/png,image/jpeg,image/webp,.svg',
  video: 'video/mp4,video/quicktime,video/webm,video/x-m4v,.mp4,.mov,.webm,.m4v',
  audio: 'audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/aac,audio/ogg,.mp3,.wav,.m4a,.aac,.ogg',
};

export function acceptFor(kinds: AssetKind[]): string {
  return kinds.map((k) => ASSET_ACCEPT[k]).join(',');
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '';
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** 1920x1080, 0:42, 3.4 MB */
export function assetMeta(asset: Asset): string {
  const parts: string[] = [];
  if (asset.width && asset.height) parts.push(`${asset.width}x${asset.height}`);
  if (asset.durationSeconds) parts.push(formatDuration(asset.durationSeconds));
  parts.push(formatStorageSize(asset.fileSizeBytes));
  return parts.join(' / ');
}

// A square-ish preview: the image itself, the video's first frame, or an
// audio tile. Videos and audio do not autoplay.
export function AssetPreview({ asset, className }: { asset: Asset; className?: string }) {
  if (asset.kind === 'image' || asset.kind === 'logo') {
    return (
      <div className={cn('flex items-center justify-center overflow-hidden bg-muted', asset.kind === 'logo' && 'p-4', className)}>
        <img
          src={asset.url}
          alt={asset.name}
          loading="lazy"
          className={cn('h-full w-full', asset.kind === 'logo' ? 'object-contain' : 'object-cover')}
        />
      </div>
    );
  }
  if (asset.kind === 'video') {
    return (
      <div className={cn('relative overflow-hidden bg-muted', className)}>
        <video src={`${asset.url}#t=0.1`} preload="metadata" muted playsInline className="h-full w-full object-cover" />
        {asset.durationSeconds ? (
          <span className="absolute bottom-2 right-2 rounded-full bg-background/80 px-1.5 py-0.5 font-mono text-[10px] text-foreground">
            {formatDuration(asset.durationSeconds)}
          </span>
        ) : null}
      </div>
    );
  }
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 bg-secondary/40', className)}>
      <AudioLines className="h-5 w-5 text-muted-foreground" />
      <span className="font-mono text-[11px] text-muted-foreground">
        {asset.source === 'voice' ? `Voice${asset.voice ? `: ${asset.voice}` : ''}` : 'Audio'}
        {asset.durationSeconds ? ` / ${formatDuration(asset.durationSeconds)}` : ''}
      </span>
    </div>
  );
}
