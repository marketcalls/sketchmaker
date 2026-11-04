import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { settingsApi, type OfferedModel, type ProviderOffer } from '@/api/settings';
import { getErrorMessage } from '@/utils/errors';

const keyOf = (providerId: number, name: string) => `${providerId}:${name}`;

function statusMessage(offer: ProviderOffer): string | null {
  if (offer.status === 'key_rejected') return `${offer.provider} rejected your key. Check it under API keys.`;
  if (offer.status === 'unavailable') return `${offer.provider} could not be reached. Try again in a minute.`;
  return null;
}

function details(model: OfferedModel): string {
  const parts: string[] = [];
  if (model.released) {
    parts.push(new Date(model.released).toLocaleDateString(undefined, { month: 'short', year: 'numeric', timeZone: 'UTC' }));
  }
  if (model.context_window) parts.push(`${(model.context_window / 1000).toFixed(0)}K context`);
  return parts.join(' · ');
}

/** Asks each provider with a key what it offers now, and adds what the owner ticks. */
export function RefreshModelsDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: (count: number) => Promise<void>;
}) {
  const [offers, setOffers] = useState<ProviderOffer[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setOffers(null);
    setError(null);
    settingsApi
      .refreshModels()
      .then((providers) => {
        if (cancelled) return;
        setOffers(providers);
        setSelected(
          new Set(
            providers.flatMap((p) =>
              p.new_models.filter((m) => m.recommended).map((m) => keyOf(p.provider_id, m.name))
            )
          )
        );
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'The providers could not be checked.'));
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const newCount = useMemo(() => offers?.reduce((sum, p) => sum + p.new_models.length, 0) ?? 0, [offers]);

  const toggle = (key: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleAdd = async () => {
    if (!offers) return;
    setSaving(true);
    setError(null);
    try {
      const models = offers.flatMap((p) =>
        p.new_models
          .filter((m) => selected.has(keyOf(p.provider_id, m.name)))
          .map((m) => ({
            provider_id: p.provider_id,
            name: m.name,
            display_name: m.display_name,
            description: m.description,
            context_window: m.context_window,
          }))
      );
      const { added } = await settingsApi.addOfferedModels(models);
      await onAdded(added);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, 'The models could not be added.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Refresh models</DialogTitle>
          <DialogDescription>
            New models from each provider you have a key for. Recent ones are ticked. Nothing changes until you add them.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[55vh] space-y-5 overflow-y-auto pr-1">
          {!offers && !error && (
            <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Checking your providers
            </p>
          )}

          {offers?.length === 0 && (
            <p className="py-6 text-sm text-muted-foreground">
              Add a language model key first, under{' '}
              <Link className="text-primary underline underline-offset-4" to="/settings?tab=api-keys" reloadDocument>
                API keys
              </Link>
              .
            </p>
          )}

          {offers?.map((offer) => {
            const problem = statusMessage(offer);
            return (
              <section key={offer.provider_id} className="space-y-2">
                <h3 className="text-sm font-semibold">{offer.provider}</h3>
                {problem && <p className="text-sm text-destructive">{problem}</p>}
                {!problem && offer.new_models.length === 0 && (
                  <p className="text-sm text-muted-foreground">Up to date.</p>
                )}
                {offer.new_models.length > 0 && (
                  <ul className="divide-y divide-border rounded-xl border border-border">
                    {offer.new_models.map((model) => {
                      const key = keyOf(offer.provider_id, model.name);
                      return (
                        <li key={key}>
                          <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
                            <input
                              type="checkbox"
                              className="mt-0.5 h-4 w-4 accent-primary"
                              checked={selected.has(key)}
                              onChange={() => toggle(key)}
                            />
                            <span className="min-w-0">
                              <span className="block text-sm font-medium">{model.display_name}</span>
                              <span className="block break-all font-mono text-xs text-muted-foreground">{model.name}</span>
                              {details(model) && (
                                <span className="tabular block text-xs text-muted-foreground">{details(model)}</span>
                              )}
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {offer.no_longer_listed.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    No longer listed by {offer.provider}: {offer.no_longer_listed.join(', ')}. You can turn these off in the
                    model list.
                  </p>
                )}
              </section>
            );
          })}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {newCount === 0 ? 'Close' : 'Cancel'}
          </Button>
          {newCount > 0 && (
            <Button onClick={handleAdd} disabled={saving || selected.size === 0}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {saving ? 'Adding' : `Add ${selected.size} ${selected.size === 1 ? 'model' : 'models'}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
