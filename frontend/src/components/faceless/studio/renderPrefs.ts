import { useCallback, useEffect, useState } from 'react';
import type { RenderResolution, SafeZone } from '@/api/faceless';

// Render options the API takes per render run (music gain, music on or off)
// and preview-only choices. Kept per project in this browser so they survive
// a reload; the project's own settings hold everything the backend stores.
export interface RenderPrefs {
  musicGainDb: number | null; // null: the template's level
  music: boolean;
  resolution: RenderResolution | null;
  previewZone: SafeZone | null;
}

const DEFAULTS: RenderPrefs = { musicGainDb: null, music: true, resolution: null, previewZone: null };

function read(projectId: number): RenderPrefs {
  try {
    const raw = localStorage.getItem(`faceless:render:${projectId}`);
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<RenderPrefs>) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export function useRenderPrefs(projectId: number) {
  const [prefs, setPrefs] = useState<RenderPrefs>(() => read(projectId));
  useEffect(() => setPrefs(read(projectId)), [projectId]);
  const update = useCallback(
    (patch: Partial<RenderPrefs>) =>
      setPrefs((p) => {
        const next = { ...p, ...patch };
        try {
          localStorage.setItem(`faceless:render:${projectId}`, JSON.stringify(next));
        } catch {
          // storage unavailable: the choice holds for this session
        }
        return next;
      }),
    [projectId],
  );
  return [prefs, update] as const;
}
