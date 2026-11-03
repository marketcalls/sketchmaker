import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { SEO } from '@/components/SEO';
import { QuickClip } from '@/components/stories/QuickClip';
import { StoryRoom } from '@/components/stories/StoryRoom';
import type { ClipSource } from '@/components/stories/MakeVideoTab';
import { storyRoomApi } from '@/api/storyRoom';
import { useStoryStore } from '@/stores/storyStore';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';

type PageTab = 'room' | 'clip';

/**
 * /stories: the Story Room (default) and the Quick clip maker.
 *
 *   /stories?thread=ID                      opens a story
 *   /stories?tab=clip                       the clip maker
 *   /stories?tab=clip&thread=ID&shot=s1.2   the clip maker prefilled from a shot
 *   /stories?tab=clip&thread=ID&take=1      prefilled with the whole piece as one take
 */
export function StoriesPage() {
  const [params, setParams] = useSearchParams();
  const tab: PageTab = params.get('tab') === 'clip' ? 'clip' : 'room';
  const threadParam = Number(params.get('thread'));
  const threadId = Number.isInteger(threadParam) && threadParam > 0 ? threadParam : null;
  const shotId = params.get('shot');
  const take = params.get('take') === '1';

  const prefillFromShot = useStoryStore((s) => s.prefillFromShot);
  const openThread = useStoryRoomStore((s) => s.thread);
  const [prefill, setPrefill] = useState<{ threadId: number; label: string } | null>(null);
  const [prefilling, setPrefilling] = useState(false);
  const [prefillError, setPrefillError] = useState<string | null>(null);
  const handled = useRef<string | null>(null);

  const setTab = (next: PageTab) => {
    const p: Record<string, string> = {};
    if (next === 'clip') p.tab = 'clip';
    else {
      setPrefill(null);
      setPrefillError(null);
    }
    if (threadId) p.thread = String(threadId);
    setParams(p);
  };

  // Deep link into Quick clip: fetch the director's clip prompt and fill the maker.
  useEffect(() => {
    if (tab !== 'clip' || !threadId || (!shotId && !take)) return;
    const key = `${threadId}:${shotId ?? 'take'}`;
    if (handled.current === key) return;
    handled.current = key;
    setPrefilling(true);
    setPrefillError(null);
    (shotId ? storyRoomApi.shotClip(threadId, shotId) : storyRoomApi.treatmentClip(threadId))
      .then((clip) => {
        if (useStoryStore.getState().isGenerating) {
          setPrefillError('A clip is being generated. When it finishes, open the shot again to fill the maker.');
          return;
        }
        prefillFromShot(clip);
        setPrefill({ threadId, label: shotId ? `shot ${shotId}` : 'the treatment, as one take' });
      })
      .catch((err) => setPrefillError(getErrorMessage(err, 'The clip prompt could not be loaded.')))
      .finally(() => {
        setPrefilling(false);
        handled.current = null;
        // Keep the story for "Back to the story"; a reload must not refill.
        setParams({ tab: 'clip', thread: String(threadId) }, { replace: true });
      });
  }, [tab, threadId, shotId, take, prefillFromShot, setParams]);

  const openClip = (id: number, source: ClipSource) => {
    const p: Record<string, string> = { tab: 'clip', thread: String(id) };
    if (source.kind === 'shot') p.shot = source.shotId;
    else p.take = '1';
    setParams(p);
  };

  const storyTitle = prefill && openThread?.id === prefill.threadId ? openThread.title : '';

  return (
    <>
      {tab === 'room' && (
        <SEO
          title="Story Room - AI Story and Ad Director"
          description="Develop a story or an ad with an AI director: a full treatment, cast, shot list and reference images, then video"
        />
      )}
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-balance text-2xl font-semibold tracking-tight">{tab === 'room' ? 'Story Room' : 'Quick clip'}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {tab === 'room'
              ? 'Develop a story or an ad with a director, then turn it into video.'
              : 'Generate a video clip from text, images or keyframes.'}
          </p>
        </div>
        <div role="tablist" aria-label="Stories" className="inline-flex rounded-md border border-border bg-secondary/50 p-1">
          {([
            { id: 'room', label: 'Story Room' },
            { id: 'clip', label: 'Quick clip' },
          ] as { id: PageTab; label: string }[]).map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'rounded px-4 py-1.5 text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                tab === t.id ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {tab === 'room' ? (
        <StoryRoom
          threadId={threadId}
          onThreadChange={(id) => setParams(id ? { thread: String(id) } : {})}
          onOpenClip={openClip}
        />
      ) : (
        <>
          {(prefilling || prefill || prefillError) && (
            <div
              className={cn(
                'mb-2 flex max-w-3xl flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm',
                prefillError ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-border bg-secondary/30',
              )}
            >
              <span>
                {prefilling ? (
                  <span className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading the director's prompt</span>
                ) : prefillError ? (
                  prefillError
                ) : (
                  <>
                    Filled from {prefill!.label}
                    {storyTitle && <> of <span className="font-medium">{storyTitle}</span></>}. Check the model and price, then generate.
                  </>
                )}
              </span>
              {threadId && (
                <button
                  type="button"
                  onClick={() => setTab('room')}
                  className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Back to the story
                </button>
              )}
            </div>
          )}
          <QuickClip />
        </>
      )}
    </>
  );
}
