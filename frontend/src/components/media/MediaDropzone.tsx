import type { ReactNode } from 'react';
import { Upload, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMediaPicker, type MediaPickerOptions } from './useMediaPicker';

interface MediaDropzoneProps extends MediaPickerOptions {
  icon?: LucideIcon;
  // The prompt shown while nothing is chosen.
  label: string;
  hint?: string;
  // Rendered instead of the prompt once something is chosen (the preview).
  children?: ReactNode;
  className?: string;
}

// The one upload control: click to open the media window (upload or pick from
// My Assets), or drop files straight onto it.
export function MediaDropzone({ icon: Icon = Upload, label, hint, children, className, ...options }: MediaDropzoneProps) {
  const media = useMediaPicker(options);
  const { disabled } = options;

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={media.open}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          media.open();
        }
      }}
      {...media.dropProps}
      className={cn(
        'relative flex min-h-[180px] items-center justify-center rounded-xl border border-dashed bg-secondary/20 p-4 text-center transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
        media.dragOver ? 'border-primary bg-secondary/40' : 'border-border hover:border-foreground/30',
        className,
      )}
    >
      {children ?? (
        <div className="flex flex-col items-center">
          <Icon className="mb-3 h-6 w-6 text-muted-foreground" />
          <p className="font-medium">{label}</p>
          <p className="mt-1 text-sm text-muted-foreground">Drop here, or click to upload or choose from My Assets</p>
          {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
        </div>
      )}
      {media.dialog}
    </div>
  );
}
