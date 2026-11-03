import { useEffect, useMemo, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableEmptyRow,
  TableHead,
  TableHeader,
  TableLoadingRows,
  TableRow,
} from '@/components/ui/table';
import { TablePagination } from '@/components/common/TablePagination';
import { Stagger, StaggerItem } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { usageApi, type FalModels, type FalPrice, type UsageKind, type UsageLogEntry, type UsageSummary } from '@/api/usage';
import { formatLocalDateTime } from '@/lib/dateUtils';
import { cn } from '@/lib/utils';
import { formatUsd } from '@/stores/pricingStore';
import { friendlyError, getErrorMessage } from '@/utils/errors';

const DAYS = 30;
const LOG_PAGE_SIZE = 25;

const KIND_LABELS: Record<UsageKind, string> = {
  fal: 'fal',
  sarvam: 'Sarvam',
  llm: 'Language model',
};

function featureLabel(feature: string | null): string {
  if (!feature) return 'Other';
  const text = feature.replace(/[_-]+/g, ' ').trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// An amount the price table does not know (some LLM models) shows as a dash, never $0.00.
const estimate = (usd: number | null | undefined) => (usd === null || usd === undefined ? '-' : formatUsd(usd));

const tokens = (input: number, output: number) => `${input.toLocaleString()} in, ${output.toLocaleString()} out`;

function logAmount(entry: UsageLogEntry): string {
  if (entry.kind === 'llm') return `${tokens(entry.input_tokens ?? 0, entry.output_tokens ?? 0)} tokens`;
  if (entry.units === null) return '-';
  return `${entry.units.toLocaleString()}${entry.unit ? ` ${entry.unit}` : ''}`;
}

function StatTile({ label, value, note, loading }: { label: string; value: string; note?: string; loading: boolean }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        {loading ? (
          <div className="mt-2 space-y-2" aria-hidden="true">
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3 w-32" />
          </div>
        ) : (
          <>
            <p className="mt-1 font-mono text-2xl font-semibold">{value}</p>
            {note && <p className="tabular mt-1 text-xs text-muted-foreground">{note}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}

const countNote = (count: number) => `${count.toLocaleString()} result${count === 1 ? '' : 's'}`;

export function UsagePage() {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [entries, setEntries] = useState<UsageLogEntry[]>([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logPage, setLogPage] = useState(1);
  const [logLoading, setLogLoading] = useState(true);
  const [logLoaded, setLogLoaded] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);

  const [falModels, setFalModels] = useState<FalModels | null>(null);
  const [falLoading, setFalLoading] = useState(true);
  const [falError, setFalError] = useState<string | null>(null);
  const [prices, setPrices] = useState<Record<string, FalPrice>>({});
  const [loadingPrices, setLoadingPrices] = useState<Record<string, boolean>>({});

  useEffect(() => {
    usageApi
      .getSummary(DAYS)
      .then(setSummary)
      .catch((err) => setSummaryError(getErrorMessage(err, 'The totals could not be loaded. Refresh the page to try again.')));
    usageApi
      .getFalModels()
      .then(setFalModels)
      .catch((err) => setFalError(getErrorMessage(err, 'The model list could not be loaded. Refresh the page to try again.')))
      .finally(() => setFalLoading(false));
  }, []);

  useEffect(() => {
    let stale = false;
    setLogLoading(true);
    setLogError(null);
    usageApi
      .getLog(logPage, LOG_PAGE_SIZE)
      .then((data) => {
        if (stale) return;
        setEntries(data.entries);
        setLogTotal(data.total);
        setLogLoaded(true);
      })
      .catch((err) => {
        if (!stale) setLogError(getErrorMessage(err, 'The log could not be loaded. Refresh the page to try again.'));
      })
      .finally(() => {
        if (!stale) setLogLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [logPage]);

  const falCategories = useMemo(() => {
    const grouped = new Map<string, FalModels['models']>();
    for (const model of falModels?.models ?? []) {
      grouped.set(model.category, [...(grouped.get(model.category) ?? []), model]);
    }
    return [...grouped.entries()];
  }, [falModels]);

  const fetchPrice = async (modelId: string, displayName: string) => {
    setLoadingPrices((prev) => ({ ...prev, [modelId]: true }));
    try {
      const price = await usageApi.getFalPrice(modelId);
      setPrices((prev) => ({ ...prev, [modelId]: price }));
    } catch {
      setPrices((prev) => ({
        ...prev,
        [modelId]: {
          endpoint_id: modelId,
          display_name: displayName,
          unit_price: null,
          unit: 'unknown',
          currency: 'USD',
          error: 'Failed to fetch pricing',
        },
      }));
    } finally {
      setLoadingPrices((prev) => ({ ...prev, [modelId]: false }));
    }
  };

  const renderPriceCell = (modelId: string, displayName: string) => {
    if (loadingPrices[modelId]) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Fetching
        </span>
      );
    }

    const price = prices[modelId];
    if (price) {
      if (price.error) {
        return <span className="text-xs text-destructive">{friendlyError(price.error, 'Price not available.')}</span>;
      }
      if (price.unit_price !== null) {
        return <span className="tabular font-mono text-xs">{formatUsd(price.unit_price)}</span>;
      }
      return <Badge variant="secondary">No data</Badge>;
    }

    return (
      <Button variant="outline" size="sm" onClick={() => fetchPrice(modelId, displayName)}>
        <Search className="h-3.5 w-3.5" />
        Get price
      </Button>
    );
  };

  const renderUnitCell = (modelId: string) => {
    const price = prices[modelId];
    if (price && !price.error) {
      return <Badge variant="outline">{price.unit}</Badge>;
    }
    return <span className="text-muted-foreground">-</span>;
  };

  const falFrame = (rows: React.ReactNode) => (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <Table density="compact">
        <TableHeader>
          <TableRow>
            <TableHead>Model</TableHead>
            <TableHead>Endpoint id</TableHead>
            <TableHead className="text-right">Unit price</TableHead>
            <TableHead>Unit</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>{rows}</TableBody>
      </Table>
    </div>
  );

  const llm = summary?.by_kind.llm;
  const summaryLoading = !summary && !summaryError;
  const logPages = Math.max(1, Math.ceil(logTotal / LOG_PAGE_SIZE));
  const llmNotes = llm
    ? [
        `${tokens(llm.input_tokens ?? 0, llm.output_tokens ?? 0)} tokens`,
        llm.unpriced_calls
          ? `${llm.unpriced_calls.toLocaleString()} call${llm.unpriced_calls === 1 ? '' : 's'} with no known price`
          : '',
      ].filter(Boolean)
    : [];

  return (
    <>
      <SEO title="Usage" />
      <Stagger className="space-y-6" interval={0.04}>
        <StaggerItem>
          <header>
            <h1 className="text-2xl font-semibold tracking-tight">Usage</h1>
            <p className="mt-1 max-w-prose text-pretty text-sm text-muted-foreground">
              Estimated spending over the last {DAYS} days. Figures come from a built-in price table, not your
              provider's invoice.
            </p>
          </header>
        </StaggerItem>

        {summaryError && <Alert variant="destructive">{summaryError}</Alert>}

        <StaggerItem>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Estimated total" value={estimate(summary?.total_usd)} loading={summaryLoading} />
            <StatTile
              label="Estimated fal"
              value={estimate(summary?.by_kind.fal.usd)}
              note={summary ? countNote(summary.by_kind.fal.count) : undefined}
              loading={summaryLoading}
            />
            <StatTile
              label="Estimated Sarvam"
              value={estimate(summary?.by_kind.sarvam.usd)}
              note={summary ? countNote(summary.by_kind.sarvam.count) : undefined}
              loading={summaryLoading}
            />
            <StatTile
              label="Estimated language models"
              value={estimate(llm?.usd)}
              note={llmNotes.join(', ') || undefined}
              loading={summaryLoading}
            />
          </div>
        </StaggerItem>

        <StaggerItem>
          <section className="space-y-3">
            <h2 className="text-base font-semibold">By feature</h2>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <Table density="compact">
                <TableHeader>
                  <TableRow>
                    <TableHead>Feature</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-right">Uses</TableHead>
                    <TableHead className="text-right">Tokens</TableHead>
                    <TableHead className="text-right">Estimated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summaryLoading ? (
                    <TableLoadingRows columns={5} />
                  ) : !summary || summary.by_feature.length === 0 ? (
                    <TableEmptyRow columns={5}>Nothing has been spent in the last {DAYS} days.</TableEmptyRow>
                  ) : (
                    summary.by_feature.map((row) => (
                      <TableRow key={`${row.kind}:${row.feature}`}>
                        <TableCell className="font-medium">{featureLabel(row.feature)}</TableCell>
                        <TableCell className="text-muted-foreground">{KIND_LABELS[row.kind]}</TableCell>
                        <TableCell className="tabular text-right font-mono text-xs">{row.count.toLocaleString()}</TableCell>
                        <TableCell className="tabular text-right font-mono text-xs">
                          {row.kind === 'llm' ? tokens(row.input_tokens ?? 0, row.output_tokens ?? 0) : '-'}
                        </TableCell>
                        <TableCell className="tabular text-right font-mono text-xs">{estimate(row.usd)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </section>
        </StaggerItem>

        <StaggerItem>
          <section className="space-y-3">
            <h2 className="text-base font-semibold">Recent log</h2>
            {logError && <Alert variant="destructive">{logError}</Alert>}
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <Table stickyHeader density="compact">
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Feature</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead className="text-right">Estimated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className={cn('transition-opacity duration-150', logLoading && logLoaded && 'opacity-60')}>
                  {logLoading && !logLoaded ? (
                    <TableLoadingRows columns={5} />
                  ) : entries.length === 0 ? (
                    <TableEmptyRow columns={5}>Nothing has been logged yet.</TableEmptyRow>
                  ) : (
                    entries.map((entry) => (
                      <TableRow key={`${entry.kind}:${entry.id}`}>
                        <TableCell className="tabular whitespace-nowrap font-mono text-xs text-muted-foreground">
                          {formatLocalDateTime(entry.created_at, {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </TableCell>
                        <TableCell className="font-medium">{featureLabel(entry.feature)}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{entry.model ?? '-'}</TableCell>
                        <TableCell className="tabular text-right font-mono text-xs">{logAmount(entry)}</TableCell>
                        <TableCell className="tabular text-right font-mono text-xs">{estimate(entry.usd)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
              {logPages > 1 && (
                <TablePagination
                  page={logPage}
                  totalPages={logPages}
                  total={logTotal}
                  pageSize={LOG_PAGE_SIZE}
                  onPageChange={(p) => setLogPage(Math.min(Math.max(1, p), logPages))}
                  disabled={logLoading}
                />
              )}
            </div>
          </section>
        </StaggerItem>

        <StaggerItem>
          <section className="space-y-3">
            <div>
              <h2 className="text-base font-semibold">fal model prices</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Unit prices from fal.ai, fetched one model at a time with Get price.
              </p>
            </div>

            {falError && <Alert variant="destructive">{falError}</Alert>}

            {falLoading ? (
              <div aria-busy="true">{falFrame(<TableLoadingRows columns={4} rows={8} />)}</div>
            ) : (
              <div className="space-y-8">
                {falCategories.map(([category, categoryModels]) => (
                  <div key={category}>
                    <div className="mb-3 flex items-baseline justify-between gap-4">
                      <h3 className="text-sm font-semibold">{category}</h3>
                      <span className="tabular text-xs text-muted-foreground">
                        {categoryModels.length} model{categoryModels.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    {falFrame(
                      categoryModels.map((model) => (
                        <TableRow key={model.endpoint_id}>
                          <TableCell className="font-medium">{model.display_name}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{model.endpoint_id}</TableCell>
                          <TableCell className="text-right">
                            {renderPriceCell(model.endpoint_id, model.display_name)}
                          </TableCell>
                          <TableCell>{renderUnitCell(model.endpoint_id)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </div>
                ))}

                {falModels && (
                  <p className="tabular text-center text-xs text-muted-foreground">
                    {falModels.total_models} models across {falCategories.length} categories
                  </p>
                )}
              </div>
            )}
          </section>
        </StaggerItem>
      </Stagger>
    </>
  );
}
