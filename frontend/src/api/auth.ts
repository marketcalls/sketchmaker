import apiClient from './client';
import type { User, MessageResponse } from '../types';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface SetupRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  user: User;
  message: string;
}

export interface AuthSettings {
  setup_required: boolean;
  // False on a public site, where the account is created in the terminal.
  web_setup: boolean;
}

// Transform snake_case user response to camelCase. /auth/me leaves out the
// model choice; /users/profile carries it (api/settings.ts).
export function transformUser(data: Record<string, unknown>): User {
  return {
    id: data.id as number,
    username: data.username as string,
    createdAt: data.created_at as string,
    selectedProviderId: (data.selected_provider_id as number | null | undefined) ?? undefined,
    selectedModelId: (data.selected_model_id as number | null | undefined) ?? undefined,
  };
}

export const authApi = {
  settings: async (): Promise<AuthSettings> => {
    const response = await apiClient.get('/auth/settings');
    return response.data;
  },

  setup: async (data: SetupRequest): Promise<TokenResponse> => {
    const response = await apiClient.post('/auth/setup', data);
    return {
      user: transformUser(response.data.user),
      message: response.data.message,
    };
  },

  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post('/auth/login', data);
    return {
      user: transformUser(response.data.user),
      message: response.data.message,
    };
  },

  logout: async (): Promise<MessageResponse> => {
    const response = await apiClient.post('/auth/logout');
    return response.data;
  },

  me: async (): Promise<{ user: User }> => {
    const response = await apiClient.get('/auth/me');
    return { user: transformUser(response.data) };
  },

  refresh: async (): Promise<TokenResponse> => {
    const response = await apiClient.post('/auth/refresh');
    return {
      user: transformUser(response.data.user),
      message: response.data.message,
    };
  },
};
