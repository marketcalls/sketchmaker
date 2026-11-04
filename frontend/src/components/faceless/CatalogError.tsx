import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useFacelessStore } from '@/stores/facelessStore';

// Why the catalog is missing (templates, voices, models, moods, the consent
// statement), with a way to ask again. Nothing while it is fine or loading.
export function CatalogError({ className }: { className?: string }) {
  const catalogError = useFacelessStore((s) => s.catalogError);
  const loadCatalog = useFacelessStore((s) => s.loadCatalog);
  if (!catalogError) return null;
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive',
        className,
      )}
    >
      <span>{catalogError}</span>
      <Button type="button" variant="outline" size="sm" onClick={() => loadCatalog(true)}>
        Try again
      </Button>
    </div>
  );
}
