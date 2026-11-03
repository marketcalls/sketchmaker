import apiClient from './client';
import type { GeneratedVideo } from '../types';

export type MotionModelTier = 'v3-standard' | 'v3-pro' | 'v2.6';

export interface VideoGenerateRequest {
  sourceImage: string;  // Base64 data URL or URL
  motionReference: string;  // URL of the motion reference video
  characterOrientation?: 'video' | 'image';
  // Kling tier; the server defaults to V3 Standard.
  modelTier?: MotionModelTier;
  // Optional scene description (max 2000 characters).
  prompt?: string;
  // Carry the reference video's sound through (server default true).
  keepOriginalSound?: boolean;
  // Face lock: URL from uploadFaceImage. V3 tiers with 'video' orientation only.
  faceImageUrl?: string | null;
  motionReferenceAssetId?: number | null;
  faceAssetId?: number | null;
}

export type RecastResolution = '768p' | '1080p';

export interface RecastRequest {
  videoUrl?: string | null;
  videoAssetId?: number | null;
  // One photo per person, left to right (#Image1 first).
  references: { url: string; assetId?: number }[];
  resolution: RecastResolution;
  prompt?: string;
  enhanceRealism: boolean;
}

export interface FaceUploadResponse {
  url: string;
  filename: string;
  fileSizeBytes: number;
  width: number;
  height: number;
}

export interface VideoJobSubmitResponse {
  jobId: string;
  status: string;
  message: string;
}

export interface VideoJobStatusResponse {
  jobId: string;
  status: 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
  createdAt?: string;
  startedAt?: string;
}

export interface VideoJobResultResponse {
  jobId: string;
  status: string;
  video: GeneratedVideo;
  completedAt?: string;
}

export interface VideoUploadResponse {
  url: string;
  filename: string;
  fileSizeBytes: number;
  // Length measured by the server (motion reference uploads only), or null.
  durationSeconds?: number | null;
  message: string;
}

