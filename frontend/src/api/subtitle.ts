import apiClient from './client';

// Subtitle video response type
export interface SubtitleVideo {
  id: number;
  filename: string;
  thumbnailUrl?: string;
  url: string;
  videoType: string;
  transcript?: string;
  durationSeconds?: number;
  width?: number;
  height?: number;
  fps?: number;
  fileSizeBytes?: number;
  createdAt: string;
}

export interface SubtitleUploadResponse {
  url: string;
  filename: string;
  durationSeconds: number;
  estimatedUsd: number;
  fileSizeBytes: number;
  message: string;
}

export interface SubtitleGenerateRequest {
  videoUrl: string;
  fontColor?: string;
  strokeColor?: string;
  highlightColor?: string;
  backgroundColor?: string;
  position?: string;
  fontSize?: number;
  fontName?: string;
  fontWeight?: string;
  strokeWidth?: number;
  yOffset?: number;
  wordsPerSubtitle?: number;
  enableAnimation?: boolean;
  language?: string;
}

export interface SubtitleJobSubmitResponse {
  jobId: string;
  status: string;
  message: string;
  estimatedUsd: number;
}

export interface SubtitleJobStatusResponse {
  jobId: string;
  status: 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed';
  progress: number;
  logs?: string[];
  error?: string;
  createdAt?: string;
  startedAt?: string;
}

export interface SubtitleJobResultResponse {
  jobId: string;
  status: string;
  video: SubtitleVideo;
  transcript: string;
  completedAt?: string;
}

export interface SubtitleGalleryResponse {
  videos: SubtitleVideo[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// Transform snake_case video response to camelCase
function transformSubtitleVideo(data: Record<string, unknown>): SubtitleVideo {
  return {
    id: data.id as number,
    filename: data.filename as string,
    thumbnailUrl: data.thumbnail_url as string | undefined,
    url: data.url as string,
    videoType: data.video_type as string,
    transcript: data.transcript as string | undefined,
    durationSeconds: data.duration_seconds as number | undefined,
    width: data.width as number | undefined,
    height: data.height as number | undefined,
    fps: data.fps as number | undefined,
    fileSizeBytes: data.file_size_bytes as number | undefined,
    createdAt: data.created_at as string,
  };
}

export const subtitleApi = {
  // Upload a video for subtitle generation
  uploadVideo: async (file: File): Promise<SubtitleUploadResponse> => {
    const formData = new FormData();
    formData.append('video', file);

    const response = await apiClient.post('/subtitle/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      durationSeconds: data.duration_seconds as number,
      estimatedUsd: data.estimated_usd as number,
      fileSizeBytes: data.file_size_bytes as number,
      message: data.message as string,
    };
  },

  // Submit async subtitle generation job
  submitGenerateJob: async (data: SubtitleGenerateRequest): Promise<SubtitleJobSubmitResponse> => {
    const response = await apiClient.post('/subtitle/generate', {
      video_url: data.videoUrl,
      font_color: data.fontColor ?? 'white',
      stroke_color: data.strokeColor ?? 'black',
      highlight_color: data.highlightColor ?? null,
      background_color: data.backgroundColor ?? null,
      position: data.position ?? 'bottom',
      font_size: data.fontSize ?? 100,
      font_name: data.fontName ?? 'Montserrat',
      font_weight: data.fontWeight ?? 'bold',
      stroke_width: data.strokeWidth ?? 3,
      y_offset: data.yOffset ?? 75,
      words_per_subtitle: data.wordsPerSubtitle ?? 3,
      enable_animation: data.enableAnimation ?? true,
      language: data.language ?? 'en',
    });
    const responseData = response.data as Record<string, unknown>;
    return {
      jobId: responseData.job_id as string,
      status: responseData.status as string,
      message: responseData.message as string,
      estimatedUsd: responseData.estimated_usd as number,
    };
  },

  // Poll job status
  getJobStatus: async (jobId: string): Promise<SubtitleJobStatusResponse> => {
    const response = await apiClient.get(`/subtitle/status/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as 'pending' | 'in_progress' | 'processing' | 'ready' | 'completed' | 'failed',
      progress: data.progress as number,
      logs: data.logs as string[] | undefined,
      error: data.error as string | undefined,
      createdAt: data.created_at as string | undefined,
      startedAt: data.started_at as string | undefined,
    };
  },

  // Get job result (video with subtitles)
  getJobResult: async (jobId: string): Promise<SubtitleJobResultResponse> => {
    const response = await apiClient.get(`/subtitle/result/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as string,
      video: transformSubtitleVideo(data.video as Record<string, unknown>),
      transcript: data.transcript as string,
      completedAt: data.completed_at as string | undefined,
    };
  },

  // Get user's subtitled video gallery
  getGallery: async (page: number = 1, pageSize: number = 20): Promise<SubtitleGalleryResponse> => {
    const response = await apiClient.get('/subtitle/gallery', {
      params: { page, page_size: pageSize },
    });
    const data = response.data as Record<string, unknown>;
    return {
      videos: (data.videos as Record<string, unknown>[]).map(transformSubtitleVideo),
      total: data.total as number,
      page: data.page as number,
      pageSize: data.page_size as number,
      totalPages: data.total_pages as number,
    };
  },

  // Delete a subtitled video
  deleteVideo: async (videoId: number): Promise<void> => {
    await apiClient.delete(`/subtitle/${videoId}`);
  },

  // Download a subtitled video
  downloadVideo: async (videoId: number): Promise<{ downloadUrl: string; filename: string }> => {
    const response = await apiClient.get(`/subtitle/${videoId}/download`);
    const data = response.data as Record<string, unknown>;
    return {
      downloadUrl: data.download_url as string,
      filename: data.filename as string,
    };
  },
};
