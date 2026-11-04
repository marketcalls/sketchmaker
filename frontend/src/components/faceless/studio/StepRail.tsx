import { useRef } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { STUDIO_STEPS, type FacelessProject, type StepRun, type StudioStep } from '@/api/faceless';
import { StepStateChip } from '../shared';
import { stepProgress, stepState } from './stepState';

// Vertical rail on large screens, a scrollable tab bar below. Arrow keys
// move between steps (WAI-ARIA tabs pattern).
export function StepRail({
  project,
  runs,
  active,
  onChange,
}: {
  project: FacelessProject;
  runs: StepRun[];
  active: StudioStep;
  onChange: (s: StudioStep) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = STUDIO_STEPS.length;
    let j = -1;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') j = (i + 1) % n;
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') j = (i - 1 + n) % n;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = n - 1;
    if (j >= 0) {
      e.preventDefault();
      refs.current[j]?.focus();
      onChange(STUDIO_STEPS[j].id);
    }
  };

  return (
    <div
      role="tablist"
      aria-label="Production steps"
      aria-orientation="vertical"
      className="-mx-4 flex gap-1 overflow-x-auto border-b border-border px-4 pb-2 lg:mx-0 lg:flex-col lg:overflow-visible lg:border-b-0 lg:px-0 lg:pb-0"
    >
      {STUDIO_STEPS.map((s, i) => {
        const state = stepState(project, runs, s.id);
        const selected = s.id === active;
        return (
          <button
            key={s.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={`studio-tab-${s.id}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`studio-panel-${s.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(s.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              'relative flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:w-full',
              selected ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] tabular',
                selected ? 'border-primary text-foreground' : 'border-border text-muted-foreground',
              )}
            >
              {state === 'done' ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <span className={cn('whitespace-nowrap', selected && 'font-medium')}>{s.label}</span>
            {s.id === 'captions' && (
              <span className="hidden text-[11px] text-muted-foreground/70 xl:inline">Free</span>
            )}
            {state !== 'idle' && state !== 'done' && (
              <span className="ml-auto pl-1">
                <StepStateChip state={state} progress={stepProgress(project, s.id)} compact />
              </span>
            )}
            {state === 'done' && <span className="sr-only">Done</span>}
          </button>
        );
      })}
    </div>
  );
}
