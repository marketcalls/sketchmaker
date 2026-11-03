import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, Download, Lightbulb, Sparkles, RefreshCw, Plus, Image as ImageIcon, FileText, GitBranch, Clock, LayoutGrid, Boxes, BarChart3, Presentation, Upload, X, Layers, Zap, Megaphone, Hash } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { explainerKey, formatUsd, usePricingStore } from '@/stores/pricingStore';
import { useQualityConfig } from '@/components/quality/QualityBadge';
import { ImageQuality } from '@/components/quality/ImageQuality';
import type { Quality } from '@/api/quality';
import { Stagger, StaggerItem } from '@/components/motion';
import apiClient from '@/api/client';
import { useMediaPicker } from '@/components/media/useMediaPicker';
import { getErrorMessage } from '@/utils/errors';
import { useElapsedSeconds, formatElapsed, ratioToCss, isSubmitShortcut } from '@/components/generate';

// Content types: must match backend CONTENT_TEMPLATES keys in app/routers/explainer.py
const CONTENT_TYPES = [
  { value: 'infographic', label: 'Infographic', icon: BarChart3, description: 'Data visualization with stats' },
  { value: 'flowchart', label: 'Flowchart', icon: GitBranch, description: 'Process and workflow diagrams' },
  { value: 'mindmap', label: 'Mind Map', icon: LayoutGrid, description: 'Hierarchical concept maps' },
  { value: 'timeline', label: 'Timeline', icon: Clock, description: 'Sequential events and milestones' },
  { value: 'comparison', label: 'Comparison', icon: Boxes, description: 'Side-by-side comparisons' },
  { value: 'architecture', label: 'Architecture', icon: Boxes, description: 'System and software diagrams' },
  { value: 'pitchdeck', label: 'Pitch Deck', icon: Presentation, description: 'Investor pitch slides' },
  { value: 'concept', label: 'Concept', icon: Lightbulb, description: 'Visual explanations of ideas' },
  { value: 'ppt_slide', label: 'PPT Slide', icon: Presentation, description: '16:9 talk slide' },
  { value: 'educational_poster', label: 'Edu Poster', icon: Lightbulb, description: 'Classroom poster' },
  { value: 'cheatsheet', label: 'Cheat Sheet', icon: Layers, description: 'Dense reference card' },
  { value: 'saas_landing_hero', label: 'SaaS Hero', icon: Zap, description: 'Landing-page hero' },
  { value: 'dashboard_mockup', label: 'Dashboard', icon: BarChart3, description: 'Analytics UI mockup' },
  { value: 'social_card', label: 'Social Card', icon: Megaphone, description: 'LinkedIn/X post' },
  { value: 'stat_callout', label: 'Stat Callout', icon: Hash, description: 'Hero number visual' },
];

// Visual styles: must match backend VISUAL_STYLES keys in app/routers/explainer.py
const VISUAL_STYLES = [
  { value: 'saas_startup', label: 'SaaS Startup', description: 'Linear/Vercel/Stripe register' },
  { value: 'premium_dark', label: 'Premium Dark', description: 'Dark editorial + neon highlight' },
  { value: 'editorial', label: 'Editorial', description: 'Magazine typographic layout' },
  { value: 'pitch_premium', label: 'Pitch Premium', description: 'YC/a16z investor polish' },
  { value: 'glassmorphism', label: 'Glassmorphism', description: 'Frosted cards on vivid mesh' },
  { value: 'neumorphic', label: 'Neumorphic', description: 'Soft shadows, monochrome surfaces' },
  { value: 'brutalist', label: 'Brutalist', description: 'Raw, opinionated, oversized type' },
  { value: 'isometric', label: 'Isometric', description: '30° axonometric vector' },
  { value: 'blueprint', label: 'Blueprint', description: 'Engineering schematic look' },
  { value: 'professional', label: 'Professional', description: 'Clean, corporate, minimal' },
  { value: 'modern', label: 'Modern', description: 'Sleek, contemporary' },
  { value: 'creative', label: 'Creative', description: 'Artistic and visually striking' },
  { value: 'minimal', label: 'Minimal', description: 'Quiet, elegant breathing room' },
  { value: 'tech', label: 'Tech', description: 'Dark, futuristic, neon' },
  { value: 'educational', label: 'Educational', description: 'Friendly classroom feel' },
];

