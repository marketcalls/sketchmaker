import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Loader2, Pause, Play } from 'lucide-react';
import { assetsApi, type VoiceOption, type VoiceProviderId } from '@/api/assets';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';

type Gender = 'all' | 'female' | 'male';

// Sample URLs already fetched this session, per provider and voice.
const sampleUrls = new Map<string, string>();
// One sample plays at a time across every picker on the page.
let sharedAudio: HTMLAudioElement | null = null;

interface VoicePickerProps {
  provider: VoiceProviderId;
  voices: VoiceOption[];
  value: string | null;
  onChange: (voiceId: string) => void;
  disabled?: boolean;
  className?: string;
}

// The voice list for every voice picker: who the voice is (name, gender,
// accent or style) and a sample to listen to before choosing.
export function VoicePicker({ provider, voices, value, onChange, disabled, className }: VoicePickerProps) {
  const [gender, setGender] = useState<Gender>('all');
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const hasGender = voices.some((v) => v.gender === 'female' || v.gender === 'male');
  const shown = useMemo(
    () => (gender === 'all' ? voices : voices.filter((v) => v.gender === gender)),
    [voices, gender],
  );

  // Stop this picker's sample when it goes away (unmount only).
  const playingRef = useRef<string | null>(null);
  playingRef.current = playing;
  useEffect(
    () => () => {
      if (sharedAudio && playingRef.current) sharedAudio.pause();
    },
    [],
  );

  // Keep the chosen voice in view when the list opens or the language changes.
  useEffect(() => {
    if (!value || !listRef.current) return;
    const row = listRef.current.querySelector<HTMLElement>(`[data-voice="${CSS.escape(value)}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }, [value, voices]);

  const toggleSample = async (voice: VoiceOption) => {
    setError(null);
    if (playing === voice.id) {
      sharedAudio?.pause();
      setPlaying(null);
      return;
    }
    const key = `${provider}:${voice.id}`;
    try {
      let url = sampleUrls.get(key);
      if (!url) {
        setLoading(voice.id);
        url = await assetsApi.voiceSample(provider, voice.id);
        sampleUrls.set(key, url);
      }
      sharedAudio?.pause();
      const audio = new Audio(url);
      sharedAudio = audio;
      audio.onended = () => setPlaying((p) => (p === voice.id ? null : p));
      audio.onpause = () => setPlaying((p) => (p === voice.id ? null : p));
      await audio.play();
      setPlaying(voice.id);
    } catch (err) {
      setError(getErrorMessage(err, 'This sample could not be played. Please try again.'));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className={cn('space-y-2', className)}>
      {hasGender && (
        <div role="radiogroup" aria-label="Voice gender" className="inline-flex rounded-full border border-border bg-muted/60 p-1">
          {(['all', 'female', 'male'] as Gender[]).map((g) => (
            <button
              key={g}
              type="button"
              role="radio"
              aria-checked={gender === g}
              onClick={() => setGender(g)}
              className={cn(
                'rounded-full px-3 py-1 text-xs capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                gender === g ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {g}
            </button>
          ))}
        </div>
      )}

      <div
        ref={listRef}
        role="radiogroup"
        aria-label="Voice"
        className="max-h-72 space-y-1 overflow-y-auto rounded-xl border border-border bg-secondary/10 p-1"
      >
        {shown.length === 0 && <p className="p-3 text-sm text-muted-foreground">No voices match.</p>}
        {shown.map((v) => {
          const selected = v.id === value;
          return (
            <div
              key={v.id}
              data-voice={v.id}
              className={cn(
                'flex items-center gap-2 rounded-lg border px-2 py-1.5 transition-colors duration-150',
                selected ? 'border-primary/60 bg-primary/10' : 'border-transparent hover:bg-muted/60',
              )}
            >
              <button
                type="button"
                onClick={() => toggleSample(v)}
                disabled={loading !== null && loading !== v.id}
                aria-label={playing === v.id ? `Stop the ${v.label} sample` : `Play a sample of ${v.label}`}
                title={playing === v.id ? 'Stop' : 'Listen'}
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40',
                  playing === v.id ? 'border-foreground/40 bg-accent text-foreground' : 'border-border text-foreground hover:border-foreground/30',
                )}
              >
                {loading === v.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : playing === v.id ? (
                  <Pause className="h-3.5 w-3.5" />
                ) : (
                  <Play className="ml-0.5 h-3.5 w-3.5" />
                )}
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={disabled}
                onClick={() => onChange(v.id)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{v.label}</span>
                  <span className="block truncate text-xs capitalize text-muted-foreground">
                    {[v.gender && v.gender !== 'neutral' ? v.gender : null, v.description].filter(Boolean).join(', ') || 'voice'}
                  </span>
                </span>
                {selected && <Check className="h-4 w-4 shrink-0 text-primary" />}
              </button>
            </div>
          );
        })}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <p className="text-xs text-muted-foreground">Press play to hear a voice.</p>
    </div>
  );
}
