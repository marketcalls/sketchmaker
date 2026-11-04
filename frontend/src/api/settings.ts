import apiClient from './client';
import { transformUser } from './auth';
import type { MessageResponse, User } from '../types';

export interface APIKeyStatus {
  is_configured: boolean;
  // Stored, but it cannot be decrypted with the current .env.
  unreadable: boolean;
  // ****abcd, or null for a key too short to show any of.
  masked_key: string | null;
}

export interface APIKeysResponse {
  keys: Record<string, APIKeyStatus>;
  // Everything stored was encrypted with a different SECRET_KEY or ENCRYPTION_SALT.
  secrets_unreadable: boolean;
  default_provider_id: number | null;
  default_model_id: number | null;
  fallback_provider_id: number | null;
  fallback_model_id: number | null;
}

export interface Provider {
  id: number;
  name: string;
  is_active: boolean;
}

export interface AIModel {
  id: number;
  name: string;
  display_name: string | null;
  description: string | null;
  provider_id: number;
  provider_name: string | null;
  context_window: number | null;
  is_latest: boolean;
  is_active: boolean;
}

export interface AIModelCreate {
  name: string;
  display_name: string | null;
  provider_id: number;
  context_window: number | null;
  is_active: boolean;
}

export type AIModelUpdate = Partial<
  Pick<AIModel, 'name' | 'display_name' | 'description' | 'is_active' | 'is_latest'>
>;

// A model a provider offers that is not in the app yet (Refresh models).
export interface OfferedModel {
  name: string;
  display_name: string;
  description: string | null;
  context_window: number | null;
  released: string | null;
  recommended: boolean;
}

export interface ProviderOffer {
  provider_id: number;
  provider: string;
  status: 'ok' | 'key_rejected' | 'unavailable';
  new_models: OfferedModel[];
  no_longer_listed: string[];
}

// One of the models offered for the owner's own choice (/users/models).
export interface ModelOption {
  id: number;
  name: string;
  display_name: string | null;
  provider_id: number;
  is_latest: boolean;
}

// The column a provider's key is saved under.
const keyField = (provider: string) => (provider === 'fal' ? 'fal_key' : `${provider}_api_key`);

export const settingsApi = {
  getApiKeys: async (): Promise<APIKeysResponse> => {
    const response = await apiClient.get('/settings/api-keys');
    return response.data;
  },

  saveApiKey: async (provider: string, value: string): Promise<MessageResponse> => {
    const response = await apiClient.put('/settings/api-keys', { [keyField(provider)]: value });
    return response.data;
  },

  clearApiKey: async (provider: string): Promise<MessageResponse> => {
    const response = await apiClient.delete(`/settings/api-keys/${provider}`);
    return response.data;
  },

  // The provider follows the model on the server, so only the model is sent.
  saveModelChoice: async (
    choice: { default_model_id: number } | { fallback_model_id: number }
  ): Promise<MessageResponse> => {
    const response = await apiClient.put('/settings/api-keys', choice);
    return response.data;
  },

  listProviders: async (): Promise<Provider[]> => {
    const response = await apiClient.get('/settings/providers');
    return response.data;
  },

  listModels: async (): Promise<AIModel[]> => {
    const response = await apiClient.get('/settings/models');
    return response.data;
  },

  createModel: async (data: AIModelCreate): Promise<AIModel> => {
    const response = await apiClient.post('/settings/models', data);
    return response.data;
  },

  // Asks every provider with a key, so it can take a few seconds. Adds nothing.
  refreshModels: async (): Promise<ProviderOffer[]> => {
    const response = await apiClient.post('/settings/models/refresh');
    return response.data.providers;
  },

  addOfferedModels: async (
    models: Array<Pick<OfferedModel, 'name' | 'display_name' | 'description' | 'context_window'> & { provider_id: number }>
  ): Promise<{ added: number }> => {
    const response = await apiClient.post('/settings/models/add-offered', { models });
    return response.data;
  },

  updateModel: async (id: number, data: AIModelUpdate): Promise<AIModel> => {
    const response = await apiClient.patch(`/settings/models/${id}`, data);
    return response.data;
  },

  deleteModel: async (id: number): Promise<MessageResponse> => {
    const response = await apiClient.delete(`/settings/models/${id}`);
    return response.data;
  },

  // The profile, unlike /auth/me, carries the owner's model choice.
  getProfile: async (): Promise<User> => {
    const response = await apiClient.get('/users/profile');
    return transformUser(response.data);
  },

  updateProfile: async (data: {
    username: string;
    selected_provider_id: number | null;
    selected_model_id: number | null;
  }): Promise<User> => {
    const response = await apiClient.patch('/users/profile', data);
    return transformUser(response.data);
  },

  changePassword: async (currentPassword: string, newPassword: string): Promise<MessageResponse> => {
    const response = await apiClient.post('/users/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  // Providers that have a key stored.
  listAvailableProviders: async (): Promise<Provider[]> => {
    const response = await apiClient.get('/users/providers');
    return response.data;
  },

  listAvailableModels: async (providerId: number): Promise<ModelOption[]> => {
    const response = await apiClient.get('/users/models', { params: { provider_id: providerId } });
    return response.data;
  },
};
