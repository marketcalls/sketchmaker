import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// Small building blocks shared by the Story Room panels.

export function FieldLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn('mb-1 block text-xs font-medium text-muted-foreground', className)}>
      {children}
    </span>
  );
}

// Metadata chip: shot type, camera, transition, duration.
export function Chip({ children, accent = false, className }: { children: ReactNode; accent?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border px-1.5 py-px text-[11px]',
        accent ? 'border-border bg-secondary/60 text-foreground' : 'border-border bg-secondary/40 text-muted-foreground',
        className,
      )}
    >
      {children}
    </span>
  );
}

const inputBase =
  'w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 hover:border-border focus-visible:border-ring focus-visible:bg-secondary/40 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60';

/**
 * Text that saves when it loses focus (or on Enter for one line), so a hand
 * edit is one save rather than one per keystroke. Escape puts it back.
 */
export function EditableText({
  value, onCommit, multiline = false, placeholder, disabled, className, label, maxLength, rows = 2,
}: {
  value: string;
  onCommit: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  label?: string;
  maxLength?: number;
  rows?: number;
}) {
  const [draft, setDraft] = useState(value ?? '');
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setDraft(value ?? '');
  }, [value]);

  const commit = () => {
    focused.current = false;
    if (draft !== (value ?? '')) onCommit(draft);
  };

  const shared = {
    value: draft,
    placeholder,
    disabled,
    maxLength,
    'aria-label': label ?? placeholder,
    onFocus: () => {
      focused.current = true;
    },
    onBlur: commit,
  };

  const field = multiline ? (
    <textarea
      {...shared}
      rows={rows}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          setDraft(value ?? '');
          (e.target as HTMLTextAreaElement).blur();
        }
      }}
      className={cn(inputBase, 'resize-none leading-relaxed [field-sizing:content]', className)}
    />
  ) : (
    <input
      {...shared}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        if (e.key === 'Escape') {
          setDraft(value ?? '');
          (e.target as HTMLInputElement).blur();
        }
      }}
      className={cn(inputBase, className)}
    />
  );

  if (!label) return field;
  return (
    <label className="block">
      <FieldLabel className="px-2">{label}</FieldLabel>
      {field}
    </label>
  );
}

// Inline **bold** inside chat prose.
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4
      ? <strong key={i} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>
      : part,
  );
}

const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

/**
 * Chat text as readable prose: paragraphs, bulleted and numbered lists.
 * `trailing` is placed at the end of the last line (the caret of a reply
 * that is still being written).
 */
