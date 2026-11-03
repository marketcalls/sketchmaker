import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Loader2, Search, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { assetsApi, type Asset, type AssetKind } from '@/api/assets';
import { AssetPreview, assetMeta } from '@/components/assets/AssetPreview';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';

const PAGE_SIZE = 24;

type Tab = 'upload' | 'library';

interface MediaPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kinds: AssetKind[];
  accept: string;
  title: string;
  description?: string;
  multiple: boolean;
  maxFiles: number;
  unusableReason?: (asset: Asset) => string | null;
  // Both may be async; the dialog shows a spinner, closes when they settle and
  // shows the error (staying open) when they throw.
  onUpload: (files: File[]) => Promise<void>;
  onPick: (assets: Asset[]) => Promise<void>;
}

// "Upload files" or "My Assets", like the WordPress media window. One window
// for every upload in the app.
export function MediaPickerDialog({
  open,
  onOpenChange,
  kinds,
  accept,
  title,
  description,
  multiple,
  maxFiles,
  unusableReason,
  onUpload,
  onPick,
}: MediaPickerDialogProps) {
  const [tab, setTab] = useState<Tab>('library');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Asset[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestSeq = useRef(0);
  const firstLoad = useRef(true);
  const kindsKey = kinds.join(',');

  const load = useCallback(
    async (nextPage: number, q: string) => {
      const seq = ++requestSeq.current;
      setLoading(true);
      setError(null);
      try {
        const result = await assetsApi.list({ kinds: kindsKey.split(',') as AssetKind[], q, page: nextPage, pageSize: PAGE_SIZE });
        if (seq !== requestSeq.current) return; // a newer search replaced this request
        setAssets((prev) => {
          if (nextPage === 1) return result.assets;
          // Items added or removed since the last page shift the offsets.
          const seen = new Set(prev.map((a) => a.id));
          return [...prev, ...result.assets.filter((a) => !seen.has(a.id))];
        });
        setPage(result.page);
        setTotalPages(result.totalPages);
        // Nothing saved yet: start on the upload tab instead of an empty library.
        if (firstLoad.current && !q && result.total === 0) setTab('upload');
        firstLoad.current = false;
      } catch (err) {
        setError(getErrorMessage(err, 'Could not load your assets'));
      } finally {
        if (seq === requestSeq.current) setLoading(false);
      }
    },
    [kindsKey],
  );

  // Fresh state each time the window opens.
  useEffect(() => {
    if (!open) return;
    firstLoad.current = true;
    setTab('library');
    setSelected([]);
    setError(null);
    setQuery('');
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => load(1, query.trim()), query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [open, query, load]);

  const run = async (work: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await work();
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not use that file'));
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = (list: FileList | File[] | null | undefined) => {
    const files = Array.from(list ?? []);
    if (files.length === 0) return;
    if (files.length > maxFiles) {
      setError(maxFiles === 1 ? 'Choose one file.' : `Choose up to ${maxFiles} files.`);
      return;
    }
    run(() => onUpload(files));
  };

  const toggle = (asset: Asset) => {
    if (unusableReason?.(asset) || busy) return;
    if (!multiple) {
      run(() => onPick([asset]));
      return;
    }
    setError(null);
    setSelected((prev) => {
      if (prev.some((a) => a.id === asset.id)) return prev.filter((a) => a.id !== asset.id);
      if (prev.length >= maxFiles) {
        setError(`Choose up to ${maxFiles} files.`);
        return prev;
      }
      return [...prev, asset];
    });
  };

  const what = kinds.includes('video') ? 'videos' : kinds.includes('audio') && kinds.length === 1 ? 'audio files' : 'images';

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-hidden p-0">
        <div className="flex max-h-[90vh] flex-col">
          <DialogHeader className="space-y-3 border-b border-border p-4">
            <div>
              <DialogTitle>{title}</DialogTitle>
              {description && <DialogDescription className="mt-1">{description}</DialogDescription>}
            </div>
            <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
              <TabsList>
                <TabsTrigger value="upload">Upload files</TabsTrigger>
                <TabsTrigger value="library">My Assets</TabsTrigger>
              </TabsList>
            </Tabs>
          </DialogHeader>

          {error && (
            <p className="mx-4 mt-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>
          )}

          {tab === 'upload' ? (
            <div className="p-4">
              <div
                role="button"
                tabIndex={0}
                onClick={() => !busy && inputRef.current?.click()}
                onKeyDown={(e) => {
                  if (!busy && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    inputRef.current?.click();
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  if (!busy) uploadFiles(e.dataTransfer.files);
                }}
                className={cn(
                  'flex min-h-[280px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed bg-secondary/20 p-6 text-center transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  dragOver ? 'border-primary bg-secondary/40' : 'border-border hover:border-foreground/30',
                )}
              >
                {busy ? (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Uploading
                  </p>
                ) : (
                  <>
                    <Upload className="mb-3 h-6 w-6 text-muted-foreground" />
                    <p className="font-medium">Drop {multiple ? 'files' : 'a file'} here</p>
                    <p className="mt-1 text-sm text-muted-foreground">or</p>
                    <Button type="button" variant="outline" size="sm" className="mt-2" tabIndex={-1}>
                      Select {multiple ? 'files' : 'a file'}
                    </Button>
                    <p className="mt-4 max-w-sm text-xs text-muted-foreground">
                      Uploads are also kept in My Assets, so you can use them again in any tool.
                    </p>
                  </>
                )}
              </div>
              <input
                ref={inputRef}
                type="file"
                accept={accept}
                multiple={multiple}
                className="hidden"
                onChange={(e) => {
                  uploadFiles(e.target.files);
                  e.target.value = '';
                }}
              />
            </div>
          ) : (
            <>
              <div className="px-4 pt-4">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search your ${what}`} className="pl-9" aria-label="Search My Assets" />
                </div>
              </div>
              <div className="min-h-[280px] flex-1 overflow-y-auto p-4">
                {loading && assets.length === 0 ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4" aria-busy="true" aria-label="Loading My Assets">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <div key={i} className="overflow-hidden rounded-lg border border-border">
                        <div className="shimmer aspect-video w-full bg-muted" />
                        <div className="space-y-1.5 p-2">
                          <div className="shimmer h-3 w-3/4 rounded bg-muted" />
                          <div className="shimmer h-2.5 w-1/2 rounded bg-muted" />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : assets.length === 0 ? (
                  <div className="flex flex-col items-center py-12 text-center">
                    <p className="font-semibold tracking-tight">{query ? 'Nothing matches' : 'Nothing here yet'}</p>
                    <p className="mt-1 max-w-sm text-sm text-muted-foreground">
                      Files you upload are kept here. Manage them in{' '}
                      <Link to="/my-assets" className="text-primary hover:underline" onClick={() => onOpenChange(false)}>
                        My Assets
                      </Link>
                      .
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                      {assets.map((asset) => {
                        const reason = unusableReason?.(asset) ?? null;
                        const isSelected = selected.some((a) => a.id === asset.id);
                        return (
                          <button
                            key={asset.id}
                            type="button"
                            onClick={() => toggle(asset)}
                            disabled={!!reason || busy}
                            aria-pressed={multiple ? isSelected : undefined}
                            title={reason ?? asset.name}
                            className={cn(
                              'group overflow-hidden rounded-lg border text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                              reason
                                ? 'cursor-not-allowed border-border opacity-60'
                                : isSelected
                                  ? 'border-primary ring-2 ring-primary/40'
                                  : 'border-border hover:border-foreground/30',
                            )}
                          >
                            <div className="relative">
                              <AssetPreview asset={asset} className="aspect-video w-full" />
                              {isSelected && (
                                <span className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                                  <Check className="h-3.5 w-3.5" />
                                </span>
                              )}
                              {busy && !multiple && (
                                <div className="absolute inset-0 flex items-center justify-center bg-background/40" />
                              )}
                            </div>
                            <div className="space-y-0.5 p-2">
                              <p className="truncate text-sm">{asset.name}</p>
                              <p className={cn('truncate text-[11px] text-muted-foreground', !reason && 'font-mono')}>{reason ?? assetMeta(asset)}</p>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                    {page < totalPages && (
                      <div className="mt-4 flex justify-center">
                        <Button variant="ghost" size="sm" onClick={() => load(page + 1, query.trim())} disabled={loading}>
                          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                          Load more
                        </Button>
                      </div>
                    )}
                  </>
                )}
              </div>
              {(multiple || busy) && (
                <div className="flex items-center justify-end gap-3 border-t border-border p-4">
                  {busy && (
                    <span className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Preparing
                    </span>
                  )}
                  {multiple && (
                    <Button onClick={() => run(() => onPick(selected))} disabled={selected.length === 0 || busy}>
                      Select{selected.length > 0 ? ` (${selected.length})` : ''}
                    </Button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
