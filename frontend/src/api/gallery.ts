import apiClient from './client';
import type { GeneratedImage, MessageResponse } from '../types';

export interface GalleryResponse {
  images: GeneratedImage[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// Transform snake_case image response to camelCase
export function transformImage(data: Record<string, unknown>): GeneratedImage {
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
  };
}

export const galleryApi = {
  getGallery: async (page = 1, pageSize = 20): Promise<GalleryResponse> => {
    const response = await apiClient.get('/gallery', {
      params: { page, page_size: pageSize },
    });
    const data = response.data;
    return {
      images: data.images.map(transformImage),
      total: data.total,
      page: data.page,
      pageSize: data.page_size,
      totalPages: data.total_pages,
    };
  },

  getImage: async (imageId: number): Promise<GeneratedImage> => {
    const response = await apiClient.get(`/gallery/${imageId}`);
    return transformImage(response.data);
  },

  deleteImage: async (imageId: number): Promise<MessageResponse> => {
    const response = await apiClient.delete(`/gallery/${imageId}`);
    return response.data;
  },

  downloadImage: (imageId: number, format: string): string => {
    return `/api/gallery/${imageId}/download/${format}`;
  },
};
