import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { isSubmitShortcut } from '@/components/generate';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { FieldLabel } from '@/components/faceless/shared';
import { assetsApi, type Asset, type VoiceCatalog, type VoiceProviderId } from '@/api/assets';
import { VoicePicker } from './VoicePicker';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { formatUsd, usePricingStore } from '@/stores/pricingStore';

// Speaking pace used for the length estimate (the real length is measured
// once the voice exists).
const WORDS_PER_MINUTE = 160;

let catalogCache: VoiceCatalog | null = null;

/** USD for `chars` characters, rounded to 4 decimals (backend pricing.tts_usd). */
export function voiceUsd(per1k: number, chars: number): number {
  if (chars <= 0) return 0;
  return Math.round(((per1k * chars) / 1000) * 1e4) / 1e4;
}

export function estimateSpeechSeconds(text: string, pace = 1): number {
  const words = text.replace(/\[[^\]]*\]/g, ' ').trim().split(/\s+/).filter(Boolean).length;
  return (words / WORDS_PER_MINUTE) * 60 / (pace || 1);
}

interface VoiceGeneratorProps {
  // Called with the new audio asset (already saved in My Assets).
  onCreated: (asset: Asset) => void;
  disabled?: boolean;
  // Shown under the length estimate, e.g. the Lip Sync limits.
  lengthHint?: string;
  minSeconds?: number;
  maxSeconds?: number;
}

