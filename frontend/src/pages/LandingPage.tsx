import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Image,
  LayoutGrid,
  Camera,
  Check,
  Shirt,
  Eraser,
  Video,
  AudioLines,
  Film,
  Subtitles,
  PenTool,
  Clapperboard,
  ChartColumn,
  Users,
  Mic,
  Music,
  Captions,
  ReceiptText,
  Type,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { PublicHeader, PublicFooter } from '@/components/landing/PublicShell';
import { useAuthStore } from '@/stores/authStore';
import { SEO } from '@/components/SEO';
import { cn } from '@/lib/utils';
import { Stagger, StaggerItem } from '@/components/motion';

const samplePrompt = 'golden hour portrait, 85mm cinematic film still';

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background';

// ---------------------------------------------------------------------------
// Content
// ---------------------------------------------------------------------------

interface Tool {
  href: string;
  icon: LucideIcon;
  title: string;
  description: string;
  tags: string[];
  span?: string;
  studio?: boolean;
}

// Ordered so each md row of three fills: a wide card beside a single one.
const tools: Tool[] = [
  {
    href: '/faceless',
    icon: Clapperboard,
    title: 'Faceless Studio',
    description:
      'Build a cast of recurring characters, run them as a series and draft scripts from templates. Storyboard stills, animated clips, voiceover, music and word-synced captions come together in one render: Shorts up to 3 minutes, long-form up to 15.',
    span: 'md:col-span-2',
    tags: ['Recurring cast', 'Series and templates', '9:16 / 16:9 / 1:1 / 4:5'],
    studio: true,
  },
  {
    href: '/motion-graphics',
    icon: ChartColumn,
    title: 'Motion Graphics',
    description:
      'Data and kinetic typography videos: stat and number reveals, charts, quotes, lists, lower thirds and logo reveals, in your brand kit colours and fonts.',
    tags: ['Kinetic type', 'Animated charts', 'Brand kit'],
    studio: true,
  },
  {
    href: '/stories',
    icon: Film,
    title: 'AI Video Stories',
    description:
      'Text, image and reference to video on five models: MiniMax H3 Max by default, Seedance 2.5, Kling v4, FLUX 3 Max and Gemini Omni Flash 1.1. Priced per second by model and resolution.',
    tags: ['5 video models', 'H3 Max default'],
  },
  {
    href: '/logo',
    icon: PenTool,
    title: 'Logo Studio',
    description:
      'Answer a short brief and get vector SVG logos, then refine, simplify or turn an image into a vector. Recolor, lockups, the brand kit and mockups are free.',
    span: 'md:col-span-2',
    tags: ['SVG', 'Free brand kit', 'Mockups'],
  },
  {
    href: '/generate',
    icon: Image,
    title: 'AI Image Generation',
    description:
      'Nine models, including Flux 3, GPT Image 2.5, Nano Banana 2.1, Ideogram V4.5 and Grok Imagine, with styles and aspect ratios.',
    span: 'md:col-span-2',
    tags: ['9 models', 'Styles'],
  },
  {
    href: '/lip-sync',
    icon: AudioLines,
    title: 'Lip Sync',
    description:
      'Make a portrait speak: upload a face and a voice track and the mouth follows every word, up to 2K. Priced per second of audio.',
    tags: ['Talking video', 'Up to 2K'],
  },
  {
    href: '/magix',
    icon: Camera,
    title: 'Magix Photography',
    description: 'Twenty-two professional portrait styles that keep the face. Studio, editorial, headshot and more.',
    tags: ['22 styles', 'Face preserved'],
  },
  {
    href: '/virtual',
    icon: Shirt,
    title: 'Virtual Try-On',
    description: 'Photo plus garment in, realistic fit out. Built for fashion and outfit planning.',
    tags: ['Fashion'],
  },
  {
    href: '/motion-control',
    icon: Video,
    title: 'Motion Control',
    description:
      'Copy the movement of a reference video onto your character with Kling V3 Standard, V3 Pro or v2.6, up to 30 seconds.',
    tags: ['Kling V3', 'Motion transfer'],
  },
  {
    href: '/explainer',
    icon: LayoutGrid,
    title: 'Visual Explainers',
    description: 'Infographics, flowcharts, timelines and diagrams from a single prompt, up to 4K.',
    tags: ['Infographics'],
  },
  {
    href: '/subtitles',
    icon: Subtitles,
    title: 'Auto Subtitles',
    description: 'Transcription in 10+ languages with styled captions for social.',
    tags: ['10+ languages'],
  },
  {
    href: '/remove-bg',
    icon: Eraser,
    title: 'Background Removal',
    description: 'One click, clean edges, transparent PNG. Built for products and portraits.',
    tags: ['One click'],
  },
];

