import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertTriangle, Bot, Check, Eye, EyeOff, Key, KeyRound, Loader2, Palette, Plus, RefreshCw, Settings, Trash2, User, X } from 'lucide-react';
import { RefreshModelsDialog } from '@/components/settings/RefreshModelsDialog';
import { Alert } from '@/components/ui/alert';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { SavedNote } from '@/components/common/SavedNote';
import { StatusBadge } from '@/components/common/StatusBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableEmptyRow, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { Stagger, StaggerItem } from '@/components/motion';
import { settingsApi, type AIModel, type APIKeysResponse, type ModelOption, type Provider } from '@/api/settings';
import { getErrorMessage } from '@/utils/errors';

const PASSWORD_MIN_LENGTH = 12;

const PROVIDER_CONFIG = [
  { key: 'openai', name: 'OpenAI', description: 'GPT-4o, GPT-4, GPT-3.5' },
  { key: 'anthropic', name: 'Anthropic', description: 'Claude 3.5, Claude 3' },
  { key: 'gemini', name: 'Google Gemini', description: 'Gemini Pro, Gemini Flash' },
  { key: 'groq', name: 'Groq', description: 'LLaMA, Mixtral' },
  { key: 'xai', name: 'xAI', description: 'Grok models' },
  { key: 'cerebras', name: 'Cerebras', description: 'LLaMA on Cerebras' },
  { key: 'openrouter', name: 'OpenRouter', description: 'Multiple providers' },
  { key: 'baseten', name: 'Baseten', description: 'Kimi K3, GLM 5.2 (OpenAI-compatible)' },
  { key: 'fal', name: 'FAL', description: 'Image generation' },
  { key: 'sarvam', name: 'Sarvam AI', description: 'Bulbul v4 voices for Indian languages (Lip Sync, My Assets)' },
];

const modelName = (model: { display_name: string | null; name: string }) => model.display_name || model.name;

