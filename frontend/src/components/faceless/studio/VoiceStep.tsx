import { useEffect, useMemo, useRef, useState } from 'react';
import { AudioLines, Loader2, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { errorSuffix, getErrorMessage } from '@/utils/errors';
import { VOICE_KEY, formatUsd, usePricingStore } from '@/stores/pricingStore';
import {
  FACELESS_LANGUAGES,
  facelessApi,
  type FacelessCharacter,
  type FacelessProject,
  type StepRun,
  type VoiceSettings,
} from '@/api/faceless';
import { useFacelessStore } from '@/stores/facelessStore';
import { CharacterAvatar } from '../CharacterCard';
import { VoiceSelect } from '../VoicePicker';
import { AssetStateIcon, EmptyState, ErrorNote, FieldLabel, Kicker, formatDuration } from '../shared';
import { usePaidStep } from './usePaidStep';
import { usePaidGate } from './gate';
import { useDebouncedCallback } from './useDebouncedCallback';
import { sceneAssetState, sceneRunState, voiceReady } from './stepState';

export function VoiceStep({ project, runs }: { project: FacelessProject; runs: StepRun[] }) {
  const { voices, characters, setProject, upsertCharacter, refreshProject } = useFacelessStore();
  const { getModelCost } = usePricingStore();
  const gate = usePaidGate(project, 'voice');
  const { request, dialog } = usePaidStep(project.id);
  const [stability, setStability] = useState(project.voice_settings?.stability ?? 0.5);
  const [similarity, setSimilarity] = useState(project.voice_settings?.similarity_boost ?? 0.75);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const per1k = getModelCost(VOICE_KEY);

  useEffect(() => {
    setStability(project.voice_settings?.stability ?? 0.5);
    setSimilarity(project.voice_settings?.similarity_boost ?? 0.75);
  }, [project.voice_settings?.stability, project.voice_settings?.similarity_boost]);

  const cast = useMemo(
    () => project.cast_ids.map((id) => characters.find((c) => c.id === id)).filter((c): c is FacelessCharacter => !!c),
    [project.cast_ids, characters],
  );
  const scenes = project.script?.scenes ?? [];
  const pending = project.scenes.filter((a) => a.voice.length > 0 && !voiceReady(a));
  const totalChars = pending.reduce((n, a) => n + a.voice.filter((v) => !v.current).reduce((m, v) => m + v.text.length, 0), 0);

  // Replies can land out of order: only the newest save may change the page.
  const lastSave = useRef(0);
  const update = async (body: Parameters<typeof facelessApi.updateProject>[1]) => {
    const seq = ++lastSave.current;
    setSaving(true);
    setError(null);
    try {
      const saved = await facelessApi.updateProject(project.id, body);
      if (seq === lastSave.current) setProject(saved);
    } catch (err) {
      if (seq === lastSave.current) setError(getErrorMessage(err, 'Could not save the voice settings'));
    } finally {
      if (seq === lastSave.current) setSaving(false);
    }
  };
  // A slider commits on every arrow key press, so a held key would flood the route.
  const saveVoiceSettings = useDebouncedCallback((voice_settings: VoiceSettings) => update({ voice_settings }));

  const setCharacterVoice = async (c: FacelessCharacter, voiceId: string | null) => {
    setError(null);
    try {
      upsertCharacter(await facelessApi.updateCharacter(c.id, { voice_id: voiceId }));
      await refreshProject();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not change the voice'));
    }
  };

  if (scenes.length === 0) {
    return <EmptyState icon={AudioLines} title="Script first">Voices read the narration and dialogue of the saved script.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <div className="panel grid grid-cols-1 gap-5 rounded-xl p-4 lg:grid-cols-2">
        <div className="space-y-4">
          <div>
            <FieldLabel htmlFor="vs-narrator">Narrator</FieldLabel>
            <VoiceSelect id="vs-narrator" voices={voices} value={project.narrator_voice} onChange={(v) => v && update({ narrator_voice: v })} label="Narrator voice" disabled={saving} />
          </div>
          <div>
            <FieldLabel htmlFor="vs-lang">Language</FieldLabel>
            <Select value={project.language} onValueChange={(language) => update({ language })} disabled={saving}>
              <SelectTrigger id="vs-lang">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FACELESS_LANGUAGES.map((l) => (
                  <SelectItem key={l.code} value={l.code}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <FieldLabel hint={`${stability.toFixed(2)}, lower is more expressive`}>Stability</FieldLabel>
            <Slider
              value={[stability]}
              min={0}
              max={1}
              step={0.05}
              onValueChange={([v]) => setStability(v)}
              onValueCommit={([v]) => saveVoiceSettings.call({ stability: v, similarity_boost: similarity })}
              aria-label="Voice stability"
            />
          </div>
          <div>
            <FieldLabel hint={similarity.toFixed(2)}>Similarity</FieldLabel>
            <Slider
              value={[similarity]}
              min={0}
              max={1}
              step={0.05}
              onValueChange={([v]) => setSimilarity(v)}
              onValueCommit={([v]) => saveVoiceSettings.call({ stability, similarity_boost: v })}
              aria-label="Voice similarity"
            />
          </div>
        </div>
        <div>
          <Kicker className="mb-2">Character voices</Kicker>
          {cast.length === 0 ? (
            <p className="text-sm text-muted-foreground">Narration only. Add cast to the project to give lines to characters.</p>
          ) : (
            <ul className="space-y-2">
              {cast.map((c) => (
                <li key={c.id} className="flex items-center gap-2">
                  <CharacterAvatar character={c} size={32} />
                  <span className="w-28 truncate text-sm">{c.name}</span>
                  <div className="min-w-0 flex-1">
                    <VoiceSelect voices={voices} value={c.voice_id} onChange={(v) => setCharacterVoice(c, v)} label={`${c.name} voice`} allowNone="Narrator voice" />
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            Stock Eleven v4 voices only; voice cloning is not offered. Changing a voice or a line marks its clip out of date.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground">
          {pending.length} scene{pending.length === 1 ? '' : 's'} to voice, about {totalChars.toLocaleString()} characters
          {per1k !== undefined && `, ${formatUsd(per1k)} per 1,000 characters`}
          <span className="block">
            Runtime {formatDuration(project.total_seconds)} of {formatDuration(project.length_seconds)}
            {project.timing_measured ? ', measured' : ', estimated'}
          </span>
        </p>
        <Button
          disabled={!!gate || pending.length === 0}
          title={gate ?? undefined}
          onClick={() =>
            request({
              step: 'voice',
              title: 'Generate voices',
              description: `Voice clips for ${pending.length} scene${pending.length === 1 ? '' : 's'} with missing or outdated lines.`,
            })
          }
        >
          <AudioLines className="h-4 w-4" /> {pending.length === 0 ? 'All voiced' : 'Voice all missing'}
        </Button>
      </div>
      {gate && gate !== 'Already running' && <p className="text-xs text-muted-foreground">{gate}.</p>}
      <ErrorNote>{error}</ErrorNote>

      <ol className="space-y-3" aria-label="Scene voices">
        {scenes.map((scene, i) => {
          const a = project.scenes.find((x) => x.scene_id === scene.id);
          const { running, failed } = sceneRunState(project, runs, 'voice', scene.id);
          const ready = voiceReady(a);
          const target = scene.duration || 0;
          const actual = a?.duration ?? 0;
          const drift = target > 0 && a?.measured ? (actual - target) / target : 0;
          return (
            <li key={scene.id} className={cn('panel rounded-xl p-3 sm:p-4', running && 'beam-border')}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <AssetStateIcon state={sceneAssetState(running, ready, !!failed)} label="Voice" />
                <span className="font-mono text-[11px] tabular text-muted-foreground">{String(i + 1).padStart(2, '0')}</span>
                <span className="text-sm">{scene.beat_name || scene.beat}</span>
                <span className={cn('ml-auto font-mono text-[11px] tabular', Math.abs(drift) > 0.25 ? 'text-warning' : 'text-muted-foreground')}>
                  {formatDuration(actual)} {a?.measured ? 'measured' : 'est.'}
                  {target > 0 && ` / ${formatDuration(target)} planned`}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!!gate || running || !a || a.voice.length === 0}
                  title={gate ?? undefined}
                  onClick={() =>
                    request({
                      step: 'voice',
                      sceneIds: [scene.id],
                      title: `Voice scene ${i + 1}`,
                      description: `Every line of "${scene.beat_name || scene.beat}", regenerated.`,
                    })
                  }
                >
                  {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
                  {running ? 'Voicing' : ready ? 'Redo' : 'Voice'}
                </Button>
              </div>
              <ul className="space-y-2">
                {(a?.voice ?? []).map((line) => (
                  <li key={line.index} className="rounded-lg bg-secondary/30 p-2">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center">
                      <div className="md:w-40">
                        <p className="truncate text-xs">{line.speaker}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {line.voice}
                          {line.duration ? `, ${line.duration.toFixed(1)}s` : ''}
                          {line.wpm ? `, ${line.wpm} wpm` : ''}
                          {line.url && !line.current && <span className="text-warning">, outdated</span>}
                        </p>
                      </div>
                      <p className="min-w-0 flex-1 text-sm">{line.text}</p>
                      {line.url ? (
                        <audio src={line.url} controls preload="none" className="h-9 w-full md:w-64" aria-label={`${line.speaker} line audio`} />
                      ) : (
                        <span className="text-xs text-muted-foreground md:w-64">No audio yet</span>
                      )}
                    </div>
                    {line.warning && (
                      <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-2 py-1.5">
                        <p className="min-w-0 flex-1 text-xs text-warning">{line.warning}</p>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!!gate || running}
                          title={gate ?? undefined}
                          onClick={() =>
                            request({
                              step: 'voice',
                              sceneIds: [scene.id],
                              options: { lines: [line.index] },
                              title: 'Voice this line again',
                              description: `A new take of ${line.speaker}'s line, priced like any voice line.`,
                            })
                          }
                        >
                          Re-voice
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              {failed && !running && (
                <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-destructive">
                  Failed{errorSuffix(failed.error)}
                </p>
              )}
            </li>
          );
        })}
      </ol>
      {dialog}
    </div>
  );
}