export interface VideoGalleryResponse {
  videos: GeneratedVideo[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// Transform snake_case video response to camelCase
export function transformVideo(data: Record<string, unknown>): GeneratedVideo {
  return {
    id: data.id as number,
    filename: data.filename as string,
    thumbnailUrl: data.thumbnail_url as string | undefined,
    url: data.url as string,
    sourceImageUrl: data.source_image_url as string | undefined,
    motionReferenceUrl: data.motion_reference_url as string | undefined,
    characterOrientation: data.character_orientation as string | undefined,
    prompt: data.prompt as string | undefined,
    videoType: data.video_type as string | undefined,
    durationSeconds: data.duration_seconds as number | undefined,
    width: data.width as number | undefined,
    height: data.height as number | undefined,
    fps: data.fps as number | undefined,
    model: data.model as string | undefined,
    seed: data.seed as number | undefined,
    fileSizeBytes: data.file_size_bytes as number | undefined,
    createdAt: data.created_at as string,
  };
}

export const videoApi = {
  // Upload a source image for video generation
  // FAL's Kling Video API requires hosted URLs, not base64 data URLs
  uploadSourceImage: async (file: File): Promise<VideoUploadResponse> => {
    const formData = new FormData();
    formData.append('image', file);

    const response = await apiClient.post('/video/upload-image', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      message: data.message as string,
    };
  },

  // Use an image from My Assets as the character image (fitted to fal's limits when needed)
  characterFromAsset: async (assetId: number): Promise<VideoUploadResponse> => {
    const response = await apiClient.post(`/video/asset-image/${assetId}`);
    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      message: data.message as string,
    };
  },

  // Upload a face for Kling V3 face lock (min 300x300, aspect 0.4 to 2.5, max 20 MB)
  uploadFaceImage: async (file: File): Promise<FaceUploadResponse> => {
    const formData = new FormData();
    formData.append('image', file);

    const response = await apiClient.post('/video/upload-face', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      width: data.width as number,
      height: data.height as number,
    };
  },

  // Upload a motion reference video
  uploadVideo: async (file: File): Promise<VideoUploadResponse> => {
    const formData = new FormData();
    formData.append('video', file);

    const response = await apiClient.post('/video/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      durationSeconds: (data.duration_seconds as number | null | undefined) ?? null,
      message: data.message as string,
    };
  },

  // Submit async video generation job
  submitGenerateJob: async (data: VideoGenerateRequest): Promise<VideoJobSubmitResponse> => {
    const response = await apiClient.post('/video/generate', {
      source_image: data.sourceImage,
      motion_reference: data.motionReferenceAssetId ? null : data.motionReference,
      motion_reference_asset_id: data.motionReferenceAssetId ?? null,
      face_asset_id: data.faceAssetId ?? null,
      character_orientation: data.characterOrientation || 'video',
      model_tier: data.modelTier || 'v3-standard',
      prompt: data.prompt?.trim() ? data.prompt.trim() : null,
      keep_original_sound: data.keepOriginalSound ?? true,
      face_image_url: data.faceAssetId ? null : data.faceImageUrl || null,
    });
    const responseData = response.data as Record<string, unknown>;
    return {
      jobId: responseData.job_id as string,
      status: responseData.status as string,
      message: responseData.message as string,
    };
  },

  // Multi-character motion transfer (MiniMax H3 Max Recast). Runs as a Motion
  // Control job: poll getJobStatus, then getJobResult.
  submitRecast: async (data: RecastRequest): Promise<VideoJobSubmitResponse> => {
    const response = await apiClient.post('/video/recast', {
      video_url: data.videoAssetId ? null : data.videoUrl ?? null,
      video_asset_id: data.videoAssetId ?? null,
      references: data.references.map((r) => (r.assetId ? { asset_id: r.assetId } : { image_url: r.url })),
      resolution: data.resolution,
      prompt: data.prompt?.trim() ? data.prompt.trim() : null,
      enhance_realism: data.enhanceRealism,
    });
    const responseData = response.data as Record<string, unknown>;
    return {
      jobId: responseData.job_id as string,
      status: responseData.status as string,
      message: responseData.message as string,
    };
  },

  // Poll job status
  getJobStatus: async (jobId: string): Promise<VideoJobStatusResponse> => {
    const response = await apiClient.get(`/video/status/${jobId}`);
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

  // Get job result (video)
  getJobResult: async (jobId: string): Promise<VideoJobResultResponse> => {
    const response = await apiClient.get(`/video/result/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as string,
      video: transformVideo(data.video as Record<string, unknown>),
      completedAt: data.completed_at as string | undefined,
    };
  },

  // Get user's video gallery
  getGallery: async (page: number = 1, pageSize: number = 20): Promise<VideoGalleryResponse> => {
    const response = await apiClient.get('/video/gallery', {
      params: { page, page_size: pageSize },
    });
    const data = response.data as Record<string, unknown>;
    return {
      videos: (data.videos as Record<string, unknown>[]).map(transformVideo),
      total: data.total as number,
      page: data.page as number,
      pageSize: data.page_size as number,
      totalPages: data.total_pages as number,
    };
  },

  // Get specific video
  getVideo: async (videoId: number): Promise<GeneratedVideo> => {
    const response = await apiClient.get(`/video/${videoId}`);
    return transformVideo(response.data as Record<string, unknown>);
  },

  // Delete a video
  deleteVideo: async (videoId: number): Promise<void> => {
    await apiClient.delete(`/video/${videoId}`);
  },

  // Retry a stuck/failed video job
  retryJob: async (jobId: string): Promise<{ message: string; job_id: string; status: string }> => {
    const response = await apiClient.post(`/video/job/${jobId}/retry`);
    return response.data as { message: string; job_id: string; status: string };
  },

  // Download a video
  downloadVideo: async (videoId: number, filename?: string): Promise<void> => {
    const response = await apiClient.get(`/video/${videoId}/download`, {
      responseType: 'blob',
    });
    const blob = new Blob([response.data as BlobPart], { type: 'video/mp4' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `video-${videoId}.mp4`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },
};
