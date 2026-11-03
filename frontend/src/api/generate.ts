import apiClient from './client';
import type { GeneratedImage } from '../types';

export interface CameraSettings {
  angle?: string;
  distance?: string;
  lens?: string;
}

export interface AdvancedPromptSettings {
  style?: string;
  colorPalette?: string[];
  lighting?: string;
  mood?: string;
  composition?: string;
  camera?: CameraSettings;
  timeOfDay?: string;
  weather?: string;
  quality?: string;
}

export interface GeneratePromptRequest {
  topic: string;
  style?: string;
  advanced?: AdvancedPromptSettings;
  // The image model and frame the prompt is written for.
  model?: string;
  aspectRatio?: string;
  lora?: boolean;
  // What the image is for (a PURPOSES id), text to keep out of the image
  // (written as positive description), and Directions: 2 to 4 prompts that
  // differ along one named axis.
  purpose?: string;
  avoid?: string;
  directions?: number;
}

export interface GeneratePromptResponse {
  prompt: string;
  enhanced: boolean;
  settings_applied?: Record<string, unknown>;
  prompts?: string[];
  axis?: string;
  // Checkable rubric lines for the opt-in quality check (not with Directions)
  checks?: string[];
}

export interface GenerateImageRequest {
  prompt: string;
  originalPrompt?: string; // Original prompt before AI enhancement
  model?: string;
  artStyle?: string;
  // Unified size parameters
  aspectRatio?: string;
  resolution?: string;
  numImages?: number;
  loraUrl?: string;
  loraScale?: number;
  // Advanced settings
  guidanceScale?: number;
  inferenceSteps?: number;
  negativePrompt?: string;
  seed?: number;
  // Opt-in quality check, charged per image at the qa:vision-check price
  qualityCheck?: boolean;
  checkLines?: string[];
}

// Async generation response types
export interface GenerateJobSubmitResponse {
  jobId: string;
  status: string;
  message: string;
}

export interface GenerateJobStatusResponse {
  jobId: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
  createdAt?: string;
  startedAt?: string;
}

export interface GenerateJobResultResponse {
  jobId: string;
  status: string;
  images: GeneratedImage[];
  completedAt?: string;
  // A sentence for people when the safety filter blocked some images
  notice?: string;
}

// Transform snake_case image response to camelCase
function transformImage(data: Record<string, unknown>): GeneratedImage {
  return {
    id: data.id as number,
    filename: data.filename as string,
    prompt: data.prompt as string,
    magicPrompt: data.magic_prompt as string | undefined,
    artStyle: data.art_style as string | undefined,
    width: data.width as number | undefined,
    height: data.height as number | undefined,
    model: data.model as string | undefined,
    seed: data.seed as number | undefined,
    rendering: data.rendering as string | undefined,
    aspectRatio: data.aspect_ratio as string | undefined,
    guidanceScale: data.guidance_scale as number | undefined,
    inferenceSteps: data.inference_steps as number | undefined,
    createdAt: data.created_at as string,
    url: data.url as string,
    thumbnailUrl: data.thumbnail_url as string | undefined,
    quality: (data.quality as GeneratedImage['quality']) ?? null,
  };
}

export interface PendingJob {
  jobId: string;
  status: string;
  progress: number;
  model: string;
  createdAt: string | null;
}

