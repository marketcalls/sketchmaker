import { useCallback, useState } from 'react';
import { facelessApi, newIdempotencyKey, type PaidStep, type StepOptions } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { QuoteConfirmDialog } from '../QuoteConfirmDialog';

export interface PaidRequest {
  step: PaidStep;
  sceneIds?: string[];
  options?: StepOptions;
  title: string;
  description: string;
  confirmLabel?: string;
}

// Quote, confirm, run: the one path every paid action in the studio takes.
// The quote comes from GET /projects/{id}/quote with exactly the scene ids
// and options the run will send, and the run carries a fresh idempotency key
// so a retried request never runs twice. Returns `request` to open the
// dialog and the dialog element to render.
export function usePaidStep(projectId: number | undefined) {
  const refreshProject = useFacelessStore((s) => s.refreshProject);
  const [req, setReq] = useState<(PaidRequest & { key: string }) | null>(null);
  const [open, setOpen] = useState(false);

  // One key per opened dialog: retrying a confirm that timed out reuses it.
  const request = useCallback((r: PaidRequest) => {
    setReq({ ...r, key: newIdempotencyKey(`${r.step}-${projectId ?? 0}`) });
    setOpen(true);
  }, [projectId]);

  const dialog =
    projectId && req ? (
      <QuoteConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={req.title}
        description={req.description}
        confirmLabel={req.confirmLabel}
        loadQuote={() => facelessApi.quote(projectId, req.step, req.sceneIds, req.options)}
        onConfirm={async (quote) => {
          await facelessApi.runStep(projectId, req.step, {
            scene_ids: req.sceneIds && req.sceneIds.length > 0 ? req.sceneIds : undefined,
            options: req.options,
            idempotency_key: req.key,
            expected_usd: quote.usd,
          });
          await refreshProject();
        }}
      />
    ) : null;

  return { request, dialog };
}
