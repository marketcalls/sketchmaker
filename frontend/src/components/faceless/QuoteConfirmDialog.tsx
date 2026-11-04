import { useEffect, useRef, useState } from 'react';
import { Loader2, ReceiptText, ShieldCheck } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { formatUsd } from '@/stores/pricingStore';
import { getErrorMessage } from '@/utils/errors';
import type { Quote } from '@/api/faceless';
import { ErrorNote } from './shared';

const unitCount = (units: number) => (Math.round((Number(units) || 0) * 100) / 100).toFixed(2);

interface QuoteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  // What will happen, in one sentence.
  description: string;
  confirmLabel?: string;
  // Fetches the server quote (GET /projects/{id}/quote). Called on open.
  loadQuote: () => Promise<Quote>;
  // Runs the step. The dialog stays open with the error if it throws.
  onConfirm: (quote: Quote) => Promise<void>;
}

// Every paid action goes through here: the server's estimate, line by line,
// and a confirm that carries the total.
export function QuoteConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm and generate',
  loadQuote,
  onConfirm,
}: QuoteConfirmDialogProps) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set synchronously, so a fast double click cannot send the step twice
  // before the disabled state renders.
  const submitting = useRef(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setQuote(null);
    setError(null);
    setLoading(true);
    loadQuote()
      .then((q) => {
        if (!cancelled) setQuote(q);
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'Could not price this step'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // loadQuote is recreated by callers each render; open is the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const total = quote?.usd ?? 0;
  // A render runs on this machine and costs nothing, so an empty render quote
  // is still a render to confirm.
  const nothingToDo = !!quote && quote.step !== 'render' && total <= 0 && quote.breakdown.length === 0;

  const confirm = async () => {
    if (!quote || submitting.current) return;
    submitting.current = true;
    setRunning(true);
    setError(null);
    try {
      await onConfirm(quote);
      onOpenChange(false);
    } catch (err) {
      // The price moved since the quote was shown: show the new one and let
      // the user confirm again (nothing started).
      const data = (err as { response?: { data?: { code?: string; quote?: Quote } } })?.response?.data;
      if (data?.code === 'quote_changed' && data.quote) setQuote(data.quote);
      setError(getErrorMessage(err, 'The step could not start'));
    } finally {
      submitting.current = false;
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !running && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ReceiptText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div aria-live="polite" aria-busy={loading}>
          {loading && (
            <div className="space-y-2">
              <div className="shimmer h-9 rounded-lg" />
              <div className="shimmer h-9 rounded-lg" />
              <div className="shimmer h-12 rounded-lg" />
            </div>
          )}

          {quote && (
            <div className="space-y-3">
              {quote.breakdown.length > 0 && (
                <table className="w-full text-sm">
                  <caption className="sr-only">Cost breakdown</caption>
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th scope="col" className="py-2 text-left font-normal">Item</th>
                      <th scope="col" className="py-2 text-right font-normal">Units</th>
                      <th scope="col" className="py-2 text-right font-normal">Estimate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quote.breakdown.map((line, i) => (
                      <tr key={`${line.label}-${i}`} className="border-b border-border/60">
                        <td className="py-2 pr-2">
                          <span>{line.label}</span>
                          <span className="block text-[11px] text-muted-foreground">
                            {line.count > 1 ? `${line.count} requests, ` : ''}
                            {formatUsd(line.unit_usd)} per {line.unit}
                          </span>
                        </td>
                        <td className="py-2 text-right font-mono text-xs tabular text-muted-foreground">{unitCount(line.units)}</td>
                        <td className="py-2 text-right font-mono text-xs tabular">{formatUsd(line.usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <div className="flex items-end justify-between rounded-lg border border-border bg-secondary/40 p-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Estimated cost</p>
                  <p className="font-mono text-2xl font-medium tabular text-foreground">{formatUsd(total)}</p>
                </div>
              </div>

              {quote.assumptions.length > 0 && (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {quote.assumptions.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              )}

              <p className="flex items-start gap-2 text-xs text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden="true" />
                <span>
                  Anything that fails costs nothing; only what is delivered counts. Estimated from a built-in price table, not fal's invoice.
                  {quote.step === 'render' && ' Rendering runs on this machine, so it has no provider cost.'}
                </span>
              </p>

              {nothingToDo && (
                <p className="text-sm text-muted-foreground">Nothing to generate for this selection.</p>
              )}
            </div>
          )}

          {error && <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={running}>
            Cancel
          </Button>
          <Button
            onClick={confirm}
            disabled={!quote || loading || running || nothingToDo}
          >
            {running && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {quote ? `${confirmLabel} (${formatUsd(total)})` : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
