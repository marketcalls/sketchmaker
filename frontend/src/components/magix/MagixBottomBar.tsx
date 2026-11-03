import { useState } from 'react';
import { Sparkles, Loader2, Settings2, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

const ASPECT_RATIOS = [
  { value: 'auto', label: 'Auto' },
  { value: '1:1', label: '1:1 Square' },
  { value: '4:5', label: '4:5 Portrait' },
  { value: '3:4', label: '3:4' },
  { value: '2:3', label: '2:3' },
  { value: '9:16', label: '9:16 Story' },
  { value: '16:9', label: '16:9 Wide' },
];

const RESOLUTIONS = [
  { value: '1K', label: '1K' },
  { value: '2K', label: '2K' },
  { value: '4K', label: '4K' },
];

// Mode-specific option configurations
const BACKGROUND_OPTIONS = [
  { value: 'neutral_gray', label: 'Neutral Gray' },
  { value: 'clean_white', label: 'Clean White' },
  { value: 'soft_gradient', label: 'Soft Gradient' },
  { value: 'office_blur', label: 'Blurred Office' },
  { value: 'outdoor_blur', label: 'Blurred Outdoor' },
];

const AESTHETIC_OPTIONS = [
  { value: 'glamorous', label: 'Glamorous & Luxe' },
  { value: 'natural_beauty', label: 'Natural Beauty' },
  { value: 'golden_hour', label: 'Golden Hour Glow' },
  { value: 'urban_chic', label: 'Urban Chic' },
  { value: 'soft_dreamy', label: 'Soft & Dreamy' },
  { value: 'vibrant_bold', label: 'Vibrant & Bold' },
];

const DATING_VIBE_OPTIONS = [
  { value: 'confident_authentic', label: 'Confident & Authentic' },
  { value: 'playful_fun', label: 'Playful & Fun' },
  { value: 'warm_approachable', label: 'Warm & Approachable' },
  { value: 'adventurous', label: 'Adventurous Spirit' },
  { value: 'sophisticated', label: 'Sophisticated & Classy' },
  { value: 'casual_relaxed', label: 'Casual & Relaxed' },
];

const FOUNDER_VIBE_OPTIONS = [
  { value: 'visionary', label: 'Visionary Leader' },
  { value: 'approachable_ceo', label: 'Approachable CEO' },
  { value: 'tech_innovator', label: 'Tech Innovator' },
  { value: 'disruptor', label: 'Industry Disruptor' },
  { value: 'thought_leader', label: 'Thought Leader' },
  { value: 'creative_founder', label: 'Creative Founder' },
];

const AVATAR_STYLE_OPTIONS = [
  { value: 'semi_realistic', label: 'Semi-Realistic' },
  { value: '3d_pixar', label: '3D Pixar Style' },
  { value: 'anime', label: 'Anime Character' },
  { value: 'comic_book', label: 'Comic Book Hero' },
  { value: 'digital_art', label: 'Digital Art' },
  { value: 'fantasy', label: 'Fantasy Character' },
];

interface MagixBottomBarProps {
  prompt: string;
  onPromptChange: (prompt: string) => void;
  aspectRatio: string;
  onAspectRatioChange: (ratio: string) => void;
  resolution: string;
  onResolutionChange: (resolution: string) => void;
  seed: string;
  onSeedChange: (seed: string) => void;
  selectedMode: string;
  modeOptions: {
    background: string;
    aesthetic: string;
    datingVibe: string;
    founderVibe: string;
    avatarStyle: string;
  };
  onModeOptionChange: (key: string, value: string) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  canGenerate: boolean;
  imageCount: number;
}

export function MagixBottomBar({
  prompt,
  onPromptChange,
  aspectRatio,
  onAspectRatioChange,
  resolution,
  onResolutionChange,
  seed,
  onSeedChange,
  selectedMode,
  modeOptions,
  onModeOptionChange,
  onGenerate,
  isGenerating,
  canGenerate,
  imageCount,
}: MagixBottomBarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Determine which mode-specific option to show
  const getModeSpecificControl = () => {
    switch (selectedMode) {
      case 'corporate_headshot':
        return (
          <Select value={modeOptions.background} onValueChange={(v) => onModeOptionChange('background', v)}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue placeholder="Background" />
            </SelectTrigger>
            <SelectContent>
              {BACKGROUND_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      case 'influencer':
        return (
          <Select value={modeOptions.aesthetic} onValueChange={(v) => onModeOptionChange('aesthetic', v)}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue placeholder="Aesthetic" />
            </SelectTrigger>
            <SelectContent>
              {AESTHETIC_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      case 'dating':
        return (
          <Select value={modeOptions.datingVibe} onValueChange={(v) => onModeOptionChange('datingVibe', v)}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue placeholder="Vibe" />
            </SelectTrigger>
            <SelectContent>
              {DATING_VIBE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      case 'founder_headshot':
        return (
          <Select value={modeOptions.founderVibe} onValueChange={(v) => onModeOptionChange('founderVibe', v)}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue placeholder="Vibe" />
            </SelectTrigger>
            <SelectContent>
              {FOUNDER_VIBE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      case 'avatar':
        return (
          <Select value={modeOptions.avatarStyle} onValueChange={(v) => onModeOptionChange('avatarStyle', v)}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue placeholder="Style" />
            </SelectTrigger>
            <SelectContent>
              {AVATAR_STYLE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      default:
        return null;
    }
  };

  return (
    <div className="border-t border-border bg-background p-4">
      <div className="max-w-4xl mx-auto space-y-3">
        {/* Prompt Textarea */}
        <div className="relative">
          <Textarea
            placeholder="Describe what you want to create... (optional - mode defaults will be used)"
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            rows={2}
            className="pr-4 sm:pr-32 resize-none text-base min-h-[80px] pb-14 sm:pb-3"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (canGenerate) onGenerate();
              }
            }}
          />
          <div className="absolute right-2 bottom-2 flex gap-2">
            <Button
              size="sm"
              className="sm:hidden"
              onClick={onGenerate}
              disabled={!canGenerate || isGenerating}
            >
              {isGenerating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="lg"
              className="hidden sm:flex"
              onClick={onGenerate}
              disabled={!canGenerate || isGenerating}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-2" />
                  Generate
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Inline Controls */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          {/* Aspect Ratio */}
          <Select value={aspectRatio} onValueChange={onAspectRatioChange}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASPECT_RATIOS.map((ratio) => (
                <SelectItem key={ratio.value} value={ratio.value}>
                  {ratio.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Resolution */}
          <Select value={resolution} onValueChange={onResolutionChange}>
            <SelectTrigger className="w-auto h-7 sm:h-8 text-xs bg-muted border-0 px-2 sm:px-3">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RESOLUTIONS.map((res) => (
                <SelectItem key={res.value} value={res.value}>
                  {res.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Mode-specific control */}
          {getModeSpecificControl()}

          {/* Advanced Settings Popover */}
          <Popover open={showAdvanced} onOpenChange={setShowAdvanced}>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" className="h-7 sm:h-8 text-xs px-2 sm:px-3">
                <Settings2 className="h-3 w-3 sm:mr-1" />
                <span className="hidden sm:inline">Advanced</span>
                <ChevronDown className="h-3 w-3 ml-1" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-72" align="start" side="top">
              <div className="space-y-4">
                <h4 className="font-medium text-sm">Advanced Settings</h4>

                {/* Seed */}
                <div className="space-y-2">
                  <Label className="text-xs font-medium">Seed</Label>
                  <Input
                    type="number"
                    placeholder="Random (leave empty)"
                    value={seed}
                    onChange={(e) => onSeedChange(e.target.value)}
                    className="h-8 text-xs"
                  />
                  <p className="text-xs text-muted-foreground">Use same seed for reproducible results</p>
                </div>
              </div>
            </PopoverContent>
          </Popover>

          {/* Image count indicator */}
          <div className="ml-auto whitespace-nowrap font-mono text-xs text-muted-foreground">
            {imageCount} image{imageCount > 1 ? 's' : ''}
          </div>
        </div>
      </div>
    </div>
  );
}
