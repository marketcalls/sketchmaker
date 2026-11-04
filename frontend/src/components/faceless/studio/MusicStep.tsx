import { useState } from 'react';
import { Music } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { cn } from '@/lib/utils';
import { errorSuffix, getErrorMessage } from '@/utils/errors';
import { MUSIC_KEY, formatUsd, usePricingStore } from '@/stores/pricingStore';
import { facelessApi, type FacelessProject, type StepRun } from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { EmptyState, ErrorNote, FieldLabel, Kicker, formatDuration } from '../shared';
import { usePaidStep } from './usePaidStep';
import { usePaidGate } from './gate';
import { useRenderPrefs } from './renderPrefs';
import { activeRun, lastRun } from './stepState';
import { Elapsed } from './RunsStrip';

export function MusicStep({ project, runs }: { project: FacelessProject; runs: StepRun[] }) {
  const { musicMoods, templates, setProject } = useFacelessStore();
  const { getModelCost } = usePricingStore();
  const gate = usePaidGate(project, 'music');
  const { request, dialog } = usePaidStep(project.id);
  const template = templates.find((t) => t.id === project.template_id);
  const [instrumental, setInstrumental] = useState(project.music?.instrumental ?? template?.music.force_instrumental ?? true);
  const [prefs, setPrefs] = useRenderPrefs(project.id);
  const [error, setError] = useState<string | null>(null);
  const mood = project.music_mood ?? 'template';
  const tracks = (project.music?.tracks ?? []).filter((t) => t.url);
  const perMinute = getModelCost(MUSIC_KEY);
  const templateGain = template?.music.gain_db ?? -18;
  const gain = prefs.musicGainDb ?? templateGain;
  const failed = lastRun(runs, 'music');
  const live = activeRun(project, 'music');

  const pickMood = async (id: string) => {
    setError(null);
    try {
      setProject(await facelessApi.updateProject(project.id, { music_mood: id }));
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the mood'));
    }
  };

  if (!project.script) {
    return <EmptyState icon={Music} title="Script first">Music is scored to the scene timing of the script.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <section aria-labelledby="music-moods">
        <Kicker className="mb-2">
          <span id="music-moods">Mood</span>
        </Kicker>
        <div role="radiogroup" aria-label="Music mood" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {musicMoods.map((m) => {
            const active = m.id === mood;
            const desc = m.id === 'template' ? template?.music.positive_global_styles.join(', ') || 'The template score' : m.positive.join(', ') || 'Voice only';
            return (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => pickMood(m.id)}
                className={cn(
                  'rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  active ? 'border-primary/60 bg-primary/10' : 'border-border bg-secondary/30 hover:border-foreground/30',
                )}
              >
                <span className="block text-sm font-medium text-foreground">{m.label}</span>
                <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{desc}</span>
              </button>
            );
          })}
        </div>
      </section>

      <div className={cn('panel grid grid-cols-1 gap-5 rounded-xl p-4 md:grid-cols-2', live && 'beam-border')}>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <label htmlFor="mu-inst" className="text-sm font-medium">Instrumental</label>
              <p className="text-xs text-muted-foreground">No vocals under the narration.</p>
            </div>
            <Switch id="mu-inst" checked={instrumental} onCheckedChange={setInstrumental} />
          </div>
          <div>
            <FieldLabel hint={`${gain.toFixed(0)} dB${prefs.musicGainDb === null ? ', template level' : ''}`}>Music volume</FieldLabel>
            <Slider
              value={[gain]}
              min={-30}
              max={-6}
              step={1}
              onValueChange={([v]) => setPrefs({ musicGainDb: v })}
              aria-label="Music volume in decibels"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Applied at render. The music ducks automatically under every voice line, fades in and out, and the mix is levelled to -14 LUFS.
            </p>
          </div>
        </div>
        <div className="flex flex-col justify-between gap-3">
          <div>
            <Kicker className="mb-2">Track</Kicker>
            {live && (
              <p className="mb-2 text-sm" role="status">
                {live.status === 'queued' ? 'Music queued' : `Composing the track, ${live.progress}%`}
                <Elapsed since={live.started_at ?? live.created_at} className="ml-2 font-mono text-xs tabular text-muted-foreground" />
              </p>
            )}
            {tracks.length === 0 ? (
              !live && <p className="text-sm text-muted-foreground">No track yet.</p>
            ) : (
              <ul className="space-y-2">
                {tracks.map((t, i) => (
                  <li key={i}>
                    <audio src={t.url ?? undefined} controls preload="none" className="h-9 w-full" aria-label={`Music track ${i + 1}`} />
                    <p className="mt-1 font-mono text-[11px] tabular text-muted-foreground">
                      {formatDuration(t.duration)} from {formatDuration(t.start ?? 0)}
                      {project.music?.mood && `, ${project.music.mood}`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            {!project.timing_measured && (
              <p className="mt-2 text-xs text-warning">Voice the scenes first so the score follows the real cuts.</p>
            )}
            {failed?.status === 'failed' && tracks.length === 0 && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
                The last track failed{errorSuffix(failed.error)}
              </p>
            )}
          </div>
          <div>
            <p className="mb-2 font-mono text-[11px] tabular text-muted-foreground">
              {perMinute !== undefined && `${formatUsd(perMinute)} per started minute per track`}
            </p>
            <Button
              disabled={!!gate || mood === 'none'}
              title={gate ?? (mood === 'none' ? 'No music chosen' : undefined)}
              onClick={() =>
                request({
                  step: 'music',
                  options: { mood, instrumental, regenerate: tracks.length > 0 },
                  title: tracks.length > 0 ? 'New music track' : 'Generate music',
                  description: `An ElevenLabs score in the ${musicMoods.find((m) => m.id === mood)?.label ?? mood} mood, timed to the scenes.`,
                })
              }
            >
              <Music className="h-4 w-4" /> {tracks.length > 0 ? 'Generate a new track' : 'Generate music'}
            </Button>
          </div>
        </div>
      </div>
      {gate && gate !== 'Already running' && <p className="text-xs text-muted-foreground">{gate}.</p>}
      <ErrorNote>{error}</ErrorNote>
      {dialog}
    </div>
  );
}
