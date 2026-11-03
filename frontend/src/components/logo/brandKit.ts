/**
 * Brand kit assets made in the browser from the logo's SVG: transparent PNGs,
 * favicons, social images and mockups. Everything is deterministic canvas
 * drawing, so it has no provider cost; the SVG inputs come from the API, which
 * rebuilt them with the server-side sanitiser.
 *
 * Colors in this file are artwork colors (paper, ink, shadows of the mockup
 * scenes), not UI colors, so they are plain hex values.
 */

import { makeIco, makeZip, textBytes, type ArchiveEntry } from './archive';

export interface KitSources {
  slug: string;
  brandName: string;
  tagline: string;
  /** The logo as stored (may carry a solid background). */
  original: string;
  /** Background removed, or the original when it has none. */
  transparent: string;
  monoBlack: string;
  monoWhite: string;
  /** Optional wordmark lockup built in the studio. */
  lockup?: string | null;
  brandSheet?: string | null;
  /** Background the logo was drawn on (#rrggbb), for icons and banners. */
  paper: string;
  palette: string[];
  headingFont: string;
  bodyFont: string;
}

interface SvgImage {
  img: HTMLImageElement;
  width: number;
  height: number;
}

function intrinsic(svgText: string): { doc: Document; width: number; height: number } {
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  const svg = doc.documentElement;
  if (svg.nodeName.toLowerCase() !== 'svg' || doc.getElementsByTagName('parsererror').length > 0) {
    throw new Error('The file is not a valid SVG');
  }
  const vb = svg.getAttribute('viewBox')?.trim().split(/[\s,]+/).map(Number);
  let width = 0;
  let height = 0;
  if (vb && vb.length === 4 && vb[2] > 0 && vb[3] > 0) {
    width = vb[2];
    height = vb[3];
  } else {
    width = parseFloat(svg.getAttribute('width') || '') || 1;
    height = parseFloat(svg.getAttribute('height') || '') || 1;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  }
  return { doc, width, height };
}

/** Load SVG text as an image rasterised at `pixels` on its long side. */
export async function loadSvg(svgText: string, pixels = 2048): Promise<SvgImage> {
  const { doc, width, height } = intrinsic(svgText);
  const scale = pixels / Math.max(width, height);
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));
  doc.documentElement.setAttribute('width', String(w));
  doc.documentElement.setAttribute('height', String(h));
  const source = new XMLSerializer().serializeToString(doc.documentElement);
  const href = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml' }));
  try {
    const img = new window.Image();
    img.decoding = 'async';
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('The SVG could not be rendered'));
      img.src = href;
    });
    return { img, width: w, height: h };
  } finally {
    // The decoded image stays usable after the URL is revoked.
    window.setTimeout(() => URL.revokeObjectURL(href), 0);
  }
}

function canvas(width: number, height: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('Canvas is not available in this browser');
  ctx.imageSmoothingQuality = 'high';
  return [c, ctx];
}