// The capability ticker, in story order.
const ticker = [
  'Faceless Studio',
  'Motion Graphics',
  'Video Stories',
  'Logo Studio',
  'Lip Sync',
  'Image Generation',
  'Magix Photography',
  'Virtual Try-On',
  'Motion Control',
  'Visual Explainers',
  'Auto Subtitles',
  'Background Removal',
];

const heroStudios: { href: string; label: string; icon: LucideIcon }[] = [
  { href: '/faceless', label: 'Faceless Studio', icon: Clapperboard },
  { href: '/motion-graphics', label: 'Motion Graphics', icon: ChartColumn },
  { href: '/stories', label: 'Stories', icon: Film },
  { href: '/logo', label: 'Logo Studio', icon: PenTool },
  { href: '/lip-sync', label: 'Lip Sync', icon: AudioLines },
];

const stats = [
  { value: '5', label: 'Video models' },
  { value: '9', label: 'Image models' },
  { value: '15 min', label: 'Long-form faceless video' },
  { value: '4K', label: 'Max image resolution' },
];

const steps = [
  {
    number: '01',
    title: 'Describe it',
    description: 'Start from a prompt, a template or a brief. Scripts are drafted for you.',
  },
  {
    number: '02',
    title: 'See the price first',
    description:
      'Every paid step shows its estimated cost before you confirm. Pick the model and resolution that fit the job.',
  },
  {
    number: '03',
    title: 'Render and ship',
    description: 'Download the finished file. If the network drops mid-job, the paid result is not thrown away.',
  },
];

const costFacts = [
  {
    title: 'An estimate before every paid step',
    body: 'Each model has its own price, so the cost depends on the model, the resolution and the length. You see the estimate before you confirm.',
  },
  {
    title: 'Paid results are kept',
    body: 'If the network drops or a key is rejected while a job runs, the app keeps checking it, so a result you paid for is not thrown away.',
  },
  {
    title: 'Free where it should be',
    body: 'Rendering on your machine, exporting, and the logo brand kit and mockups cost nothing.',
  },
];

// Faceless Studio pipeline, one row per step with what it costs.
const facelessSteps: { icon: LucideIcon; title: string; detail: string; price: string }[] = [
  { icon: Users, title: 'Cast', detail: 'Recurring characters with a character bible; real people only with their consent', price: 'Free, reference sheet per image' },
  { icon: Type, title: 'Script', detail: 'Drafted from a template or your idea, scene by scene, with originality and compliance checks', price: 'LLM tokens on your key' },
  { icon: Image, title: 'Storyboard', detail: 'A still for every scene, keeping your cast on model', price: 'Estimated per image' },
  { icon: Film, title: 'Clips', detail: 'Animated shots on MiniMax H3 Max', price: 'Estimated per second' },
  { icon: Mic, title: 'Voice', detail: 'Narration and dialogue with a voice per character', price: 'Estimated per character' },
  { icon: Music, title: 'Music', detail: 'An original score that ducks under the voice', price: 'Estimated per minute' },
  { icon: Captions, title: 'Captions', detail: 'Word-synced styles placed clear of each platform\'s buttons', price: 'Included' },
  { icon: Clapperboard, title: 'Render', detail: 'One finished video, ready to upload', price: 'Free, runs on your machine' },
  { icon: ReceiptText, title: 'Package', detail: 'Titles, description, tags, chapters and disclosure advice; thumbnails on request', price: 'LLM tokens, thumbnails per image' },
];

const motionGraphicsBits = [
  'Kinetic typography',
  'Stat and number reveals',
  'Bar, line and pie charts',
  'Quotes and lists',
  'Lower thirds',
  'Logo reveals',
];

