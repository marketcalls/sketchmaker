import apiClient from './client';

export type UsageKind = 'fal' | 'sarvam' | 'llm';

export interface UsageKindTotals {
  usd: number;
  count: number;
  input_tokens?: number;
  output_tokens?: number;
  unpriced_calls?: number;
}

export interface UsageFeatureRow {
  kind: UsageKind;
  feature: string | null;
  count: number;
  // null when no LLM call for this feature has a known price
  usd: number | null;
  input_tokens?: number;
  output_tokens?: number;
  unpriced_calls?: number;
}

export interface UsageSummary {
  days: number;
  total_usd: number;
  by_kind: Record<UsageKind, UsageKindTotals>;
  by_feature: UsageFeatureRow[];
}

export interface UsageLogEntry {
  id: number;
  kind: UsageKind;
  created_at: string | null;
  feature: string | null;
  model: string | null;
  usd: number | null;
  units: number | null;
  unit: string | null;
  job_type: string | null;
  job_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface UsageLogPage {
  entries: UsageLogEntry[];
  total: number;
  page: number;
  per_page: number;
}

export interface FalModel {
  endpoint_id: string;
  display_name: string;
  category: string;
}

export interface FalModels {
  models: FalModel[];
  total_models: number;
}

export interface FalPrice {
  endpoint_id: string;
  display_name: string;
  unit_price: number | null;
  unit: string;
  currency: string;
  error?: string | null;
}

export const usageApi = {
  getSummary: async (days: number): Promise<UsageSummary> => {
    const response = await apiClient.get('/usage/summary', { params: { days } });
    return response.data;
  },

  getLog: async (page: number, perPage: number): Promise<UsageLogPage> => {
    const response = await apiClient.get('/usage/log', { params: { page, per_page: perPage } });
    return response.data;
  },

  getFalModels: async (): Promise<FalModels> => {
    const response = await apiClient.get('/usage/fal-models');
    return response.data;
  },

  getFalPrice: async (modelId: string): Promise<FalPrice> => {
    const response = await apiClient.get(`/usage/fal-pricing/${encodeURIComponent(modelId)}`);
    return response.data;
  },
};