// Aspect ratios
const ASPECT_RATIOS = [
  { value: '16:9', label: '16:9 Widescreen', description: 'Presentations, YouTube' },
  { value: '4:3', label: '4:3 Standard', description: 'Classic presentations' },
  { value: '1:1', label: '1:1 Square', description: 'Social media posts' },
  { value: '9:16', label: '9:16 Portrait', description: 'Mobile, Stories' },
  { value: '3:2', label: '3:2 Classic', description: 'Photography standard' },
];

// Resolutions
const RESOLUTIONS = [
  { value: '1K', label: '1K, standard', description: 'Default resolution' },
  { value: '2K', label: '2K, high detail', description: 'Higher detail' },
  { value: '4K', label: '4K, largest', description: 'Largest file, most detail' },
];

// Example templates
const EXAMPLE_TEMPLATES: Record<string, string> = {
  infographic: `Create an infographic about the benefits of renewable energy.

Include:
- Key statistics about solar, wind, and hydro power
- Year-over-year growth data
- Environmental impact comparisons
- Cost savings projections
- Icons representing each energy type
- A modern color scheme with green and blue tones`,
  flowchart: `Create a flowchart showing the software development lifecycle (SDLC).

Include these stages:
1. Planning & Requirements
2. Design & Architecture
3. Development & Coding
4. Testing & QA
5. Deployment
6. Maintenance

Show decision points and feedback loops between stages.`,
  mindmap: `Create a mind map about machine learning concepts.

Central topic: Machine Learning
Main branches:
- Supervised Learning (classification, regression)
- Unsupervised Learning (clustering, dimensionality reduction)
- Reinforcement Learning (agents, rewards)
- Deep Learning (neural networks, CNNs, RNNs)

Use color coding for each branch.`,
  timeline: `Create a timeline of major tech innovations from 2000 to 2024.

Key milestones:
- 2007: iPhone launch
- 2008: Android release
- 2010: iPad introduction
- 2012: Deep learning breakthrough
- 2016: AlphaGo victory
- 2022: ChatGPT release
- 2024: Multimodal AI

Include icons and brief descriptions for each milestone.`,
  comparison: `Create a comparison chart between React, Vue, and Angular.

Compare these aspects:
- Learning curve
- Performance
- Community size
- Job market demand
- Bundle size
- Flexibility

Use a professional table or grid layout with icons.`,
  architecture: `Create a system architecture diagram for a cloud-based e-commerce platform.

Components:
- Frontend (React SPA)
- API Gateway
- Microservices (User, Product, Order, Payment)
- Message Queue (Kafka)
- Databases (PostgreSQL, Redis)
- CDN and Storage

Show connections and data flow between components.`,
  pitchdeck: `Create a pitch deck slide about a SaaS startup.

Include:
- Company name and logo placeholder
- Value proposition headline
- Key metrics (ARR, growth rate, users)
- Market opportunity size
- Competitive advantage
- Call to action

Modern, clean design with gradient accents.`,
  concept: `Create a visual explanation of how blockchain works.

Show:
- Block structure (hash, data, timestamp)
- Chain of blocks
- Decentralized network nodes
- Transaction verification process
- Mining/consensus mechanism

Use simple icons and arrows to show the flow.`,
  ppt_slide: `Create a PPT title slide for a talk titled "Why Reasoning Models Change Everything".

Include:
- Headline "Why Reasoning Models Change Everything" centered
- Speaker line "Rajandran R · OpenAlgo · 2026"
- Subtle accent shape on the right
- Footer with talk track and slide number "01 / 24"`,
  educational_poster: `Create a classroom poster on Newton's Three Laws of Motion.

Include:
- Big subject heading "Newton's Laws of Motion"
- Three sectioned cards, one per law, with a tiny diagram each
- A worked example for the second law (F = ma)
- A friendly cartoon scientist mascot in a corner
- Citations row at the bottom`,
  cheatsheet: `Create a Git command cheat sheet.

Include:
- Four columns: Setup, Branching, Sync, Recovery
- Monospace command snippets ("git rebase -i HEAD~3")
- Inline keyboard glyphs for shortcuts
- A small "danger zone" callout for destructive ops
- Tight 4px baseline spacing`,
  saas_landing_hero: `Create a SaaS landing hero for a fictional product "Halo Analytics".

Include:
- Headline "Ship the metric, not the meeting."
- Subhead "Halo turns dashboards into Slack-ready stories."
- Primary CTA button labeled "Start free"
- Floating product screenshot to the right
- Trust strip with five anonymous logo placeholders below`,
  dashboard_mockup: `Create an analytics dashboard UI mockup for a fintech app.

Include:
- Left sidebar with iconified nav (Home, Trades, Portfolio, Reports, Settings)
- Top bar with search and avatar
- Four KPI cards across the top with sparklines
- A primary area chart showing equity curve
- A right-side donut for asset allocation and a recent-trades table`,
  social_card: `Create a LinkedIn share card.

Include:
- Hook line "Most dashboards lie to you. Yours doesn't have to."
- Subline "5 telemetry mistakes most teams make"
- Author chip "Rajandran R · OpenAlgo"
- A single decorative geometric accent in the corner`,
  stat_callout: `Create a statistic callout image.

Include:
- Massive figure "73%"
- Label "of retail traders quit within 24 months"
- One-sentence context line
- Source attribution in small caps "Source: SEBI 2025"
- Single accent color used sparingly`,
};

