import { useState } from 'react';
import { Check, ImagePlus, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { assetsApi } from '@/api/assets';
import { MAX_PRODUCTS, newProduct, type Product, type StoryDoc } from '@/api/storyRoom';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { EditableText } from './fields';

function nextProductKey(products: Product[]): string {
  const used = new Set(products.map((p) => p.key));
  let n = products.length + 1;
  while (used.has(`p${n}`)) n += 1;
  return `p${n}`;
}

/** The product photo: an upload of the real product (or a My Assets pick), never a generated image. */
function ProductPhoto({ product, disabled }: { product: Product; disabled: boolean }) {
  const { approveCastImage, clearCastImage } = useStoryRoomStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const approved = product.image_approved && !!product.image_url;

  const run = async (fn: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(getErrorMessage(err, fallback));
      throw err;
    } finally {
      setBusy(false);
    }
  };

  // Library picks go by asset id; uploads are saved to My Assets first.
  const media = useMediaPicker({
    kinds: ['image'],
    title: `Photo of ${product.name || 'the product'}`,
    description: 'A clear photo of the real product with its label readable. It is sent with every shot that shows it.',
    disabled: disabled || busy,
    saveUploads: false,
    onAssets: (assets) =>
      run(() => approveCastImage(product.key, { assetId: assets[0].id }), 'That photo could not be used.'),
    onFiles: (files) =>
      run(async () => {
        const asset = await assetsApi.upload(files[0]);
        await approveCastImage(product.key, { assetId: asset.id });
      }, 'That photo could not be used.'),
  });

  return (
    <div {...media.dropProps} className="shrink-0">
      {approved ? (
        <div className="relative aspect-square w-24 overflow-hidden rounded-lg border-2 border-primary/60 bg-muted">
          <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" />
          <span className="absolute left-1 top-1 flex items-center gap-1 rounded-md bg-background/85 px-1.5 py-0.5 text-[11px] text-foreground">
            <Check className="h-3 w-3 text-success" aria-hidden="true" /> Photo
          </span>
          <button
            type="button"
            disabled={disabled || busy}
            onClick={() => run(() => clearCastImage(product.key), 'The photo could not be removed.').catch(() => {})}
            className="absolute inset-x-1 bottom-1 flex items-center justify-center gap-1 rounded-md bg-background/80 py-0.5 text-[11px] text-foreground hover:bg-background disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} Change
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={media.open}
          disabled={disabled || busy}
          className={cn(
            'flex aspect-square w-24 flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed bg-secondary/20 px-1 text-center text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground disabled:opacity-60',
            media.dragOver ? 'border-foreground/40 bg-accent/40' : 'border-border',
          )}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
          <span className="text-[11px]">Add photo</span>
        </button>
      )}
      {error && <p className="mt-1 w-24 text-xs text-destructive">{error}</p>}
      {media.dialog}
    </div>
  );
}

/** Products: the real things the piece shows, each with an uploaded photo and the details that must never drift. */
export function ProductsPanel({ story, disabled }: { story: StoryDoc; disabled: boolean }) {
  const editStory = useStoryRoomStore((s) => s.editStory);
  const max = useStoryRoomStore((s) => s.config?.limits.maxProducts ?? MAX_PRODUCTS);
  const products = story.products ?? [];
  const [removing, setRemoving] = useState<Product | null>(null);

  const patch = (key: string, p: Partial<Product>) =>
    editStory((d) => ({ ...d, products: (d.products ?? []).map((x) => (x.key === key ? { ...x, ...p } : x)) }));
  const add = () => editStory((d) => ({ ...d, products: [...(d.products ?? []), newProduct(nextProductKey(d.products ?? []))] }));
  const remove = (key: string) =>
    editStory((d) => ({
      ...d,
      products: (d.products ?? []).filter((x) => x.key !== key),
      scenes: d.scenes.map((s) => ({ ...s, shots: s.shots.map((sh) => ({ ...sh, props: (sh.props ?? []).filter((k) => k !== key) })) })),
    }));

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-base font-semibold">Products</h3>
        <Button size="sm" variant="ghost" disabled={disabled || products.length >= max} onClick={add}>
          <Plus className="h-3.5 w-3.5" /> Add
        </Button>
      </div>
      <p className="mb-2 text-xs text-muted-foreground">
        Products are never generated. Add a photo of the real thing: it goes with every shot that shows it, and a hero shot opens on it.
      </p>
      {products.length === 0 && <p className="text-sm text-muted-foreground">No products. The director adds one when the brief names it.</p>}
      <div className="space-y-3">
        {products.map((p) => (
          <div key={p.key} className={cn('flex gap-3 rounded-xl border border-border p-3', !p.image_approved && 'bg-secondary/10')}>
            <ProductPhoto product={p} disabled={disabled} />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-start gap-1">
                <div className="min-w-0 flex-1">
                  <EditableText
                    value={p.name}
                    placeholder="Product name"
                    disabled={disabled}
                    maxLength={120}
                    onCommit={(name) => patch(p.key, { name })}
                    className="text-sm font-semibold"
                  />
                  <p className="px-2 font-mono text-[10px] tabular text-muted-foreground">{p.key}</p>
                </div>
                <button
                  type="button"
                  aria-label="Remove product"
                  disabled={disabled}
                  onClick={() => setRemoving(p)}
                  className="rounded p-1 text-muted-foreground hover:text-destructive disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <EditableText
                label="Description"
                multiline
                rows={1}
                value={p.description}
                disabled={disabled}
                onCommit={(description) => patch(p.key, { description })}
              />
              <EditableText
                label="Must keep (label text, colours, shape; one per line)"
                multiline
                rows={2}
                value={(p.must_keep ?? []).join('\n')}
                disabled={disabled}
                onCommit={(v) => patch(p.key, { must_keep: v.split('\n').map((x) => x.trim()).filter(Boolean) })}
              />
            </div>
          </div>
        ))}
      </div>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Remove this product?"
        description={`"${removing?.name || 'Untitled product'}" and its photo are removed from the story and from every shot that shows it.`}
        confirmText="Remove"
        variant="destructive"
        onConfirm={() => {
          if (removing) remove(removing.key);
        }}
      />
    </section>
  );
}
