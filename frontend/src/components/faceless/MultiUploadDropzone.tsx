import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import type { AssetKind } from '@/api/assets';

interface MultiUploadDropzoneProps {
  accept: string;
  icon: LucideIcon;
  title: string;
  hint: string;
  multiple?: boolean;
  disabled?: boolean;
  compact?: boolean;
  // Asset types My Assets offers in the media window (read from accept when
  // not given); a picked asset arrives in onFiles like a file from disk.
  assetKinds?: AssetKind[];
  // Most files in one go, when the caller has a limit.
  maxFiles?: number;
  onFiles: (files: File[]) => void;
}

function kindsIn(accept: string): AssetKind[] {
  const kinds = (['image', 'video', 'audio'] as const).filter((k) => accept.includes(`${k}/`));
  return kinds.length > 0 ? [...kinds] : ['image'];
}

// Drop or click to open the media window (upload, or pick from My Assets) for
// one or more files (keyboard: Enter or Space).
export function MultiUploadDropzone({
  accept,
  icon: Icon,
  title,
  hint,
  multiple = true,
  disabled,
  compact,
  assetKinds,
  maxFiles,
  onFiles,
}: MultiUploadDropzoneProps) {
  const media = useMediaPicker({
    kinds: assetKinds ?? kindsIn(accept),
    accept,
    multiple,
    maxFiles,
    title,
    description: hint,
    disabled,
    onFiles,
  });

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-label={`${title}. ${hint}`}
      onClick={media.open}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          media.open();
        }
      }}
      {...media.dropProps}
      className={cn(
        'flex items-center justify-center rounded-xl border border-dashed bg-secondary/20 p-4 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        compact ? 'min-h-[96px]' : 'min-h-[150px]',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
        media.dragOver ? 'border-foreground/40 bg-secondary/40' : 'border-border hover:border-foreground/30',
      )}
    >
      <div className="flex flex-col items-center">
        <Icon className="mb-2 h-5 w-5 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium leading-tight">{title}</p>
        <p className="mt-1 text-xs text-muted-foreground">Drop here, or click to upload or choose from My Assets</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>
      </div>
      {media.dialog}
    </div>
  );
}
