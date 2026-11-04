import axios from 'axios';
import { sanitizeApiError } from '@/utils/errors';

let sessionExpiredHandler: (() => void) | null = null;

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for handling auth errors
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest) return Promise.reject(sanitizeApiError(error));

    // A read that hit a restarting worker or a dropped connection (the proxy
    // answers 502/503/504, or nothing comes back) is safe to repeat once.
    const status = error.response?.status;
    const transient =
      status === 502 || status === 503 || status === 504 || (!error.response && error.code === 'ERR_NETWORK');
    if (transient && (originalRequest.method ?? 'get').toLowerCase() === 'get' && !originalRequest._transientRetry) {
      originalRequest._transientRetry = true;
      await new Promise((resolve) => window.setTimeout(resolve, 800));
      return apiClient(originalRequest);
    }

    // Don't try to refresh if:
    // - Already retried
    // - The request is to the refresh endpoint itself
    // - The request is to auth endpoints (login, setup, etc.)
    const isAuthEndpoint = originalRequest.url?.includes('/auth/');

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthEndpoint
    ) {
      originalRequest._retry = true;

      try {
        await apiClient.post('/auth/refresh');
        return apiClient(originalRequest);
      } catch (refreshError: unknown) {
        // A refused refresh means the session has ended, say after signing out in another
        // tab. Anything else, such as a network blip, leaves the person signed in.
        if ((refreshError as { response?: { status?: number } }).response?.status === 401) {
          sessionExpiredHandler?.();
        }
        return Promise.reject(sanitizeApiError(error));
      }
    }

    // Every page shows err.message or response.data.detail; make both fit for people.
    return Promise.reject(sanitizeApiError(error));
  }
);

// The auth store imports this file, so it registers here rather than being imported.
export function onSessionExpired(handler: () => void): void {
  sessionExpiredHandler = handler;
}

export default apiClient;
