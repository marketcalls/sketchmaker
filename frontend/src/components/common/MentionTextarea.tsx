import { Fragment, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface MentionItem {
  // What is inserted into the text (for example "#Image2" or "the left character").
  insert: string;
  label: string;
  hint?: string;
  thumbnail?: string;
}

export interface MentionTrigger {
  char: '#' | '@';
  title: string;
  items: MentionItem[];
}

interface MentionTextareaProps {
  value: string;
  onChange: (value: string) => void;
  triggers: MentionTrigger[];
  // Spans of the text to highlight, each with its own class.
  highlights: { pattern: RegExp; className: string }[];
  placeholder?: string;
  rows?: number;
  maxLength?: number;
  disabled?: boolean;
  id?: string;
  'aria-label'?: string;
}

interface OpenMenu {
  trigger: MentionTrigger;
  start: number; // index of the trigger character
  query: string;
}

// The textarea's text is transparent and a mirror underneath draws the same
// text with highlights; both share font, padding and wrapping so they line up.
const SHARED = 'whitespace-pre-wrap break-words px-3 py-2 text-sm leading-6 font-sans';

function renderHighlighted(text: string, highlights: MentionTextareaProps['highlights']): ReactNode[] {
  type Span = { start: number; end: number; className: string };
  const spans: Span[] = [];
  for (const { pattern, className } of highlights) {
    const re = new RegExp(pattern.source, pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`);
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m[0].length === 0) {
        re.lastIndex += 1;
        continue;
      }
      const span = { start: m.index, end: m.index + m[0].length, className };
      if (!spans.some((s) => s.start < span.end && span.start < s.end)) spans.push(span);
    }
  }
  spans.sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let at = 0;
  spans.forEach((s, i) => {
    if (s.start > at) out.push(<Fragment key={`t${i}`}>{text.slice(at, s.start)}</Fragment>);
    out.push(
      <mark key={`m${i}`} className={cn('rounded-sm', s.className)}>
        {text.slice(s.start, s.end)}
      </mark>,
    );
    at = s.end;
  });
  if (at < text.length) out.push(<Fragment key="end">{text.slice(at)}</Fragment>);
  // A trailing newline needs a character after it to keep the mirror's height.
  out.push(<Fragment key="pad">{'​'}</Fragment>);
  return out;
}

// A textarea where typing a trigger character (# or @) opens a list of
// things to insert, and matching spans are highlighted as you type.
export function MentionTextarea({
  value,
  onChange,
  triggers,
  highlights,
  placeholder,
  rows = 3,
  maxLength,
  disabled,
  id,
  'aria-label': ariaLabel,
}: MentionTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const [menu, setMenu] = useState<OpenMenu | null>(null);
  const [active, setActive] = useState(0);

  // Grow with the text instead of scrolling: a scrollbar would narrow the
  // textarea but not the mirror, and the highlights would drift.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  const options = useMemo(() => {
    if (!menu) return [];
    const q = menu.query.toLowerCase();
    return menu.trigger.items.filter(
      (item) => !q || item.insert.toLowerCase().replace(/^[#@]/, '').includes(q) || item.label.toLowerCase().includes(q),
    );
  }, [menu]);

  const detect = (text: string, caret: number) => {
    // The trigger must start a word: at the beginning or after whitespace or
    // an opening bracket, with no space between it and the caret.
    const before = text.slice(0, caret);
    const match = before.match(/(^|[\s([{"'])([#@])([^\s#@]*)$/);
    if (!match) {
      setMenu(null);
      return;
    }
    const trigger = triggers.find((t) => t.char === match[2]);
    if (!trigger || trigger.items.length === 0) {
      setMenu(null);
      return;
    }
    setMenu({ trigger, start: caret - match[3].length - 1, query: match[3] });
    setActive(0);
  };

  const insert = (item: MentionItem) => {
    if (!menu) return;
    const el = textareaRef.current;
    const caret = el?.selectionStart ?? value.length;
    const after = value.slice(caret);
    const spacer = after.startsWith(' ') || after.startsWith(',') || after.startsWith('.') ? '' : ' ';
    const next = value.slice(0, menu.start) + item.insert + spacer + after;
    if (maxLength && next.length > maxLength) return;
    onChange(next);
    setMenu(null);
    const pos = menu.start + item.insert.length + spacer.length;
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(pos, pos);
    });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!menu || options.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => (i - 1 + options.length) % options.length);
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      insert(options[Math.min(active, options.length - 1)]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setMenu(null);
    }
  };

  return (
    <div className="relative">
      <div
        className={cn(
          'relative overflow-hidden rounded-lg border border-input bg-background focus-within:ring-2 focus-within:ring-ring',
          disabled && 'opacity-60',
        )}
      >
        <div ref={mirrorRef} aria-hidden className={cn(SHARED, 'pointer-events-none absolute inset-0 overflow-hidden text-foreground')}>
          {renderHighlighted(value, highlights)}
        </div>
        <textarea
          ref={textareaRef}
          id={id}
          aria-label={ariaLabel}
          value={value}
          rows={rows}
          maxLength={maxLength}
          disabled={disabled}
          placeholder={placeholder}
          spellCheck
          onChange={(e) => {
            onChange(e.target.value);
            detect(e.target.value, e.target.selectionStart ?? e.target.value.length);
          }}
          onKeyDown={onKeyDown}
          onClick={(e) => detect(e.currentTarget.value, e.currentTarget.selectionStart ?? 0)}
          onBlur={() => setTimeout(() => setMenu(null), 150)}
          className={cn(
            SHARED,
            'relative block w-full resize-none overflow-hidden bg-transparent text-transparent caret-foreground outline-none placeholder:text-muted-foreground selection:bg-primary/30 selection:text-transparent disabled:cursor-not-allowed',
          )}
        />
      </div>

      {menu && options.length > 0 && (
        <div
          role="listbox"
          aria-label={menu.trigger.title}
          className="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-card"
        >
          <p className="px-2 pb-1 pt-1.5 text-xs font-medium text-muted-foreground">{menu.trigger.title}</p>
          {options.map((item, i) => (
            <button
              key={item.insert}
              type="button"
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                insert(item);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                i === active ? 'bg-accent text-accent-foreground' : 'text-foreground',
              )}
            >
              {item.thumbnail && <img src={item.thumbnail} alt="" className="h-7 w-7 shrink-0 rounded object-cover" />}
              <span className="font-mono text-xs text-foreground">{item.insert}</span>
              <span className="truncate text-xs text-muted-foreground">{item.label}</span>
              {item.hint && <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">{item.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
