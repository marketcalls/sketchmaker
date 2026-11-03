import { create } from 'zustand';
import { apiClient } from '@/api/client';
import { videoApi } from '@/api/video';
import { getErrorMessage } from '@/utils/errors';

export interface Job {
  jobId: string;
  jobType: 'image' | 'video' | 'story' | 'subtitle' | 'lipsync';
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number;
  prompt?: string;
  error?: string;
  thumbnailUrl?: string;
  resultId?: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

interface JobsState {
  jobs: Job[];
  total: number;
  pendingCount: number;
  inProgressCount: number;
  isLoading: boolean;
  error: string | null;
  filter: 'all' | 'pending' | 'completed' | 'failed';
  typeFilter: 'all' | 'image' | 'video' | 'story' | 'subtitle' | 'lipsync';

  // Actions
  fetchJobs: (force?: boolean) => Promise<void>;
  setFilter: (filter: 'all' | 'pending' | 'completed' | 'failed') => void;
  setTypeFilter: (filter: 'all' | 'image' | 'video' | 'story' | 'subtitle' | 'lipsync') => void;
  // Only these job types have a retry route.
  retryJob: (jobId: string, jobType: 'video' | 'lipsync') => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
  reset: () => void;
}

let pollInterval: ReturnType<typeof setInterval> | null = null;

export const useJobsStore = create<JobsState>((set, get) => ({
  jobs: [],
  total: 0,
  pendingCount: 0,
  inProgressCount: 0,
  isLoading: false,
  error: null,
  filter: 'all',
  typeFilter: 'all',

  fetchJobs: async (force = false) => {
    const { filter, typeFilter, isLoading } = get();
    if (isLoading && !force) return;

    set({ isLoading: true, error: null });

    try {
      const params: Record<string, string> = { days: '7' };
      if (filter !== 'all') {
        params.status = filter;
      }
      if (typeFilter !== 'all') {
        params.job_type = typeFilter;
      }

      const response = await apiClient.get('/jobs', { params });
      const data = response.data as {
        jobs: Array<Record<string, unknown>>;
        total: number;
        pending_count: number;
        in_progress_count: number;
      };

      set({
        jobs: data.jobs.map((job) => ({
          jobId: job.job_id as string,
          jobType: job.job_type as 'image' | 'video' | 'story' | 'subtitle' | 'lipsync',
          status: job.status as Job['status'],
          progress: job.progress as number,
          prompt: job.prompt as string | undefined,
          error: job.error as string | undefined,
          thumbnailUrl: job.thumbnail_url as string | undefined,
          resultId: job.result_id as number | undefined,
          createdAt: job.created_at as string,
          startedAt: job.started_at as string | undefined,
          completedAt: job.completed_at as string | undefined,
        })),
        total: data.total,
        pendingCount: data.pending_count,
        inProgressCount: data.in_progress_count,
        isLoading: false,
      });
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to fetch jobs');
      set({ error: message, isLoading: false });
    }
  },

  setFilter: (filter) => {
    set({ filter });
    get().fetchJobs(true);
  },

  setTypeFilter: (typeFilter) => {
    set({ typeFilter });
    get().fetchJobs(true);
  },

  retryJob: async (jobId, jobType) => {
    try {
      if (jobType === 'video') {
        await videoApi.retryJob(jobId);
      } else {
        await apiClient.post(`/lip-sync/job/${jobId}/retry`);
      }
      // Update local state to show job as in_progress
      set((state) => ({
        jobs: state.jobs.map((job) =>
          job.jobId === jobId
            ? { ...job, status: 'in_progress' as const, progress: 50, error: undefined }
            : job
        ),
      }));
      // Refresh after a short delay to get updated data
      setTimeout(() => get().fetchJobs(true), 2000);
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to retry job');
      set({ error: message });
      throw error;
    }
  },

  startPolling: () => {
    if (pollInterval) return;
    get().fetchJobs();
    // Poll every 30 seconds to match backend scheduler
    pollInterval = setInterval(() => get().fetchJobs(), 30000);
  },

  stopPolling: () => {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  },

  reset: () => {
    get().stopPolling();
    set({
      jobs: [],
      total: 0,
      pendingCount: 0,
      inProgressCount: 0,
      isLoading: false,
      error: null,
      filter: 'all',
      typeFilter: 'all',
    });
  },
}));
