import { useEffect, useState } from 'react';
import { getErrorMessage } from '@/utils/errors';
import { facelessApi, type PaidStep, type Quote, type StepOptions } from '@/api/faceless';

// A debounced server quote that follows the current selection, for showing
// the price inline before the confirm dialog. `version` re-quotes when the
// project changes underneath (new assets, new script).
export function useLiveQuote(
  projectId: number,
  step: PaidStep,
  sceneIds: string[] | undefined,
  options: StepOptions | undefined,
  enabled: boolean,
  version: string | number,
) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const key = JSON.stringify([sceneIds ?? null, options ?? null, version]);

  useEffect(() => {
    if (!enabled) {
      setQuote(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(() => {
      facelessApi
        .quote(projectId, step, sceneIds, options)
        .then((q) => {
          if (!cancelled) {
            setQuote(q);
            setError(null);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setQuote(null);
            setError(getErrorMessage(err, 'Could not price this'));
          }
        })
        .finally(() => !cancelled && setLoading(false));
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // key captures sceneIds, options and version
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, step, enabled, key]);

  return { quote, error, loading };
}
