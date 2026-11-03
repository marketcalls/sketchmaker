import { useEffect, useState } from 'react';
import { Archive, ArchiveRestore, Loader2, MoreHorizontal, Plus, Search, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import type { StoryFormat, ThreadSummary } from '@/api/storyRoom';
import { formatRelativeTime } from '@/lib/dateUtils';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';

/** Left column: new story or ad, search, the thread list and the archive. */
export function ThreadList({
  activeId, onOpen, onCreate, creating,
}: {
  activeId: number | null;
  onOpen: (id: number) => void;
  onCreate: (format: StoryFormat) => void;
  creating: StoryFormat | null;
}) {
  const {
    threads, threadsLoading, threadsError, query, setQuery, showArchived, setShowArchived,
    loadThreads, archiveThread, deleteThread,
  } = useStoryRoomStore();
  const [search, setSearch] = useState(query);
  const [deleting, setDeleting] = useState<ThreadSummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Search as the user types, a moment after they stop.
  useEffect(() => {
    if (search === query) return;
    const t = window.setTimeout(() => {
      setQuery(search);
      loadThreads();
    }, 300);
    return () => window.clearTimeout(t);
  }, [search, query, setQuery, loadThreads]);

  const archive = async (t: ThreadSummary) => {
    setActionError(null);
    try {
      await archiveThread(t.id, !showArchived);
    } catch (err) {
      setActionError(getErrorMessage(err, 'That story could not be moved.'));
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="grid grid-cols-2 gap-2">
        <Button size="sm" onClick={() => onCreate('story')} disabled={creating !== null}>
          {creating === 'story' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          New story
        </Button>
        <Button size="sm" variant="outline" onClick={() => onCreate('ad')} disabled={creating !== null}>
          {creating === 'ad' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          New ad
        </Button>
      </div>

      <div className="relative mt-3">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search stories"
          aria-label="Search stories"
          className="h-9 pl-8 text-sm"
        />
      </div>

      <div className="mt-3 flex items-center justify-between px-1">
        <p className="text-xs font-medium text-muted-foreground">
          {showArchived ? 'Archive' : 'Stories'}
        </p>
        <button
          type="button"
          onClick={() => setShowArchived(!showArchived)}
          className="text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          {showArchived ? 'Back to stories' : 'Archive'}
        </button>
      </div>

      {(threadsError || actionError) && (
        <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">{threadsError || actionError}</p>
      )}

      <div className="mt-2 min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-1">
        {threadsLoading && threads.length === 0 && (
          <div className="space-y-2 pt-1">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="space-y-1.5 rounded-lg px-2.5 py-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        )}
        {!threadsLoading && threads.length === 0 && !threadsError && (
          <p className="px-1 pt-2 text-xs text-muted-foreground">
            {query ? 'No stories match that search.' : showArchived ? 'Nothing archived.' : 'Your stories will appear here.'}
          </p>
        )}
        {threads.map((t) => {
          const active = t.id === activeId;
          return (
            <div
              key={t.id}
              className={cn(
                'group relative rounded-lg border px-2.5 py-2 transition-colors',
                active ? 'border-primary/60 bg-primary/10' : 'border-transparent hover:border-border hover:bg-accent/40',
              )}
            >
              <button type="button" onClick={() => onOpen(t.id)} className="block w-full min-w-0 pr-6 text-left">
                <span className={cn('block truncate text-sm', active ? 'text-foreground' : 'text-foreground/90')}>
                  {t.title || (t.format === 'ad' ? 'Untitled ad' : 'Untitled story')}
                </span>
                <span className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span>{t.format === 'ad' ? 'Ad' : 'Story'}</span>
                  <span className="tabular">{t.scenes} {t.scenes === 1 ? 'scene' : 'scenes'}</span>
                  <span className="tabular">{t.shots} {t.shots === 1 ? 'shot' : 'shots'}</span>
                  {t.busy ? (
                    <span className="flex items-center gap-1 text-foreground">
                      <Loader2 className="h-2.5 w-2.5 animate-spin" aria-hidden="true" /> Writing
                    </span>
                  ) : (
                    <span className="truncate">{formatRelativeTime(t.updatedAt)}</span>
                  )}
                </span>
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="Story actions"
                    className="absolute right-1.5 top-2 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100 [@media(hover:none)]:opacity-100"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-40">
                  <DropdownMenuItem onClick={() => archive(t)}>
                    {showArchived ? <ArchiveRestore className="mr-2 h-4 w-4" /> : <Archive className="mr-2 h-4 w-4" />}
                    {showArchived ? 'Restore' : 'Archive'}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setDeleting(t)} className="text-destructive focus:text-destructive">
                    <Trash2 className="mr-2 h-4 w-4" /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        })}
      </div>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this story?"
        description={`"${deleting?.title || 'Untitled'}" and its conversation will be deleted. Characters and environments saved to your library stay.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={async () => {
          if (!deleting) return;
          setActionError(null);
          try {
            await deleteThread(deleting.id);
          } catch (err) {
            setActionError(getErrorMessage(err, 'That story could not be deleted.'));
          }
        }}
      />
    </div>
  );
}