/** Draw `image` fitted (contain) into the box, centred. */
function drawFitted(ctx: CanvasRenderingContext2D, image: SvgImage, x: number, y: number, w: number, h: number) {
  const s = Math.min(w / image.width, h / image.height);
  const dw = image.width * s;
  const dh = image.height * s;
  ctx.drawImage(image.img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
}

export function canvasToBlob(c: HTMLCanvasElement, type = 'image/png'): Promise<Blob> {
  return new Promise((resolve, reject) =>
    c.toBlob((b) => (b ? resolve(b) : reject(new Error('Image export failed'))), type)
  );
}

async function pngBytes(c: HTMLCanvasElement): Promise<Uint8Array> {
  return new Uint8Array(await (await canvasToBlob(c)).arrayBuffer());
}

/** The logo on a square or rectangular tile, optionally on a background. */
export async function renderTile(
  svgText: string,
  width: number,
  height: number,
  options: { background?: string | null; padding?: number; radius?: number } = {}
): Promise<HTMLCanvasElement> {
  const pad = options.padding ?? 0;
  const image = await loadSvg(svgText, Math.max(width, height) * 2);
  const [c, ctx] = canvas(width, height);
  if (options.background) {
    ctx.fillStyle = options.background;
    if (options.radius) {
      ctx.beginPath();
      ctx.roundRect(0, 0, width, height, options.radius);
      ctx.fill();
    } else {
      ctx.fillRect(0, 0, width, height);
    }
  }
  const px = width * pad;
  const py = height * pad;
  drawFitted(ctx, image, px, py, width - 2 * px, height - 2 * py);
  return c;
}

/** PNG of the SVG at `pixels` on its long side, transparent. */
export async function renderPng(svgText: string, pixels: number): Promise<HTMLCanvasElement> {
  const image = await loadSvg(svgText, pixels);
  const [c, ctx] = canvas(image.width, image.height);
  ctx.drawImage(image.img, 0, 0, image.width, image.height);
  return c;
}

function luminance(hex: string): number {
  const v = hex.replace('#', '');
  const ch = (i: number) => {
    const c = parseInt(v.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(0) + 0.7152 * ch(2) + 0.0722 * ch(4);
}

/** A brand color usable as a fill behind white artwork, or null. */
export function accentColor(palette: string[]): string | null {
  return palette.find((c) => /^#[0-9a-f]{6}$/i.test(c) && luminance(c) > 0.03 && luminance(c) < 0.45) ?? null;
}

// ---------------------------------------------------------------------------
// Mockups
// ---------------------------------------------------------------------------

export type MockupKind = 'business-card' | 'app-icon' | 'storefront' | 't-shirt';

export const MOCKUPS: { kind: MockupKind; label: string }[] = [
  { kind: 'business-card', label: 'Business cards' },
  { kind: 'app-icon', label: 'App icon' },
  { kind: 'storefront', label: 'Storefront sign' },
  { kind: 't-shirt', label: 'T-shirt' },
];

const UI_FONT = "'Hanken Grotesk', system-ui, -apple-system, 'Segoe UI', sans-serif";

function shadow(ctx: CanvasRenderingContext2D, blur: number, y: number, alpha = 0.22) {
  ctx.shadowColor = `rgba(0, 0, 0, ${alpha})`;
  ctx.shadowBlur = blur;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = y;
}

function noShadow(ctx: CanvasRenderingContext2D) {
  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;
}

async function businessCards(src: KitSources): Promise<HTMLCanvasElement> {
  const [c, ctx] = canvas(1600, 1000);
  const g = ctx.createLinearGradient(0, 0, 1600, 1000);
  g.addColorStop(0, '#ece9e2');
  g.addColorStop(1, '#d6d1c6');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 1600, 1000);
  const cw = 700;
  const ch = 400;
  const accent = accentColor(src.palette) ?? '#1b1b1b';
  const white = await loadSvg(src.monoWhite, 1200);
  const color = await loadSvg(src.transparent, 1200);

  // Back of the card: brand color with the white logo.
  ctx.save();
  ctx.translate(520, 600);
  ctx.rotate((-9 * Math.PI) / 180);
  shadow(ctx, 50, 22);
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.roundRect(-cw / 2, -ch / 2, cw, ch, 14);
  ctx.fill();
  noShadow(ctx);
  drawFitted(ctx, white, -cw * 0.3, -ch * 0.3, cw * 0.6, ch * 0.6);
  ctx.restore();

  // Front: logo, name and contact lines.
  ctx.save();
  ctx.translate(1060, 430);
  ctx.rotate((5 * Math.PI) / 180);
  shadow(ctx, 50, 22);
  ctx.fillStyle = '#fbfaf7';
  ctx.beginPath();
  ctx.roundRect(-cw / 2, -ch / 2, cw, ch, 14);
  ctx.fill();
  noShadow(ctx);
  drawFitted(ctx, color, -cw / 2 + 44, -ch / 2 + 44, 190, 190);
  ctx.fillStyle = '#1b1b1b';
  ctx.font = `700 40px ${UI_FONT}`;
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(src.brandName || 'Your brand', -cw / 2 + 44, ch / 2 - 110, cw - 88);
  ctx.fillStyle = '#6b6860';
  ctx.font = `400 22px ${UI_FONT}`;
  if (src.tagline) ctx.fillText(src.tagline, -cw / 2 + 44, ch / 2 - 74, cw - 88);
  ctx.font = `500 20px ${UI_FONT}`;
  const site = `${src.slug}.com`;
  ctx.textAlign = 'right';
  ctx.fillText(`hello@${site}`, cw / 2 - 44, -ch / 2 + 70);
  ctx.fillText(site, cw / 2 - 44, -ch / 2 + 100);
  ctx.restore();
  return c;
}

async function appIcon(src: KitSources): Promise<HTMLCanvasElement> {
  const [c, ctx] = canvas(1200, 1200);
  const g = ctx.createLinearGradient(0, 0, 1200, 1200);
  g.addColorStop(0, '#dfe3ea');
  g.addColorStop(1, '#b9c0cc');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 1200, 1200);
  const logo = await loadSvg(src.transparent, 1200);
  const size = 560;
  const x = (1200 - size) / 2;
  const y = 250;
  shadow(ctx, 60, 26, 0.25);
  ctx.fillStyle = src.paper;
  ctx.beginPath();
  ctx.roundRect(x, y, size, size, size * 0.225);
  ctx.fill();
  noShadow(ctx);
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(x, y, size, size, size * 0.225);
  ctx.clip();
  drawFitted(ctx, logo, x + size * 0.17, y + size * 0.17, size * 0.66, size * 0.66);
  ctx.restore();
  ctx.fillStyle = '#20232a';
  ctx.font = `600 44px ${UI_FONT}`;
  ctx.textAlign = 'center';
  ctx.fillText(src.brandName || 'App', 600, y + size + 90, 900);
  // Small sizes, as on a home screen and in a tab.
  const smalls = [180, 120, 64];
  let sx = 600 - (smalls.reduce((a, b) => a + b, 0) + 2 * 60) / 2;
  for (const s of smalls) {
    const sy = 1040 - s / 2;
    ctx.fillStyle = src.paper;
    shadow(ctx, 20, 8, 0.18);
    ctx.beginPath();
    ctx.roundRect(sx, sy, s, s, s * 0.225);
    ctx.fill();
    noShadow(ctx);
    drawFitted(ctx, logo, sx + s * 0.17, sy + s * 0.17, s * 0.66, s * 0.66);
    sx += s + 60;
  }
  return c;
}

async function storefront(src: KitSources): Promise<HTMLCanvasElement> {
  const W = 1600;
  const H = 1100;
  const [c, ctx] = canvas(W, H);
  ctx.fillStyle = '#d9d3c5';
  ctx.fillRect(0, 0, W, H);
  // Brick courses.
  ctx.strokeStyle = 'rgba(80, 64, 48, 0.12)';
  ctx.lineWidth = 2;
  for (let y = 0, row = 0; y < H; y += 44, row++) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
    ctx.stroke();
    for (let x = row % 2 ? 60 : 0; x < W; x += 120) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x, y + 44);
      ctx.stroke();
    }
  }
  const accent = accentColor(src.palette) ?? '#1b1b1b';
  // Sign board.
  const signW = 1040;
  const signH = 260;
  const signX = (W - signW) / 2;
  const signY = 90;
  shadow(ctx, 40, 18, 0.3);
  ctx.fillStyle = '#1d1d1f';
  ctx.beginPath();
  ctx.roundRect(signX, signY, signW, signH, 18);
  ctx.fill();
  noShadow(ctx);
  const mark = await loadSvg(src.lockup ? recolorWhiteHint(src) : src.monoWhite, 2000);
  drawFitted(ctx, mark, signX + 60, signY + 40, signW - 120, signH - 80);
  // Awning with stripes and a scalloped edge.
  const awY = signY + signH + 40;
  const awH = 120;
  const stripes = 16;
  const sw = (W - 200) / stripes;
  for (let i = 0; i < stripes; i++) {
    ctx.fillStyle = i % 2 ? '#f4f1ea' : accent;
    ctx.beginPath();
    ctx.moveTo(100 + i * sw, awY);
    ctx.lineTo(100 + (i + 1) * sw, awY);
    ctx.lineTo(100 + (i + 1) * sw, awY + awH);
    ctx.arc(100 + (i + 0.5) * sw, awY + awH, sw / 2, 0, Math.PI);
    ctx.closePath();
    ctx.fill();
  }
  // Windows and door.
  const baseY = awY + awH + 60;
  const glass = ctx.createLinearGradient(0, baseY, 0, H - 120);
  glass.addColorStop(0, '#5f7684');
  glass.addColorStop(1, '#2b3a44');
  ctx.fillStyle = '#2a2a2c';
  ctx.fillRect(140, baseY - 16, W - 280, H - 120 - baseY + 16);
  ctx.fillStyle = glass;
  ctx.fillRect(160, baseY, 480, H - 140 - baseY);
  ctx.fillRect(W - 640, baseY, 480, H - 140 - baseY);
  ctx.fillRect(680, baseY, 240, H - 120 - baseY);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)';
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(200, baseY + 40);
  ctx.lineTo(320, baseY + 160);
  ctx.moveTo(W - 600, baseY + 40);
  ctx.lineTo(W - 480, baseY + 160);
  ctx.stroke();
  // Door decal.
  const small = await loadSvg(src.monoWhite, 600);
  drawFitted(ctx, small, 720, baseY + 60, 160, 120);
  // Pavement.
  ctx.fillStyle = '#9a958b';
  ctx.fillRect(0, H - 120, W, 120);
  return c;
}

