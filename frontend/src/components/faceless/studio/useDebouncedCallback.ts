import { useCallback, useEffect, useRef } from 'react';

// Holds a save back until the control has been quiet for `delay` ms, so dragging
// a colour or holding an arrow key sends one request, not one per event. A save
// still waiting when the step closes goes out then instead of being lost.
export function useDebouncedCallback<A extends unknown[]>(fn: (...args: A) => void, delay = 500) {
  const latest = useRef(fn);
  useEffect(() => {
    latest.current = fn;
  });
  const pending = useRef<{ timer: ReturnType<typeof setTimeout>; args: A } | null>(null);

  const cancel = useCallback(() => {
    if (pending.current) clearTimeout(pending.current.timer);
    pending.current = null;
  }, []);

  const flush = useCallback(() => {
    if (!pending.current) return;
    const { args, timer } = pending.current;
    clearTimeout(timer);
    pending.current = null;
    latest.current(...args);
  }, []);

  const call = useCallback(
    (...args: A) => {
      if (pending.current) clearTimeout(pending.current.timer);
      pending.current = { args, timer: setTimeout(flush, delay) };
    },
    [delay, flush],
  );

  useEffect(() => flush, [flush]);

  return { call, flush, cancel };
}
