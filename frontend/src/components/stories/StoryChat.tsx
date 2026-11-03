import { useEffect, useRef, useState } from 'react';
import { History, Loader2, Send, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useStoryRoomStore } from '@/stores/storyRoomStore';
import { formatUsd, usePricingStore } from '@/stores/pricingStore';
import type { StoryMessage, StoryThread } from '@/api/storyRoom';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/utils/errors';
import { EditableText, Prose } from './fields';

const STORY_STARTERS = [
  'A 30 second mystery short: a courier finds a letter addressed to her, dated tomorrow.',
  'A quiet three-act short about a lighthouse keeper on his last night before the light is automated.',
  'A 60 second vertical story for social with a hook in the first two seconds: a street musician gets one unexpected listener.',
  'I only have a character: a retired stunt double who now runs a bakery. Help me find the story.',
];

const AD_STARTERS = [
  'A 15 second ad where two friends talk about a new phone at home.',
  'A 30 second ad for a steel water bottle that keeps drinks cold for 24 hours. Call to action: shop now.',
  'A 20 second vertical launch ad for a food delivery app with 50 percent off the first order.',
  'A product demo ad for a budgeting app: the problem, the app, the call to action.',
];

// Distance from the bottom (px) within which the conversation follows new text.
const STICK_PX = 48;