// Script, voice model and voice. ElevenLabs for natural English and
// multilingual voices; Sarvam Bulbul v4 for Indian accents and regional
// languages (shown once the Sarvam key is saved).
export function VoiceGenerator({ onCreated, disabled, lengthHint, minSeconds, maxSeconds }: VoiceGeneratorProps) {
  const { getModelCost } = usePricingStore();
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(catalogCache);
  const [providerId, setProviderId] = useState<VoiceProviderId>('elevenlabs');
  const [language, setLanguage] = useState<string | null>(null);
  const [voices, setVoices] = useState<Partial<Record<VoiceProviderId, string>>>({});
  const [text, setText] = useState('');
  const [stability, setStability] = useState(0.5);
  const [pace, setPace] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A voice that finishes after the generator closed (the user switched to
  // another audio source) is kept in My Assets but not selected.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (catalogCache) return;
    let live = true;
    assetsApi
      .voices()
      .then((c) => {
        catalogCache = c;
        if (live) setCatalog(c);
      })
      .catch((err) => live && setError(getErrorMessage(err, 'Could not load the voices')));
    return () => {
      live = false;
    };
  }, []);

  const provider = catalog?.providers.find((p) => p.id === providerId) ?? catalog?.providers[0] ?? null;
  const isSarvam = provider?.id === 'sarvam';
  const activeLanguage = isSarvam ? language ?? provider?.defaultLanguage ?? null : null;
  const voiceOptions = useMemo(
    () => (provider ? provider.voices.filter((v) => !isSarvam || v.language === activeLanguage) : []),
    [provider, isSarvam, activeLanguage],
  );
  const chosen = provider ? voices[provider.id] : undefined;
  const voice = voiceOptions.some((v) => v.id === chosen)
    ? chosen!
    : voiceOptions.find((v) => v.id === provider?.defaultVoice)?.id ?? voiceOptions[0]?.id ?? null;

  const maxChars = provider?.maxCharacters ?? 2500;
  const chars = text.trim().length;
  const per1k = provider ? getModelCost(provider.priceKey) : undefined;
  const cost = per1k !== undefined ? voiceUsd(per1k, chars) : undefined;
  const estimate = estimateSpeechSeconds(text, isSarvam ? pace : 1);
  const tooLong = chars > maxChars;
  const lengthWarning =
    chars > 0 && maxSeconds && estimate > maxSeconds
      ? `About ${Math.round(estimate)} seconds: longer than the ${maxSeconds} seconds allowed here. Shorten the text.`
      : chars > 0 && minSeconds && estimate < minSeconds
        ? `About ${Math.round(estimate)} seconds: shorter than the ${minSeconds} seconds needed here. Add a little more text.`
        : null;
  const locked = disabled || busy;

  const generate = async () => {
    if (!provider || !voice || chars === 0 || tooLong || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { asset } = await assetsApi.generateVoice({
        text: text.trim(),
        voice,
        provider: provider.id,
        ...(provider.id === 'sarvam' ? { pace } : { stability }),
      });
      if (mounted.current) onCreated(asset);
    } catch (err) {
      if (mounted.current) setError(getErrorMessage(err, 'The voice could not be generated'));
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {catalog && catalog.providers.length > 1 && (
        <div>
          <FieldLabel>Voice model</FieldLabel>
          <div role="radiogroup" aria-label="Voice model" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {catalog.providers.map((p) => {
              const active = p.id === provider?.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setProviderId(p.id)}
                  disabled={locked}
                  className={cn(
                    'rounded-lg border px-3 py-2 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60',
                    active
                      ? 'border-primary/60 bg-primary/10 text-foreground'
                      : 'border-border bg-secondary/20 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                  )}
                >
                  <span className="block text-sm font-medium">
                    {p.label} <span className="font-mono text-[10px] text-muted-foreground">{p.model}</span>
                  </span>
                  <span className="block text-xs text-muted-foreground">{p.description}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div>
        <FieldLabel htmlFor="voice-text" hint={`${chars} / ${maxChars}`}>
          Script
        </FieldLabel>
        <Textarea
          id="voice-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (isSubmitShortcut(e) && !locked && voice && chars > 0 && !tooLong) {
              e.preventDefault();
              void generate();
            }
          }}
          rows={5}
          maxLength={maxChars + 500}
          placeholder={
            isSarvam
              ? 'Type the script in the language you picked, for example: नमस्ते, आज हम बात करेंगे...'
              : 'Type what the voice should say. Audio tags such as [excited] or [whispers] change the delivery.'
          }
          disabled={locked}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          {chars > 0 ? `About ${Math.max(1, Math.round(estimate))} seconds of speech` : 'Length follows the text'}
          {lengthHint ? `. ${lengthHint}` : ''}
        </p>
        {tooLong && <p className="mt-1 text-xs text-warning">The text is over {maxChars} characters. Shorten it.</p>}
        {!tooLong && lengthWarning && <p className="mt-1 text-xs text-warning">{lengthWarning}</p>}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {isSarvam && provider && (
          <div>
            <FieldLabel htmlFor="voice-language">Language</FieldLabel>
            <Select value={activeLanguage ?? undefined} onValueChange={setLanguage} disabled={locked}>
              <SelectTrigger id="voice-language" aria-label="Language">
                <SelectValue placeholder="Choose a language" />
              </SelectTrigger>
              <SelectContent>
                {provider.languages.map((l) => (
                  <SelectItem key={l.id} value={l.id}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div>
          <FieldLabel htmlFor="voice-select" hint={isSarvam ? `${voiceOptions.length} voices` : undefined}>
            Voice
          </FieldLabel>
          {provider && (
            <VoicePicker
              provider={provider.id}
              voices={voiceOptions}
              value={voice}
              onChange={(v) => setVoices((prev) => ({ ...prev, [provider.id]: v }))}
              disabled={locked}
            />
          )}
        </div>
        {isSarvam ? (
          <div>
            <FieldLabel hint={`${pace.toFixed(2)}x`}>Pace</FieldLabel>
            <div className="pt-3">
              <Slider
                value={[pace]}
                min={0.5}
                max={2}
                step={0.05}
                onValueChange={([v]) => setPace(v)}
                disabled={locked}
                aria-label="Speaking pace"
              />
            </div>
          </div>
        ) : (
          <div>
            <FieldLabel hint={`${stability.toFixed(2)}, lower is more expressive`}>Stability</FieldLabel>
            <div className="pt-3">
              <Slider
                value={[stability]}
                min={0}
                max={1}
                step={0.05}
                onValueChange={([v]) => setStability(v)}
                disabled={locked}
                aria-label="Voice stability"
              />
            </div>
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono tabular text-xs text-muted-foreground">
          {per1k === undefined
            ? 'Loading price'
            : chars > 0
              ? `${formatUsd(cost ?? 0)} (${formatUsd(per1k)} per 1,000 characters)`
              : `${formatUsd(per1k)} per 1,000 characters`}
        </p>
        <Button className="min-w-[9.5rem]" onClick={generate} disabled={locked || !voice || chars === 0 || tooLong}>
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating
            </>
          ) : (
            'Generate voice'
          )}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Ctrl+Enter in the script generates.{' '}
        {isSarvam
          ? 'Sarvam Bulbul v4 voices speak Indian languages with natural Indian accents. '
          : 'ElevenLabs stock voices. '}
        Each voice is saved to My Assets, so you can reuse it or delete it later.
      </p>
    </div>
  );
}