function ApiKeysTab({
  apiKeys,
  loadFailed,
  onChanged,
}: {
  apiKeys: APIKeysResponse | null;
  loadFailed: boolean;
  onChanged: () => Promise<void>;
}) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [newKeyValue, setNewKeyValue] = useState('');
  const [showKeyValue, setShowKeyValue] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [results, setResults] = useState<Record<string, { success: boolean; message: string }>>({});
  const [clearKeyTarget, setClearKeyTarget] = useState<{ key: string; name: string } | null>(null);

  const showResult = (providerKey: string, success: boolean, message: string) =>
    setResults((prev) => ({ ...prev, [providerKey]: { success, message } }));

  const closeEditor = () => {
    setEditingKey(null);
    setNewKeyValue('');
    setShowKeyValue(false);
  };

  const handleSaveKey = async (providerKey: string) => {
    if (!newKeyValue.trim()) return;
    setSavingKey(true);
    try {
      await settingsApi.saveApiKey(providerKey, newKeyValue);
      await onChanged();
      closeEditor();
      showResult(providerKey, true, 'Key saved.');
    } catch (err) {
      showResult(providerKey, false, getErrorMessage(err, 'The key could not be saved.'));
    } finally {
      setSavingKey(false);
    }
  };

  const handleClearKey = async (providerKey: string) => {
    try {
      await settingsApi.clearApiKey(providerKey);
      await onChanged();
      showResult(providerKey, true, 'Key removed.');
    } catch (err) {
      showResult(providerKey, false, getErrorMessage(err, 'The key could not be removed.'));
    }
  };

  // Reads the status above; it does not call the provider.
  const handleCheckSaved = (providerKey: string, providerName: string) => {
    const status = apiKeys?.keys[providerKey];
    if (status?.unreadable) {
      showResult(providerKey, false, 'A key is saved, but it cannot be read.');
    } else if (status?.is_configured) {
      showResult(providerKey, true, `A key is saved. This does not test it with ${providerName}.`);
    } else {
      showResult(providerKey, false, 'No key is saved.');
    }
  };

  if (!apiKeys) {
    if (loadFailed) return null;
    return (
      <div className="grid gap-4 md:grid-cols-2" aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-40 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <>
      {apiKeys.secrets_unreadable && (
        <Alert variant="destructive">
          The stored keys cannot be read with the current SECRET_KEY or ENCRYPTION_SALT. Restore the original .env, or
          enter the keys again.
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {PROVIDER_CONFIG.map((provider) => {
          const keyStatus = apiKeys.keys[provider.key];
          const isConfigured = keyStatus?.is_configured || false;
          const isUnreadable = keyStatus?.unreadable || false;

          return (
            <Card key={provider.key} className="overflow-hidden">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-secondary/40">
                      <Key className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="text-base">{provider.name}</CardTitle>
                      <CardDescription className="text-xs">{provider.description}</CardDescription>
                    </div>
                  </div>
                  {isUnreadable ? (
                    <Badge variant="destructive">
                      <AlertTriangle className="h-3 w-3" />
                      Unreadable
                    </Badge>
                  ) : isConfigured ? (
                    <Badge variant="success">
                      <Check className="h-3 w-3" />
                      Configured
                    </Badge>
                  ) : (
                    <Badge variant="outline">
                      <X className="h-3 w-3" />
                      Not set
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {keyStatus?.masked_key && (
                    <div className="max-w-full truncate rounded-md border border-border bg-secondary/40 px-3 py-2 font-mono text-xs text-muted-foreground">
                      {keyStatus.masked_key}
                    </div>
                  )}

                  {isUnreadable && (
                    <p className="text-xs text-destructive">
                      This key is stored but cannot be read with the current .env. Replace it to use {provider.name}.
                    </p>
                  )}

                  {editingKey === provider.key ? (
                    <div className="space-y-2">
                      <Label htmlFor={`key-${provider.key}`}>API key</Label>
                      <div className="relative">
                        <Input
                          id={`key-${provider.key}`}
                          type={showKeyValue ? 'text' : 'password'}
                          value={newKeyValue}
                          onChange={(e) => setNewKeyValue(e.target.value)}
                          placeholder={`${provider.name} API key`}
                          className="pr-10 font-mono"
                          autoComplete="off"
                          autoFocus
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="absolute right-0 top-0 h-full"
                          aria-label={showKeyValue ? 'Hide key' : 'Show key'}
                          onClick={() => setShowKeyValue(!showKeyValue)}
                        >
                          {showKeyValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </Button>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => handleSaveKey(provider.key)} disabled={savingKey || !newKeyValue.trim()}>
                          {savingKey && <Loader2 className="h-4 w-4 animate-spin" />}
                          {savingKey ? 'Saving' : 'Save key'}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={closeEditor}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          closeEditor();
                          setEditingKey(provider.key);
                        }}
                      >
                        {isConfigured ? 'Replace key' : 'Set key'}
                      </Button>
                      {isConfigured && (
                        <>
                          <Button size="sm" variant="outline" onClick={() => handleCheckSaved(provider.key, provider.name)}>
                            <RefreshCw className="h-4 w-4" />
                            Check saved
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                            onClick={() => setClearKeyTarget({ key: provider.key, name: provider.name })}
                          >
                            Remove key
                          </Button>
                        </>
                      )}
                    </div>
                  )}

                  {results[provider.key] && (
                    <p className={`text-xs ${results[provider.key].success ? 'text-muted-foreground' : 'text-destructive'}`}>
                      {results[provider.key].message}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <ConfirmDialog
        open={!!clearKeyTarget}
        onOpenChange={(open) => !open && setClearKeyTarget(null)}
        title="Remove API key"
        description={
          clearKeyTarget
            ? `Remove the ${clearKeyTarget.name} API key? Features that use ${clearKeyTarget.name} stop working until a new key is set.`
            : ''
        }
        confirmText="Remove key"
        variant="destructive"
        onConfirm={async () => {
          if (clearKeyTarget) await handleClearKey(clearKeyTarget.key);
        }}
      />
    </>
  );
}

function ProviderAndModelFields({
  idPrefix,
  providers,
  models,
  providerId,
  modelId,
  primaryProviderId,
  onProviderChange,
  onModelChange,
}: {
  idPrefix: string;
  providers: Provider[];
  models: AIModel[];
  providerId: number | null;
  modelId: number | null;
  // Set on the fallback's fields, to mark the provider the primary already uses.
  primaryProviderId?: number | null;
  onProviderChange: (id: number) => void;
  onModelChange: (id: number) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-provider`}>Provider</Label>
        <Select value={providerId?.toString() || ''} onValueChange={(value) => onProviderChange(parseInt(value))}>
          <SelectTrigger id={`${idPrefix}-provider`}>
            <SelectValue placeholder="Select provider" />
          </SelectTrigger>
          <SelectContent>
            {providers.filter((p) => p.is_active).map((p) => (
              <SelectItem key={p.id} value={p.id.toString()}>
                {p.name}
                {primaryProviderId && p.id === primaryProviderId ? ' (same as primary)' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-model`}>Model</Label>
        <Select value={modelId?.toString() || ''} onValueChange={(value) => onModelChange(parseInt(value))}>
          <SelectTrigger id={`${idPrefix}-model`}>
            <SelectValue placeholder="Select model" />
          </SelectTrigger>
          <SelectContent>
            {models
              .filter((m) => m.is_active && (!providerId || m.provider_id === providerId))
              .map((m) => (
                <SelectItem key={m.id} value={m.id.toString()}>
                  {modelName(m)}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function DefaultModelCard({
  apiKeys,
  providers,
  models,
  onChanged,
}: {
  apiKeys: APIKeysResponse;
  providers: Provider[];
  models: AIModel[];
  onChanged: () => Promise<void>;
}) {
  // The server sets the provider from the model, so a provider picked here only
  // narrows the model list until a model is chosen.
  const [defaultProviderId, setDefaultProviderId] = useState(apiKeys.default_provider_id);
  const [fallbackProviderId, setFallbackProviderId] = useState(apiKeys.fallback_provider_id);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDefaultProviderId(apiKeys.default_provider_id);
    setFallbackProviderId(apiKeys.fallback_provider_id);
  }, [apiKeys.default_provider_id, apiKeys.fallback_provider_id]);

  const saveChoice = async (choice: { default_model_id: number } | { fallback_model_id: number }) => {
    setSaved(false);
    setError(null);
    try {
      await settingsApi.saveModelChoice(choice);
      await onChanged();
      setSaved(true);
    } catch (err) {
      setError(getErrorMessage(err, 'That choice could not be saved.'));
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <CardTitle className="text-base">Default language model</CardTitle>
          <SavedNote show={saved} />
        </div>
        <CardDescription>Used for prompt generation, explainers and other text features.</CardDescription>
      </CardHeader>
      <CardContent>
        <ProviderAndModelFields
          idPrefix="default"
          providers={providers}
          models={models}
          providerId={defaultProviderId}
          modelId={apiKeys.default_model_id}
          onProviderChange={setDefaultProviderId}
          onModelChange={(id) => saveChoice({ default_model_id: id })}
        />
        <p className="mt-2 text-xs text-muted-foreground">Changes save as soon as you pick a model.</p>
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

        <div className="mt-6 border-t border-border pt-6">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">Fallback model</h3>
            <p className="mt-1 max-w-prose text-sm text-muted-foreground">
              Used automatically when the primary model fails (an outage, a rate limit or a bad response). Choose a model
              from a <span className="text-foreground">different provider</span>: a second model on the same provider
              will not help when that provider is the one that is down.
            </p>
          </div>

          <ProviderAndModelFields
            idPrefix="fallback"
            providers={providers}
            models={models}
            providerId={fallbackProviderId}
            modelId={apiKeys.fallback_model_id}
            primaryProviderId={apiKeys.default_provider_id}
            onProviderChange={setFallbackProviderId}
            onModelChange={(id) => saveChoice({ fallback_model_id: id })}
          />

          {apiKeys.fallback_model_id && apiKeys.fallback_model_id === apiKeys.default_model_id && (
            <p className="mt-3 text-xs text-warning">
              The fallback is the same as the primary model, so failover is skipped.
            </p>
          )}
          {!apiKeys.fallback_model_id && (
            <p className="mt-3 text-xs text-muted-foreground">No fallback set. A primary failure shows as an error.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

const EMPTY_NEW_MODEL = { name: '', display_name: '', provider_id: 0, context_window: 0, is_active: true };

function LiteLLMModels({
  providers,
  models,
  onChanged,
}: {
  providers: Provider[];
  models: AIModel[];
  onChanged: () => Promise<void>;
}) {
  const [isAddingModel, setIsAddingModel] = useState(false);
  const [newModel, setNewModel] = useState(EMPTY_NEW_MODEL);
  const [editingModel, setEditingModel] = useState<AIModel | null>(null);
  const [deleteModelTarget, setDeleteModelTarget] = useState<AIModel | null>(null);
  const [saving, setSaving] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [listNotice, setListNotice] = useState<string | null>(null);

  const handleModelsAdded = async (count: number) => {
    await onChanged();
    setListNotice(`${count} ${count === 1 ? 'model' : 'models'} added.`);
  };

  const handleCreateModel = async () => {
    setSaving(true);
    setDialogError(null);
    try {
      await settingsApi.createModel({
        name: newModel.name.trim(),
        display_name: newModel.display_name.trim() || null,
        provider_id: newModel.provider_id,
        context_window: newModel.context_window || null,
        is_active: newModel.is_active,
      });
      await onChanged();
      setIsAddingModel(false);
      setNewModel(EMPTY_NEW_MODEL);
    } catch (err) {
      setDialogError(getErrorMessage(err, 'The model could not be added.'));
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateModel = async () => {
    if (!editingModel) return;
    setSaving(true);
    setDialogError(null);
    try {
      await settingsApi.updateModel(editingModel.id, {
        name: editingModel.name,
        display_name: editingModel.display_name,
        description: editingModel.description,
        is_active: editingModel.is_active,
        is_latest: editingModel.is_latest,
      });
      await onChanged();
      setEditingModel(null);
    } catch (err) {
      setDialogError(getErrorMessage(err, 'The model could not be saved.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteModel = async (modelId: number) => {
    setListError(null);
    try {
      await settingsApi.deleteModel(modelId);
      await onChanged();
    } catch (err) {
      setListError(getErrorMessage(err, 'The model could not be deleted.'));
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">LiteLLM models</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Language models available to the app (<span className="tabular">{models.length}</span>).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setListNotice(null);
              setIsRefreshing(true);
            }}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh models
          </Button>
          <Button
            onClick={() => {
              setDialogError(null);
              setIsAddingModel(true);
            }}
          >
            <Plus className="h-4 w-4" />
            Add model
          </Button>
        </div>
      </div>

      <RefreshModelsDialog open={isRefreshing} onOpenChange={setIsRefreshing} onAdded={handleModelsAdded} />

      {listNotice && <p className="text-sm text-muted-foreground" role="status">{listNotice}</p>}
      {listError && <p className="text-sm text-destructive">{listError}</p>}

      {/* Group models by provider */}
      {providers.filter((p) => models.some((m) => m.provider_id === p.id)).map((provider) => (
        <section key={provider.id} className="space-y-2">
          <div className="flex items-baseline gap-2">
            <h3 className="text-sm font-semibold">{provider.name}</h3>
            <span className="tabular text-xs text-muted-foreground">
              {models.filter((m) => m.provider_id === provider.id).length} models
            </span>
          </div>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <Table stickyHeader density="compact">
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Context</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24 text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {models
                  .filter((m) => m.provider_id === provider.id)
                  .map((model) => (
                    <TableRow key={model.id}>
                      <TableCell>
                        <p className="font-medium">{modelName(model)}</p>
                        <p className="font-mono text-xs text-muted-foreground">{model.name}</p>
                      </TableCell>
                      <TableCell className="tabular text-right font-mono text-xs">
                        {model.context_window ? `${(model.context_window / 1000).toFixed(0)}K` : '-'}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <StatusBadge status={model.is_active ? 'active' : 'inactive'} />
                          {model.is_latest && <Badge variant="outline">Latest</Badge>}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            aria-label={`Edit ${modelName(model)}`}
                            onClick={() => {
                              setDialogError(null);
                              setEditingModel(model);
                            }}
                          >
                            <Settings className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-destructive hover:bg-destructive/10 hover:text-destructive"
                            aria-label={`Delete ${modelName(model)}`}
                            onClick={() => setDeleteModelTarget(model)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}

      {models.length === 0 && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <Table>
            <TableBody>
              <TableEmptyRow columns={1}>No models configured. Add a model to offer it in the app.</TableEmptyRow>
            </TableBody>
          </Table>
        </div>
      )}

      {/* Add Model Dialog */}
      <Dialog open={isAddingModel} onOpenChange={setIsAddingModel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add model</DialogTitle>
            <DialogDescription>Register a LiteLLM model under one of the providers.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-model-name">Model name</Label>
              <Input
                id="new-model-name"
                className="font-mono"
                value={newModel.name}
                onChange={(e) => setNewModel({ ...newModel, name: e.target.value })}
                placeholder="gpt-6.1-sol"
              />
              <p className="text-xs text-muted-foreground">
                The exact name the provider uses. OpenRouter names include the vendor, such as openai/gpt-6.1-sol.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-model-display">Display name</Label>
              <Input
                id="new-model-display"
                value={newModel.display_name}
                onChange={(e) => setNewModel({ ...newModel, display_name: e.target.value })}
                placeholder="GPT-6.1 Sol"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-model-provider">Provider</Label>
              <Select
                value={newModel.provider_id ? String(newModel.provider_id) : ''}
                onValueChange={(v) => setNewModel({ ...newModel, provider_id: Number(v) })}
              >
                <SelectTrigger id="new-model-provider">
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-model-context">Context window</Label>
              <Input
                id="new-model-context"
                type="number"
                className="tabular"
                value={newModel.context_window}
                onChange={(e) => setNewModel({ ...newModel, context_window: Number(e.target.value) })}
                placeholder="128000"
              />
              <p className="text-xs text-muted-foreground">In tokens.</p>
            </div>
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="new-model-active">Active</Label>
              <Switch
                id="new-model-active"
                checked={newModel.is_active}
                onCheckedChange={(checked) => setNewModel({ ...newModel, is_active: checked })}
              />
            </div>
            {dialogError && <p className="text-sm text-destructive">{dialogError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddingModel(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateModel} disabled={saving || !newModel.name.trim() || !newModel.provider_id}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              {saving ? 'Adding' : 'Add model'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Model Dialog */}
      <Dialog open={!!editingModel} onOpenChange={() => setEditingModel(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit model</DialogTitle>
            <DialogDescription>Name, label and availability of this model.</DialogDescription>
          </DialogHeader>
          {editingModel && (
            <>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-model-name">Model name</Label>
                  <Input
                    id="edit-model-name"
                    className="font-mono"
                    value={editingModel.name}
                    onChange={(e) => setEditingModel({ ...editingModel, name: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-model-display">Display name</Label>
                  <Input
                    id="edit-model-display"
                    value={editingModel.display_name ?? ''}
                    onChange={(e) => setEditingModel({ ...editingModel, display_name: e.target.value })}
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="edit-model-active">Active</Label>
                  <Switch
                    id="edit-model-active"
                    checked={editingModel.is_active}
                    onCheckedChange={(checked) => setEditingModel({ ...editingModel, is_active: checked })}
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <Label htmlFor="edit-model-latest">Latest</Label>
                    <p className="mt-1 text-xs text-muted-foreground">Marks the newest model of this family.</p>
                  </div>
                  <Switch
                    id="edit-model-latest"
                    checked={editingModel.is_latest}
                    onCheckedChange={(checked) => setEditingModel({ ...editingModel, is_latest: checked })}
                  />
                </div>
                {dialogError && <p className="text-sm text-destructive">{dialogError}</p>}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setEditingModel(null)}>
                  Cancel
                </Button>
                <Button onClick={handleUpdateModel} disabled={saving || !editingModel.name.trim()}>
                  {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                  {saving ? 'Saving' : 'Save changes'}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete model confirmation */}
      <ConfirmDialog
        open={!!deleteModelTarget}
        onOpenChange={(open) => !open && setDeleteModelTarget(null)}
        title="Delete model"
        description={
          deleteModelTarget
            ? `Delete ${modelName(deleteModelTarget)} (${deleteModelTarget.name})? It is no longer offered anywhere in the app.`
            : ''
        }
        confirmText="Delete model"
        variant="destructive"
        onConfirm={async () => {
          if (deleteModelTarget) await handleDeleteModel(deleteModelTarget.id);
        }}
      />
    </section>
  );
}

export function SettingsPage() {
  const [searchParams] = useSearchParams();
  const { user, setUser } = useAuthStore();
  const { theme, setTheme } = useUIStore();

  const [username, setUsername] = useState(user?.username || '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(user?.selectedProviderId || null);
  const [selectedModelId, setSelectedModelId] = useState<number | null>(user?.selectedModelId || null);

  const [availableProviders, setAvailableProviders] = useState<Provider[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [loadingModels, setLoadingModels] = useState(false);

  const [isUpdatingProfile, setIsUpdatingProfile] = useState(false);
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // API keys, the default and fallback model, and the LiteLLM model list
  const [apiKeys, setApiKeys] = useState<APIKeysResponse | null>(null);
  const [allProviders, setAllProviders] = useState<Provider[]>([]);
  const [allModels, setAllModels] = useState<AIModel[]>([]);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  // The owner's model choice comes from the profile: /auth/me leaves it out, so
  // the persisted user alone would show this tab blank after a reload.
  useEffect(() => {
    settingsApi
      .getProfile()
      .then((profile) => {
        setUser(profile);
        setSelectedProviderId(profile.selectedProviderId ?? null);
        setSelectedModelId(profile.selectedModelId ?? null);
      })
      .catch(() => {
        // The fields keep what the persisted user had.
      });
  }, [setUser]);

  const loadAvailableProviders = useCallback(async () => {
    try {
      setAvailableProviders(await settingsApi.listAvailableProviders());
    } catch {
      // Ignore error
    } finally {
      setLoadingProviders(false);
    }
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const [keys, providers, models] = await Promise.all([
        settingsApi.getApiKeys(),
        settingsApi.listProviders(),
        settingsApi.listModels(),
      ]);
      setApiKeys(keys);
      setAllProviders(providers);
      setAllModels(models);
      setSettingsError(null);
    } catch (err) {
      setSettingsError(getErrorMessage(err, 'These settings could not be loaded. Refresh the page to try again.'));
    }
  }, []);

  // A change here can change which providers have a key, and which models exist.
  const reloadAfterChange = useCallback(async () => {
    await Promise.all([loadSettings(), loadAvailableProviders()]);
  }, [loadSettings, loadAvailableProviders]);

  useEffect(() => {
    reloadAfterChange();
  }, [reloadAfterChange]);

  // Fetch models when provider changes (and when the model list itself changes)
  useEffect(() => {
    if (selectedProviderId) {
      setLoadingModels(true);
      const fetchModels = async () => {
        try {
          setAvailableModels(await settingsApi.listAvailableModels(selectedProviderId));
        } catch {
          setAvailableModels([]);
        } finally {
          setLoadingModels(false);
        }
      };
      fetchModels();
    } else {
      setAvailableModels([]);
    }
  }, [selectedProviderId, allModels]);

  const handleUpdateProfile = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    setIsUpdatingProfile(true);
    setProfileError(null);
    setProfileSuccess(false);

    try {
      const profile = await settingsApi.updateProfile({
        username,
        selected_provider_id: selectedProviderId,
        selected_model_id: selectedModelId,
      });
      setUser(profile);
      setProfileSuccess(true);
    } catch (err: unknown) {
      setProfileError(getErrorMessage(err, 'Failed to update profile'));
    } finally {
      setIsUpdatingProfile(false);
    }
  };

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordSuccess(false);
    if (newPassword.length < PASSWORD_MIN_LENGTH) {
      setPasswordError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }

    setIsUpdatingPassword(true);
    setPasswordError(null);

    try {
      await settingsApi.changePassword(currentPassword, newPassword);
      setPasswordSuccess(true);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      setPasswordError(getErrorMessage(err, 'Failed to update password'));
    } finally {
      setIsUpdatingPassword(false);
    }
  };

  return (
    <Stagger className="space-y-6" interval={0.04}>
      <StaggerItem>
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Profile, API keys, AI model, password and theme.
          </p>
        </header>
      </StaggerItem>

      <StaggerItem>
      <Tabs defaultValue={searchParams.get('tab') ?? 'profile'}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="profile">
            <User className="h-4 w-4" />
            Profile
          </TabsTrigger>
          <TabsTrigger value="api-keys">
            <KeyRound className="h-4 w-4" />
            API keys
          </TabsTrigger>
          <TabsTrigger value="ai-settings">
            <Bot className="h-4 w-4" />
            AI model
          </TabsTrigger>
          <TabsTrigger value="security">
            <Key className="h-4 w-4" />
            Security
          </TabsTrigger>
          <TabsTrigger value="appearance">
            <Palette className="h-4 w-4" />
            Appearance
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Profile</CardTitle>
              <CardDescription>Your name as shown in the app.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <Input
                    id="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={isUpdatingProfile}
                  />
                </div>

                {profileError && (
                  <p className="text-sm text-destructive">{profileError}</p>
                )}

                <div className="flex items-center gap-3">
                  <Button type="submit" disabled={isUpdatingProfile}>
                    {isUpdatingProfile && <Loader2 className="h-4 w-4 animate-spin" />}
                    {isUpdatingProfile ? 'Saving' : 'Save changes'}
                  </Button>
                  <SavedNote show={profileSuccess && !isUpdatingProfile} />
                </div>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="api-keys" className="space-y-4 mt-4">
          {settingsError && <Alert variant="destructive">{settingsError}</Alert>}
          <ApiKeysTab apiKeys={apiKeys} loadFailed={!!settingsError} onChanged={reloadAfterChange} />
        </TabsContent>

        <TabsContent value="ai-settings" className="space-y-6 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI model</CardTitle>
              <CardDescription>The provider and model used for prompt writing and other text.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {loadingProviders ? (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : availableProviders.length === 0 ? (
                <div className="py-4 text-sm text-muted-foreground">
                  No AI provider has a key yet. Add one under API keys.
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="ai-provider">Provider</Label>
                    <Select
                      value={selectedProviderId?.toString() || ''}
                      onValueChange={(v) => {
                        setSelectedProviderId(v ? parseInt(v) : null);
                        setSelectedModelId(null); // Reset model when provider changes
                      }}
                    >
                      <SelectTrigger id="ai-provider">
                        <SelectValue placeholder="Select a provider" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableProviders.map((provider) => (
                          <SelectItem key={provider.id} value={provider.id.toString()}>
                            {provider.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Which AI provider writes text for you.
                    </p>
                  </div>

                  {selectedProviderId && (
                    <div className="space-y-2">
                      <Label htmlFor="ai-model">Model</Label>
                      {loadingModels ? (
                        <Skeleton className="h-10 w-full" />
                      ) : availableModels.length === 0 ? (
                        <p className="text-sm text-muted-foreground py-2">
                          No models are available for this provider.
                        </p>
                      ) : (
                        <Select
                          value={selectedModelId?.toString() || ''}
                          onValueChange={(v) => setSelectedModelId(v ? parseInt(v) : null)}
                        >
                          <SelectTrigger id="ai-model">
                            <SelectValue placeholder="Select a model" />
                          </SelectTrigger>
                          <SelectContent>
                            {availableModels.map((model) => (
                              <SelectItem key={model.id} value={model.id.toString()}>
                                {modelName(model)}
                                {model.is_latest && ' (latest)'}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                      <p className="text-xs text-muted-foreground">
                        The model to use with this provider.
                      </p>
                    </div>
                  )}

                  {profileError && (
                    <p className="text-sm text-destructive">{profileError}</p>
                  )}

                  <div className="flex items-center gap-3 pt-2">
                    <Button onClick={handleUpdateProfile} disabled={isUpdatingProfile}>
                      {isUpdatingProfile && <Loader2 className="h-4 w-4 animate-spin" />}
                      {isUpdatingProfile ? 'Saving' : 'Save AI model'}
                    </Button>
                    <SavedNote show={profileSuccess && !isUpdatingProfile} />
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {settingsError && <Alert variant="destructive">{settingsError}</Alert>}
          {apiKeys && (
            <>
              <DefaultModelCard apiKeys={apiKeys} providers={allProviders} models={allModels} onChanged={reloadAfterChange} />
              <LiteLLMModels providers={allProviders} models={allModels} onChanged={reloadAfterChange} />
            </>
          )}
        </TabsContent>

        <TabsContent value="security" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Password</CardTitle>
              <CardDescription>Change the password you sign in with.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleUpdatePassword} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="currentPassword">Current password</Label>
                  <Input
                    id="currentPassword"
                    type="password"
                    autoComplete="current-password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    disabled={isUpdatingPassword}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="newPassword">New password</Label>
                  <Input
                    id="newPassword"
                    type="password"
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    disabled={isUpdatingPassword}
                  />
                  <p className="text-xs text-muted-foreground">At least {PASSWORD_MIN_LENGTH} characters.</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">Confirm new password</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={isUpdatingPassword}
                    aria-invalid={confirmPassword.length > 0 && newPassword !== confirmPassword}
                  />
                  {confirmPassword.length > 0 && newPassword !== confirmPassword && (
                    <p className="text-xs text-destructive">The passwords do not match.</p>
                  )}
                </div>

                {passwordError && (
                  <p className="text-sm text-destructive">{passwordError}</p>
                )}

                <div className="flex items-center gap-3">
                  <Button type="submit" disabled={isUpdatingPassword}>
                    {isUpdatingPassword && <Loader2 className="h-4 w-4 animate-spin" />}
                    {isUpdatingPassword ? 'Updating' : 'Update password'}
                  </Button>
                  <SavedNote show={passwordSuccess && !isUpdatingPassword}>Password updated</SavedNote>
                </div>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="appearance" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Theme</CardTitle>
              <CardDescription>Light or dark interface.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <Label htmlFor="theme-select">Theme</Label>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Applies on this device.
                  </p>
                </div>
                <Select value={theme} onValueChange={(v: 'light' | 'dark') => setTheme(v)}>
                  <SelectTrigger id="theme-select" className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="light">Light</SelectItem>
                    <SelectItem value="dark">Dark</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      </StaggerItem>
    </Stagger>
  );
}
