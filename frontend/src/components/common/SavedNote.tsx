import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SavedNoteProps {
  show: boolean;
  /** Defaults to "Saved". */
  children?: React.ReactNode;
  className?: string;
}

/** Quiet inline confirmation placed next to a save button. */
export function SavedNote({ show, children = 'Saved', className }: SavedNoteProps) {
  return (
    <span
      aria-live="polite"
      className={cn(
        'inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-opacity duration-200',
        show ? 'opacity-100' : 'opacity-0',
        className
      )}
    >
      {show && (
        <>
          <Check className="h-4 w-4 text-success" />
          {children}
        </>
      )}
    </span>
  );
}