type ReferenceImage = { url: string; filename: string; previewUrl: string };

export function ExplainerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [contentType, setContentType] = useState('infographic');
  const [prompt, setPrompt] = useState('');
  const [enhancedPrompt, setEnhancedPrompt] = useState('');
  const [style, setStyle] = useState('saas_startup');
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [resolution, setResolution] = useState('2K');
  const [outputFormat, setOutputFormat] = useState('png');
  const [enhanceEnabled, setEnhanceEnabled] = useState(false);
  const [referenceImages, setReferenceImages] = useState<ReferenceImage[]>([]);
  const [isUploadingRef, setIsUploadingRef] = useState(false);

  const [result, setResult] = useState<{ url: string; width: number; height: number; id: number; quality?: Quality | null } | null>(null);
  // Opt-in read-back of the quoted copy, run once the visual is saved.
  const qa = useQualityConfig();
  const [checkSpelling, setCheckSpelling] = useState(false);
  const spellingOn = checkSpelling && !!qa?.available;
  const [isEnhancing, setIsEnhancing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEnhanced, setShowEnhanced] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);

  const { getModelCost } = usePricingStore();

  // Read prompt from URL query parameter
  useEffect(() => {
    const promptParam = searchParams.get('prompt');
    if (promptParam) {
      setPrompt(promptParam);
      // Clear the URL parameter after setting
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);
  // Priced per image by resolution, with a separate price when reference
  // images send the request to GPT Image 2.5's edit endpoint (live table from
  // /pricing/costs).
  const withReferences = referenceImages.length > 0;
  const explainerCost = (() => {
    const base = getModelCost(explainerKey(resolution, withReferences));
    return base !== undefined && spellingOn && qa ? base + qa.estimated_usd : base;
  })();

  const wordCount = prompt.trim() ? prompt.trim().split(/\s+/).length : 0;
  const enhancedWordCount = enhancedPrompt.trim() ? enhancedPrompt.trim().split(/\s+/).length : 0;

  const handleEnhance = async () => {
    if (!prompt.trim()) {
      setError('Describe the visual first.');
      return;
    }

    setIsEnhancing(true);
    setError(null);

    try {
      const response = await apiClient.post('/explainer/enhance', {
        prompt,
        content_type: contentType,
        style,
        aspect_ratio: aspectRatio,
      });

      setEnhancedPrompt(response.data.enhanced_prompt);
      setShowEnhanced(true);
    } catch (err: unknown) {
      const errorMessage = getErrorMessage(err, 'The prompt could not be improved. Please try again.');
      setError(errorMessage);
    } finally {
      setIsEnhancing(false);
    }
  };

  const handleGenerate = async (useEnhanced: boolean = false) => {
    const promptToUse = useEnhanced ? enhancedPrompt : prompt;

    if (!promptToUse.trim()) {
      setError('Describe the visual first.');
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      const response = await apiClient.post('/explainer/generate', {
        topic: promptToUse,
        content_type: contentType,
        style,
        aspect_ratio: aspectRatio,
        resolution: resolution,
        output_format: outputFormat,
        enhance_prompt: !useEnhanced, // Only enhance if not already using enhanced prompt
        reference_image_urls: referenceImages.map((r) => r.url),
        quality_check: spellingOn,
      });

      setResult({
        url: response.data.url || response.data.image?.urls?.png,
        width: response.data.width || response.data.image?.width,
        height: response.data.height || response.data.image?.height,
        id: response.data.id || response.data.image?.id,
        quality: response.data.quality ?? null,
      });
      setShowEnhanced(false);
    } catch (err: unknown) {
      const errorMessage = getErrorMessage(err, 'The visual could not be generated. Please try again.');
      setError(errorMessage);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSubmit = async () => {
    if (enhanceEnabled) {
      await handleEnhance();
    } else {
      await handleGenerate(false);
    }
  };

  const handleDownload = async (format: 'png' | 'jpeg' | 'webp') => {
    if (!result) return;

    try {
      const response = await fetch(result.url);
      const blob = await response.blob();

      let finalBlob = blob;
      if (format !== 'png') {
        const img = new Image();
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        await new Promise<void>((resolve) => {
          img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            if (format === 'jpeg') {
              ctx!.fillStyle = '#FFFFFF';
              ctx!.fillRect(0, 0, canvas.width, canvas.height);
            }
            ctx?.drawImage(img, 0, 0);
            resolve();
          };
          img.src = URL.createObjectURL(blob);
        });

        finalBlob = await new Promise<Blob>((resolve) => {
          canvas.toBlob((b) => resolve(b!), `image/${format}`, format === 'jpeg' ? 0.95 : undefined);
        });
      }

      const url = window.URL.createObjectURL(finalBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `explainer-${contentType}-${Date.now()}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const handleCreateAnother = () => {
    setResult(null);
    setShowEnhanced(false);
    setPrompt('');
    setEnhancedPrompt('');
    setEnhanceEnabled(false);
    referenceImages.forEach((r) => URL.revokeObjectURL(r.previewUrl));
    setReferenceImages([]);
  };

  const handleReferenceUpload = async (files: FileList | File[] | null) => {
    if (!files || files.length === 0) return;
    const remainingSlots = 4 - referenceImages.length;
    if (remainingSlots <= 0) {
      setError('You can add up to 4 reference images. Remove one to add another.');
      return;
    }
    const toUpload = Array.from(files).slice(0, remainingSlots);
    setIsUploadingRef(true);
    setError(null);
    try {
      const uploaded: ReferenceImage[] = [];
      for (const file of toUpload) {
        const fd = new FormData();
        fd.append('image', file);
        const res = await apiClient.post('/explainer/upload-reference', fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        uploaded.push({
          url: res.data.url,
          filename: res.data.filename,
          previewUrl: URL.createObjectURL(file),
        });
      }
      setReferenceImages((prev) => [...prev, ...uploaded]);
    } catch (err) {
      const msg = getErrorMessage(err, 'The reference image could not be uploaded. Please try again.');
      setError(msg);
    } finally {
      setIsUploadingRef(false);
    }
  };

  const referencePicker = useMediaPicker({
    kinds: ['image'],
    multiple: true,
    maxFiles: 4,
    title: 'Add reference images',
    disabled: isUploadingRef || isEnhancing || isGenerating,
    onFiles: handleReferenceUpload,
  });

  const removeReference = (idx: number) => {
    setReferenceImages((prev) => {
      const next = [...prev];
      const [removed] = next.splice(idx, 1);
      if (removed) URL.revokeObjectURL(removed.previewUrl);
      return next;
    });
  };

  const loadTemplate = (type: string) => {
    setContentType(type);
    setPrompt(EXAMPLE_TEMPLATES[type] || '');
    setShowTemplates(false);
  };

  const elapsed = useElapsedSeconds(isGenerating);

  return (
    <Stagger className="space-y-6" interval={0.08}>
      {/* Header */}
      <StaggerItem>
        <header className="mb-2">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Explainer Tool</h1>
          <p className="mt-1 text-sm text-muted-foreground">Turn a description into an infographic, diagram or slide.</p>
        </header>
      </StaggerItem>

      {/* Main Card */}
      <StaggerItem>
        <Card>
        <CardContent className="p-6 space-y-8">
          {/* Step 1: Content Type Selection */}
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Type</h2>
            <p className="mb-4 mt-1 text-sm text-muted-foreground">The kind of visual to make.</p>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {CONTENT_TYPES.map((type) => {
                const Icon = type.icon;
                const isSelected = contentType === type.value;
                return (
                  <button
                    key={type.value}
                    type="button"
                    aria-pressed={isSelected}
                    title={type.description}
                    onClick={() => setContentType(type.value)}
                    className={`flex h-20 items-center justify-center rounded-xl border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:h-24 ${
                      isSelected
                        ? 'ring-2 ring-primary border-primary bg-card'
                        : 'border-border bg-card hover:border-foreground/20'
                    }`}
                  >
                    <div className="text-center px-3">
                      <Icon className={`mx-auto mb-1 h-6 w-6 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                      <span className="text-xs font-medium tracking-tight sm:text-sm">{type.label}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Step 2: Describe Content */}
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Description</h2>
            <p className="mb-4 mt-1 text-sm text-muted-foreground">
              Include the topic, data points, structure and anything that must appear. Ctrl+Enter submits.
            </p>

            <div className="relative">
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (isSubmitShortcut(e) && prompt.trim() && !isEnhancing && !isGenerating) {
                    e.preventDefault();
                    void handleSubmit();
                  }
                }}
                aria-label="Description"
                placeholder="Example: a visual explainer about how photosynthesis works. Show the main stages (light reaction and Calvin cycle), the inputs (sunlight, water, CO2) and outputs (glucose, oxygen), with a plant cell diagram in the centre and arrows for the flow of energy."
                className="min-h-[250px] resize-none bg-secondary/20 pb-8"
                disabled={isEnhancing || isGenerating}
              />
              <div className={`absolute bottom-3 right-3 font-mono tabular text-xs ${wordCount > 2000 ? 'text-destructive' : wordCount > 1800 ? 'text-warning' : 'text-muted-foreground'}`}>
                {wordCount} / 2000 words
              </div>
            </div>

            <div className="mt-4">
              <Button variant="outline" size="sm" onClick={() => setShowTemplates(true)}>
                <FileText className="w-4 h-4 mr-2" />
                Load an example
              </Button>
            </div>
          </div>

          {/* Step 2.5: Reference Images (optional), routes to the GPT Image 2.5 edit endpoint */}
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Reference images <span className="text-sm font-normal text-muted-foreground">(optional)</span></h2>
            <p className="mb-4 mt-1 text-sm text-muted-foreground">
              Upload up to 4 images to anchor brand, style, characters, or layouts.
              When references are present, the model uses GPT Image 2.5's edit mode.
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {referenceImages.map((ref, idx) => (
                <div key={ref.url} className="relative group aspect-square overflow-hidden rounded-xl border border-border bg-secondary/20">
                  <img src={ref.previewUrl} alt={`reference ${idx + 1}`} className="w-full h-full object-cover" />
                  <button
                    type="button"
                    onClick={() => removeReference(idx)}
                    className="glass absolute top-1 right-1 rounded-md p-1 text-foreground transition-opacity duration-150 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:opacity-0 sm:group-hover:opacity-100"
                    aria-label="Remove reference"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}

              {referenceImages.length < 4 && (
                <button
                  type="button"
                  onClick={referencePicker.open}
                  {...referencePicker.dropProps}
                  disabled={isUploadingRef || isEnhancing || isGenerating}
                  className={`flex aspect-square flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-secondary/20 transition-colors duration-150 hover:border-foreground/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed ${referencePicker.dragOver ? 'border-primary' : 'border-border'}`}
                >
                  {isUploadingRef ? (
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  ) : (
                    <Upload className="h-5 w-5 text-muted-foreground" />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {isUploadingRef ? 'Uploading' : <>Add image <span className="tabular">({referenceImages.length}/4)</span></>}
                  </span>
                </button>
              )}
            </div>

            {referencePicker.dialog}
          </div>

          {/* Step 3: Style & Settings */}
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Style and settings</h2>
            <p className="mb-4 mt-1 text-sm text-muted-foreground">The look, frame and file format.</p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {/* Visual Style */}
              <div className="space-y-2">
                <Label>Visual style</Label>
                <Select value={style} onValueChange={setStyle}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VISUAL_STYLES.map((s) => (
                      <SelectItem key={s.value} value={s.value}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {VISUAL_STYLES.find(s => s.value === style)?.description}
                </p>
              </div>

              {/* Aspect Ratio */}
              <div className="space-y-2">
                <Label>Aspect ratio</Label>
                <Select value={aspectRatio} onValueChange={setAspectRatio}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ASPECT_RATIOS.map((ar) => (
                      <SelectItem key={ar.value} value={ar.value}>
                        {ar.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {ASPECT_RATIOS.find(ar => ar.value === aspectRatio)?.description}
                </p>
              </div>

              {/* Resolution */}
              <div className="space-y-2">
                <Label>Resolution</Label>
                <Select value={resolution} onValueChange={setResolution}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RESOLUTIONS.map((r) => {
                      const cost = getModelCost(explainerKey(r.value, withReferences));
                      return (
                        <SelectItem key={r.value} value={r.value}>
                          {r.label}
                          {cost !== undefined && (
                            <span className="ml-2 font-mono tabular text-xs text-muted-foreground">
                              {formatUsd(cost)}
                            </span>
                          )}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {RESOLUTIONS.find(r => r.value === resolution)?.description}
                </p>
              </div>

              {/* Output Format */}
              <div className="space-y-2">
                <Label>Output format</Label>
                <Select value={outputFormat} onValueChange={setOutputFormat}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="png">PNG, best quality</SelectItem>
                    <SelectItem value="jpeg">JPEG, smaller file</SelectItem>
                    <SelectItem value="webp">WebP, modern format</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {outputFormat === 'png' ? 'Best for transparency' : outputFormat === 'jpeg' ? 'Smaller file size' : 'Modern compression'}
                </p>
              </div>
            </div>

            {/* AI Enhancement Toggle */}
            <div className="mt-6 rounded-lg border border-border bg-secondary/40 p-4">
              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex items-center gap-3">
                  <Sparkles className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <span className="font-medium">Improve the prompt first</span>
                    <p className="text-sm text-muted-foreground">Rewrites your description in more detail. You review it before generating.</p>
                  </div>
                </div>
                <Switch checked={enhanceEnabled} onCheckedChange={setEnhanceEnabled} aria-label="Improve the prompt first" />
              </label>
              {qa?.available && (
                <label className="mt-4 flex cursor-pointer items-center justify-between border-t border-border pt-4">
                  <div>
                    <span className="font-medium">Check spelling</span>
                    <p className="text-sm text-muted-foreground">
                      After the visual is saved, the words in quotes are read back letter by letter.{' '}
                      <span className="font-mono tabular text-xs">{formatUsd(qa.estimated_usd)}</span>.
                    </p>
                  </div>
                  <Switch checked={checkSpelling} onCheckedChange={setCheckSpelling} aria-label="Check spelling" />
                </label>
              )}
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Action Button */}
          <div className="flex flex-col items-center pt-2">
            <Button
              size="lg"
              className="min-w-[13rem] px-8"
              onClick={handleSubmit}
              disabled={!prompt.trim() || isEnhancing || isGenerating}
            >
              {isEnhancing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Improving prompt
                </>
              ) : isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating
                </>
              ) : (
                enhanceEnabled ? 'Improve prompt' : 'Generate visual'
              )}
            </Button>
            {explainerCost !== undefined && (
              <p className="mt-2 text-xs text-muted-foreground">
                <span className="font-mono tabular text-foreground">{formatUsd(explainerCost)}</span>{' '}
                per generation at {resolution}
                {withReferences ? ' with reference images' : ''}
                {spellingOn ? ', spelling check included' : ''}
              </p>
            )}
          </div>

          {/* Enhanced Prompt Container */}
          {showEnhanced && (
            <div className={`mt-8 rounded-xl border border-border bg-secondary/20 p-6 ${isGenerating ? 'beam-border' : ''}`}>
              <h3 className="mb-1 text-lg font-semibold tracking-tight">Improved prompt</h3>
              <p className="text-sm text-muted-foreground mb-4">Edit it if you like, then generate. Ctrl+Enter generates.</p>

              <div className="relative">
                <Textarea
                  value={enhancedPrompt}
                  onChange={(e) => setEnhancedPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (isSubmitShortcut(e) && !isGenerating) {
                      e.preventDefault();
                      void handleGenerate(true);
                    }
                  }}
                  aria-label="Improved prompt"
                  className="min-h-[250px] resize-none bg-secondary/20 pb-8"
                />
                <div className="absolute bottom-3 right-3 font-mono tabular text-xs text-muted-foreground">
                  {enhancedWordCount} words
                </div>
              </div>

              <div className="flex flex-wrap justify-center gap-3 mt-6">
                <Button variant="outline" size="lg" onClick={handleEnhance} disabled={isEnhancing || isGenerating}>
                  {isEnhancing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  Rewrite again
                </Button>
                <Button size="lg" className="min-w-[11rem]" onClick={() => handleGenerate(true)} disabled={isGenerating}>
                  {isGenerating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Generating
                    </>
                  ) : (
                    'Generate visual'
                  )}
                </Button>
              </div>
              {isGenerating && (
                <p className="mt-3 text-center text-xs text-muted-foreground" role="status" aria-live="polite">
                  Generating, usually under a minute. <span className="font-mono tabular">{formatElapsed(elapsed)}</span>
                </p>
              )}
            </div>
          )}

          {/* Loading Indicator */}
          {isGenerating && !showEnhanced && (
            <div className="beam-border mt-8 rounded-xl border border-border bg-secondary/20 p-6" role="status" aria-live="polite">
              <p className="mb-4 text-center text-sm text-muted-foreground">
                Generating your visual, usually under a minute.{' '}
                <span className="font-mono tabular text-foreground">{formatElapsed(elapsed)}</span>
              </p>
              <div
                className="shimmer max-h-[70vh] w-full max-w-4xl rounded-xl bg-muted"
                style={{ aspectRatio: ratioToCss(aspectRatio, '16 / 9') }}
              />
            </div>
          )}

          {/* Result Section */}
          {result && (
            <motion.div
              className="mt-8 rounded-xl border border-border bg-secondary/20 p-6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
            >
              <div className="relative max-w-4xl overflow-hidden rounded-xl border border-border">
                <img
                  src={result.url}
                  alt="Generated visual"
                  width={result.width}
                  height={result.height}
                  className="w-full h-auto"
                />
              </div>

              {/* Downloads, always visible */}
              <div className="mt-3 flex max-w-4xl flex-wrap items-center justify-between gap-2">
                <span className="font-mono tabular text-xs text-muted-foreground">{result.width} x {result.height}px</span>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleDownload('png')}>
                    <Download className="w-4 h-4" /> PNG
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleDownload('webp')}>
                    <Download className="w-4 h-4" /> WebP
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleDownload('jpeg')}>
                    <Download className="w-4 h-4" /> JPEG
                  </Button>
                </div>
              </div>

              {result.quality && (
                <ImageQuality
                  key={result.id}
                  image={result}
                  onFixed={(fixed) =>
                    setResult({ url: fixed.url, width: fixed.width ?? result.width, height: fixed.height ?? result.height,
                      id: fixed.id, quality: fixed.quality ?? null })
                  }
                  className="mt-3 max-w-4xl"
                />
              )}

              <div className="flex flex-wrap justify-center gap-4 mt-6">
                <Button variant="outline" asChild>
                  <a href={`/gallery`}>
                    <ImageIcon className="w-4 h-4 mr-2" />
                    View in gallery
                  </a>
                </Button>
                <Button variant="secondary" onClick={handleCreateAnother}>
                  <Plus className="w-4 h-4 mr-2" />
                  Start a new visual
                </Button>
              </div>
            </motion.div>
          )}
        </CardContent>
        </Card>
      </StaggerItem>

      {/* Template Modal */}
      <Dialog open={showTemplates} onOpenChange={setShowTemplates}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Examples</DialogTitle>
          </DialogHeader>
          <p className="mb-4 text-sm text-muted-foreground">Choose an example to load it into the description. It replaces what is there.</p>

          <div className="space-y-3">
            {CONTENT_TYPES.map((type) => {
              const Icon = type.icon;
              const template = EXAMPLE_TEMPLATES[type.value];
              if (!template) return null;

              return (
                <button
                  type="button"
                  key={type.value}
                  className="block w-full cursor-pointer rounded-xl border border-border bg-card p-4 text-left transition-colors duration-150 hover:border-foreground/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => loadTemplate(type.value)}
                >
                  <div className="flex items-start gap-3">
                    <Icon className="w-5 h-5 text-muted-foreground mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <h4 className="font-semibold tracking-tight">{type.label}</h4>
                      <p className="text-sm text-muted-foreground mb-2">{type.description}</p>
                      <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-border bg-secondary/40 p-3 font-sans text-xs text-muted-foreground">
                        {template}
                      </pre>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>
    </Stagger>
  );
}
