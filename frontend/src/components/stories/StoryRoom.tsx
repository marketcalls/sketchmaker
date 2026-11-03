import { useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, MessagesSquare, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import { imageProgress, type StoryFormat } from '@/api/storyRoom';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { ThreadList } from './ThreadList';
import { StoryChat } from './StoryChat';
import { StoryTab } from './StoryTab';
import { CastTab } from './CastTab';
import { ShotListTab } from './ShotListTab';
import { MakeVideoTab, type ClipSource } from './MakeVideoTab';

type Pane = 'threads' | 'chat' | 'story';
type PanelTab = 'story' | 'cast' | 'shots' | 'video';

const PANEL_TABS: { id: PanelTab; label: string }[] = [
  { id: 'story', label: 'Story' },
  { id: 'cast', label: 'Cast' },
  { id: 'shots', label: 'Shot list' },
  { id: 'video', label: 'Make video' },
];

// While a turn runs elsewhere (another tab, or after a proxy timeout), check
// the thread on this interval until the reply lands.
const BUSY_POLL_MS = 4000;

/**
 * The Story Room: threads on the left, the conversation with the director in
 * the middle, the story document on the right. Below lg the three columns
 * become tabs.
 */
export function StoryRoom({
  threadId, onThreadChange, onOpenClip,
}: {
  threadId: number | null;
  onThreadChange: (id: number | null) => void;
  onOpenClip: (threadId: number, source: ClipSource) => void;
}) {
  const {
    thread, threadLoading, threadError, sending, saving, dirty, saveError, saveNotice,
    loadConfig, loadThreads, openThread, closeThread, refreshThread, createThread, setComposer,
    retrySave, dismissSaveNotice,
  } = useStoryRoomStore();
  const [pane, setPane] = useState<Pane>(threadId ? 'chat' : 'threads');
  const [panelTab, setPanelTab] = useState<PanelTab>('story');
  const [creating, setCreating] = useState<StoryFormat | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
    loadThreads();
  }, [loadConfig, loadThreads]);

  useEffect(() => {
    if (threadId) openThread(threadId);
    else closeThread();
  }, [threadId, openThread, closeThread]);

  const busy = !!thread?.busy && !sending;
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => refreshThread(), BUSY_POLL_MS);
    return () => window.clearInterval(t);
  }, [busy, refreshThread]);

  const open = (id: number) => {
    onThreadChange(id);
    setPane('chat');
  };

  const create = async (format: StoryFormat) => {
    setCreating(format);
    setCreateError(null);
    try {
      const t = await createThread(format);
      onThreadChange(t.id);
      setPane('chat');
      setPanelTab('story');
    } catch (err) {
      setCreateError(getErrorMessage(err, 'A new story could not be started. Please try again.'));
    } finally {
      setCreating(null);
    }
  };

  const story = thread?.story ?? null;
  const locked = sending || !!thread?.busy;
  const progress = imageProgress(story);

  return (
    <div className="flex flex-col">
      {/* Mobile: the three columns as tabs */}
      <div className="mb-3 grid grid-cols-3 gap-1 rounded-md border border-border bg-secondary/40 p-1 lg:hidden">
        {(['threads', 'chat', 'story'] as Pane[]).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPane(p)}
            className={cn(
              'rounded py-2 text-sm capitalize transition-colors duration-150',
              pane === p ? 'bg-background text-foreground shadow-card' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {p}
          </button>
        ))}
      </div>

      {createError && (
        <p className="mb-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{createError}</p>
      )}

      <div className="grid h-[calc(100dvh-15rem)] min-h-[520px] grid-cols-1 gap-4 lg:h-[calc(100dvh-13rem)] lg:grid-cols-[230px_minmax(0,1fr)_minmax(360px,420px)]">
        {/* Threads */}
        <aside className={cn('min-h-0 lg:block', pane === 'threads' ? 'block' : 'hidden')}>
          <ThreadList activeId={thread?.id ?? threadId} onOpen={open} onCreate={create} creating={creating} />
        </aside>

        {/* Chat */}
        <main className={cn('min-h-0 min-w-0 rounded-xl border border-border bg-card/40 p-4 lg:block', pane === 'chat' ? 'block' : 'hidden')}>
          {thread ? (
            <StoryChat thread={thread} />
          ) : threadLoading ? (
            <div className="flex h-full flex-col gap-4" aria-busy="true" aria-label="Loading story">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="ml-auto h-12 w-2/3 rounded-xl" />
              <div className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/6" />
              </div>
              <Skeleton className="mt-auto h-24 w-full rounded-xl" />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <MessagesSquare className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
              <p className="mt-3 text-base font-semibold">{threadError ? 'This story could not be opened' : 'Develop a story with a director'}</p>
              <p className="mt-1 max-w-md text-sm text-muted-foreground">
                {threadError ?? 'Give a one line brief. You get a full treatment, a cast and a shot list, then reference images to approve, then video.'}
              </p>
              <div className="mt-5 flex gap-2">
                <Button onClick={() => create('story')} disabled={creating !== null}>
                  {creating === 'story' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} New story
                </Button>
                <Button variant="outline" onClick={() => create('ad')} disabled={creating !== null}>
                  {creating === 'ad' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} New ad
                </Button>
              </div>
            </div>
          )}
        </main>

        {/* Story panel */}
        <aside className={cn('min-h-0 min-w-0 flex-col rounded-xl border border-border bg-card/40 lg:flex', pane === 'story' ? 'flex' : 'hidden')}>
          {thread && story ? (
            <>
              <div className="flex items-center justify-between gap-2 border-b border-border px-3 pt-3">
                <div className="flex gap-0.5 overflow-x-auto">
                  {PANEL_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setPanelTab(t.id)}
                      className={cn(
                        '-mb-px whitespace-nowrap border-b-2 px-2.5 pb-2 text-sm transition-colors',
                        panelTab === t.id ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
                      )}
                    >
                      {t.label}
                      {t.id === 'cast' && progress.total > 0 && (
                        <span className={cn('ml-1.5 font-mono text-[10px] tabular', progress.approved === progress.total ? 'text-success' : 'text-muted-foreground')}>
                          {progress.approved}/{progress.total}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
                <span className="shrink-0 pb-2 text-[11px] text-muted-foreground">
                  {saving || dirty ? (
                    <span className="flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> Saving</span>
                  ) : saveError ? (
                    <button type="button" onClick={retrySave} className="flex items-center gap-1 text-destructive hover:underline">
                      <AlertTriangle className="h-3 w-3" /> Retry save
                    </button>
                  ) : (
                    <span className="flex items-center gap-1 font-mono tabular"><Check className="h-3 w-3" /> v{thread.storyVersion}</span>
                  )}
                </span>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                {locked && (
                  <p className="mb-3 rounded-lg border border-border bg-secondary/30 p-2 text-xs text-muted-foreground">
                    The director is updating the story. Editing opens again when the reply arrives.
                  </p>
                )}
                {saveError && (
                  <p className="mb-3 rounded-lg border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">{saveError}</p>
                )}
                {saveNotice && (
                  <div className="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-2 text-xs text-warning">
                    {saveNotice}{' '}
                    <button type="button" onClick={dismissSaveNotice} className="underline">Dismiss</button>
                  </div>
                )}
                {panelTab === 'story' && (
                  <StoryTab
                    story={story}
                    disabled={locked}
                    onAnswer={(q) => {
                      setComposer(`On "${q}": `);
                      setPane('chat');
                    }}
                  />
                )}
                {panelTab === 'cast' && <CastTab story={story} disabled={locked} />}
                {panelTab === 'shots' && <ShotListTab story={story} disabled={locked} />}
                {panelTab === 'video' && (
                  <MakeVideoTab
                    story={story}
                    disabled={locked}
                    onOpenClip={(source) => onOpenClip(thread.id, source)}
                    onOpenCast={() => setPanelTab('cast')}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
              The treatment, cast and shot list of the open story appear here.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
