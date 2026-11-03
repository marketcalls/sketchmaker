import { useEffect, useState } from 'react';

/** Seconds since `active` turned true; resets to 0 when it turns false. */
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return;
    }
    const start = Date.now();
    setSeconds(0);
    const id = window.setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return seconds;
}

/** "8s" or "1m 05s" for a status line. */
export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

/** CSS aspect-ratio for a "16:9" style ratio, so placeholders match the output. */
export function ratioToCss(ratio: string | undefined | null, fallback = '1 / 1'): string {
  if (!ratio) return fallback;
  const [w, h] = ratio.split(':').map(Number);
  return w > 0 && h > 0 ? `${w} / ${h}` : fallback;
}

/** True for Ctrl+Enter or Cmd+Enter, the submit shortcut in prompt boxes. */
export function isSubmitShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean }): boolean {
  return e.key === 'Enter' && (e.ctrlKey || e.metaKey);
}
