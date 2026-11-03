import { create } from 'zustand';
import { assetsApi, type AssetKind } from '@/api/assets';
import { getErrorMessage } from '@/utils/errors';

// Every file a person uploads anywhere in the app is also kept in My Assets,
// so it can be picked again later (the WordPress media library model). The
// copy is made in the background after the tool already has the file: a
// failed copy (storage full, a video longer than My Assets keeps) never
// blocks the tool, it only shows a short notice.

interface MediaNotice {
  id: number;
  text: string;
}

interface MediaNoticeState {
  notices: MediaNotice[];
  push: (text: string) => void;
  dismiss: (id: number) => void;
}

let nextNotice = 1;

export const useMediaNoticeStore = create<MediaNoticeState>((set) => ({
  notices: [],
  push: (text) => {
    const id = nextNotice++;
    set((s) => ({ notices: [...s.notices.slice(-2), { id, text }] }));
    window.setTimeout(() => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })), 8000);
  },
  dismiss: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),
}));

/** The My Assets kind a file would be stored as, or null when My Assets does not keep that type. */
export function libraryKind(file: File, kinds: AssetKind[]): AssetKind | null {
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  if (type === 'image/svg+xml' || name.endsWith('.svg')) return 'logo';
  if (/^image\/(png|jpeg|webp)$/.test(type)) return kinds.length === 1 && kinds[0] === 'logo' ? 'logo' : 'image';
  if (type.startsWith('video/') || /\.(mp4|mov|webm|m4v)$/.test(name)) return 'video';
  if (type.startsWith('audio/') || /\.(mp3|wav|m4a|aac|ogg)$/.test(name)) return 'audio';
  return null;
}

let queue: Promise<void> = Promise.resolve();

/** Copies freshly uploaded files into My Assets, one at a time, in the background. */
export function saveToLibrary(files: File[], kinds: AssetKind[]): void {
  for (const file of files) {
    const kind = libraryKind(file, kinds);
    if (!kind) continue;
    queue = queue.then(async () => {
      try {
        await assetsApi.upload(file, { asLogo: kind === 'logo' });
      } catch (err) {
        useMediaNoticeStore
          .getState()
          .push(`${file.name} was used, but not saved to My Assets. ${getErrorMessage(err, 'Please try again later.')}`);
      }
    });
  }
}
