import { useState } from 'react';
import { editKey, usePricingStore } from '@/stores/pricingStore';
import { getErrorMessage } from '@/utils/errors';
import { fixedImage, fixResolution, qualityApi, type Quality, type QualityFixTarget } from '@/api/quality';
import type { GeneratedImage } from '@/types';
import { QualityBadge, useImageQuality, useQualityConfig } from './QualityBadge';

// The check of one stored image (/generate, explainers) with its paid fixes:
// an edit of the kept image on the fix model, at that model's edit price.
export function ImageQuality({
  image,
  onFixed,
  className,
}: {
  image: Pick<GeneratedImage, 'id' | 'width' | 'height' | 'quality'>;
  onFixed: (image: GeneratedImage) => void;
  className?: string;
}) {
  const quality: Quality | null = useImageQuality(image.id, image.quality);
  const config = useQualityConfig();
  const costs = usePricingStore((s) => s.costs);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!quality) return null;

  const price = config ? costs?.[editKey(config.fix_model, fixResolution(image.width, image.height))] : undefined;
  const fixes = (quality.fixable ?? []).map((target) => ({ target, usd: price }));

  const fix = async (target: QualityFixTarget) => {
    setBusy(true);
    setError(null);
    try {
      onFixed(fixedImage(await qualityApi.fix(image.id, target)));
    } catch (err) {
      setError(getErrorMessage(err, 'The fix could not be made'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={className}>
      <QualityBadge quality={quality} fixes={fixes} onFix={config?.available === false ? undefined : fix} busy={busy} />
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
