import apiClient from '@/api/client';

/** Long side of a PNG exported from an SVG logo. */
export const PNG_EXPORT_SIZE = 2048;

/** Whether a gallery item is a vector file (logos are stored as .svg). */
export function isSvgImage(item: { filename?: string; url?: string }): boolean {
  const name = (item.filename || item.url || '').split('?')[0].toLowerCase();
  return name.endsWith('.svg');
}

/**
 * SVG source of a stored logo. Reads the public URL first and falls back to
 * the authenticated gallery download when the CDN refuses a cross-origin read.
 */
export async function fetchSvgText(url: string, galleryId?: number | null): Promise<string> {
  try {
    const response = await fetch(url, { credentials: 'omit' });
    if (response.ok) {
      const text = await response.text();
      if (text.includes('<svg')) return text;
    }
  } catch {
    // Fall through to the API.
  }
  if (galleryId == null) throw new Error('Could not load the SVG file');
  const response = await apiClient.get(`/gallery/${galleryId}/download/svg`, { responseType: 'text' });
  return response.data as string;
}

export function downloadBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Give the browser a moment to start the download before revoking.
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export function downloadSvgText(svgText: string, filename: string) {
  downloadBlob(new Blob([svgText], { type: 'image/svg+xml' }), filename);
}

function intrinsicSize(svg: Element): { width: number; height: number; fromViewBox: boolean } | null {
  const viewBox = svg.getAttribute('viewBox')?.trim().split(/[\s,]+/).map(Number);
  if (viewBox && viewBox.length === 4 && viewBox[2] > 0 && viewBox[3] > 0) {
    return { width: viewBox[2], height: viewBox[3], fromViewBox: true };
  }
  const width = parseFloat(svg.getAttribute('width') || '');
  const height = parseFloat(svg.getAttribute('height') || '');
  if (width > 0 && height > 0) return { width, height, fromViewBox: false };
  return null;
}

/**
 * Render SVG source to a PNG whose long side is `maxSide` pixels, keeping the
 * transparent background unless a `background` fill is given. The SVG is
 * loaded from a blob URL, so the canvas is never tainted by a cross-origin
 * image.
 */
export async function svgToPngBlob(svgText: string, maxSide = PNG_EXPORT_SIZE, background?: string): Promise<Blob> {
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  const svg = doc.documentElement;
  if (svg.nodeName.toLowerCase() !== 'svg' || doc.getElementsByTagName('parsererror').length > 0) {
    throw new Error('The file is not a valid SVG');
  }

  const size = intrinsicSize(svg) ?? { width: 1, height: 1, fromViewBox: false };
  if (!size.fromViewBox && size.width > 1) {
    // Without a viewBox, changing width/height would crop instead of scale.
    svg.setAttribute('viewBox', `0 0 ${size.width} ${size.height}`);
  }
  const scale = maxSide / Math.max(size.width, size.height);
  const outWidth = Math.max(1, Math.round(size.width * scale));
  const outHeight = Math.max(1, Math.round(size.height * scale));
  svg.setAttribute('width', String(outWidth));
  svg.setAttribute('height', String(outHeight));

  const source = new XMLSerializer().serializeToString(svg);
  const href = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml' }));
  try {
    const img = new window.Image();
    img.decoding = 'async';
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('The SVG could not be rendered'));
      img.src = href;
    });
    const canvas = document.createElement('canvas');
    canvas.width = outWidth;
    canvas.height = outHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas is not available in this browser');
    if (background) {
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, outWidth, outHeight);
    }
    ctx.drawImage(img, 0, 0, outWidth, outHeight);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG export failed'))), 'image/png');
    });
  } finally {
    URL.revokeObjectURL(href);
  }
}

/** A short file-name-safe slug, or the fallback when nothing usable is left. */
export function slugify(value: string | undefined | null, fallback = 'logo'): string {
  const slug = (value || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
  return slug || fallback;
}

export function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error('Could not read the image'));
    reader.readAsDataURL(blob);
  });
}

/** A PNG data URL of a stored logo, for the model calls that read raster input. */
export async function logoPngDataUrl(url: string, id: number, size = 1024): Promise<string> {
  const text = await fetchSvgText(url, id);
  return blobToDataUrl(await svgToPngBlob(text, size));
}
