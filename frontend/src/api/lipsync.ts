import apiClient from './client';
import { transformVideo, type VideoJobStatusResponse, type VideoJobResultResponse, type VideoGalleryResponse } from './video';

export type LipSyncResolution = '480p' | '768p' | '1080p' | '2k';

export interface LipSyncImageUpload {
  url: string;
  filename: string;
  fileSizeBytes: number;
  width: number;
  height: number;
  aspectRatio: number;
  // Set when the portrait comes from My Assets instead of an upload here.
  assetId?: number;
}

export interface LipSyncAudioUpload {
  url: string;
  filename: string;
  fileSizeBytes: number;
  // Measured by the server; the job is priced on it.
  durationSeconds: number;
  billableSeconds: number;
  // Set when the audio comes from My Assets (uploaded or a generated voice).
  assetId?: number;
}

export interface LipSyncGenerateRequest {
  imageUrl: string;
  audioUrl: string;
  imageAssetId?: number;
  audioAssetId?: number;
  resolution: LipSyncResolution;
  enableTranscription: boolean;
  // Portrait check first (one large, frontal face); a fail refuses the video
  faceCheck?: boolean;
}

export interface LipSyncJobSubmitResponse {
  jobId: string;
  status: string;
  estimatedUsd: number;
  message: string;
}

function multipart(field: string, file: File): FormData {
  const formData = new FormData();
  formData.append(field, file);
  return formData;
}

export const lipsyncApi = {
  uploadImage: async (file: File): Promise<LipSyncImageUpload> => {
    const response = await apiClient.post('/lip-sync/upload-image', multipart('image', file), {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      width: data.width as number,
      height: data.height as number,
      aspectRatio: data.aspect_ratio as number,
    };
  },

  uploadAudio: async (file: File): Promise<LipSyncAudioUpload> => {
    const response = await apiClient.post('/lip-sync/upload-audio', multipart('audio', file), {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    const data = response.data as Record<string, unknown>;
    return {
      url: data.url as string,
      filename: data.filename as string,
      fileSizeBytes: data.file_size_bytes as number,
      durationSeconds: data.duration_seconds as number,
      billableSeconds: data.billable_seconds as number,
    };
  },

  submit: async (req: LipSyncGenerateRequest): Promise<LipSyncJobSubmitResponse> => {
    const response = await apiClient.post('/lip-sync/generate', {
      image_url: req.imageAssetId ? undefined : req.imageUrl,
      audio_url: req.audioAssetId ? undefined : req.audioUrl,
      image_asset_id: req.imageAssetId,
      audio_asset_id: req.audioAssetId,
      resolution: req.resolution,
      enable_transcription: req.enableTranscription,
      face_check: req.faceCheck ?? false,
    });
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as string,
      estimatedUsd: data.estimated_usd as number,
      message: data.message as string,
    };
  },

  getStatus: async (jobId: string): Promise<VideoJobStatusResponse> => {
    const response = await apiClient.get(`/lip-sync/status/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as VideoJobStatusResponse['status'],
      progress: data.progress as number,
      logs: data.logs as string[] | undefined,
      error: data.error as string | undefined,
      createdAt: data.created_at as string | undefined,
      startedAt: data.started_at as string | undefined,
    };
  },

  getResult: async (jobId: string): Promise<VideoJobResultResponse> => {
    const response = await apiClient.get(`/lip-sync/result/${jobId}`);
    const data = response.data as Record<string, unknown>;
    return {
      jobId: data.job_id as string,
      status: data.status as string,
      video: transformVideo(data.video as Record<string, unknown>),
      completedAt: data.completed_at as string | undefined,
    };
  },

  getGallery: async (page: number = 1, pageSize: number = 12): Promise<VideoGalleryResponse> => {
    const response = await apiClient.get('/lip-sync/gallery', { params: { page, page_size: pageSize } });
    const data = response.data as Record<string, unknown>;
    return {
      videos: (data.videos as Record<string, unknown>[]).map(transformVideo),
      total: data.total as number,
      page: data.page as number,
      pageSize: data.page_size as number,
      totalPages: data.total_pages as number,
    };
  },

  retryJob: async (jobId: string): Promise<void> => {
    await apiClient.post(`/lip-sync/job/${jobId}/retry`);
  },
};