/** The lockup in white, when there is one (the sign is dark). */
function recolorWhiteHint(src: KitSources): string {
  if (!src.lockup) return src.monoWhite;
  // Paint every explicit fill of the lockup white; it is our own sanitised
  // output with plain fill attributes.
  return src.lockup.replace(/fill="#[0-9a-fA-F]{6}"/g, 'fill="#ffffff"').replace(/<svg /, '<svg fill="#ffffff" ');
}

function shirtPath(ctx: CanvasRenderingContext2D) {
  ctx.beginPath();
  ctx.moveTo(520, 180);
  ctx.quadraticCurveTo(700, 290, 880, 180);
  ctx.lineTo(1120, 270);
  ctx.lineTo(1270, 560);
  ctx.lineTo(1090, 640);
  ctx.lineTo(1040, 560);
  ctx.lineTo(1040, 1240);
  ctx.quadraticCurveTo(700, 1270, 360, 1240);
  ctx.lineTo(360, 560);
  ctx.lineTo(310, 640);
  ctx.lineTo(130, 560);
  ctx.lineTo(280, 270);
  ctx.closePath();
}

async function tShirt(src: KitSources): Promise<HTMLCanvasElement> {
  const [c, ctx] = canvas(1400, 1400);
  ctx.fillStyle = '#e7e4dd';
  ctx.fillRect(0, 0, 1400, 1400);
  const dark = luminance(src.paper) < 0.5;
  const shirt = dark ? '#232325' : '#fbfbf9';
  ctx.save();
  shadow(ctx, 50, 24, 0.25);
  ctx.fillStyle = shirt;
  shirtPath(ctx);
  ctx.fill();
  ctx.restore();
  // Collar and soft folds.
  ctx.strokeStyle = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  ctx.lineWidth = 14;
  ctx.beginPath();
  ctx.moveTo(530, 186);
  ctx.quadraticCurveTo(700, 300, 870, 186);
  ctx.stroke();
  const folds = ctx.createLinearGradient(360, 0, 1040, 0);
  folds.addColorStop(0, 'rgba(0,0,0,0.06)');
  folds.addColorStop(0.5, 'rgba(0,0,0,0)');
  folds.addColorStop(1, 'rgba(0,0,0,0.06)');
  ctx.save();
  shirtPath(ctx);
  ctx.clip();
  ctx.fillStyle = folds;
  ctx.fillRect(0, 0, 1400, 1400);
  ctx.restore();
  const art = await loadSvg(dark ? src.monoWhite : src.transparent, 1200);
  drawFitted(ctx, art, 530, 420, 340, 340);
  return c;
}

