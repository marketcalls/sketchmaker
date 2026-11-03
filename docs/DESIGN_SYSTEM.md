# SketchMaker Design System: "Calm Studio"

A professional creative tool: dark, quiet surfaces, one accent, motion that
only explains what changed. The reference implementation lives in
`frontend/src/index.css` (tokens), `frontend/src/components/ui/` (kit),
`frontend/src/components/motion/` (motion primitives) and the layout shell
(`frontend/src/components/layout/`).

## Principles

1. The work is the hero. Generated images and videos carry the colour; the
   interface stays neutral around them.
2. Nothing glows. No coloured shadows, text shadows, pulsing, beams, aurora
   blobs, grain or floating elements. Light comes from content, not chrome.
3. Motion is information. It shows that something appeared, moved or
   finished, briefly and gently, then gets out of the way.
4. One accent. Lime (`primary`) marks the one primary action in a view, the
   active navigation item's icon, focus rings, selected states and progress.
   It is never a background wash for decoration.
5. Smooth means predictable. No layout jumps, no surprise scroll, no dead
   clicks, clear feedback within 100 ms of every action.

## Tokens and surfaces

- Use token classes only: `bg-background`, `bg-card`, `bg-secondary`,
  `bg-muted`, `bg-accent`, `text-foreground`, `text-muted-foreground`,
  `border-border`, `text-primary`, `bg-primary`. Never raw `text-white`,
  `bg-black`, `bg-gray-*` or hex values (content swatches such as logo
  backdrops are the only exception).
- Semantic colours: `destructive` (errors, deletes), `success` (done),
  `warning` (attention). Nothing else: no purple, cyan, pink or gradient text.
- Surfaces: `Card` (border plus `bg-card`, `shadow-card` which is nearly
  flat). `panel` for the same look on a plain div. `glass` only for sticky
  bars and controls laid over imagery.
- Radii: controls `rounded-md`, cards and panels `rounded-xl`, large media
  `rounded-xl`, pills (`rounded-full`) only for avatars, toggles and dots.
- Shadows: `shadow-card` or none. `shadow-glow`, `shadow-glow-sm`,
  `text-glow`, `glow-blob`, `animate-pulse-glow`, `animate-aurora`,
  `animate-float`, `animate-border-beam` are retired: the tokens now render
  as nothing or as plain elevation, and new code must not use them.

## Typography

- UI text: Hanken Grotesk (default sans). Weights 400, 500, 600.
- Page titles in the app: `text-2xl font-semibold tracking-tight` (sans).
  Instrument Serif (`font-display`, `headline`) is for public marketing
  pages only (landing hero, pricing, about), never in tool pages, dialogs or
  admin.
- Mono (`font-mono`) only for real technical values: credits, prices, ids,
  seeds, sizes, durations, timestamps, model ids. Not for labels, kickers or
  buttons. Add `tabular` (tabular figures) to numbers that change or align.
- Sentence case everywhere. No all-caps kickers with wide tracking above
  titles. A section label is `text-xs font-medium text-muted-foreground`.
- Body copy max width about 65 characters (`max-w-prose`); `text-pretty` on
  paragraphs, `text-balance` on titles.

## Page anatomy (app and admin)

```tsx
<header className="mb-6 flex flex-wrap items-end justify-between gap-4">
  <div>
    <h1 className="text-2xl font-semibold tracking-tight">Page title</h1>
    <p className="mt-1 text-sm text-muted-foreground">One plain sentence about what this does.</p>
  </div>
  {/* optional: the page's one primary action, or filters */}
</header>
```

- Tool pages: form or controls first, results next to or below them; on
  `lg` two columns, on mobile stacked with the form first.
