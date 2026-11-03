import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AlertTriangle, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { settingsApi, type APIKeysResponse } from '@/api/settings';

// Keys in the API response that are not language models.
const NON_LLM_KEYS = ['fal', 'sarvam'];

function messageFor(status: APIKeysResponse): string | null {
  if (status.secrets_unreadable) {
    return 'Your stored API keys cannot be read with the current .env. Enter them again, or restore the original .env.';
  }
  const usable = (name: string) => {
    const key = status.keys[name];
    return !!key?.is_configured && !key.unreadable;
  };
  const hasFal = usable('fal');
  const hasLanguageModel = Object.keys(status.keys).some((name) => !NON_LLM_KEYS.includes(name) && usable(name));
  if (!hasFal && !hasLanguageModel) {
    return 'Add your API keys to start: fal for images and video, and a language model for prompts and the story tools.';
  }
  if (!hasFal) return 'Add a fal API key to generate images and video.';
  if (!hasLanguageModel) return 'Add a language model key for Magic Prompt, the story tools and other writing features.';
  return null;
}

/** Tells a new owner which keys are missing. Hidden on Settings, where they get added. */
export function MissingKeysBanner() {
  const { pathname } = useLocation();
  const [message, setMessage] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const onSettings = pathname.startsWith('/settings');

  useEffect(() => {
    if (onSettings) return;
    let cancelled = false;
    settingsApi
      .getApiKeys()
      .then((status) => {
        if (!cancelled) setMessage(messageFor(status));
      })
      .catch(() => {
        // Not worth interrupting the page: the tool itself reports a missing key.
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, onSettings]);

  if (dismissed || onSettings || !message) return null;

  return (
    <div className="border-b border-warning/30 bg-warning/10 px-4 py-2.5" role="status">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <p className="text-sm text-foreground">{message}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button asChild size="sm">
            <Link to="/settings?tab=api-keys">Open API keys</Link>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}
