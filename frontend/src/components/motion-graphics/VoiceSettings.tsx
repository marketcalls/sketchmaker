import { useEffect, useMemo, useState } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { assetsApi, type VoiceCatalog, type VoiceOption } from '@/api/assets';
import { VoicePicker } from '@/components/assets/VoicePicker';
import type { AudioSettings, MGCatalog } from '@/api/motionGraphics';
import { cn } from '@/lib/utils';
import { FieldLabel } from './shared';

type Voice = AudioSettings['voice'];

let providersCache: VoiceCatalog | null = null;

// Voice model and voice for a motion graphics voiceover: ElevenLabs (Eleven
// v4, the stock voice list) or Sarvam Bulbul v4 (Indian voices and languages;
// shown once the Sarvam key is set).
export function VoiceSettings({
  catalog,
  voice,
  busy,
  onChange,
}: {
  catalog: MGCatalog;
  voice: Voice;
  busy: boolean;
  onChange: (patch: Partial<Voice>) => void;
}) {
  const [providers, setProviders] = useState<VoiceCatalog | null>(providersCache);
  const [language, setLanguage] = useState<string | null>(null);

  useEffect(() => {
    if (providersCache) return;
    let live = true;
    assetsApi
      .voices()
      .then((c) => {
        providersCache = c;
        if (live) setProviders(c);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const sarvam = providers?.providers.find((p) => p.id === 'sarvam') ?? null;
  const provider = voice.provider === 'sarvam' && sarvam ? 'sarvam' : 'elevenlabs';
  const voiceLanguage = sarvam?.voices.find((v) => v.id === voice.voice_id)?.language ?? null;
  const activeLanguage = language ?? voiceLanguage ?? sarvam?.defaultLanguage ?? null;
  const sarvamVoices = useMemo(
    () => (sarvam ? sarvam.voices.filter((v) => v.language === activeLanguage) : []),
    [sarvam, activeLanguage],
  );

  // The shared catalog carries gender for the picker's filter; the motion
  // graphics catalog is the fallback until it loads (same voice ids).
  const elevenVoices = useMemo<VoiceOption[]>(
    () =>
      providers?.providers.find((p) => p.id === 'elevenlabs')?.voices ??
      catalog.voices.map((v) => ({ id: v.id, label: v.id, language: null, description: `${v.accent}, ${v.tone}` })),
    [providers, catalog.voices],
  );

  return (
    <div className="space-y-3">
      {sarvam && (
        <div>
          <FieldLabel>Voice model</FieldLabel>
          <div role="radiogroup" aria-label="Voice model" className="grid grid-cols-2 gap-2">
            {[
              { id: 'elevenlabs' as const, label: 'ElevenLabs', hint: 'Eleven v4' },
              { id: 'sarvam' as const, label: 'Sarvam', hint: 'Bulbul v4, Indian languages' },
            ].map((m) => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={provider === m.id}
                disabled={busy}
                onClick={() => m.id !== provider && onChange({ provider: m.id })}
                className={cn(
                  'rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-60',
                  provider === m.id
                    ? 'border-primary/60 bg-primary/10 text-foreground'
                    : 'border-border bg-secondary/20 text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                )}
              >
                <span className="block text-sm font-medium">{m.label}</span>
                <span className="block text-[11px] text-muted-foreground">{m.hint}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {provider === 'sarvam' && sarvam ? (
        <>
          <div>
            <FieldLabel>Language</FieldLabel>
            <Select
              value={activeLanguage ?? undefined}
              onValueChange={(lang) => {
                setLanguage(lang);
                const first = sarvam.voices.find((v) => v.language === lang);
                if (first) onChange({ voice_id: first.id });
              }}
              disabled={busy}
            >
              <SelectTrigger aria-label="Language">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {sarvam.languages.map((l) => (
                  <SelectItem key={l.id} value={l.id}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <FieldLabel hint={`${sarvamVoices.length} voices`}>Voice</FieldLabel>
            <VoicePicker
              provider="sarvam"
              voices={sarvamVoices}
              value={voice.voice_id}
              onChange={(v) => onChange({ voice_id: v })}
              disabled={busy}
            />
          </div>
          <div>
            <FieldLabel hint={`${(voice.pace ?? 1).toFixed(2)}x`}>Pace</FieldLabel>
            <Slider
              value={[voice.pace ?? 1]}
              min={0.5}
              max={2}
              step={0.05}
              onValueCommit={(v) => onChange({ pace: v[0] })}
              aria-label="Speaking pace"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Write the scene lines in the language you picked. Sarvam returns no word timings, so caption and word
            sync is estimated from the audio's pauses: close, not frame exact.
          </p>
        </>
      ) : (
        <>
          <div>
            <FieldLabel>Voice</FieldLabel>
            <VoicePicker
              provider="elevenlabs"
              voices={elevenVoices}
              value={voice.voice_id}
              onChange={(v) => onChange({ voice_id: v })}
              disabled={busy}
            />
          </div>
          <div>
            <FieldLabel hint={voice.stability.toFixed(2)}>Stability</FieldLabel>
            <Slider
              value={[voice.stability]}
              min={0}
              max={1}
              step={0.05}
              onValueCommit={(v) => onChange({ stability: v[0] })}
              aria-label="Voice stability"
            />
          </div>
        </>
      )}
    </div>
  );
}