- Admin pages: the same header, then filters in one row, then the table.
  Tables: sticky header, `tabular` numbers right-aligned, row hover
  `hover:bg-accent/40`, empty and loading rows inside the table frame.
  Use the kit: `<Table stickyHeader density="compact">` (scrolls inside a box
  capped at 70vh, `containerClassName` changes it), `TableLoadingRows`,
  `TableEmptyRow`, and from `components/common/`: `SavedNote` (quiet "Saved"),
  `TablePagination`, `StatusBadge` with `statusVariant`. Changing a filter
  or search returns to page 1; rows stay visible at reduced opacity while
  data reloads.

## Components

- Buttons: `default` for the one primary action per view; `outline`,
  `secondary`, `ghost` for the rest; `link` for inline text actions.
  `glow` still exists for old call sites and is identical to `default`. No
  hover scale, lift or rotation. A busy button keeps its width, shows a small
  `Loader2 animate-spin` and a verb ("Generating"), and is disabled.
- Badges: `rounded-md`, small. Status: success, warning (processing,
  pending), destructive (failed), outline (neutral). "New" appears only in
  the sidebar, on at most four features at a time.
- Cards: no hover lift, no hover scale. A clickable card may change its
  border on hover (`hover:border-foreground/20`) and must have a focus ring.
- Inputs: visible label, helper text below in `text-xs text-muted-foreground`,
  inline error below in `text-xs text-destructive`. Submit with the button or
  Ctrl+Enter / Cmd+Enter in prompt boxes.
- Dropzones: `rounded-xl border border-dashed border-border bg-secondary/20
  hover:border-foreground/30`; icon muted, not lime.
- Empty states: muted icon (no lime ring), one short heading in sans
  semibold, one sentence, at most one primary button.
- Dialogs: plain overlay (no blur), solid popover surface, short fade.

## States (smoothness)

- Loading a page or list: skeletons in the final layout's shape (`Skeleton`
  or `shimmer` blocks with the same size as the content), never a centred
  spinner on a blank page.
- Generating or rendering: the working surface gets `beam-border` (a steady
  accent outline, no movement), a plain status line ("Generating, about 20
  seconds"), elapsed time when known, a cancel action where supported, and a
  placeholder with the output's aspect ratio so nothing jumps when the result
  arrives.
- Reserve space for media: give image and video slots their aspect ratio
  before the file loads.
- Errors: inline, next to what failed, in plain words (CLAUDE.md error
  rules), with the next step. Toasts only for background events.
- Destructive actions confirm with a dialog naming the thing.
- After an action, keep the user's place: no scroll jumps, keep filters and
  inputs, focus moves to the result or the next field.

## Motion

Allowed, and only these:

- Fade in on mount or route change: opacity only, 150 to 250 ms.
- Small entrance travel: at most 8 px, at most 350 ms (`Reveal`, `fadeUp`).
- List cascade: at most 40 to 50 ms between items, only for the first
  screenful (`Stagger`).
- Layout highlight (active nav, tabs): a plain 200 ms tween, no spring.
- Hover and press: colour and border changes, 150 ms.
- Progress bars filling; `Loader2 animate-spin` inside a busy control.
- Skeleton shimmer (slow, low contrast).

Not allowed: glow, pulse or ping, floating, aurora or background blobs,
rotating or sweeping borders, hover scale, lift or rotate, parallax, blur
transitions, infinite decorative loops (the landing logo marquee is the one
exception, at its slow default), spring overshoot.

`Reveal` and `Stagger` cap distance, duration, delay and interval
internally, so callers cannot exceed these limits. `prefers-reduced-motion`
turns all of it off (global rule in `index.css`).

## Copy

Sentence case, plain verbs, no exclamation marks, no hype words (elevate,
unleash, seamless, magic, next-gen, supercharge). Say what happens and what
it costs: "Generate, 2 credits".

## Don'ts

- No per-page `<style>` blocks; no new dependencies.
- No layout shell duplication: pages render inside MainLayout, AdminLayout
  or AuthLayout, which already apply `PageTransition`.
- Do not change logic while restyling: API calls, stores, handlers, state,
  routing and validation stay as they are unless a UX fix requires it.
- No emoji, icons in copy, em dashes or en dashes in UI strings.
