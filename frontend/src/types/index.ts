// User types
export interface User {
  id: number;
  username: string;
  createdAt: string;
  selectedProviderId?: number;
  selectedModelId?: number;
}

// Image types
export interface GeneratedImage {
  id: number;
  filename: string;
  prompt: string;
  magicPrompt?: string;
  artStyle?: string;
  width?: number;
  height?: number;
  model?: string;
  seed?: number;
  rendering?: string;
  aspectRatio?: string;
  guidanceScale?: number;
  inferenceSteps?: number;
  createdAt: string;
  url: string;
  thumbnailUrl?: string;
  // The opt-in quality check (api/quality.ts), when one was asked for
  quality?: import('../api/quality').Quality | null;
}

// Video types
export interface GeneratedVideo {
  id: number;
  filename: string;
  thumbnailUrl?: string;
  url: string;
  sourceImageUrl?: string;
  motionReferenceUrl?: string;
  characterOrientation?: string;
  prompt?: string;
  // motion, story, subtitle or lipsync
  videoType?: string;
  durationSeconds?: number;
  width?: number;
  height?: number;
  fps?: number;
  model?: string;
  seed?: number;
  fileSizeBytes?: number;
  createdAt: string;
}

export interface VideoJob {
  jobId: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
  createdAt?: string;
  startedAt?: string;
}

// Training types
export interface Training {
  id?: string;
  trainingId: string;
  queueId?: string;
  triggerWord: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress?: number;
  logs?: string;
  configUrl?: string;
  weightsUrl?: string;
  createdAt: string;
  completedAt?: string;
  result?: Record<string, unknown>;
  modelName?: string;
}

// Alias for backwards compatibility
export type TrainingJob = Training;

// API response types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface MessageResponse {
  message: string;
  success: boolean;
}

export interface ErrorResponse {
  detail: string;
  errorCode?: string;
}
