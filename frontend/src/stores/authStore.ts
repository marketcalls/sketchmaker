import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi } from '../api/auth';
import type { User } from '../types';
import { getErrorMessage } from '@/utils/errors';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  // No owner exists yet, so every protected page goes to /setup.
  setupRequired: boolean;

  // Actions
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  clearError: () => void;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,  // Start true to wait for checkAuth
      error: null,
      setupRequired: false,

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
        } catch {
          let setupRequired = false;
          try {
            setupRequired = (await authApi.settings()).setup_required;
          } catch {
            // Without an answer, the login page is the safe place to land.
          }
          set({
            user: null,
            isAuthenticated: false,
            isLoading: false,
            setupRequired,
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
