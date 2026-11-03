import apiClient from './client';
import { transformImage } from './gallery';
import type { GeneratedImage } from '../types';

// Add text (backend app/routers/text_overlay.py, services/text_overlay.py):
// exact text layers drawn with the bundled fonts on a copy of a gallery image.

export type TextRole = 'headline' | 'subhead' | 'label' | 'cta';
export type TextAlign = 'left' | 'center' | 'right';
export type TextBackdrop = 'none' | 'scrim' | 'box';

export interface TextLayer {
  role: TextRole;
  text: string;
  weight: number;
  size: number; // per cent of the image width
  color: string;
  uppercase: boolean;
  align: TextAlign;
  x: number; // block centre, fraction of the width
  y: number; // block centre, fraction of the height
  max_width: number;
  line_height: number;
  backdrop: TextBackdrop;
  backdrop_color: string;
  backdrop_opacity: number;
  stroke: boolean;
  stroke_color: string;
  shadow: boolean;
}

export interface TextSpec {
  font: string;
  layers: TextLayer[];
}

export interface TextOverlayRole {
  id: TextRole;
  label: string;
  weight: number;
  size: number;
  uppercase: boolean;
  backdrop: TextBackdrop;
  y: number;
}

export interface SafeZone {
  top: number;
  bottom: number;
  left: number;
  right: number;
  name: string;
}

export interface TextOverlayFormat {
  destination: string;
  view_width: number;
  min_px: number;
  min_size: number;
  safe_zone: SafeZone;
}

export interface TextOverlayConfig {
  max_layers: number;
  max_text_chars: number;
  roles: TextOverlayRole[];
  fonts: { key: string; name: string; weights: [number, number]; hint: string }[];
  palette: { name: string; hex: string }[];
  positions: { id: string; x: number; y: number }[];
  formats: Record<string, TextOverlayFormat>;
}

export interface LayerBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface TextWarning {
  layer: number;
  kind: 'legibility' | 'safe_zone' | 'font';
  message: string;
}

export interface TextPreview {
  image: string; // PNG data URL
  boxes: LayerBox[];
  warnings: TextWarning[];
  width: number;
  height: number;
  format: string;
}

export const textOverlayApi = {
  config: async (): Promise<TextOverlayConfig> => (await apiClient.get('/text-overlay/config')).data,

  preview: async (imageId: number, spec: TextSpec, signal?: AbortSignal): Promise<TextPreview> =>
    (await apiClient.post('/text-overlay/preview', { image_id: imageId, spec }, { signal })).data,

  render: async (imageId: number, spec: TextSpec): Promise<{ image: GeneratedImage; warnings: TextWarning[] }> => {
    const { data } = await apiClient.post('/text-overlay/render', { image_id: imageId, spec });
    return { image: transformImage(data.image), warnings: data.warnings };
  },
};