export async function renderMockup(kind: MockupKind, src: KitSources): Promise<HTMLCanvasElement> {
  switch (kind) {
    case 'business-card':
      return businessCards(src);
    case 'app-icon':
      return appIcon(src);
    case 'storefront':
      return storefront(src);
    case 't-shirt':
      return tShirt(src);
  }
}

// ---------------------------------------------------------------------------
// The kit
// ---------------------------------------------------------------------------

export const PNG_SIZES = [256, 512, 1024, 2048];
export const FAVICON_SIZES = [16, 32, 48];

export const SOCIAL_FORMATS: { file: string; width: number; height: number; safe?: [number, number] }[] = [
  { file: 'profile-square-1080.png', width: 1080, height: 1080 },
  { file: 'og-image-1200x630.png', width: 1200, height: 630 },
  { file: 'x-header-1500x500.png', width: 1500, height: 500 },
  { file: 'linkedin-banner-1584x396.png', width: 1584, height: 396 },
  // YouTube crops banners to 1546x423 on most screens.
  { file: 'youtube-banner-2560x1440.png', width: 2560, height: 1440, safe: [1546, 423] },
];

function readme(src: KitSources, files: string[]): string {
  const rgb = (hex: string) =>
    [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(' ');
  const lines = [
    `${src.brandName || 'Brand'} brand kit`,
    '',
    src.tagline ? `Tagline: ${src.tagline}` : '',
    '',
    'Colors',
    ...src.palette.map((c) => `  ${c.toUpperCase()}   RGB ${rgb(c)}`),
    '',
    'Fonts (SIL Open Font License, free on Google Fonts)',
    `  Headings: ${src.headingFont}`,
    `  Body: ${src.bodyFont}`,
    '',
    'Usage',
    '  Use the SVG files wherever possible: they scale to any size.',
    '  Use the transparent PNGs on light backgrounds and the white version on dark ones.',
    '  Keep clear space around the logo and do not stretch, recolor or redraw it.',
    '  favicon: add <link rel="icon" href="/favicon.ico" sizes="any"> and',
    '  <link rel="icon" href="/favicon.svg" type="image/svg+xml"> and',
    '  <link rel="apple-touch-icon" href="/apple-touch-icon.png"> to your page head.',
    '',
    'Files',
    ...files.map((f) => `  ${f}`),
    '',
  ];
  return lines.filter((l, i, all) => !(l === '' && all[i - 1] === '')).join('\r\n');
}

/** Build the whole kit as a ZIP. `onProgress` gets a 0 to 1 fraction. */
export async function buildBrandKit(src: KitSources, onProgress?: (fraction: number, label: string) => void): Promise<Blob> {
  const entries: ArchiveEntry[] = [];
  const s = src.slug;
  const svgEntry = (name: string, text: string) => entries.push({ name, data: textBytes(text) });
  const steps: [string, () => Promise<void>][] = [];
  const add = (label: string, fn: () => Promise<void>) => steps.push([label, fn]);

  add('Vector files', async () => {
    svgEntry(`logo/${s}.svg`, src.original);
    svgEntry(`logo/${s}-transparent.svg`, src.transparent);
    svgEntry(`logo/${s}-black.svg`, src.monoBlack);
    svgEntry(`logo/${s}-white.svg`, src.monoWhite);
    if (src.lockup) svgEntry(`logo/${s}-wordmark.svg`, src.lockup);
  });
  for (const size of PNG_SIZES) {
    add(`PNG ${size}`, async () => {
      entries.push({ name: `png/${s}-${size}.png`, data: await pngBytes(await renderPng(src.transparent, size)) });
    });
  }
  add('One-color PNGs', async () => {
    entries.push({ name: `png/${s}-black-1024.png`, data: await pngBytes(await renderPng(src.monoBlack, 1024)) });
    entries.push({ name: `png/${s}-white-1024.png`, data: await pngBytes(await renderPng(src.monoWhite, 1024)) });
    if (src.lockup) {
      entries.push({ name: `png/${s}-wordmark-2048.png`, data: await pngBytes(await renderPng(src.lockup, 2048)) });
    }
  });
  add('Favicons', async () => {
    const icons = [];
    for (const size of FAVICON_SIZES) {
      const png = await pngBytes(await renderTile(src.transparent, size, size));
      icons.push({ size, png });
      if (size !== 48) entries.push({ name: `favicon/favicon-${size}x${size}.png`, data: png });
    }
    entries.push({ name: 'favicon/favicon.ico', data: makeIco(icons) });
    svgEntry('favicon/favicon.svg', src.transparent);
    entries.push({
      name: 'favicon/apple-touch-icon.png',
      data: await pngBytes(await renderTile(src.transparent, 180, 180, { background: src.paper, padding: 0.12 })),
    });
    for (const size of [192, 512]) {
      entries.push({
        name: `favicon/android-chrome-${size}x${size}.png`,
        data: await pngBytes(await renderTile(src.transparent, size, size, { background: src.paper, padding: 0.12 })),
      });
    }
    const manifest = {
      name: src.brandName || s,
      short_name: (src.brandName || s).slice(0, 12),
      icons: [
        { src: '/android-chrome-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: '/android-chrome-512x512.png', sizes: '512x512', type: 'image/png' },
      ],
      theme_color: accentColor(src.palette) ?? src.paper,
      background_color: src.paper,
      display: 'standalone',
    };
    svgEntry('favicon/site.webmanifest', JSON.stringify(manifest, null, 2));
  });
  add('Social images', async () => {
    const wide = src.lockup || src.transparent;
    for (const f of SOCIAL_FORMATS) {
      const square = f.width === f.height;
      const art = square ? src.transparent : wide;
      let c: HTMLCanvasElement;
      if (f.safe) {
        const [canvasEl, ctx] = canvas(f.width, f.height);
        ctx.fillStyle = src.paper;
        ctx.fillRect(0, 0, f.width, f.height);
        const tile = await renderTile(art, f.safe[0], f.safe[1], { padding: 0.12 });
        ctx.drawImage(tile, (f.width - f.safe[0]) / 2, (f.height - f.safe[1]) / 2);
        c = canvasEl;
      } else {
        c = await renderTile(art, f.width, f.height, { background: src.paper, padding: square ? 0.18 : 0.16 });
      }
      entries.push({ name: `social/${f.file}`, data: await pngBytes(c) });
    }
  });
  if (src.brandSheet) {
    add('Brand sheet', async () => {
      svgEntry('brand/brand-sheet.svg', src.brandSheet as string);
      entries.push({ name: 'brand/brand-sheet.png', data: await pngBytes(await renderPng(src.brandSheet as string, 2240)) });
    });
  }
  for (const m of MOCKUPS) {
    add(`Mockup: ${m.label}`, async () => {
      entries.push({ name: `mockups/${m.kind}.png`, data: await pngBytes(await renderMockup(m.kind, src)) });
    });
  }

  for (let i = 0; i < steps.length; i++) {
    onProgress?.(i / steps.length, steps[i][0]);
    await steps[i][1]();
  }
  const names = entries.map((e) => e.name);
  entries.push({ name: 'README.txt', data: textBytes(readme(src, names)) });
  onProgress?.(1, 'Packing');
  const zip = makeZip(entries.map((e) => ({ name: `${s}-brand-kit/${e.name}`, data: e.data })));
  return new Blob([zip as BlobPart], { type: 'application/zip' });
}