export function Prose({ text, className, trailing }: { text: string; className?: string; trailing?: ReactNode }) {
  const blocks = text.replace(/\r\n/g, '\n').split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  const tail = (i: number, j: number, count: number) => (i === blocks.length - 1 && j === count - 1 ? trailing : null);
  return (
    <div className={cn('space-y-3 text-sm leading-relaxed', className)}>
      {blocks.length === 0 && trailing && <p>{trailing}</p>}
      {blocks.map((block, i) => {
        const lines = block.split('\n').filter((l) => l.trim());
        if (lines.every((l) => BULLET.test(l))) {
          return (
            <ul key={i} className="list-disc space-y-1 pl-5 marker:text-muted-foreground">
              {lines.map((l, j) => <li key={j}>{inline(l.replace(BULLET, ''))}{tail(i, j, lines.length)}</li>)}
            </ul>
          );
        }
        if (lines.every((l) => NUMBERED.test(l))) {
          return (
            <ol key={i} className="list-decimal space-y-1 pl-5 marker:font-mono marker:text-xs marker:text-muted-foreground">
              {lines.map((l, j) => <li key={j}>{inline(l.replace(NUMBERED, ''))}{tail(i, j, lines.length)}</li>)}
            </ol>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {inline(l)}
                {tail(i, j, lines.length)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

const KNOWN_SECTIONS = /^(setting|visual direction|audio direction|important constraints|constraints|look|music|cast|characters|product|logline|synopsis|notes)$/i;
const SCENE_HEAD = /^(scene\s+\d+)\s*(\(([^)]*)\))?$/i;
// Name (delivery): "line"
const DIALOGUE = /^([^:()"“]{1,40}?)\s*(?:\(([^)]*)\))?\s*:\s*["“](.+?)["”]?\s*$/;

type TreatmentBlock =
  | { kind: 'heading'; title: string; time: string | null; rest: string }
  | { kind: 'dialogue'; name: string; delivery: string | null; line: string }
  | { kind: 'bullet'; text: string }
  | { kind: 'text'; text: string }
  | { kind: 'gap' };

function parseTreatment(text: string): TreatmentBlock[] {
  const out: TreatmentBlock[] = [];
  for (const raw of text.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trim().replace(/^\*\*(.+?)\*\*/, '$1');
    if (!line) {
      if (out.length && out[out.length - 1].kind !== 'gap') out.push({ kind: 'gap' });
      continue;
    }
    const dialogue = DIALOGUE.exec(line);
    if (dialogue) {
      out.push({ kind: 'dialogue', name: dialogue[1].trim(), delivery: dialogue[2]?.trim() || null, line: dialogue[3].trim() });
      continue;
    }
    const colon = line.indexOf(':');
    if (colon > 0 && colon <= 60) {
      const label = line.slice(0, colon).replace(/\*/g, '').trim();
      const rest = line.slice(colon + 1).trim();
      const scene = SCENE_HEAD.exec(label);
      if (scene) {
        out.push({ kind: 'heading', title: scene[1], time: scene[3] ?? null, rest });
        continue;
      }
      if (KNOWN_SECTIONS.test(label)) {
        out.push({ kind: 'heading', title: label, time: null, rest });
        continue;
      }
    }
    if (BULLET.test(line)) {
      out.push({ kind: 'bullet', text: line.replace(BULLET, '') });
      continue;
    }
    out.push({ kind: 'text', text: line });
  }
  return out;
}

/** The production treatment, typeset like a director's document. */
export function Treatment({ text }: { text: string }) {
  const blocks = parseTreatment(text);
  return (
    <div className="space-y-2 text-[13px] leading-relaxed text-foreground/90">
      {blocks.map((b, i) => {
        if (b.kind === 'gap') return <div key={i} className="h-1" />;
        if (b.kind === 'heading') {
          return (
            <div key={i} className={cn(i > 0 && 'pt-3')}>
              <p className="flex flex-wrap items-baseline gap-x-2 border-b border-border/70 pb-1">
                <span className="text-sm font-semibold text-foreground">{b.title}</span>
                {b.time && <span className="font-mono text-[11px] tabular text-muted-foreground">{b.time}</span>}
              </p>
              {b.rest && <p className="mt-1.5">{b.rest}</p>}
            </div>
          );
        }
        if (b.kind === 'dialogue') {
          return (
            <div key={i} className="mx-auto max-w-[85%] py-0.5 text-center">
              <p className="font-mono text-[11px] uppercase text-foreground">{b.name}</p>
              {b.delivery && <p className="text-xs italic text-muted-foreground">({b.delivery})</p>}
              <p className="mt-0.5">{b.line}</p>
            </div>
          );
        }
        if (b.kind === 'bullet') {
          return (
            <p key={i} className="relative pl-4">
              <span className="absolute left-0 top-[0.6em] h-1 w-1 rounded-full bg-muted-foreground" />
              {b.text}
            </p>
          );
        }
        return <p key={i}>{b.text}</p>;
      })}
    </div>
  );
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={!text}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1800);
        } catch {
          // Clipboard blocked: nothing to show beyond the button not changing.
        }
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : label}
    </Button>
  );
}

// A compact native select styled like the inline fields, for dense rows.
export function InlineSelect<T extends string>({
  value, options, onChange, disabled, label, render,
}: {
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
  disabled?: boolean;
  label: string;
  render?: (v: T) => string;
}) {
  return (
    <label className="block min-w-0">
      <FieldLabel>{label}</FieldLabel>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as T)}
        className="h-8 w-full rounded-md border border-input bg-secondary/40 px-2 font-mono text-xs text-foreground focus-visible:border-ring focus-visible:outline-none disabled:opacity-60"
      >
        {options.map((o) => (
          <option key={o} value={o} className="bg-popover text-foreground">
            {render ? render(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}
