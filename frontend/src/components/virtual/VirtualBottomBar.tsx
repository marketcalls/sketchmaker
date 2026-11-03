import { useState } from 'react';
import { Shirt, Loader2, Settings2, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { EDIT_MODELS, type EditModelId } from '@/utils/models';
import { usePricingStore, editKey, formatUsd } from '@/stores/pricingStore';

const NUM_IMAGES_OPTIONS = [
  { value: '1', label: '1 image' },
  { value: '2', label: '2 images' },
  { value: '3', label: '3 images' },
  { value: '4', label: '4 images' },
];

const controlClass =
  'h-8 w-auto gap-1 rounded-md border border-border bg-transparent px-2.5 text-xs text-foreground hover:border-foreground/30';

const ASPECT_RATIOS = [
  { value: '16:9', label: '16:9 Wide' },
  { value: '9:16', label: '9:16 Portrait' },
  { value: '1:1', label: '1:1 Square' },
  { value: '4:5', label: '4:5' },
  { value: '3:4', label: '3:4' },
  { value: '4:3', label: '4:3' },
];

interface VirtualBottomBarProps {
  prompt: string;
  onPromptChange: (prompt: string) => void;
  aspectRatio: string;
  onAspectRatioChange: (ratio: string) => void;
  editModel: EditModelId;
  onEditModelChange: (model: EditModelId) => void;
  numImages: number;
  onNumImagesChange: (num: number) => void;
  useDressBackground: boolean;
  onUseDressBackgroundChange: (use: boolean) => void;
  seed: string;
  onSeedChange: (seed: string) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  canGenerate: boolean;
}

export function VirtualBottomBar({
  prompt,
  onPromptChange,
  aspectRatio,
  onAspectRatioChange,
  editModel,
  onEditModelChange,
  numImages,
  onNumImagesChange,
  useDressBackground,
  onUseDressBackgroundChange,
  seed,
  onSeedChange,
  onGenerate,
  isGenerating,
  canGenerate,
}: VirtualBottomBarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const maxImages = EDIT_MODELS.find((m) => m.value === editModel)?.maxImages ?? 4;
  const numImagesOptions = NUM_IMAGES_OPTIONS.filter((opt) => Number(opt.value) <= maxImages);
  // Try-On renders at 1K and is billed per output image, by edit model.
  const costs = usePricingStore((s) => s.costs);
  const perImage = (model: string): number | undefined => costs?.[editKey(model)];
  const selectedPerImage = perImage(editModel);
  const totalCost =
    selectedPerImage !== undefined ? selectedPerImage * Math.min(numImages, maxImages) : undefined;

  const handleModelChange = (value: string) => {
    const model = EDIT_MODELS.find((m) => m.value === value);
    if (!model) return;
    onEditModelChange(model.value);
    // Models that return one image per request are charged for one
    if (numImages > model.maxImages) onNumImagesChange(model.maxImages);
  };

  return (
    <div className="border-t border-border bg-background p-4">
      <div className="max-w-4xl mx-auto space-y-3">
        {/* Prompt Textarea */}
        <div className="relative">
          <Textarea
            placeholder="Optional: describe how the outfit should look. Leave empty to use the setting's defaults."
            aria-label="Try-on prompt"
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            rows={2}
            className="pr-4 sm:pr-40 resize-none text-base min-h-[80px] pb-14 sm:pb-3"
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
              aria-label={isGenerating ? 'Generating' : 'Try on'}
            >
              {isGenerating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Shirt className="h-4 w-4" />
              )}
            </Button>
            <Button
              className="hidden min-w-[8.5rem] sm:flex"
              onClick={onGenerate}
              disabled={!canGenerate || isGenerating}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating
                </>
              ) : (
                'Try on'
              )}
            </Button>
          </div>
        </div>

        {/* Inline Controls */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          {/* Edit Model */}
          <Select value={editModel} onValueChange={handleModelChange}>
            <SelectTrigger aria-label="Edit model" className={controlClass}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {EDIT_MODELS.map((m) => {
                const cost = perImage(m.value);
                return (
                  <SelectItem key={m.value} value={m.value}>
                    <span className="inline-flex w-full items-center gap-1.5">
                      {m.label}
                      {cost !== undefined && (
                        <span className="ml-auto pl-3 font-mono tabular text-[11px] text-muted-foreground">
                          {formatUsd(cost)} per image
                        </span>
                      )}
                    </span>
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>

          {/* Aspect Ratio */}
          <Select value={aspectRatio} onValueChange={onAspectRatioChange}>
            <SelectTrigger aria-label="Aspect ratio" className={controlClass}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASPECT_RATIOS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Number of Images */}
          <Select value={String(numImages)} onValueChange={(v) => onNumImagesChange(Number(v))}>
            <SelectTrigger aria-label="Number of images" className={controlClass}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {numImagesOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Use Dress Background Toggle */}
          <label className="flex h-8 cursor-pointer items-center gap-2 rounded-md border border-border px-2.5 text-xs">
            Outfit background
            <Switch
              checked={useDressBackground}
              onCheckedChange={onUseDressBackgroundChange}
              aria-label="Use the outfit photo's background"
              className="scale-75"
            />
          </label>

          {/* Advanced Settings Popover */}
          <Popover open={showAdvanced} onOpenChange={setShowAdvanced}>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" aria-label="More settings" className="h-8 gap-1 rounded-md border border-border px-2.5 text-xs text-foreground hover:border-foreground/30">
                <Settings2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">More</span>
                <ChevronDown className="h-3 w-3" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-72" align="start" side="top">
              <div className="space-y-4">
                <h4 className="font-medium text-sm">More settings</h4>

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
                  <p className="text-xs text-muted-foreground">The same seed repeats a result.</p>
                </div>
              </div>
            </PopoverContent>
          </Popover>

          {/* Images indicator */}
          <div className="ml-auto whitespace-nowrap text-xs text-muted-foreground">
            {numImages} variation{numImages > 1 ? 's' : ''}
            {totalCost !== undefined && (
              <span className="font-mono tabular text-foreground">
                {', '}
                {formatUsd(totalCost)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
