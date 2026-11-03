import { create } from 'zustand';
import { generateApi } from '../api/generate';
import type { GeneratedImage } from '../types';
import { getErrorMessage } from '@/utils/errors';

// Helper to extract error message from API errors

interface ImageSettings {
  aspectRatio: string;
  resolution: string;
  numImages: number;
}

interface AdvancedSettings {
  guidanceScale: number;
  inferenceSteps: number;
  negativePrompt: string;
  seed: string;
}

// Settings for prompt enhancement
interface PromptEnhanceSettings {
  style: string;
  lighting: string;
  mood: string;
  composition: string;
  timeOfDay: string;
  weather: string;
  quality: string;
  cameraAngle: string;
  cameraDistance: string;
  cameraLens: string;
  colorPalette: string[];
}

// Default values for prompt enhance settings - use 'auto' for Radix Select compatibility
const defaultPromptEnhanceSettings: PromptEnhanceSettings = {
  style: 'auto',
  lighting: 'auto',
  mood: 'auto',
  composition: 'auto',
  timeOfDay: 'auto',
  weather: 'auto',
  quality: 'auto',
  cameraAngle: 'auto',
  cameraDistance: 'auto',
  cameraLens: 'auto',
  colorPalette: [],
};

// Helper to check if a value should be sent to API (not 'auto' or empty)
const isValidSetting = (value: string) => value && value !== 'auto';

// Request fields each /generate model takes (MODEL_CONFIG supports and omit
// in backend/app/clients/fal_client.py). None takes guidance or a negative
// prompt; only Z-Image takes inference steps (1 to 8).
const STEPS_MODELS: Record<string, { max: number }> = {
  'fal-ai/z-image/turbo/lora': { max: 8 },
};
const NO_SEED_MODELS = new Set([
  'openai/gpt-image-2.5/sunburst/text-to-image',
  'blackforestlabs/flux-3/text-to-image',
  'microsoft/mai-image-2.5',
  'xai/grok-imagine-image/v2.0/text-to-image',
]);

export function modelSettings(model: string): { steps: { max: number } | null; seed: boolean } {
  return { steps: STEPS_MODELS[model] ?? null, seed: !NO_SEED_MODELS.has(model) };
}

// Job tracking state
interface GenerationJob {
  jobId: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
}

interface GenerationState {
  isGenerating: boolean;
  currentPrompt: string;
  originalPrompt: string | null; // Original prompt before AI enhancement
  enhancedPrompt: string | null; // AI-enhanced prompt (editable)
  selectedPromptType: 'original' | 'enhanced'; // Which prompt to use for generation
  isEnhanced: boolean; // Whether enhancement has been done
  generatedImages: GeneratedImage[];
  selectedModel: string;
  selectedStyle: string;
  imageSettings: ImageSettings;
  advancedSettings: AdvancedSettings;
  error: string | null;
  loraUrl: string | null;
  loraScale: number;
  promptEnhanceSettings: PromptEnhanceSettings;
  // Async job tracking
  currentJob: GenerationJob | null;
  generationProgress: number;
  generationStatus: string;
  // "Use for": a platform format (image_prompt_profiles.PURPOSES), or 'none'
  purpose: string;
  // Directions: Magic Prompt writes one prompt per image along a named axis
  directionsEnabled: boolean;
  directionPrompts: string[] | null;
  directionAxis: string | null;
  // A sentence for people about the last result (safety filter, partial runs)
  notice: string | null;
  // Opt-in quality check (api/quality.ts), charged per image, and the
  // checkable lines Magic Prompt wrote for it
  qualityCheck: boolean;
  checkLines: string[] | null;

  // Actions
  setPrompt: (prompt: string, isManual?: boolean) => void;
  setModel: (model: string) => void;
  setStyle: (style: string) => void;
  setImageSettings: (settings: Partial<ImageSettings>) => void;
  setAdvancedSettings: (settings: Partial<AdvancedSettings>) => void;
  setPromptEnhanceSettings: (settings: Partial<PromptEnhanceSettings>) => void;
  resetPromptEnhanceSettings: () => void;
  setLoraUrl: (url: string | null) => void;
  setLoraScale: (scale: number) => void;
  setPurpose: (purpose: string) => void;
  setDirectionsEnabled: (enabled: boolean) => void;
  setEnhancedPrompt: (prompt: string) => void;
  setQualityCheck: (on: boolean) => void;
  // A fixed image (a paid "Fix this" edit) joins the results
  addImage: (image: GeneratedImage) => void;
  setSelectedPromptType: (type: 'original' | 'enhanced') => void;
  resetEnhancement: () => void;
  generateImage: () => Promise<void>;
  generatePrompt: (topic: string) => Promise<string>;
  clearError: () => void;
  clearImages: () => void;
  cancelGeneration: () => void;
  resumePendingJobs: () => Promise<void>;
}