export const generateApi = {
  // Get pending jobs for current user
  getPendingJobs: async (): Promise<PendingJob[]> => {
    const response = await apiClient.get('/generate/jobs/pending');
    return (response.data as Array<Record<string, unknown>>).map(job => ({
      jobId: job.job_id as string,
      status: job.status as string,
      progress: job.progress as number,
      model: job.model as string,
      createdAt: job.created_at as string | null,
    }));
  },

  generatePrompt: async (data: GeneratePromptRequest): Promise<GeneratePromptResponse> => {
    // Transform camelCase to snake_case for backend
    const payload: Record<string, unknown> = {
      topic: data.topic,
      style: data.style,
      model: data.model,
      aspect_ratio: data.aspectRatio,
      lora: data.lora ?? false,
      purpose: data.purpose,
      avoid: data.avoid || undefined,
      directions: data.directions ?? 0,
    };

    if (data.advanced) {
      payload.advanced = {
        style: data.advanced.style,
        color_palette: data.advanced.colorPalette,
        lighting: data.advanced.lighting,
        mood: data.advanced.mood,
        composition: data.advanced.composition,
        time_of_day: data.advanced.timeOfDay,
        weather: data.advanced.weather,
        quality: data.advanced.quality,
        camera: data.advanced.camera ? {
          angle: data.advanced.camera.angle,
          distance: data.advanced.camera.distance,
          lens: data.advanced.camera.lens,
        } : undefined,
      };
    }

    const response = await apiClient.post('/generate/prompt', payload);
    return response.data;
  },

  // Submit async generation job
  submitGenerateJob: async (data: GenerateImageRequest): Promise<GenerateJobSubmitResponse> => {
    const response = await apiClient.post('/generate/image', {
      prompt: data.prompt,
      original_prompt: data.originalPrompt,
      model: data.model,
      art_style: data.artStyle,
      aspect_ratio: data.aspectRatio,
      resolution: data.resolution,
      num_images: data.numImages,
      lora_url: data.loraUrl,
      lora_scale: data.loraScale,
      guidance_scale: data.guidanceScale,
      inference_steps: data.inferenceSteps,
      negative_prompt: data.negativePrompt,
      seed: data.seed,
      quality_check: data.qualityCheck ?? false,
      check_lines: data.qualityCheck && data.checkLines?.length ? data.checkLines.slice(0, 6) : undefined,
    });
    const data_response = response.data as Record<string, unknown>;
    return {
      jobId: data_response.job_id as string,
      status: data_response.status as string,
      message: data_response.message as string,
    };
  },

  // Poll job status
  getJobStatus: async (jobId: string): Promise<GenerateJobStatusResponse> => {
    const response = await apiClient.get(`/generate/status/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as 'pending' | 'in_progress' | 'completed' | 'failed',
      progress: data.progress as number,
      logs: data.logs as string[] | undefined,
      error: data.error as string | undefined,
      createdAt: data.created_at as string | undefined,
      startedAt: data.started_at as string | undefined,
    };
  },

  // Get job result (images)
  getJobResult: async (jobId: string): Promise<GenerateJobResultResponse> => {
    const response = await apiClient.get(`/generate/result/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as string,
      images: (data.images as Record<string, unknown>[]).map(transformImage),
      completedAt: data.completed_at as string | undefined,
      notice: (data.notice as string | null) || undefined,
    };
  },

  // One image at a platform's exact pixels (YouTube 1280x720, LinkedIn
  // 1200x627), cropped and resized on the server.
  exportImage: async (imageId: number, purpose: string): Promise<Blob> => {
    const response = await apiClient.get(`/generate/export/${imageId}`, {
      params: { purpose },
      responseType: 'blob',
    });
    return response.data as Blob;
  },

  // Edit one of the user's images with an instruction (Ideogram V4.5,
  // precise mode). The result is a new image; the source is left as it was.
  editImage: async (imageId: number, instruction: string): Promise<GeneratedImage> => {
    // An edit takes up to a minute; the default client timeout is shorter.
    const response = await apiClient.post(`/image-edit/${imageId}`, { instruction }, { timeout: 180000 });
    return transformImage(response.data as Record<string, unknown>);
  },

  // Legacy sync method - now calls async under the hood
  generateImage: async (data: GenerateImageRequest): Promise<GeneratedImage[]> => {
    // Submit job
    const job = await generateApi.submitGenerateJob(data);

    // Poll for completion
    const maxAttempts = 120; // 2 minutes at 1 second intervals
    let attempts = 0;

    while (attempts < maxAttempts) {
      const status = await generateApi.getJobStatus(job.jobId);

      if (status.status === 'completed') {
        const result = await generateApi.getJobResult(job.jobId);
        return result.images;
      }

      if (status.status === 'failed') {
        throw new Error(status.error || 'Generation failed');
      }

      // Wait 1 second before next poll
      await new Promise(resolve => setTimeout(resolve, 1000));
      attempts++;
    }

    throw new Error('Generation timed out');
  },
};
