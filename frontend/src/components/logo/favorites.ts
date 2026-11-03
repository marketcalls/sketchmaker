import { useCallback, useEffect, useState } from 'react';

// Favorites are a per-browser shortlist, so they live in localStorage. Reads
// and writes are guarded: storage can be blocked or full.
const KEY = 'sketchmaker.logo.favorites';

function read(): number[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((v) => Number.isInteger(v)) : [];
  } catch {
    return [];
  }
}

export function useLogoFavorites() {
  const [ids, setIds] = useState<number[]>(read);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setIds(read());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const toggle = useCallback((id: number) => {
    setIds((prev) => {
      const next = prev.includes(id) ? prev.filter((v) => v !== id) : [id, ...prev].slice(0, 500);
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // Not persisted; the in-memory list still works for this visit.
      }
      return next;
    });
  }, []);

  return { favorites: ids, isFavorite: (id: number) => ids.includes(id), toggleFavorite: toggle };
}