export const useGenerationStore = create<GenerationState>((set, get) => ({
  isGenerating: false,
  currentPrompt: '',
  originalPrompt: null,
  enhancedPrompt: null,
  selectedPromptType: 'enhanced',
  isEnhanced: false,
  generatedImages: [],
  selectedModel: 'blackforestlabs/flux-3/klein/text-to-image',
  selectedStyle: 'none',
  imageSettings: {
    aspectRatio: '16:9',
    resolution: '1k',
    numImages: 1,
  },
  advancedSettings: {
    guidanceScale: 2.5,
    inferenceSteps: 8,
    negativePrompt: '',
    seed: '',
  },
  error: null,
  loraUrl: null,
  loraScale: 1.0,
  promptEnhanceSettings: { ...defaultPromptEnhanceSettings },
  currentJob: null,
  generationProgress: 0,
  generationStatus: '',
  purpose: 'none',
  directionsEnabled: false,
  directionPrompts: null,
  directionAxis: null,
  notice: null,
  qualityCheck: false,
  checkLines: null,

  // When user manually types, reset enhancement state
  setPrompt: (prompt, isManual = true) => set({
    currentPrompt: prompt,
    // If manually typing, reset the enhancement state
    ...(isManual ? {
      originalPrompt: null,
      enhancedPrompt: null,
      isEnhanced: false,
      selectedPromptType: 'enhanced' as const,
      directionPrompts: null,
      directionAxis: null,
      checkLines: null,
    } : {}),
  }),
  setModel: (model) => set({ selectedModel: model }),
  setStyle: (style) => set({ selectedStyle: style }),
  setImageSettings: (settings) =>
    set((state) => ({
      imageSettings: { ...state.imageSettings, ...settings },
    })),
  setAdvancedSettings: (settings) =>
    set((state) => ({
      advancedSettings: { ...state.advancedSettings, ...settings },
    })),
  setPromptEnhanceSettings: (settings) =>
    set((state) => ({
      promptEnhanceSettings: { ...state.promptEnhanceSettings, ...settings },
    })),
  resetPromptEnhanceSettings: () =>
    set({ promptEnhanceSettings: { ...defaultPromptEnhanceSettings } }),
  setLoraUrl: (url) => set({ loraUrl: url }),
  setLoraScale: (scale) => set({ loraScale: scale }),
  setPurpose: (purpose) => set({ purpose }),
  setDirectionsEnabled: (enabled) => set({ directionsEnabled: enabled }),
  setEnhancedPrompt: (prompt) => set({ enhancedPrompt: prompt }),
  setQualityCheck: (on) => set({ qualityCheck: on }),
  addImage: (image) => set((state) => ({ generatedImages: [image, ...state.generatedImages] })),
  setSelectedPromptType: (type) => set({ selectedPromptType: type }),
  resetEnhancement: () => set({
    originalPrompt: null,
    enhancedPrompt: null,
    isEnhanced: false,
    selectedPromptType: 'enhanced',
    directionPrompts: null,
    directionAxis: null,
    checkLines: null,
  }),

  generateImage: async () => {
    const { currentPrompt, originalPrompt, enhancedPrompt, selectedPromptType, isEnhanced, selectedModel, selectedStyle, imageSettings, advancedSettings, loraUrl, loraScale, directionPrompts, qualityCheck, checkLines } = get();

    // Determine which prompt to use based on selection
    let promptToUse = currentPrompt;
    let originalPromptToSend = originalPrompt;

    if (isEnhanced) {
      if (selectedPromptType === 'enhanced' && enhancedPrompt) {
        promptToUse = enhancedPrompt;
        originalPromptToSend = originalPrompt;
      } else if (selectedPromptType === 'original' && originalPrompt) {
        promptToUse = originalPrompt;
        originalPromptToSend = null; // No enhancement was used
      }
    }
    // Directions: one job of one image per prompt instead of one prompt for
    // every image. Same images, same price.
    const useDirections = isEnhanced && selectedPromptType === 'enhanced' && !!directionPrompts && directionPrompts.length > 1;
    const prompts = useDirections ? directionPrompts! : [promptToUse];
    const caps = modelSettings(selectedModel);

    set({
      isGenerating: true,
      error: null,
      notice: null,
      generationProgress: 0,
      generationStatus: 'Submitting job...',
      currentJob: null,
    });

    const jobIds: string[] = [];
    let submitError: string | null = null;
    for (const prompt of prompts) {
      try {
        // Only the settings this model takes are sent.
        const job = await generateApi.submitGenerateJob({
          prompt,
          originalPrompt: originalPromptToSend || undefined,
          model: selectedModel,
          artStyle: selectedStyle,
          aspectRatio: imageSettings.aspectRatio,
          resolution: imageSettings.resolution,
          numImages: useDirections ? 1 : imageSettings.numImages,
          loraUrl: loraUrl || undefined,
          loraScale,
          inferenceSteps: caps.steps ? advancedSettings.inferenceSteps : undefined,
          seed: caps.seed && advancedSettings.seed ? parseInt(advancedSettings.seed) : undefined,
          qualityCheck,
          // The Magic Prompt lines describe the enhanced prompt only.
          checkLines: isEnhanced && selectedPromptType === 'enhanced' && !useDirections ? checkLines ?? undefined : undefined,
        });
        jobIds.push(job.jobId);
      } catch (error: unknown) {
        submitError = getErrorMessage(error);
        break;
      }
    }

    if (jobIds.length === 0) {
      set({
        error: submitError,
        isGenerating: false,
        currentJob: null,
        generationProgress: 0,
        generationStatus: '',
      });
      throw new Error(submitError || 'Generation failed');
    }

    set({
      currentJob: { jobId: jobIds[0], status: 'pending', progress: 0 },
      generationStatus: 'Queued...',
      generationProgress: 10,
    });
    void pollJobs(jobIds, set, get, submitError);
  },

  generatePrompt: async (topic) => {
    try {
      const { promptEnhanceSettings, selectedStyle, selectedModel, imageSettings, loraUrl, purpose, directionsEnabled, advancedSettings } = get();

      // Build advanced settings from promptEnhanceSettings (excluding 'auto' values)
      const hasAdvancedSettings = Object.entries(promptEnhanceSettings).some(
        ([key, value]) => key !== 'colorPalette'
          ? isValidSetting(value as string)
          : (value as string[]).length > 0
      );

      const hasCameraSettings = isValidSetting(promptEnhanceSettings.cameraAngle) ||
        isValidSetting(promptEnhanceSettings.cameraDistance) ||
        isValidSetting(promptEnhanceSettings.cameraLens);

      const directions = directionsEnabled && imageSettings.numImages > 1 ? Math.min(imageSettings.numImages, 4) : 0;

      const response = await generateApi.generatePrompt({
        topic,
        model: selectedModel,
        aspectRatio: imageSettings.aspectRatio,
        lora: !!loraUrl,
        purpose: purpose !== 'none' ? purpose : undefined,
        // No /generate model takes a negative prompt; Magic Prompt rewrites
        // it as positive description instead.
        avoid: advancedSettings.negativePrompt.trim() || undefined,
        directions,
        style: selectedStyle !== 'none' ? selectedStyle : undefined,
        advanced: hasAdvancedSettings ? {
          style: isValidSetting(promptEnhanceSettings.style) ? promptEnhanceSettings.style : undefined,
          colorPalette: promptEnhanceSettings.colorPalette.length > 0 ? promptEnhanceSettings.colorPalette : undefined,
          lighting: isValidSetting(promptEnhanceSettings.lighting) ? promptEnhanceSettings.lighting : undefined,
          mood: isValidSetting(promptEnhanceSettings.mood) ? promptEnhanceSettings.mood : undefined,
          composition: isValidSetting(promptEnhanceSettings.composition) ? promptEnhanceSettings.composition : undefined,
          timeOfDay: isValidSetting(promptEnhanceSettings.timeOfDay) ? promptEnhanceSettings.timeOfDay : undefined,
          weather: isValidSetting(promptEnhanceSettings.weather) ? promptEnhanceSettings.weather : undefined,
          quality: isValidSetting(promptEnhanceSettings.quality) ? promptEnhanceSettings.quality : undefined,
          camera: hasCameraSettings ? {
            angle: isValidSetting(promptEnhanceSettings.cameraAngle) ? promptEnhanceSettings.cameraAngle : undefined,
            distance: isValidSetting(promptEnhanceSettings.cameraDistance) ? promptEnhanceSettings.cameraDistance : undefined,
            lens: isValidSetting(promptEnhanceSettings.cameraLens) ? promptEnhanceSettings.cameraLens : undefined,
          } : undefined,
        } : undefined,
      });

      const prompts = directions && response.prompts && response.prompts.length > 1 ? response.prompts : null;
      // Store original prompt and enhanced prompt separately
      set({
        originalPrompt: topic, // Save the original user prompt
        enhancedPrompt: response.prompt, // Save the AI-enhanced prompt
        isEnhanced: true, // Mark as enhanced
        selectedPromptType: 'enhanced', // Default to using enhanced prompt
        directionPrompts: prompts,
        directionAxis: prompts ? response.axis || null : null,
        checkLines: response.checks && response.checks.length > 0 ? response.checks : null,
      });
      return response.prompt;
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      set({ error: message });
      throw error;
    }
  },

  clearError: () => set({ error: null, notice: null }),
  clearImages: () => set({ generatedImages: [] }),
  cancelGeneration: () => set({
    isGenerating: false,
    currentJob: null,
    generationProgress: 0,
    generationStatus: '',
  }),

  resumePendingJobs: async () => {
    try {
      // Check for pending jobs
      const pendingJobs = await generateApi.getPendingJobs();

      if (pendingJobs.length === 0) {
        return;
      }

      // Resume the most recent pending job
      const job = pendingJobs[0];

      set({
        isGenerating: true,
        generationProgress: 10,
        generationStatus: 'Resuming job...',
        currentJob: {
          jobId: job.jobId,
          status: job.status as 'pending' | 'in_progress' | 'completed' | 'failed',
          progress: job.progress,
        },
      });

      void pollJobs([job.jobId], set, get, null);
    } catch (error) {
      console.error('Failed to resume pending jobs:', error);
    }
  },
}));

