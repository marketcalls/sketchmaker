import { create } from 'zustand';
import { galleryApi } from '../api/gallery';
import type { GeneratedImage } from '../types';
import { getErrorMessage } from '@/utils/errors';

interface GalleryState {
  images: GeneratedImage[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  selectedImage: GeneratedImage | null;

  // Actions
  fetchGallery: () => Promise<void>;
  loadMore: () => Promise<void>;
  deleteImage: (imageId: number) => Promise<void>;
  selectImage: (image: GeneratedImage | null) => void;
  reset: () => void;
}

export const useGalleryStore = create<GalleryState>((set, get) => ({
  images: [],
  total: 0,
  page: 1,
  pageSize: 20,
  totalPages: 0,
  isLoading: false,
  isLoadingMore: false,
  hasMore: true,
  error: null,
  selectedImage: null,

  fetchGallery: async () => {
    const { pageSize } = get();
    set({ isLoading: true, error: null, page: 1, images: [] });

    try {
      const response = await galleryApi.getGallery(1, pageSize);
      set({
        images: response.images,
        total: response.total,
        page: 1,
        totalPages: response.totalPages,
        hasMore: response.page < response.totalPages,
        isLoading: false,
      });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to fetch gallery');
      set({ error: message, isLoading: false });
    }
  },

  loadMore: async () => {
    const { page, pageSize, isLoadingMore, hasMore, images } = get();
    if (isLoadingMore || !hasMore) return;

    const nextPage = page + 1;
    set({ isLoadingMore: true, error: null });

    try {
      const response = await galleryApi.getGallery(nextPage, pageSize);
      set({
        images: [...images, ...response.images],
        total: response.total,
        page: nextPage,
        totalPages: response.totalPages,
        hasMore: nextPage < response.totalPages,
        isLoadingMore: false,
      });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to load more images');
      set({ error: message, isLoadingMore: false });
    }
  },

  deleteImage: async (imageId) => {
    try {
      await galleryApi.deleteImage(imageId);
      set((state) => ({
        images: state.images.filter((img) => img.id !== imageId),
        total: state.total - 1,
        selectedImage: state.selectedImage?.id === imageId ? null : state.selectedImage,
      }));
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to delete image');
      set({ error: message });
      throw error;
    }
  },

  selectImage: (image) => set({ selectedImage: image }),

  reset: () => set({
    images: [],
    total: 0,
    page: 1,
    totalPages: 0,
    hasMore: true,
    error: null,
    selectedImage: null,
  }),
}));
