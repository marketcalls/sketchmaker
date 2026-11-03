// Model ID to display name mapping. Retired models stay so images and jobs
// made with them still show a readable name. Keep in step with MODEL_NAMES in
// backend/app/utils/media_labels.py (the gallery payloads send its names).
export const MODEL_DISPLAY_NAMES: Record<string, string> = {
  // Text to image (/generate)
  'blackforestlabs/flux-3/klein/text-to-image': 'Flux 3 Klein',
  'blackforestlabs/flux-3/text-to-image': 'Flux 3',
  'openai/gpt-image-2.5/sunburst/text-to-image': 'GPT Image 2.5',
  'google/nano-banana-2.1': 'Nano Banana 2.1',
  'ideogram/v4.5': 'Ideogram V4.5',
  'microsoft/mai-image-2.5': 'MAI Image 2.5',
  'xai/grok-imagine-image/v2.0/text-to-image': 'Grok Imagine 2.0',
  'fal-ai/z-image/turbo/lora': 'Z-Image Turbo',
  'bytedance/seedream/v5/pro/text-to-image': 'Seedream V5 Pro',
  // Image edit (Magix, Virtual Try-On)
  'google/nano-banana-2.1/edit': 'Nano Banana 2.1',
  'openai/gpt-image-2.5/sunburst/edit': 'GPT Image 2.5',
  'blackforestlabs/flux-3/edit-image': 'Flux 3',
  'xai/grok-imagine-image/v2.0/edit': 'Grok Imagine 2.0',
  'ideogram/v4.5/edit': 'Ideogram V4.5',
  // Add text (Pillow, no provider)
  'sketchmaker/text-overlay': 'Add text',
  // Explainer
  'openai/gpt-image-2': 'GPT Image 2',
  'openai/gpt-image-2/edit': 'GPT Image 2 (Edit)',
  // Logo
  'ideogram/vector/text-to-vector': 'Ideogram Vector',
  'ideogram/vector/image-to-vector': 'Ideogram Vectorize',
  // Stories
  'minimax/h3-max/text-to-video': 'MiniMax H3 Max',
  'minimax/h3-max/image-to-video': 'MiniMax H3 Max',
  'minimax/h3-max/reference-to-video': 'MiniMax H3 Max',
  'bytedance/seedance-2.5/us/text-to-video': 'Seedance 2.5',
  'bytedance/seedance-2.5/us/image-to-video': 'Seedance 2.5',
  'bytedance/seedance-2.5/us/reference-to-video': 'Seedance 2.5',
  'kling/v4/text-to-video': 'Kling v4',
  'kling/v4/image-to-video': 'Kling v4',
  'kling/v4/reference-to-video': 'Kling v4',
  'blackforestlabs/flux-3-max/text-to-video': 'FLUX 3 Max',
  'blackforestlabs/flux-3-max/image-to-video': 'FLUX 3 Max',
  'blackforestlabs/flux-3-max/keyframes-to-video': 'FLUX 3 Max',
  'google/gemini-omni-flash/v1.1/text-to-video': 'Gemini Omni Flash 1.1',
  'google/gemini-omni-flash/v1.1/image-to-video': 'Gemini Omni Flash 1.1',
  'google/gemini-omni-flash/v1.1/reference-to-video': 'Gemini Omni Flash 1.1',
  // Lip sync
  'minimax/h3-max/lip-sync/image-to-video': 'MiniMax H3 Max Lip Sync',
  // Motion control
  'fal-ai/kling-video/v2.6/standard/motion-control': 'Kling 2.6 Motion Control',
  'fal-ai/kling-video/v3/standard/motion-control': 'Kling 3 Motion Control',
  'fal-ai/kling-video/v3/pro/motion-control': 'Kling 3 Pro Motion Control',
  'minimax/h3-max/recast': 'H3 Max Recast (multi-character)',
  // Subtitles
  'fal-ai/workflow-utilities/auto-subtitle': 'Auto Subtitle',
  // Retired
  'bytedance/seedance-2.0/fast/text-to-video': 'Seedance 2.0 Fast',
  'bytedance/seedance-2.0/fast/image-to-video': 'Seedance 2.0 Fast',
  'bytedance/seedance-2.0/fast/reference-to-video': 'Seedance 2.0 Fast',
  'fal-ai/gpt-image-1.5': 'GPT Image 1.5',
  'fal-ai/bytedance/seedream/v4.5/text-to-image': 'Seedream V4.5',
  'fal-ai/nano-banana-2': 'Nano Banana 2',
  'fal-ai/nano-banana-2/edit': 'Nano Banana 2',
  'fal-ai/flux-2-flex': 'Flux 2 Flex',
  'fal-ai/flux-2-pro': 'Flux 2 Pro',
  'fal-ai/flux-2-max': 'Flux 2 Max',
  'fal-ai/flux-2/turbo': 'Flux 2 Turbo',
  'fal-ai/flux-lora': 'Flux LoRA',
  'ideogram/v4': 'Ideogram V4',
  'fal-ai/imagen4/preview': 'Imagen 4',
};

/**
 * Get user-friendly display name for a model ID
 */
export function getModelDisplayName(modelId: string | undefined | null): string {
  if (!modelId) return 'Unknown';
  return MODEL_DISPLAY_NAMES[modelId] || modelId.split('/').pop()?.replace(/-/g, ' ') || modelId;
}

// Image edit models offered by Magix and Virtual Try-On. Must match
// EDIT_MODEL_CONFIG in backend/app/clients/fal_client.py; the first is the default.
// maxImages: results one request returns (Try-On charges per result).
export const EDIT_MODELS = [
  { value: 'google/nano-banana-2.1/edit', label: 'Nano Banana 2.1', maxImages: 4 },
  { value: 'openai/gpt-image-2.5/sunburst/edit', label: 'GPT Image 2.5', maxImages: 4 },
  { value: 'blackforestlabs/flux-3/edit-image', label: 'Flux 3', maxImages: 1 },
  { value: 'xai/grok-imagine-image/v2.0/edit', label: 'Grok Imagine 2.0', maxImages: 4 },
  { value: 'ideogram/v4.5/edit', label: 'Ideogram V4.5', maxImages: 4 },
] as const;

export type EditModelId = (typeof EDIT_MODELS)[number]['value'];

export const DEFAULT_EDIT_MODEL: EditModelId = EDIT_MODELS[0].value;
