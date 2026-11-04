import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi } from '../api/auth';
import { onSessionExpired } from '../api/client';
import type { User } from '../types';
import { getErrorMessage } from '@/utils/errors';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  // No owner exists yet, so every protected page goes to /setup.
  setupRequired: boolean;
  // False on a public site, where the account is created in the terminal.
  webSetup: boolean;

  // Actions
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  clearError: () => void;
  setUser: (user: User | null) => void;
}

const statusOf = (error: unknown): number | undefined =>
  (error as { response?: { status?: number } }).response?.status;

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,  // Start true to wait for checkAuth
      error: null,
      setupRequired: false,
      webSetup: true,

      login: async (username, password) => {
        set({ isLoading: true, error: null });
        try {
          const response = await authApi.login({ username, password });
          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error: unknown) {
          set({ error: getErrorMessage(error, 'Login failed'), isLoading: false });
          throw error;
        }
      },

      // The setup reply carries the session cookie, so this also signs in.
      setup: async (username, password) => {
        const response = await authApi.setup({ username, password });
        set({
          user: response.user,
          isAuthenticated: true,
          setupRequired: false,
        });
      },

      logout: async () => {
        try {
          await authApi.logout();
        } finally {
          set({ user: null, isAuthenticated: false });
        }
      },

      checkAuth: async () => {
        set({ isLoading: true });
        try {
          const response = await authApi.me();
          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
            setupRequired: false,
          });
        } catch (error: unknown) {
          // Only the server saying so ends a session. A rate limit or a network blip must
          // not send someone with a valid cookie to the login page.
          if (statusOf(error) !== 401) {
            set({ isLoading: false });
            return;
          }
          let setupRequired = false;
          let webSetup = true;
          try {
            const authSettings = await authApi.settings();
            setupRequired = authSettings.setup_required;
            webSetup = authSettings.web_setup;
          } catch {
            // Without an answer, the login page is the safe place to land.
          }
          set({
            user: null,
            isAuthenticated: false,
            isLoading: false,
            setupRequired,
            webSetup,
          });
        }
      },

      clearError: () => set({ error: null }),

      setUser: (user) => set({ user, isAuthenticated: !!user }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// A session that has really ended, noticed during normal use: ProtectedRoute takes it from here.
onSessionExpired(() => useAuthStore.setState({ user: null, isAuthenticated: false }));