/** A still sample: the prompt and four empty slots for its results. */
function HeroSample() {
  return (
    <div className="panel mx-auto w-full max-w-2xl rounded-xl p-4 text-left sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-sm text-foreground/90">{samplePrompt}</p>
        <span className="shrink-0 text-xs text-muted-foreground">Example prompt</span>
      </div>
      <div className="mt-4 grid grid-cols-4 gap-2">
        {[0, 1, 2, 3].map((slot) => (
          <div key={slot} className="aspect-square rounded-lg bg-muted/50" aria-hidden="true" />
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span className="truncate font-mono">Flux 3 / 1:1</span>
        <span className="shrink-0 font-mono tabular">Priced per model</span>
      </div>
    </div>
  );
}

function SectionHeader({
  id,
  title,
  children,
  center,
}: {
  id?: string;
  title: string;
  children?: ReactNode;
  center?: boolean;
}) {
  return (
    <div className={cn('mb-10 max-w-2xl md:mb-12', center && 'mx-auto text-center')}>
      <h2 id={id} className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
        {title}
      </h2>
      {children && <p className="mt-4 text-pretty text-base leading-relaxed text-muted-foreground">{children}</p>}
    </div>
  );
}

/** The public home page. It calls no API of its own and never redirects: only
 * the auth check App already runs decides which buttons the visitor sees. */
export function LandingPage() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const startHref = isAuthenticated ? '/generate' : '/login';

  return (
    <div className="min-h-screen bg-background">
      <SEO title="Faceless Videos, Motion Graphics and Images" />

      <PublicHeader />

      {/* Hero */}
      <section className="px-4 pb-16 pt-32 sm:pt-40 md:pb-24">
        <Stagger className="mx-auto max-w-4xl text-center">
          <StaggerItem>
            <h1 className="headline text-5xl sm:text-6xl md:text-7xl lg:text-8xl">
              Direct the whole
              <br />
              production.
            </h1>
          </StaggerItem>
          <StaggerItem>
            <p className="mx-auto mt-6 max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
              <span className="text-foreground">
                Faceless videos with a recurring cast, motion graphics, video on five models, lip sync, vector logos and images
              </span>
              , in one studio. Every paid step shows an estimated price before you run it.
            </p>
          </StaggerItem>
          <StaggerItem>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button size="xl" asChild className="w-full sm:w-auto">
                <Link to={startHref}>
                  Start creating
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </Button>
              <Button size="xl" variant="outline" asChild className="w-full sm:w-auto">
                <a href="#studio">See the tools</a>
              </Button>
            </div>
          </StaggerItem>
          <StaggerItem>
            <ul className="mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-center gap-2" aria-label="Studios">
              {heroStudios.map((s) => (
                <li key={s.href}>
                  <Link
                    to={s.href}
                    className={cn(
                      'inline-flex min-h-[40px] items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors duration-150 hover:border-foreground/30 hover:text-foreground',
                      focusRing,
                    )}
                  >
                    <s.icon className="h-4 w-4" aria-hidden="true" />
                    {s.label}
                  </Link>
                </li>
              ))}
            </ul>
          </StaggerItem>
          <StaggerItem className="mt-14">
            <HeroSample />
          </StaggerItem>
        </Stagger>
      </section>

      {/* Capability ticker: the page's one slow loop */}
      <div className="overflow-hidden border-y border-border py-5">
        <div className="flex w-max animate-marquee">
          {[0, 1].map((copy) => (
            <div key={copy} className="flex items-center whitespace-nowrap" aria-hidden={copy === 1}>
              {ticker.map((label) => (
                <span key={label} className="flex items-center">
                  <span className="px-8 text-lg font-medium text-muted-foreground/70 sm:text-xl">{label}</span>
                  <span className="h-1 w-1 rounded-full bg-border" aria-hidden="true" />
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Stats */}
      <section className="px-4 py-16 md:py-20" aria-label="At a glance">
        <dl className="mx-auto grid max-w-5xl grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="flex flex-col-reverse bg-card p-6 text-center sm:p-8">
              <dt className="mt-2 text-sm text-muted-foreground">{stat.label}</dt>
              <dd className="tabular text-3xl font-semibold tracking-tight sm:text-4xl">{stat.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Studio (tools grid) */}
      <section id="studio" className="scroll-mt-20 px-4 py-16 md:py-24">
        <div className="mx-auto max-w-6xl">
          <SectionHeader title="From a script to a finished video, in one place">
            Studios for faceless video and motion graphics, plus every single-shot tool a creator reaches for.
            Estimated prices come from the live table and are shown before you confirm.
          </SectionHeader>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
            {tools.map((tool) => (
              <Link
                key={tool.title}
                to={tool.href}
                className={cn('group block h-full rounded-xl', focusRing, tool.span)}
              >
                <Card className="flex h-full flex-col p-6 transition-colors duration-150 group-hover:border-foreground/20 sm:p-7">
                  <div className="flex items-start justify-between gap-3">
                    <tool.icon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                    {tool.studio && <span className="text-xs text-muted-foreground">Studio</span>}
                  </div>
                  <h3 className="mt-4 text-lg font-semibold tracking-tight">{tool.title}</h3>
                  <p className="mt-2 flex-1 text-pretty text-sm leading-relaxed text-muted-foreground">{tool.description}</p>
                  <ul className="mt-4 flex flex-wrap gap-1.5" aria-label="Highlights">
                    {tool.tags.map((tag) => (
                      <li
                        key={tag}
                        className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground"
                      >
                        {tag}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 flex items-center justify-between gap-2 border-t border-border pt-3 text-xs text-muted-foreground">
                    <span className="truncate font-mono">Estimated before you run it</span>
                    <ArrowRight className="h-3.5 w-3.5 shrink-0 transition-colors duration-150 group-hover:text-foreground" aria-hidden="true" />
                  </p>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Faceless Studio and Motion Graphics */}
      <section className="border-y border-border px-4 py-16 md:py-24">
        <div className="mx-auto max-w-6xl">
          <SectionHeader title="A channel's worth of video, step by step">
            Each step is its own decision: see what it costs, run it, redo one scene without paying for the
            rest.
          </SectionHeader>

          <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
            <Card className="h-full p-6 sm:p-7">
              <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3">
                <h3 className="text-xl font-semibold tracking-tight">Faceless Studio</h3>
                <span className="text-xs text-muted-foreground">
                  Shorts to 3 min, long-form to 15 min
                </span>
              </div>
              <ol className="divide-y divide-border">
                {facelessSteps.map((step, i) => (
                  <li key={step.title} className="grid grid-cols-[2rem_1fr] gap-3 py-3 sm:grid-cols-[2rem_1fr_auto] sm:items-center">
                    <span className="font-mono text-xs text-muted-foreground tabular">{String(i + 1).padStart(2, '0')}</span>
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 text-sm font-medium">
                        <step.icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                        {step.title}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{step.detail}</p>
                    </div>
                    <span className="col-start-2 font-mono text-xs text-foreground/80 sm:col-start-auto sm:text-right">
                      {step.price}
                    </span>
                  </li>
                ))}
              </ol>
              <div className="mt-6">
                <Button asChild>
                  <Link to="/faceless">
                    Open Faceless Studio <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </Card>

            <Card className="flex h-full flex-col p-6 sm:p-7">
              <h3 className="mb-5 text-xl font-semibold tracking-tight">Motion Graphics</h3>
              <p className="text-pretty text-sm leading-relaxed text-muted-foreground">
                Turn numbers and short copy into animated videos for social, reports and launches. Paste
                your data, pick a template, and every frame follows your brand kit.
              </p>
              <ul className="mt-5 grid flex-1 grid-cols-1 content-start gap-2 sm:grid-cols-2 lg:grid-cols-1">
                {motionGraphicsBits.map((bit) => (
                  <li key={bit} className="flex items-center gap-2 text-sm">
                    <Check className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    {bit}
                  </li>
                ))}
              </ul>
              <p className="mt-5 font-mono text-xs text-muted-foreground">
                Rendering is free on your machine, voiceover is estimated before you run it
              </p>
              <div className="mt-5">
                <Button variant="outline" asChild>
                  <Link to="/motion-graphics">
                    Open Motion Graphics <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </Card>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-b border-border px-4 py-16 md:py-24">
        <div className="mx-auto max-w-6xl">
          <SectionHeader title="From idea to upload" center />

          <ol className="grid gap-10 md:grid-cols-3 md:gap-8">
            {steps.map((step) => (
              <li key={step.number} className="border-t border-border pt-5">
                <p className="font-mono text-sm text-muted-foreground tabular">{step.number}</p>
                <h3 className="mt-2 text-lg font-semibold tracking-tight">{step.title}</h3>
                <p className="mt-2 text-pretty text-sm leading-relaxed text-muted-foreground">{step.description}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* What it costs, explained */}
      <section className="px-4 py-16 md:py-24">
        <div className="mx-auto max-w-6xl">
          <SectionHeader title="Pay for what you run, nothing else" />

          <div className="grid gap-8 md:grid-cols-3">
            {costFacts.map((item) => (
              <div key={item.title} className="border-t border-border pt-5">
                <h3 className="text-base font-semibold tracking-tight">{item.title}</h3>
                <p className="mt-2 text-pretty text-sm leading-relaxed text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Closing call to action */}
      <section className="border-t border-border px-4 py-20 md:py-28">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
            Start with your own keys
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-pretty text-base text-muted-foreground sm:text-lg">
            Then pay only for the steps you run, with the estimated price shown before each one.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button size="lg" asChild>
              <Link to={startHref}>Start creating</Link>
            </Button>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
