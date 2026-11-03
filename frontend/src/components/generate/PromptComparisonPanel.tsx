import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { X, Sparkles, FileText } from 'lucide-react';

interface PromptComparisonPanelProps {
  originalPrompt: string;
  enhancedPrompt: string;
  selectedPromptType: 'original' | 'enhanced';
  onEnhancedPromptChange: (prompt: string) => void;
  onSelectedPromptTypeChange: (type: 'original' | 'enhanced') => void;
  onClose: () => void;
}

export function PromptComparisonPanel({
  originalPrompt,
  enhancedPrompt,
  selectedPromptType,
  onEnhancedPromptChange,
  onSelectedPromptTypeChange,
  onClose,
}: PromptComparisonPanelProps) {
  return (
    <div className="border rounded-lg bg-muted/30 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Choose a prompt</h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label="Close"
          className="h-7 w-7 p-0"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Side-by-side panels - stack on mobile */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Original Prompt Panel */}
        <div
          className={`relative rounded-lg border p-4 cursor-pointer transition-colors duration-150 ${
            selectedPromptType === 'original'
              ? 'border-primary bg-accent/40'
              : 'border-border hover:border-muted-foreground/50'
          }`}
          onClick={() => onSelectedPromptTypeChange('original')}
        >
          {/* Radio indicator */}
          <div className="flex items-center gap-2 mb-3">
            <div
              className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                selectedPromptType === 'original'
                  ? 'border-primary'
                  : 'border-muted-foreground/50'
              }`}
            >
              {selectedPromptType === 'original' && (
                <div className="w-2 h-2 rounded-full bg-primary" />
              )}
            </div>
            <Label className="text-sm font-medium flex items-center gap-1.5 cursor-pointer">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              Original prompt
            </Label>
          </div>

          {/* Original prompt text (read-only) */}
          <div className="bg-background rounded-md p-3 text-sm min-h-[100px] max-h-[200px] overflow-y-auto">
            {originalPrompt}
          </div>
        </div>

        {/* Enhanced Prompt Panel */}
        <div
          className={`relative rounded-lg border p-4 transition-colors duration-150 ${
            selectedPromptType === 'enhanced'
              ? 'border-primary bg-accent/40'
              : 'border-border hover:border-muted-foreground/50'
          }`}
        >
          {/* Radio indicator */}
          <div
            className="flex items-center gap-2 mb-3 cursor-pointer"
            onClick={() => onSelectedPromptTypeChange('enhanced')}
          >
            <div
              className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                selectedPromptType === 'enhanced'
                  ? 'border-primary'
                  : 'border-muted-foreground/50'
              }`}
            >
              {selectedPromptType === 'enhanced' && (
                <div className="w-2 h-2 rounded-full bg-primary" />
              )}
            </div>
            <Label className="text-sm font-medium flex items-center gap-1.5 cursor-pointer">
              <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
              Enhanced prompt
              <span className="text-xs text-muted-foreground font-normal">(editable)</span>
            </Label>
          </div>

          {/* Enhanced prompt textarea (editable) */}
          <Textarea
            value={enhancedPrompt}
            onChange={(e) => onEnhancedPromptChange(e.target.value)}
            onClick={() => onSelectedPromptTypeChange('enhanced')}
            className="min-h-[100px] max-h-[200px] text-sm resize-none"
            placeholder="The enhanced prompt appears here"
          />
        </div>
      </div>

      {/* Selection indicator */}
      <div className="text-xs text-muted-foreground text-center">
        {selectedPromptType === 'enhanced' ? (
          <span className="flex items-center justify-center gap-1">
            <Sparkles className="h-3 w-3" />
            Using enhanced prompt for generation
          </span>
        ) : (
          <span className="flex items-center justify-center gap-1">
            <FileText className="h-3 w-3" />
            Using original prompt for generation
          </span>
        )}
      </div>
    </div>
  );
}
