import { useRef, useState, type DragEvent, type ReactNode } from 'react';
import { assetsApi, type Asset, type AssetKind } from '@/api/assets';
import { acceptFor } from '@/components/assets/AssetPreview';
import { getErrorMessage } from '@/utils/errors';
import { saveToLibrary, useMediaNoticeStore } from './library';
import { MediaPickerDialog } from './MediaPickerDialog';

export interface MediaPickerOptions {
  // What the tool takes (filters My Assets and the file chooser).
  kinds: AssetKind[];
  // File chooser filter when it differs from the kinds' defaults.
  accept?: string;
  multiple?: boolean;
  // Most files in one go (defaults to 1, or 20 with multiple).
  maxFiles?: number;
  title?: string;
  description?: string;
  disabled?: boolean;
  // Why an asset cannot be used here (shown on its card), or null.
  unusableReason?: (asset: Asset) => string | null;
  // The page's ordinary upload handler. Assets picked from the library arrive
  // as Files too (unless onAssets is given), so the page's checks still run.
  onFiles: (files: File[]) => void | Promise<void>;
  // Tools that read an asset by id on the server take library picks here,
  // without downloading the file to the browser and uploading it again.
  onAssets?: (assets: Asset[]) => void | Promise<void>;
  // Uploads are copied into My Assets unless this is false (inputs that are
  // not media, such as documents).
  saveUploads?: boolean;
}

export interface MediaPicker {
  // Opens the media window.
  open: () => void;
  // Render once, anywhere in the page.
  dialog: ReactNode;
  // Spread on a drop area so files dropped on the page take the same path.
  dropProps: {
    onDragOver: (e: DragEvent) => void;
    onDragLeave: () => void;
    onDrop: (e: DragEvent) => void;
  };
  dragOver: boolean;
}

const KIND_WORDS: Record<AssetKind, string> = { image: 'an image', logo: 'a logo', video: 'a video', audio: 'audio' };

// One way to add media anywhere in the app: the WordPress-style window with
// "Upload files" and "My Assets", plus drag and drop onto the page.
export function useMediaPicker(options: MediaPickerOptions): MediaPicker {
  const { kinds, multiple = false, disabled, unusableReason } = options;
  const [isOpen, setOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const accept = options.accept ?? acceptFor(kinds);
  const maxFiles = options.maxFiles ?? (multiple ? 20 : 1);
  // Handlers change every render; the dialog always calls the latest ones.
  const latest = useRef(options);
  latest.current = options;

  const deliver = async (files: File[]) => {
    const chosen = files.slice(0, maxFiles);
    if (chosen.length === 0) return;
    await latest.current.onFiles(chosen);
    if (latest.current.saveUploads !== false) saveToLibrary(chosen, kinds);
  };

  const pick = async (assets: Asset[]) => {
    if (assets.length === 0) return;
    if (latest.current.onAssets) {
      await latest.current.onAssets(assets);
      return;
    }
    const files = await Promise.all(assets.map((a) => assetsApi.toFile(a)));
    await latest.current.onFiles(files);
  };

  // Files dropped on the page have nowhere else to show an error.
  const deliverQuietly = (files: File[]) => {
    deliver(files).catch((err) => useMediaNoticeStore.getState().push(getErrorMessage(err, 'Could not use that file.')));
  };

  // React events bubble through the dialog's portal to the page; a clickable
  // or droppable upload area around it must not see clicks or drops made inside.
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

  const open = () => {
    if (disabled) return;
    setOpen(true);
  };

  const dialog = (
    <span className="contents" onClick={stop} onKeyDown={stop} onDrop={stop} onDragOver={stop}>
      <MediaPickerDialog
        open={isOpen}
        onOpenChange={setOpen}
        kinds={kinds}
        accept={accept}
        title={options.title ?? (multiple ? 'Add files' : `Add ${KIND_WORDS[kinds[0]] ?? 'a file'}`)}
        description={options.description}
        multiple={multiple}
        maxFiles={maxFiles}
        unusableReason={unusableReason}
        onUpload={deliver}
        onPick={pick}
      />
    </span>
  );

  return {
    open,
    dialog,
    dragOver,
    dropProps: {
      onDragOver: (e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      },
      onDragLeave: () => setDragOver(false),
      onDrop: (e) => {
        e.preventDefault();
        setDragOver(false);
        if (!disabled) deliverQuietly(Array.from(e.dataTransfer.files));
      },
    },
  };
}
