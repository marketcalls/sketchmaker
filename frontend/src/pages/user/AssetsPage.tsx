import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AudioLines,
  Download,
  FolderOpen,
  Loader2,
  Mic,
  Pencil,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Stagger, StaggerItem } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { AssetPreview, ASSET_KIND_LABELS, acceptFor, assetMeta } from '@/components/assets/AssetPreview';
import { VoiceGenerator } from '@/components/assets/VoiceGenerator';
import { assetsApi, type Asset, type AssetKind } from '@/api/assets';
import { cn } from '@/lib/utils';
import { formatLocalDate } from '@/lib/dateUtils';
import { getErrorMessage } from '@/utils/errors';

const PAGE_SIZE = 24;
const ALL_KINDS: AssetKind[] = ['image', 'logo', 'video', 'audio'];

const FILTERS: { id: 'all' | AssetKind; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'image', label: 'Images' },
  { id: 'logo', label: 'Logos' },
  { id: 'video', label: 'Videos' },
  { id: 'audio', label: 'Audio' },
];

interface UploadState {
  name: string;
  percent: number;
}

export function AssetsPage() {
  const [filter, setFilter] = useState<'all' | AssetKind>('all');
  const [query, setQuery] = useState('');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadState | null>(null);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [viewing, setViewing] = useState<Asset | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Asset | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestSeq = useRef(0);

  const kinds = filter === 'all' ? ALL_KINDS : [filter];

  const load = useCallback(
    async (nextPage: number) => {
      const seq = ++requestSeq.current;
      setLoading(true);
      setError(null);
      try {
        const result = await assetsApi.list({
          kinds: filter === 'all' ? undefined : [filter],
          q: query.trim(),
          page: nextPage,
          pageSize: PAGE_SIZE,
        });
        if (seq !== requestSeq.current) return; // a newer filter or search replaced this request
        setAssets((prev) => {
          if (nextPage === 1) return result.assets;
          // Items added or removed since the last page shift the offsets.
          const seen = new Set(prev.map((a) => a.id));
          return [...prev, ...result.assets.filter((a) => !seen.has(a.id))];
        });
        setPage(result.page);
        setTotalPages(result.totalPages);
        setTotal(result.total);
      } catch (err) {
        setError(getErrorMessage(err, 'Could not load your assets'));
      } finally {
        if (seq === requestSeq.current) setLoading(false);
      }
    },
    [filter, query],
  );

  useEffect(() => {
    const timer = setTimeout(() => load(1), query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, query]);

  const added = (asset: Asset) => {
    if (filter === 'all' || filter === asset.kind) {
      setAssets((prev) => [asset, ...prev.filter((a) => a.id !== asset.id)]);
      setTotal((n) => n + 1);
    }
  };

  const uploadFiles = async (files: File[]) => {
    if (files.length === 0) return;
    const errors: string[] = [];
    for (const file of files) {
      setUploads({ name: file.name, percent: 0 });
      try {
        const asset = await assetsApi.upload(file, {
          asLogo: filter === 'logo',
          onProgress: (percent) => setUploads({ name: file.name, percent }),
        });
        added(asset);
      } catch (err) {
        errors.push(`${file.name}: ${getErrorMessage(err, 'upload failed')}`);
      }
    }
    setUploads(null);
    setUploadErrors(errors);
  };

  const remove = async (asset: Asset) => {
    try {
      await assetsApi.remove(asset.id);
      setAssets((prev) => prev.filter((a) => a.id !== asset.id));
      setTotal((n) => Math.max(0, n - 1));
      if (viewing?.id === asset.id) setViewing(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not delete the asset'));
    }
  };

  const renamed = (asset: Asset) => {
    setAssets((prev) => prev.map((a) => (a.id === asset.id ? asset : a)));
    setViewing(asset);
  };

  return (
    <>
      <SEO title="My Assets" description="Your uploaded images, logos, videos and audio, and generated voices." url="/my-assets" />
      <Stagger className="w-full" interval={0.06}>
        <StaggerItem>
          <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-balance text-2xl font-semibold tracking-tight">My Assets</h1>
              <p className="mt-1 max-w-xl text-pretty text-sm text-muted-foreground">
                Upload images, logos, videos and audio once and use them in Lip Sync and Motion Control. Voices you
                generate are kept here too.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setVoiceOpen(true)}>
                <Mic className="mr-2 h-4 w-4" />
                Generate voice
              </Button>
              <Button onClick={() => inputRef.current?.click()} disabled={uploads !== null}>
                {uploads ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                Upload
              </Button>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept={acceptFor(kinds)}
                className="hidden"
                onChange={(e) => {
                  uploadFiles(Array.from(e.target.files ?? []));
                  e.target.value = '';
                }}
              />
            </div>
          </div>
        </StaggerItem>

        <StaggerItem>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div role="tablist" aria-label="Asset type" className="flex flex-wrap gap-0.5 self-start rounded-md border border-border bg-muted/60 p-0.5">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  role="tab"
                  aria-selected={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    'rounded px-3 py-1.5 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    filter === f.id ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="relative sm:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name" className="pl-9" aria-label="Search assets" />
            </div>
          </div>
        </StaggerItem>

        <StaggerItem>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              uploadFiles(Array.from(e.dataTransfer.files));
            }}
            className={cn('rounded-xl transition-shadow duration-150', dragOver && 'ring-2 ring-primary/40 ring-offset-4 ring-offset-background')}
          >
            {uploads && (
              <div className="mb-4 rounded-lg border border-border bg-secondary/30 p-3">
                <p className="mb-2 truncate text-xs text-muted-foreground" role="status" aria-live="polite">
                  Uploading {uploads.name} <span className="font-mono tabular">{uploads.percent}%</span>
                </p>
                <Progress value={uploads.percent} className="h-1.5" />
              </div>
            )}
            {uploadErrors.length > 0 && (
              <div role="alert" className="mb-4 flex items-start justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                <ul className="space-y-1">
                  {uploadErrors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => setUploadErrors([])}
                  aria-label="Dismiss"
                  className="rounded-md p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            {error && (
              <p role="alert" className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>
            )}

            {loading && assets.length === 0 ? (
              <div aria-busy="true" aria-label="Loading assets">
                <div className="mb-3 h-4" />
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="overflow-hidden rounded-xl border border-border bg-card">
                      <div className="shimmer aspect-video w-full bg-muted" />
                      <div className="space-y-2 p-3">
                        <div className="shimmer h-3.5 w-3/4 rounded bg-muted" />
                        <div className="shimmer h-2.5 w-1/2 rounded bg-muted" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : assets.length === 0 ? (
              error ? null : query ? (
                <div className="flex min-h-[260px] flex-col items-center justify-center rounded-xl border border-border bg-secondary/20 p-6 text-center">
                  <Search className="mb-3 h-6 w-6 text-muted-foreground" />
                  <p className="font-semibold tracking-tight">Nothing matches "{query.trim()}"</p>
                  <p className="mt-1 text-sm text-muted-foreground">Try another name, or clear the search.</p>
                  <Button variant="outline" className="mt-5" onClick={() => setQuery('')}>
                    Clear search
                  </Button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="flex min-h-[260px] w-full flex-col items-center justify-center rounded-xl border border-dashed border-border bg-secondary/20 p-6 text-center transition-colors duration-150 hover:border-foreground/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <FolderOpen className="mb-3 h-6 w-6 text-muted-foreground" />
                  <p className="font-semibold tracking-tight">No assets yet</p>
                  <p className="mt-1 text-sm text-muted-foreground">Drop files here or click to upload.</p>
                  <p className="mt-3 max-w-prose text-pretty text-xs text-muted-foreground">
                    Images PNG, JPG or WebP up to 25 MB. Logos SVG or PNG up to 5 MB. Videos MP4, MOV or WebM up to 100 MB. Audio MP3, WAV, M4A, AAC or OGG up to 25 MB.
                  </p>
                </button>
              )
            ) : (
              <>
                <p className="mb-3 text-xs tabular text-muted-foreground">
                  {total} {total === 1 ? 'asset' : 'assets'}
                </p>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                  {assets.map((asset) => (
                    <Card key={asset.id} className="group overflow-hidden transition-colors duration-150 hover:border-foreground/20">
                      <button
                        type="button"
                        onClick={() => setViewing(asset)}
                        className="relative block w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                        aria-label={`Open ${asset.name}`}
                      >
                        <AssetPreview asset={asset} className="aspect-video w-full" />
                        <span className="glass absolute left-2 top-2 rounded-md px-1.5 py-0.5 text-[11px] font-medium text-foreground">
                          {asset.source === 'voice' ? 'Voice' : ASSET_KIND_LABELS[asset.kind]}
                        </span>
                      </button>
                      <CardContent className="space-y-1 p-3">
                        <p className="truncate text-sm" title={asset.name}>{asset.name}</p>
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate font-mono text-[11px] text-muted-foreground">{assetMeta(asset)}</p>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 shrink-0 hover:text-destructive"
                            onClick={() => setDeleteTarget(asset)}
                            aria-label={`Delete ${asset.name}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
                {page < totalPages && (
                  <div className="mt-6 flex justify-center">
                    <Button variant="ghost" onClick={() => load(page + 1)} disabled={loading}>
                      {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Load more
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </StaggerItem>
      </Stagger>

      <Dialog open={voiceOpen} onOpenChange={setVoiceOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AudioLines className="h-4 w-4 text-muted-foreground" />
              Generate a voice
            </DialogTitle>
            <DialogDescription>Type a script, pick an ElevenLabs voice, and the audio is saved to My Assets.</DialogDescription>
          </DialogHeader>
          <VoiceGenerator
            onCreated={(asset) => {
              added(asset);
              setVoiceOpen(false);
              setViewing(asset);
            }}
          />
        </DialogContent>
      </Dialog>

      {viewing && (
        <AssetViewer
          asset={viewing}
          onClose={() => setViewing(null)}
          onRenamed={renamed}
          onDelete={() => setDeleteTarget(viewing)}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Delete "${deleteTarget?.name ?? ''}"?`}
        description="It is removed from My Assets and its storage freed. Videos already made with it are kept. This cannot be undone."
        confirmText="Delete asset"
        variant="destructive"
        onConfirm={async () => {
          if (deleteTarget) await remove(deleteTarget);
          setDeleteTarget(null);
        }}
      />
    </>
  );
}

function AssetViewer({
  asset,
  onClose,
  onRenamed,
  onDelete,
}: {
  asset: Asset;
  onClose: () => void;
  onRenamed: (asset: Asset) => void;
  onDelete: () => void;
}) {
  const [name, setName] = useState(asset.name);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(asset.name);
    setEditing(false);
    setError(null);
  }, [asset]);

  const save = async () => {
    const next = name.trim();
    if (!next || next === asset.name) {
      setEditing(false);
      setName(asset.name);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onRenamed(await assetsApi.rename(asset.id, next));
      setEditing(false);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not rename the asset'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          {editing ? (
            <form
              className="flex gap-2 pr-8"
              onSubmit={(e) => {
                e.preventDefault();
                save();
              }}
            >
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoFocus aria-label="Asset name" />
              <Button type="submit" size="sm" disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
              </Button>
            </form>
          ) : (
            <DialogTitle className="flex items-center gap-2 pr-8">
              <span className="truncate">{asset.name}</span>
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-md p-0.5 text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Rename"
                title="Rename"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </DialogTitle>
          )}
          <DialogDescription className="text-xs">
            {asset.source === 'voice' ? 'Generated voice' : ASSET_KIND_LABELS[asset.kind]} / {assetMeta(asset)} / {formatLocalDate(asset.createdAt)}
          </DialogDescription>
        </DialogHeader>
        {error && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}

        <div className="flex max-h-[60vh] items-center justify-center overflow-hidden rounded-lg border border-border bg-background">
          {asset.kind === 'image' || asset.kind === 'logo' ? (
            <img src={asset.url} alt={asset.name} className={cn('max-h-[60vh] w-full object-contain', asset.kind === 'logo' && 'p-6')} />
          ) : asset.kind === 'video' ? (
            <video src={asset.url} controls playsInline className="max-h-[60vh] w-full" />
          ) : (
            <div className="w-full space-y-3 p-4">
              <audio src={asset.url} controls preload="metadata" className="w-full" />
              {asset.text && (
                <p className="whitespace-pre-wrap rounded-lg bg-secondary/40 p-3 text-sm text-muted-foreground">
                  {asset.voice && <span className="mr-2 font-mono text-[11px] text-foreground">{asset.voice}</span>}
                  {asset.text}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap justify-between gap-2">
          <Button variant="ghost" className="hover:text-destructive" onClick={onDelete}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
          <div className="flex flex-wrap gap-2">
            {(asset.kind === 'image' || asset.kind === 'audio') && (
              <Button variant="outline" asChild>
                <Link to="/lip-sync" state={{ asset }}>Use in Lip Sync</Link>
              </Button>
            )}
            {(asset.kind === 'image' || asset.kind === 'video') && (
              <Button variant="outline" asChild>
                <Link to="/motion-control" state={{ asset }}>Use in Motion Control</Link>
              </Button>
            )}
            <Button asChild>
              <a href={asset.url} target="_blank" rel="noopener noreferrer" download>
                <Download className="mr-2 h-4 w-4" />
                Open file
              </a>
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default AssetsPage;