/** Middle column: the conversation with the director and the composer. */
export function StoryChat({ thread }: { thread: StoryThread }) {
  const {
    config, sending, pendingText, streamText, streamStatus, turnError, composer, setComposer, sendMessage, stopTurn,
    clearTurnError, restoreVersion, renameThread, pricePerTurn,
  } = useStoryRoomStore();
  // The price falls back to this table until /config arrives.
  usePricingStore((s) => s.costs);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Whether the reader is at the bottom: new text scrolls into view only then,
  // so scrolling up to reread is never pulled back down.
  const atBottom = useRef(true);

  const price = pricePerTurn();
  const maxChars = config?.limits.maxMessageChars ?? 4000;
  const maxMessages = config?.limits.maxMessages ?? null;
  const full = maxMessages !== null && thread.messages.length >= maxMessages;
  const working = sending || thread.busy;
  const canSend = !!composer.trim() && !working && !full;
  const starters = thread.format === 'ad' ? AD_STARTERS : STORY_STARTERS;
  const empty = thread.messages.length === 0 && !pendingText;
  // A streamed reply is on screen and can be stopped.
  const streaming = sending && streamText !== null;

  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [thread.messages.length, pendingText, working, streamText, streamStatus, turnError]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
  };

  const send = (text: string) => {
    if (working || full || !text.trim()) return;
    setLocalError(null);
    atBottom.current = true;
    sendMessage(text);
  };

  const restore = async (m: StoryMessage) => {
    setRestoring(m.id);
    setLocalError(null);
    try {
      await restoreVersion(m.id);
    } catch (err) {
      setLocalError(getErrorMessage(err, 'That version could not be restored.'));
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Title and running totals */}
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-1 border-b border-border pb-3">
        <div className="min-w-0 flex-1">
          <p className="px-2 text-xs text-muted-foreground">
            {thread.format === 'ad' ? 'Ad' : 'Story'} <span className="font-mono tabular">#{thread.id}</span>
          </p>
          <EditableText
            value={thread.title}
            placeholder={thread.format === 'ad' ? 'Untitled ad' : 'Untitled story'}
            maxLength={200}
            onCommit={(title) => {
              renameThread(title.trim()).catch((err) => setLocalError(getErrorMessage(err, 'The title could not be saved.')));
            }}
            className="text-lg font-semibold tracking-tight"
          />
        </div>
        <p className="px-2 font-mono text-[10px] tabular text-muted-foreground">
          {thread.turnsUsed} {thread.turnsUsed === 1 ? 'reply' : 'replies'}, {formatUsd(thread.estimatedUsd)} spent
        </p>
      </div>

      {/* Conversation */}
      <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto py-4 pr-1">
        {empty && (
          <div className="mx-auto max-w-xl py-6">
            <p className="text-base font-semibold">{thread.format === 'ad' ? 'Brief the director' : 'Pitch the director'}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              One or two sentences is enough. The first reply is a complete treatment with cast, setting and a shot list; the
              director lists its assumptions so you can change anything.
            </p>
            <div className="mt-5 grid gap-2">
              {starters.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setComposer(s)}
                  className="rounded-lg border border-border bg-secondary/30 px-3 py-2.5 text-left text-sm text-foreground/90 transition-colors hover:border-foreground/20 hover:bg-accent/40"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-5">
          {thread.messages.map((m) =>
            m.role === 'user' ? (
              <div key={m.id} className="ml-auto max-w-[85%] rounded-xl bg-secondary px-3.5 py-2.5 text-sm text-foreground">
                <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
              </div>
            ) : (
              <div key={m.id} className="max-w-[92%]">
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">Director</p>
                <Prose text={m.content} className="text-foreground/95" />
                {m.storyVersion !== null && (
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span className="font-mono tabular">v{m.storyVersion}</span>
                    {m.estimatedUsd > 0 && <span className="font-mono tabular">{formatUsd(m.estimatedUsd)}</span>}
                    {m.storyVersion === thread.storyVersion ? (
                      <span className="text-foreground">Current version</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => restore(m)}
                        disabled={restoring !== null || working}
                        className="flex items-center gap-1 transition-colors hover:text-foreground disabled:opacity-50"
                      >
                        {restoring === m.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <History className="h-3 w-3" />}
                        Restore this version
                      </button>
                    )}
                  </div>
                )}
              </div>
            ),
          )}

          {pendingText && (
            <div className="ml-auto max-w-[85%] rounded-xl bg-secondary px-3.5 py-2.5 text-sm text-foreground">
              <p className="whitespace-pre-wrap leading-relaxed">{pendingText}</p>
            </div>
          )}
          {streaming ? (
            <div className="max-w-[92%]" aria-live="polite">
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">Director</p>
              <Prose
                text={streamText ?? ''}
                className="text-foreground/95"
                trailing={
                  !streamStatus && (
                    <span aria-hidden className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] bg-foreground/60" />
                  )
                }
              />
              {streamStatus && (
                <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                  {streamStatus}
                </p>
              )}
            </div>
          ) : (
            working && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                The director is writing. Treatment and shot list update when the reply arrives.
              </div>
            )
          )}

          {turnError && (
            <div
              className={cn(
                'rounded-lg border p-3 text-sm',
                turnError.kind === 'pending' || turnError.kind === 'busy'
                  ? 'border-warning/30 bg-warning/10 text-warning'
                  : 'border-destructive/30 bg-destructive/10 text-destructive',
              )}
            >
              <p>{turnError.message}</p>
              <div className="mt-1.5 flex gap-3 text-xs">
                <button type="button" onClick={clearTurnError} className="text-muted-foreground hover:text-foreground">Dismiss</button>
              </div>
            </div>
          )}
          {localError && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{localError}</p>
          )}
        </div>
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(composer);
        }}
        className={cn('rounded-xl', working && 'beam-border')}
      >
        <div className="rounded-xl border border-border bg-secondary/30 p-2">
          <Textarea
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send(composer);
              }
            }}
            rows={3}
            maxLength={maxChars}
            disabled={full}
            placeholder={
              full
                ? 'This story has reached its message limit. Start a new one to keep going.'
                : empty
                  ? thread.format === 'ad' ? 'Describe the product, the length and the feeling of the ad' : 'Describe your idea'
                  : 'Ask for a change: tighten scene 2, add a jump cut, make the ending land harder'
            }
            className="min-h-[72px] resize-none border-0 bg-transparent text-sm focus-visible:ring-0"
          />
          <div className="flex flex-wrap items-center justify-between gap-2 px-1">
            <span className="text-[11px] text-muted-foreground">
              <span className="font-mono tabular">{composer.length}/{maxChars}</span>
              {maxMessages !== null && `, ${Math.max(0, maxMessages - thread.messages.length)} messages left`}
            </span>
            {streaming ? (
              // Stops the live reply only: the director finishes and saves it on the server.
              <Button type="button" size="sm" variant="outline" onClick={stopTurn} className="gap-1.5">
                <Square className="h-3 w-3 fill-current" />
                Stop
              </Button>
            ) : (
              <Button type="submit" size="sm" disabled={!canSend} className="gap-1.5">
                {working ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                {working ? 'Writing' : 'Send'}
                {price !== undefined && <span className="font-mono text-xs opacity-75">{formatUsd(price)}</span>}
              </Button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
