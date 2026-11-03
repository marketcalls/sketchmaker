import axios from 'axios';
import { sanitizeApiError } from '@/utils/errors';

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
      } catch {
        // Refresh failed - clear any stored auth state and let the app handle it
        // Don't force redirect here, let the ProtectedRoute handle it
        return Promise.reject(sanitizeApiError(error));
      }
    }

    // Every page shows err.message or response.data.detail; make both fit for people.
    return Promise.reject(sanitizeApiError(error));
  }
);

export default apiClient;