type SetState = (partial: Partial<GenerationState> | ((state: GenerationState) => Partial<GenerationState>)) => void;

// Poll the submitted jobs until each has finished or failed, then add every
// image that arrived (newest first) and report what did not.
async function pollJobs(jobIds: string[], set: SetState, get: () => GenerationState, submitError: string | null) {
  const maxAttempts = 120; // 2 minutes
  const pending = new Set(jobIds);
  const running = new Set<string>();
  const images: GeneratedImage[] = [];
  const notices: string[] = [];
  const errors: string[] = submitError ? [submitError] : [];

  for (let attempt = 0; pending.size > 0; attempt++) {
    if (!get().isGenerating) {
      return; // Cancelled
    }
    for (const jobId of [...pending]) {
      try {
        const status = await generateApi.getJobStatus(jobId);
        if (status.status === 'completed') {
          const result = await generateApi.getJobResult(jobId);
          images.push(...result.images);
          if (result.notice) notices.push(result.notice);
          pending.delete(jobId);
        } else if (status.status === 'failed') {
          errors.push(status.error || 'Generation failed');
          pending.delete(jobId);
        } else if (status.status === 'in_progress') {
          running.add(jobId);
        }
      } catch (error) {
        errors.push(getErrorMessage(error));
        pending.delete(jobId);
      }
    }
    if (pending.size === 0) break;

    const done = jobIds.length - pending.size;
    const anyRunning = [...pending].some((id) => running.has(id));
    set({
      generationProgress: Math.round(10 + (anyRunning ? 40 : 0) + (40 * done) / jobIds.length),
      generationStatus: anyRunning ? 'Generating...' : 'Queued...',
    });

    if (attempt + 1 >= maxAttempts) {
      errors.push('Generation timed out');
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  if (!get().isGenerating) {
    return; // Cancelled while the last results were fetched
  }

  if (images.length === 0) {
    set({
      error: errors[0] || 'Generation failed',
      isGenerating: false,
      currentJob: null,
      generationProgress: 0,
      generationStatus: '',
    });
    return;
  }

  // Some jobs of a Directions run can fail while others deliver.
  const partial = errors.length > 0 ? `Some images could not be made: ${errors[0]}` : null;
  set((state) => ({
    generatedImages: [...images, ...state.generatedImages],
    isGenerating: false,
    notice: [...notices, ...(partial ? [partial] : [])].join(' ') || null,
    // Reset all enhancement state after successful generation
    originalPrompt: null,
    enhancedPrompt: null,
    isEnhanced: false,
    selectedPromptType: 'enhanced',
    directionPrompts: null,
    currentJob: null,
    generationProgress: 100,
    generationStatus: 'Complete!',
  }));
}
